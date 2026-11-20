"""One collection cycle over a fixed schedule; the scheduler (systemd) calls it.

Each run checks which sources are due, fetches each due source once through
`observe` (so every attempt is journaled), and exits. There is no loop and no
process stays resident. A source in a rate-limit cooldown is skipped without a
request. Public data only: no keys, no wallet, no orders.
"""
from __future__ import annotations

import time

from ..core import SOL, USDC, QuoteRequest, Rejected, atoms
from .candles import BinanceKlines
from .news import NEWS_FEEDS
from .observe import observe
from .quotes import JupiterQuoteSample
from .transport import https_get

# (job, adapter factory, seconds between attempts). Sizes match the paper book
# (25 USDC buy) and roughly the same value back (0.35 SOL sell).
SCHEDULE = (
    ("candles_1m", lambda: BinanceKlines(interval="1m", limit=10), 60),
    ("quote_buy_25usdc", lambda: JupiterQuoteSample(QuoteRequest(USDC, SOL, atoms("25", USDC))), 60),
    ("quote_sell_0.35sol", lambda: JupiterQuoteSample(QuoteRequest(SOL, USDC, atoms("0.35", SOL))), 60),
    ("solana_status", NEWS_FEEDS["solana_status"], 3600),
    ("jupiter_status", NEWS_FEEDS["jupiter_status"], 3600),
    ("agave_releases", NEWS_FEEDS["agave_releases"], 3600),
)
SLACK = 10.0          # a timer firing every 60 s +- jitter must not skip a cycle
MAX_WAIT = 10.0       # wait at most this long for a source's min interval


def last_attempt(journal, adapter):
    row = journal.db.execute(
        """SELECT max(requested_at) FROM fetches
           WHERE source=? AND coalesce(instrument, '')=? AND outcome != 'COOLDOWN'""",
        (adapter.source, getattr(adapter, "instrument", None) or "")).fetchone()
    return row[0]


def collect(journal, fetch=None, clock=None, sleep=None, schedule=SCHEDULE):
    fetch, clock, sleep = fetch or https_get, clock or time.time, sleep or time.sleep
    report = []
    for job, factory, every in schedule:
        adapter = factory()
        last = last_attempt(journal, adapter)
        if last is not None and clock() - last < every - SLACK:
            report.append(dict(job=job, status="NOT_DUE"))
            continue
        limiter = journal.db.execute("SELECT last_requested_at, blocked_until FROM limiter WHERE source=?",
                                     (adapter.source,)).fetchone()
        if limiter is not None:
            if limiter["blocked_until"] > clock():
                report.append(dict(job=job, status="COOLING_DOWN", until=limiter["blocked_until"]))
                continue
            wait = limiter["last_requested_at"] + adapter.min_interval - clock()
            if wait > MAX_WAIT:
                report.append(dict(job=job, status="NOT_DUE"))
                continue
            if wait > 0:
                sleep(wait + 0.1)
        try:
            result = observe(journal, adapter, fetch=fetch, clock=clock)
            report.append(dict(job=job, status=result["outcome"], fetch_id=result["fetch_id"],
                               new=result.get("new"), revisions=result.get("revisions")))
        except Exception as exc:  # one source failing must not stop the others
            error = str(exc) if isinstance(exc, Rejected) else "%s: %s" % (type(exc).__name__, exc)
            report.append(dict(job=job, status="FAILED", error=error))
    return report


def exit_code(report):
    """0 all attempted jobs fine, 1 some failed, 2 every attempted job failed."""
    attempted = [entry for entry in report if entry["status"] not in ("NOT_DUE", "COOLING_DOWN")]
    failed = [entry for entry in attempted if entry["status"] == "FAILED"]
    if not failed:
        return 0
    return 2 if len(failed) == len(attempted) else 1
