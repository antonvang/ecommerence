"""PROTOCOL_V3 amendment 40: shared data-gate helpers for research tools.

news_rows is the only way a research tool reads news/1: backfilled rows published on or after 2024-01-01 (the holdout
and later) are filtered out in SQL, so they never reach Python; live rows (backfill false) are forward data.
"""
import json

HOLDOUT_START_TS = 1704067200          # 2024-01-01 00:00 UTC


def news_rows(con, metric="news_item"):
    """news/1 rows of `metric` from a read-only sqlite connection: live rows, and backfilled rows before 2024."""
    sql = ("SELECT ts, payload FROM observations WHERE detector='news/1' AND metric=? AND ("
           "COALESCE(json_extract(payload, '$.backfill'), 0) IN (0, 'False', 'false') "
           "OR CAST(json_extract(payload, '$.published_ts') AS REAL) < ?) ORDER BY ts")
    return [(ts, json.loads(p)) for ts, p in con.execute(sql, (metric, HOLDOUT_START_TS))]
