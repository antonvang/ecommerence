"""PROTOCOL_V3 amendment 30: the "EU-tradable" label, information only.

Reads the static research/data/eu_venue_markets.json (built outside lab/ by research/tools/eu_venue_markets.py) and
names, per coin, the EU-authorised venues with a Danish passport whose public market list trades it. It fetches
nothing, and nothing that selects, rejects or ranks reads it."""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "data",
                    "eu_venue_markets.json")
_CACHE = {}


def _load(path=None):
    path = path or PATH
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _CACHE.get("key") != (path, mtime):
        with open(path, encoding="utf-8") as fh:
            _CACHE.update(key=(path, mtime), data=json.load(fh))
    return _CACHE["data"]


def base(symbol):
    s = (symbol or "").upper().split(".")[0]
    for q in ("USDT", "USDC", "FDUSD", "BUSD"):
        if s.endswith(q) and len(s) > len(q):
            return s[:-len(q)]
    return s


def eu_venues(symbol, path=None):
    """Sorted venue names trading the coin, [] if none, None when the source file is missing."""
    d = _load(path)
    if d is None:
        return None
    b = base(symbol)
    return sorted(n for n, v in d["venues"].items() if v.get("qualifies") and b in (v.get("coins") or {}))


def label(symbols, path=None):
    """{symbol: venues} for display, plus the source's date and the unresolved API mapping."""
    d = _load(path)
    if d is None:
        return {"source": None}
    return {"coins": {s: eu_venues(s, path) for s in symbols}, "source_generated_at": d["generated_at"],
            "register_sha256": d["register"]["sha256"],
            "note": "kun oplysning (ændring 30); børsernes API-enhed er uafklaret"}
