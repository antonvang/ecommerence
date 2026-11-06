"""Compare two EVALUATOR_SPEC v1 output directories field by field (spec section 9 tolerances).

    python3 research/desk/crosscheck/compare.py DIR_A DIR_B [--json OUT]
"""
from __future__ import annotations

import argparse
import glob
import json
import os

TOL = 1e-9


def close(a, b):
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def walk(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append({"path": f"{path}.{k}", "a": a.get(k, "<missing>"), "b": b.get(k, "<missing>")})
            else:
                walk(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append({"path": path, "a": a, "b": b})
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]", out)
    elif not close(a, b):
        out.append({"path": path, "a": a, "b": b})


def compare(dir_a, dir_b):
    res = {}
    names = sorted({os.path.basename(p) for p in glob.glob(os.path.join(dir_a, "*.json"))} |
                   {os.path.basename(p) for p in glob.glob(os.path.join(dir_b, "*.json"))})
    for n in names:
        pa, pb = os.path.join(dir_a, n), os.path.join(dir_b, n)
        if not (os.path.exists(pa) and os.path.exists(pb)):
            res[n] = [{"path": "<file>", "a": os.path.exists(pa), "b": os.path.exists(pb)}]
            continue
        with open(pa, encoding="utf-8") as fa, open(pb, encoding="utf-8") as fb:
            diffs = []
            walk(json.load(fa), json.load(fb), "", diffs)
        res[n] = diffs
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    res = compare(a.a, a.b)
    for n, d in res.items():
        print(f"{n}: {len(d)} afvigelser")
        for x in d[:40]:
            print("   ", x["path"], x["a"], "|", x["b"])
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
