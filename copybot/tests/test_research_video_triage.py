"""Director order 58 P1: the offline video-claim triage tool validates claim records, classifies them with fixed rules,
computes the DIAGNOSTIC_ONLY luck bar and the lot/notional red flag, reads the factory register read-only, refuses
URLs and never imports network, sqlite or lab code."""
import ast
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from research.tools import video_triage as vt  # noqa: E402

SRC = os.path.join(HERE, "research", "tools", "video_triage.py")
SHA = "ab" * 32


def full_record(cid="T01"):
    """A complete, REPLICABLE record: every element OBSERVED."""
    r = vt.skeleton(cid, "@test / synthetic", SHA)
    r["claims"] = {"performance_claimed": True, "trading_rule_claimed": True}
    r["observed_facts"] = [{"at": 12, "quote": "long above the range high", "fact": "entry rule"},
                           {"at": "f004.png", "quote": "stop at range low", "fact": "stop rule"}]
    r["assumptions"] = [{"label": "ASSUMPTION", "text": "chart time is UTC"}]
    r["rule_checklist"] = {k: {"status": "OBSERVED", "note": "synthetic"} for k in vt.CHECKLIST}
    r["performance"] = {"numbers": ["+10 %"], "trades_shown": 3, "account": "SIM"}
    r["classification"] = "REPLICABLE"
    return r


def sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Schema(unittest.TestCase):
    def test_skeleton_and_full_record_are_valid(self):
        self.assertEqual(vt.validate(vt.skeleton("X1", "src", SHA)), [])
        self.assertEqual(vt.validate(full_record()), [])

    def test_missing_fields_are_named(self):
        r = full_record()
        del r["selection"]
        del r["rule_checklist"]["stop"]
        del r["performance"]["account"]
        del r["observed_facts"][0]["quote"]
        errs = vt.validate(r)
        for want in ("missing field: selection", "missing field: rule_checklist.stop",
                     "missing field: performance.account", "missing field: observed_facts[0].quote"):
            self.assertIn(want, errs)

    def test_bad_values_give_clear_errors(self):
        r = full_record()
        r["rule_checklist"]["market"]["status"] = "YES"
        r["observed_facts"][0]["quote"] = " ".join(["w"] * 16)
        r["observed_facts"][1]["at"] = "later"
        r["assumptions"][0]["label"] = "GUESS"
        r["performance"]["account"] = "LIVE"
        r["video_sha256"] = "xyz"
        r["extra"] = 1
        r["red_flags"]["standard"]["lead_generation"] = "yes"
        errs = "\n".join(vt.validate(r))
        for want in ("rule_checklist.market.status must be one of OBSERVED/PARTIAL/UNKNOWN",
                     "observed_facts[0].quote has 16 words (max 15)", "observed_facts[1].at must be seconds",
                     "assumptions[0].label must be ASSUMPTION or UNKNOWN", "performance.account must be one of",
                     "video_sha256 must be 64 lowercase hex", "unknown field: extra",
                     "red_flags.standard.lead_generation must be true, false or null"):
            self.assertIn(want, errs)

    def test_quote_of_exactly_15_words_is_allowed(self):
        r = full_record()
        r["observed_facts"][0]["quote"] = " ".join(["w"] * 15)
        self.assertEqual(vt.validate(r), [])

    def test_stored_classification_must_match(self):
        r = full_record()
        r["classification"] = "PARTIAL"
        with tempfile.TemporaryDirectory() as d:
            reg = os.path.join(d, "registry.json")
            with open(reg, "w") as f:
                json.dump({"records": []}, f)
            ev = vt.evaluate(r, reg)
            self.assertIn("stored classification PARTIAL != computed REPLICABLE", ev["errors"])
            r["classification"] = "PENDING"
            ev = vt.evaluate(r, reg)
            self.assertEqual(ev["errors"], [])
            self.assertIn("classification PENDING; computed REPLICABLE", ev["warnings"])

    def test_seed_records_are_valid_and_classified_as_stored(self):
        names = sorted(n for n in os.listdir(vt.CLAIMS_DIR) if n.endswith(".json"))
        want = {f"V{i:02d}.json" for i in range(1, 11)} | {"FOMO.json", "EDWARD.json"}
        self.assertTrue(want <= set(names), want - set(names))
        for n in names:
            rec = vt.load(os.path.join(vt.CLAIMS_DIR, n))
            self.assertEqual(vt.validate(rec), [], n)
            self.assertEqual(vt.classify(rec)[0], rec["classification"], n)
        self.assertEqual(vt.load(os.path.join(vt.CLAIMS_DIR, "EDWARD.json"))["classification"],
                         "NOT_REPLICABLE_FROM_VIDEO")                    # as ORB15_VIDEO_RULE_AUDIT.md section 3


class Classification(unittest.TestCase):
    def test_replicable_ignores_costs(self):
        r = full_record()
        r["rule_checklist"]["costs"]["status"] = "UNKNOWN"
        self.assertEqual(vt.classify(r)[0], "REPLICABLE")

    def test_each_core_element_triggers_not_replicable(self):
        for k in vt.CORE:
            for st in ("UNKNOWN", "PARTIAL"):
                r = full_record()
                r["rule_checklist"][k]["status"] = st
                cls, reasons = vt.classify(r)
                self.assertEqual(cls, "NOT_REPLICABLE_FROM_VIDEO", (k, st))
                self.assertIn(f"core element not observed: {k}={st}", reasons)

    def test_non_core_gap_is_partial(self):
        for k in set(vt.CHECKLIST) - set(vt.CORE) - {"costs"}:
            r = full_record()
            r["rule_checklist"][k]["status"] = "PARTIAL"
            self.assertEqual(vt.classify(r)[0], "PARTIAL", k)

    def test_no_claim_wins(self):
        r = full_record()
        r["claims"] = {"performance_claimed": False, "trading_rule_claimed": False}
        self.assertEqual(vt.classify(r)[0], "NO_TRADING_CLAIM")
        r["rule_checklist"]["stop"]["status"] = "UNKNOWN"
        self.assertEqual(vt.classify(r)[0], "NO_TRADING_CLAIM")
        for claims in ((True, False), (False, True)):
            r["claims"] = {"performance_claimed": claims[0], "trading_rule_claimed": claims[1]}
            self.assertEqual(vt.classify(r)[0], "NOT_REPLICABLE_FROM_VIDEO")


class LuckBar(unittest.TestCase):
    def test_fvllport_value(self):
        self.assertAlmostEqual(vt.luck_bar(24, 2.9), 1.16, delta=0.01)

    def test_monotone_in_n_and_decreasing_in_t(self):
        bars = [vt.luck_bar(n, 2.9) for n in (1, 2, 5, 10, 24, 100, 1000, 10 ** 6)]
        self.assertEqual(bars[0], 0.0)
        self.assertTrue(all(a < b for a, b in zip(bars, bars[1:])), bars)
        ts = [vt.luck_bar(24, t) for t in (0.5, 1, 2, 2.9, 5, 10, 30)]
        self.assertTrue(all(a > b for a, b in zip(ts, ts[1:])), ts)

    def test_diagnostic_only_output(self):
        d = vt.luck_diagnostic({"strategies_tried_n": 24, "backtest_years_t": 2.9, "stated_sharpe": 1.46})
        self.assertEqual(d["status"], "DIAGNOSTIC_ONLY")
        self.assertAlmostEqual(d["luck_bar"], 1.1626, places=3)
        self.assertAlmostEqual(d["sr_minus_luck_bar"], 0.2974, places=3)
        self.assertIn("not a statistical test", d["note"])
        self.assertIn("iid trials", d["assumptions"])
        d = vt.luck_diagnostic({"strategies_tried_n": None, "backtest_years_t": 2.9, "stated_sharpe": 1.46})
        self.assertEqual((d["status"], d["luck_bar"], d["sr_minus_luck_bar"]), ("DIAGNOSTIC_ONLY", None, None))

    def test_bad_inputs_raise(self):
        for n, t in ((0, 1), (2.5, 1), (True, 1), (10, 0), (10, -1)):
            with self.assertRaises(ValueError):
                vt.luck_bar(n, t)


class Notional(unittest.TestCase):
    def test_gold_mobile_bot(self):
        r = vt.notional_check(6, 5.46, 100, 5026, 1731.87)
        self.assertAlmostEqual(r["notional"], 16.5e6, delta=0.1e6)
        self.assertGreater(r["leverage"], 1000 * 5)
        self.assertTrue(r["flag"])

    def test_normal_position_is_not_flagged(self):
        self.assertFalse(vt.notional_check(1, 0.01, 100, 5026, 1731.87)["flag"])  # ~$5k notional, ~2.9x

    def test_seed_v05_flags_impossible_notional(self):
        rec = vt.load(os.path.join(vt.CLAIMS_DIR, "V05.json"))
        self.assertTrue(vt.computed_flags(rec)["impossible_notional"])


class Extract(unittest.TestCase):
    def test_refuses_http_and_urls(self):
        for bad in ("http://example.com/v.mp4", "https://vm.tiktok.com/x", "HTTPS://X", "ftp://h/v.mp4",
                    "file:///tmp/v.mp4"):
            with self.assertRaises(ValueError):
                vt.extract(bad, tempfile.gettempdir())
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(vt.main(["extract", "--video", "https://x/v.mp4", "--out", "/nonexistent"]), 2)
        self.assertIn("refused", err.getvalue())

    def test_extract_on_synthetic_video(self):
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
            Gst.init(None)
        except (ImportError, ValueError):
            self.skipTest("GStreamer/PyGObject not available")
        enc = next((e for e in (("theoraenc", "oggmux"), ("x264enc", "mp4mux"))
                    if all(Gst.ElementFactory.find(x) for x in e)), None)
        if enc is None:
            self.skipTest("no local encoder to make a synthetic video")
        with tempfile.TemporaryDirectory() as d:
            video = os.path.join(d, "t.vid")
            p = Gst.parse_launch("videotestsrc num-buffers=30 ! video/x-raw,framerate=10/1,width=160,height=120 ! "
                                 f"videoconvert ! {enc[0]} ! {enc[1]} ! filesink name=out")
            p.get_by_name("out").set_property("location", video)
            p.set_state(Gst.State.PLAYING)
            msg = p.get_bus().timed_pop_filtered(30 * Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
            p.set_state(Gst.State.NULL)
            if msg is None or msg.type != Gst.MessageType.EOS or not os.path.getsize(video):
                self.skipTest("could not generate a synthetic video locally")
            out = os.path.join(d, "frames")
            m = vt.extract(video, out, every_s=1, width=80, timeout_s=60)
            self.assertGreaterEqual(m["frame_count"], 2)
            self.assertEqual(m["video_sha256"], sha_file(video))
            self.assertAlmostEqual(m["duration_s"], 3.0, delta=0.5)
            self.assertEqual(m["settings"]["every_s"], 1)
            self.assertEqual([f["t_s"] for f in m["frames"]], list(range(m["frame_count"])))
            with open(os.path.join(out, "manifest.json")) as f:
                self.assertEqual(json.load(f), m)
            with open(os.path.join(out, "f000.png"), "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
            with self.assertRaises(FileExistsError):                       # never mixes two runs in one dir
                vt.extract(video, out, every_s=1, width=80)


class NewCheckReport(unittest.TestCase):
    def test_new_creates_skeleton_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(vt.main(["new", "--id", "V99", "--source", "@x / y", "--video-sha256", SHA.upper(),
                                          "--dir", d]), 0)
            rec = vt.load(os.path.join(d, "V99.json"))
            self.assertEqual(vt.validate(rec), [])
            self.assertEqual((rec["video_sha256"], rec["classification"]), (SHA, "PENDING"))
            with redirect_stderr(io.StringIO()):
                self.assertEqual(vt.main(["new", "--id", "V99", "--source", "z", "--video-sha256", SHA,
                                          "--dir", d]), 2)
                self.assertEqual(vt.main(["new", "--id", "V98", "--source", "z", "--video-sha256", "abc",
                                          "--dir", d]), 2)

    def test_check_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "g.json")
            with open(good, "w") as f:
                f.write(vt.dump(full_record()))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(vt.main(["check", "--claim", good]), 0)
            self.assertIn("CLASSIFICATION: REPLICABLE", out.getvalue())
            bad = full_record()
            del bad["claims"]
            with open(good, "w") as f:
                f.write(vt.dump(bad))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(vt.main(["check", "--claim", good]), 1)
            self.assertIn("ERROR: missing field: claims", out.getvalue())

    def test_report_is_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, "a"), os.path.join(d, "b")
            os.makedirs(a)
            os.makedirs(b)
            recs = [full_record("V02"), full_record("V10"), full_record("ZED")]
            recs[1]["rule_checklist"]["stop"]["status"] = "UNKNOWN"
            recs[1]["classification"] = "NOT_REPLICABLE_FROM_VIDEO"
            for r in recs:                                            # write the two dirs in opposite orders
                with open(os.path.join(a, r["id"] + ".json"), "w") as f:
                    f.write(vt.dump(r))
            for r in reversed(recs):
                with open(os.path.join(b, r["id"] + ".json"), "w") as f:
                    f.write(vt.dump(r))
            ra, rb = vt.report(a), vt.report(b)
            self.assertEqual(ra.replace("`a`", "`x`"), rb.replace("`b`", "`x`"))
            self.assertEqual(ra, vt.report(a))
            rows = [ln.split(" | ")[0] for ln in ra.splitlines() if ln.startswith("| ") and not ln.startswith("| ID")]
            self.assertEqual(rows, ["| V02", "| V10", "| ZED"])          # V-numbers numerically, others after
            self.assertIn("REPLICABLE 2, NOT_REPLICABLE_FROM_VIDEO 1", ra)
            self.assertNotIn("Ugyldige", ra)
            with open(os.path.join(a, "BAD.json"), "w") as f:
                f.write("{}")
            self.assertIn("Ugyldige poster", vt.report(a))           # an invalid record is listed, never hidden

    def test_report_on_seeds_lists_all_twelve(self):
        text = vt.report(vt.CLAIMS_DIR)
        for cid in [f"V{i:02d}" for i in range(1, 11)] + ["FOMO", "EDWARD"]:
            self.assertIn(f"| {cid} |", text)
        self.assertNotIn("Ugyldige", text)
        self.assertIn("N=24, T=2.9 → 1.16", text)


class Registry(unittest.TestCase):
    def test_lookup_is_read_only_and_lists_matches(self):
        before = sha_file(vt.REGISTRY)
        mtime = os.stat(vt.REGISTRY).st_mtime_ns
        ids, unknown = vt.registry_matches(["copy_trading"], ["trend_following"])
        self.assertIn("L01_copy_kol", ids)
        self.assertIn("L03_sol_trend_hourly", ids)
        self.assertEqual(unknown, [])
        self.assertEqual(ids, sorted(ids))
        _, unknown = vt.registry_matches(["no_such_lineage"], [])
        self.assertEqual(unknown, ["lineage:no_such_lineage"])
        self.assertEqual(vt.registry_matches([], []), ([], []))
        for n in sorted(os.listdir(vt.CLAIMS_DIR)):
            if n.endswith(".json"):
                vt.evaluate(vt.load(os.path.join(vt.CLAIMS_DIR, n)))
        self.assertEqual(sha_file(vt.REGISTRY), before)
        self.assertEqual(os.stat(vt.REGISTRY).st_mtime_ns, mtime)

    def test_fill_prior_writes_only_the_claim(self):
        with tempfile.TemporaryDirectory() as d:
            reg = os.path.join(d, "registry.json")
            with open(reg, "w") as f:
                json.dump({"records": [{"id": "L1", "lineage": "copy_trading", "mechanism_tag": "copy_trading"},
                                       {"id": "L2", "lineage": "other", "mechanism_tag": "x"}]}, f)
            rb = sha_file(reg)
            r = full_record()
            r["lab_prior"]["lineages"] = ["copy_trading"]
            p = os.path.join(d, "c.json")
            with open(p, "w") as f:
                f.write(vt.dump(r))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(vt.main(["check", "--claim", p, "--registry", reg]), 0)
            self.assertIn("WARNING: lab_prior.matches differ", out.getvalue())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(vt.main(["check", "--claim", p, "--registry", reg, "--fill-prior"]), 0)
            self.assertEqual(vt.load(p)["lab_prior"]["matches"], ["L1"])
            self.assertEqual(sha_file(reg), rb)


class Purity(unittest.TestCase):
    ALLOW = {"__future__", "argparse", "hashlib", "json", "math", "os", "re", "statistics", "sys"}
    BANNED = {"socket", "urllib", "requests", "sqlite3", "http", "lab", "subprocess", "importlib", "ssl", "ftplib"}

    def test_imports(self):
        with open(SRC, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        top, lazy = set(), {}
        for node in tree.body:
            if isinstance(node, ast.Import):
                top |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                top.add((node.module or "").split(".")[0])
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
            for node in ast.walk(fn):
                if isinstance(node, ast.Import):
                    lazy.setdefault(fn.name, set()).update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom):
                    lazy.setdefault(fn.name, set()).add((node.module or "").split(".")[0])
        self.assertTrue(top <= self.ALLOW, top - self.ALLOW)
        self.assertEqual(lazy, {"extract": {"gi"}})                      # GStreamer only, only inside extract
        every = top | set().union(*lazy.values())
        self.assertFalse(every & self.BANNED)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | \
                {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertFalse(names & {"__import__", "urlopen", "connect", "import_module", "system", "popen"})

    def test_module_import_does_not_load_gstreamer(self):
        self.assertNotIn("gi", vt.__dict__)


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
