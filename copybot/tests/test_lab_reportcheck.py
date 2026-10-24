"""research/LINUX_DRIFT.md 2026-10-22: `lab report-verify` recomputes the daily lane report on its own and names every
deviation. A real lane account (fake market), the real report, then deliberate damage."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import lane, pipeline, reportcheck  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.test_lab_lane import Base, HOUR, NOW, market  # noqa: E402

DAY_ = "2026-10-20"                                     # NOW is 2026-10-20 02:30 UTC


def load(path):
    with open(path) as f:
        return json.load(f)


class ReportVerify(Base):
    def setUp(self):
        super().setUp()
        self.led = self.started()
        lane.run_one(self.db, self.led, market(), NOW)              # fills, funding-free, one mark

    def record(self):
        out = lane.report(self.db, DAY_)
        art = pipeline.save_artifact(lane.REPORT_DIR, DAY_, out)
        self.db.event("research.lane_report", "system:test", None,
                      {"day": DAY_, "accounts": len(out["accounts"]), "met": out["met"],
                       "net_total": out["net_total"], "decisional": False, "artifact_sha256": art["sha256"]})
        return os.path.join(pipeline.ARTIFACTS, lane.REPORT_DIR, f"{DAY_}.json")

    def run_check(self, day=DAY_):
        lines = []
        rc = reportcheck.main(self.db.path, day, out=lines.append, artifacts=pipeline.ARTIFACTS)
        return rc, {ln[8:].split(":")[0]: ln[3:5] == "OK" for ln in lines if ln.startswith("  [")}, lines

    def test_the_real_report_verifies(self):
        Risk(self.db, lambda: NOW + 60).pause(self.led, "data_fetch", None, None, "fixture")
        self.record()
        rc, rows, lines = self.run_check(None)                      # the latest report
        self.assertEqual((rc, lines[-1]), (0, "REPORT OK"), lines)
        self.assertTrue(rows[self.led])
        self.assertIn("pause: data_fetch", "\n".join(lines))
        self.assertTrue(any(r["equity"] != 10_000.0 for r in load(
            os.path.join(pipeline.ARTIFACTS, lane.REPORT_DIR, f"{DAY_}.json"))["accounts"]))   # it really traded

    def test_an_edited_file_is_caught(self):
        path = self.record()
        art = load(path)
        art["accounts"][0]["equity"] += 5
        with open(path, "w") as f:
            json.dump(art, f, sort_keys=True)
        rc, rows, lines = self.run_check()
        self.assertEqual(rc, 1)
        self.assertFalse(rows["report 2026-10-20"])                 # SHA-256 no longer the recorded one
        self.assertFalse(rows[self.led])
        self.assertIn("equity", next(ln for ln in lines if self.led in ln))
        self.assertEqual(lines[-1], "REPORT MISMATCH")

    def test_a_later_registry_change_and_a_missing_account_are_caught(self):
        self.record()
        self.db.append("sim_equity", exp_id=self.led, ts=int(NOW + HOUR), equity=9_900.0, cash=9_900.0, exposure=0.0,
                       peak=10_000.0, drawdown=0.01)               # a mark the report never saw, wrong cash too
        led2 = self.started(now=NOW + 2 * HOUR, key="k2", fn="carry_floor", params={"days": 7, "q": 0.8})
        rc, rows, lines = self.run_check()
        self.assertEqual(rc, 1)
        line = next(ln for ln in lines if self.led in ln)
        self.assertIn("equity", line)
        self.assertIn("marked cash 9900.0 vs replayed", line)
        self.assertFalse(rows["accounts are exactly the ones live that day"])
        self.assertIn(f"missing {led2}", "\n".join(lines))
        self.assertFalse(rows["net_total is the sum"])

    def test_the_report_job_verifies_its_report_and_records_the_outcome(self):
        """research/LINUX_DRIFT.md 2026-10-23: automatic, right after the report."""
        from lab import command
        path = self.record()
        p = lane.verify_report(self.db, DAY_, "report-1", artifacts=pipeline.ARTIFACTS)
        self.assertTrue(p["ok"], p)
        self.assertGreater(p["checks"], 3)
        rep = self.db.one("SELECT payload FROM events WHERE kind='research.lane_report' ORDER BY id DESC LIMIT 1")
        self.assertTrue(command._report_with_check(self.db, rep)["verified"]["ok"])
        art = load(path)
        art["net_total"] += 1
        with open(path, "w") as f:
            json.dump(art, f, sort_keys=True)
        p = lane.verify_report(self.db, DAY_, "report-1", artifacts=pipeline.ARTIFACTS)
        self.assertFalse(p["ok"])
        self.assertTrue(any(x.startswith("report 2026-10-20: artifact SHA-256") for x in p["failed"]))
        self.assertFalse(command._report_with_check(self.db, rep)["verified"]["ok"])      # the newest check counts
        with mock.patch("lab.reportcheck.checks", side_effect=OSError("disk")):
            p = lane.verify_report(self.db, DAY_, "report-1")
        self.assertEqual((p["ok"], p["failed"]), (False, ["check failed: OSError('disk')"]))

    def test_a_fill_better_than_mid_breaks_the_price_identity(self):          # amendment 21t
        mark_ts = self.db.one("SELECT MAX(ts) FROM sim_equity WHERE exp_id=?", self.led)[0]
        self.db.append("sim_orders", order_id="x1", exp_id=self.led, ts=mark_ts, instrument="BBBUSDT", side="buy",
                       qty=1.0, limit_px=None, style="maker", reduce_only=0, signal_ref=None, cost_model={})
        self.db.append("sim_fills", fill_id="x1|0", order_id="x1", exp_id=self.led, ts=mark_ts, instrument="BBBUSDT",
                       side="buy", px=99.0, qty=1.0, fee=0.0, slippage=None, liquidity="maker", mid=100.0, book_ts=None)
        self.record()
        rc, rows, lines = self.run_check()
        self.assertEqual(rc, 1)
        self.assertRegex("\n".join(lines), r"price/basis residual differs from the mid-based price P&L by [\d.]+ USD \(21t\)")

    def test_no_report_is_a_failure(self):
        rc, rows, lines = self.run_check()
        self.assertEqual((rc, rows), (1, {"a recorded report": False}))


if __name__ == "__main__":
    unittest.main()
