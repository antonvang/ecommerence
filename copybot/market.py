"""Priser og likviditet.

LiveMarket:     DexScreener lige nu (paper trading).
BacktestMarket: minut-candles fra GeckoTerminal + poolstørrelse fra walletens egne transaktioner.
"""
from __future__ import annotations

import bisect
import math
import time
import urllib.error
from dataclasses import dataclass
from typing import Optional

from net import DiskCache, Throttle, http_json
from swaps import WSOL

DEX = "https://api.dexscreener.com"
GECKO = "https://api.geckoterminal.com/api/v2"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"


@dataclass
class Quote:
    price: float                  # USD pr. token
    reserve_usd: Optional[float]  # SOL/USD-siden af poolen (halvdelen af "liquidity")
    symbol: str


def _liq(p):
    return ((p.get("liquidity") or {}).get("usd")) or 0.0


class Dex:
    """DexScreener: pools, symboler og live-priser. Gratis, ingen nøgle, 300 kald/min."""

    def __init__(self, cache_dir=None, log=print):
        self.th = Throttle(0.25)
        self.cache = DiskCache(cache_dir)
        self.log = log

    def pairs(self, mints, use_cache=False):
        """mint -> liste af pools hvor mint er base-token, største likviditet først."""
        out, need = {}, []
        for m in mints:
            hit = self.cache.get("dex:" + m) if use_cache else None
            if hit is not None:
                out[m] = hit
            else:
                need.append(m)
        for k in range(0, len(need), 30):
            chunk = need[k:k + 30]
            self.th.wait()
            data = http_json(f"{DEX}/tokens/v1/solana/{','.join(chunk)}", log=self.log) or []
            if isinstance(data, dict):
                data = data.get("pairs") or []
            got = {m: [] for m in chunk}
            for p in data:
                base = (p.get("baseToken") or {}).get("address")
                if base in got:
                    got[base].append(p)
            for m, lst in got.items():
                lst.sort(key=_liq, reverse=True)
                out[m] = lst
                if use_cache:
                    self.cache.put("dex:" + m, lst)
        return out

    def sol_usdc_pool(self):
        for p in self.pairs([WSOL], use_cache=True)[WSOL]:
            if (p.get("quoteToken") or {}).get("address") == USDC:
                return p["pairAddress"]
        raise RuntimeError("Fandt ingen SOL/USDC-pool på DexScreener")


class LiveMarket:
    def __init__(self, log=print):
        self.dex = Dex(log=log)
        self.log = log
        self._cache = {}
        self._sol = (0.0, None)

    def quotes(self, mints, ts=None):
        now = time.time()
        need = [m for m in mints if not (m in self._cache and now - self._cache[m][0] < 5)]
        if need:
            try:
                pairs = self.dex.pairs(need)
            except Exception as e:  # netværksfejl må ikke stoppe botten
                self.log(f"  DexScreener-fejl: {e}")
                pairs = {}
            for m in need:
                lst = pairs.get(m) or []
                p = lst[0] if lst else None
                if p and p.get("priceUsd"):
                    liq = _liq(p)
                    sym = (p.get("baseToken") or {}).get("symbol") or m[:4]
                    self._cache[m] = (now, Quote(float(p["priceUsd"]), liq / 2 if liq else None, sym))
                elif m not in self._cache:
                    self._cache[m] = (now, None)
        return {m: self._cache[m][1] for m in mints if m in self._cache}

    def quote(self, mint, ts=None, swap=None):
        q = self.quotes([mint]).get(mint)
        if q and q.reserve_usd is None and swap is not None and swap.reserve_usd:
            q = Quote(q.price, swap.reserve_usd, q.symbol)
        return q

    def sol_usd(self, ts=None):
        t, v = self._sol
        if v is None or time.time() - t > 60:
            q = self.quotes([WSOL]).get(WSOL)
            if q:
                self._sol = (time.time(), q.price)
            elif v is None:
                raise RuntimeError("Kan ikke hente SOL-prisen fra DexScreener")
        return self._sol[1]


class Gecko:
    """GeckoTerminal-candles. Gratis, ingen nøgle, ca. 30 kald/min."""

    def __init__(self, cache_dir=None, log=print):
        self.th = Throttle(2.2)
        self.cache = DiskCache(cache_dir)
        self.log = log

    def ohlcv(self, pool, tf, before, token, limit=1000):
        url = (f"{GECKO}/networks/solana/pools/{pool}/ohlcv/{tf}?aggregate=1&limit={limit}"
               f"&before_timestamp={before}&currency=usd&token={token}")
        hit = self.cache.get(url)
        if hit is not None:
            return hit
        self.th.wait()
        try:
            data = http_json(url, log=self.log)
            lst = ((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 422):
                lst = []
            else:
                raise
        self.cache.put(url, lst)
        return lst

    def range(self, pool, tf, t0, t1, token):
        before = (int(t1) // 3600 + 1) * 3600  # rundet, så cachen kan genbruges
        out = {}
        while True:
            lst = self.ohlcv(pool, tf, before, token)
            if not lst:
                break
            for r in lst:
                out[int(r[0])] = tuple(float(x) for x in r[1:5])
            oldest = min(int(r[0]) for r in lst)
            if oldest <= t0 or len(lst) < 1000 or oldest >= before:
                break
            before = oldest
        return out

    def candles_for(self, mint, pools, t0, t1):
        """Minut-candles for en token. Prøver op til 3 pools (fx pump.fun før og PumpSwap efter)."""
        merged = {}
        for pool in pools[:3]:
            for ts, c in self.range(pool, "minute", t0, t1, mint).items():
                merged.setdefault(ts, c)
            if merged and min(merged) <= t0 + 600:
                break
        return sorted((ts,) + c for ts, c in merged.items())


class BacktestMarket:
    def __init__(self, candles, sol_hours, symbols):
        self.c = {m: ([r[0] for r in rows], rows) for m, rows in candles.items() if rows}
        self.sol_ts = [r[0] for r in sol_hours]
        self.sol_px = [r[4] for r in sol_hours]
        self.sym = symbols
        self.ref = {}

    def reset(self):
        self.ref = {}

    def sol_usd(self, ts):
        if not self.sol_ts:
            raise RuntimeError("Ingen SOL-priser")
        i = max(bisect.bisect_right(self.sol_ts, ts) - 1, 0)
        return self.sol_px[i]

    def observe(self, sw):
        if sw.reserve_usd:
            self.ref[sw.mint] = (sw.reserve_usd, self.price_at(sw.mint, sw.ts) or sw.price_usd)

    def price_at(self, mint, ts):
        d = self.c.get(mint)
        if not d:
            return None
        tss, rows = d
        i = bisect.bisect_right(tss, ts) - 1
        if i < 0:
            return None
        t0, o, h, l, c = rows[i]
        if ts >= t0 + 60:
            return c  # ingen handler siden: prisen står stille
        return o + (ts - t0) / 60.0 * (c - o)

    def quote(self, mint, ts, swap=None):
        p = self.price_at(mint, ts)
        if p is None or p <= 0:
            return None
        r = None
        if swap is not None and swap.mint == mint and swap.reserve_usd:
            r = swap.reserve_usd
        elif mint in self.ref:
            r0, p0 = self.ref[mint]
            r = r0 * math.sqrt(p / p0) if p0 > 0 else r0  # x*y=k: SOL-siden vokser med kvadratroden af prisen
        return Quote(p, r, self.sym.get(mint, mint[:4]))

    def quotes(self, mints, ts):
        return {m: self.quote(m, ts) for m in mints}
