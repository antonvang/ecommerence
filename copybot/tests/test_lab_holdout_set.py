"""The holdout is opened once as one declared file set (research/PROTOCOL_V3.md amendment 7 section 8): a template with
an extra source (MVRV: klines and funding plus CoinMetrics) can complete its holdout reads, and nothing outside the set,
no changed file and no other code may be read afterwards."""
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import pipeline  # noqa: E402
from lab.data import AccessRefused, Gateway  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.engine import data  # noqa: E402

EID = "E_mvrv_value_p3"


class HoldoutSet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="labhset")
        self.db = DB(os.path.join(self.tmp, "lab.db"))
        self.spec = pipeline.template_spec("mvrv_value")
        self.db.append("experiments", exp_id=EID, version=1, created_ts=0, mechanism_tag="m", fingerprint="f",
                       spec_json=self.spec)
        self.db.append("transitions", exp_id=EID, ts=0, from_state=None, to_state="VALIDATION", actor="fixture",
                       reason="fixture: holdout approved")
        self.calls = []
        real = Gateway.access

        def spy(gw, exp_id, split, paths, *a, **k):
            self.calls.append((split, len(paths)))
            return real(gw, exp_id, split, paths, *a, **k)
        self.p = [mock.patch.object(data, "files_for", self.files_for), mock.patch.object(data, "cm_for", self.cm_for),
                  mock.patch.object(data, "load", lambda f, split: ([], [], 0)),
                  mock.patch.object(data, "load_cm", lambda p: {}), mock.patch.object(Gateway, "access", spy)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()
        self.db.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mk(self, name, body):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as f:
            f.write(body)
        return p

    def files_for(self, sym, split, get=None):
        return {"klines": [self.mk(f"{sym}_{split}_k.csv", sym + "k")],
                "funding": [self.mk(f"{sym}_{split}_f.csv", sym + "f")]}

    def cm_for(self, metric, split, symbols, get=None):
        return self.mk(f"cm_{metric}_{split}.json", metric)

    def refused(self):
        return self.db.one("SELECT COUNT(*) FROM events WHERE kind='data.refused'")[0]

    def test_without_a_declared_set_an_extra_source_could_never_be_read(self):
        with self.assertRaises(AccessRefused):                     # the bug amendment 7 section 8 fixes
            pipeline._market(self.db, EID, "holdout", "validation-1", self.spec)
        self.assertEqual([c[1] for c in self.calls], [32, 1])

    def test_with_the_declared_set_every_holdout_read_passes_once(self):
        pipeline._declare_holdout(self.db, EID, self.spec, "validation-1")
        pipeline._market(self.db, EID, "holdout", "validation-1", self.spec)
        self.assertEqual([c[1] for c in self.calls], [33, 32, 1])
        self.assertEqual(self.db.one("SELECT COUNT(*) FROM events WHERE kind='holdout.opened'")[0], 1)
        self.assertEqual(self.refused(), 0)
        pipeline._market(self.db, EID, "holdout", "validation-1", self.spec)    # a same-code re-run reads the same set
        self.assertEqual(self.refused(), 0)

    def test_nothing_outside_the_set_no_changed_file_and_no_other_code(self):
        pipeline._declare_holdout(self.db, EID, self.spec, "validation-1")
        gw, win, code = Gateway(self.db, "system:t"), data.window("holdout"), pipeline._code_hash()
        extra = self.mk("not_declared.csv", "BTCUSDTk")              # same bytes as a declared file, other path
        with self.assertRaises(AccessRefused):
            gw.access(EID, "holdout", [extra], win, "t", "evaluate", code)
        some = self.files_for("BTCUSDT", "holdout")["klines"][0]
        with self.assertRaises(AccessRefused):
            gw.access(EID, "holdout", [some], win, "t", "evaluate", "another code hash")
        with open(some, "w") as f:
            f.write("changed")
        with self.assertRaises(AccessRefused):
            gw.access(EID, "holdout", [some], win, "t", "evaluate", code)
        self.assertEqual(self.refused(), 3)


if __name__ == "__main__":
    unittest.main()
