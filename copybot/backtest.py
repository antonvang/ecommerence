"""Backtest: hvad ville det have givet at kopiere dine wallets de sidste N dage?

1. Henter walletternes transaktioner fra Solana og finder deres køb/salg.
2. Henter minut-priser (GeckoTerminal) for de tokens, de handlede.
3. Afspiller det hele i tidsrækkefølge med forsinkelse, slippage og gebyrer.
Alt hentet gemmes i data/cache, så næste kørsel er hurtig.
"""
from __future__ import annotations

import copy
import os
import time

from engine import Engine
from market import BacktestMarket, Dex, Gecko
from report import print_report, trade_stats, max_drawdown
from solana_rpc import RPC
from store import Store
from swaps import WSOL, parse_swaps


def fetch_wallet_swaps(rpc, wallet, label, cutoff, max_tx, sol_usd, log):
    txs = rpc.history(wallet, cutoff)
    if txs is not None:
        swaps = []
        for tx in txs:
            try:
                swaps += parse_swaps(tx, wallet, sol_usd)
            except Exception as e:
                log(f"    sprang {((tx.get('transaction') or {}).get('signatures') or ['?'])[0][:10]}... over: {e}")
        return swaps, cutoff, len(txs)
    sigs, before = [], None
    done = False
    while len(sigs) < max_tx and not done:
        batch = rpc.signatures(wallet, before=before, limit=min(1000, max_tx - len(sigs)))
        if not batch:
            break
        for s in batch:
            if (s.get("blockTime") or 0) < cutoff:
                done = True
                break
            sigs.append(s)
        before = batch[-1]["signature"]
    ok = [s for s in sigs if s.get("err") is None]
    swaps = []
    for k, s in enumerate(ok, 1):
        if k % 50 == 0 or k == len(ok):
            log(f"    @{label}: transaktion {k}/{len(ok)}")
        try:
            swaps += parse_swaps(rpc.transaction(s["signature"]), wallet, sol_usd)
        except Exception as e:
            log(f"    sprang {s['signature'][:10]}... over: {e}")
    covered_from = min((s["blockTime"] for s in sigs if s.get("blockTime")), default=cutoff)
    return swaps, covered_from, len(sigs)


def candle_ranges(swaps, max_hold, now):
    first_buy, hi = {}, {}
    for s in sorted(swaps, key=lambda x: x.ts):
        if s.side == "buy":
            first_buy.setdefault(s.mint, s.ts)
            hi[s.mint] = max(hi.get(s.mint, 0), min(s.ts + max_hold * 3600 + 600, now))
        elif s.mint in first_buy:
            hi[s.mint] = max(hi.get(s.mint, 0), s.ts + 600)
    out = {}
    for m, t0 in first_buy.items():
        last_sell = max((s.ts for s in swaps if s.mint == m and s.side == "sell"), default=0)
        last_buy = max(s.ts for s in swaps if s.mint == m and s.side == "buy")
        t1 = last_sell + 600 if last_sell > last_buy else hi[m]
        out[m] = (t0 - 300, min(max(t1, t0 + 600), now))
    return out


def replay(cfg, wallets, swaps, market, store, delay, start_ts, end_ts):
    market.reset()
    eng = Engine(cfg, store, market, wallets, delay=delay, quiet=True)
    store.begin()
    store.set("mode", "BACKTEST")
    eng.start(start_ts)
    clock = start_ts

    def advance(t):
        nonlocal clock
        while clock < t:
            if not eng.has_open():
                clock = t
                eng.check(clock)
                break
            clock = min(clock + 60, t)
            eng.check(clock)

    for sw in sorted(swaps, key=lambda s: (s.ts, s.sig)):
        advance(sw.ts + delay)
        market.observe(sw)
        eng.on_swap(sw)
    advance(end_ts)
    eng.close_all(max(clock, end_ts))
    store.commit()
    return eng


def summary(store):
    pnls = [r[0] for r in store.q("SELECT pnl_usd FROM positions WHERE book='port' AND closed_ts IS NOT NULL ORDER BY closed_ts")]
    st = trade_stats(pnls)
    st["end"] = store.get("cash")
    st["max_dd"] = max_drawdown([r[0] for r in store.q("SELECT equity FROM equity ORDER BY ts")])
    st["fired"] = store.get("fired_count", 0)
    return st


def variants(cfg):
    def v(name, delay=None, **over):
        c = copy.deepcopy(cfg)
        for k, val in over.items():
            if k == "bot_pct":
                c["fees"]["bot_pct"] = val
            else:
                c[k] = val
        return name, c, delay
    return [
        v("Din config"),
        v("Videoens regel: 2 tab -> næste på listen", fire_after_losses=2, next_trader="list"),
        v("Fyr aldrig, følg #1 på listen", fire_after_losses=0, next_trader="list"),
        v("Bedste wallet (shadow), fyr aldrig", fire_after_losses=0, next_trader="best_shadow"),
        v("Hurtig bot: 3 sek forsinkelse", delay=3),
        v("Langsom: 30 sek forsinkelse", delay=30),
        v("Uden 1 % bot-gebyr", bot_pct=0.0),
    ]


def run_backtest(cfg, wallets, root, days=None, sweep=True, log=print):
    b = cfg["backtest"]
    days = days or b["days"]
    cache = os.path.join(root, "cache")
    rpc = RPC(cfg["rpc_url"], cfg["rpc_requests_per_second"], os.path.join(cache, "tx"), log=log)
    dex = Dex(os.path.join(cache, "dex"), log=log)
    gecko = Gecko(os.path.join(cache, "gecko"), log=log)
    now = int(time.time())
    cutoff = now - days * 86400

    log(f"1/4  SOL-pris for de sidste {days} dage ...")
    sol_pool = dex.sol_usdc_pool()
    sol = gecko.range(sol_pool, "hour", cutoff - 2 * 86400, now, WSOL)
    sol_hours = sorted((ts,) + c for ts, c in sol.items())
    if not sol_hours:
        raise SystemExit("Kunne ikke hente SOL-priser fra GeckoTerminal. Prøv igen om lidt.")
    market0 = BacktestMarket({}, sol_hours, {})

    log(f"2/4  Henter walletternes handler (op til {b['max_tx_per_wallet']} transaktioner pr. wallet) ...")
    all_swaps, coverage = [], {}
    for w in wallets:
        swaps, frm, n = fetch_wallet_swaps(rpc, w["addr"], w["label"], cutoff, b["max_tx_per_wallet"], market0.sol_usd, log)
        coverage[w["addr"]] = frm
        buys = sum(1 for s in swaps if s.side == "buy")
        days_cov = (now - frm) / 86400
        note = f"  (loftet på {n} transaktioner nået: dækker kun {days_cov:.1f} dage)" if n >= b["max_tx_per_wallet"] and frm > cutoff else ""
        log(f"    @{w['label']}: {n} transaktioner, {buys} køb, {len(swaps) - buys} salg{note}")
        all_swaps += swaps
    if not all_swaps:
        raise SystemExit("Fandt ingen køb/salg. Er adresserne i wallets.txt rigtige Solana-wallets, der handler memecoins?")

    c = cfg
    wanted = sorted({s.mint for s in all_swaps if s.side == "buy" and s.quote_usd >= c["min_leader_buy_usd"]
                     and (s.reserve_usd is None or 2 * s.reserve_usd >= c["min_liquidity_usd"] * 0.5)})
    log(f"3/4  Priser for {len(wanted)} tokens (ca. {len(wanted) * 2.2 / 60:.0f} min første gang, cachet bagefter) ...")
    pools = dex.pairs(wanted, use_cache=True)
    symbols = {m: ((pools[m][0].get("baseToken") or {}).get("symbol") or m[:4]) if pools.get(m) else m[:4] for m in wanted}
    ranges = candle_ranges([s for s in all_swaps if s.mint in set(wanted)], c["max_hold_hours"], now)
    candles = {}
    for k, m in enumerate(wanted, 1):
        if k % 10 == 0 or k == len(wanted):
            log(f"    token {k}/{len(wanted)}")
        addrs = [p["pairAddress"] for p in pools.get(m) or []]
        if addrs and m in ranges:
            candles[m] = gecko.candles_for(m, addrs, *ranges[m])
    market = BacktestMarket(candles, sol_hours, symbols)
    no_data = sum(1 for m in wanted if not candles.get(m))
    if no_data:
        log(f"    {no_data} tokens havde ingen prisdata (typisk døde/fjernede coins) og tælles som 'ingen prisdata'.")

    log("4/4  Afspiller handlerne ...")
    start_ts = min(coverage.values())
    db_path = os.path.join(root, "backtest.db")
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass
    store = Store(db_path)
    replay(cfg, wallets, all_swaps, market, store, b["copy_delay_seconds"], start_ts, now)
    print_report(store, f"BACKTEST  {days} dage  ·  forsinkelse {b['copy_delay_seconds']} sek  ·  {len(wallets)} wallets", log)

    if sweep:
        log("")
        log(" Sammenligning af regler (samme data):")
        log(f" {'variant':<44}{'handler':>8}{'vind%':>7}{'netto $':>10}{'PF':>6}{'DD %':>6}{'fyret':>6}")
        for name, vc, dl in variants(cfg):
            st = summary_of(vc, wallets, all_swaps, market, b["copy_delay_seconds"] if dl is None else dl, start_ts, now)
            pf = "inf" if st["pf"] == float("inf") else f"{st['pf']:.2f}"
            log(f" {name[:43]:<44}{st['n']:>8}{st['win_rate']:>7.0f}{st['net']:>10.2f}{pf:>6}{st['max_dd']:>6.0f}{st['fired']:>6}")
        sh = trade_stats([r[0] for r in store.q("SELECT pnl_usd FROM positions WHERE book='shadow' AND closed_ts IS NOT NULL")])
        pf = "inf" if sh["pf"] == float("inf") else f"{sh['pf']:.2f}"
        log(f" {'Kopiér ALLE wallets, $' + str(cfg['shadow_trade_usd']) + ' pr. handel':<44}{sh['n']:>8}{sh['win_rate']:>7.0f}{sh['net']:>10.2f}{pf:>6}{'-':>6}{'-':>6}")
        log("")
        log(" HUSK: wallets fra en leaderboard er valgt, fordi de vandt i netop denne periode.")
        log(" Backtesten er derfor for optimistisk. Er den negativ, så er svaret nej.")
        log(" Er den positiv, så kør paper trading (valg 2) i 1-2 uger for at få det ærlige svar.")
    store.close()
    log("")
    log(f" Se backtesten i dashboardet: vælg 3 i START_COPYBOT.bat")


def summary_of(cfg, wallets, swaps, market, delay, start_ts, end_ts):
    st = Store(":memory:")
    replay(cfg, wallets, swaps, market, st, delay, start_ts, end_ts)
    res = summary(st)
    st.close()
    return res
