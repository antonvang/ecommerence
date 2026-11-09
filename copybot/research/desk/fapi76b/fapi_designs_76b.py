"""Director order 76-B: the five mechanism designs as data, the six fast-falsification gates, their V2 representation
(in code, never persisted) and a validation_engine assessment. UDKAST, IKKE LÅST: this module locks nothing, charges no
alpha, writes no file and adds no ledger row. Numbers come from fapi_power_76b.ENDPOINTS and are ASSUMPTIONS.
"""
from __future__ import annotations

import hashlib
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.desk.fapi76b import fapi_evaluators_76b as ev  # noqa: E402
from research.desk.fapi76b import fapi_power_76b as pw  # noqa: E402
from research.tools import factory, register_v2 as v2, validation_engine as ve  # noqa: E402

SNAPSHOT = os.path.join(HERE, "research", "desk", "register_snapshots", "SNAPSHOT_v1.json")
EVALUATOR = ev.__file__
STATUS = "UDKAST, IKKE LÅST"

EXISTING, CACHED, BLOCKED_FWD, NOT_APPROVED = "EXISTING_ACTIVE", "CACHED_FROM_2026-11-14", "BLOCKED_FORWARD", "NOT_APPROVED"
DATA = {
    "bn_census": {"status": EXISTING, "what": "census/1: time for time alle USD-M-perps: mark, index, lastFundingRate, rullende 24 t-ticker"},
    "bn_abnormal_move": {"status": EXISTING, "what": "abnormal_move/1: 12 markeder, 1 t-klines, z, book_rt (5.000 USD)"},
    "klines_1h_archive": {"status": CACHED, "what": "data.binance.vision 1 t-klines, explore0 og train3/validation3; ikke 2024+"},
    "funding_archive": {"status": CACHED, "what": "data.binance.vision afregnet funding, samme vinduer"},
    "metrics_archive_history": {"status": CACHED, "what": "metrics (OI, 5 min), 30 mønter, kun train3/validation3 (ændring 21j-kortlægningen)"},
    "metrics_archive_forward": {"status": BLOCKED_FWD, "what": "metrics efter låsen; data.binance.vision er DNS-blokeret lokalt (ordre 61), omgås ikke"},
    "oi_endpoint_forward": {"status": NOT_APPROVED, "what": "OI fra fapi: ny datalinje, ikke godkendt"},
    "premium_index_klines": {"status": NOT_APPROVED, "what": "premiumIndexKlines/markPriceKlines: kun brugt én gang i research/m3.py; ingen protokolgodkendelse fundet"},
    "force_orders": {"status": NOT_APPROVED, "what": "likvidationsfeed: ingen godkendt strøm"},
}
_DATA_OK = (EXISTING, CACHED)

GATES = ("MECHANISM", "DATA_ALLOWED", "DATA_REALISTIC", "DISTINCT", "EFFECT_REACHABLE", "VALIDATION_PLAN")
MIN_CLUSTERS, MAX_MONTHS = 40, 24

DESIGNS = {
    "CB1": {
        "priority": "P1 volatilitetsregimer og strukturelle brud", "title": "Kompression, derefter udbrud med deltagelse (dagsbarer)",
        "lineage": "cross_sectional_momentum", "related_lineages": ["betting_against_beta"],
        "endpoints": ["CB1_VOL", "CB1_DIR"], "universe": "alle USD-M-perps i census, pr. dag: volumen >= 1 mio. USD, set >= 30 d, ingen kendt afnotering",
        "mechanism_ok": True, "mechanism_reason": "brud i volatilitetsregime og stop- og gearingspres kan testes mekanisk på dagsbarer",
        "distinct_ok": True, "distinct_reason": "hændelsesbetinget dagsregel; afviger fra timetrend; retning og vol adskilt; VOL efter FUNDFRAG1-præcedensen uden for F2's grænse (åbent punkt)",
        "data_required": ["bn_census"], "secondary_data": ["metrics_archive_history"], "validation_data": ["bn_census"],
        "window": {"start": "2026-12-07", "end": "2028-03-05", "months": 15, "note": "90 d opvarmning efter låsen + 12 mdr. hændelser"},
    },
    "PR1": {
        "priority": "P1 funding og perp-prisdannelse", "title": "Fundingperiodens premium-henfald: likvide mod tynde perps",
        "lineage": "cross_venue_perp_gap", "related_lineages": [],
        "endpoints": ["PR1"], "universe": "census-perps med volumen >= 1 mio. USD; likvid og tynd = øverste og nederste volumentercil pr. døgn",
        "mechanism_ok": True, "mechanism_reason": "funding-transfer og begrænset arbitragekapital giver testbar forskel i premium-henfald",
        "distinct_ok": True, "distinct_reason": "måler ingen handel; M3 og L22 viste handlen død; kontrasten likvid mod tynd er ikke testet",
        "data_required": ["bn_census"], "secondary_data": [], "validation_data": ["bn_census"],
        "window": {"start": "2026-12-07", "end": "2027-06-05", "months": 6, "note": "kun efter låsen"},
    },
    "LD1": {
        "priority": "P2 likviditetsforstyrrelser og normalisering", "title": "Kursledt mod likviditetsledt bogforstyrrelse",
        "lineage": "maker_adverse_selection_measurement", "related_lineages": ["liquidation_cascade_reversal"],
        "endpoints": ["LD1"], "universe": "scannerens 12 markeder (som LQ1)",
        "mechanism_ok": True, "mechanism_reason": "lager- mod informationsdrevet likviditet er en testbar forskel",
        "distinct_ok": False, "distinct_reason": "samme rækker og hændelser som LQ1 og inden for LIQREC1's mekanismegrænse; kan kun være sekundær analyse under LQ1",
        "data_required": ["bn_abnormal_move"], "secondary_data": [], "validation_data": ["bn_abnormal_move"],
        "window": {"start": "2026-11-23", "end": "2027-02-22", "months": 3, "note": "LQ1's vindue, antagelse"},
    },
    "FL1": {
        "priority": "P2 ekstreme bevægelser og efterfølgende dynamik", "title": "4 sigma-fald med OI-flush, hold 24 t",
        "lineage": "liquidation_cascade_reversal", "related_lineages": ["cross_sectional_momentum"],
        "endpoints": ["FL1"], "universe": "30v3 (metrics findes kun der)",
        "mechanism_ok": True, "mechanism_reason": "tvunget salg overskyder, og likviditetsudbydere betales (Brunnermeier og Pedersen 2009)",
        "distinct_ok": False, "distinct_reason": "M2 (L21) testede OI-fald plus kursbevægelse: alle 18 varianter netto negative, og længere hold var brutto negative; 4 sigma-faldet er set efter data i explore0",
        "data_required": ["metrics_archive_history", "klines_1h_archive"], "secondary_data": [], "validation_data": ["metrics_archive_forward"],
        "window": {"start": "2022-01-01", "end": "2023-12-31", "months": 24, "note": "kun udvikling; ingen fremadrettet OI"},
    },
    "TS1": {
        "priority": "P3 tidsmønstre og regimeskift (betinget)", "title": "US-session i BTC i højvol-regime",
        "lineage": "calendar_day_of_week", "related_lineages": [],
        "endpoints": ["TS1"], "universe": "BTCUSDT",
        "mechanism_ok": False, "mechanism_reason": "ETF-flow i US-timer startede 2024; hele regimet ligger i forseglede vinduer; ingen mekanisme ud over timemønster",
        "distinct_ok": False, "distinct_reason": "hour_of_day, day_of_week og turn_of_month er afvist; en betingelse giver flere gafler, ikke en ny mekanisme",
        "data_required": ["bn_census"], "secondary_data": [], "validation_data": ["bn_census"],
        "window": {"start": "2026-12-07", "end": "2027-12-06", "months": 12, "note": "kun fremad"},
    },
}

# Planned cost tests for return endpoints (bp round trip), as a realistic figure and the screening floor of amendment 21i.
GROSS_BPS = {"CB1_DIR": 45.0, "FL1": 60.0, "TS1": 4.0}
PROTECTED = [("2024-01-01", "2024-12-31"), ("2025-01-01", "2026-11-15")]     # 2024 holdout; reserved until the earliest lock
BANNED_SOURCES = ["quarantine_register", "reserved_archive_2025plus"]
QUARANTINED = ["quarantined_pair_file"]


def lineage_status(did, snapshot):
    """'IN_SNAPSHOT' when the lineage is a key of the snapshot's lineage map, else 'NOT_IN_SNAPSHOT' (no ledger row)."""
    return "IN_SNAPSHOT" if DESIGNS[did]["lineage"] in snapshot["lineage_map"] else "NOT_IN_SNAPSHOT"


def gates(did):
    """The six gates of the order's fast falsification. EFFECT_REACHABLE is per endpoint; the rest apply to the design."""
    d = DESIGNS[did]
    rows = {e: pw.endpoint_row(e) for e in d["endpoints"]}
    blocked = [s for s in d["data_required"] if DATA[s]["status"] not in _DATA_OK]
    validation_blocked = [s for s in d["validation_data"] if DATA[s]["status"] != EXISTING]
    n_ok = all(r["n"] >= MIN_CLUSTERS for r in rows.values()) and d["window"]["months"] <= MAX_MONTHS
    out = {"MECHANISM": (d["mechanism_ok"], d["mechanism_reason"]),
           "DATA_ALLOWED": (not blocked, "ok" if not blocked else f"blokeret: {blocked}"),
           "DATA_REALISTIC": (n_ok, f"min. klynger {min(r['n'] for r in rows.values())}, {d['window']['months']} mdr."),
           "DISTINCT": (d["distinct_ok"], d["distinct_reason"]),
           "EFFECT_REACHABLE": ({e: r["reachable"] for e, r in rows.items()},
                                {e: {"mde": r["mde_alpha_f"], "plausibel": r["plausible_net"]} for e, r in rows.items()}),
           "VALIDATION_PLAN": (not validation_blocked, "fremadrettet vindue efter låsen, kørt af anden session" if not validation_blocked
                               else f"ingen fremadrettet datakilde: {validation_blocked}")}
    return out


def verdict(did):
    """{endpoint: (verdict, failed gates)}. Survival means descriptive measurement at alpha = 0, nothing more."""
    g = gates(did)
    fixed = [k for k in GATES if k != "EFFECT_REACHABLE" and not g[k][0]]
    out = {}
    for e, reachable in g["EFFECT_REACHABLE"][0].items():
        failed = fixed + ([] if reachable else ["EFFECT_REACHABLE"])
        out[e] = ("OVERLEVER_BESKRIVENDE" if not failed else "AFVIST", failed)
    return out


def snapshot_text():
    with open(SNAPSHOT, encoding="utf-8") as f:
        return f.read()


def snapshot_counts():
    import json
    return json.loads(snapshot_text())


def evaluator_sha():
    with open(EVALUATOR, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def v2_record(did):
    """A validated FUTURE record in memory. variants_tested stays MISSING_INPUT until a run; data_quality is NOT_CHECKED."""
    d = DESIGNS[did]
    eps = {e: pw.ENDPOINTS[e] for e in d["endpoints"]}
    rt = max(pw.ENDPOINTS[e]["cost_rt_bps"] for e in d["endpoints"])
    params = v2.parameters_block({
        "status": STATUS, "independent_discovery_claim": False, "alpha": "0 beskrivende; testniveau 0.0125 ensidet",
        "register_n_minimum": pw.REGISTER_N, "register_n_is_final": False, "n_eff": "MISSING_INPUT",
        "related_lineages": d["related_lineages"], "endpoints": eps, "cb1_rules": ev.CB1, "pr1_rules": ev.PR1, "ld1_rules": ev.LD1,
        "fl1_rules": ev.FL1, "ts1_rules": ev.TS1, "universe": d["universe"]})
    return v2.record(
        f"FAPI76B-{did}", v2.FUTURE, hypothesis_id=did, lineage=d["lineage"],
        trial_universe={"definition": f"forhåndsregistrerede endepunkter {sorted(d['endpoints'])}", "size": len(d["endpoints"]),
                        "members_sha256": factory.sha(sorted(d["endpoints"]))},
        variants_tested=None, parameters=params, code_hash=evaluator_sha(),
        data_source={"name": "+".join(d["data_required"]), "sha256": factory.sha({s: DATA[s] for s in d["data_required"]})},
        data_period={"start": d["window"]["start"], "end": d["window"]["end"]},
        cost_model={"name": "21i-gulv og realistisk rundtur (ANTAGELSE)" if rt else "ingen ordrer", "round_trip_bps": rt,
                    "sha256": factory.sha({"rt": rt, "floor": [pw.ENDPOINTS[e]["floor_bps"] for e in d["endpoints"]]})},
        evaluation_method={"name": "ensidet klynge-t, UTC-døgn, alpha 0.0125; dom beskrivende (alpha 0)", "sha256": factory.sha(eps)},
        data_quality={"status": "NOT_CHECKED"}, deviations=[],
        register_snapshot={"sha256": v2.snapshot_sha(snapshot_text()), "rules_version": 1})


# ---- validation_engine assessment on synthetic inputs (a design is never passed) ----

def signal_for(did):
    """(signal_fn, synthetic rows) for the truncation test; a fixed seed and no market data."""
    rng = random.Random(76)
    if did == "CB1":
        bars, c = [], 100.0
        for i in range(260):
            c *= math.exp(rng.gauss(0, 0.01))
            bars.append({"ts": i * ev.DAY, "close": c, "high": c * (1 + abs(rng.gauss(0, 0.01))), "low": c * (1 - abs(rng.gauss(0, 0.01))),
                         "volume": 1e6 * math.exp(rng.gauss(0, 0.4))})
        return ev.cb1_signal_series, bars
    if did == "PR1":
        rows = [{"mark": 100 * (1 + rng.gauss(0, 0.0015)), "index": 100.0} for _ in range(200)]
        return ev.pr1_signal_series, rows
    if did == "LD1":
        return ev.ld1_signal_series, [{"z_abs": abs(rng.gauss(0, 2))} for _ in range(100)]
    if did == "FL1":
        rows = [{"r": rng.gauss(0, 0.01), "oi_chg": rng.gauss(0, 0.01)} for _ in range(800)]
        return ev.fl1_signal_series, rows
    rows = [{"ts": i * ev.HOUR, "r": rng.gauss(0, 0.005)} for i in range(24 * 45)]
    return ev.ts1_signal_series, rows


def assess_design(did, best_t=None, n_reported=None):
    """Run what can be checked before any data. The engine ends in MISSING_INPUT or worse: a design never reaches PASS."""
    d = DESIGNS[did]
    k = len(d["endpoints"])
    fn, rows = signal_for(did)
    checks = {
        ve.LOOKAHEAD: {"signal_fn": fn, "data": rows},
        ve.CONTAMINATION: {"windows": [(d["window"]["start"], d["window"]["end"])], "protected_windows": PROTECTED,
                           "sources": d["data_required"], "banned_sources": BANNED_SOURCES, "artifacts": [], "quarantined": QUARANTINED},
        ve.MULTIPLE_TESTING: {"best_t": best_t, "n_tested": pw.REGISTER_N + k, "n_reported": n_reported},
    }
    ret = [e for e in d["endpoints"] if pw.ENDPOINTS[e]["unit"] == "frac" and pw.ENDPOINTS[e]["cost_rt_bps"] > 0]
    if ret:
        e = ret[0]
        floor = pw.ENDPOINTS[e]["floor_bps"]
        checks[ve.COSTS] = {"gross_bps_per_trade": GROSS_BPS[e], "assumed_cost_bps": max(pw.ENDPOINTS[e]["cost_rt_bps"], floor),
                            "floor_cost_bps": floor}
    return ve.evaluate(checks)
