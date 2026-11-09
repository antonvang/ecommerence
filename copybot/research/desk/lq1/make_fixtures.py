"""Bygger de syntetiske LQ1-fixtures (lq1/fixtures/*.json). Ingen data, intet netvaerk; samme output hver gang.

Alle verdener er opdigtede: markederne hedder SYN_A.. og laasedatoen ligger i 2030. Intet er kalibreret efter observationer.
Normal time: RT = b * exp(0,15 z). Et brud ved t: RT_t = b * k, RT_t+1 = b + rho * (RT_t - b), saa
S = 1/2 (1 - rho) (k - 1) b. Med k ~ U(3,3; 5) er E[k] = 4,15.

Kor: python3 research/desk/lq1/make_fixtures.py
"""
from __future__ import annotations

import calendar
import json
import math
import os
import random

HERE = os.path.dirname(os.path.realpath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
LOCK = calendar.timegm((2030, 1, 7, 0, 0, 0))     # mandag 00:00 UTC; bevidst et aar uden data
AS_OF = LOCK + 99 * 86400
N_HOURS = 99 * 24 + 1
EQUAL_BASES = (8.0, 8.0, 8.0, 8.0)
MIXED_BASES = (4.0, 6.0, 8.0, 12.0)
K_LOW, K_HIGH = 3.3, 5.0
RHO_AT_THRESHOLD = 1.0 - 5.0 / (0.5 * (0.5 * (K_LOW + K_HIGH) - 1.0) * 8.0)  # E[S] = 5 bp ved b = 8


def _off_ranges():
    """48 timer hver uge (loerdag-soendag UTC), som et TradFi-marked uden for aabningstid."""
    out, i = [], 5 * 24                         # LOCK er en mandag, saa indeks 120 er loerdag 00:00
    while i < N_HOURS:
        out.append([i, min(i + 48, N_HOURS)])
        i += 7 * 24
    return out


def series(seed, market, base, p, rho, off=None, miss=0.0, thin_t=0.0, thin_t1=0.0):
    """Timeserie i 0,1 bp. Hver marked har sin egen tilfaeldighedsstroem."""
    rng = random.Random(f"{seed}:{market}")
    off_set = {i for a, b in (off or []) for i in range(a, b)}
    cells = [max(1, round(10 * base * math.exp(0.15 * rng.gauss(0, 1)))) for _ in range(N_HOURS)]
    i, spikes = 0, []
    while i < N_HOURS - 1:
        if i not in off_set and (i + 1) not in off_set and rng.random() < p:
            spikes.append(i)
            i += 9                              # brud taet paa hinanden ville blive fjernet af dedup alligevel
        else:
            i += 1
    for i in spikes:
        k = rng.uniform(K_LOW, K_HIGH)
        cells[i] = max(1, round(10 * base * k))
        cells[i + 1] = max(1, round(10 * (base + rho * (base * k - base)) * math.exp(0.05 * rng.gauss(0, 1))))
        if rng.random() < thin_t:
            cells[i] = "T"
        if rng.random() < thin_t1:
            cells[i + 1] = "T"
    if miss:
        cells = [None if rng.random() < miss else c for c in cells]
    return cells


def world(name, seed, bases=MIXED_BASES, p=1 / 120, rho=0.1, off_markets=(), miss=0.0, thin_t=0.0, thin_t1=0.0,
          per_market=None, note=""):
    markets = {}
    for j, base in enumerate(bases):
        m = "SYN_" + "ABCDEFGH"[j]
        off = _off_ranges() if j in off_markets else None
        kw = {"p": p, "rho": rho}
        kw.update((per_market or {}).get(m, {}))
        spec = {"series": series(seed, m, base, kw["p"], kw["rho"], off=off, miss=miss, thin_t=thin_t, thin_t1=thin_t1)}
        if off:
            spec["off_hours"] = off
        markets[m] = spec
    return {"synthetic": True, "schema": "lq1-fixture/1", "world": name, "seed": seed, "note": note,
            "lock_ts": LOCK, "as_of_ts": AS_OF, "first_h": LOCK, "markets": markets}


def small(name, cells, **extra):
    """Lille haandlavet verden til fejl- og graensetilfaelde."""
    doc = {"synthetic": True, "schema": "lq1-fixture/1", "world": name, "lock_ts": LOCK, "as_of_ts": AS_OF,
           "first_h": LOCK, "markets": {"SYN_A": {"series": cells}}}
    doc.update(extra)
    return doc


def all_fixtures():
    """Navn -> fixture-dokument. Dokumenter under `err_` er bevidst forkerte."""
    fx = {
        "world_null_persistent": world(
            "world_null_persistent", 7001, rho=1.0,
            note="H1 falsk: bruddet varer en time mere, S omkring 0. Forventet FALSIFIED."),
        "world_null_at_threshold": world(
            "world_null_at_threshold", 7002, bases=EQUAL_BASES, rho=RHO_AT_THRESHOLD,
            note="Sand S-middel = taerskel paa 5 bp. Maa ikke give PASS oftere end alfa."),
        "world_effect": world(
            "world_effect", 7003, off_markets=(2, 3),
            note="Bruddet er vaek efter en time (rho 0,1). S langt over 5 bp. Forventet PASS."),
        "world_one_market_dominates": world(
            "world_one_market_dominates", 7004, bases=(40.0, 6.0, 8.0, 12.0), rho=1.0,
            per_market={"SYN_A": {"p": 1 / 24, "rho": 0.1}, "SYN_B": {"p": 1 / 400}, "SYN_C": {"p": 1 / 400},
                        "SYN_D": {"p": 1 / 400}},
            note="Alt kommer fra et marked. Testen bestaar, porten ikke. Forventet INCONCLUSIVE."),
        "world_too_few_events": world(
            "world_too_few_events", 7005, p=1 / 2200, note="Faa brud. Forventet UNTESTABLE."),
        "world_low_coverage": world(
            "world_low_coverage", 7006, miss=0.15, note="15 % af scanningerne mangler. Forventet INVALID."),
        "world_censored": world(
            "world_censored", 7007, thin_t=0.35, note="35 % af bruddene har censureret RT_t. Forventet INCONCLUSIVE_CENSORED."),
        "small_not_due": small("small_not_due", [80] * 200, as_of_ts=LOCK + 50 * 86400),
        "err_not_synthetic": small("err_not_synthetic", [80] * 5, synthetic=False),
        "err_negative_cell": small("err_negative_cell", [80, -5, 80]),
        "err_bad_cell_type": small("err_bad_cell_type", [80, "x", 80]),
        "err_lock_not_on_hour": small("err_lock_not_on_hour", [80] * 5, lock_ts=LOCK + 60),
        "err_unknown_market_key": {**small("err_unknown_market_key", [80] * 5),
                                   "markets": {"SYN_A": {"series": [80] * 5, "off_hour": [[0, 2]]}}},
        "err_offhours_out_of_range": {**small("err_offhours_out_of_range", [80] * 5),
                                      "markets": {"SYN_A": {"series": [80] * 5, "off_hours": [[0, 50]]}}},
    }
    missing = small("err_missing_field", [80] * 5)
    del missing["lock_ts"]
    fx["err_missing_field"] = missing
    return fx


def dump(doc):
    """Kanonisk tekst, saa samme verden altid giver samme bytes."""
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"


def main():
    os.makedirs(FIXTURES, exist_ok=True)
    for name, doc in sorted(all_fixtures().items()):
        path = os.path.join(FIXTURES, name + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(dump(doc))
        print(name, os.path.getsize(path))


if __name__ == "__main__":
    main()
