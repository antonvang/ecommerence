"""Amendments 29/29a: the pilot's exchange. DryExchange reads live public books and simulates fills; nothing is ever
sent. There is no account, key or order code (29a point 1)."""
import json
import math
import time
import urllib.request

from pilot import DRY_FEE

PUBLIC = "https://data-api.binance.vision"


def _get(url, timeout=10):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "copybot-pilot"}),
                                timeout=timeout) as r:
        return json.loads(r.read())


def floor_step(x, step):
    return math.floor(x / step + 1e-9) * step if step > 0 else x


def walk(levels, side, quote=None, qty=None):
    """Average price and quantity of a taker fill walking `levels` [[px, qty], ...]; by quote (buy) or qty (sell)."""
    got_q, got_quote = 0.0, 0.0
    for px, q in ((float(a), float(b)) for a, b in levels):
        take = min(q, (quote - got_quote) / px) if quote is not None else min(q, qty - got_q)
        if take <= 0:
            break
        got_q += take
        got_quote += take * px
    if got_q <= 0:
        raise RuntimeError(f"empty book for {side}")
    return got_quote / got_q, got_q, got_quote


class Public:
    """Public market data, shared by both modes."""

    def __init__(self, base=PUBLIC, get=_get):
        self.base, self.get, self._filters = base, get, {}

    def server_ms(self):
        return self.get(f"{self.base}/api/v3/time")["serverTime"]

    def book(self, symbol):
        d = self.get(f"{self.base}/api/v3/depth?symbol={symbol}&limit=20")
        bids, asks = d.get("bids") or [], d.get("asks") or []    # empty on a halted market, e.g. status BREAK (29d)
        return {"bids": bids, "asks": asks, "bid": float(bids[0][0]) if bids else None,
                "ask": float(asks[0][0]) if asks else None}

    def filters(self, symbol):
        if symbol not in self._filters:
            info = self.get(f"{self.base}/api/v3/exchangeInfo?symbol={symbol}")["symbols"][0]
            f = {x["filterType"]: x for x in info["filters"]}
            self._filters[symbol] = {
                "step": float(f["LOT_SIZE"]["stepSize"]), "tick": float(f["PRICE_FILTER"]["tickSize"]),
                "min_notional": float((f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}).get("minNotional", 5)),
                "base": info["baseAsset"]}
        return self._filters[symbol]


class DryExchange(Public):
    """Simulated fills against the live public book; a simulated wallet; nothing is ever sent."""
    dry = True

    def __init__(self, get=_get, sleep=time.sleep, usdt=100.0):
        super().__init__(PUBLIC, get)
        self.sleep, self.wallet, self._orders = sleep, {"USDT": usdt}, {}

    def balance(self, asset):
        return self.wallet.get(asset, 0.0)

    def _move(self, base, dq, dquote):
        self.wallet[base] = self.wallet.get(base, 0.0) + dq
        self.wallet["USDT"] = self.wallet.get("USDT", 0.0) + dquote

    def buy_market_quote(self, symbol, quote):
        b = self.book(symbol)
        px, q, spent = walk(b["asks"], "buy", quote=quote)
        fee = spent * DRY_FEE
        self._move(self.filters(symbol)["base"], q, -spent - fee)
        return {"status": "FILLED", "qty": q, "quote": spent, "avg_px": px, "fee_usdt": fee, "fee_assumed": True,
                "mid": (b["bid"] + b["ask"]) / 2}                       # the book the simulated fill walked

    def sell_market(self, symbol, qty):
        b = self.book(symbol)
        px, q, got = walk(b["bids"], "sell", qty=qty)
        fee = got * DRY_FEE
        self._move(self.filters(symbol)["base"], -q, got - fee)
        return {"status": "FILLED", "qty": q, "quote": got, "avg_px": px, "fee_usdt": fee, "fee_assumed": True,
                "mid": (b["bid"] + b["ask"]) / 2}

    def buy_limit_maker(self, symbol, price, qty):
        oid = f"dry{len(self._orders) + 1}"
        self._orders[oid] = {"symbol": symbol, "price": price, "qty": qty, "status": "NEW"}
        return {"order_id": oid, "status": "NEW"}

    def order_status(self, symbol, oid):
        o = self._orders[oid]
        if o["status"] == "NEW" and self.book(symbol)["ask"] <= o["price"]:     # the ask crossed our bid: filled
            o["status"] = "FILLED"
            quote = o["price"] * o["qty"]
            fee = quote * DRY_FEE
            self._move(self.filters(symbol)["base"], o["qty"], -quote - fee)
            o.update(fill={"qty": o["qty"], "quote": quote, "avg_px": o["price"], "fee_usdt": fee, "fee_assumed": True})
        return {"status": o["status"], **(o.get("fill") or {"qty": 0.0, "quote": 0.0, "fee_usdt": 0.0})}

    def cancel(self, symbol, oid):
        if self._orders[oid]["status"] == "NEW":
            self._orders[oid]["status"] = "CANCELED"
        return {"status": self._orders[oid]["status"]}

