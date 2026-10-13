"""Lead collection for the 7-day test (public data only).

Step 1 (cc):     sample pages of the Common Crawl URL index for *.dk and keep domains that have Shopify-style
                 /collections/ or /products/ URLs.  Common Crawl data is published for reuse; requests are sequential
                 with backoff, to be gentle with the shared index server.
Step 2 (detect): fetch each candidate's homepage once (polite, robots.txt respected via gmcdoktor.fetch) and keep
                 reachable Shopify stores that are not password-protected.

Usage:
  python tools/collect_leads.py cc --pages 40 --out data/cc_domains.txt
  python tools/collect_leads.py detect --inp data/cc_domains.txt --out data/shopify_dk.txt
"""
import argparse
import json
import os
import random
import ssl
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gmcdoktor.fetch import Fetcher  # noqa: E402

INDEX = "https://index.commoncrawl.org/CC-MAIN-2026-39-index"
UA = {"User-Agent": "GMC-Doktor lead research (Common Crawl index, sequential requests)"}
CTX = ssl.create_default_context()
SKIP = ("shopify", "myshopify", "facebook", "google", "instagram", "pinterest", "youtube", "wordpress")


def cc(pages, out, seed=15):
    rng = random.Random(seed)
    sample = sorted(rng.sample(range(920), pages))
    seen = set()
    if os.path.exists(out):
        seen = {l.strip() for l in open(out, encoding="utf-8") if l.strip()}
    for i, p in enumerate(sample, 1):
        q = urllib.parse.urlencode({"url": "*.dk", "output": "json", "fl": "url", "page": str(p)})
        lines = None
        for attempt in range(4):
            try:
                r = urllib.request.urlopen(urllib.request.Request(f"{INDEX}?{q}", headers=UA), timeout=240, context=CTX)
                lines = r.read().decode("utf-8", "ignore").splitlines()
                break
            except Exception as e:
                print(f"page {p} attempt {attempt + 1}: {e}", flush=True)
                time.sleep(20 * (attempt + 1))
        if lines is None:
            continue
        new = 0
        for l in lines:
            try:
                u = json.loads(l)["url"]
            except Exception:
                continue
            sp = urllib.parse.urlsplit(u)
            d = sp.netloc.lower().split(":")[0]
            d = d[4:] if d.startswith("www.") else d
            if not d.endswith(".dk") or any(s in d for s in SKIP) or d in seen:
                continue
            seen.add(d)
            new += 1
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(d + "\n")
        print(f"[{i}/{len(sample)}] page {p}: {len(lines)} urls, +{new} domains (total {len(seen)})", flush=True)
        time.sleep(3)


def dns(inp, out, workers=24):
    """Keep domains whose A record is Shopify's storefront range 23.227.38.0/24 (public DNS lookups only)."""
    import socket
    from concurrent.futures import ThreadPoolExecutor
    socket.setdefaulttimeout(5)
    doms = sorted({l.strip() for l in open(inp, encoding="utf-8") if l.strip()})
    done = set()
    if os.path.exists(out):
        done = {l.split("\t")[0] for l in open(out, encoding="utf-8") if l.strip()}
    todo = [d for d in doms if d not in done]

    def res(d):
        for host in (d, "www." + d):
            try:
                ips = socket.gethostbyname_ex(host)[2]
            except Exception:
                continue
            if any(ip.startswith("23.227.38.") for ip in ips):
                return d, True, ips[0]
        return d, False, ""

    n_shop = 0
    with ThreadPoolExecutor(workers) as ex, open(out, "a", encoding="utf-8") as fh:
        for i, (d, ok, ip) in enumerate(ex.map(res, todo), 1):
            fh.write(f"{d}\t{'shopify' if ok else 'no'}\t{ip}\n")
            n_shop += ok
            if i % 500 == 0:
                print(f"[{i}/{len(todo)}] shopify so far: {n_shop}", flush=True)
    print(f"done: {len(todo)} resolved, {n_shop} on Shopify IPs", flush=True)


def detect(inp, out):
    done = set()
    if os.path.exists(out):
        done = {l.split("\t")[0] for l in open(out, encoding="utf-8") if l.strip()}
    doms = [l.strip() for l in open(inp, encoding="utf-8") if l.strip()]
    for i, d in enumerate(doms, 1):
        if d in done:
            continue
        try:
            f = Fetcher(d, min_interval=0.5, max_requests=3, timeout=15)
            st, final, hdr, home = f.get("/")
        except Exception as e:
            st, final, hdr, home = None, "", {}, str(e)
        hl = {k.lower(): v for k, v in (hdr or {}).items()}
        shop = bool(hl.get("x-shopid") or "cdn.shopify.com" in (home or "") or "/cdn/shop/" in (home or "") or "Shopify.theme" in (home or ""))
        pw = "/password" in (final or "")
        verdict = "shopify" if (st == 200 and shop and not pw) else ("password" if pw else ("other" if st == 200 else f"down:{st}"))
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"{d}\t{verdict}\t{final}\n")
        if i % 25 == 0:
            print(f"[{i}/{len(doms)}] {d}: {verdict}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("cc")
    a.add_argument("--pages", type=int, default=40)
    a.add_argument("--out", default="data/cc_domains.txt")
    a.add_argument("--seed", type=int, default=15)
    c = sub.add_parser("dns")
    c.add_argument("--inp", default="data/cc_domains.txt")
    c.add_argument("--out", default="data/dns_shopify.txt")
    b = sub.add_parser("detect")
    b.add_argument("--inp", default="data/shopify_candidates.txt")
    b.add_argument("--out", default="data/shopify_dk.txt")
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if args.cmd == "cc":
        cc(args.pages, args.out, args.seed)
    elif args.cmd == "dns":
        dns(args.inp, args.out)
    else:
        detect(args.inp, args.out)
