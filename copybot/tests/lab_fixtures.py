"""Workers used only by the supervisor tests (loaded with --worker tests.lab_fixtures:demo_worker)."""
import time

from lab.paper import Book, PaperEngine
from lab.supervisor import Worker

EXP = "TEST_demo"
N_ORDERS = 10


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
