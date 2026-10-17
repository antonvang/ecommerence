import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lab import supervisor  # noqa: E402
from lab.db import DB  # noqa: E402
from lab.lifecycle import state  # noqa: E402
from lab.paper import Book, CostModel, PaperEngine  # noqa: E402
from lab.risk import Risk  # noqa: E402
from tests.lab_fixtures import EXP, N_ORDERS  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def paper_strategy(db, eid=EXP):
    db.append("experiments", exp_id=eid, version=1, created_ts=0, mechanism_tag="t", fingerprint=eid,
              spec_json={"execution": "taker", "risk": {"consecutive_losses": 1000}})   # demo trades lose the spread
    db.append("transitions", exp_id=eid, ts=0, from_state=None, to_state="PAPER_TRADING", actor="fixture",
              reason="fixture: strategy already approved for paper trading")
    PaperEngine(db).start(eid, 10_000.0, CostModel(taker_fee=0.0005))


class FakeClock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "lab.db")
        self.db = DB(self.path)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_startup_warmup_blocks_entries_until_fresh_data(self):
        paper_strategy(self.db)
        ok, rep = supervisor.recover(self.db, Risk(self.db), check_evidence=False)
        self.assertTrue(ok)
        self.assertEqual(rep["warmup"], [EXP])
        pe = PaperEngine(self.db)
        b = Book(ts=time.time(), bids=((99.9, 5),), asks=((100.1, 5),))
        self.assertEqual(pe.submit_taker(EXP, "o1", "X", "buy", 1, b)["status"], "refused")
        self.assertFalse(pe.risk.observe_book(EXP, Book(ts=time.time() - 600, bids=b.bids, asks=b.asks)))  # stale
        self.assertTrue(pe.risk.observe_book(EXP, b))
        self.assertEqual(pe.submit_taker(EXP, "o2", "X", "buy", 1, b)["status"], "filled")

    def test_tampered_chain_fails_closed_and_supervisor_refuses_to_start(self):
        self.db.event("x", "system:test")
        self.db.con.execute("DROP TRIGGER events_no_update")
        self.db.con.execute("UPDATE events SET kind='tampered'")
        self.db.close()
        sup = supervisor.Supervisor(self.path, [supervisor.heartbeat_worker()], log=lambda *a: None,
                                    check_evidence=False)
        self.assertEqual(sup.run(duration=1), 2)
        self.db = DB(self.path)
        self.assertTrue(Risk(self.db).fail_closed())

    def test_pause_in_risk_log_is_reconciled_into_lifecycle(self):
        paper_strategy(self.db)
        r = Risk(self.db)
        with self.db.tx():
            r._event(EXP, "consecutive_losses", 2, 2, "PAUSE", "crash happened before the lifecycle update")
        ok, rep = supervisor.recover(self.db, r, check_evidence=False)
        self.assertEqual((ok, rep["reconciled_pauses"]), (True, [EXP]))
        self.assertEqual(state(self.db, EXP), "PAUSED")

    def test_restart_backoff_then_failed_and_critical_fails_closed(self):
        clock = FakeClock()
        w = supervisor.Worker("crasher", lambda db: (_ for _ in ()).throw(RuntimeError("x")), interval=0.05,
                              critical=True)
        sup = supervisor.Supervisor(self.path, [w], now=clock, log=lambda *a: None, check_evidence=False)
        sup.db = self.db
        delays = []
        for _ in range(12):
            sup.check()
            if w.thread:
                w.thread.join(timeout=5)
            ev = self.db.one("SELECT payload FROM events WHERE kind='worker.restarted' ORDER BY id DESC LIMIT 1")
            if ev:
                delays.append(ev[0])
            clock.t += 400                                            # past any backoff
        restarts = self.db.q("SELECT payload FROM events WHERE kind='worker.restarted'")
        self.assertEqual(len(restarts), supervisor.MAX_RESTARTS_PER_HOUR)
        self.assertIn('"next_backoff_s":5.0', restarts[0][0])
        self.assertIn('"next_backoff_s":10.0', restarts[1][0])
        self.assertTrue(self.db.one("SELECT 1 FROM events WHERE kind='worker.failed'"))
        self.assertTrue(Risk(self.db).fail_closed())
        self.assertGreaterEqual(len(self.db.q("SELECT 1 FROM events WHERE kind='worker.error'")), 5)


class KillAndRestart(unittest.TestCase):
    """A real supervisor process is hard-killed mid-run and restarted: no duplicate orders, consistent state."""

    def cmd(self, path, duration):
        return [sys.executable, "-m", "lab", "--db", path, "supervise", "--no-default",
                "--worker", "tests.lab_fixtures:demo_worker", "--duration", str(duration)]

    def count(self, path, sql):
        db = DB(path)
        try:
            return db.one(sql)[0]
        finally:
            db.close()

    def test_kill_restart_no_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "lab.db")
            db = DB(path)
            paper_strategy(db)
            db.close()
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            p = subprocess.Popen(self.cmd(path, 60), cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            try:
                t0 = time.time()
                while self.count(path, "SELECT COUNT(*) FROM sim_orders") < 3:
                    self.assertLess(time.time() - t0, 30, "supervisor did not start trading")
                    self.assertIsNone(p.poll(), p.stdout.read().decode(errors="replace") if p.poll() is not None else "")
                    time.sleep(0.1)
                second = subprocess.run(self.cmd(path, 1), cwd=HERE, env=env, capture_output=True, text=True)
                self.assertEqual(second.returncode, 3, second.stdout + second.stderr)   # single instance
                p.kill()                                              # hard kill, no cleanup
                p.wait(timeout=10)
            finally:
                if p.poll() is None:
                    p.kill()
                p.stdout.close()
            before = self.count(path, "SELECT COUNT(*) FROM sim_orders")
            self.assertLess(before, N_ORDERS)
            r = subprocess.run(self.cmd(path, 9), cwd=HERE, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.count(path, "SELECT COUNT(DISTINCT order_id) FROM sim_orders"), N_ORDERS)
            self.assertEqual(self.count(path, "SELECT COUNT(*) FROM sim_orders"), N_ORDERS)
            self.assertEqual(self.count(path, "SELECT COUNT(*) FROM sim_fills"), N_ORDERS)
            self.assertEqual(self.count(path, "SELECT COUNT(*) FROM events WHERE kind='system.startup'"), 2)
            self.assertGreaterEqual(self.count(path, "SELECT COUNT(*) FROM risk_events WHERE action='WARMUP'"), 2)
            self.assertEqual(self.count(path, "SELECT COUNT(*) FROM risk_events WHERE action='FAIL_CLOSED'"), 0)
            db = DB(path)
            chains, trig = db.verify()
            self.assertTrue(trig and all(b is None for _, b in chains.values()))
            self.assertEqual(PaperEngine(db).ledger(EXP)["positions"], {})          # 5 buys, 5 sells
            db.close()


if __name__ == "__main__":
    unittest.main()
