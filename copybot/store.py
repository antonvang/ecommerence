"""SQLite-lager for positioner, hændelser og balancehistorik."""
from __future__ import annotations

import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book TEXT, wallet TEXT, mint TEXT, symbol TEXT,
  opened_ts INTEGER, closed_ts INTEGER,
  cost_usd REAL, tokens REAL, tokens_left REAL, entry_price REAL, last_price REAL,
  proceeds_usd REAL DEFAULT 0, costs_usd REAL DEFAULT 0, pnl_usd REAL, reason TEXT,
  leader_entry REAL, leader_exit REAL);
CREATE INDEX IF NOT EXISTS ix_pos_open ON positions(closed_ts, book);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, kind TEXT, wallet TEXT, text TEXT, pnl REAL);
CREATE TABLE IF NOT EXISTS equity (ts INTEGER, equity REAL, wallet TEXT);
CREATE TABLE IF NOT EXISTS seen (sig TEXT PRIMARY KEY);
"""


class Store:
    def __init__(self, path=":memory:"):
        self.path = path
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)

    def get(self, k, default=None):
        r = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else default

    def set(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO kv(k, v) VALUES(?, ?)", (k, json.dumps(v)))

    def q(self, sql, *a):
        return self.db.execute(sql, a).fetchall()

    def one(self, sql, *a):
        return self.db.execute(sql, a).fetchone()

    def x(self, sql, *a):
        return self.db.execute(sql, a).lastrowid

    def begin(self):
        self.db.execute("BEGIN")

    def commit(self):
        self.db.execute("COMMIT")

    def close(self):
        self.db.close()
