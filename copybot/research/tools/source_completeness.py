"""Source completeness for the STRAKS and PAR-BOG books (director order 83, dev design only). NOT WIRED IN: lab/straks.py
and lab/pairs.py are pinned and frozen and are neither changed nor patched here. Read research/desk/ORDER83.md.

A book is DATA_COMPLETE only when every market it trades has a fresh closed 1h bar and a valid (non-crossed) book, and,
for STRAKS, its signal source (abnormal_move/1) is fresh. Anything else is DATA_INCOMPLETE with the missing parts named.
Recovery from a data pause needs an unbroken run of complete assessments; one working market proves nothing about the
others. `probes` gives the same check in the named-source form of the order-81 Risk.auto_resume.
"""
from lab import moves, pairs

DATA_COMPLETE, DATA_INCOMPLETE = "DATA_COMPLETE", "DATA_INCOMPLETE"
RECOVERY_ALLOWED, NO_RECOVERY = "RECOVERY_ALLOWED", "NO_RECOVERY"
REQUIRED = {"straks": tuple(sorted(moves.WATCH)), "pairs": tuple(sorted({s for p in pairs.PAIRS for s in p}))}
SIGNAL_SOURCE = {"straks": "abnormal_move/1"}
HOUR = 3600
MAX_BAR_AGE_S = 2 * HOUR             # as lab.paper_runner.MAX_BAR_AGE and lab.pairs.MAX_BAR_AGE
SIGNAL_MAX_AGE_S = 2 * HOUR          # as lab.moves.MAX_AGE_S
RECOVERY_RUN_S = 50 * 60             # as amendment 18 (lab.risk.AUTO_RUN_S)


class DataIncomplete(Exception):
    pass


def assess(book, obs, now, signal_ts=None):
    """obs: {symbol: {"bar_ts": open time of the latest closed 1h bar, "book_ok": bool}}. Pure; reads nothing."""
    if book not in REQUIRED:
        raise ValueError(f"unknown book {book!r}")
    missing, stale, bad_book = [], [], []
    for s in REQUIRED[book]:
        o = obs.get(s)
        if not isinstance(o, dict):
            missing.append(s)
            continue
        bar = o.get("bar_ts")
        if not isinstance(bar, (int, float)) or isinstance(bar, bool) or now - (bar + HOUR) > MAX_BAR_AGE_S:
            stale.append(s)
        if o.get("book_ok") is not True:
            bad_book.append(s)
    sources = []
    if book in SIGNAL_SOURCE and (not isinstance(signal_ts, (int, float)) or now - signal_ts > SIGNAL_MAX_AGE_S):
        sources.append(SIGNAL_SOURCE[book])
    ok = not (missing or stale or bad_book or sources)
    return {"book": book, "status": DATA_COMPLETE if ok else DATA_INCOMPLETE, "t": now, "missing": missing,
            "stale_bars": stale, "invalid_books": bad_book, "stale_sources": sources,
            "required": list(REQUIRED[book])}


def recovery(history, now, run_s=RECOVERY_RUN_S):
    """history: [(ts, status)] since the pause began, oldest first. Allowed only after an unbroken complete run of
    run_s ending with the latest assessment; an empty history never recovers."""
    first = None
    for ts, status in history:
        first = (first if first is not None else ts) if status == DATA_COMPLETE else None
    if first is None or not history or history[-1][1] != DATA_COMPLETE or now - first < run_s:
        return NO_RECOVERY
    return RECOVERY_ALLOWED


def probes(book, now, get, cache=None, signal_ts=None):
    """[(source name, probe)] for the order-81 multi-source auto_resume: one per required market (fresh bar and a
    valid book) plus the signal source. A probe raises DataIncomplete naming what is missing."""
    from lab import paper_runner as pr

    def market(sym):
        def probe():
            bars = pr.hourly(sym, now, get, cache)[0]
            if not bars or now - (bars[-1][0] + HOUR) > MAX_BAR_AGE_S:
                raise DataIncomplete(f"{DATA_INCOMPLETE}: {sym} has no fresh closed 1h bar")
            if pr.fetch_book(sym, now, get).crossed():
                raise DataIncomplete(f"{DATA_INCOMPLETE}: {sym} book crossed or empty")
        return probe

    out = [(s, market(s)) for s in REQUIRED[book]]
    if book in SIGNAL_SOURCE:
        def signal():
            if not isinstance(signal_ts, (int, float)) or now - signal_ts > SIGNAL_MAX_AGE_S:
                raise DataIncomplete(f"{DATA_INCOMPLETE}: {SIGNAL_SOURCE[book]} is not fresh")
        out.append((SIGNAL_SOURCE[book], signal))
    return out
