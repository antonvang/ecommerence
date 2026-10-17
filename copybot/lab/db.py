"""Storage: SQLite (WAL). Append-only tables are protected by triggers and hash-chained per table."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(HERE, "data", "lab", "lab.db")
GENESIS = "0" * 64

# column order matters: it defines the hashed content of each row
TABLES = {
    "events": ("ts", "kind", "actor", "exp_id", "payload"),
    "experiments": ("exp_id", "version", "created_ts", "mechanism_tag", "fingerprint", "spec_json", "spec_path",
                    "spec_commit", "code_hash", "note"),
    "transitions": ("exp_id", "ts", "from_state", "to_state", "actor", "reason", "evidence"),
    "results": ("exp_id", "version", "ts", "label", "verdict", "metrics", "evidence", "supersedes"),
    "alpha_ledger": ("exp_id", "ts", "alpha", "note"),
    "approvals": ("code_hash", "exp_id", "to_state", "ts", "expires_ts", "actor", "reason", "evidence"),
    "observations": ("ts", "detector", "source", "instrument", "metric", "value", "threshold", "flagged", "payload"),
    "datasets": ("exp_id", "split", "source", "path", "window_start", "window_end", "ts", "sha256", "size", "purpose",
                 "code_hash"),
}

SCHEMA = "\n".join(
    f"CREATE TABLE IF NOT EXISTS {t}(id INTEGER PRIMARY KEY AUTOINCREMENT, "
    + ", ".join(f"{c}" for c in cols) + ", prev_hash TEXT NOT NULL, hash TEXT NOT NULL UNIQUE);\n"
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_update BEFORE UPDATE ON {t} BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;\n"
    f"CREATE TRIGGER IF NOT EXISTS {t}_no_delete BEFORE DELETE ON {t} BEGIN SELECT RAISE(ABORT, '{t} is append-only'); END;"
    for t, cols in TABLES.items()
) + """
CREATE UNIQUE INDEX IF NOT EXISTS experiments_ver ON experiments(exp_id, version);
CREATE INDEX IF NOT EXISTS transitions_exp ON transitions(exp_id, id);
CREATE INDEX IF NOT EXISTS results_exp ON results(exp_id, id);
CREATE INDEX IF NOT EXISTS datasets_exp ON datasets(exp_id, split, path);
CREATE INDEX IF NOT EXISTS observations_det ON observations(detector, metric, instrument, ts);
"""


def canonical(row):
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def row_hash(prev, table, row):
    return hashlib.sha256((prev + "|" + table + "|" + canonical(row)).encode()).hexdigest()


class DB:
    def __init__(self, path=DEFAULT_DB):
        if path != ":memory:":
            os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.con = sqlite3.connect(path, timeout=30, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        if path != ":memory:":
            self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(SCHEMA)

    def last_hash(self, table):
        r = self.con.execute(f"SELECT hash FROM {table} ORDER BY id DESC LIMIT 1").fetchone()
        return r[0] if r else GENESIS

    def append(self, table, **row):
        """Insert one row; returns its id. Must be called inside a transaction for multi-row consistency."""
        cols = TABLES[table]
        unknown = set(row) - set(cols)
        if unknown:
            raise ValueError(f"unknown columns for {table}: {sorted(unknown)}")
        vals = {c: row.get(c) for c in cols}
        for k, v in vals.items():
            if isinstance(v, (dict, list)):
                vals[k] = canonical(v)
        prev = self.last_hash(table)
        h = row_hash(prev, table, vals)
        cur = self.con.execute(f"INSERT INTO {table}({', '.join(cols)}, prev_hash, hash) VALUES "
                               f"({', '.join('?' for _ in cols)}, ?, ?)", [vals[c] for c in cols] + [prev, h])
        return cur.lastrowid

    def event(self, kind, actor, exp_id=None, payload=None):
        return self.append("events", ts=int(time.time()), kind=kind, actor=actor, exp_id=exp_id, payload=payload or {})

    def tx(self):
        return _Tx(self.con)

    def q(self, sql, *a):
        return self.con.execute(sql, a).fetchall()

    def one(self, sql, *a):
        return self.con.execute(sql, a).fetchone()

    def verify(self):
        """Re-walk every chain. Returns {table: (rows, first_bad_id or None)} and whether triggers are present."""
        out = {}
        for t, cols in TABLES.items():
            prev, bad, n = GENESIS, None, 0
            for r in self.con.execute(f"SELECT * FROM {t} ORDER BY id"):
                n += 1
                vals = {c: r[c] for c in cols}
                if r["prev_hash"] != prev or row_hash(prev, t, vals) != r["hash"]:
                    bad = r["id"]
                    break
                prev = r["hash"]
            out[t] = (n, bad)
        trig = {r[0] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        need = {f"{t}_no_{k}" for t in TABLES for k in ("update", "delete")}
        return out, need <= trig

    def close(self):
        self.con.close()


class _Tx:
    def __init__(self, con):
        self.con = con

    def __enter__(self):
        self.con.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, et, e, tb):
        self.con.execute("ROLLBACK" if et else "COMMIT")
        return False
