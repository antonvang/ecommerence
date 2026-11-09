"""Director order 79: FAPI research triage on top of the committed 76-B designs. Data and rules only: no file is written,
no market data is read, no lock, alpha, status or ledger row. The 76-B modules are not changed by this one.

- DIRECTOR_VERDICTS: the director's rulings, which replace the verdicts of the 76-B gates.
- CB1_VOL_COMPARISON and classify(): the read-only comparison with the locked mechanism definition of FACTORY F2.
- REJECTED and rejected_record(): the four rejected designs as in-memory V2 records (register V2 has no status field, so
  the rejection lives in the hashed parameters). Never persisted, never run, never re-optimised.
- OPEN_LIMITATIONS: what stays open. Nothing here closes any of them.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.desk.fapi76b import fapi_designs_76b as dg  # noqa: E402
from research.desk.fapi76b import fapi_power_76b as pw  # noqa: E402
from research.tools import factory, register_v2 as v2  # noqa: E402

GO_DESCRIPTIVE, HOLD, NO_GO = "GO_DESCRIPTIVE_ONLY", "HOLD", "NO_GO"
DIRECTOR_VERDICTS = {"PR1": GO_DESCRIPTIVE, "CB1_VOL": HOLD, "CB1_DIR": NO_GO, "LD1": NO_GO, "FL1": NO_GO, "TS1": NO_GO}

SAME, RELATED, DISTINCT, INSUFFICIENT = "SAME_MECHANISM", "RELATED_MECHANISM", "DISTINCT_MECHANISM", "INSUFFICIENT_EVIDENCE"
SHARED, DIFFERENT, UNRESOLVED = "SHARED", "DIFFERENT", "UNRESOLVED"
F2_SOURCE = "research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md"
F2_SHA256 = "6dd1ca82934419c0913bccb3a8962f5e5e5154d678eee59179292a7694ae5f43"

CB1_VOL_COMPARISON = [
    {"axis": "udfald", "relation": SHARED, "f2": "realiseret volatilitet", "cb1_vol": "realiseret volatilitet",
     "source": "FACTORY_P2 L78-98; fapi_evaluators_76b.cb1_vol_outcomes"},
    {"axis": "nulmodel", "relation": SHARED, "f2": "HAR-RV 1, 7, 30 d; grænsen nævner log-HAR", "cb1_vol": "log-HAR 1, 7, 30 d som nulmodel",
     "source": "FACTORY_P2 L85-86, L96-98; fapi_evaluators_76b.har_log_forecast"},
    {"axis": "kompressionsbetingelse", "relation": SHARED, "f2": "regimemodeller er inden for grænsen", "cb1_vol": "7 d-range under egen 90 d-fraktil: en tilstand af fortidig volatilitet",
     "source": "FACTORY_P2 L85-86; PROTOCOL_SHORTLIST C25"},
    {"axis": "horisont og måling", "relation": DIFFERENT, "f2": "næste døgn, 1 t-kline-lukkepriser, QLIKE mod EWMA", "cb1_vol": "næste 3 døgn, census-mark, middel af residual mod kontrol",
     "source": "FACTORY_P2 L96-103; C1_FORECAST_DESIGN afsnit 2"},
    {"axis": "ikke-RV-input", "relation": UNRESOLVED, "f2": "grænsen taler kun om fortidig realiseret volatilitet; den nævner ikke ekstra input",
     "cb1_vol": "kursbrud af 20 d-kanal og volumen >= 2 x median", "source": "FACTORY_P2 L85-86"},
    {"axis": "præcedens", "relation": UNRESOLVED, "f2": "ingen afgørelse fra direktøren om ekstra input",
     "cb1_vol": "FUNDFRAG1 kalder sig selv uden for grænsen, men er et ikke-godkendt udkast", "source": "protocols/FUNDFRAG1_v1.md afsnit 8"},
]


def classify(comparison):
    """Fail closed: an empty comparison or any unresolved axis gives INSUFFICIENT_EVIDENCE. Otherwise all shared is the
    same mechanism, none shared is distinct, and a mix is related."""
    if not comparison or any(a["relation"] == UNRESOLVED for a in comparison):
        return INSUFFICIENT
    shared = sum(a["relation"] == SHARED for a in comparison)
    if shared == len(comparison):
        return SAME
    return DISTINCT if shared == 0 else RELATED


def ruled_out(comparison):
    """Classes the documents already exclude, even when the comparison as a whole is unresolved."""
    return [DISTINCT] if any(a["relation"] == SHARED for a in comparison) else []


REJECTED = {
    "CB1_DIR": {"design": "CB1", "endpoints": ["CB1_DIR"], "gates_failed": ["EFFECT_REACHABLE"],
                "reason": "MDE 0,92 % pr. 3 døgn netto mod plausibel 0,14 % (begge antagelser); brutto krævet ca. 123 bp",
                "overlap": ["L14_tsmom_v1", "L03_sol_trend_hourly", "E_oi_confirmed_return_p3", "E_xs_high_volume_p2"]},
    "LD1": {"design": "LD1", "endpoints": ["LD1"], "gates_failed": ["DISTINCT", "EFFECT_REACHABLE"],
            "reason": "samme rækker og hændelser som LQ1, inden for LIQREC1's mekanismegrænse; MDE 8,1 bp mod plausibel 3 bp",
            "overlap": ["LQ1", "LIQREC1"]},
    "FL1": {"design": "FL1", "endpoints": ["FL1"], "gates_failed": ["DISTINCT", "VALIDATION_PLAN", "EFFECT_REACHABLE"],
            "reason": "M2 testede OI-fald plus kursbevægelse, alle 18 varianter netto negative; ingen fremadrettet OI; MDE 2,30 %",
            "overlap": ["L21_m2_liquidation_reversal", "MOVESCREEN_m21c", "E_daily_reversal_p1"]},
    "TS1": {"design": "TS1", "endpoints": ["TS1"], "gates_failed": ["MECHANISM", "DISTINCT", "EFFECT_REACHABLE"],
            "reason": "ETF-regimet ligger i forseglede vinduer; kalenderslægten er afvist; brutto krævet ca. 48 bp mod skøn 4 bp",
            "overlap": ["E_hour_of_day_p1", "E_day_of_week_p1", "E_turn_of_month_p2"]},
}

OPEN_LIMITATIONS = {
    "G05_CLUSTER_DAYS": "antal klyngedøgn er ukendt, indtil en tilladt lås findes; census må ikke tælles til formålet før (G05)",
    "FORWARD_OI": "fremadrettet OI er utilgængelig: arkivet er DNS-blokeret lokalt og omgås ikke; fapi-OI er en ugodkendt ny datalinje",
    "DELISTING_PROVENANCE": "afnoteringer ses ikke i census; provenansen er uafklaret",
    "BINANCE_FORMULA_UNVERIFIED": "Binances funding-, mark- og indeksformler er UNVERIFIED; Binance-værter må ikke kaldes",
    "REGISTER_N_MINIMUM": "19.438 historiske varianter er et konservativt minimum; N_eff er MISSING_INPUT og kendes ikke",
}


def rejected_record(name):
    """A validated FUTURE record in memory for one rejected design. The rejection is part of the hashed parameters."""
    r = REJECTED[name]
    d = dg.DESIGNS[r["design"]]
    eps = {e: pw.ENDPOINTS[e] for e in r["endpoints"]}
    params = v2.parameters_block({
        "triage_status": "REJECTED_NO_GO_ORDER_79", "never_run": True, "reoptimization_allowed": False, "ledger_row": False,
        "gates_failed": r["gates_failed"], "reason": r["reason"], "overlap": r["overlap"], "related_lineages": d["related_lineages"],
        "independent_discovery_claim": False, "register_n_minimum": pw.REGISTER_N, "register_n_is_final": False,
        "n_eff": "MISSING_INPUT", "endpoints": eps})
    rt = max(e["cost_rt_bps"] for e in eps.values())
    return v2.record(
        f"TRIAGE79-{name}", v2.FUTURE, hypothesis_id=name, lineage=d["lineage"],
        trial_universe={"definition": f"afvist design, endepunkter {sorted(r['endpoints'])}", "size": len(r["endpoints"]),
                        "members_sha256": factory.sha(sorted(r["endpoints"]))},
        variants_tested=None, parameters=params, code_hash=dg.evaluator_sha(),
        data_source={"name": "+".join(d["data_required"]), "sha256": factory.sha({s: dg.DATA[s] for s in d["data_required"]})},
        data_period={"start": d["window"]["start"], "end": d["window"]["end"]},
        cost_model={"name": "udkast, ANTAGELSE; kørsel forbudt" if rt else "ingen ordrer; kørsel forbudt", "round_trip_bps": rt,
                    "sha256": factory.sha({"rt": rt})},
        evaluation_method={"name": "ingen: afvist af direktørordre 79", "sha256": factory.sha({"run": False, "order": 79})},
        data_quality={"status": "NOT_CHECKED"}, deviations=[],
        register_snapshot={"sha256": v2.snapshot_sha(dg.snapshot_text()), "rules_version": 1})
