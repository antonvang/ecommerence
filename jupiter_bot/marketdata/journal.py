"""Forward observation journal: every fetch, its raw bytes and what was new.

Rules enforced here:
- every attempt is a `fetches` row, including failures and skipped calls;
- the raw response body is stored with its SHA-256;
- the first observed value of a bar or story is kept forever (append-only
  triggers); a later different value is a separate revision row;
- nothing is ever filled in, carried forward or rewritten.
"""
from __future__ import annotations

import hashlib

from .. import storage
from ..core import Quote, Rejected, canonical
from .candles import SETTLE_SECONDS, CandleBatch, server_now
from .news import NewsBatch, title_key, url_key

APPLICATION_ID = 0x4A424F31  # "JBO1"
SCHEMA_VERSION = 1
OUTCOMES = ("OK", "STALE", "HTTP_ERROR", "TRANSPORT_ERROR", "PARSE_ERROR", "RATE_LIMITED", "COOLDOWN")
BAR_KEY = "source, instrument, interval_s, start"

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS fetches(
         id INTEGER PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL, instrument TEXT,
         url TEXT NOT NULL, requested_at REAL NOT NULL, received_at REAL,
         http_status INTEGER, headers_json TEXT, body BLOB, body_sha256 TEXT,
         outcome TEXT NOT NULL CHECK(outcome IN %s), error TEXT, summary_json TEXT NOT NULL)""" % (OUTCOMES,),
    """CREATE TABLE IF NOT EXISTS candles(
         source TEXT NOT NULL, instrument TEXT NOT NULL, interval_s INTEGER NOT NULL,
         start REAL NOT NULL, end REAL NOT NULL, open TEXT NOT NULL, high TEXT NOT NULL,
         low TEXT NOT NULL, close TEXT NOT NULL, volume TEXT NOT NULL,
         first_seen_at REAL NOT NULL, fetch_id INTEGER NOT NULL REFERENCES fetches(id),
         PRIMARY KEY(%s))""" % BAR_KEY,
    """CREATE TABLE IF NOT EXISTS candle_revisions(
         id INTEGER PRIMARY KEY, source TEXT NOT NULL, instrument TEXT NOT NULL,
         interval_s INTEGER NOT NULL, start REAL NOT NULL, open TEXT NOT NULL, high TEXT NOT NULL,
         low TEXT NOT NULL, close TEXT NOT NULL, volume TEXT NOT NULL, seen_at REAL NOT NULL,
         fetch_id INTEGER NOT NULL REFERENCES fetches(id),
         FOREIGN KEY(%s) REFERENCES candles(%s))""" % (BAR_KEY, BAR_KEY),
    """CREATE TABLE IF NOT EXISTS news(
         source TEXT NOT NULL, story_key TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
         url_key TEXT NOT NULL, title_key TEXT NOT NULL, published_at REAL NOT NULL,
         updated_at REAL NOT NULL, published_is_updated INTEGER NOT NULL,
         content_sha256 TEXT NOT NULL, first_seen_at REAL NOT NULL,
         fetch_id INTEGER NOT NULL REFERENCES fetches(id), PRIMARY KEY(source, story_key))""",
    """CREATE TABLE IF NOT EXISTS news_revisions(
         id INTEGER PRIMARY KEY, source TEXT NOT NULL, story_key TEXT NOT NULL, title TEXT NOT NULL,
         url TEXT NOT NULL, published_at REAL NOT NULL, updated_at REAL NOT NULL,
         content_sha256 TEXT NOT NULL, seen_at REAL NOT NULL,
         fetch_id INTEGER NOT NULL REFERENCES fetches(id),
         FOREIGN KEY(source, story_key) REFERENCES news(source, story_key))""",
    """CREATE TABLE IF NOT EXISTS quotes(
         quote_id TEXT PRIMARY KEY, input_mint TEXT NOT NULL, output_mint TEXT NOT NULL,
         in_amount INTEGER NOT NULL, out_amount INTEGER NOT NULL, router TEXT NOT NULL,
         fee_bps INTEGER NOT NULL, started_at REAL NOT NULL, observed_at REAL NOT NULL,
         fetch_id INTEGER NOT NULL REFERENCES fetches(id))""",
    # Mutable by design: the cross-process rate limiter and cooldowns.
    """CREATE TABLE IF NOT EXISTS limiter(
         source TEXT PRIMARY KEY, last_requested_at REAL NOT NULL,
         blocked_until REAL NOT NULL, reason TEXT)""",
]
for _table in ("fetches", "candles", "candle_revisions", "news", "news_revisions", "quotes"):
    for _event in ("UPDATE", "DELETE"):
        SCHEMA.append("""CREATE TRIGGER IF NOT EXISTS %s_no_%s BEFORE %s ON %s
                         BEGIN SELECT RAISE(ABORT, 'append-only journal'); END""" % (
            _table, _event.lower(), _event, _table))


def sha256(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


class Journal:
    def __init__(self, path, readonly=False):
        self.readonly = readonly
        self.db = storage.connect(path, readonly)
        try:
            if readonly:
                storage.is_marked(self.db, APPLICATION_ID, SCHEMA_VERSION, True, "observation")
            else:
                storage.initialise(self.db, APPLICATION_ID, SCHEMA_VERSION, SCHEMA, "observation")
        except Exception:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def _write(self, work):
        if self.readonly:
            raise Rejected("Read-only journal")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            result = work()
            self.db.execute("COMMIT")
            return result
        except Exception:
            storage.rollback(self.db)
            raise

    def _insert_fetch(self, adapter, url, requested_at, received_at, response, outcome, error, summary):
        body = response.body if response is not None else None
        cursor = self.db.execute(
            """INSERT INTO fetches(source, kind, instrument, url, requested_at, received_at, http_status,
                                   headers_json, body, body_sha256, outcome, error, summary_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (adapter.source, adapter.kind, getattr(adapter, "instrument", None), url, requested_at,
             received_at, response.status if response is not None else None,
             canonical(response.headers) if response is not None else None, body, sha256(body),
             outcome, error, canonical(summary)))
        return cursor.lastrowid

    # Rate limiting -------------------------------------------------------

    def reserve(self, adapter, url, now):
        """Cross-process limiter: refuse (and log, without network) if too early."""
        def work():
            row = self.db.execute("SELECT * FROM limiter WHERE source=?", (adapter.source,)).fetchone()
            if row is not None:
                allowed = max(row["last_requested_at"] + adapter.min_interval, row["blocked_until"])
                if now < allowed:
                    reason = "cooldown: %s" % row["reason"] if row["blocked_until"] > now else "min interval"
                    self._insert_fetch(adapter, url, now, None, None, "COOLDOWN",
                                       "%s; next request allowed at %.3f; no request sent" % (reason, allowed),
                                       {"allowed_at": allowed})
                    return allowed
            self.db.execute("""INSERT INTO limiter(source, last_requested_at, blocked_until, reason)
                               VALUES (?, ?, 0, NULL) ON CONFLICT(source)
                               DO UPDATE SET last_requested_at=excluded.last_requested_at""",
                            (adapter.source, now))
            return None

        allowed = self._write(work)
        if allowed is not None:
            raise Rejected("Rate limit: %s not before %.3f" % (adapter.source, allowed))

    # Recording -------------------------------------------------------------

    def record(self, adapter, url, requested_at, received_at, response, outcome, error=None,
               batch=None, penalty_until=None):
        if outcome not in OUTCOMES:
            raise Rejected("Unknown outcome")

        def work():
            summary, apply = {}, None
            result_outcome = outcome
            if batch is not None:
                if isinstance(batch, CandleBatch):
                    summary, apply, stale = self._plan_candles(adapter, batch, received_at, response)
                    if stale:
                        result_outcome = "STALE"
                elif isinstance(batch, NewsBatch):
                    summary, apply = self._plan_news(adapter, batch, received_at)
                elif isinstance(batch, Quote):
                    summary, apply = self._plan_quote(batch)
                else:
                    raise Rejected("Unknown batch type")
            if penalty_until is not None:
                summary = dict(summary, blocked_until=penalty_until)
            fetch_id = self._insert_fetch(adapter, url, requested_at, received_at, response,
                                          result_outcome, error, summary)
            if apply:
                apply(fetch_id)
            if penalty_until is not None:
                self.db.execute("""INSERT INTO limiter(source, last_requested_at, blocked_until, reason)
                                   VALUES (?, ?, ?, ?) ON CONFLICT(source) DO UPDATE SET
                                   blocked_until=max(blocked_until, excluded.blocked_until),
                                   reason=excluded.reason""",
                                (adapter.source, requested_at, penalty_until, error))
            return dict(summary, fetch_id=fetch_id, outcome=result_outcome, source=adapter.source,
                        body_sha256=sha256(response.body) if response is not None else None)

        return self._write(work)

    def _latest_bar(self, key):
        revision = self.db.execute(
            """SELECT open, high, low, close, volume FROM candle_revisions
               WHERE source=? AND instrument=? AND interval_s=? AND start=?
               ORDER BY seen_at DESC, id DESC LIMIT 1""", key).fetchone()
        if revision is not None:
            return tuple(revision)
        first = self.db.execute(
            """SELECT open, high, low, close, volume FROM candles
               WHERE source=? AND instrument=? AND interval_s=? AND start=?""", key).fetchone()
        return tuple(first) if first is not None else None

    def _plan_candles(self, adapter, batch, received_at, response):
        new, revised, unchanged = [], [], 0
        for bar in batch.bars:
            key = (adapter.source, batch.instrument, batch.interval_s, bar.start)
            latest = self._latest_bar(key)
            if latest is None:
                new.append(bar)
            elif latest != bar.values():
                revised.append(bar)
            else:
                unchanged += 1
        now = server_now(response.headers if response is not None else None, received_at)
        last_end = max((bar.end for bar in batch.bars), default=None)
        stale = last_end is None or last_end < now - 2 * batch.interval_s - SETTLE_SECONDS
        summary = dict(kind="candles", instrument=batch.instrument, interval_s=batch.interval_s,
                       closed=len(batch.bars), new=len(new), revisions=len(revised), unchanged=unchanged,
                       open_skipped=batch.open_skipped, duplicates_in_response=batch.duplicates,
                       last_closed_end=last_end, stale=stale)

        def apply(fetch_id):
            for bar in new:
                self.db.execute("INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (adapter.source, batch.instrument, batch.interval_s, bar.start, bar.end,
                                 *bar.values(), received_at, fetch_id))
            for bar in revised:
                self.db.execute("""INSERT INTO candle_revisions(source, instrument, interval_s, start,
                                   open, high, low, close, volume, seen_at, fetch_id)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (adapter.source, batch.instrument, batch.interval_s, bar.start,
                                 *bar.values(), received_at, fetch_id))

        return summary, apply, stale

    def _latest_story(self, source, story_key):
        revision = self.db.execute(
            """SELECT title, url, published_at, updated_at, content_sha256 FROM news_revisions
               WHERE source=? AND story_key=? ORDER BY seen_at DESC, id DESC LIMIT 1""",
            (source, story_key)).fetchone()
        if revision is not None:
            return tuple(revision)
        first = self.db.execute(
            """SELECT title, url, published_at, updated_at, content_sha256 FROM news
               WHERE source=? AND story_key=?""", (source, story_key)).fetchone()
        return tuple(first) if first is not None else None

    def _plan_news(self, adapter, batch, received_at):
        new, revised, unchanged = [], [], 0
        for item in batch.items:
            latest = self._latest_story(adapter.source, item.story_key)
            values = (item.title, item.url, item.published_at, item.updated_at, item.content_sha256)
            if latest is None:
                new.append(item)
            elif latest != values:
                revised.append(item)
            else:
                unchanged += 1
        summary = dict(kind="news", items=len(batch.items), new=len(new), revisions=len(revised),
                       unchanged=unchanged, rejected_items=batch.rejected,
                       duplicates_in_response=batch.duplicates)

        def apply(fetch_id):
            for item in new:
                self.db.execute("INSERT INTO news VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                (adapter.source, item.story_key, item.title, item.url, url_key(item.url),
                                 title_key(item.title), item.published_at, item.updated_at,
                                 int(item.published_is_updated), item.content_sha256, received_at, fetch_id))
            for item in revised:
                self.db.execute("""INSERT INTO news_revisions(source, story_key, title, url, published_at,
                                   updated_at, content_sha256, seen_at, fetch_id)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (adapter.source, item.story_key, item.title, item.url, item.published_at,
                                 item.updated_at, item.content_sha256, received_at, fetch_id))

        return summary, apply

    def _plan_quote(self, quote):
        summary = dict(kind="quote", quote_id=quote.quote_id, in_amount=quote.request.amount,
                       out_amount=quote.out_amount, router=quote.router, fee_bps=quote.fee_bps)

        def apply(fetch_id):
            self.db.execute("INSERT INTO quotes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (quote.quote_id, quote.request.input_asset.mint, quote.request.output_asset.mint,
                             quote.request.amount, quote.out_amount, quote.router, quote.fee_bps,
                             quote.started_at, quote.observed_at, fetch_id))

        return summary, apply

    # Point-in-time reads ---------------------------------------------------

    def bars_as_of(self, source, instrument, interval_s, as_of, count):
        """Latest `count` bars knowable at `as_of`, each in the version known then."""
        rows = self.db.execute(
            """SELECT c.*, f.body_sha256 FROM candles c JOIN fetches f ON f.id = c.fetch_id
               WHERE c.source=? AND c.instrument=? AND c.interval_s=? AND c.first_seen_at<=? AND c.end<=?
               ORDER BY c.start DESC LIMIT ?""",
            (source, instrument, interval_s, as_of, as_of, count)).fetchall()
        result = []
        for row in reversed(rows):
            version = dict(row)
            revision = self.db.execute(
                """SELECT r.*, f.body_sha256 FROM candle_revisions r JOIN fetches f ON f.id = r.fetch_id
                   WHERE r.source=? AND r.instrument=? AND r.interval_s=? AND r.start=? AND r.seen_at<=?
                   ORDER BY r.seen_at DESC, r.id DESC LIMIT 1""",
                (source, instrument, interval_s, row["start"], as_of)).fetchone()
            if revision is not None:
                version.update({k: revision[k] for k in ("open", "high", "low", "close", "volume")},
                               seen_at=revision["seen_at"], fetch_id=revision["fetch_id"],
                               body_sha256=revision["body_sha256"], revised=True)
            else:
                version.update(seen_at=row["first_seen_at"], revised=False)
            result.append(version)
        return result

    def stories_as_of(self, sources, as_of, since):
        """Stories first seen by `as_of`, deduplicated across sources by URL or title."""
        marks = ",".join("?" * len(sources))
        rows = [dict(row) for row in self.db.execute(
            """SELECT * FROM news WHERE source IN (%s) AND first_seen_at<=? AND first_seen_at>=?
               ORDER BY first_seen_at, source, story_key""" % marks,
            (*sources, as_of, since)).fetchall()] if sources else []
        for row in rows:
            revision = self.db.execute(
                """SELECT title, url, published_at, updated_at FROM news_revisions
                   WHERE source=? AND story_key=? AND seen_at<=? ORDER BY seen_at DESC, id DESC LIMIT 1""",
                (row["source"], row["story_key"], as_of)).fetchone()
            if revision is not None:
                row.update(dict(revision), revised=True)
            else:
                row["revised"] = False
        # Union by url_key or title_key; the earliest first sighting represents the story.
        parent = list(range(len(rows)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        seen = {}
        for index, row in enumerate(rows):
            for key in ("url_key", "title_key"):
                other = seen.setdefault((key, row[key]), index)
                parent[find(index)] = find(other)
        stories = {}
        for index, row in enumerate(rows):
            stories.setdefault(find(index), []).append(row)
        return [group for _, group in sorted(stories.items())]

    def status(self):
        counts = {table: self.db.execute("SELECT count(*) FROM %s" % table).fetchone()[0]
                  for table in ("fetches", "candles", "candle_revisions", "news", "news_revisions", "quotes")}
        outcomes = [dict(row) for row in self.db.execute(
            "SELECT source, outcome, count(*) AS n, max(requested_at) AS last FROM fetches GROUP BY source, outcome")]
        series = []
        for row in self.db.execute("SELECT DISTINCT source, instrument, interval_s FROM candles"):
            starts = [r[0] for r in self.db.execute(
                "SELECT start FROM candles WHERE source=? AND instrument=? AND interval_s=? ORDER BY start",
                tuple(row))]
            gaps = [dict(after=a, before=b, missing=int((b - a) / row["interval_s"]) - 1)
                    for a, b in zip(starts, starts[1:]) if b - a != row["interval_s"]]
            series.append(dict(row, bars=len(starts), first=starts[0], last=starts[-1],
                               gaps=gaps[:20], gap_count=len(gaps)))
        limiter = [dict(row) for row in self.db.execute("SELECT * FROM limiter")]
        return dict(counts=counts, outcomes=outcomes, candle_series=series, limiter=limiter,
                    application_id=APPLICATION_ID, schema_version=SCHEMA_VERSION)
