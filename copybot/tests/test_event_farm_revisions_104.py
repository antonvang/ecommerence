"""Director decision 104: a revised bar never changes anything already booked. The first stored value is kept, the
revision goes to the conflict log, and nothing is recomputed backwards, also after a restart. Synthetic bars only;
the adapter path uses the loopback fake exchange of test_event_farm_source. Also checks the final text 104."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))

from research.tools import event_farm as ef  # noqa: E402
from research.tools import event_farm_forward as fw  # noqa: E402
from research.tools import event_farm_forward_v2 as fv  # noqa: E402
from research.tools import event_farm_source as src  # noqa: E402

BS = 300
T0 = ef.START
SYMS = ["SYN1", "SYN2"]
CFG = {"warmup_bars": 50, "coverage_window_bars": 40}
AMEND = os.path.join(HERE, "research", "desk", "EVENT_FARM_FORWARD_AMENDMENT_FINAL_104.md")


def revised(b, f=1.05):
    """Same ts, other values (still a valid bar): a revision."""
    return (b[0], b[1], b[2] * f, b[3] / f, b[4], b[5] + 7.0)


def without_conflicts(dump):
    return {k: v for k, v in dump.items() if k != "conflicts"}


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bars = {"SYN1": ef.random_walk_bars(71, 2), "SYN2": ef.random_walk_bars(72, 2)}
        self.n = len(self.bars["SYN1"])

    def book(self, name):
        s, now = fw.SyntheticSource(), [0]
        b = fv.ForwardBookV2(os.path.join(self.tmp.name, f"event_farm_forward_{name}.db"), s, SYMS,
                             clock=lambda: now[0], config=CFG)
        return b, s, now

    def feed(self, b, s, now, k0, k1, hold=None):
        for k in range(k0, k1):
            for sym in SYMS:
                if hold is None or (sym, k) not in hold:
                    s.publish(sym, [self.bars[sym][k]])
            now[0] = self.bars["SYN1"][k][0] + BS
            b.step()

    def test_revisions_change_nothing_booked_now_or_after_restart(self):
        ref, rs, rnow = self.book("ref")
        self.feed(ref, rs, rnow, 0, self.n)

        b, s, now = self.book("rev")
        self.feed(b, s, now, 0, 400)
        before = b.dump()
        self.assertGreater(len(before["trades"]), 100)
        for sym in SYMS:                                            # every processed bar so far, revised
            s.push_once(sym, [revised(x) for x in self.bars[sym][:400]])
        b.step()
        after = b.dump()
        self.assertEqual(without_conflicts(after), without_conflicts(before))
        self.assertEqual(len(after["conflicts"]), 800)
        self.assertEqual({r[0] for r in b.db.execute("SELECT processed FROM conflicts")}, {1})
        self.assertEqual(b.bars["SYN1"][:400], self.bars["SYN1"][:400])          # the first values are kept

        # a revision of a stored but not yet processed bar (the book waits for a missing bar)
        hold = {("SYN1", 400)}
        self.feed(b, s, now, 400, 402, hold)
        s.push_once("SYN1", [revised(self.bars["SYN1"][401]), self.bars["SYN1"][400]])   # the missing bar arrives in time
        self.feed(b, s, now, 402, 450)
        row = b.db.execute("SELECT processed FROM conflicts WHERE ts = ?", (self.bars["SYN1"][401][0],)).fetchall()
        self.assertIn((0,), row)
        self.assertEqual(b.bars["SYN1"][401], self.bars["SYN1"][401])

        b.close()
        b, s2, now2 = self.book("rev")                                # restart replays the first values
        s2.publish("SYN1", self.bars["SYN1"][:450])
        s2.publish("SYN2", self.bars["SYN2"][:450])
        now2[0] = now[0]
        b.step()
        for sym in SYMS:
            s2.push_once(sym, [revised(x, 1.1) for x in self.bars[sym][:450]])
        b.step()
        self.feed(b, s2, now2, 450, self.n)
        self.assertEqual(without_conflicts(b.dump()), without_conflicts(ref.dump()))
        self.assertEqual(b.bars["SYN2"], self.bars["SYN2"])
        b.close()
        ref.close()


class Adapter(unittest.TestCase):
    """The revision path through KlineSource (each request starts at the last stored bar)."""

    def setUp(self):
        import test_event_farm_source as tsrc
        self.t = tsrc
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bars = tsrc.truth(1)
        self.now = [T0]
        self.ex = tsrc.FakeExchange(self.bars, self.now)
        self.addCleanup(self.ex.stop)

    def open(self, name):
        log = os.path.join(self.tmp.name, f"event_farm_source_calls_{name}.jsonl")
        s = src.KlineSource(self.t.Act(), T0, log, transport=src.HttpTransport(self.ex.base), clock=lambda: self.now[0])
        return fv.ForwardBookV2(os.path.join(self.tmp.name, f"event_farm_forward_{name}.db"), s, list(src.SYMBOLS),
                                mode="live", activation=self.t.Act(), clock=lambda: self.now[0])

    def slots(self, b, k0, k1, faults=None):
        for k in range(k0, k1):
            if faults and k in faults:
                self.ex.faults = list(faults[k])
            self.now[0] = T0 + k * BS + 20
            b.step()

    def test_revised_bars_from_the_exchange_change_nothing(self):
        ref = self.open("ref")
        self.slots(ref, 1, 289)
        b = self.open("rev")
        faults = {k: ["revise", "revise"] for k in range(30, 289, 7)}
        self.slots(b, 1, 150, faults)
        b.close()
        b = self.open("rev")                                          # restart in the middle
        self.slots(b, 150, 289, faults)
        n_conf = b.db.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0]
        self.assertGreater(n_conf, 50)
        self.assertEqual(without_conflicts(b.dump()), without_conflicts(ref.dump()))
        b.close()
        ref.close()


class FinalText104(unittest.TestCase):
    def test_sha256_file_and_references(self):
        with open(AMEND[:-3] + ".sha256", encoding="utf-8") as f:
            sha, name = f.read().split()
        self.assertEqual((sha, name), (src.file_sha256(AMEND), os.path.basename(AMEND)))
        with open(AMEND, encoding="utf-8") as f:
            text = f.read()
        self.assertLess(len(text), 8000)
        refs = ["research/tools/event_farm.py", "research/tools/event_farm_driver.py", "research/tools/event_farm_filters.py",
                "research/tools/event_farm_forward.py", "research/tools/event_farm_forward_v2.py",
                "research/tools/event_farm_source.py", "research/desk/EVENT_FARM_FORWARD_FILTERS_DRAFT_101.md",
                "research/desk/EVENT_FARM.md"]
        for rel in refs:
            line = next(x for x in text.splitlines() if x.startswith(f"| `{rel}`"))
            self.assertIn(f"`{src.file_sha256(os.path.join(HERE, rel))}`", line, rel)
        for word in ("ANTAGELSE", "pr. rundtur", "ERSTATTER", "conflicts", "19.849"):
            self.assertIn(word, text)

    def test_the_cost_statement_matches_the_code(self):
        c = fw.FROZEN_CONFIG["costs"]
        self.assertAlmostEqual(2e4 * sum(c.values()), 28.0)
        flat = fw.lab_costs({"dir": 1, "entry": 100.0, "risk": 1.0}, 100.0, fw.FROZEN_CONFIG)
        self.assertAlmostEqual(-flat["net_usdt"] / fw.FROZEN_CONFIG["notional_usdt"] * 1e4, 28.0)   # exit = entry
        up = fw.lab_costs({"dir": 1, "entry": 100.0, "risk": 1.0}, 110.0, fw.FROZEN_CONFIG)
        self.assertAlmostEqual((up["fees_usdt"] + up["slippage_usdt"]) / 1000 * 1e4, 14.0 * (1 + 110 / 100))


if __name__ == "__main__":
    import direct_guard  # noqa: E402,F401  (order 75: quarantine guard for direct runs)
    unittest.main()
