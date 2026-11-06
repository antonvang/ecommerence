"""One realistic change per isolated copy of the checksum-verified evaluator."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[1] / "crosscheck" / "claude_eval_v111.py"

HOLM = '''
def _mutation_holm(ps, alpha, mode="normal", size=None):
    order = sorted(range(len(ps)), key=lambda i: (ps[i], i))
    m = len(ps) if size is None else size
    rejected = [False] * len(ps)
    for k, i in enumerate(order):
        threshold = alpha / (m - k)
        yes = ps[i] < threshold if mode == "strict" else ps[i] <= threshold
        if yes:
            rejected[i] = True
        elif mode != "nostop":
            break
    return rejected

def _mutation_family_holm(tested, out, hyps, alpha):
    families = {h["hid"]: h["family"] for h in hyps}
    result = [False] * len(tested)
    for family in sorted(set(families.values())):
        indices = [i for i, hid in enumerate(tested) if families[hid] == family]
        flags = _mutation_holm([out[tested[i]]["p_one"] for i in indices], alpha)
        for i, flag in zip(indices, flags):
            result[i] = flag
    return result
'''


def definitions():
    mutants = []
    def add(number, description, category, critical, old, new, *, silent=False,
            equivalent=False, reason="", extra="", edits=()):
        mutants.append(dict(id=f"M{number:02d}", description=description,
            category=category, classification="SIKKERHEDSKRITISK" if critical else "ØVRIG",
            equivalent=equivalent, equivalence_reason=reason, planned_silent=silent,
            edits=[(old, new), *edits], extra=extra))

    add(1, "Reject signal available exactly at t", "lookahead/time", False,
        'elif sig["avail_ts"] > t:', 'elif sig["avail_ts"] >= t:')
    add(2, "Permit one cadence of future signal availability", "lookahead/time", True,
        'elif sig["avail_ts"] > t:', 'elif sig["avail_ts"] > t + cad:')
    add(3, "Exclude embargo equality bar", "lookahead/time", False,
        't >= start + emb', 't > start + emb',
        edits=[('if t < start + emb:', 'if t <= start + emb:')])
    add(4, "Ignore configured embargo", "lookahead/time", True,
        'emb = fx["window"].get("embargo_s", 0)', 'emb = 0')
    add(5, "Anchor grid to Unix zero instead of window start", "lookahead/time", True,
        'gset = set(grid)', 'gset = {t for t in grid if t % cad == 0}')
    add(6, "Include exclusive end in time grid", "lookahead/time", True,
        'grid = list(range(start, end, cad))', 'grid = list(range(start, end + 1, cad))')
    add(7, "Exclude listing equality bar", "membership", False,
        'm["listed_from"] <= t', 'm["listed_from"] < t')
    add(8, "Retain previous positions through gap and MISSING", "position/cost", True,
        '            prev = cur', '            prev.update(cur)', silent=True)
    add(9, "Reverse funding sign", "position/cost", True,
        'f = w * fr', 'f = -w * fr', silent=True)
    add(10, "Charge absolute position rather than turnover", "position/cost", True,
        'abs(w - prev.get(a, 0.0))', 'abs(w)', silent=True)
    add(11, "Undercharge costs by tenfold unit conversion", "position/cost", True,
        'h["cost_bps"] / 10_000', 'h["cost_bps"] / 100_000', silent=True)
    add(12, "Lose funding position sign", "position/cost", True,
        'f = w * fr', 'f = abs(w) * fr', silent=True)
    add(13, "Report mean cost instead of summed cost", "reporting", False,
        '"total_cost": math.fsum(costs)', '"total_cost": math.fsum(costs) / max(1, T)', silent=True)
    add(14, "Include missing assets in portfolio denominator", "missing/numerics", True,
        'math.fsum(nets) / len(nets)', 'math.fsum(nets) / max(1, len(fx["universe"]))', silent=True)
    add(15, "Impute MISSING returns with zero", "missing/numerics", True,
        'r = num(o["ret"])', 'r = num(o["ret"])\n                r = 0.0 if r is None else r')
    add(16, "Let infinity through finite-number helper", "missing/numerics", True,
        'if not is_num(v) or not math.isfinite(v):', 'if not is_num(v) or math.isnan(v):')
    add(17, "Do not count missing funding at flat position", "reporting", False,
        'c["n_funding_missing"] += 1', 'c["n_funding_missing"] += int(w != 0)', silent=True)
    add(18, "Reject returns/funding exactly at permitted size", "validation/numerics", False,
        'abs(o[k]) > lim', 'abs(o[k]) >= lim')
    add(19, "Relax return size bound tenfold", "validation/numerics", True,
        'MAX_RET, MAX_FUNDING, MAX_VALUE, MAX_COST_BPS = 1e6, 1e6, 1e12, 1e6',
        'MAX_RET, MAX_FUNDING, MAX_VALUE, MAX_COST_BPS = 1e7, 1e6, 1e12, 1e6')
    add(20, "Silently accept undeclared fee component", "validation/protocol", True,
        'fields(h, p, hreq, set(hreq))', 'fields(h, p, hreq, set(hreq) | {"fee_bps"})')
    add(21, "Apply DUPLICATE only to statistically tested rows", "multiple testing", False,
        'if fp in seen_fp:', 'if fp in seen_fp and res["status"] == "TESTED":')
    add(22, "Include cost in fingerprint and test duplicate idea again", "multiple testing", True,
        'fp = (h["family"], h["signal_key"], h["rule"])',
        'fp = (h["family"], h["signal_key"], h["rule"], h["cost_bps"])')
    add(23, "Count excluded duplicates in Holm denominator", "multiple testing", False,
        'he.holm(ps, fx["alpha"])', '_mutation_holm(ps, fx["alpha"], size=len(out))', extra=HOLM)
    add(24, "Use strict inequality in Holm", "multiple testing", False,
        'he.holm(ps, fx["alpha"])', '_mutation_holm(ps, fx["alpha"], mode="strict")', extra=HOLM)
    add(25, "Continue Holm after its first non-rejection", "multiple testing", True,
        'he.holm(ps, fx["alpha"])', '_mutation_holm(ps, fx["alpha"], mode="nostop")', extra=HOLM)
    add(26, "Restart Holm independently per family", "multiple testing", True,
        'he.holm(ps, fx["alpha"])', '_mutation_family_holm(tested, out, fx["hypotheses"], fx["alpha"])', extra=HOLM)
    add(27, "Use alpha instead of q_fdr for diagnostic BH", "multiple testing", False,
        'he.bh(ps, fx["q_fdr"])', 'he.bh(ps, fx["alpha"])', silent=True)
    add(28, "Accidentally use doubled normal tail", "statistics", False,
        'p_one=he.p_one(tstat)', 'p_one=2 * he.p_one(tstat)', silent=True)
    add(29, "Drop HAC serial covariance by forcing lag zero", "statistics", True,
        'L = nw_lag(T)', 'L = 0', silent=True)
    add(30, "Allow T29 into the test set", "statistics", True,
        'if T >= 30:', 'if T >= 29:')
    add(31, "Charge accepted alpha again on idempotent hit", "ledger/replay", True,
        '                hits += 1', '                hits += 1\n                totals[q["family"]]["alphas"].append(a)', silent=True)
    old = '''        if q["key"] in accepted:
            if canonical(accepted[q["key"]]) == canonical([q["hid"], q["family"], v, a]):
                hits += 1
            else:
                errors.append({"key": q["key"], "reason": "key_conflict"})
            continue'''
    new = '''        if q["key"] in accepted:
            if canonical(accepted[q["key"]]) == canonical([q["hid"], q["family"], v, a]):
                hits += 1
                continue
            # retry with changed payload is incorrectly allowed to append'''
    add(32, "Accept and charge a changed-key payload", "ledger/replay", True, old, new)
    add(33, "Reserve rejected key before variants validation", "ledger/replay", True,
        'errors.append({"key": q["key"], "reason": "variants"})',
        'errors.append({"key": q["key"], "reason": "variants"})\n            accepted[q["key"]] = [q["hid"], q["family"], v, a]')
    add(34, "Compare replay by Python value rather than canonical types", "ledger/replay", True,
        'canonical(accepted[q["key"]]) == canonical([q["hid"], q["family"], v, a])',
        'accepted[q["key"]] == [q["hid"], q["family"], v, a]')
    add(35, "Omit timestamp from ledger hash preimage", "ledger/hash", False,
        'prev = sha(e)', 'prev = sha({k: v for k, v in e.items() if k != "ts"})', silent=True)
    add(36, "Skip data/protocol lock when any other error exists", "lock/protocol", True,
        'if "lock" in fx:', 'if "lock" in fx and not errs:')
    add(37, "Hash universe in place of observation data", "lock/protocol", True,
        '("data_sha256", fx.get("observations"))', '("data_sha256", fx.get("universe"))')
    add(38, "Omit alpha from protocol identity", "lock/protocol", True,
        'proto = {k: fx.get(k) for k in ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")}',
        'proto = {k: fx.get(k) for k in ("cadence_s", "window", "universe", "hypotheses", "q_fdr")}')
    add(39, "Ignore unknown lock fields", "lock/protocol", True,
        'if k not in ("protocol_sha256", "data_sha256"):',
        'if False and k not in ("protocol_sha256", "data_sha256"):')
    add(40, "Disable digest mismatch rejection", "lock/protocol", True,
        'if k not in lk or not isinstance(lk[k], str) or lk[k] != h(obj):',
        'if False and (k not in lk or not isinstance(lk[k], str) or lk[k] != h(obj)):')
    old_writer = '''    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)'''
    add(41, "Overwrite final file directly without atomic replacement", "restart/write", False,
        old_writer, '    with open(path, "w", encoding="utf-8") as f:\n        f.write(text)', silent=True)
    add(42, "Append new serialized result to previous result", "restart/write", False,
        '    os.replace(tmp, path)',
        '    with open(path, "a", encoding="utf-8") as out, open(tmp, encoding="utf-8") as src:\n        out.write(src.read())\n    os.unlink(tmp)')
    add(43, "Equivalent signed extreme predicate", "equivalent", False,
        'if abs(r) > 0.5:', 'if r > 0.5 or r < -0.5:', equivalent=True,
        reason="r is finite after num(); abs(r)>0.5 iff r>0.5 or r<-0.5, including signed zero")
    add(44, "Equivalent integer sample-size predicate", "equivalent", False,
        'if T >= 30:', 'if T > 29:', equivalent=True,
        reason="T=len(xs) is an integer; T>=30 iff T>29")
    add(45, "Count exact half-unit returns as extreme", "reporting", False,
        'if abs(r) > 0.5:', 'if abs(r) >= 0.5:', silent=True)
    return mutants


def main():
    lock = json.loads((SOURCE.parent / "EVALUATOR_V1_1_1.lock").read_text())
    source = SOURCE.read_bytes()
    assert hashlib.sha256(source).hexdigest() == lock["sha256"]
    target = ROOT / "mutants"
    target.mkdir(exist_ok=True)
    manifest = []
    for definition in definitions():
        value = source.decode()
        for old, new in definition["edits"]:
            if value.count(old) != 1:
                raise ValueError(f"{definition['id']}: expected one mutation site: {old}")
            value = value.replace(old, new, 1)
        if definition["extra"]:
            value = value.replace('if __name__ == "__main__":', definition["extra"] + '\nif __name__ == "__main__":')
        compile(value, definition["id"] + ".py", "exec")
        path = target / (definition["id"] + ".py")
        raw = value.encode()
        path.write_bytes(raw)
        manifest.append({**definition, "file": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
    (ROOT / "mutant_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
