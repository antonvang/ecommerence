"""Kopi-motoren. Samme kode bruges i backtest og paper trading.

To "bøger":
  shadow: hver wallet kopieres med et fast lille beløb. Det er målestokken, der viser,
          hvad det rent faktisk giver at kopiere netop den wallet (efter forsinkelse og gebyrer).
  port:   den rigtige (paper) konto. Følger én wallet ad gangen og fyrer den efter N tab i træk.
"""
from __future__ import annotations

import statistics
import time
from datetime import datetime


class Engine:
    def __init__(self, cfg, store, market, wallets, delay=0, live=False, quiet=True, log=print):
        self.cfg = cfg
        self.s = store
        self.m = market
        self.wallets = wallets
        self.addrs = [w["addr"] for w in wallets]
        self.label = {w["addr"]: w["label"] for w in wallets}
        self.delay = delay
        self.live = live
        self.quiet = quiet
        self.log = log
        f = cfg["fees"]
        self.fee_pct = (f["dex_pct"] + f["bot_pct"] + f["mev_slippage_pct"]) / 100.0
        self.net_fee_sol = f["network_fee_sol"]
        self._last_snap = 0

    # ---------- tilstand ----------
    @property
    def active(self):
        return self.s.get("active")

    def _lbl(self, a):
        return "@" + self.label.get(a, a[:6])

    def start(self, ts):
        self.s.set("wallets", self.wallets)
        self.s.set("config", self.cfg)
        if self.s.get("cash") is None:
            sb = float(self.cfg["start_balance_usd"])
            for k, v in (("cash", sb), ("start_balance", sb), ("started_ts", ts), ("fired", []),
                         ("streak", 0), ("fired_count", 0), ("active", None), ("skips", {})):
                self.s.set(k, v)
            self._event(ts, "start", None, f"Start med ${sb:.2f} (paper) · {len(self.wallets)} wallets")
            self._set_active(self._choose_next(ts), ts)
            self._snap(ts, force=True)

    def equity(self):
        r = self.s.one("SELECT COALESCE(SUM(tokens_left*last_price),0) FROM positions WHERE book='port' AND closed_ts IS NULL")
        return self.s.get("cash", 0.0) + r[0]

    def has_open(self):
        return self.s.one("SELECT 1 FROM positions WHERE closed_ts IS NULL LIMIT 1") is not None

    def _now(self, ts):
        return max(int(time.time()), ts) if self.live else ts + self.delay

    def _event(self, ts, kind, wallet, text, pnl=None):
        self.s.x("INSERT INTO events(ts,kind,wallet,text,pnl) VALUES(?,?,?,?,?)", ts, kind, wallet, text, pnl)
        if not self.quiet:
            p = "" if pnl is None else f"  {pnl:+.2f} USD"
            self.log(f"{datetime.fromtimestamp(ts):%H:%M:%S} [{kind.upper()}] {text}{p}")

    def _snap(self, ts, force=False):
        if force or ts - self._last_snap >= self.cfg["snapshot_seconds"]:
            self._last_snap = ts
            self.s.x("INSERT INTO equity(ts,equity,wallet) VALUES(?,?,?)", ts, self.equity(), self.active)

    # ---------- hvem kopierer vi ----------
    def shadow_stats(self, ts):
        since = ts - self.cfg["rank_window_days"] * 86400
        out = {}
        for r in self.s.q("SELECT wallet, pnl_usd, closed_ts-opened_ts AS hold FROM positions "
                          "WHERE book='shadow' AND closed_ts IS NOT NULL AND closed_ts>=? AND closed_ts<=?", since, ts):
            d = out.setdefault(r["wallet"], {"n": 0, "pnl": 0.0, "holds": []})
            d["n"] += 1
            d["pnl"] += r["pnl_usd"]
            d["holds"].append(r["hold"] / 60.0)
        for d in out.values():
            d["med_hold_min"] = statistics.median(d["holds"])
        return out

    def _choose_next(self, ts):
        c = self.cfg
        fired = set(self.s.get("fired", []))
        cands = [a for a in self.addrs if a not in fired]
        if not cands:
            self.s.set("fired", [])
            cands = list(self.addrs)
            self._event(ts, "reset", None, "Alle wallets er fyret · starter forfra")
        if c["next_trader"] == "list":
            return cands[0] if cands else None
        if ts < self.s.get("started_ts", ts) + c["warmup_hours"] * 3600:
            return None
        stats = self.shadow_stats(ts)
        best, best_pnl = None, None
        for a in cands:
            st = stats.get(a)
            if not st or st["n"] < c["min_shadow_trades"] or st["med_hold_min"] < c["min_median_hold_minutes"]:
                continue
            if c["require_positive_shadow"] and st["pnl"] <= 0:
                continue
            if best is None or st["pnl"] > best_pnl:
                best, best_pnl = a, st["pnl"]
        return best

    def _set_active(self, addr, ts):
        self.s.set("active", addr)
        self.s.set("streak", 0)
        if addr:
            self._event(ts, "follow", addr, f"Følger nu {self._lbl(addr)}")
        else:
            self._event(ts, "pause", None, "Ingen wallet er god nok endnu · observerer kun")

    def _try_resume(self, ts):
        nxt = self._choose_next(ts)
        if nxt:
            self._set_active(nxt, ts)

    def _fire(self, ts):
        a = self.active
        fired = self.s.get("fired", [])
        fired.append(a)
        self.s.set("fired", fired)
        self.s.set("fired_count", self.s.get("fired_count", 0) + 1)
        self._event(ts, "fired", a, f"{self._lbl(a)}: {self.cfg['fire_after_losses']} tab i træk → fyret")
        self._set_active(self._choose_next(ts), ts)

    # ---------- handler ----------
    def on_swap(self, sw):
        if sw.wallet not in self.label:
            return
        if self.live:
            lat = self.s.get("latency", [])[-49:] + [max(int(time.time()) - sw.ts, 0)]
            self.s.set("latency", lat)
        if sw.side == "buy":
            self._buy(sw)
        else:
            self._sell(sw)

    def _open_rows(self, wallet, mint):
        return self.s.q("SELECT * FROM positions WHERE closed_ts IS NULL AND wallet=? AND mint=?", wallet, mint)

    def _reject(self, sw, q, size):
        c = self.cfg
        if q is None:
            return "ingen prisdata"
        if sw.quote_usd < c["min_leader_buy_usd"]:
            return "lille køb"
        r = q.reserve_usd
        if r is None:
            return "ukendt likviditet" if c["min_liquidity_usd"] > 0 else None
        if 2 * r < c["min_liquidity_usd"]:
            return "lav likviditet"
        if size / r * 100 > c["max_price_impact_pct"]:
            return "for høj slippage"
        return None

    def _buy(self, sw):
        t = self._now(sw.ts)
        if self._open_rows(sw.wallet, sw.mint):
            return  # walletten køber mere af noget, vi allerede har
        q = self.m.quote(sw.mint, t, sw)
        active = self.active
        port_size = self.equity() * self.cfg["position_pct"] / 100.0
        why = self._reject(sw, q, max(port_size, self.cfg["shadow_trade_usd"]))
        sym = q.symbol if q else sw.mint[:4]
        lbl = self._lbl(sw.wallet)
        if why:
            sk = self.s.get("skips", {})
            sk[why] = sk.get(why, 0) + 1
            self.s.set("skips", sk)
            if sw.wallet == active:
                self._event(t, "skip", sw.wallet, f"{lbl} købte ${sym} · springer over ({why})")
            return
        spot = max(q.price, sw.price_usd)  # vi kan ikke købe billigere end den, vi kopierer
        self._open("shadow", sw, t, spot, q, self.cfg["shadow_trade_usd"])
        if sw.wallet != active:
            return
        n_open = self.s.one("SELECT COUNT(*) FROM positions WHERE book='port' AND closed_ts IS NULL")[0]
        cash = self.s.get("cash")
        size = min(cash, port_size)
        if n_open >= self.cfg["max_open_positions"]:
            self._event(t, "skip", sw.wallet, f"{lbl} købte ${sym} · springer over (max {n_open} positioner)")
            return
        if size < self.cfg["min_trade_usd"]:
            self._event(t, "skip", sw.wallet, f"{lbl} købte ${sym} · springer over (ikke nok kontanter)")
            return
        self._open("port", sw, t, spot, q, size)
        self.s.set("cash", cash - size)
        self._event(t, "copy", sw.wallet, f"{lbl} købte ${sym} · vi køber for ${size:.2f}")
        self._snap(t, force=True)

    def _open(self, book, sw, t, spot, q, size):
        r = q.reserve_usd or self.cfg["fallback_reserve_usd"]
        nf = self.net_fee_sol * self.m.sol_usd(t)
        s_eff = max(size - nf, 0.0) * (1 - self.fee_pct)
        avg = spot * (1 + s_eff / r)  # x*y=k: gennemsnitsprisen stiger med ordrestørrelse / pool
        tokens = s_eff / avg if avg > 0 else 0.0
        if tokens <= 0:
            return
        self.s.x("INSERT INTO positions(book,wallet,mint,symbol,opened_ts,cost_usd,tokens,tokens_left,entry_price,"
                 "last_price,costs_usd,leader_entry) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                 book, sw.wallet, sw.mint, q.symbol, t, size, tokens, tokens, size / tokens, spot,
                 size - tokens * spot, sw.price_usd)

    def _sell(self, sw):
        rows = self._open_rows(sw.wallet, sw.mint)
        if not rows:
            return
        t = self._now(sw.ts)
        left = sw.leader_left
        frac = 1.0 if left <= sw.tokens * 0.02 else sw.tokens / (sw.tokens + left)
        q = self.m.quote(sw.mint, t, sw)
        spot = min(q.price, sw.price_usd) if q else sw.price_usd  # vi kan ikke sælge dyrere end den, vi kopierer
        r = (q.reserve_usd if q else None) or sw.reserve_usd
        for p in rows:
            n = p["tokens_left"] * frac
            if p["tokens_left"] - n < 0.05 * p["tokens"]:
                n = p["tokens_left"]
            self._exit(p, n, spot, r, t, "leader", leader_price=sw.price_usd)

    def _exit(self, p, n, spot, r, t, reason, leader_price=None):
        r = r if r and r > 0 else self.cfg["fallback_reserve_usd"]
        v = n * spot
        gross = v * r / (r + v) if v > 0 else 0.0
        nf = self.net_fee_sol * self.m.sol_usd(t)
        proceeds = max(gross * (1 - self.fee_pct) - nf, 0.0)
        left = p["tokens_left"] - n
        if left <= p["tokens"] * 1e-9:
            left = 0.0
        total = p["proceeds_usd"] + proceeds
        costs = p["costs_usd"] + (v - proceeds)
        lex = leader_price if leader_price is not None else p["leader_exit"]
        if p["book"] == "port":
            self.s.set("cash", self.s.get("cash") + proceeds)
        if left == 0.0:
            pnl = total - p["cost_usd"]
            self.s.x("UPDATE positions SET tokens_left=0, proceeds_usd=?, costs_usd=?, last_price=?, leader_exit=?, "
                     "closed_ts=?, pnl_usd=?, reason=? WHERE id=?", total, costs, spot, lex, t, pnl, reason, p["id"])
            self._closed(p, pnl, t, reason)
        else:
            self.s.x("UPDATE positions SET tokens_left=?, proceeds_usd=?, costs_usd=?, last_price=?, leader_exit=? "
                     "WHERE id=?", left, total, costs, spot, lex, p["id"])
            if p["book"] == "port":
                self._event(t, "partial", p["wallet"],
                            f"{self._lbl(p['wallet'])} solgte en del af ${p['symbol']} · vi sælger samme andel", proceeds)

    def _closed(self, p, pnl, t, reason):
        if p["book"] == "shadow":
            if self.active is None:
                self._try_resume(t)
            return
        lbl, sym = self._lbl(p["wallet"]), p["symbol"]
        text = {
            "leader": f"{lbl} solgte ${sym} · vi sælger",
            "stop": f"${sym} ramte stop-loss · vi sælger",
            "rug": f"${sym} likviditeten forsvandt (rug) · vi sælger",
            "timeout": f"${sym} holdt for længe · vi sælger",
            "end": f"${sym} lukket ved testens slutning",
        }[reason]
        self._event(t, "exit" if reason in ("leader", "end") else reason, p["wallet"], text, pnl)
        self._snap(t, force=True)
        if p["wallet"] == self.active:
            st = self.s.get("streak", 0) + 1 if pnl < 0 else 0
            self.s.set("streak", st)
            if 0 < self.cfg["fire_after_losses"] <= st:
                self._fire(t)

    def check(self, t):
        """Stop-loss, rug, max holdetid og balance-snapshot. Kaldes jævnligt."""
        if self.active is None:
            self._try_resume(t)
        c = self.cfg
        rows = self.s.q("SELECT * FROM positions WHERE closed_ts IS NULL")
        if rows:
            quotes = self.m.quotes(sorted({r["mint"] for r in rows}), t)
            for p in rows:
                q = quotes.get(p["mint"])
                age = t - p["opened_ts"]
                if q is None:
                    if age >= c["max_hold_hours"] * 3600:
                        self._exit(p, p["tokens_left"], p["last_price"], None, t, "timeout")
                    continue
                self.s.x("UPDATE positions SET last_price=? WHERE id=?", q.price, p["id"])
                if c["stop_loss_pct"] > 0 and q.price <= p["entry_price"] * (1 - c["stop_loss_pct"] / 100.0):
                    reason = "stop"
                elif q.reserve_usd is not None and 2 * q.reserve_usd < c["rug_liquidity_usd"]:
                    reason = "rug"
                elif age >= c["max_hold_hours"] * 3600:
                    reason = "timeout"
                else:
                    continue
                self._exit(p, p["tokens_left"], q.price, q.reserve_usd, t, reason)
        self._snap(t)

    def close_all(self, t):
        rows = self.s.q("SELECT * FROM positions WHERE closed_ts IS NULL")
        quotes = self.m.quotes(sorted({r["mint"] for r in rows}), t) if rows else {}
        for p in rows:
            q = quotes.get(p["mint"])
            self._exit(p, p["tokens_left"], q.price if q else p["last_price"], q.reserve_usd if q else None, t, "end")
        self._snap(t, force=True)
