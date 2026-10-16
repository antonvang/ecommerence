"""HTTP-hjælpere: JSON over urllib (ingen ekstra pakker), retry, rate limit og diskcache."""
from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

HEADERS = {"User-Agent": "Mozilla/5.0 (copybot-paper/1.0)", "Accept": "application/json"}
RETRY_CODES = (403, 429, 500, 502, 503, 504)  # PublicNode svarer 403 (ikke 429), når man spørger for tit


def http_json(url, payload=None, timeout=30, tries=6, log=print):
    body = json.dumps(payload).encode() if payload is not None else None
    headers = dict(HEADERS)
    if body is not None:
        headers["Content-Type"] = "application/json"
    wait = 2.0
    host = urllib.parse.urlparse(url).netloc
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES or attempt == tries - 1:
                raise
            log(f"  {host} svarede {e.code}, venter {wait:.0f} sek ...")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if attempt == tries - 1:
                raise
            log(f"  forbindelsesfejl til {host} ({e}), venter {wait:.0f} sek ...")
        time.sleep(wait)
        wait = min(wait * 2, 60)


class Throttle:
    """Højst én request pr. `interval` sekunder."""

    def __init__(self, interval):
        self.interval = interval
        self.last = 0.0

    def wait(self):
        d = self.last + self.interval - time.time()
        if d > 0:
            time.sleep(d)
        self.last = time.time()


class DiskCache:
    def __init__(self, folder):
        self.folder = folder
        if folder:
            os.makedirs(folder, exist_ok=True)

    def _path(self, key):
        return os.path.join(self.folder, hashlib.sha1(key.encode()).hexdigest() + ".json")

    def get(self, key):
        if not self.folder:
            return None
        try:
            with open(self._path(key), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def put(self, key, value):
        if not self.folder:
            return
        tmp = self._path(key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f)
        os.replace(tmp, self._path(key))
