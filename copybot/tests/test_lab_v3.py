"""PROTOCOL v3 (research/PROTOCOL_V3.md): eight families on new data types, their parsers, end-to-end pipeline runs on
a synthetic 2022-2023 market, the holdout rules and the paper refusal. No network."""
import csv
import io
import json
import math
import os
import random
import shutil
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import fleet, jobs, lifecycle, paper_runner, pipeline, registry, templates  # noqa: E402
from lab.db import DB  # noqa: E402
from tests.lab_fixtures import frozen  # noqa: E402
from lab.engine import adversarial, catalogue, data  # noqa: E402

HOUR, DAY = 3600, 86400
V3 = [t for t, x in catalogue.TEMPLATES.items() if x.get("protocol") == 3]


def synthetic(symbols, t0, days, seed=5):
    """Bars, funding and a full v3 bundle with planted structure so every family takes positions."""
    rng = random.Random(seed)
    n = days * 24
    bars, funding, vol, tak, met = {}, {}, {}, {}, {}
    for j, s in enumerate(symbols):
        px, b, v, k = 100.0, [], {}, {}
        for i in range(n):
            o = px
            px *= 1 + rng.gauss(0.00004 * ((j % 7) - 3), 0.004 + 0.0004 * (j % 9))
            ts = t0 + i * HOUR
            b.append((ts, o, px))
            v[ts] = 1e6 * (1 + j) * (1 + rng.random()) * (4 if (i // 24) % 17 == j % 17 else 1)
            k[ts] = v[ts] * (0.45 + 0.1 * rng.random())
        bars[s], vol[s], tak[s] = b, v, k
        funding[s] = {t0 + i * 8 * HOUR: rng.gauss(0.0001, 0.0003) for i in range(n // 8)}
        oi = 1e8 * (1 + j)
        m = {}
        for d in range(days):
            oi *= 1 + rng.gauss(0.001 * ((j % 5) - 2), 0.03)
            m[t0 + d * DAY] = {"oi": oi, "top": math.exp(rng.gauss(0.1 * ((j % 3) - 1), 0.2)),
                               "acct": math.exp(rng.gauss(0, 0.2)), "rows": 288}
        met[s] = m
    dvol = {c: {t0 + d * DAY: 40 + 25 * abs(math.sin(d / 9)) + rng.random() * 5 for d in range(days)}
            for c in ("BTC", "ETH")}
    stable = {}
    sup = 1.3e11
    for d in range(days):
        sup *= 1 + 0.002 * math.sin(d / 11) + rng.gauss(0, 0.0005)
        stable[t0 + d * DAY] = sup
    rates, r = {}, 0.5
    for d in range(days):
        day = t0 + d * DAY
        r += 0.02 * math.sin(d / 23) + rng.gauss(0, 0.01)
        if datetime.fromtimestamp(day, timezone.utc).weekday() < 5:
            rates[day] = r
    cm = {"SplyCur": {}, "CapMVRVCur": {}}
    for j, s in enumerate(symbols):
        sup, mv = 1e9 * (1 + j), 1.0 + 0.1 * j
        cm["SplyCur"][s], cm["CapMVRVCur"][s] = {}, {}
        for d in range(days):
            sup *= 1 + 0.0002 * (j % 6) + rng.gauss(0, 0.0001)
            mv = max(0.2, mv * (1 + rng.gauss(0, 0.02)))
            cm["SplyCur"][s][t0 + d * DAY] = sup
            cm["CapMVRVCur"][s][t0 + d * DAY] = mv
    return bars, funding, {"volume": vol, "taker": tak, "metrics": met, "dvol": dvol, "stable": stable,
                           "rates": rates, "cm": cm}


class Families(unittest.TestCase):
    def test_every_v3_family_takes_positions_and_ignores_the_future(self):
        t0 = int(datetime(2022, 1, 3, tzinfo=timezone.utc).timestamp())          # a Monday
        for name in V3:
            tpl = catalogue.TEMPLATES[name]
            syms = catalogue.universe(name)
            bars, funding, bundle = synthetic(syms, t0, 200)
            fam = pipeline._family(name)
            for params in tpl["grid"]:
                full = fam(bars, funding, params, None, bundle)
                self.assertTrue(any(any(full[s]) for s in full), f"{name} {params} never takes a position")
                ref = syms[0]
                for cut_i in (24 * 20, 24 * 75, 24 * 120 + 7, 24 * 170):
                    cut = bars[ref][cut_i][0]
                    pb = {s: [(ts, o, c) if ts <= cut else (ts, o * 1000, c * 1000) for ts, o, c in b]
                          for s, b in bars.items()}
                    pf = {s: {k: (v if k <= cut else 1.0) for k, v in f.items()} for s, f in funding.items()}
                    got = fam(pb, pf, params, None, adversarial.cut_bundle(bundle, cut, poison=True))
                    for s in bars:
                        self.assertEqual(full[s][:cut_i + 1], got[s][:cut_i + 1],
                                         f"{name} {params} looks ahead on {s} (cut {cut_i})")

    def test_adversarial_harness_handles_the_bundle(self):
        t0 = int(datetime(2022, 1, 3, tzinfo=timezone.utc).timestamp())
        bars, funding, bundle = synthetic(catalogue.universe("smart_vs_crowd"), t0, 120)
        fam = pipeline._family("smart_vs_crowd")
        p = catalogue.TEMPLATES["smart_vs_crowd"]["grid"][0]
        self.assertTrue(adversarial.truncation_test_xs(fam, bars, funding, p, 5, volume_by=bundle)["ok"])
        self.assertTrue(adversarial.poison_test_xs(fam, bars, funding, p, volume_by=bundle)["ok"])

    def test_a_leaking_family_is_caught(self):
        """The poison test must catch use of a day that is not closed yet."""
        t0 = int(datetime(2022, 1, 3, tzinfo=timezone.utc).timestamp())
        bars, funding, bundle = synthetic(catalogue.universe("stablecoin_flow"), t0, 120)

        def leaky(b, f, p, fit=None, volume_by=None):           # reads today's value (not closed yet)
            st = volume_by["stable"]
            out = {}
            for s, rows in b.items():
                out[s] = [1.0 if st.get(ts - ts % DAY, 0) > st.get(ts - ts % DAY - DAY, 0) else 0.0 for ts, _, _ in rows]
            return out
        self.assertFalse(adversarial.poison_test_xs(leaky, bars, funding, {}, volume_by=bundle)["ok"])


class Observation(unittest.TestCase):
    """research/PROTOCOL_V3.md amendment 2: forward test for ideas that pass everything except the luck check."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labobs")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.p = [mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                  mock.patch.object(pipeline, "REPORTS", os.path.join(self.tmp, "reports"))]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _screened(self, eid, template, gates, observation=True):
        spec = {**pipeline.template_spec(template), "observation_test": observation}
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="m", fingerprint=eid,
                       spec_json=spec)
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="SCREENING", actor="fixture",
                       reason="fixture: screening done")
        net = {"net_sharpe_ann": 1.0, "gross_sharpe_ann": 1.1, "net_total": 0.1}
        pipeline.save_artifact(eid, "cost", {"variants": [{"variant": 0, "params": {}, "net": net, "net_2x_costs": net}],
                                             "benchmark": {"net_sharpe_ann": 0.5}, "selected": 0,
                                             "rejected_early": False})
        pipeline.save_artifact(eid, "adversarial", {"ok": True, "pre_validation_ok": True, "placebo": {"p": 0.01}})
        pipeline.save_artifact(eid, "validate", {"metrics": net, "benchmark": net, "dsr": 0.4, "gates": gates})

    def test_only_the_luck_check_failing_leads_to_observation_with_a_scheduled_forward_test(self):
        gates = {"net_mean_daily > 0": True, "one-sided 90% lower bound > 0": True, "net Sharpe > buy-and-hold": True,
                 "net total > 0 at 2x costs": True, "deflated Sharpe probability >= 0.95": False,
                 "adversarial checks pass": True, "validation data quality": True}
        self._screened("E_obs_a", "real_rate_filter", gates)
        r = pipeline.step_report(self.db, {"exp_id": "E_obs_a"}, "report-1")
        self.assertEqual(r["state"], "OBSERVATION")
        self.assertTrue(r["verdict"].startswith("OBSERVE"))
        ev = json.loads(self.db.one("SELECT payload FROM events WHERE kind='observation.started'")[0])
        self.assertGreaterEqual(ev["start"], data.FORWARD_MIN)
        j = jobs.get(self.db, "observe|E_obs_a")
        self.assertEqual(j["status"], "queued")
        self.assertEqual(j["next_run"], ev["end"] + data.FORWARD_LAG_S)            # not claimable before
        self.assertIsNone(jobs.claim(self.db, "validation-1", ["observe"]))
        # an idea that also fails another gate is rejected, and one without the observation flag is rejected too
        gates2 = dict(gates, **{"net Sharpe > buy-and-hold": False})
        self._screened("E_obs_b", "real_rate_filter", gates2)
        self.assertEqual(pipeline.step_report(self.db, {"exp_id": "E_obs_b"}, "report-1")["state"], "REJECTED")
        self._screened("E_obs_c", "real_rate_filter", gates, observation=False)
        self.assertEqual(pipeline.step_report(self.db, {"exp_id": "E_obs_c"}, "report-1")["state"], "REJECTED")

    def test_the_forward_window_cannot_be_read_before_it_ends(self):
        split = data.forward_split(data.FORWARD_MIN)
        a, b = data.window_bounds(split)
        with self.assertRaises(data.ReservedData):
            data.window(split, now=b)                                         # ended, but not past the lag
        self.assertEqual(data.window(split, now=b + data.FORWARD_LAG_S + 1), (a, b))
        with self.assertRaises(data.ReservedData):                           # 2025 stays reserved
            data.window(data.forward_split(int(datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp())), now=2e9)

    def test_gateway_allows_forward_reads_only_in_observation_or_paper(self):
        from lab.data import AccessRefused, Gateway
        f = os.path.join(self.tmp, "x.bin")
        with open(f, "wb") as fh:
            fh.write(b"x")
        for st, ok in (("SCREENING", False), ("OBSERVATION", True)):
            eid = f"E_gw_{st}"
            self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="m", fingerprint=eid,
                           spec_json={})
            self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=st, actor="fixture",
                           reason="fixture: gateway rule test")
            g = Gateway(self.db, "system:t")
            if ok:
                g.access(eid, "forward", [f], (1, 2), "test", "evaluate", "c")
            else:
                with self.assertRaises(AccessRefused):
                    g.access(eid, "forward", [f], (1, 2), "test", "evaluate", "c")


class Parsers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labv3p")
        self.p = mock.patch.object(data, "CACHE", self.tmp)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_metrics_zip_parsing_and_consolidation(self):
        def get(url):
            day = url.rsplit("-metrics-", 1)[1][:10]
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["create_time", "symbol", "sum_open_interest", "sum_open_interest_value",
                        "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio", "count_long_short_ratio",
                        "sum_taker_long_short_vol_ratio"])
            for k in range(288 if day != "2022-01-05" else 50):              # one thin day
                w.writerow([f"{day} {k * 5 // 60:02d}:{k * 5 % 60:02d}:00", "XUSDT", 1, 1000 + k, 1.1, 1.5, 0.9, 1])
            z = io.BytesIO()
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("x.csv", buf.getvalue())
            return z.getvalue()
        with mock.patch.dict(data.SPLITS, {"tiny": ((2022, 1), (2022, 1))}):
            path = data.metrics_for("XUSDT", "tiny", get=get)
            days = data.load_metrics(path)
            self.assertEqual(len(days), 31)
            d1 = days[int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())]
            self.assertEqual((d1["oi"], d1["rows"]), (1287, 288))                # last value of the day
            self.assertAlmostEqual(d1["top"], 1.5)
            self.assertAlmostEqual(d1["acct"], 0.9)
            self.assertEqual(days[int(datetime(2022, 1, 5, tzinfo=timezone.utc).timestamp())]["rows"], 50)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(len(json.load(f)["manifest"]), 31)              # SHA-256 per source file

    def test_dvol_pages_and_stays_inside_the_window(self):
        a, b = data.window("validation3")
        calls = []

        def get(url):
            calls.append(url)
            end = int(url.split("end_timestamp=")[1].split("&")[0]) // 1000
            start = max(a, end - 100 * DAY)
            rows = [[(d) * 1000, 1, 1, 1, 50.0 + d % 7] for d in range(start - start % DAY, end, DAY)]
            return json.dumps({"result": {"data": rows, "continuation": start * 1000 if start > a else None}}).encode()
        path = data.dvol_for("BTC", "validation3", get=get)
        days = data.load_days(path)
        self.assertGreater(len(calls), 1)                                     # paged
        self.assertEqual(min(days), a)
        self.assertLessEqual(max(days), b)
        self.assertTrue(all(f"start_timestamp={a * 1000}" in c for c in calls))

    def test_stablecoin_history_is_clipped_to_the_window_before_storing(self):
        a, b = data.window("train3")
        reserved = int(datetime(2025, 3, 1, tzinfo=timezone.utc).timestamp())
        rows = [{"date": str(d), "totalCirculatingUSD": {"peggedUSD": 1e11 + d}} for d in range(a - 400 * DAY, reserved, DAY)]
        path = data.stable_for("train3", get=lambda url: json.dumps(rows).encode())
        days = data.load_days(path)
        self.assertEqual(min(days), a)
        self.assertLessEqual(max(days), b)
        with open(path, encoding="utf-8") as f:
            self.assertNotIn(str(reserved - DAY), f.read())                     # nothing from 2025 is stored

    def test_fred_and_coinmetrics_requests_are_bounded_to_the_window(self):
        a, b = data.window("validation3")
        urls = []

        def fred(url):
            urls.append(url)
            return ("observation_date,DFII10\n2023-07-03,1.6\n2023-07-04,.\n2023-07-05,1.7\n2024-02-01,9.9\n").encode()
        days = data.load_days(data.fred_for("DFII10", "validation3", get=fred))
        self.assertIn("cosd=2023-07-01", urls[0])
        self.assertIn("coed=2023-12-31", urls[0])
        self.assertEqual(sorted(days.values()), [1.6, 1.7])                    # '.' skipped, 2024 row dropped

        pages = []

        def cmget(url):
            pages.append(url)
            if len(pages) == 1:
                return json.dumps({"data": [{"asset": "ada", "time": "2023-07-01T00:00:00.000000000Z", "SplyCur": "5"}],
                                   "next_page_url": "https://next"}).encode()
            return json.dumps({"data": [{"asset": "ada", "time": "2023-07-02T00:00:00.000000000Z", "SplyCur": "6"},
                                        {"asset": "ada", "time": "2025-01-02T00:00:00.000000000Z", "SplyCur": "99"}]}).encode()
        with mock.patch.object(data, "_get_json", lambda url, get=None: json.loads(cmget(url))):
            per = data.load_cm(data.cm_for("SplyCur", "validation3", ["ADAUSDT"]))
        self.assertIn("start_time=2023-07-01", pages[0])
        self.assertIn("end_time=2023-12-31", pages[0])
        self.assertEqual(sorted(per["ADAUSDT"].values()), [5.0, 6.0])

    def test_reserved_windows_are_refused(self):
        with mock.patch.dict(data.SPLITS, {"late": ((2025, 1), (2025, 2))}):
            for fn in (lambda: data.stable_for("late", get=lambda u: b"[]"),
                       lambda: data.dvol_for("BTC", "late", get=lambda u: b"{}"),
                       lambda: data.metrics_for("XUSDT", "late", get=lambda u: b"")):
                with self.assertRaises(data.ReservedData):
                    fn()


def write_market(root, symbols, years=(2022, 2023), seed=9):
    """Monthly kline (with volume and taker columns) and funding zips in Binance layout."""
    rng = random.Random(seed)
    a = int(datetime(years[0], 1, 1, tzinfo=timezone.utc).timestamp())
    b = int(datetime(years[-1] + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    for j, sym in enumerate(symbols):
        px, by_month, fund = 100.0, {}, {}
        for ts in range(a, b, HOUR):
            o = px
            px *= 1 + rng.gauss(0.00002 * ((j % 5) - 2), 0.005)
            d = datetime.fromtimestamp(ts, timezone.utc)
            qv = 1e6 * (1 + j) * (1 + rng.random())
            by_month.setdefault((d.year, d.month), []).append(
                [ts * 1000, o, max(o, px), min(o, px), px, 1, ts * 1000 + 3599999, qv, 10, 0.5, qv * (0.45 + 0.1 * rng.random()), 0])
            if ts % (8 * HOUR) == 0:
                fund.setdefault((d.year, d.month), []).append([ts * 1000, 8, rng.gauss(0.0001, 0.0002)])
        for (y, m), rows in by_month.items():
            _zip(os.path.join(root, "klines", f"{sym}-1h-{y}-{m:02d}.zip"), rows)
            _zip(os.path.join(root, "funding", f"{sym}-fundingRate-{y}-{m:02d}.zip"), fund[(y, m)])


def _dump(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _zip(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["h"])
    w.writerows(rows)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("x.csv", buf.getvalue())


class EndToEnd(unittest.TestCase):
    market = None

    @classmethod
    def setUpClass(cls):
        cls.market = tempfile.mkdtemp(prefix="labv3m")
        write_market(cls.market, data.UNIVERSE_30_V3)
        t0 = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
        _, _, cls.bundle = synthetic(data.UNIVERSE_30_V3, t0, 730)
        for s, m in cls.bundle["metrics"].items():
            for split in ("train3", "validation3", "holdout"):
                a, b = data.window(split)
                p = os.path.join(cls.market, "metrics_daily", f"{s}-{split}.json")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                _dump(p, {"days": {str(d): v for d, v in m.items() if a <= d <= b}, "manifest": {}})
        for split in ("train3", "validation3"):
            a, b = data.window(split)
            for c in ("BTC", "ETH"):
                p = os.path.join(cls.market, "dvol", f"{c}-{split}.json")
                os.makedirs(os.path.dirname(p), exist_ok=True)
                _dump(p, {"days": {str(d): v for d, v in cls.bundle["dvol"][c].items() if a <= d <= b}})
            p = os.path.join(cls.market, "stable", f"all-{split}.json")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            _dump(p, {"days": {str(d): v for d, v in cls.bundle["stable"].items() if a <= d <= b}})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.market, ignore_errors=True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labv3e")
        self.db_path = os.path.join(self.tmp, "lab.db")
        self.db = DB(self.db_path)

        def no_net(*a, **k):
            raise AssertionError("network access in a test")
        self.patches = [mock.patch.object(data, "CACHE", self.market),
                        mock.patch.object(data, "_fetch", lambda url, path, get=None: path if os.path.exists(path) else None),
                        mock.patch.object(data, "_get_json", no_net),
                        mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                        mock.patch.object(pipeline, "REPORTS", os.path.join(self.tmp, "reports")),
                        mock.patch.object(pipeline, "PLACEBO_N", 5),
                        mock.patch.object(fleet, "PROCESSES", False),
                        mock.patch.object(fleet.control, "ram", lambda: {"total": 16e9, "free": 8e9, "load_pct": 50}),
                        mock.patch.object(templates, "catalogue_blob", lambda: "blob-test"),
                        mock.patch.object(registry, "last_commit", lambda path: "c0ffee"),
                        mock.patch.object(registry, "blob_at", lambda c, p: "blob-test")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_v3_batch_runs_to_a_registered_decision_on_v3_windows(self):
        self.db.append("experiments", exp_id="L20_m1_orderflow", version=1, created_ts=0,
                       mechanism_tag="orderflow_imbalance", fingerprint="l20", spec_json={"execution": "taker"})
        self.db.append("transitions", exp_id="L20_m1_orderflow", ts=0, from_state=None, to_state="REJECTED",
                       actor="fixture", reason="fixture: rejected order-flow idea")
        pipeline.discover_catalogue(self.db)
        self.assertEqual(lifecycle.state(self.db, "E_taker_pressure_p3"), "SUPPRESSED")     # graveyard: L20 tag
        for t in ("stablecoin_flow", "smart_vs_crowd", "vrp_timing"):
            code = templates.request(self.db, t, "human:test", "fixture approval for tests")
            templates.confirm(self.db, code, "human:test")
        fleet.strategy_pass(self.db)
        ag = [a for a in fleet.agents(self.db_path) if a.kinds]
        for _ in range(200):
            for a in ag:
                a(self.db)
            c = jobs.counts(self.db)
            if not (c["queued"] or c["running"] or c["blocked"]):
                break
        self.assertEqual(c["failed"], 0, c)
        for e in ("E_stablecoin_flow_p3", "E_smart_vs_crowd_p3", "E_vrp_timing_p3"):
            self.assertIn(lifecycle.state(self.db, e), ("REJECTED", "SCREEN_PASSED"))
            self.assertTrue(self.db.one("SELECT 1 FROM results WHERE exp_id=?", e))
            spec = json.loads(registry.latest(self.db, e)["spec_json"])
            self.assertEqual(spec["protocol_version"], 3)
            self.assertEqual(spec["datasets"]["splits"]["train"], ["2022-01", "2023-06"])
        # the windows read were the v3 ones: no 2023-08 train / 2023-09 validation boundaries, nothing from 2024+
        a3 = data.window("train3")[0]
        self.assertEqual(self.db.one("SELECT MIN(window_start) FROM datasets")[0], a3)
        self.assertLess(self.db.one("SELECT MAX(window_end) FROM datasets")[0], data.window("holdout")[0])
        b = pipeline.batch_of(self.db, "E_vrp_timing_p3")
        self.assertEqual(sorted(b["exp_ids"]), ["E_smart_vs_crowd_p3", "E_stablecoin_flow_p3", "E_vrp_timing_p3"])
        self.assertEqual(b["protocol_version"], 3)

    def test_holdout_rules(self):
        with self.assertRaises(pipeline.StepError):
            spec = {"template": "vrp_timing", "protocol_version": 3}
            with mock.patch.object(pipeline, "_spec", lambda db, eid: spec), \
                    mock.patch.object(lifecycle, "state", lambda db, eid: "VALIDATION"):
                pipeline.step_holdout(self.db, {"exp_id": "E_vrp_timing_p3"}, "t")
        self.assertEqual(set(data.HOLDOUT_SEEN), {"BTCUSDT", "ETHUSDT", "SOLUSDT"})

    def test_paper_runner_refuses_v3_templates_without_live_inputs(self):
        eid = "E_smart_vs_crowd_p3"
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="m", fingerprint="f",
                       spec_json={"template": "smart_vs_crowd"})
        from tests.lab_fixtures import approve_paper
        approve_paper(self.db, eid)
        with mock.patch("lab.promotion.supervisor_ok", lambda db, now=None: True):
            r = paper_runner.run(self.db, lambda url: (_ for _ in ()).throw(AssertionError("no fetch")), 1.8e9)
        self.assertEqual(r["results"][eid]["status"], "unsupported")
        self.assertIsNone(self.db.one("SELECT 1 FROM events WHERE kind='paper.started'"))   # no ledger opened
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM sim_orders")[0], 0)


class ForwardEvaluation(unittest.TestCase):
    """step_observe end to end on a synthetic 2026-27 market: refused before the window ends, decided after it."""

    @classmethod
    def setUpClass(cls):
        cls.market = tempfile.mkdtemp(prefix="labfwd")
        write_market(cls.market, data.UNIVERSE_30_V3, years=(2026, 2027))
        cls.split = data.forward_split(data.FORWARD_MIN)
        a, b = data.window_bounds(cls.split)
        os.makedirs(os.path.join(cls.market, "fred"), exist_ok=True)
        rates = {str(d): 1.5 - 0.002 * ((d - a) // DAY) for d in range(a, b, DAY)
                 if datetime.fromtimestamp(d, timezone.utc).weekday() < 5}
        _dump(os.path.join(cls.market, "fred", f"DFII10-{cls.split}.json"), {"days": rates})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.market, ignore_errors=True)

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labfwde")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        a, b = data.window_bounds(self.split)
        self.after = b + data.FORWARD_LAG_S + 1
        self.patches = [mock.patch.object(data, "CACHE", self.market),
                        mock.patch.object(data, "_fetch", lambda url, path, get=None: path if os.path.exists(path) else None),
                        mock.patch.object(pipeline, "ARTIFACTS", os.path.join(self.tmp, "artifacts")),
                        mock.patch.object(pipeline, "REPORTS", os.path.join(self.tmp, "reports")),
                        mock.patch.object(registry, "last_commit", lambda path: "c0ffee"),
                        mock.patch.object(registry, "blob_at", lambda c, p: "blob-test")]
        for x in self.patches:
            x.start()
        eid = self.eid = "E_real_rate_filter_p3"
        self.db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="real_rate_timing",
                       fingerprint="f", spec_json={**pipeline.template_spec("real_rate_filter")})
        self.db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="OBSERVATION", actor="fixture",
                       reason="fixture: entered observation")
        self.db.event("observation.started", "system:t", eid, {"window": self.split, "start": a, "end": b})
        frozen(self.db, eid, "cost", {"selected": 0})
        frozen(self.db, eid, "backtest", {"variants": [{"variant": 0, "params": {"n": 20}, "fit": None,
                                                               "positions": {}}]})
        self.job = {"exp_id": eid, "payload": {"start": a, "months": 6}}

    def tearDown(self):
        for x in self.patches:
            x.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_refused_before_the_window_ends(self):
        with mock.patch.object(data, "CLOCK", lambda: self.after - data.FORWARD_LAG_S):
            with self.assertRaises(data.ReservedData):
                pipeline.step_observe(self.db, self.job, "validation-1")
        self.assertEqual(lifecycle.state(self.db, self.eid), "OBSERVATION")
        self.assertIsNone(self.db.one("SELECT 1 FROM datasets"))                 # nothing was read

    def test_decided_after_the_window_with_a_recorded_result(self):
        with mock.patch.object(data, "CLOCK", lambda: self.after):
            r = pipeline.step_observe(self.db, self.job, "validation-1")
        self.assertIn(r["state"], ("SCREEN_PASSED", "REJECTED"))
        self.assertEqual(lifecycle.state(self.db, self.eid), r["state"])
        res = self.db.one("SELECT label, verdict, metrics FROM results WHERE exp_id=?", self.eid)
        self.assertEqual(res["label"], "VALIDATION")
        self.assertTrue(res["verdict"].startswith(("PASS (forward test)", "FAIL (forward test)")))
        self.assertEqual(json.loads(res["metrics"])["cohort"], 1)
        splits = {x[0] for x in self.db.q("SELECT DISTINCT split FROM datasets")}
        self.assertEqual(splits, {"forward"})
        a, b = data.window_bounds(self.split)
        self.assertEqual(self.db.one("SELECT MIN(window_start), MAX(window_end) FROM datasets")[:], (a, b))


if __name__ == "__main__":
    unittest.main()
