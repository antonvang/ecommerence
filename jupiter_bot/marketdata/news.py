"""News/status adapters. Content is data: stored, hashed, shown, never obeyed.

Only a title, an HTTPS link and times are kept, plus a hash of the raw entry
for revision detection. No article bodies are stored or passed to any model,
and nothing here can change trading or wallet limits.
"""
from __future__ import annotations

import email.utils
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ..core import Rejected, canonical, strict_json
from .transport import Endpoint

MAX_TITLE = 300
TRACKING = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_src$)")


@dataclass(frozen=True)
class NewsItem:
    story_key: str
    title: str
    url: str
    published_at: float
    updated_at: float
    published_is_updated: bool
    content_sha256: str


@dataclass(frozen=True)
class NewsBatch:
    feed: str
    items: tuple
    rejected: int
    duplicates: int


def clean_text(value):
    """Plain single-line text: no control or format characters, bounded length."""
    if not isinstance(value, str):
        raise Rejected("Text field must be a string")
    text = "".join(" " if unicodedata.category(ch)[0] in "CZ" else ch for ch in value)
    text = " ".join(text.split())
    if not text:
        raise Rejected("Empty text field")
    return text[:MAX_TITLE]


def normalise_url(url):
    if not isinstance(url, str):
        raise Rejected("News link must be a string")
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port  # raises ValueError for an invalid port
    except ValueError as exc:
        raise Rejected("Malformed news link") from exc
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise Rejected("News link must be a plain HTTPS URL")
    query = urlencode([(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                       if not TRACKING.match(k.lower())])
    path = parsed.path.rstrip("/") or "/"
    netloc = parsed.hostname.lower() + (":%d" % port if port else "")
    return urlunsplit(("https", netloc, path, query, ""))


def title_key(title):
    folded = unicodedata.normalize("NFKD", title).casefold()
    return hashlib.sha256(" ".join(re.findall(r"\w+", folded)).encode()).hexdigest()


def url_key(url):
    return hashlib.sha256(normalise_url(url).encode()).hexdigest()


def iso_time(value):
    if not isinstance(value, str):
        raise Rejected("Timestamp must be an ISO 8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise Rejected("Unparseable ISO 8601 time") from exc
    if parsed.tzinfo is None:
        raise Rejected("Timestamp without timezone")
    return parsed.timestamp()


def rfc822_time(value):
    text = (value or "").strip() if isinstance(value, str) else ""
    try:
        parsed = email.utils.parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError) as exc:
        raise Rejected("Unparseable RFC 822 time") from exc
    if parsed is not None and parsed.tzinfo is None and text.endswith("-0000"):
        # RFC 5322 3.3: "-0000" is UTC with unknown local zone. Python returns
        # it naive, exactly like a missing zone, so decide from the text.
        # (Seen live in status.jup.ag/feed.rss, 2026-11-20.)
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed is None or parsed.tzinfo is None:
        raise Rejected("Timestamp without timezone")
    return parsed.timestamp()


def make_item(story_key, title, url, published, updated, raw):
    published_is_updated = published is None
    published = updated if published is None else published
    updated = published if updated is None else updated
    if published is None:
        raise Rejected("Item has no time")
    return NewsItem(clean_text(story_key)[:200], clean_text(title), normalise_url(url),
                    published, updated, published_is_updated,
                    hashlib.sha256(raw.encode() if isinstance(raw, str) else raw).hexdigest())


def collect(feed, candidates):
    """Per-item failures are counted, not fatal; identical repeats merged."""
    items, rejected, duplicates = {}, 0, 0
    for build in candidates:
        try:
            item = build()
        except Rejected:
            rejected += 1
            continue
        if item.story_key in items:
            if items[item.story_key] != item:
                raise Rejected("Conflicting duplicate story in one response")
            duplicates += 1
            continue
        items[item.story_key] = item
    return NewsBatch(feed, tuple(items.values()), rejected, duplicates)


class StatuspageIncidents:
    """Atlassian Statuspage v2 `incidents.json` (format used by status.solana.com)."""

    kind = "news"
    min_interval = 60.0
    default_cooldown = 300.0
    ban_cooldown = 3600.0

    def __init__(self, source, host):
        self.source = source
        self.endpoint = Endpoint(host, "/api/v2/incidents.json")
        self.host = host

    def params(self):
        return {}

    def parse(self, body, requested_at, received_at, headers):
        document = strict_json(body)
        incidents = document.get("incidents") if isinstance(document, dict) else None
        if not isinstance(incidents, list):
            raise Rejected("Expected an incidents list")

        def builder(incident):
            def build():
                if not isinstance(incident, dict) or not isinstance(incident.get("id"), str):
                    raise Rejected("Incident without id")
                link = incident.get("shortlink") or "https://%s/incidents/%s" % (self.host, incident["id"])
                name, status = incident.get("name"), incident.get("status")
                if not isinstance(name, str):
                    raise Rejected("Incident without name")
                title = "%s [%s]" % (name, status) if isinstance(status, str) else name
                return make_item(incident["id"], title, link, iso_time(incident.get("created_at")),
                                 iso_time(incident.get("updated_at") or incident.get("created_at")),
                                 canonical(incident))
            return build

        return collect(self.source, (builder(incident) for incident in incidents))


ATOM = "{http://www.w3.org/2005/Atom}"


def parse_xml(body):
    # Feeds need no DTD. Refusing DOCTYPE/ENTITY rules out entity-expansion tricks.
    if not isinstance(body, bytes):
        raise Rejected("Feed body must be raw bytes")
    lowered = body.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise Rejected("XML with DOCTYPE or ENTITY declarations is refused")
    try:
        return ElementTree.fromstring(body)
    except ElementTree.ParseError as exc:
        raise Rejected("Malformed XML") from exc


class Feed:
    """RSS 2.0 or Atom 1.0 feed from one fixed URL."""

    kind = "news"
    min_interval = 60.0
    default_cooldown = 300.0
    ban_cooldown = 3600.0

    def __init__(self, source, host, path):
        self.source = source
        self.endpoint = Endpoint(host, path, accept="application/atom+xml, application/rss+xml, application/xml")

    def params(self):
        return {}

    def parse(self, body, requested_at, received_at, headers):
        root = parse_xml(body)
        if root.tag == ATOM + "feed":
            candidates = (self._atom(entry) for entry in root.findall(ATOM + "entry"))
        elif root.tag == "rss" and root.find("channel") is not None:
            candidates = (self._rss(item) for item in root.find("channel").findall("item"))
        else:
            raise Rejected("Neither RSS 2.0 nor Atom")
        return collect(self.source, candidates)

    @staticmethod
    def _atom(entry):
        def build():
            link = None
            for candidate in entry.findall(ATOM + "link"):
                if candidate.get("rel", "alternate") == "alternate" and candidate.get("href"):
                    link = candidate.get("href")
                    break
            published = entry.findtext(ATOM + "published")
            updated = entry.findtext(ATOM + "updated")
            return make_item(entry.findtext(ATOM + "id") or link, entry.findtext(ATOM + "title"), link or "",
                             iso_time(published) if published else None,
                             iso_time(updated) if updated else None,
                             ElementTree.tostring(entry))
        return build

    @staticmethod
    def _rss(item):
        def build():
            link = item.findtext("link") or ""
            date = item.findtext("pubDate")
            return make_item(item.findtext("guid") or link, item.findtext("title"), link,
                             rfc822_time(date) if date else None, None, ElementTree.tostring(item))
        return build


NEWS_FEEDS = {
    "solana_status": lambda: StatuspageIncidents("solana_status", "status.solana.com"),
    "jupiter_status": lambda: Feed("jupiter_status", "status.jup.ag", "/feed.rss"),
    "agave_releases": lambda: Feed("agave_releases", "github.com", "/anza-xyz/agave/releases.atom"),
}
