"""Director order 102 (DESIGN COMPLETION ONLY): the forward paper book v2 with all 96 forward tests.

ForwardBookV2 extends event_farm_forward.ForwardBook (unchanged) so that every 5m bar books
- the 12 baseline variants exactly as before (test id "base/<variant>"), and
- the 7 filter combinations of event_farm_filters for each variant ("<combo>/<variant>", 84 tests),
each with its own simulated 10,000 USDT account, the same entry, stop, target, fills, costs and statuses.

KNOWN_TS IN THE LIVE PATH. The filter values at bar k come only from the processed bars up to k:
- F1: an incremental 1h tracker identical to event_farm_filters.trend_1h, stepped with every processed bar (an hour
  counts only when all twelve 5m bars of it were processed; a missing 5m bar makes the hour invalid);
- F2: event_farm_filters.prior_day_retest on the processed bars from the start of day D-1 up to k;
- F3: event_farm_filters.vwap_series on the processed bars of the current session up to k (INCOMPLETE, hence BLOCKED,
  after a missing bar or a bar without volume).
Booking is bar by bar, so the values cannot see a later bar; tests compare every booked decision with the offline
filters on bars[:k + 1] and on the full series.

No network code, no data source, no activation: the same injected-source and NotActivated rules as v1 apply, and the
database identity is a new schema (a v1 file is refused).
"""
from __future__ import annotations

import bisect
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from research.tools import event_farm_driver as drv  # noqa: E402
from research.tools import event_farm_filters as ff  # noqa: E402
from research.tools import event_farm_forward as fw  # noqa: E402

SCHEMA = "event_farm_forward/2"
BS = fw.BS


def test_ids():
    """The 96 forward tests in register order (event_farm_filters.all_forward_tests)."""
    return ff.all_forward_tests()


class Trend1H:
    """Incremental twin of event_farm_filters.trend_1h: step(bar) returns the trend known at that bar's close."""

    def __init__(self, k1=ff.FILTER_PARAMS["k1"], hour_s=ff.FILTER_PARAMS["hour_s"]):
        self.k1, self.hour_s, self.need = k1, hour_s, hour_s // BS
        self.h1, self.sh, self.sl = [], [], []
        self.cur, self.members, self.state = None, [], 0
        self.states = []

    def step(self, b):
        start = b[0] // self.hour_s * self.hour_s
        if start != self.cur:
            self.cur, self.members = start, []
        self.members.append(b)
        if b[0] + BS == start + self.hour_s:
            m = self.members
            if len(m) == self.need and all(x[0] == start + k * BS for k, x in enumerate(m)):
                self.h1.append((start, m[0][1], max(x[2] for x in m), min(x[3] for x in m), m[-1][4]))
                k1, j = self.k1, len(self.h1) - 1 - self.k1
                if j - k1 >= 0:
                    H, L = [x[2] for x in self.h1[j - k1:j + k1 + 1]], [x[3] for x in self.h1[j - k1:j + k1 + 1]]
                    if H[k1] > max(H[:k1]) and H[k1] >= max(H[k1 + 1:]):
                        self.sh.append(H[k1])
                    if L[k1] < min(L[:k1]) and L[k1] <= min(L[k1 + 1:]):
                        self.sl.append(L[k1])
                    if len(self.sh) >= 2 and len(self.sl) >= 2:
                        up = self.sh[-1] > self.sh[-2] and self.sl[-1] > self.sl[-2]
                        down = self.sh[-1] < self.sh[-2] and self.sl[-1] < self.sl[-2]
                        self.state = 1 if up else (-1 if down else 0)
            self.cur, self.members = None, []
        self.states.append(self.state)
        return self.state


class ForwardBookV2(fw.ForwardBook):
    def __init__(self, db_path, source, symbols, mode="synthetic", activation=None, clock=None, config=None):
        self.trend, self.ts, self._ctx_cache = {}, {}, {}
        super().__init__(db_path, source, symbols, mode=mode, activation=activation, clock=clock, config=config)
        self.base_variants = list(self.variants)
        by_vid = dict(self.base_variants)
        self.variants = []
        for tid in test_ids():
            vid = tid.split("/", 1)[1]
            self.variants.append((tid, by_vid[vid]))
            self.params[tid] = self.params[vid]

    def _identity(self):
        ident = super()._identity()
        ident.update(schema=SCHEMA, tests=test_ids(), filter_params=ff.FILTER_PARAMS, reference_n=ff.reference_n())
        return ident

    def _load(self):
        super()._load()
        self.trend, self.ts, self._ctx_cache = {}, {}, {}
        for s in self.symbols:
            tr = Trend1H()
            for b in self.bars[s]:
                tr.step(b)
            self.trend[s], self.ts[s] = tr, [b[0] for b in self.bars[s]]

    def _take(self, s, bar, gap, step_no, now, stats):
        self.trend[s].step(bar)
        self.ts[s].append(bar[0])
        super()._take(s, bar, gap, step_no, now, stats)

    def point_context(self, s, k):
        """The filter context at processed bar k of s, from bars[:k + 1] only, keyed by k."""
        key = (s, k)
        if key in self._ctx_cache:
            return self._ctx_cache[key]
        bars, ts = self.bars[s], self.ts[s]
        t = bars[k][0]
        lo_pd = bisect.bisect_left(ts, (t // 86400 - 1) * 86400, 0, k + 1)
        a = ff._hhmm(ff.FILTER_PARAMS["vwap_anchor"])
        lo_vw = bisect.bisect_left(ts, (t - a) // 86400 * 86400 + a, 0, k + 1)
        ctx = {"trend": {k: self.trend[s].states[k]}, "pd": {k: ff.prior_day_retest(bars[lo_pd:k + 1])[-1]},
               "vwap": {k: ff.vwap_series(bars[lo_vw:k + 1])[-1]}, "close": {k: bars[k][4]}, "fp": ff.FILTER_PARAMS}
        self._ctx_cache = {key: ctx}                       # one bar at a time
        return ctx

    def _book(self, s, k, step_no, now, stats):
        bars = self.bars[s]
        evs = [e for e in self.events[s] if e["known_i"] >= k - self.margin]
        end_ts = int(self.db.execute("SELECT v FROM meta WHERE k = 'start_ts'").fetchone()[0]) + \
            self.cfg["duration_days"] * 86400
        for vid, _ in self.base_variants:
            setups, _ = self.ef.build_setups(evs, bars, self.params[vid])
            for st in setups:
                if st["known_i"] != k:
                    continue
                if st["known_ts"] != bars[k][0] + BS or st["i"] > k:
                    raise fw.IntegrityHalt(f"{s}/{vid}: setup not known at its bar")
                ctx = self.point_context(s, k)
                for tid in ["base/" + vid] + [f"{c}/{vid}" for c in ff.COMBOS]:
                    combo = tid.split("/", 1)[0]
                    if combo != "base" and not ff.passes(st, ctx, combo):
                        continue
                    self._insert(tid, s, st, k, end_ts, step_no, now, stats)

    def _insert(self, tid, s, st, k, end_ts, step_no, now, stats):
        if k < self.cfg["warmup_bars"]:
            status = "not_taken_warmup"
        elif st["known_ts"] > end_ts:
            status = "not_taken_ended"
        elif self._coverage(s, k) < self.cfg["coverage_min"]:
            status = "not_taken_coverage"
        elif self._account(tid, st["known_ts"]) <= self.cfg["account_stop_usdt"]:
            status = "not_taken_variant_stopped"
        else:
            status = "pending"
        key = (tid, s, st["known_ts"], st["kind"])
        if self.db.execute("SELECT 1 FROM trades WHERE variant = ? AND symbol = ? AND known_ts = ? AND kind = ?",
                           key).fetchone():
            raise fw.IntegrityHalt(f"{key}: booked twice")
        self.db.execute(
            "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, "
            "NULL, NULL, NULL, NULL, NULL, 0)",
            key + (k, st["ts"], st["chain"], st["dir"], st["entry"], st["stop"], st["target"], st["risk"],
                   st["atr"], st["entry_mode"], step_no, now, now - st["known_ts"], status))
        stats["new_trades"] += 1


def report_v2(book, null_filters=None):
    """event_farm_forward.report over the 96 tests (book.variants holds them), plus the filter null side by side
    (event_farm_filters.null_with_filters output) when given."""
    out = fw.report(book)
    out["n_tests"] = len(out["variants"])
    out["reference_n"] = ff.reference_n()
    if null_filters is not None:
        for tid, v in out["variants"].items():
            n = null_filters["tests"][tid]
            v["null"] = {"setups_per_instrument_day": n["setups_per_instrument_day"], "trades": n["trades"],
                         "mean_gross_r": n["mean_gross_r"], "mean_net_r": n["mean_net_r"]}
        out["null"] = {"seed": null_filters["seed"], "instruments": null_filters["instruments"],
                       "days": null_filters["days"]}
    return out


# ---------------------------------------------------------------- the final register set (in code, not persisted)

def v2_final_records(start_date, end_date):
    """19 FUTURE records for the whole forward family: 12 baseline records and 7 combo records, all with the 96-test
    universe and reference N 19,849. They supersede event_farm_forward.v2_plan_records (universe 12, N 19,765), whose
    record ids are kept for the baseline so the supersession is visible as a revision of the same ids."""
    from research.tools import factory, register_v2 as v2
    tests = test_ids()
    universe = {"definition": "96 fremadrettede tests: 12 baseline + 7 filterkombinationer x 12 (ordre 101/102)",
                "size": len(tests), "members_sha256": factory.sha(tests)}
    src = {"name": "GET /fapi/v1/klines interval=5m BTCUSDT/ETHUSDT, felter 0-5 (open time, OHLC, volume), kun lukkede barer",
           "sha256": factory.sha({"endpoint": "GET /fapi/v1/klines", "interval": "5m", "fields": [0, 1, 2, 3, 4, 5, 6]})}
    cost = {"name": "ANTAGELSE: lab-papirbog 28 bps rundtur (ikke verificerede fremtidige omkostninger)",
            "round_trip_bps": 28.0, "sha256": factory.sha(fw.FROZEN_CONFIG["costs"])}
    method = f"beskrivende papirbog, 96 tests, null seed 83 med filtre, N = {ff.reference_n()}"
    common = {"study_id": "EVENT_FARM", "classification": "RELATED_MECHANISM", "independent_lineage": False,
              "independent_discovery_claim": False, "status": "UDKAST, IKKE LÅST", "activated": False,
              "reference_n": ff.reference_n(), "n_tests_family": len(tests), "frozen_config": fw.FROZEN_CONFIG,
              "filter_params": ff.FILTER_PARAMS, "engine": {"commit": drv.ENGINE_COMMIT, "sha256": drv.ENGINE_SHA256}}
    groups = [(f"EVENT_FARM_FWD_{vid.replace('/', '_')}", f"EVENT_FARM:FWD:{vid}", {"variant": vid, "combo": "base"})
              for vid in [t.split("/", 1)[1] for t in tests if t.startswith("base/")]]
    groups += [(f"EVENT_FARM_FWD_FILTER_{c.replace('+', '_')}", f"EVENT_FARM:FWD:{c}", {"combo": c, "family_tests": 12})
               for c in ff.COMBOS]
    recs = []
    for rid, hid, extra in groups:
        recs.append(v2.record(
            rid, v2.FUTURE, hypothesis_id=hid, lineage=drv.LINEAGE, trial_universe=universe, variants_tested=None,
            parameters=v2.parameters_block({**common, **extra}), code_hash=drv.ENGINE_SHA256, data_source=src,
            data_period={"start": start_date, "end": end_date}, cost_model=cost,
            evaluation_method={"name": method, "sha256": factory.sha(method)},
            data_quality={"status": "NOT_CHECKED"},
            deviations=[{"date": "2026-11-12", "fields": ["trial_universe", "parameters", "data_source", "cost_model",
                                                          "evaluation_method"],
                         "description": "Ordre 101/102: familien er 96 tests (12 baseline + 84 filtrerede), N 19.849; "
                                        "afløser udkast 100's plan med univers 12 og N 19.765."}]))
    return recs


def register_counts(recs):
    """(tests covered by the records, universe sizes, reference Ns) for the review in order 102 point 4."""
    covered = 0
    for r in recs:
        vals = r["parameters"]["values"]
        covered += 1 if vals.get("combo") == "base" else vals["family_tests"]
    return {"covered": covered, "universe": sorted({r["trial_universe"]["size"] for r in recs}),
            "reference_n": sorted({r["parameters"]["values"]["reference_n"] for r in recs}),
            "members_sha256": sorted({r["trial_universe"]["members_sha256"] for r in recs})}


def file_sha256(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


__all__ = ["ForwardBookV2", "Trend1H", "report_v2", "v2_final_records", "register_counts", "test_ids", "file_sha256"]
