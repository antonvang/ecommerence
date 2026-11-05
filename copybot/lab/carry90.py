"""Long carry book (research/PROTOCOL_V3.md amendment 42). SIMULATION ONLY: no exchange, no keys, no real money.

Two lane accounts (source "carry90"), one pair each (BTC, ETH): long Binance spot and short the USD-M perp in the same
quantity, 5 000 USDT per leg, held up to 180 days without the 14-day source rule. They trade through lane.run_one's
two-leg code with a fixed +1 signal. Never evidence; nothing here is a candidate, an alpha row or a lock.
"""
from __future__ import annotations

SOURCE = "carry90"
COINS = ("BTCUSDT", "ETHUSDT")
LABEL = "CARRY90-KONTO (lang carry, simuleret, aldrig bevis)"
RULE = "research/PROTOCOL_V3.md amendment 42"
LOSS = 0.05                                     # point 3a: value <= 9 500
MAX_AGE_S = 180 * 86400                         # point 3d
PAUSE_S = 86400                                 # point 3c
ACTOR = "system:lane"


def is_carry90(info):
    return (info or {}).get("source") == SOURCE


def rules_text():
    return (f"lang spot / kort perp holdt op til {MAX_AGE_S // 86400} dage uden 14-dages-regel; stoppes ved værdi ≤ "
            f"{1 - LOSS:.0%} af kapitalen, afnotering, 24 t pause eller {MAX_AGE_S // 86400} dage")


def ensure(db, now):
    """Point 2: start both accounts once (a key that was ever started is never started again)."""
    from lab import lane
    if not db.one("SELECT 1 FROM observations WHERE detector='census/1' LIMIT 1"):
        return []                                                # no funding census on this database: not the lab
    have = {p.get("key") for p in lane.started(db).values()}
    out = []
    for coin in COINS:
        key = f"{SOURCE}|{coin}"
        if key in have:
            continue
        led = lane.ledger_id(key)
        db.event("lane.started", ACTOR, led, {
            "key": key, "source": SOURCE, "name": f"CARRY90-{coin[:-4]}", "function": "hold", "family": SOURCE,
            "params": {"hold_days_max": MAX_AGE_S // 86400, "leg_usd": lane.CAPITAL / lane.UNIT_CAPITAL},
            "coins": [coin], "expectation": None, "capital": lane.CAPITAL, "t": int(now),
            "costs": lane.COSTS.__dict__, "label": LABEL, "simulated": True, "decisional": False, "rule": RULE})
        out.append(led)
    return out


def retire_reason(db, ledger, info, now):
    """Point 3: value, delisting, a long pause, age. No source, flat or edge rule."""
    from lab import lane
    from lab.risk import Risk
    st, risk = lane.stats(db, ledger, now, info), Risk(db, lambda: now)
    coin = info["coins"][0]
    title = lane.delistings(db, now).get(lane._base(coin, "scanner"))   # announcement titles name the base coin
    if title:
        return "delisting", f"afnotering annonceret (16e): {title}"[:200], st
    if now - info["ts"] >= MAX_AGE_S:
        return "expired", f"{MAX_AGE_S // 86400} dage efter start", st
    if st["equity"] is not None and st["equity"] <= lane.CAPITAL * (1 - LOSS):
        return "loss", f"værdi {st['equity']:.2f} er mindst {LOSS:.0%} under startkapitalen", st
    age, rule = lane._paused_for(risk, ledger, now)
    if age is not None and age >= PAUSE_S:
        return "paused", f"på pause i {age / 3600:.0f} timer ({rule})", st
    return None, None, st
