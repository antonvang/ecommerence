"""Non-decisional research jobs from the scans (research/PROTOCOL_V3.md amendment 9 section 3).

- scan_digest (report-1, one per UTC day, job 'scan_digest|YYYY-MM-DD', queued from 00:30 UTC the day after): reads
  only the observations table, for the day (24 h) and the 7 d that end with it. Per detector, metric and instrument
  (or family, as the scanner recorded it): observations, flagged rows, distinct flagged clock hours, persistence, size
  against the threshold (median, p90), the detector's error rate and, for price gaps, the median |value| against a
  fixed cost reference. A fixed rule (below) records INVESTIGATE or NO_ACTION with its reason ->
  artifacts/_diagnostic/scanner/<day>.json and a research.digest event.
- scan_dossier (report-1, one per INVESTIGATE market.event key, job 'scan_dossier|<sha1 of the key>'): the same
  statistics for that key over 24 h and 7 d up to the scan that decided INVESTIGATE, plus its registry status (read
  only) -> artifacts/_diagnostic/scanner/dossier_<sha1>.json and a research.dossier event with a recommendation text.

Neither job registers an experiment, trades, changes a state, writes results/trials/transitions/approvals/alpha or
fetches data. A recommendation is text for a human, never an action: a test needs a new hypothesis family that the
user approves (amendment 8), and data from 2025 on is reserved, so a scanner finding can only be tested forward.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone

from lab import jobs, lifecycle, pipeline, registry, scanner
from lab.engine import catalogue

DAY, HOUR = 86400, 3600
SPAN_7D = 7 * DAY
DIGEST_DELAY_S = 1800       # the digest of day D is queued from D+1 00:30 UTC: the day's last scan has landed by then
MIN_FLAGGED_HOURS = 6       # INVESTIGATE: flagged in >= 6 distinct clock hours of the 24 h (1 in 4 hourly scans) ...
COST_MULT = 4.0             # ... and median flagged |value| >= 4x the cost reference: a price gap is only captured with
                            # two legs (two venues, or perp and spot), each entered and left = 4 taker fills
COST_REF = catalogue.COSTS["taker_fee"] + catalogue.COSTS["half_spread"] + catalogue.COSTS["slippage"]   # one fill
PRICE_GAPS = {"cross_venue_gap": "Hyperliquid mid / Binance perp mid - 1, a fraction of price",
              "perp_premium": "Binance mark / index - 1, a fraction of price"}
NO_COST_REF = {"median_gross_yield_day": "gross reward yield per day before adverse selection: an income rate, not a "
                                         "price gap",
               "negrisk_locked_profit": "USD at best-level size, already net of Polymarket taker fees: not a fraction "
                                        "of price",
               "identity_mismatch_suspected": "a data-identity check, never an opportunity"}
JOB = {"priority": 60, "max_attempts": 2, "timeout_s": 120}      # light, like diagnose (never HEAVY)
RULES = {"investigate": f"flagged in >= {MIN_FLAGGED_HOURS} distinct clock hours of the 24 h and median flagged "
                        f"|value| >= {COST_MULT:g}x the cost reference (price-gap metrics only); otherwise NO_ACTION",
         "cost_reference": COST_REF,
         "cost_reference_basis": "lab/engine/catalogue.py COSTS taker_fee + half_spread + slippage: one taker fill on "
                                 "a liquid Binance perp, as a fraction of notional (illiquid instruments cost more)",
         "cost_mult_basis": "two legs, each entered and left: 4 fills", "price_gap_metrics": PRICE_GAPS,
         "windows": "24 h = the UTC day, 7 d = the 7 days that end with it, both [start, end) on the scan clock",
         "persistence": "distinct flagged clock hours / distinct clock hours in which the detector scanned",
         "size_vs_threshold": "|value| / |threshold| over flagged rows; median and p90 by linear interpolation",
         "detector_error_rate": "share of the detector's scans with an error observation",
         "rounding": "sizes are rounded to 6 decimals before the rule compares them"}


def _r(x):
    return None if x is None else round(x, 6)


def _quant(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    i = int(pos)
    return xs[i] if i + 1 >= len(xs) else xs[i] + (xs[i + 1] - xs[i]) * (pos - i)


def _start(day):
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def _ymd(ts):
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def key_id(key):
    """sha1 of the market.event key (canonical JSON): the dossier's job id and artifact name."""
    return hashlib.sha1(json.dumps(key, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def cost_note(metric):
    return PRICE_GAPS.get(metric) or NO_COST_REF.get(metric) or "count or bookkeeping metric: no cost reference"


# ---------- statistics (observations table only) ----------
def _rows(db, a, b):
    """Observations with a <= ts < b: rows per (detector, metric, instrument) without error rows, and per detector the
    clock hours and scans it ran and the scans with an error."""
    keys, det = {}, {}
    for r in db.q("SELECT ts, detector, instrument, metric, value, threshold, flagged FROM observations "
                  "WHERE ts>=? AND ts<?", a, b):
        d = det.setdefault(r["detector"], (set(), set(), set()))
        d[0].add(r["ts"] // HOUR)
        d[1].add(r["ts"])
        if r["metric"] == "error":
            d[2].add(r["ts"])
        else:
            keys.setdefault((r["detector"], r["metric"], r["instrument"]), []).append(r)
    return keys, det


def _stats(rows, det, metric):
    hours_run, scans, errors = det or (set(), set(), set())
    flagged = [r for r in rows if r["flagged"]]
    hours = sorted({r["ts"] // HOUR for r in flagged})
    longest = run = 0
    for i, h in enumerate(hours):
        run = run + 1 if i and h == hours[i - 1] + 1 else 1
        longest = max(longest, run)
    size = [abs(r["value"]) / abs(r["threshold"]) for r in flagged if r["value"] is not None and r["threshold"]]
    s = {"observations": len(rows), "flagged": len(flagged), "flagged_clock_hours": len(hours),
         "scanned_clock_hours": len(hours_run),
         "persistence": _r(len(hours) / len(hours_run)) if hours_run else None, "longest_flagged_run_h": longest,
         "size_vs_threshold": {"median": _r(_quant(size, 0.5)), "p90": _r(_quant(size, 0.9))},
         "detector_error_rate": _r(len(errors) / len(scans)) if scans else None}
    if metric in PRICE_GAPS:
        med = _quant([abs(r["value"]) for r in flagged if r["value"] is not None], 0.5)
        s["median_abs_value"] = _r(med)
        s["vs_cost_reference"] = _r(med / COST_REF) if med is not None else None
    return s


def rule(s, metric):
    """The fixed decision rule on the 24 h statistics (a registered reading for a human, never a gate)."""
    h = s["flagged_clock_hours"]
    if not s["observations"]:
        return "NO_ACTION", "not observed in the 24 h"
    if not s["flagged"]:
        return "NO_ACTION", "never flagged in the 24 h"
    if h < MIN_FLAGGED_HOURS:
        return "NO_ACTION", (f"not persistent: flagged in {h} of the required {MIN_FLAGGED_HOURS} distinct clock hours "
                             f"in 24 h")
    if metric not in PRICE_GAPS:
        return "NO_ACTION", f"persistent ({h} clock hours in 24 h) but no trading-cost reference: {cost_note(metric)}"
    x = s.get("vs_cost_reference")
    if x is None:
        return "NO_ACTION", f"persistent ({h} clock hours in 24 h) but no flagged value to compare with the costs"
    if x < COST_MULT:
        return "NO_ACTION", (f"persistent ({h} clock hours in 24 h) but the median |value| is {x:.2f}x the cost "
                             f"reference, below {COST_MULT:g}x")
    return "INVESTIGATE", (f"persistent ({h} clock hours in 24 h) and the median |value| is {x:.2f}x the cost "
                           f"reference (>= {COST_MULT:g}x): candidate for a family draft, which needs a new family and "
                           f"the user's approval")


def _kstr(det, metric, inst):
    return f"{det}|{metric}|{'' if inst is None else inst}"


def digest(db, day):
    """Deterministic digest of one UTC day: the same observations always give the same bytes."""
    a = _start(day)
    end = a + DAY
    k24, d24 = _rows(db, a, end)
    k7, d7 = _rows(db, end - SPAN_7D, end)
    out = []
    for det, metric, inst in sorted(set(k7) | set(k24), key=lambda k: (k[0], k[1], "" if k[2] is None else k[2])):
        s24 = _stats(k24.get((det, metric, inst), []), d24.get(det), metric)
        decision, why = rule(s24, metric)
        out.append({"detector": det, "metric": metric, "instrument": inst, "24h": s24,
                    "7d": _stats(k7.get((det, metric, inst), []), d7.get(det), metric),
                    "cost_reference": COST_REF if metric in PRICE_GAPS else None, "cost_note": cost_note(metric),
                    "decision": decision, "why": why})
    inv = sum(1 for x in out if x["decision"] == "INVESTIGATE")
    return {"day": day, "windows": {"24h": [a, end], "7d": [end - SPAN_7D, end]}, "source": "observations table only",
            "decisional": False, "rules": RULES, "keys": out,
            "summary": {"keys": len(out), "keys_24h": sum(1 for x in out if x["24h"]["observations"]),
                        "investigate": inv, "no_action": len(out) - inv,
                        "observations_24h": sum(len(v) for v in k24.values()),
                        "scans_24h": {d: len(v[1]) for d, v in sorted(d24.items())},
                        "error_scans_24h": {d: len(v[2]) for d, v in sorted(d24.items())}}}


def step_digest(db, job, worker):
    day = (job.get("payload") or {}).get("day") or str(job.get("job_id") or "").split("|", 1)[-1]
    try:
        a = _start(day)
    except (TypeError, ValueError):
        raise pipeline.StepError(f"scan_digest needs a day YYYY-MM-DD, got {day!r}") from None
    if time.time() < a + DAY + DIGEST_DELAY_S:
        raise pipeline.StepError(f"{day} is not over (+{DIGEST_DELAY_S // 60} min): its scans may still land")
    out = digest(db, day)
    art = pipeline.save_artifact(os.path.join("_diagnostic", "scanner"), day, out)
    dec = {_kstr(x["detector"], x["metric"], x["instrument"]): [x["decision"], x["why"]] for x in out["keys"]}
    inv = [k for k, v in dec.items() if v[0] == "INVESTIGATE"]
    db.event("research.digest", f"system:{worker}", None, {"day": day, "keys": len(dec), "investigate": inv,
                                                          "keys_24h": out["summary"]["keys_24h"],
                                                          "decisions": dec, "decisional": False,
                                                          "observations_24h": out["summary"]["observations_24h"],
                                                          "artifact_sha256": art["sha256"]})
    return {"day": day, "keys": len(dec), "investigate": len(inv), "artifact": art}


# ---------- dossier of one INVESTIGATE key ----------
def _registry(db, eid):
    """Read-only registry status of the candidate the market.event names (no write, no transition)."""
    v = registry.latest(db, eid) if eid else None
    if v is None:
        return {"exp_id": eid, "state": None, "mechanism": None, "execution": None, "graveyard": [], "covering": []}
    spec = json.loads(v["spec_json"] or "{}")
    ex = spec.get("execution")
    return {"exp_id": eid, "state": lifecycle.state(db, eid), "mechanism": v["mechanism_tag"], "execution": ex,
            "graveyard": sorted(registry.graveyard(db, v["mechanism_tag"], ex, v["fingerprint"])),
            "covering": sorted(x for x in registry.covering(db, v["mechanism_tag"], ex, v["fingerprint"]) if x != eid)}


def recommend(reg, decision, why):
    """(advice code, text) in a fixed order: graveyard, covered, persistent above costs, keep observing. Never an
    action."""
    tail = " Non-decisional: nothing was registered, traded or changed."
    if reg["state"] in scanner.GRAVEYARD or reg["graveyard"]:
        return "graveyard", (f"graveyard ({', '.join(reg['graveyard'] or [str(reg['exp_id'])])}): the same mechanism "
                             f"was rejected or suppressed before; a new test needs a new family with a different "
                             f"mechanism and the user's approval." + tail)
    if reg["covering"]:
        return "covered", f"covered by {', '.join(reg['covering'])}: follow that experiment; no new draft." + tail
    if decision == "INVESTIGATE":
        return "family_draft", (f"{why}. A hypothesis-family draft (amendment 8) needs the user's approval; data from "
                                f"2025 on is reserved, so it can only be tested forward." + tail)
    return "observe", f"keep observing: {why}; the daily scan digest measures it again." + tail


def dossier(db, key, exp_id, scan_ts):
    """The digest statistics for one market.event key over the 24 h and 7 d up to the scan that decided INVESTIGATE.
    A key whose instrument is a family (the scanner's pricing-constraint proposals) covers every instrument of the
    detector and metric; the scope is recorded."""
    end = int(scan_ts) + 1
    det, metric, inst = key.get("detector"), key.get("metric"), key.get("instrument")
    k24, d24 = _rows(db, end - DAY, end)
    k7, d7 = _rows(db, end - SPAN_7D, end)
    family = not db.one("SELECT 1 FROM observations WHERE detector=? AND metric=? AND instrument=? LIMIT 1", det,
                        metric, inst)

    def pick(keys):
        return [r for (d, m, i), rs in keys.items() for r in rs if d == det and m == metric and (family or i == inst)]
    s24, s7 = _stats(pick(k24), d24.get(det), metric), _stats(pick(k7), d7.get(det), metric)
    meeting = []
    if family:                                   # judged per instrument: pooled rows are occurrences across coins,
        per = {i: rule(_stats(rs, d24.get(det), metric), metric)       # not persistence of one price relation
               for (d, m, i), rs in k24.items() if d == det and m == metric}
        meeting = sorted(str(i) for i, (dec, _) in per.items() if dec == "INVESTIGATE")
        decision = "INVESTIGATE" if meeting else "NO_ACTION"
        why = (f"{len(meeting)} of {len(per)} instruments meet the rule on their own: {', '.join(meeting)}" if meeting
               else f"no single instrument meets the rule on its own ({len(per)} instruments; the pooled numbers "
                    f"below are occurrences across instruments, not persistence)")
    else:
        decision, why = rule(s24, metric)
    reg = _registry(db, exp_id)
    advice, text = recommend(reg, decision, why)
    return {"key": key, "key_sha1": key_id(key), "anchor_scan_ts": int(scan_ts),
            "windows": {"24h": [end - DAY, end], "7d": [end - SPAN_7D, end]},
            "scope": "family: every instrument of the detector and metric" if family else "instrument",
            "instruments_flagged_7d": sorted({str(r["instrument"]) for r in pick(k7) if r["flagged"]}),
            "instruments_meeting_rule": meeting,
            "24h": s24, "7d": s7, "cost_reference": COST_REF if metric in PRICE_GAPS else None,
            "cost_note": cost_note(metric), "rule_decision": decision, "rule_why": why, "registry": reg,
            "advice": advice, "recommendation": text, "decisional": False, "rules": RULES,
            "source": "observations table and registry status (read only)"}


def step_dossier(db, job, worker):
    p = job.get("payload") or {}
    key = p.get("key")
    if not isinstance(key, dict) or not key.get("metric") or p.get("scan_ts") is None:
        raise pipeline.StepError("scan_dossier needs the market.event key and its scan_ts")
    out = dossier(db, key, p.get("exp_id"), p["scan_ts"])
    out["market_event_id"] = p.get("event_id")
    art = pipeline.save_artifact(os.path.join("_diagnostic", "scanner"), f"dossier_{out['key_sha1']}", out)
    db.event("research.dossier", f"system:{worker}", p.get("exp_id"),
             {"key": key, "key_sha1": out["key_sha1"], "advice": out["advice"], "recommendation": out["recommendation"],
              "rule_decision": out["rule_decision"], "registry_state": out["registry"]["state"],
              "flagged_clock_hours_7d": out["7d"]["flagged_clock_hours"], "decisional": False,
              "artifact_sha256": art["sha256"]})
    return {"key_sha1": out["key_sha1"], "advice": out["advice"], "artifact": art}


# ---------- queueing (strategy_pass) ----------
def enqueue(db, now=None, actor="strategy-1"):
    """The digest of the last UTC day that ended at least 30 min ago (only if it has observations), and one dossier per
    INVESTIGATE market.event key that has none. Reads only, unless a job is new. Returns the number of new jobs."""
    now = now or time.time()
    jobs.init(db)
    n = 0
    last_end = int(now - DIGEST_DELAY_S) // DAY * DAY
    for end in range(last_end - 6 * DAY, last_end + 1, DAY):   # the last 7 ended days: a stopped fleet catches up
        jid = f"scan_digest|{_ymd(end - DAY)}"
        if not db.one("SELECT 1 FROM jobs WHERE job_id=?", jid) and \
                db.one("SELECT 1 FROM observations WHERE ts>=? AND ts<? LIMIT 1", end - DAY, end):
            n += jobs.enqueue(db, jid, "scan_digest", None, {"day": _ymd(end - DAY)}, actor=f"system:{actor}",
                              not_before=end + DIGEST_DELAY_S, **JOB)[1]
    seen = set()
    for r in db.q("SELECT id, ts, exp_id, payload FROM events WHERE kind='market.event' AND actor=? AND "
                  "json_extract(payload, '$.decision')='INVESTIGATE' ORDER BY id", scanner.ACTOR):
        p = json.loads(r["payload"])
        if not isinstance(p.get("key"), dict) or key_id(p["key"]) in seen:
            continue
        kid = key_id(p["key"])
        seen.add(kid)
        if db.one("SELECT 1 FROM jobs WHERE job_id=?", f"scan_dossier|{kid}"):
            continue
        n += jobs.enqueue(db, f"scan_dossier|{kid}", "scan_dossier", None,
                          {"key": p["key"], "exp_id": r["exp_id"], "event_id": r["id"],
                           "scan_ts": p.get("scan_ts") or r["ts"]}, actor=f"system:{actor}", **JOB)[1]
    return n


# ---------- Danish feed texts (lab/command.feed; the stored events stay as written) ----------
METRIC_DA = {"cross_venue_gap": "prisforskel Hyperliquid/Binance", "perp_premium": "perp-præmie mod indeks",
             "median_gross_yield_day": "belønningsafkast pr. dag (brutto)",
             "negrisk_locked_profit": "negRisk låst gevinst", "configured_pool_usd_day": "belønningspulje pr. dag",
             "identity_mismatch_suspected": "mistænkt forkert instrument",
             "coins_compared": "mønter sammenlignet", "symbols_compared": "symboler sammenlignet",
             "events_checked": "begivenheder tjekket", "error": "datafejl"}
WHY_DA = ((r"^waiting for persistence: flagged in (\d+) of the required (\d+) clock hours within 24 h",
           r"venter på vedvarenhed: markeret i \1 af de krævede \2 klokketimer inden for 24 timer"),
          (r"^graveyard match (.+?): suppressed as (\S+)", r"kirkegård: matcher \1, sorteret fra som \2"),
          (r"^graveyard: (\S+) is (\w+)", "kirkegård: {0} er {1}"),
          (r"^already registered: (\S+) is (\w+)", "allerede registreret: {0} er {1}"),
          (r"^covered by active experiment (\S+)", r"dækket af aktivt eksperiment \1"),
          (r"^new candidate (\S+); a test needs a pre-registered forward template",
           r"ny kandidat \1; en test kræver en forhåndsregistreret fremadtest-skabelon"),
          (r"^new candidate ", "ny kandidat "),
          (r"^data source failed: ", "datakilde fejlede: "),
          (r"detector failed: ", "detektor fejlede: "))
LESSON_DA = ((r"^no edge: net total <= 0 on validation", "ingen fordel: nettoafkastet i alt er <= 0 i valideringen"),
             (r"^no edge: net total <= 0", "ingen fordel: nettoafkastet i alt er <= 0"),
             (r"^unstable: positive in fewer than (\d+) of (\d+) chronological thirds",
              r"ustabil: positiv i færre end \1 af \2 tidsmæssige tredjedele"),
             (r"^concentrated: the best (\d+) days carry (\S+) of positive net",
              r"koncentreret: de \1 bedste dage står for \2 af det positive nettoafkast"),
             (r"^rarely active: a non-zero net on only (\S+) of days \(small effective sample\)",
              r"sjældent aktiv: nettoafkast forskelligt fra 0 på kun \1 af dagene (lille effektiv stikprøve)"),
             (r"^beaten by buy-and-hold over the same period", "slået af køb-og-hold i samme periode"),
             (r"^failed only the luck check \(multiple testing\)", "fejlede kun held-tjekket (mange forsøg)"),
             (r"^no single weakness flagged by these rules", "ingen enkelt svaghed fundet af disse regler"),
             (r"^no recorded validation series", "ingen registreret valideringsserie"),
             (r"^no edge", "ingen fordel"), (r"^unstable", "ustabil"), (r"^concentrated", "koncentreret"),
             (r"^rarely active", "sjældent aktiv"))
ADVICE_DA = {"graveyard": "på kirkegården: samme mekanisme er afvist før; en ny test kræver en ny familie og din "
                           "godkendelse",
             "covered": "dækket af et aktivt eksperiment: følg det",
             "family_draft": "vedvarende over omkostningerne: kandidat til et familieudkast (kræver din godkendelse)",
             "observe": "endnu ikke vedvarende over omkostningerne: måles videre i døgnoverblikket"}


def metric_da(m):
    return METRIC_DA.get(m, m or "")


def why_da(text, states=None):
    """A scanner reason in Danish; numbers and ids are kept, an unknown text is returned unchanged."""
    s = str(text or "")
    for pat, rep in WHY_DA:
        if "{0}" in rep:
            m = re.match(pat, s)
            if m:
                s = rep.format(m[1], (states or {}).get(m[2], m[2])) + s[m.end():]
        else:
            s = re.sub(pat, rep, s, count=1)
    return s


def lesson_da(text):
    """A diagnose lesson (lab/diagnose.py) in Danish; numbers are kept, only the first matching rule applies."""
    s = str(text or "")
    for pat, rep in LESSON_DA:
        t, n = re.subn(pat, rep, s, count=1)
        if n:
            return t
    return s


def _what(k):
    det, metric, inst = (str(k).split("|", 2) + ["", ""])[:3]
    return f"{metric_da(metric)} {inst}".strip()


def digest_da(p):
    inv = p.get("investigate") or []
    names = ", ".join(_what(k) for k in inv[:3]) + (f" og {len(inv) - 3} flere" if len(inv) > 3 else "")
    n = p.get("keys_24h", p.get("keys", 0))
    return (f"Døgnoverblik over søgningen {p.get('day')}: {n} målte serier i døgnet · {len(inv)} undersøges"
            + (f" ({names})" if inv else "") + f" · {n - len(inv)} ingen handling (afgør intet)")


def dossier_da(p):
    k = p.get("key") or {}
    return (f"Dossier: {metric_da(k.get('metric'))} {k.get('instrument') or ''} - "
            f"{ADVICE_DA.get(p.get('advice'), p.get('advice'))} (afgør intet)")
