"""Short public facts about each call target, so the caller knows who they are calling.

From the store's own pages only (robots.txt respected, ~1 request/second via gmcdoktor.fetch.Fetcher):
name (og:site_name / <title>), one-line description (meta description), what they sell (top product types,
else three example products), product count, and the town from the address the checker already found.
Writes data/store_info.json (local only; data/ is gitignored)."""
import json
import os
import re
import sys
from collections import Counter
from html import unescape

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from gmcdoktor.fetch import Fetcher  # noqa: E402


def meta(html, *names):
    for n in names:
        m = re.search(r'<meta[^>]+(?:name|property)=["\']%s["\'][^>]*content=["\']([^"\']*)' % re.escape(n), html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:name|property)=["\']%s["\']' % re.escape(n), html, re.I)
        if m and m.group(1).strip():
            return unescape(m.group(1)).strip()
    return ""


def short(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0].rstrip(" ,.;:-") + " …"


TOWN = re.compile(r"\b(\d{4})\s+([A-ZÆØÅ][a-zæøå]+(?:[ -][A-ZÆØÅ][a-zæøå]+)?(?:\s(?:C|K|V|Ø|N|S|SV|NV|SØ|NØ)\b)?)")
NOT_TOWN = {"Mobil", "Tlf", "Telefon", "Tel", "Email", "Mail", "Cvr", "Danmark", "Denmark", "Kontakt", "Åbningstider"}


def town(result):
    for c in result.get("checks", []):
        if c["id"] == "C02" and c["status"] == "ok":
            m = TOWN.search(str(c["evidence"]))
            if m:
                words = [w for w in m.group(2).split() if w not in NOT_TOWN]
                return f"{m.group(1)} {' '.join(words)}" if words else ""
    return ""


def tidy_info(i):
    """Drop a description that only repeats the name, and repeated example products."""
    i = dict(i)
    if i.get("om", "").strip().lower() in ("", i.get("navn", "").strip().lower()) or len(i.get("om", "")) < 25:
        i["om"] = ""
    if i.get("saelger", "").startswith("fx "):
        seen = []
        for x in i["saelger"][3:].split(", "):
            if x not in seen:
                seen.append(x)
        i["saelger"] = "fx " + ", ".join(seen)
    return i


def info(domain, batch_dir):
    f = Fetcher(domain, min_interval=1.0, max_requests=4)
    out = {"navn": "", "om": "", "saelger": "", "varer": 0, "by": ""}
    st, _, _, html = f.get("/")
    if st == 200 and html:
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        name = meta(html, "og:site_name") or (unescape(title.group(1)) if title else "")
        out["navn"] = short(re.split(r"\s[|–—-]\s", name.strip())[0], 60)
        out["om"] = short(meta(html, "description", "og:description"), 160)
    st, _, _, body = f.get("/products.json?limit=250")
    if st == 200 and body:
        try:
            prods = json.loads(body).get("products", [])
        except ValueError:
            prods = []
        out["varer"] = len(prods)
        types = Counter(p.get("product_type", "").strip() for p in prods if p.get("product_type", "").strip())
        if types:
            out["saelger"] = ", ".join(t for t, _ in types.most_common(3))
        elif prods:
            out["saelger"] = "fx " + ", ".join(short(p["title"], 30) for p in prods[:3])
    try:
        out["by"] = town(json.load(open(os.path.join(batch_dir, domain + ".json"), encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return tidy_info(out)


if __name__ == "__main__":
    seed_dir, batch_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    done = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else {}
    for d in json.load(open(os.path.join(seed_dir, "_index.json"))):
        if d in done:
            continue
        try:
            done[d] = info(d, batch_dir)
        except Exception as e:  # keep going; the dashboard simply shows less info
            done[d] = {"fejl": str(e)[:100]}
        json.dump(done, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(d, done[d], flush=True)
