import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import registry, web  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.lifecycle import state  # noqa: E402
from lab.paper import Book, CostModel, PaperEngine  # noqa: E402
from tests.lab_fixtures import approve_paper, supervised  # noqa: E402


def fixture(path):
    db = DB(path)
    for eid, st, verdict in (("L1", "REJECTED", "FAIL: fixture"), ("X1", "EXTERNAL", "RUNNING fixture"),
                             ("P1", "PAPER_TRADING", None), ("P2", "PAPER_TRADING", None)):
        db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag=f"m_{eid}", fingerprint=eid,
                  spec_json={"execution": "taker", "risk": {"consecutive_losses": 99}})
        if st == "PAPER_TRADING":
            approve_paper(db, eid)
        else:
            db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state=st, actor="fixture",
                      reason="fixture for dashboard tests")
        if verdict:
            db.append("results", exp_id=eid, version=1, ts=0, label="LEGACY", verdict=verdict, metrics={}, evidence={})
    registry.discover(db, "C1", "a hypothesis", "new_mech", "inst", "minutes", "taker", "unit test", "human:t")
    registry.discover(db, "C2", "another hypothesis", "new_mech2", "inst", "minutes", "taker", "unit test", "human:t")
    pe = PaperEngine(db)
    pe.start("P2", 1000.0, CostModel(taker_fee=0.001))
    pe.start("P1", 1000.0, CostModel(taker_fee=0.001, expected_spread=0.01))
    b = Book(ts=time.time(), bids=((99.9, 50),), asks=((100.1, 50),))
    supervised(db)
    pe.submit_taker("P1", "o1", "X", "buy", 2, b)
    pe.mark("P1", {"X": 100.5})
    pe.mark("P1", {"X": 99.0})
    db.append("observations", ts=int(time.time()), detector="pricing_constraint/2", source="fixture", instrument="ETH",
              metric="cross_venue_gap", value=0.004, threshold=0.003, flagged=1, payload={})
    db.close()


class Dashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "lab.db")
        fixture(cls.path)
        cls.srv = web.LabServer(("127.0.0.1", 0), cls.path)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def get(self, p):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{p}", timeout=10) as r:
            body = r.read()
            return json.loads(body) if p.startswith("/api") else body.decode()

    def post(self, p, body, token=True, origin=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["X-Lab-Token"] = self.srv.token
        if origin:
            h["Origin"] = origin
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{p}", data=json.dumps(body).encode(), headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def db(self):
        return DB(self.path)

    def test_page_has_paper_only_banner_and_token(self):
        html = self.get("/")
        self.assertIn("PAPER ONLY", html)
        self.assertIn(self.srv.token, html)
        self.assertNotIn("__LAB_TOKEN__", html)

    def test_numbers_come_from_the_database(self):
        ov = self.get("/api/overview")
        db = self.db()
        try:
            counts = {}
            for x in registry.status(db):
                counts[x["state"]] = counts.get(x["state"], 0) + 1
            self.assertEqual(ov["pipeline"], counts)
            self.assertEqual(ov["rejected"], counts["REJECTED"])
            self.assertTrue(ov["chain_ok"] and ov["paper_only"])
            pa = self.get("/api/paper")
            self.assertTrue(pa["simulated"])
            s = pa["strategies"][0]
            rows = db.q("SELECT equity, drawdown FROM sim_equity WHERE exp_id='P1' ORDER BY id")
            self.assertEqual([round(p["equity"], 9) for p in s["equity"]], [round(r[0], 9) for r in rows])
            self.assertEqual(s["positions"], {"X": 2})
            fees = db.one("SELECT SUM(fee) FROM sim_fills WHERE exp_id='P1'")[0]
            self.assertAlmostEqual(sum(c["fees"] for c in s["costs"]), fees)
        finally:
            db.close()

    def test_every_experiment_is_labelled(self):
        ex = self.get("/api/experiments")
        self.assertTrue(all(e["display_label"] for e in ex))
        lab = {e["exp_id"]: e["display_label"] for e in ex}
        self.assertEqual(lab["P1"], "PAPER (simulated)")
        self.assertEqual(lab["C1"], "CANDIDATE")
        self.assertEqual(lab["X1"], "EXTERNAL")
        ca = self.get("/api/candidates")
        self.assertIn("C1", [c["exp_id"] for c in ca["candidates"]])
        self.assertTrue(any(o["flagged"] for o in ca["last_scan"]))
        d = self.get("/api/experiment/L1")
        self.assertEqual(d["results"][0]["verdict"], "FAIL: fixture")
        self.assertEqual(self.get("/api/audit?limit=5")["events"].__len__(), 5)

    def test_controls_are_guarded(self):
        self.assertEqual(self.post("/api/control/approve", {"exp_id": "C2", "to": "WITHDRAWN",
                                                            "reason": "not needed any more"}, token=False)[0], 403)
        self.assertEqual(self.post("/api/control/approve", {"exp_id": "C2", "to": "WITHDRAWN", "reason": "x" * 20},
                                   origin="http://evil.example")[0], 403)
        code, r = self.post("/api/control/approve", {"exp_id": "X1", "to": "PAPER_TRADING", "reason": "promote it now"})
        self.assertEqual(code, 400)                                    # EXTERNAL cannot be promoted
        code, r = self.post("/api/control/approve", {"exp_id": "C2", "to": "REGISTERED", "reason": "looks great"})
        self.assertEqual(code, 400)                                    # incomplete spec
        code, r = self.post("/api/control/approve", {"exp_id": "C2", "to": "WITHDRAWN", "reason": "not needed any more"})
        self.assertEqual(code, 200)
        code, r = self.post("/api/control/confirm", {"code": r["code"]})
        self.assertEqual((code, r["state"]), (200, "WITHDRAWN"))
        self.assertEqual(self.post("/api/control/pause", {"exp_id": "L1", "reason": "pause a rejected one"})[0], 400)
        code, r = self.post("/api/control/pause", {"exp_id": "P2", "reason": "manual check of fills"})
        self.assertEqual((code, r["state"]), (200, "PAUSED"))
        code, r = self.post("/api/control/approve", {"exp_id": "P2", "to": "PAPER_TRADING", "reason": "resume please"})
        self.assertEqual(code, 400)                                    # resume needs committed revalidation evidence
        db = self.db()
        try:
            self.assertEqual(state(db, "P2"), "PAUSED")
            self.assertTrue(db.one("SELECT 1 FROM events WHERE actor LIKE 'human:%@dashboard'"))
            chains, trig = db.verify()
            self.assertTrue(trig and all(b is None for _, b in chains.values()))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
