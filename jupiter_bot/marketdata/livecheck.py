"""One-time live format check: one fetch per source into a fresh journal.

Purpose: compare real responses with the parsers' assumptions before any
continuous collection. It is not data collection, research or trading.

Writes into a NEW directory (default under the git-ignored runtime/):
- observations.db   the normal journal (raw bodies + SHA-256 for every fetch)
- raw/<id>-<source>  each raw body as received
- summary.json       small, shareable: outcomes, status, headers, clock skew,
                     structure sketches, and the full public Jupiter quote
                     payloads (no taker, no wallet). Send this file back.
"""
from __future__ import annotations

import json
import platform
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from ..core import SOL, USDC, QuoteRequest, Rejected, atoms, strict_json
from .candles import BinanceKlines, server_now
from .journal import Journal
from .news import NEWS_FEEDS, parse_xml
from .observe import observe
from .quotes import JupiterQuoteSample
from .transport import https_get

NOTE = ("Live format check only: one fetch per source. Not research data, "
        "no profit claim, no orders, no wallet, no keys.")


def plan():
    """The fixed list of single fetches, in order."""
    return [
        ("candles SOL/USDC 1m", lambda: BinanceKlines(interval="1m", limit=5)),
        ("quote USDC->SOL 25", lambda: JupiterQuoteSample(QuoteRequest(USDC, SOL, atoms("25", USDC)))),
        ("quote SOL->USDC 0.1", lambda: JupiterQuoteSample(QuoteRequest(SOL, USDC, atoms("0.1", SOL)))),
    ] + [("news " + name, factory) for name, factory in NEWS_FEEDS.items()]


def sketch(value, depth=0):
    """Structure with short sample values; enough to fix a parser, small to share."""
    if depth > 6:
        return "..."
    if isinstance(value, dict):
        items = list(value.items())
        result = {key: sketch(item, depth + 1) for key, item in items[:80]}
        if len(items) > 80:
            result["..."] = "%d more keys" % (len(items) - 80)
        return result
    if isinstance(value, list):
        result = [sketch(item, depth + 1) for item in value[:2]]
        return result + (["... %d more" % (len(value) - 2)] if len(value) > 2 else [])
    return "%s:%s" % (type(value).__name__, repr(value)[:120])


def sketch_xml(element, depth=0, siblings=2):
    if depth > 5:
        return "..."
    text = (element.text or "").strip()
    node = {"tag": element.tag, "attrs": sorted(element.attrib)}
    if text:
        node["text"] = text[:120]
    children, counts = [], {}
    for child in element:
        counts[child.tag] = counts.get(child.tag, 0) + 1
        if counts[child.tag] <= siblings:
            children.append(sketch_xml(child, depth + 1, siblings))
    if children:
        node["children"] = children
    if any(n > siblings for n in counts.values()):
        node["counts"] = counts
    return node


def describe_body(body, content_type):
    if not body:
        return None
    try:
        return {"json": sketch(strict_json(body))}
    except Exception:
        pass
    try:
        return {"xml": sketch_xml(parse_xml(body))}
    except (Rejected, ElementTree.ParseError):
        return {"unparsed_head": body[:300].decode("utf-8", "replace")}


def fetch_report(row, out_dir):
    row = dict(row)
    body = row.pop("body")
    headers = json.loads(row["headers_json"]) if row["headers_json"] else {}
    if body is not None:
        (out_dir / "raw" / ("%d-%s.bin" % (row["id"], row["source"]))).write_bytes(body)
    report = dict(outcome=row["outcome"], http_status=row["http_status"], url=row["url"], headers=headers,
                  body_bytes=len(body) if body is not None else None, body_sha256=row["body_sha256"],
                  error=row["error"], summary=json.loads(row["summary_json"]),
                  structure=describe_body(body, headers.get("content-type")))
    if headers.get("date") and row["received_at"] is not None:
        # Positive: the server clock is ahead of ours (1 s Date resolution).
        report["server_minus_local_s"] = round(server_now(headers, float("inf")) - row["received_at"], 3)
    if row["source"] == "jupiter_quote" and body:
        try:
            report["full_public_payload"] = strict_json(body)
        except Exception:
            pass
    return report


def run(out_dir, fetch=https_get, clock=time.time, sleep=time.sleep):
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise Rejected("Output directory already exists; use a new one")
    (out_dir / "raw").mkdir(parents=True)
    journal = Journal(out_dir / "observations.db")
    checks = []
    try:
        for label, factory in plan():
            adapter = factory()
            # Wait out the journal limiter instead of tripping it (Jupiter is asked twice).
            row = journal.db.execute("SELECT last_requested_at, blocked_until FROM limiter WHERE source=?",
                                     (adapter.source,)).fetchone()
            if row is not None:
                wait = max(row[0] + adapter.min_interval, row[1]) - clock()
                if 0 < wait <= 30:
                    sleep(wait + 0.1)
            before = journal.db.execute("SELECT coalesce(max(id), 0) FROM fetches").fetchone()[0]
            entry = {"check": label, "source": adapter.source}
            try:
                entry["result"] = observe(journal, adapter, fetch=fetch, clock=clock)
            except Rejected as exc:
                entry["error"] = str(exc)
            # observe() writes exactly one fetches row per call, success or not.
            rows = journal.db.execute("SELECT * FROM fetches WHERE id > ? ORDER BY id", (before,)).fetchall()
            entry["fetches"] = [fetch_report(fetch_row, out_dir) for fetch_row in rows]
            checks.append(entry)
    finally:
        journal.close()
    summary = dict(note=NOTE, python=platform.python_version(), system=platform.system(),
                   finished_at=clock(), checks=checks)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return dict(note=NOTE, summary=str(out_dir / "summary.json"),
                outcomes=[dict(check=entry["check"],
                               outcome=[f["outcome"] for f in entry["fetches"]],
                               error=entry.get("error")) for entry in checks])
