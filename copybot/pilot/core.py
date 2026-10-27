"""Amendment 29: one pilot round, the hard stops, the append-only ledger and the live-mode checks."""
import datetime
import fcntl
import json
import os
import random
import statistics
import time

import pilot as P
from pilot.exchange import floor_step


class Stopped(Exception):
    pass


def k3_window(now):
    """Amendment 22 windows: every even UTC hour ± 35 min (real and placebo rounds alike)."""
    g = time.gmtime(now)
    return (g.tm_hour % 2 == 0 and g.tm_min < 35) or (g.tm_hour % 2 == 1 and g.tm_min >= 25)


class Ledger:
    def __init__(self, data=P.DATA):
        self.data = data
        os.makedirs(data, exist_ok=True)
        self.path, self.state_path = os.path.join(data, "ledger.jsonl"), os.path.join(data, "state.json")

    def append(self, **row):
        row = {"ts": round(time.time(), 3), **row}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return row

    def rows(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]

    def state(self):
        if not os.path.exists(self.state_path):
            return {"stopped": None}
        with open(self.state_path, encoding="utf-8") as fh:
            return json.load(fh)

    def set_state(self, **kv):
        s = {**self.state(), **kv}
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(s, fh)
        os.replace(tmp, self.state_path)
        return s

    def stop(self, reason):
        self.set_state(stopped=reason, stopped_at=time.time())
        self.append(kind="stop", reason=reason)
        raise Stopped(reason)

    def results(self, dry):
        return [r for r in self.rows() if r.get("kind") == "result" and r.get("dry") == dry]


def realized(ledger, dry):
    return sum(r["pnl_usdt"] for r in ledger.results(dry))


def bp(x):
    return round(x * 1e4, 2)


def play(ex, ledger, rng, now=time.time, sleep=time.sleep):
    """One round (amendment 29 point 4). Returns the result row, or None when the round was skipped."""
    dry = ex.dry
    st = ledger.state()
    if st.get("stopped"):
        raise Stopped(st["stopped"])
    if -realized(ledger, dry) >= P.LOSS_CAP_USDT - P.LOSS_BUFFER_USDT:
        ledger.stop(f"tabsloft: realiseret {realized(ledger, dry):.2f} USDT")
    if len(ledger.results(dry)) >= P.MAX_ROUNDS:
        ledger.stop("højst 80 runder nået")
    if P.ROUND_USDT > P.MAX_ORDER_USDT:
        ledger.stop("rundebeløb over største ordre")
    symbol, mode = rng.choice(P.SYMBOLS), rng.choice(("taker", "maker"))
    f = ex.filters(symbol)
    skew = ex.server_ms() - now() * 1000
    if abs(skew) > P.MAX_SKEW_MS:
        ledger.stop(f"urforskel {skew:.0f} ms")
    book = ex.book(symbol)
    mid = (book["bid"] + book["ask"]) / 2
    spread = (book["ask"] - book["bid"]) / mid
    rid = f"{'D' if dry else 'L'}{len([r for r in ledger.rows() if r.get('kind') == 'plan']) + 1}"
    plan = dict(kind="plan", round=rid, dry=dry, symbol=symbol, mode=mode, quote=P.ROUND_USDT, bid=book["bid"],
                ask=book["ask"], mid=mid, spread_bp=bp(spread), skew_ms=round(skew))
    if spread > P.MAX_SPREAD:
        ledger.append(**plan, skipped="spread")
        return None
    ledger.append(**plan)                                       # logged before anything is sent
    before = ex.balance(f["base"])
    buy = None
    try:
        if mode == "taker":
            buy = ex.buy_market_quote(symbol, P.ROUND_USDT)
        else:
            qty = floor_step(P.ROUND_USDT / book["bid"], f["step"])
            if qty * book["bid"] > P.MAX_ORDER_USDT:
                ledger.stop("ordrebeløb over største ordre")
            o = ex.buy_limit_maker(symbol, book["bid"], qty)
            t0 = now()
            buy = ex.order_status(symbol, o["order_id"])
            while buy["status"] not in ("FILLED", "REJECTED", "EXPIRED") and now() - t0 < P.MAKER_TIMEOUT_S:
                sleep(P.POLL_S)
                buy = ex.order_status(symbol, o["order_id"])
            if buy["status"] not in ("FILLED", "REJECTED", "EXPIRED"):
                ex.cancel(symbol, o["order_id"])
                buy = ex.order_status(symbol, o["order_id"])    # a partial fill before the cancel counts
        if not buy["qty"]:
            return ledger.append(kind="result", round=rid, dry=dry, symbol=symbol, mode=mode, filled=False,
                                 status=buy["status"], pnl_usdt=0.0)
        sleep(P.HOLD_S)
        sell_mid_book = ex.book(symbol)
        sell_mid = (sell_mid_book["bid"] + sell_mid_book["ask"]) / 2
        held = ex.balance(f["base"]) - before
        qty = floor_step(min(held, buy["qty"]), f["step"])
        sell = ex.sell_market(symbol, qty) if qty * sell_mid_book["bid"] >= f["min_notional"] else None
    except Stopped:
        raise
    except Exception as e:                                      # noqa: BLE001 - a failure may leave a position
        _flatten(ex, ledger, symbol, f, before, rid, e)
        return None
    after = ex.balance(f["base"])
    sold = sell["qty"] if sell else 0.0
    if not (0.99 * buy["qty"] - f["step"] <= held <= buy["qty"] + f["step"]) or \
            abs(after - (before + held - sold)) > f["step"] * 1.01:
        ledger.stop(f"beholdning {f['base']}: før {before}, købt {buy['qty']}, holdt {held}, solgt {sold}, efter {after}")
    pnl = (sell["quote"] if sell else 0.0) - buy["quote"] - buy["fee_usdt"] - (sell["fee_usdt"] if sell else 0.0)
    dust_usdt = (held - sold) * sell_mid
    row = ledger.append(
        kind="result", round=rid, dry=dry, symbol=symbol, mode=mode, filled=True, status=buy["status"],
        buy_px=buy["avg_px"], buy_qty=buy["qty"], buy_quote=buy["quote"], buy_fee_usdt=buy["fee_usdt"],
        buy_slip_bp=bp((buy["avg_px"] - mid) / mid), sell_mid=sell_mid,
        sell_px=sell["avg_px"] if sell else None, sell_qty=sell["qty"] if sell else 0.0,
        sell_slip_bp=bp((sell_mid - sell["avg_px"]) / sell_mid) if sell else None,
        sell_fee_usdt=sell["fee_usdt"] if sell else 0.0, dust_qty=held - sold, dust_usdt=dust_usdt,
        pnl_usdt=pnl, cost_bp=bp(-(pnl + dust_usdt) / buy["quote"]) if buy["quote"] else None,
        fee_assumed=bool(buy.get("fee_assumed")))
    if -realized(ledger, dry) >= P.LOSS_CAP_USDT - P.LOSS_BUFFER_USDT:
        ledger.stop(f"tabsloft: realiseret {realized(ledger, dry):.2f} USDT")
    return row


def _flatten(ex, ledger, symbol, f, before, rid, err):
    """An error during a round: sell whatever was bought (one attempt); stop if a position was or may be left."""
    try:
        held = ex.balance(f["base"]) - before
    except Exception as e:                                      # noqa: BLE001
        ledger.stop(f"fejl {err!r:.150}; beholdning ukendt ({e!r:.80})")
    if held * ex.book(symbol)["bid"] < f["min_notional"]:
        ledger.append(kind="error", round=rid, error=repr(err)[:200], position=False)
        return
    try:
        sold = ex.sell_market(symbol, floor_step(held, f["step"]))
        ledger.append(kind="error", round=rid, error=repr(err)[:200], position=True, flattened=sold["qty"])
    except Exception as e:                                      # noqa: BLE001
        ledger.append(kind="error", round=rid, error=repr(err)[:200], position=True, flatten_error=repr(e)[:200])
    ledger.stop(f"fejl med åben position i {symbol}: {err!r:.150}")


def dry_evidence(ledger):
    """Amendment 29 point 8: >= 20 dry rounds over >= 48 h, no stop."""
    res = ledger.results(True)
    stops = [r for r in ledger.rows() if r.get("kind") == "stop"]
    hours = (res[-1]["ts"] - res[0]["ts"]) / 3600 if len(res) > 1 else 0
    ok = len(res) >= P.DRY_MIN_ROUNDS and hours >= P.DRY_MIN_HOURS and not stops
    return ok, {"dry_rounds": len(res), "hours": round(hours, 1), "stops": len(stops)}


def confirm_path(ledger, day=None):
    return os.path.join(ledger.data, f"confirm-{day or datetime.date.today().isoformat()}")


def live_blockers(ledger, key_path=P.KEY_PATH, terms=P.TERMS_DOC):
    """Every condition of amendment 29 point 9 that does not hold (an empty list allows a live run)."""
    out = []
    ok, ev = dry_evidence(ledger)
    if not ok:
        out.append(f"tør kørsel ikke grøn: {ev}")
    if not os.path.exists(key_path):
        out.append("ingen nøglefil")
    elif os.stat(key_path).st_mode & 0o077:
        out.append("nøglefilen skal have rettigheder 600")
    if not os.path.exists(terms):
        out.append("vilkår og skat ikke dokumenteret")
    if not os.path.exists(confirm_path(ledger)):
        out.append("ingen bekræftelse fra brugeren i dag (python3 -m pilot confirm-today)")
    first = next((r["ts"] for r in ledger.results(False)), None)
    if first and time.time() - first > P.MAX_LIVE_DAYS * 86400:
        out.append("5 døgn fra første rigtige ordre er gået")
    if ledger.state().get("stopped"):
        out.append(f"stoppet: {ledger.state()['stopped']}")
    return out


def human_typed(phrase, inp=input, tty=None):
    """True only in an interactive terminal where the exact phrase was typed."""
    if not (tty if tty is not None else os.isatty(0)):
        return False
    return inp(f'Skriv "{phrase}": ').strip() == phrase


def report(ledger):
    out = {}
    for dry in (True, False):
        res = ledger.results(dry)
        if not res:
            continue
        d = {"rounds": len(res), "realized_usdt": round(sum(r["pnl_usdt"] for r in res), 4)}
        for mode in ("taker", "maker"):
            m = [r for r in res if r["mode"] == mode]
            filled = [r for r in m if r.get("filled")]
            row = {"n": len(m), "filled": len(filled)}
            for k in ("buy_slip_bp", "sell_slip_bp", "cost_bp"):
                xs = sorted(r[k] for r in filled if r.get(k) is not None)
                if xs:
                    row[k] = {"mean": round(statistics.mean(xs), 2), "median": round(statistics.median(xs), 2),
                              "p95": xs[min(len(xs) - 1, int(0.95 * len(xs)))]}
            d[mode] = row
        out["dry" if dry else "live"] = d
    out["state"] = ledger.state()
    return out


def run(ex, ledger, rounds, rng=None, now=time.time, sleep=time.sleep):
    """Rounds spaced 30-120 min apart, never inside a K3 window; one process at a time."""
    rng = rng or random.Random()
    lock = open(os.path.join(ledger.data, "run.lock"), "w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    ledger.append(kind="run", dry=ex.dry, rounds=rounds)
    done = 0
    while done < rounds:
        while k3_window(now()) or k3_window(now() + P.MAKER_TIMEOUT_S + P.HOLD_S + 30):
            sleep(60)
        if play(ex, ledger, rng, now, sleep) is not None:
            done += 1
        if done < rounds:
            sleep(rng.uniform(P.MIN_GAP_S, P.MAX_GAP_S))
    return done
