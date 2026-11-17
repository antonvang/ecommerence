"""Build the README snapshot contract from the journal, point-in-time.

Only bars and stories first seen by `as_of` are used, each in the version that
was known at `as_of`. A gap is never filled: the snapshot uses the most recent
contiguous run and states where it was cut. The result is self-checked with
`core.analyse`, so an unusable snapshot fails here rather than in paper-step.
"""
from __future__ import annotations

from ..core import Candle, Rejected, analyse, timestamp

DEFAULT_BARS = 200
NEWS_WINDOW = 86400.0


def build_snapshot(journal, as_of, candle_source="binance_spot_klines", instrument="SOL/USDC",
                   interval_s=60, bars=DEFAULT_BARS, news_sources=(), news_window=NEWS_WINDOW):
    as_of = timestamp(as_of)
    if instrument != "SOL/USDC":
        raise Rejected("Only SOL/USDC snapshots are supported")
    rows = journal.bars_as_of(candle_source, instrument, interval_s, as_of, bars)
    if not rows:
        raise Rejected("No observed closed bars at as_of")
    cut = None
    for index in range(len(rows) - 1, 0, -1):
        if rows[index]["start"] != rows[index - 1]["end"]:
            cut = dict(missing_after=rows[index - 1]["end"], resumes_at=rows[index]["start"])
            rows = rows[index:]
            break
    candles = [dict(start=row["start"], end=row["end"], observed_at=row["seen_at"],
                    open=row["open"], high=row["high"], low=row["low"], close=row["close"],
                    volume=row["volume"]) for row in rows]

    news, excluded = [], {}
    for group in journal.stories_as_of(list(news_sources), as_of, as_of - news_window):
        first = group[0]
        if first["published_at"] > first["first_seen_at"]:
            # Claimed publication after we first saw it: clock or feed error.
            excluded["published_after_first_seen"] = excluded.get("published_after_first_seen", 0) + 1
            continue
        news.append(dict(title=first["title"], url=first["url"], published_at=first["published_at"],
                         observed_at=first["first_seen_at"], source=first["source"],
                         also_seen_in=sorted({row["source"] for row in group[1:]}),
                         revised=first["revised"], published_is_updated=bool(first["published_is_updated"])))

    snapshot = dict(market=instrument, source="RECORDED", as_of=as_of, candles=candles, news=news,
                    provenance=dict(
                        candle_source=candle_source, interval_s=interval_s,
                        bars_requested=bars, bars_used=len(candles), cut_at_gap=cut,
                        revised_bars=sum(1 for row in rows if row["revised"]),
                        fetches=sorted({(row["fetch_id"], row["body_sha256"]) for row in rows}),
                        news_sources=sorted(news_sources), news_excluded=excluded,
                        note="Observations only; no profit claim, no live execution"))
    # Self-check with the same rules paper-step applies.
    check = analyse([Candle.parse(row) for row in candles], news, as_of)
    snapshot["provenance"]["analyse_check"] = dict(action=check["action"], reason=check.get("reason"))
    return snapshot
