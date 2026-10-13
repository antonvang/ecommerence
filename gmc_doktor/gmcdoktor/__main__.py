"""CLI: python -m gmcdoktor check <domain> [--out DIR]  |  python -m gmcdoktor batch <domains.txt> [--out DIR]"""
import argparse
import csv
import json
import os
import sys

from . import checks, report


def _save(res, out):
    os.makedirs(out, exist_ok=True)
    base = os.path.join(out, res["domain"].replace(":", "_"))
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    with open(base + ".html", "w", encoding="utf-8") as fh:
        fh.write(report.render(res))
    return base + ".html"


def _summary(res):
    if not res.get("reachable"):
        return f"{res['domain']}: kunne ikke hentes ({' '.join(res.get('notes', []))})"
    top = [c["title"] for c in res["checks"] if c["status"] == "fejl"][:3]
    return (f"{res['domain']}: score {res['score']} · fejl {res['n_fail']} (kritiske {res['counts'].get('kritisk', 0)}, "
            f"høje {res['counts'].get('høj', 0)}) · advarsler {res['n_warn']} · shopify={res['shopify']} · top: {'; '.join(top)}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gmcdoktor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("check")
    a.add_argument("domain")
    a.add_argument("--out", default="reports")
    b = sub.add_parser("batch")
    b.add_argument("file")
    b.add_argument("--out", default="data/batch")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        res = checks.run(args.domain)
        path = _save(res, args.out)
        print(_summary(res))
        print("rapport:", path)
        return 0
    domains = [l.strip() for l in open(args.file, encoding="utf-8") if l.strip() and not l.startswith("#")]
    rows = []
    for i, d in enumerate(domains, 1):
        prev = os.path.join(args.out, d.replace(":", "_") + ".json")
        res = None
        if os.path.exists(prev):  # resume: reuse a finished result
            try:
                res = json.load(open(prev, encoding="utf-8"))
                if res.get("checker_version") != checks.VERSION:
                    res = None  # stale result from an older checker version
            except Exception:
                res = None
        if res is None:
            try:
                res = checks.run(d)
            except Exception as e:  # keep the batch going
                res = {"domain": d, "reachable": False, "notes": [f"fejl i tjek: {e}"], "checks": [], "checked_at": ""}
            _save(res, args.out)
        print(f"[{i}/{len(domains)}] {_summary(res)}", flush=True)
        ct = res.get("contact", {}) or {}
        cnt = res.get("counts", {}) or {}
        rows.append({"domain": res["domain"], "reachable": res.get("reachable"), "shopify": res.get("shopify"),
                     "password": res.get("password"), "score": res.get("score"), "kritiske": cnt.get("kritisk", 0),
                     "hoeje": cnt.get("høj", 0), "fejl_i_alt": res.get("n_fail"), "advarsler": res.get("n_warn"),
                     "top_fejl": " | ".join(c["title"] for c in res.get("checks", []) if c["status"] == "fejl")[:300],
                     "telefon": ct.get("phone"), "email": ct.get("email"), "cvr": ct.get("cvr"),
                     "n_produkter": res.get("n_products_sampled")})
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "leads.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["domain"])
        w.writeheader()
        w.writerows(rows)
    print("leads:", os.path.join(args.out, "leads.csv"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
