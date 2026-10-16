"""Funding-carry (paper): ej coinen og short dens perp på Hyperliquid, så prisen går ud mod hinanden, og indsaml funding.

Når markedet er grådigt, betaler dem, der er long på perps, en gebyr hver time til dem, der er short. Reglen er den
samme som i historik-testen (6 mdr., +8,6 %/år, alle uger i plus): hver uge (mandag 00:00 UTC) vælges de 5 likvide
perps med højest funding den forgangne uge, dog kun hvis den var over 10 %/år. Kapitalen deles i to: halvdelen
køber coinen, halvdelen er margin for shorten. KUN FALSKE PENGE.

Ikke med i tallene: forskel mellem spot- og perp-pris ved ind- og udgang, og risikoen for at shorten skal have mere
margin, hvis prisen stiger meget. Spot-benet findes ikke på Hyperliquid for alle coins.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

from store import Store

API = "https://api.hyperliquid.xyz/info"
HOUR = 3600
WEEK = 7 * 24 * HOUR
SCHEMA = """
CREATE TABLE IF NOT EXISTS fpos (id INTEGER PRIMARY KEY AUTOINCREMENT, coin TEXT, week INTEGER, opened_ts INTEGER,
  closed_ts INTEGER, notional REAL, picked_apr REAL);
CREATE TABLE IF NOT EXISTS fpay (pos_id INTEGER, hour INTEGER, rate REAL, usd REAL, PRIMARY KEY (pos_id, hour));
CREATE TABLE IF NOT EXISTS fcost (ts INTEGER, coin TEXT, usd REAL);
"""


def week_of(ts):
    """Ugenummer, der skifter mandag 00:00 UTC (1.1.1970 var en torsdag)."""
    return int((ts - 4 * 86400) // WEEK)


def pick(candidates, top=5, min_apr=0.10):
    """candidates: {coin: sum af funding de sidste 7 dage}. De `top` højeste, der årligt giver over `min_apr`."""
    best = sorted(candidates.items(), key=lambda kv: -kv[1])[:top]
    return [(c, f * 52) for c, f in best if f * 52 > min_apr]


class HL:
    def __init__(self, url=API, log=print):
        self.url = url
        self.log = log

    def post(self, body):
        for i in range(5):
            try:
                req = urllib.request.Request(self.url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except Exception:
                if i == 4:
                    raise
                time.sleep(2 * (i + 1))

    def liquid(self, min_oi=5e6, min_vol=5e6):
        """{coin: nuværende funding pr. time} for perps med nok open interest og volumen."""
        meta, ctxs = self.post({"type": "metaAndAssetCtxs"})
        out = {}
        for a, c in zip(meta["universe"], ctxs):
            px = float(c.get("markPx") or 0)
            if not a.get("isDelisted") and float(c.get("openInterest") or 0) * px >= min_oi and float(c.get("dayNtlVlm") or 0) >= min_vol:
                out[a["name"]] = float(c.get("funding") or 0)
        return out

    def history(self, coin, start_ts):
        """[(time_s, rate)] siden start_ts (Hyperliquid betaler funding hver time)."""
        rows, t = [], int(start_ts * 1000)
        while True:
            batch = self.post({"type": "fundingHistory", "coin": coin, "startTime": t})
            if not batch:
                return rows
            rows += [(int(b["time"]) // 1000, float(b["fundingRate"])) for b in batch]
            nt = int(batch[-1]["time"]) + 1
            if nt <= t or len(batch) < 500:
                return rows
            t = nt


class FundingCarry:
    def __init__(self, cfg, root, hl=None, log=print):
        fc = cfg["funding"]
        self.capital = float(fc["capital_usd"])
        self.top = int(fc["top"])
        self.min_apr = fc["min_apr_pct"] / 100.0
        self.switch = fc["switch_cost_pct"] / 100.0  # ind + ud, begge ben, af positionens størrelse
        self.hl = hl or HL(log=log)
        self.s = Store(os.path.join(root, "funding.db"))
        self.s.db.executescript(SCHEMA)
        self.log = log

    def open_positions(self):
        return self.s.q("SELECT * FROM fpos WHERE closed_ts IS NULL")

    def rotate(self, now):
        """Ny uge (eller første start): vælg de nye 5 ud fra den forgangne uges funding, betal for skiftene."""
        liquid = self.hl.liquid()
        sums = {}
        for coin in liquid:
            hist = [r for t, r in self.hl.history(coin, now - WEEK) if t >= now - WEEK]
            if len(hist) >= 0.9 * 7 * 24:
                sums[coin] = sum(hist)
        chosen = pick(sums, self.top, self.min_apr)
        held = {r["coin"]: r for r in self.open_positions()}
        new = {c for c, _ in chosen}
        notional = self.capital / 2 / self.top  # halvdelen køber coins, halvdelen er margin
        for coin, r in held.items():
            if coin not in new:
                self.s.x("UPDATE fpos SET closed_ts=? WHERE id=?", now, r["id"])
                self.s.x("INSERT INTO fcost(ts, coin, usd) VALUES(?,?,?)", now, coin, r["notional"] * self.switch / 2)
            else:
                self.s.x("UPDATE fpos SET week=? WHERE id=?", week_of(now), r["id"])
        for coin, apr in chosen:
            if coin not in held:
                self.s.x("INSERT INTO fpos(coin, week, opened_ts, notional, picked_apr) VALUES(?,?,?,?,?)",
                         coin, week_of(now), now, notional, apr)
                self.s.x("INSERT INTO fcost(ts, coin, usd) VALUES(?,?,?)", now, coin, notional * self.switch / 2)
        self.s.set("funding_week", week_of(now))
        self.s.set("funding_picked", [[c, a] for c, a in chosen])
        self.log(f"[FUNDING] uge {week_of(now)}: " + (", ".join(f"{c} {a * 100:.0f}%/år" for c, a in chosen) or "ingen over grænsen"))

    def accrue(self):
        """Bogfør funding for hver hele time, positionen har været åben (short modtager, når satsen er positiv)."""
        for r in self.open_positions():
            last = self.s.one("SELECT MAX(hour) FROM fpay WHERE pos_id=?", r["id"])[0]
            since = (last + 1) * HOUR if last is not None else r["opened_ts"]
            for t, rate in self.hl.history(r["coin"], since):
                h = t // HOUR
                if t > r["opened_ts"]:  # betalingen ved købet dækker timen før: den ejede vi ikke
                    self.s.x("INSERT OR IGNORE INTO fpay(pos_id, hour, rate, usd) VALUES(?,?,?,?)", r["id"], h, rate, rate * r["notional"])

    def step(self, now=None):
        now = int(now or time.time())
        if self.s.get("funding_week") != week_of(now):
            self.rotate(now)
        self.accrue()
        self.s.set("funding_heartbeat", now)

    def run(self, stop=None):
        self.log(f"Funding-carry (paper) kører · ${self.capital:.0f} · top {self.top} · min {self.min_apr * 100:.0f} %/år")
        while not (stop and stop.is_set()):
            try:
                self.step()
            except Exception as e:
                self.s.set("funding_error", [int(time.time()), f"{type(e).__name__}: {str(e)[:160]}"])
            time.sleep(300)  # funding betales hver time; 5 min er rigeligt


def start_in_background(cfg, root, log=print):
    fc = FundingCarry(cfg, root, log=log)
    threading.Thread(target=fc.run, daemon=True).start()
    return fc
