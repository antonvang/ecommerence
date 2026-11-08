"""Director order 58 P1: a LOCAL, OFFLINE video-claim triage tool (video -> claim -> rule -> triage).

The tool never watches a video and never fetches anything. A human (or Claude) looks at frames and fills a claim
record; the tool validates the record, classifies it with fixed rules, computes two diagnostics and writes a register.
Spec by example: research/desk/VIDEO_TRIAGE_2026-11-08.md, VIDEO_USABLE_2026-11-09.md (U3, U6),
research/desk/orb15/ORB15_VIDEO_RULE_AUDIT.md and research/desk/fomo/FOMO_COPY_30S_PROTOCOL_DRAFT.md section 1.
Danish description: research/desk/VIDEO_TRIAGE_TOOL_REPORT.md.

    python3 research/tools/video_triage.py extract --video PATH --out DIR [--every-s 3] [--width 360]
    python3 research/tools/video_triage.py new --id ID --source "handle/description" --video-sha256 HEX
    python3 research/tools/video_triage.py check --claim FILE [--fill-prior]
    python3 research/tools/video_triage.py report --dir research/data/video_claims --out FILE.md

Claim record (schema "copybot.video_claim/1", one JSON file per video, every key required, no extra keys):
- id, source ("@handle / description"), video_sha256 (64 hex, or "UNKNOWN" when the file is not in the repo);
- provenance: {method, refs[]}: how the facts were read (frames every N s, or SEED_FROM_TRIAGE_NOTES);
- claims: {performance_claimed, trading_rule_claimed} (booleans; a rule "claimed" means a specific rule or system is
  presented as the source of trades, not just "I have rules");
- observed_facts[]: {at, quote, fact}; `at` is seconds (number), a frame file name ("f012.png") or "UNKNOWN"; `quote`
  is the on-screen text, at most 15 words; `fact` is what it shows. Facts only; inferences go below;
- assumptions[]: {label: ASSUMPTION | UNKNOWN, text};
- rule_checklist: {element: {status: OBSERVED | PARTIAL | UNKNOWN, note}} for the 13 CHECKLIST elements. OBSERVED means
  the rule for that element is fully known from the video; an explicitly stated "none" (e.g. "no time exit") is
  OBSERVED, a silent video is UNKNOWN;
- performance: {numbers[] (as shown, strings), trades_shown (int|null), account: SIM|DEMO|REAL|BACKTEST|UNKNOWN};
- selection: {trades_total, strategies_tried_n, backtest_years_t, stated_sharpe (each number|null), note};
- red_flags: {free[], standard{STANDARD_FLAGS: true|false|null}, notional_check (null or {instrument, positions, lots,
  contract_size, price, balance, source})};
- lab_prior: {lineages[], mechanism_tags[], matches[]}: matches are factory-register record ids whose lineage or
  mechanism_tag is in the query (registry read-only; listed, not judged). `check --fill-prior` writes them;
- classification: one of CLASSES, or PENDING for a fresh skeleton.

Classification (deterministic, first rule that applies):
1. NO_TRADING_CLAIM if neither a performance nor a trading rule is claimed;
2. REPLICABLE if every checklist element except costs is OBSERVED;
3. NOT_REPLICABLE_FROM_VIDEO if any of entry_signal, stop, target, time_exit is UNKNOWN or PARTIAL;
4. otherwise PARTIAL.

Luck bar (DIAGNOSTIC_ONLY, not a statistical test): Bailey & Lopez de Prado's expected maximum of N iid null Sharpe
estimates, E[max] ~ sd * ((1 - g) * Phi^-1(1 - 1/N) + g * Phi^-1(1 - 1/(N e))), g = Euler-Mascheroni, sd = 1/sqrt(T)
for an annualised Sharpe over T years. Assumes iid trials, normal returns, no autocorrelation; skew and kurtosis are
not modelled.

Purity: stdlib only. PyGObject/GStreamer is imported lazily inside extract() and nowhere else. No network, no sqlite,
no lab imports. extract() refuses anything that looks like a URL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLAIMS_DIR = os.path.join(HERE, "research", "data", "video_claims")
REGISTRY = os.path.join(HERE, "research", "data", "factory", "registry.json")

SCHEMA = "copybot.video_claim/1"
MANIFEST_SCHEMA = "copybot.video_frames/1"
STATUSES = ("OBSERVED", "PARTIAL", "UNKNOWN")
CHECKLIST = ("market", "instrument", "calendar_timezone", "entry_signal", "entry_execution", "stop", "target",
             "time_exit", "short_rule", "max_signals_per_session", "position_size", "costs", "data_source")
CORE = ("entry_signal", "stop", "target", "time_exit")          # any one not OBSERVED -> NOT_REPLICABLE_FROM_VIDEO
CLASSES = ("REPLICABLE", "NOT_REPLICABLE_FROM_VIDEO", "NO_TRADING_CLAIM", "PARTIAL")
ACCOUNTS = ("SIM", "DEMO", "REAL", "BACKTEST", "UNKNOWN")
LABELS = ("ASSUMPTION", "UNKNOWN")
STANDARD_FLAGS = ("lead_generation", "selected_examples_only", "backtest_only", "paid_product_or_fee",
                  "sim_or_demo_account", "forbidden_resource_needed")
MAX_QUOTE_WORDS = 15
MAX_LEVERAGE = 1000.0                 # notional / balance above this is flagged as impossible on a normal account
EULER_GAMMA = 0.5772156649
LUCK_ASSUMPTIONS = ("iid trials", "normal returns", "no autocorrelation",
                    "skew and kurtosis not modelled", "sd = 1/sqrt(T years) for an annualised Sharpe")

TOP_KEYS = ("schema", "id", "source", "video_sha256", "provenance", "claims", "observed_facts", "assumptions",
            "rule_checklist", "performance", "selection", "red_flags", "lab_prior", "classification")
SUB_KEYS = {
    "provenance": ("method", "refs"),
    "claims": ("performance_claimed", "trading_rule_claimed"),
    "performance": ("numbers", "trades_shown", "account"),
    "selection": ("trades_total", "strategies_tried_n", "backtest_years_t", "stated_sharpe", "note"),
    "red_flags": ("free", "standard", "notional_check"),
    "lab_prior": ("lineages", "mechanism_tags", "matches"),
}
NOTIONAL_KEYS = ("instrument", "positions", "lots", "contract_size", "price", "balance", "source")
ID_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,31}$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
FRAME_RE = re.compile(r"^f\d{3,}\.png$")
URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")


# ---------------------------------------------------------------- diagnostics

def luck_bar(n, t_years):
    """Expected maximum annualised Sharpe of n iid null strategies over t_years (Bailey & Lopez de Prado).
    n = 1 gives 0.0 (the expected value of a single null estimate)."""
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f"N must be an integer >= 1, got {n!r}")
    if isinstance(t_years, bool) or not isinstance(t_years, (int, float)) or not t_years > 0:
        raise ValueError(f"T must be a positive number of years, got {t_years!r}")
    if n == 1:
        return 0.0
    inv = statistics.NormalDist().inv_cdf
    sd = 1.0 / math.sqrt(t_years)
    return sd * ((1 - EULER_GAMMA) * inv(1 - 1.0 / n) + EULER_GAMMA * inv(1 - 1.0 / (n * math.e)))


def luck_diagnostic(selection):
    """DIAGNOSTIC_ONLY: the luck bar and stated SR minus the bar. Never a pass/fail."""
    n, t, sr = selection.get("strategies_tried_n"), selection.get("backtest_years_t"), selection.get("stated_sharpe")
    out = {"status": "DIAGNOSTIC_ONLY", "N": n, "T_years": t, "stated_sr": sr, "luck_bar": None,
           "sr_minus_luck_bar": None, "assumptions": list(LUCK_ASSUMPTIONS),
           "note": "diagnostic, not a statistical test"}
    if n is None or t is None:
        out["note"] += "; N or T UNKNOWN, no bar"
        return out
    bar = luck_bar(int(n), float(t))
    out["luck_bar"] = round(bar, 4)
    if sr is not None:
        out["sr_minus_luck_bar"] = round(float(sr) - bar, 4)
    return out


def notional_check(positions, lots, contract_size, price, balance, max_leverage=MAX_LEVERAGE):
    """Notional of `positions` x `lots` x `contract_size` units at `price`, and leverage against `balance`.
    flag = leverage > max_leverage (not possible on a normal retail account; looks like demo or an edited screen)."""
    for k, v in (("positions", positions), ("lots", lots), ("contract_size", contract_size), ("price", price),
                 ("balance", balance)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not v > 0:
            raise ValueError(f"{k} must be a positive number, got {v!r}")
    units = positions * lots * contract_size
    notional = units * price
    lev = notional / balance
    return {"units": round(units, 6), "notional": round(notional, 2), "leverage": round(lev, 1),
            "max_leverage": max_leverage, "flag": lev > max_leverage}


# ---------------------------------------------------------------- registry (read-only)

def registry_matches(lineages, tags, path=REGISTRY):
    """Factory-register records whose lineage or mechanism_tag is queried. Opens the file read-only; lists, never
    judges. Returns (sorted ids, unknown query terms)."""
    lineages, tags = set(lineages or ()), set(tags or ())
    if not lineages and not tags:
        return [], []
    with open(path, "r", encoding="utf-8") as f:
        reg = json.load(f)
    recs = reg.get("records", [])
    seen_l = {r.get("lineage") for r in recs}
    seen_t = {r.get("mechanism_tag") for r in recs}
    ids = sorted(r["id"] for r in recs if r.get("lineage") in lineages or r.get("mechanism_tag") in tags)
    unknown = sorted([f"lineage:{x}" for x in lineages - seen_l] + [f"mechanism_tag:{x}" for x in tags - seen_t])
    return ids, unknown


# ---------------------------------------------------------------- schema

def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _keys(errors, obj, keys, where):
    if not isinstance(obj, dict):
        errors.append(f"{where} must be an object")
        return False
    for k in keys:
        if k not in obj:
            errors.append(f"missing field: {where}.{k}" if where else f"missing field: {k}")
    for k in sorted(set(obj) - set(keys)):
        errors.append(f"unknown field: {where}.{k}" if where else f"unknown field: {k}")
    return True


def validate(rec):
    """Return a list of error strings; empty means valid."""
    e = []
    if not _keys(e, rec, TOP_KEYS, ""):
        return e
    if rec.get("schema") != SCHEMA:
        e.append(f"schema must be {SCHEMA!r}, got {rec.get('schema')!r}")
    if not isinstance(rec.get("id"), str) or not ID_RE.match(rec.get("id") or ""):
        e.append(f"id must match {ID_RE.pattern}, got {rec.get('id')!r}")
    if not isinstance(rec.get("source"), str) or not rec.get("source", "").strip():
        e.append("source must be a non-empty string")
    v = rec.get("video_sha256")
    if not (v == "UNKNOWN" or (isinstance(v, str) and HEX_RE.match(v))):
        e.append(f"video_sha256 must be 64 lowercase hex or 'UNKNOWN', got {v!r}")
    for sec, keys in SUB_KEYS.items():
        if sec in rec:
            _keys(e, rec[sec], keys, sec)
    p = rec.get("provenance")
    if isinstance(p, dict):
        if not isinstance(p.get("method"), str) or not p.get("method"):
            e.append("provenance.method must be a non-empty string")
        if not isinstance(p.get("refs"), list) or not all(isinstance(x, str) for x in p.get("refs", [])):
            e.append("provenance.refs must be a list of strings")
    c = rec.get("claims")
    if isinstance(c, dict):
        for k in SUB_KEYS["claims"]:
            if k in c and not isinstance(c[k], bool):
                e.append(f"claims.{k} must be true or false")
    facts = rec.get("observed_facts")
    if not isinstance(facts, list):
        e.append("observed_facts must be a list")
    else:
        for i, f in enumerate(facts):
            w = f"observed_facts[{i}]"
            if not _keys(e, f, ("at", "quote", "fact"), w):
                continue
            at = f.get("at")
            if not ((_is_num(at) and at >= 0) or at == "UNKNOWN" or (isinstance(at, str) and FRAME_RE.match(at))):
                e.append(f"{w}.at must be seconds >= 0, a frame name like 'f012.png' or 'UNKNOWN', got {at!r}")
            q = f.get("quote")
            if not isinstance(q, str) or not q.strip():
                e.append(f"{w}.quote must be the non-empty on-screen text")
            elif len(q.split()) > MAX_QUOTE_WORDS:
                e.append(f"{w}.quote has {len(q.split())} words (max {MAX_QUOTE_WORDS})")
            if not isinstance(f.get("fact"), str) or not f.get("fact", "").strip():
                e.append(f"{w}.fact must be a non-empty string")
    asm = rec.get("assumptions")
    if not isinstance(asm, list):
        e.append("assumptions must be a list")
    else:
        for i, a in enumerate(asm):
            w = f"assumptions[{i}]"
            if not _keys(e, a, ("label", "text"), w):
                continue
            if a.get("label") not in LABELS:
                e.append(f"{w}.label must be ASSUMPTION or UNKNOWN, got {a.get('label')!r}")
            if not isinstance(a.get("text"), str) or not a.get("text", "").strip():
                e.append(f"{w}.text must be a non-empty string")
    rc = rec.get("rule_checklist")
    if "rule_checklist" in rec and _keys(e, rc, CHECKLIST, "rule_checklist"):
        for k in CHECKLIST:
            item = rc.get(k)
            if item is None:
                continue
            w = f"rule_checklist.{k}"
            if not _keys(e, item, ("status", "note"), w):
                continue
            if item.get("status") not in STATUSES:
                e.append(f"{w}.status must be one of {'/'.join(STATUSES)}, got {item.get('status')!r}")
            if not isinstance(item.get("note"), str):
                e.append(f"{w}.note must be a string")
    perf = rec.get("performance")
    if isinstance(perf, dict):
        if not isinstance(perf.get("numbers"), list) or not all(isinstance(x, str) for x in perf.get("numbers", [])):
            e.append("performance.numbers must be a list of strings (as shown)")
        ts = perf.get("trades_shown")
        if ts is not None and (not isinstance(ts, int) or isinstance(ts, bool) or ts < 0):
            e.append("performance.trades_shown must be a non-negative integer or null")
        if "account" in perf and perf.get("account") not in ACCOUNTS:
            e.append(f"performance.account must be one of {'/'.join(ACCOUNTS)}, got {perf.get('account')!r}")
    sel = rec.get("selection")
    if isinstance(sel, dict):
        for k in ("trades_total", "strategies_tried_n"):
            x = sel.get(k)
            if x is not None and (not isinstance(x, int) or isinstance(x, bool) or x < 1):
                e.append(f"selection.{k} must be a positive integer or null")
        x = sel.get("backtest_years_t")
        if x is not None and (not _is_num(x) or x <= 0):
            e.append("selection.backtest_years_t must be a positive number or null")
        x = sel.get("stated_sharpe")
        if x is not None and not _is_num(x):
            e.append("selection.stated_sharpe must be a number or null")
        if "note" in sel and not isinstance(sel.get("note"), str):
            e.append("selection.note must be a string")
        tt, ts = sel.get("trades_total"), (perf or {}).get("trades_shown") if isinstance(perf, dict) else None
        if isinstance(tt, int) and isinstance(ts, int) and ts > tt:
            e.append("performance.trades_shown exceeds selection.trades_total")
    rf = rec.get("red_flags")
    if isinstance(rf, dict):
        if not isinstance(rf.get("free"), list) or not all(isinstance(x, str) for x in rf.get("free", [])):
            e.append("red_flags.free must be a list of strings")
        if "standard" in rf and _keys(e, rf.get("standard"), STANDARD_FLAGS, "red_flags.standard"):
            for k in STANDARD_FLAGS:
                if k in rf["standard"] and rf["standard"][k] not in (True, False, None):
                    e.append(f"red_flags.standard.{k} must be true, false or null (UNKNOWN)")
        nc = rf.get("notional_check")
        if nc is not None and _keys(e, nc, NOTIONAL_KEYS, "red_flags.notional_check"):
            for k in ("positions", "lots", "contract_size", "price", "balance"):
                if k in nc and (not _is_num(nc[k]) or nc[k] <= 0):
                    e.append(f"red_flags.notional_check.{k} must be a positive number")
    lp = rec.get("lab_prior")
    if isinstance(lp, dict):
        for k in SUB_KEYS["lab_prior"]:
            if k in lp and (not isinstance(lp[k], list) or not all(isinstance(x, str) for x in lp[k])):
                e.append(f"lab_prior.{k} must be a list of strings")
    cl = rec.get("classification")
    if cl not in CLASSES + ("PENDING",):
        e.append(f"classification must be one of {'/'.join(CLASSES + ('PENDING',))}, got {cl!r}")
    return e


# ---------------------------------------------------------------- classification

def classify(rec):
    """(classification, reasons). Requires a record that passes validate()."""
    c, rc = rec["claims"], rec["rule_checklist"]
    if not c["performance_claimed"] and not c["trading_rule_claimed"]:
        return "NO_TRADING_CLAIM", ["no performance and no trading rule claimed"]
    not_obs = [k for k in CHECKLIST if k != "costs" and rc[k]["status"] != "OBSERVED"]
    if not not_obs:
        return "REPLICABLE", ["every checklist element except costs is OBSERVED"]
    core = [f"{k}={rc[k]['status']}" for k in CORE if rc[k]["status"] != "OBSERVED"]
    if core:
        return "NOT_REPLICABLE_FROM_VIDEO", [f"core element not observed: {x}" for x in core]
    return "PARTIAL", [f"not observed: {k}={rc[k]['status']}" for k in not_obs]


def computed_flags(rec):
    """Flags the tool derives itself (on top of the hand-set standard flags)."""
    out = {"costs_not_shown": rec["rule_checklist"]["costs"]["status"] != "OBSERVED"}
    nc = rec["red_flags"]["notional_check"]
    out["impossible_notional"] = None if nc is None else notional_check(
        nc["positions"], nc["lots"], nc["contract_size"], nc["price"], nc["balance"])["flag"]
    return out


def evaluate(rec, registry=REGISTRY):
    """Full check of one record: errors, warnings, classification, diagnostics, prior."""
    errors = validate(rec)
    out = {"id": rec.get("id") if isinstance(rec, dict) else None, "errors": errors, "warnings": []}
    if errors:
        out["classification"] = None
        return out
    cls, reasons = classify(rec)
    out.update({"classification": cls, "reasons": reasons, "stored": rec["classification"],
                "luck": luck_diagnostic(rec["selection"]), "computed_flags": computed_flags(rec)})
    nc = rec["red_flags"]["notional_check"]
    if nc is not None:
        out["notional"] = notional_check(nc["positions"], nc["lots"], nc["contract_size"], nc["price"], nc["balance"])
    if rec["classification"] == "PENDING":
        out["warnings"].append(f"classification PENDING; computed {cls}")
    elif rec["classification"] != cls:
        out["errors"].append(f"stored classification {rec['classification']} != computed {cls}")
    lp = rec["lab_prior"]
    ids, unknown = registry_matches(lp["lineages"], lp["mechanism_tags"], registry)
    out["prior_matches"] = ids
    if unknown:
        out["warnings"].append("lab_prior query terms not in the register: " + ", ".join(unknown))
    if sorted(lp["matches"]) != ids:
        out["warnings"].append("lab_prior.matches differ from the register now; run check --fill-prior")
    return out


# ---------------------------------------------------------------- records

def skeleton(cid, source, video_sha256):
    return {
        "schema": SCHEMA, "id": cid, "source": source, "video_sha256": video_sha256,
        "provenance": {"method": "frames", "refs": []},
        "claims": {"performance_claimed": False, "trading_rule_claimed": False},
        "observed_facts": [], "assumptions": [],
        "rule_checklist": {k: {"status": "UNKNOWN", "note": ""} for k in CHECKLIST},
        "performance": {"numbers": [], "trades_shown": None, "account": "UNKNOWN"},
        "selection": {"trades_total": None, "strategies_tried_n": None, "backtest_years_t": None,
                      "stated_sharpe": None, "note": ""},
        "red_flags": {"free": [], "standard": {k: None for k in STANDARD_FLAGS}, "notional_check": None},
        "lab_prior": {"lineages": [], "mechanism_tags": [], "matches": []},
        "classification": "PENDING",
    }


def dump(rec):
    return json.dumps(rec, ensure_ascii=False, indent=1) + "\n"


def new_claim(cid, source, video_sha256, claims_dir=CLAIMS_DIR):
    if not ID_RE.match(cid or ""):
        raise ValueError(f"id must match {ID_RE.pattern}")
    sha = (video_sha256 or "").lower()
    if not HEX_RE.match(sha):
        raise ValueError("--video-sha256 must be 64 hex characters")
    path = os.path.join(claims_dir, f"{cid}.json")
    if os.path.exists(path):
        raise FileExistsError(f"{path} exists; claims are never overwritten by `new`")
    os.makedirs(claims_dir, exist_ok=True)
    with open(path, "x", encoding="utf-8") as f:
        f.write(dump(skeleton(cid, source, sha)))
    return path


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _order(cid):
    m = re.match(r"^V(\d+)$", cid)
    return (0, int(m.group(1)), cid) if m else (1, 0, cid)


def _cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def report(claims_dir, registry=REGISTRY):
    """Markdown register of every *.json claim in claims_dir. Deterministic: no clock, sorted rows."""
    rows, bad = [], []
    for name in sorted(os.listdir(claims_dir)):
        if not name.endswith(".json"):
            continue
        p = os.path.join(claims_dir, name)
        try:
            rec = load(p)
        except (OSError, ValueError) as ex:
            bad.append((name, f"unreadable: {ex}"))
            continue
        ev = evaluate(rec, registry)
        if ev["errors"]:
            bad.append((name, "; ".join(ev["errors"])))
            continue
        rows.append((rec, ev))
    rows.sort(key=lambda x: _order(x[0]["id"]))
    lines = ["| ID | Kilde | Klassifikation | Kerne ikke OBSERVED | Performance vist | Handler vist/i alt | "
             "Konto | Held-bar (DIAGNOSTIC_ONLY) | Røde flag | Lab-prior |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    counts = {k: 0 for k in CLASSES}
    for rec, ev in rows:
        counts[ev["classification"]] += 1
        rc = rec["rule_checklist"]
        no_claim = ev["classification"] == "NO_TRADING_CLAIM"
        core = "n/a" if no_claim else (
            ", ".join(f"{k}:{rc[k]['status'][0]}" for k in CORE if rc[k]["status"] != "OBSERVED") or "–")
        perf = "; ".join(rec["performance"]["numbers"]) or "–"
        ts, tt = rec["performance"]["trades_shown"], rec["selection"]["trades_total"]
        shown = f"{'?' if ts is None else ts}/{'?' if tt is None else tt}"
        lk = ev["luck"]
        if lk["luck_bar"] is None:
            luck = "–"
        else:
            luck = f"N={lk['N']}, T={lk['T_years']} → {lk['luck_bar']:.2f}"
            if lk["sr_minus_luck_bar"] is not None:
                luck += f"; SR {lk['stated_sr']} − bar = {lk['sr_minus_luck_bar']:+.2f}"
        flags = [k for k in STANDARD_FLAGS if rec["red_flags"]["standard"][k] is True]
        flags += [k for k, v in ev["computed_flags"].items() if v is True and not (no_claim and k == "costs_not_shown")]
        flags.append(f"fri:{len(rec['red_flags']['free'])}")
        prior = ", ".join(rec["lab_prior"]["matches"]) or "–"
        lines.append("| " + " | ".join(_cell(x) for x in (
            rec["id"], rec["source"], ev["classification"], core, perf, shown, rec["performance"]["account"], luck,
            ", ".join(flags), prior)) + " |")
    out = ["# Video-claim register", "",
           f"Genereret af `research/tools/video_triage.py report` fra `{_rel(claims_dir)}` ({len(rows)} poster). "
           "Kerne: entry_signal, stop, target, time_exit (P = PARTIAL, U = UNKNOWN). Held-baren er DIAGNOSTIC_ONLY, "
           "ikke en statistisk test. Lab-prior er kun en liste over factory-registrets poster med samme lineage eller "
           "mechanism_tag; den vurderer intet.", "",
           "Optælling: " + ", ".join(f"{k} {counts[k]}" for k in CLASSES), ""] + lines
    if bad:
        out += ["", "Ugyldige poster (ikke med i tabellen):", ""] + [f"- `{n}`: {_cell(m)}" for n, m in bad]
    return "\n".join(out) + "\n"


def _rel(p):
    a = os.path.abspath(p)
    return os.path.relpath(a, HERE) if a.startswith(HERE + os.sep) else os.path.basename(a)


# ---------------------------------------------------------------- frames (GStreamer, lazy)

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def refuse_url(path):
    s = str(path).strip()
    if s.lower().startswith("http") or URL_RE.match(s):
        raise ValueError(f"refused: {s[:60]!r} looks like a URL; only local files are read, nothing is fetched")


PIPELINE = ("filesrc name=src ! decodebin ! videoconvert ! videorate ! video/x-raw,framerate=1/{n} ! videoscale ! "
            "video/x-raw,width={w} ! pngenc ! multifilesink name=sink")


def extract(video, out, every_s=3, width=360, timeout_s=600):
    """Write one PNG every `every_s` seconds (frame fNNN.png ~ second NNN * every_s) plus manifest.json."""
    refuse_url(video)
    refuse_url(out)
    if isinstance(every_s, bool) or not isinstance(every_s, int) or every_s < 1:
        raise ValueError("--every-s must be an integer >= 1")
    if isinstance(width, bool) or not isinstance(width, int) or not 16 <= width <= 4096:
        raise ValueError("--width must be an integer in 16..4096")
    if not os.path.isfile(video):
        raise FileNotFoundError(video)
    try:
        import gi  # lazy: the only non-stdlib import, used only here
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
    except (ImportError, ValueError) as ex:
        raise RuntimeError(f"GStreamer via PyGObject is not available: {ex}") from ex
    os.makedirs(out, exist_ok=True)
    if any(FRAME_RE.match(n) for n in os.listdir(out)):
        raise FileExistsError(f"{out} already holds frames; use an empty directory")
    Gst.init(None)
    desc = PIPELINE.format(n=every_s, w=width)
    pipe = Gst.parse_launch(desc)
    pipe.get_by_name("src").set_property("location", os.path.abspath(video))     # set, not parsed: no quoting issues
    pipe.get_by_name("sink").set_property("location", os.path.join(os.path.abspath(out), "f%03d.png"))
    bus = pipe.get_bus()
    duration_s = None
    try:
        pipe.set_state(Gst.State.PAUSED)
        res, _, _ = pipe.get_state(min(timeout_s, 30) * Gst.SECOND)
        if res == Gst.StateChangeReturn.FAILURE:
            msg = bus.timed_pop_filtered(0, Gst.MessageType.ERROR)
            raise RuntimeError("pipeline failed to preroll" + (f": {msg.parse_error()[0].message}" if msg else ""))
        ok, dur = pipe.query_duration(Gst.Format.TIME)
        if ok and dur > 0:
            duration_s = round(dur / Gst.SECOND, 3)
        pipe.set_state(Gst.State.PLAYING)
        msg = bus.timed_pop_filtered(int(timeout_s * Gst.SECOND), Gst.MessageType.EOS | Gst.MessageType.ERROR)
        if msg is None:
            raise TimeoutError(f"no EOS within {timeout_s} s")
        if msg.type == Gst.MessageType.ERROR:
            err, dbg = msg.parse_error()
            raise RuntimeError(f"GStreamer error: {err.message} ({dbg})")
    finally:
        pipe.set_state(Gst.State.NULL)
    frames = sorted(n for n in os.listdir(out) if FRAME_RE.match(n))
    manifest = {
        "schema": MANIFEST_SCHEMA, "video": os.path.basename(video), "video_sha256": sha256_file(video),
        "video_bytes": os.path.getsize(video), "duration_s": duration_s, "frame_count": len(frames),
        "frames": [{"file": n, "t_s": i * every_s} for i, n in enumerate(frames)],
        "settings": {"every_s": every_s, "width": width, "pipeline": desc},
        "gstreamer": Gst.version_string(),
    }
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(manifest, indent=1) + "\n")
    return manifest


# ---------------------------------------------------------------- CLI

def _print_eval(ev):
    print(f"id: {ev['id']}")
    for x in ev["errors"]:
        print(f"ERROR: {x}")
    for x in ev["warnings"]:
        print(f"WARNING: {x}")
    if ev["classification"] is None:
        print("INVALID")
        return
    for r in ev["reasons"]:
        print(f"reason: {r}")
    lk = ev["luck"]
    print(f"luck: {lk['status']} N={lk['N']} T={lk['T_years']} bar={lk['luck_bar']} SR={lk['stated_sr']} "
          f"SR-bar={lk['sr_minus_luck_bar']} ({'; '.join(lk['assumptions'])})")
    if "notional" in ev:
        n = ev["notional"]
        print(f"notional: {n['notional']:,.2f} leverage {n['leverage']:,.1f}x (max {n['max_leverage']:,.0f}) "
              f"flag={n['flag']}")
    print("computed flags: " + ", ".join(f"{k}={v}" for k, v in ev["computed_flags"].items()))
    print("lab prior (listed, not judged): " + (", ".join(ev["prior_matches"]) or "none"))
    print(("INVALID " if ev["errors"] else "") + f"CLASSIFICATION: {ev['classification']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("extract", help="frames via GStreamer (local files only)")
    x.add_argument("--video", required=True)
    x.add_argument("--out", required=True)
    x.add_argument("--every-s", type=int, default=3)
    x.add_argument("--width", type=int, default=360)
    x.add_argument("--timeout-s", type=int, default=600)
    n = sub.add_parser("new", help="create a claim skeleton")
    n.add_argument("--id", required=True)
    n.add_argument("--source", required=True)
    n.add_argument("--video-sha256", required=True)
    n.add_argument("--dir", default=CLAIMS_DIR)
    c = sub.add_parser("check", help="validate and classify one claim")
    c.add_argument("--claim", required=True)
    c.add_argument("--registry", default=REGISTRY)
    c.add_argument("--fill-prior", action="store_true", help="write the register matches into the claim file")
    r = sub.add_parser("report", help="markdown register of all claims")
    r.add_argument("--dir", default=CLAIMS_DIR)
    r.add_argument("--out", required=True)
    r.add_argument("--registry", default=REGISTRY)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "extract":
            m = extract(a.video, a.out, a.every_s, a.width, a.timeout_s)
            print(f"{m['frame_count']} frames, duration {m['duration_s']} s, sha256 {m['video_sha256']}")
        elif a.cmd == "new":
            print(new_claim(a.id, a.source, a.video_sha256, a.dir))
        elif a.cmd == "check":
            rec = load(a.claim)
            ev = evaluate(rec, a.registry)
            if a.fill_prior and not validate(rec):
                rec["lab_prior"]["matches"] = ev["prior_matches"]
                with open(a.claim, "w", encoding="utf-8") as f:
                    f.write(dump(rec))
                ev["warnings"] = [w for w in ev["warnings"] if "fill-prior" not in w]
                print("lab_prior.matches written")
            _print_eval(ev)
            return 1 if ev["errors"] else 0
        elif a.cmd == "report":
            text = report(a.dir, a.registry)
            with open(a.out, "w", encoding="utf-8") as f:
                f.write(text)
            print(a.out)
    except (ValueError, OSError, RuntimeError) as ex:
        print(f"ERROR: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
