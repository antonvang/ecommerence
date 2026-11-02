"""N4 draft (MISSION27_3 point 6c, method n4): does a rising Upbit KRW premium for a coin forecast its Binance perp
return against BTC over the next 24 hours?

  python3 research/tools/n4_kimchi.py run      refuses until PROTOCOL_V3.md holds a locked amendment for method n4
                                               and the date is >= 2026-11-14 (no historical query before that)

Written before any Upbit candle or explore0 kline was read. Statistics only (signal, quintile L/S, the decision);
the data loader is written after the lock.
"""
import datetime as dt
import json
import math
import os
import re
import statistics as st
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
from lab.edgemonitor import t_cdf  # noqa: E402

PROTOCOL = os.path.join(HERE, "research", "PROTOCOL_V3.md")
PAIRS = os.path.join(HERE, "research", "data", "N4_KIMCHI_PAIRS_2026-11-02.json")
EARLIEST = dt.date(2026, 11, 14)
MIN_COINS = 40             # point 2
FLOOR = 0.0046             # point 6 (21i)
ALPHA = 0.005
PLACEBO_DAYS = 7           # point 6


def q(upbit_krw, binance_usdt):
    """ln U - ln B (point 3). A contract multiplier or the USD/KRW rate only shifts it by a constant."""
    return math.log(upbit_krw) - math.log(binance_usdt)


def signal(q_today, q_prev):
    """s_c = (q_c,d - q_c,d-1) - cross-sectional median; only coins in both days; None below MIN_COINS."""
    common = sorted(set(q_today) & set(q_prev))
    if len(common) < MIN_COINS:
        return None
    dq = {c: q_today[c] - q_prev[c] for c in common}
    med = st.median(dq.values())
    return {c: v - med for c, v in dq.items()}


def outcome(p_in, p_out, btc_in, btc_out):
    """y = ln perp return from entry to exit minus BTCUSDT's over the same hours (point 4)."""
    return math.log(p_out / p_in) - math.log(btc_out / btc_in)


def quintile_ls(s, y):
    """r_d = mean y of the top fifth by s minus the bottom fifth; ties by symbol (point 5)."""
    coins = sorted((c for c in s if c in y), key=lambda c: (s[c], c))
    if len(coins) < MIN_COINS:
        return None
    k = len(coins) // 5
    return st.fmean(y[c] for c in coins[-k:]) - st.fmean(y[c] for c in coins[:k])


def tstat(xs):
    if len(xs) < 3 or st.stdev(xs) == 0:
        return None, None
    t = st.fmean(xs) / (st.stdev(xs) / math.sqrt(len(xs)))
    return t, 2 * (1 - t_cdf(abs(t), len(xs) - 1))


def judge(rs, placebo):
    """Point 6: SCREEN_PASS / SIGNAL_BELOW_FLOOR / REVERSED / SCREEN_FAIL over daily r_d (chronological)."""
    if len(rs) < 3:
        return {"verdict": "UNTESTABLE", "days": len(rs)}
    t, p = tstat(rs)
    mean = st.fmean(rs)
    half = len(rs) // 2
    h1, h2 = st.fmean(rs[:half]), st.fmean(rs[half:])
    drop = st.fmean(sorted(rs, key=abs)[:-2])
    tp, _ = tstat(placebo)
    sig = p is not None and p <= ALPHA
    robust = (h1 > 0) == (h2 > 0) == (mean > 0) and (drop > 0) == (mean > 0) and tp is not None and abs(tp) < 2
    if sig and mean > 0 and mean - FLOOR > 0 and robust:
        verdict = "SCREEN_PASS"
    elif sig and mean > 0:
        verdict = "SIGNAL_BELOW_FLOOR" if mean < FLOOR else "SCREEN_FAIL"
    elif sig and mean < 0:
        verdict = "REVERSED"
    else:
        verdict = "SCREEN_FAIL"
    return {"verdict": verdict, "days": len(rs), "mean": mean, "t": t, "p": p, "halves": [h1, h2],
            "without_2_largest": drop, "placebo_t": tp, "floor": FLOOR}


def locked(text):
    return re.search(r"^## Ændring [^\n]*metode n4\b", text, re.M) is not None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    today = dt.datetime.now(dt.timezone.utc).date()
    if argv[:1] != ["run"]:
        print("usage: n4_kimchi.py run")
        return
    if today < EARLIEST or not locked(open(PROTOCOL, encoding="utf-8").read()):
        print(json.dumps({"refused": "no locked amendment for method n4 or before 2026-11-14 (no historical query)"}))
        return
    print(json.dumps({"refused": "data loader not written yet; it is written after the lock"}))


if __name__ == "__main__":
    main()
