"""PROTOCOL_V3 amendment 21y section A: the session of an hourly bar [t, t+1h) for K1/K2.

Equities: RTH (the bar lies wholly inside the NYSE regular session, 13:00 ET on early-close days), WEEKEND (wholly in
Sat 00:00 - Mon 00:00 UTC, Binance's EWMA window in moves.off_hours), HOLIDAY (an NYSE full holiday on a weekday) or
OTHER. Commodities and FX: CLOSED when moves.off_hours, else OPEN. The holiday list is an assumption to be checked
against NYSE's published calendar before the first measurement (21y A).
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HOUR = 3600
NYSE_CLOSED = frozenset(dt.date.fromisoformat(d) for d in (
    "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31", "2027-06-18"))
NYSE_EARLY = frozenset(dt.date.fromisoformat(d) for d in ("2026-11-27", "2026-12-24"))
CALENDAR_UNTIL = dt.date(2027, 6, 30)
RTH, WEEKEND, HOLIDAY, OTHER, OPEN, CLOSED = "RTH", "WEEKEND", "HOLIDAY", "OTHER", "OPEN", "CLOSED"


def equity(t):
    """Session of the equity bar opening at UTC epoch t."""
    u0 = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    u1 = u0 + dt.timedelta(hours=1)
    if u0.weekday() >= 5 and (u1.weekday() >= 5 or (u1.weekday() == 0 and u1.hour == 0 and u1.minute == 0)):
        return WEEKEND
    e0, e1 = u0.astimezone(ET), u1.astimezone(ET)
    day = e0.date()
    if day > CALENDAR_UNTIL:
        raise ValueError(f"no NYSE calendar after {CALENDAR_UNTIL}")
    if e0.weekday() < 5 and day in NYSE_CLOSED:
        return HOLIDAY
    if e0.weekday() >= 5 or e1.date() != day:
        return OTHER
    close = 13 * 60 if day in NYSE_EARLY else 16 * 60
    m0, m1 = e0.hour * 60 + e0.minute, e1.hour * 60 + e1.minute
    return RTH if m0 >= 9 * 60 + 30 and m1 <= close else OTHER


def session(cls, t):
    """21y A: the bar's session for a market class (moves.WATCH)."""
    from lab import moves
    if cls == "equity_etf":
        return equity(t)
    if cls in ("commodity", "fx"):
        return CLOSED if moves.off_hours(cls, t) else OPEN
    return OPEN


def closed(cls, t):
    """The K2 'underlying closed' window: equities WEEKEND, commodities/FX CLOSED."""
    return session(cls, t) in (WEEKEND, CLOSED)


def opened(cls, t):
    """The K2 'underlying open' comparison: equities RTH, commodities/FX OPEN."""
    return session(cls, t) in (RTH, OPEN)


def weekend_key(t):
    """The weekend a bar belongs to: the UTC date of its Saturday (None on weekdays)."""
    u = dt.datetime.fromtimestamp(t, dt.timezone.utc)
    if u.weekday() == 5:
        return u.date().isoformat()
    if u.weekday() == 6:
        return (u.date() - dt.timedelta(days=1)).isoformat()
    return None
