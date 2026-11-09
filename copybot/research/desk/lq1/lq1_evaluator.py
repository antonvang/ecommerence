"""LQ1: syntetisk evaluator for LQ1_PROTOCOL_DRAFT.md. UDKAST, IKKE LAAST.

LQ1 er beskrivende forskning om handelsomkostninger. Den er ikke en dokumenteret handelsfordel, og en dom her er ikke
evidens for noget marked: denne fil laeser kun syntetiske fixtures under `fixtures/` i sin egen mappe.

Spoergsmaal: naar 5.000-USD-rundturen i et marked er mindst 3 gange sin egen 168-timers median, er den saa en time senere
saa meget lavere, at ventetiden sparer mere end 5 bp pr. side? S_i = 1/2 (RT_t - RT_t+1) i bp; H0: S-middel <= 5 bp;
ensidet t-test paa UTC-doegnklyngernes middel.

Rent stdlib, deterministisk og uden netvaerk, database eller markedsdata. Bruges ikke af nogen bog, bane eller ordre.
Foer fristen (L + 99 d) returneres kun antal, aldrig et udfald. Ugyldigt input giver status ERROR, aldrig en dom.

Kor: python3 research/desk/lq1/lq1_evaluator.py research/desk/lq1/fixtures/<navn>.json
"""
from __future__ import annotations

import bisect
import collections
import hashlib
import json
import math
import os
import sys

SCHEMA = "lq1-fixture/1"
RESULT_SCHEMA = "lq1-result/1"
FIXTURE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fixtures")

HOUR, DAY = 3600, 86400
BREAK_MULT = 3.0                # brud: RT_t >= 3 x baseline
BASELINE_MAX, BASELINE_MIN = 168, 120   # brugbare timer
DEDUP_S = 6 * HOUR              # hoejst een haendelse pr. marked pr. 6 t
MAX_SCAN_DELAY_S = 600          # tidligste scanning hoejst 10 min efter timeskiftet
THRESHOLD_BP = 5.0              # en standard-taker pr. side
ALPHA_F = 0.0125                # ensidet; alfa-status er BESKRIVENDE (alfa = 0), se LABEL
START_D, END_D, DEADLINE_D = 7, 98, 99      # haendelser i [L + 7 d, L + 98 d); dom ved L + 99 d
MIN_CLUSTER_DAYS = 30
MIN_COVERAGE = 0.90
MAX_CENSORED = 0.20
MIN_MARKETS = 3
DEFAULT_SCAN_DELAY_S = 120

PASS, FALSIFIED, INCONCLUSIVE = "PASS", "FALSIFIED", "INCONCLUSIVE"
INCONCLUSIVE_CENSORED, UNTESTABLE, INVALID = "INCONCLUSIVE_CENSORED", "UNTESTABLE", "INVALID"
VERDICTS = (PASS, FALSIFIED, INCONCLUSIVE, INCONCLUSIVE_CENSORED, UNTESTABLE, INVALID)
LABEL = "BESKRIVENDE (alfa = 0), syntetisk: en omkostningsmaaling, ikke en dokumenteret handelsfordel"

THIN, ERR = "T", "E"            # celle: bogen for tynd til 5.000 USD / anden fejl i scanningen
_MARKET_KEYS = {"series", "off_hours", "delays", "extra_scans"}
_REQUIRED = ("synthetic", "schema", "world", "lock_ts", "as_of_ts", "first_h", "markets")
_OPTIONAL = {"scan_delay_s", "seed", "note", "params"}


class LQ1InputError(ValueError):
    """Fixturen er ugyldig. Giver status ERROR; der gaettes aldrig en dom ud fra daarligt input."""


# ---- t-fordeling (eksakt via regulariseret ufuldstaendig beta; ingen tilnaermelse i beslutningen) ----

def _betacf(a, b, x):
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 501):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d, c = 1.0 + aa * d, 1.0 + aa / c
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d, c = 1.0 + aa * d, 1.0 + aa / c
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h


def _betainc(a, b, x):
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_sf(t, df):
    """P(T_df >= t)."""
    tail = 0.5 * _betainc(df / 2.0, 0.5, df / (df + t * t))
    return tail if t >= 0 else 1.0 - tail


_QUANTILES = {}


def t_quantile(p, df):
    """Kvantil ved bisektion paa den eksakte fordeling (deterministisk; gemmes pr. (p, df))."""
    if (p, df) not in _QUANTILES:
        lo, hi = -1e4, 1e4
        for _ in range(200):
            mid = (lo + hi) / 2.0
            if t_sf(mid, df) > 1.0 - p:
                lo = mid
            else:
                hi = mid
        _QUANTILES[(p, df)] = (lo + hi) / 2.0
    return _QUANTILES[(p, df)]


def one_sided_test(means, mu0=THRESHOLD_BP):
    """Ensidet t-test af H0: middel <= mu0 og ensidet 95 %-oevre graense. Klynger er uafhaengige (design)."""
    n = len(means)
    if n < 2:
        raise LQ1InputError("mindst 2 klynger kraeves til en t-test")
    mean = math.fsum(means) / n
    var = math.fsum((x - mean) ** 2 for x in means) / (n - 1)
    se = math.sqrt(var / n)
    df = n - 1
    if se == 0.0:                                   # fx alle S_i = 0: alle RT_t+1 censureret
        p = 0.0 if mean > mu0 else 1.0
        return {"n": n, "mean": mean, "sd": 0.0, "se": 0.0, "t": None, "p": p, "upper95": mean, "df": df}
    t = (mean - mu0) / se
    return {"n": n, "mean": mean, "sd": math.sqrt(var), "se": se, "t": t, "p": t_sf(t, df),
            "upper95": mean + t_quantile(0.95, df) * se, "df": df}


def decide(coverage, n_clusters, censored_share, test, robust_ok):
    """Domstraeet i LQ1_PROTOCOL_DRAFT.md afsnit 3, i praecis denne raekkefoelge. Domme udelukker hinanden."""
    if coverage < MIN_COVERAGE:
        return INVALID, "COVERAGE_BELOW_90"
    if n_clusters < MIN_CLUSTER_DAYS:
        return UNTESTABLE, "FEWER_THAN_30_CLUSTER_DAYS"
    if censored_share > MAX_CENSORED:
        return INCONCLUSIVE_CENSORED, "CENSORED_ABOVE_20"
    if test["upper95"] < THRESHOLD_BP:
        return FALSIFIED, "UPPER95_BELOW_THRESHOLD"
    if test["p"] <= ALPHA_F and test["mean"] > THRESHOLD_BP:
        if robust_ok:
            return PASS, "P_BELOW_ALPHA_AND_ROBUST"
        return INCONCLUSIVE, "ROBUSTNESS_GATE_FAILED"
    return INCONCLUSIVE, "NOT_SIGNIFICANT"


# ---- input ----

def _int(value, what):
    if isinstance(value, bool) or not isinstance(value, int):
        raise LQ1InputError(f"{what} skal vaere et heltal")
    return value


def _cell(cell, what):
    if cell in (None, THIN, ERR):
        return cell
    if isinstance(cell, bool) or not isinstance(cell, int) or cell <= 0:
        raise LQ1InputError(f"{what}: ugyldig celle {cell!r} (heltal i 0,1 bp > 0, null, 'T' eller 'E')")
    return cell


def _index(i, n, what):
    _int(i, what)
    if not 0 <= i < n:
        raise LQ1InputError(f"{what}: indeks {i} uden for serien")
    return i


def decode_fixture(doc):
    """Valider et fixture-dokument og byg verdenen. Alt uventet er en fejl (fail closed)."""
    if not isinstance(doc, dict):
        raise LQ1InputError("fixturen skal vaere et objekt")
    missing = [k for k in _REQUIRED if k not in doc]
    if missing:
        raise LQ1InputError(f"manglende felter: {missing}")
    unknown = sorted(set(doc) - set(_REQUIRED) - _OPTIONAL)
    if unknown:
        raise LQ1InputError(f"ukendte felter: {unknown}")
    if doc["synthetic"] is not True:
        raise LQ1InputError("kun syntetiske fixtures (synthetic: true) maa laeses")
    if doc["schema"] != SCHEMA:
        raise LQ1InputError(f"forkert skema: {doc['schema']!r}")
    lock, as_of, first = (_int(doc[k], k) for k in ("lock_ts", "as_of_ts", "first_h"))
    if lock % HOUR or first % HOUR:
        raise LQ1InputError("lock_ts og first_h skal ligge paa et timeskifte")
    if as_of < lock:
        raise LQ1InputError("as_of_ts ligger foer lock_ts")
    default_delay = _int(doc.get("scan_delay_s", DEFAULT_SCAN_DELAY_S), "scan_delay_s")
    if default_delay < 0:
        raise LQ1InputError("scan_delay_s er negativ")
    if not isinstance(doc["markets"], dict) or not doc["markets"]:
        raise LQ1InputError("markets skal vaere et ikke-tomt objekt")
    scans, off, n_dupes = {}, {}, 0
    for market in sorted(doc["markets"]):
        spec = doc["markets"][market]
        if not isinstance(spec, dict) or not isinstance(spec.get("series"), list) or not spec["series"]:
            raise LQ1InputError(f"{market}: series mangler eller er tom")
        bad = sorted(set(spec) - _MARKET_KEYS)
        if bad:
            raise LQ1InputError(f"{market}: ukendte felter {bad}")
        series, n = spec["series"], len(spec["series"])
        delay_at = {}
        for pair in spec.get("delays", []):
            if not isinstance(pair, list) or len(pair) != 2:
                raise LQ1InputError(f"{market}: delays skal vaere [indeks, sekunder]")
            i = _index(pair[0], n, f"{market}.delays")
            if _int(pair[1], f"{market}.delays") < 0:
                raise LQ1InputError(f"{market}: negativ forsinkelse")
            delay_at[i] = pair[1]
        by_hour = {}
        for i, raw in enumerate(series):
            cell = _cell(raw, f"{market}[{i}]")
            if cell is not None:
                by_hour.setdefault(first + i * HOUR, []).append((delay_at.get(i, default_delay), 0, cell))
        for j, row in enumerate(spec.get("extra_scans", [])):
            if not isinstance(row, list) or len(row) != 3:
                raise LQ1InputError(f"{market}: extra_scans skal vaere [indeks, sekunder, celle]")
            i = _index(row[0], n, f"{market}.extra_scans")
            if _int(row[1], f"{market}.extra_scans") < 0:
                raise LQ1InputError(f"{market}: negativ forsinkelse")
            cell = _cell(row[2], f"{market}.extra_scans")
            if cell is None:
                raise LQ1InputError(f"{market}: extra_scans kan ikke vaere null")
            by_hour.setdefault(first + i * HOUR, []).append((row[1], j + 1, cell))
        off_h = set()
        for rng in spec.get("off_hours", []):
            if not isinstance(rng, list) or len(rng) != 2:
                raise LQ1InputError(f"{market}: off_hours skal vaere [start, slut)")
            a, b = _int(rng[0], f"{market}.off_hours"), _int(rng[1], f"{market}.off_hours")
            if not 0 <= a < b <= n:
                raise LQ1InputError(f"{market}: off_hours uden for serien")
            off_h.update(first + i * HOUR for i in range(a, b))
        scans[market] = {}
        for h, rows in by_hour.items():
            n_dupes += len(rows) - 1
            scans[market][h] = min(rows)[0::2]          # tidligste scanning: (forsinkelse, celle)
        off[market] = off_h
    return {"world": doc["world"], "lock_ts": lock, "as_of_ts": as_of, "first_h": first, "scans": scans,
            "off": off, "last_h": first + (max(len(doc["markets"][m]["series"]) for m in doc["markets"]) - 1) * HOUR,
            "n_duplicate_scans": n_dupes}


def load_fixture(path):
    """Laes en fixture. Kun filer direkte under `fixtures/` i denne mappe; alt andet afvises."""
    real = os.path.realpath(path)
    if os.path.dirname(real) != FIXTURE_DIR or not real.endswith(".json"):
        raise LQ1InputError("kun .json-filer direkte i lq1/fixtures/ maa laeses")
    try:
        with open(real, encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError as e:
        raise LQ1InputError(f"filen kan ikke laeses: {e.strerror}") from e
    except json.JSONDecodeError as e:
        raise LQ1InputError(f"ugyldig JSON: {e.msg}") from e
    return decode_fixture(doc)


# ---- haendelser ----

class _Baseline:
    """Median af de seneste hoejst 168 brugbare timer, kun efter laasen (rullende, O(n) indsaettelse)."""

    def __init__(self):
        self.window, self.sorted = collections.deque(), []

    def add(self, x):
        self.window.append(x)
        bisect.insort(self.sorted, x)
        if len(self.window) > BASELINE_MAX:
            del self.sorted[bisect.bisect_left(self.sorted, self.window.popleft())]

    def median(self):
        n = len(self.sorted)
        if n < BASELINE_MIN:
            return None
        return self.sorted[n // 2] if n % 2 else (self.sorted[n // 2 - 1] + self.sorted[n // 2]) / 2.0


def _state(world, market, h):
    """('ok', rt-brok) | ('thin', None) | ('missing', aarsag). Kun den tidligste scanning taeller."""
    row = world["scans"][market].get(h)
    if row is None:
        return "missing", "no_scan"
    delay, cell = row
    if delay > MAX_SCAN_DELAY_S:
        return "missing", "late_scan"
    if cell == ERR:
        return "missing", "error_scan"
    if cell == THIN:
        return "thin", None
    return "ok", cell * 1e-5                         # 0,1 bp -> broek af prisen, som scannerens round_trip


def find_events(world):
    """Alle haendelser og taellere. Maalingstimen h er timen, scanningen ligger i (open_s + 3600 = h)."""
    lock = world["lock_ts"]
    start, end = lock + START_D * DAY, lock + END_D * DAY
    c = collections.Counter()
    events = []
    for market in sorted(world["scans"]):
        off = world["off"][market]
        baseline = _Baseline()
        last_event = None
        h = max(lock, world["first_h"])
        while h < end:
            state, val = _state(world, market, h)
            is_off, after_reopen = h in off, (h - HOUR) in off and h not in off
            in_window = start <= h
            if in_window and not is_off:
                c["market_hours_total"] += 1
                if state == "missing":
                    c[f"missing_hours_{val}"] += 1
                else:
                    c["market_hours_scanned"] += 1
            if in_window and state != "missing":
                base = baseline.median()
                is_break = state == "thin" or (base is not None and val >= BREAK_MULT * base)
                if base is None:
                    if state == "thin" or not is_off:
                        c["no_baseline_hours"] += 1
                elif is_break:
                    if is_off:
                        c["excluded_off_hours_t"] += 1
                    elif after_reopen:
                        c["excluded_first_after_reopen"] += 1
                    elif last_event is not None and h - last_event < DEDUP_S:
                        c["deduped"] += 1
                    else:
                        last_event = h                  # en kandidat bruger dedup, ogsaa hvis t+1 mangler
                        h1 = h + HOUR
                        st1, v1 = _state(world, market, h1)
                        if h1 in off:
                            c["excluded_off_hours_t1"] += 1
                        elif st1 == "missing":
                            c["excluded_missing_t1"] += 1
                        else:
                            events.append(_event(market, h, state, val, st1, v1, base, c))
            if state == "ok" and not is_off and not after_reopen:   # kun brugbare timer efter laasen i baseline
                baseline.add(val)
            h += HOUR
    c["duplicate_scans_dropped"] = world["n_duplicate_scans"]
    return events, c


def _event(market, h, state, val, st1, v1, base, c):
    c["events"] += 1
    if state == "thin":                                 # RT_t censureret: taeller, men indgaar ikke i S-middel
        c["censored_t"] += 1
        return {"market": market, "h": h, "s": None, "censored_t1": False, "reverted": None, "full": None}
    if st1 == "thin":                                    # RT_t+1 censureret: S = 0 (konservativt mod H1)
        c["censored_t1"] += 1
        return {"market": market, "h": h, "s": 0.0, "censored_t1": True, "reverted": None,
                "full": 0.5 * (val - base) * 1e4}
    excess = val - base
    return {"market": market, "h": h, "s": 0.5 * (val - v1) * 1e4, "censored_t1": False,
            "reverted": (val - v1) / excess if excess > 0 else None, "full": 0.5 * excess * 1e4}


def cluster_means(events, without=None):
    """UTC-doegnklyngernes middel af S (kun haendelser med S-vaerdi), sorteret efter doegn."""
    days = collections.defaultdict(list)
    for e in events:
        if e["s"] is not None and e["market"] != without:
            days[e["h"] // DAY].append(e["s"])
    return [math.fsum(days[d]) / len(days[d]) for d in sorted(days)]


def robustness(events):
    """Porten: mindst 3 markeder bidrager, og S-middel uden markedet med flest haendelser er > 5 bp (punktskoen).
    Ved lighed bruges det laveste S-middel (konservativt)."""
    counts = collections.Counter(e["market"] for e in events if e["s"] is not None)
    markets = sorted(counts)
    if not markets:
        return {"markets_contributing": 0, "top_markets": [], "s_bar_without_top": None, "ok": False}
    top = max(counts.values())
    tied = sorted(m for m in markets if counts[m] == top)
    without = []
    for m in tied:
        means = cluster_means(events, without=m)
        without.append(math.fsum(means) / len(means) if means else None)
    worst = None if any(v is None for v in without) else min(without)
    ok = len(markets) >= MIN_MARKETS and worst is not None and worst > THRESHOLD_BP
    return {"markets_contributing": len(markets), "top_markets": tied, "s_bar_without_top": worst, "ok": ok}


# ---- resultat ----

def _rounded(x):
    if isinstance(x, float):
        return round(x, 9)
    if isinstance(x, dict):
        return {k: _rounded(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_rounded(v) for v in x]
    return x


def _sealed(result):
    out = _rounded(result)
    blob = json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    out["result_sha256"] = hashlib.sha256(blob).hexdigest()
    return out


def _counts(c, events, coverage, n_clusters):
    keys = ("market_hours_total", "market_hours_scanned", "missing_hours_no_scan", "missing_hours_late_scan",
            "missing_hours_error_scan", "events", "censored_t", "censored_t1", "no_baseline_hours", "deduped",
            "excluded_off_hours_t", "excluded_first_after_reopen", "excluded_off_hours_t1", "excluded_missing_t1",
            "duplicate_scans_dropped")
    out = {k: c[k] for k in keys}
    out["coverage"] = coverage
    out["cluster_days"] = n_clusters
    out["cluster_days_any_event"] = len({e["h"] // DAY for e in events})
    return out


def evaluate_world(world):
    """Domstraeet paa en afkodet verden. Foer fristen returneres kun antal (ordre 69 afsnit 0 punkt 4)."""
    events, c = find_events(world)
    total = c["market_hours_total"]
    coverage = c["market_hours_scanned"] / total if total else 0.0
    means = cluster_means(events)
    counts = _counts(c, events, coverage, len(means))
    base = {"schema": RESULT_SCHEMA, "world": world["world"], "label": LABEL, "counts": counts}
    deadline = world["lock_ts"] + DEADLINE_D * DAY
    if world["as_of_ts"] < deadline:
        return _sealed({**base, "status": "NOT_DUE", "verdict": None, "reason": "BEFORE_DEADLINE",
                        "deadline_ts": deadline})
    censored_share = c["censored_t"] / c["events"] if c["events"] else 0.0
    gate = robustness(events)
    test = one_sided_test(means) if len(means) >= 2 else None
    if test is None and coverage >= MIN_COVERAGE and len(means) >= MIN_CLUSTER_DAYS:
        raise LQ1InputError("umuligt: klynger uden test")           # kan ikke ske, men aldrig en stille dom
    verdict, reason = decide(coverage, len(means), censored_share, test or {"upper95": math.inf, "p": 1.0, "mean": 0.0},
                             gate["ok"])
    return _sealed({**base, "status": "OK", "verdict": verdict, "reason": reason, "alpha_F": ALPHA_F,
                    "mode": "BESKRIVENDE (alfa = 0)", "threshold_bp": THRESHOLD_BP, "censored_share": censored_share,
                    "test": test, "robustness": gate, "descriptive": _descriptive(events)})


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return math.fsum(xs) / len(xs) if xs else None


def _descriptive(events):
    """Kun beskrivende: S pr. marked, andel af overskuddet der er vaek efter en time og S ved fuld tilbagevenden.
    Selektion paa RT_t >= 3 x baseline giver regression mod middelvaerdien; `s_full_reversion_bp` viser loftet."""
    by = collections.defaultdict(list)
    for e in events:
        by[e["market"]].append(e)
    per_market = {}
    for m in sorted(by):
        rows = by[m]
        per_market[m] = {"events": len(rows),
                         "s_bar_bp": _mean([e["s"] for e in rows]),
                         "reverted_share": _mean([e["reverted"] for e in rows]),
                         "s_full_reversion_bp": _mean([e["full"] for e in rows])}
    return {"per_market": per_market, "event_mean_s_bp": _mean([e["s"] for e in events]),
            "note": "retningsdrift er ikke implementeret her (kraever felter, fixtures ikke har)"}


def evaluate_doc(doc):
    """Som evaluate_path, men paa et dokument i hukommelsen. Input-fejl giver status ERROR."""
    try:
        return evaluate_world(decode_fixture(doc))
    except LQ1InputError as e:
        return _error(str(e))


def _error(msg):
    return _sealed({"schema": RESULT_SCHEMA, "status": "ERROR", "verdict": None, "reason": "INPUT_ERROR",
                    "error": msg, "label": LABEL})


def evaluate_path(path):
    try:
        return evaluate_world(load_fixture(path))
    except LQ1InputError as e:
        return _error(str(e))


def main(argv):
    if len(argv) != 2:
        print("brug: lq1_evaluator.py <fixture.json>", file=sys.stderr)
        return 2
    result = evaluate_path(argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=1, sort_keys=True))
    return 0 if result["status"] != "ERROR" else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
