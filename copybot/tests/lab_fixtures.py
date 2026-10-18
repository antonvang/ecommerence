"""Workers used only by the supervisor tests (loaded with --worker tests.lab_fixtures:demo_worker)."""
import time

from lab.paper import Book, PaperEngine
from lab.supervisor import Worker

EXP = "TEST_demo"
N_ORDERS = 10


def approve_paper(db, eid, actor="human:fixture", ts=0, from_state=None):
    """A verifiable human paper approval written the way lifecycle.confirm writes one (amendment 4a): an approvals
    row, the transition citing its approval_id, and exactly one approval.used by the same human."""
    aid = db.append("approvals", code_hash=f"fixture-{eid}-{ts}", exp_id=eid, to_state="PAPER_TRADING", ts=ts,
                    expires_ts=ts + 900, actor=actor, reason="fixture: approved for paper trading", evidence={})
    db.append("transitions", exp_id=eid, ts=ts, from_state=from_state, to_state="PAPER_TRADING", actor=actor,
              reason="fixture: approved for paper trading", evidence={"approval_id": aid})
    db.event("approval.used", actor, eid, {"approval_id": aid})
    return aid


def supervised(db, ts=None, status="running"):
    """A supervisor heartbeat (the exposure gate needs one within 30 s)."""
    db.con.execute("INSERT INTO heartbeats(worker, ts, pid, ok, detail, status) VALUES('supervisor',?,1,1,'',?) "
                   "ON CONFLICT(worker) DO UPDATE SET ts=excluded.ts, status=excluded.status",
                   (int(ts if ts is not None else time.time()), status))


def demo_worker():
    state = {"k": 0}

    def tick(db):
        pe = PaperEngine(db)
        book = Book(ts=time.time(), bids=((99.9, 100.0),), asks=((100.1, 100.0),))
        pe.risk.observe_book(EXP, book)                  # ends the post-restart warm-up with fresh data
        if state["k"] < N_ORDERS:
            pe.submit_taker(EXP, f"demo|{state['k']}", "X", "buy" if state["k"] % 2 == 0 else "sell", 1, book)
            state["k"] += 1

    return Worker("demo", tick, interval=0.5, critical=True)


def crashing_worker():
    def boom(db):
        raise RuntimeError("fixture crash")
    return Worker("crasher", boom, interval=0.1)
