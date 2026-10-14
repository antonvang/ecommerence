"""Polite fetcher for public storefront pages: robots.txt (Google-style wildcards), rate limit, request cap."""
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (compatible; GMC-Doktor/0.1; offentligt Merchant Center-tjek af butikssider)"
UA_TOKEN = "gmc-doktor"
_CTX = ssl.create_default_context()


class Robots:
    """Minimal robots.txt matcher with '*' and '$' support. Longest match wins; allow wins ties."""

    def __init__(self, text, token=UA_TOKEN):
        self.rules = []
        groups, agents, rules, in_rules = [], [], [], False
        for raw in (text or "").splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            k, v = [x.strip() for x in line.split(":", 1)]
            k = k.lower()
            if k == "user-agent":
                if in_rules:
                    groups.append((agents, rules))
                    agents, rules, in_rules = [], [], False
                agents.append(v.lower())
            elif k in ("allow", "disallow"):
                in_rules = True
                if v:
                    rules.append((k == "allow", v))
        groups.append((agents, rules))
        mine = [r for a, r in groups if any(token in x for x in a)]
        star = [r for a, r in groups if "*" in a]
        self.rules = [x for r in (mine or star) for x in r]

    @staticmethod
    def _match(pattern, path):
        rx = "^" + re.escape(pattern).replace(r"\*", ".*")
        if rx.endswith(r"\$"):
            rx = rx[:-2] + "$"
        m = re.match(rx, path)
        return len(pattern) if m else -1

    def allowed(self, path):
        best_len, best_allow = -1, True
        for allow, pat in self.rules:
            n = self._match(pat, path)
            if n > best_len or (n == best_len and n >= 0 and allow):
                best_len, best_allow = n, allow
        return best_allow if best_len >= 0 else True


class Fetcher:
    def __init__(self, domain, min_interval=1.0, max_requests=15, timeout=20):
        d = domain.strip().lower()
        d = re.sub(r"^https?://", "", d).split("/")[0]
        self.domain = d
        self.base = "https://" + d
        self.min_interval, self.max_requests, self.timeout = min_interval, max_requests, timeout
        self.n, self._last = 0, 0.0
        self.log = []
        st, _, _, txt = self._raw("/robots.txt")
        self.robots_txt = txt if st == 200 else ""
        self.robots = Robots(self.robots_txt)

    def _raw(self, path):
        wait = self.min_interval - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        self.n += 1
        url = self.base + path
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "da-DK,da;q=0.9,en;q=0.5"})
        try:
            r = urllib.request.urlopen(req, timeout=self.timeout, context=_CTX)
            body = r.read(3_000_000).decode("utf-8", "ignore")
            out = (r.status, r.geturl(), dict(r.headers), body)
        except urllib.error.HTTPError as e:
            out = (e.code, url, dict(e.headers or {}), "")
        except Exception as e:  # DNS, TLS, timeout
            out = (None, url, {}, f"ERROR: {e}")
        self.log.append((path, out[0]))
        return out

    def get(self, path):
        """Returns (status, final_url, headers, text); status 'robots' if disallowed, 'cap' if over the request cap."""
        p = urllib.parse.urlsplit(path)
        path_only = p.path + (("?" + p.query) if p.query else "")
        if not self.robots.allowed(path_only):
            self.log.append((path, "robots"))
            return ("robots", self.base + path, {}, "")
        if self.n >= self.max_requests:
            return ("cap", self.base + path, {}, "")
        return self._raw(path)
