"""Director order 74 P2: a reproducible snapshot of the research register, frozen before any new result is assessed.

Reads research/data/factory/registry.json (tracked, aggregate register) and writes nothing unless --out is given. The
same register and the same rules give byte-identical output: there is no timestamp in the snapshot. It adds no ledger
row and changes no hash chain. DSR and PBO stay MISSING_INPUT: the register holds no return series.

The max-z figures are diagnostics, not significance limits. 19,438 is the conservative historical reference and is not
a documented effective number of independent tests.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(HERE, "research", "tools"))
import register_stats as rs  # noqa: E402

REGISTER = os.path.join(HERE, "research", "data", "factory", "registry.json")
SCHEMA = "copybot.register_snapshot/1"
MISSING = "MISSING_INPUT"
RULES = {
    "version": 1,
    "universe": "every entry of ledger.entries in the register file; nothing is added, merged or left out",
    "attempt": "one ledger entry",
    "variant": "the integer ledger entry field 'variants'; an entry without trials counts as recorded by the factory",
    "lineage": "the ledger entry field 'lineage', exactly as recorded",
    "reference_n": "the total variant count is the conservative historical reference, not a documented N_eff",
    "n_eff": "MISSING_INPUT until return series and a validated correlation method exist",
    "forbidden": ["choosing a lower N because it gives a lower bar", "reconstructing return series without documentation",
                  "using 43 lineages as the only limit"],
}


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entry_key(e):
    return {"seq": e["seq"], "hid": e["hid"], "lineage": e["lineage"], "variants": e["variants"], "hash": e["hash"]}


def build(raw):
    """raw: the bytes of the register file."""
    reg = json.loads(raw.decode("utf-8"))
    ledger = reg["ledger"]
    entries = ledger["entries"]
    seqs = [e["seq"] for e in entries]
    if seqs != list(range(len(entries))):
        raise ValueError("ledger sequence has holes or is out of order")
    for i, e in enumerate(entries):
        if not isinstance(e["variants"], int) or e["variants"] < 1:
            raise ValueError(f"entry {i}: variants must be a positive integer")
        if not e.get("lineage"):
            raise ValueError(f"entry {i}: lineage missing")
    by = {}
    for e in entries:
        t = by.setdefault(e["lineage"], {"attempts": 0, "variants": 0, "hypotheses": set()})
        t["attempts"] += 1
        t["variants"] += e["variants"]
        t["hypotheses"].add(e["hid"])
    lineage_map = {k: {"attempts": v["attempts"], "variants": v["variants"], "hypotheses": sorted(v["hypotheses"])}
                   for k, v in sorted(by.items())}
    counts = {"attempts": len(entries), "variants": sum(e["variants"] for e in entries), "lineages": len(by),
              "hypotheses": len({e["hid"] for e in entries})}
    claimed = {"attempts": ledger["attempts"], "variants": ledger["variants"], "lineages": len(ledger["lineages"])}
    mismatch = {k: (claimed[k], counts[k]) for k in claimed if claimed[k] != counts[k]}
    if mismatch:
        raise ValueError(f"register totals do not match its entries: {mismatch}")
    table = rs.n_table({"lineages": counts["lineages"], "attempts": counts["attempts"], "variants": counts["variants"]})
    return {"schema": SCHEMA, "rules": RULES, "source": {"path": "research/data/factory/registry.json",
                                                         "sha256": hashlib.sha256(raw).hexdigest()},
            "counts": counts, "alpha_gross": ledger["alpha_gross"], "lineage_map": lineage_map,
            "entries_sha256": hashlib.sha256(canonical([_entry_key(e) for e in entries]).encode()).hexdigest(),
            "n": {"conservative_reference": counts["variants"], "n_eff": MISSING,
                  "diagnostic_expected_max_z": {k: round(v["expected_max_z"], 4) for k, v in sorted(table.items())}},
            "dsr": MISSING, "pbo": MISSING}


def render(snap):
    return json.dumps(snap, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--register", default=REGISTER)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    with open(args.register, "rb") as f:
        text = render(build(f.read()))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(hashlib.sha256(text.encode()).hexdigest())


if __name__ == "__main__":
    main()
