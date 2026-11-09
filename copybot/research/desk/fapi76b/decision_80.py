"""Director order 80 P1: CB1_VOL is registered as RELATED_MECHANISM with FACTORY F2. Registration only: the classification
is the director's conservative ruling, not a claim that the mechanisms are identical, and CB1_VOL stays on HOLD.

The committed 76-B and 79 files are not changed. The update is expressed the way register V2 requires: a new entry on the
same record id, with a deviation naming each changed locked field. Nothing here is persisted, no ledger row is added, no
sealed F2 result is opened, and the protocol of F2 is not changed, retroactively or otherwise.
"""
from __future__ import annotations

import copy
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.desk.fapi76b import fapi_designs_76b as dg  # noqa: E402
from research.desk.fapi76b import triage_79 as tr  # noqa: E402
from research.tools import register_v2 as v2  # noqa: E402

CLASSIFICATION = tr.RELATED
DOCUMENTARY_FINDING_79 = tr.INSUFFICIENT                 # order 79's reading of the documents; the ruling does not rewrite it
RULED_BY = "direktørordre 80"
STATUS_CB1_VOL = tr.HOLD
F2_LINEAGE = "betting_against_beta"                      # F2's own lineage in the test budget (FACTORY_P2 L86-88)
DEVIATION_DATE = "2026-11-10"

# Everything that counts in the overlap audit. "ledger" says if the item has a row in snapshot v1.
F2_OVERLAP_AUDIT = [
    {"id": "FACTORY_F2", "ledger": False, "state": "CONDITIONAL", "note": "HAR-RV mod EWMA, QLIKE; låst tekst; ingen resultater åbnet"},
    {"id": "C1", "ledger": False, "state": "READY_NOT_ACTIVE", "note": "F2's fremadrettede prognosejournal"},
    {"id": "E_vol_managed_long_p1", "ledger": True, "state": "i snapshot", "note": "volatility_managed_exposure"},
    {"id": "E_vol_managed_long_p2", "ledger": True, "state": "i snapshot", "note": "volatility_managed_exposure"},
    {"id": "E_xs_betting_against_beta_p2", "ledger": True, "state": "i snapshot", "note": "samme lineage"},
    {"id": "E_xs_low_volatility_p2", "ledger": True, "state": "i snapshot", "note": "low_volatility_anomaly"},
    {"id": "FUNDFRAG1", "ledger": False, "state": "udkast", "note": "matcher på fortidig RV; funding som ekstra input"},
    {"id": "C3", "ledger": False, "state": "låst census-nøgle", "note": "halebredde mod volatilitet"},
    {"id": "C4", "ledger": False, "state": "låst census-nøgle", "note": "volumen uden kurs mod volatilitet; udelukker CB1-hændelser, deler rækker"},
]


def revised_record():
    """FAPI76B-CB1 as a correction: lineage moved to F2's, parameters extended, and one deviation naming both fields."""
    rec = copy.deepcopy(dg.v2_record("CB1"))
    values = copy.deepcopy(rec["parameters"]["values"])
    values.update({
        "order_80": {"classification": CLASSIFICATION, "ruled_by": RULED_BY, "identical_mechanism_claim": False,
                     "documentary_finding_order_79": DOCUMENTARY_FINDING_79, "cb1_vol_status": STATUS_CB1_VOL,
                     "cb1_dir_status": "NO_GO, se TRIAGE79-CB1_DIR", "independent_lineage": False, "related_to": "FACTORY_F2",
                     "sealed_f2_results_opened": False, "f2_protocol_changed": False, "activated": False,
                     "overlap_audit": [a["id"] for a in F2_OVERLAP_AUDIT]},
        "related_lineages": ["cross_sectional_momentum"]})             # the rejected direction endpoint's old lineage
    rec["lineage"] = F2_LINEAGE
    rec["parameters"] = v2.parameters_block(values)
    rec["deviations"] = [{"date": DEVIATION_DATE, "fields": ["lineage", "parameters"],
                          "description": "Direktørordre 80: CB1_VOL registreres som RELATED_MECHANISM med FACTORY F2 uden "
                                         "selvstændig lineage. Ikke en påstand om identisk mekanisme. Ingen F2-resultater åbnet."}]
    return v2.record(rec["record_id"], rec["era"], **{k: rec[k] for k in v2.FIELDS + v2.OPTIONAL if k in rec})


def update_chain():
    """An in-memory chain: the 76-B record, then its correction. chain_verify replays the revision rules."""
    chain = []
    v2.chain_append(chain, dg.v2_record("CB1"), "2026-11-09")
    v2.chain_append(chain, revised_record(), DEVIATION_DATE)
    v2.chain_verify(chain)
    return chain
