"""Amendment 29: the pilot's two exchanges with one interface. DryExchange reads live public books and simulates fills
(nothing is sent); LiveExchange signs requests to Binance spot with the user's trade-only key."""
import hashlib
import hmac
import json
import math
import os
import stat
import time
import urllib.parse
import urllib.request

from pilot import DRY_FEE, KEY_PATH

PUBLIC = "https://data-api.binance.vision"
LIVE = "https://api.binance.com"


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
        return {"bids": d["bids"], "asks": d["asks"], "bid": float(d["bids"][0][0]), "ask": float(d["asks"][0][0])}

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
        px, q, spent = walk(self.book(symbol)["asks"], "buy", quote=quote)
        fee = spent * DRY_FEE
        self._move(self.filters(symbol)["base"], q, -spent - fee)
        return {"status": "FILLED", "qty": q, "quote": spent, "avg_px": px, "fee_usdt": fee, "fee_assumed": True}

    def sell_market(self, symbol, qty):
        px, q, got = walk(self.book(symbol)["bids"], "sell", qty=qty)
        fee = got * DRY_FEE
        self._move(self.filters(symbol)["base"], -q, got - fee)
        return {"status": "FILLED", "qty": q, "quote": got, "avg_px": px, "fee_usdt": fee, "fee_assumed": True}

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


def load_key(path=KEY_PATH):
    """The user's key file, refused unless only its owner can read it. Its content is never logged or printed."""
    st = os.stat(path)
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise PermissionError(f"{path} must have mode 600")
    with open(path, encoding="utf-8") as fh:
        k = json.load(fh)
    return k["key"], k["secret"]


class LiveExchange(Public):
    """Signed Binance spot requests with the user's trade-only key. Only constructed after every live check passed."""
    dry = False

    def __init__(self, key_path=KEY_PATH, opener=urllib.request.urlopen):
        super().__init__(LIVE, _get)
        self._key, self._secret = load_key(key_path)
        self._open = opener

    def __repr__(self):
        return "LiveExchange(<key hidden>)"

    def _signed(self, method, path, params):
        params = dict(params, timestamp=int(time.time() * 1000), recvWindow=5000)
        qs = urllib.parse.urlencode(params)
        sig = hmac.new(self._secret.encode(), qs.encode(), hashlib.sha256).hexdigest()
        req = urllib.request.Request(f"{LIVE}{path}?{qs}&signature={sig}", method=method,
                                     headers={"X-MBX-APIKEY": self._key, "User-Agent": "copybot-pilot"})
        with self._open(req, timeout=10) as r:
            return json.loads(r.read())

    def balance(self, asset):
        for b in self._signed("GET", "/api/v3/account", {"omitZeroBalances": "true"})["balances"]:
            if b["asset"] == asset:
                return float(b["free"])
        return 0.0

    def _fee_usdt(self, symbol, fills):
        base, total = self.filters(symbol)["base"], 0.0
        for f in fills:
            c, a = float(f["commission"]), f["commissionAsset"]
            if a == "USDT":
                total += c
            elif a == base:
                total += c * float(f["price"])
            else:                                       # e.g. BNB: valued at its bid now
                total += c * self.book(f"{a}USDT")["bid"]
        return total

    def _fill(self, symbol, r):
        q, quote = float(r.get("executedQty", 0)), float(r.get("cummulativeQuoteQty", 0))
        return {"status": r["status"], "qty": q, "quote": quote, "avg_px": quote / q if q else None,
                "fee_usdt": self._fee_usdt(symbol, r.get("fills", [])), "order_id": r.get("orderId")}

    def buy_market_quote(self, symbol, quote):
        return self._fill(symbol, self._signed("POST", "/api/v3/order", {
            "symbol": symbol, "side": "BUY", "type": "MARKET", "quoteOrderQty": f"{quote:.2f}",
            "newOrderRespType": "FULL"}))

    def sell_market(self, symbol, qty):
        return self._fill(symbol, self._signed("POST", "/api/v3/order", {
            "symbol": symbol, "side": "SELL", "type": "MARKET", "quantity": f"{qty:.8f}".rstrip("0").rstrip("."),
            "newOrderRespType": "FULL"}))

    def buy_limit_maker(self, symbol, price, qty):
        r = self._signed("POST", "/api/v3/order", {
            "symbol": symbol, "side": "BUY", "type": "LIMIT_MAKER", "price": f"{price:.8f}".rstrip("0").rstrip("."),
            "quantity": f"{qty:.8f}".rstrip("0").rstrip("."), "newOrderRespType": "FULL"})
        return {"order_id": r["orderId"], "status": r["status"]}

    def order_status(self, symbol, oid):
        r = self._signed("GET", "/api/v3/order", {"symbol": symbol, "orderId": oid})
        q, quote = float(r["executedQty"]), float(r["cummulativeQuoteQty"])
        fee = 0.0
        if q:
            trades = self._signed("GET", "/api/v3/myTrades", {"symbol": symbol, "orderId": oid})
            fee = self._fee_usdt(symbol, [{"commission": t["commission"], "commissionAsset": t["commissionAsset"],
                                           "price": t["price"]} for t in trades])
        return {"status": r["status"], "qty": q, "quote": quote, "avg_px": quote / q if q else None, "fee_usdt": fee}

    def cancel(self, symbol, oid):
        return {"status": self._signed("DELETE", "/api/v3/order", {"symbol": symbol, "orderId": oid})["status"]}
