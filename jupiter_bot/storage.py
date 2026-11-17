"""SQLite files that identify themselves. Foreign databases are never written.

Each jupiter_bot database carries a fixed `PRAGMA application_id` and a schema
`user_version`, set in the same write transaction that creates its tables.
A non-empty file without that marker (for example a Copybot database) is
refused before any statement that could change it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .core import Rejected


def connect(path, readonly=False):
    if readonly:
        if str(path) == ":memory:" or not Path(path).is_file():
            raise Rejected("Database does not exist")
        db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True,
                             timeout=10, isolation_level=None)
    else:
        db = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    return db


def rollback(db):
    # A failed BEGIN (e.g. "database is locked") leaves no transaction; a blind
    # ROLLBACK would then replace the real error with a misleading one.
    if db.in_transaction:
        db.execute("ROLLBACK")


def is_marked(db, application_id, version, readonly, label):
    """True if marked as ours, False if empty and claimable; otherwise Rejected."""
    app_id = db.execute("PRAGMA application_id").fetchone()[0]
    has_tables = db.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] > 0
    if app_id != application_id and (has_tables or app_id != 0 or readonly):
        raise Rejected("Not a jupiter_bot %s database; refusing to read or write it" % label)
    if app_id == application_id and db.execute("PRAGMA user_version").fetchone()[0] != version:
        raise Rejected("Unsupported %s database schema version" % label)
    return app_id == application_id


def initialise(db, application_id, version, schema, label, extra=None):
    """Claim an empty file or verify ours, create tables and run `extra`, atomically."""
    db.execute("PRAGMA foreign_keys=ON")
    try:
        db.execute("BEGIN IMMEDIATE")
        if not is_marked(db, application_id, version, False, label):
            db.execute("PRAGMA application_id=%d" % application_id)
            db.execute("PRAGMA user_version=%d" % version)
        for statement in schema:
            db.execute(statement)
        result = extra(db) if extra else None
        db.execute("COMMIT")
        return result
    except Exception:
        rollback(db)
        raise
