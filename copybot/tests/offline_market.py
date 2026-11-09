"""Offline market fixture for tests (director orders 59-E/59-F P2). Protected data must never depend on DNS: a test
that reaches the market-data download layer without a fixture fails closed with OfflineFixtureMissing, and never
downloads.

- data.CACHE points at an empty temporary directory, so no cached real file (2024 holdout included) is ever opened;
- data._fetch returns only files inside that temporary directory and raises OfflineFixtureMissing for anything else
  (no retries, no sleep, no fallback to another cache);
- urllib.request.urlopen raises OfflineFixtureMissing, as a second line;
- synthetic_files_for writes small synthetic stand-in files (no market data) for a test that only needs paths;
- market_cache(tmp) points data.CACHE (and so families.absent / hypogen.missing) at a temporary directory holding a
  synthetic absent_404.json, for a test that must not read the checkout's data/lab/market (order 59-H P1);
- file_guard() patches open/io.open/os.open so a protected path (a real market cache, a real 2024 zip, a lab or research
  database outside the temporary directory) raises ProtectedFileAccess. No host-specific path is named here.
"""
import builtins
import fnmatch
import io
import json
import os
import tempfile
import urllib.request
from unittest import mock

BLOCKED = "BLOCKED: no offline fixture"
TEMP = os.path.realpath(tempfile.gettempdir())


class OfflineFixtureMissing(AssertionError):
    """A test reached a real market-data download. Supply a synthetic fixture; never download."""


class ProtectedFileAccess(OfflineFixtureMissing):
    """A test tried to open protected data (a real market cache, a 2024 zip, a real lab/research database)."""


def in_temp(path):
    p = os.path.realpath(os.fspath(path))
    return p == TEMP or p.startswith(TEMP + os.sep)


def _quarantined():
    """Repo-relative paths of the quarantine register (order 73). Only the register is read, never a listed file."""
    register = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "research", "data",
                            "QUARANTINE.json")
    with open(register, encoding="utf-8") as fh:
        return tuple(e["path"].replace("/", os.sep) for e in json.load(fh)["entries"] if e.get("path"))


QUARANTINED = _quarantined()


def is_quarantined(path):
    """True for a path in the quarantine register, in any checkout. String work only: the file is not even stat'ed."""
    try:
        p = os.path.abspath(os.fsdecode(path))
    except TypeError:                            # a file descriptor, not a path
        return False
    return any(p.endswith(os.sep + rel) for rel in QUARANTINED)


def quarantine_wrappers(real_open, real_os_open):
    """open and os.open stand-ins that refuse a quarantined path before calling the real function."""
    def check(path):
        if not isinstance(path, int) and is_quarantined(path):
            raise ProtectedFileAccess(f"{BLOCKED}: quarantined file")

    def guarded_open(file, *a, **k):
        check(file)
        return real_open(file, *a, **k)

    def guarded_os_open(path, *a, **k):
        check(path)
        return real_os_open(path, *a, **k)
    return guarded_open, guarded_os_open


_process_guard = False


def install_quarantine_guard():
    """Process-wide and idempotent; tests/__init__.py calls it, so `python3 -m unittest tests.x` cannot open the file."""
    global _process_guard
    if _process_guard:
        return
    _process_guard = True
    guarded_open, guarded_os_open = quarantine_wrappers(builtins.open, os.open)
    builtins.open = io.open = guarded_open
    os.open = guarded_os_open


def protected(path):
    """True for a quarantined file, a real market cache file, a 2024 zip or a lab/research database outside the
    temporary directory."""
    if is_quarantined(path):
        return True
    try:
        p = os.path.realpath(os.fspath(path))
    except TypeError:                            # a file descriptor, not a path
        return False
    if in_temp(p):
        return False
    return (fnmatch.fnmatch(p, "*/data/lab/market/*") or fnmatch.fnmatch(os.path.basename(p), "*2024-*.zip")
            or fnmatch.fnmatch(p, "*/data/lab/*.db*") or fnmatch.fnmatch(p, "*/data/research/*"))


def _fetcher(cache):
    root = os.path.realpath(cache)

    def fetch(url, path, get=None):
        p = os.path.realpath(path)
        if (p.startswith(root + os.sep)) and os.path.exists(p):   # only the test's own temporary cache
            return path
        raise OfflineFixtureMissing(f"{BLOCKED}: {url}")
    return fetch


def _blocked_urlopen(req, *a, **k):
    url = getattr(req, "full_url", req)
    raise OfflineFixtureMissing(f"{BLOCKED}: {url}")


def patches(tmp):
    """Patchers that keep the data layer offline: start() them in setUp, stop() them in tearDown."""
    from lab.engine import data
    cache = os.path.join(tmp, "offline-market")
    os.makedirs(cache, exist_ok=True)
    return [mock.patch.object(data, "CACHE", cache), mock.patch.object(data, "_fetch", _fetcher(cache)),
            mock.patch.object(urllib.request, "urlopen", _blocked_urlopen)]


def file_guard(seen=None):
    """Patchers for open/io.open/os.open that raise ProtectedFileAccess on a protected path (appended to `seen`)."""
    real_open, real_os_open = builtins.open, os.open

    def check(path):
        if not isinstance(path, int) and protected(path):
            if seen is not None:
                seen.append(os.fspath(path))
            raise ProtectedFileAccess(f"{BLOCKED}: protected file {os.fspath(path)}")

    def guarded_open(file, *a, **k):
        check(file)
        return real_open(file, *a, **k)

    def guarded_os_open(path, *a, **k):
        check(path)
        return real_os_open(path, *a, **k)
    return [mock.patch.object(builtins, "open", guarded_open), mock.patch.object(io, "open", guarded_open),
            mock.patch.object(os, "open", guarded_os_open)]


def synthetic_absent():
    """Synthetic 404 URLs in the format families._mark_absent writes (made-up symbols, no 2024 month, no real data)."""
    from lab.engine import data
    return sorted({f"{data.BASE}/klines/SYNTHAUSDT/1h/SYNTHAUSDT-1h-2021-03.zip",
                   f"{data.BASE}/fundingRate/SYNTHAUSDT/SYNTHAUSDT-fundingRate-2021-03.zip",
                   f"{data.SPOT_BASE}/klines/SYNTHBUSDT/1h/SYNTHBUSDT-1h-2020-11.zip"})


def market_cache(tmp, absent=None):
    """A patcher for data.CACHE -> tmp/offline-market, which holds a synthetic absent_404.json (`absent`, default
    synthetic_absent()). Only the cache path changes: data._fetch and urlopen stay as they are (see patches())."""
    from lab.engine import data
    cache = os.path.join(tmp, "offline-market")
    os.makedirs(cache, exist_ok=True)
    with open(os.path.join(cache, "absent_404.json"), "w", encoding="utf-8") as fh:
        json.dump(synthetic_absent() if absent is None else sorted(absent), fh)
    return mock.patch.object(data, "CACHE", cache)


def synthetic_files_for(tmp):
    """A data.files_for stand-in: one synthetic klines and one funding file per symbol and split, in tmp."""
    def files_for(sym, split, get=None):
        out = {}
        for kind in ("klines", "funding"):
            p = os.path.join(tmp, f"synthetic-{sym}-{split}-{kind}.csv")
            with open(p, "w") as fh:
                fh.write(f"synthetic {kind} for {sym} {split}: no market data\n")
            out[kind] = [p]
        return out
    return files_for
