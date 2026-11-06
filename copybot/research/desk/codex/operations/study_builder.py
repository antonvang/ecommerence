"""Deterministic synthetic proposals for the offline research runner.

Recipes and lookbacks are fixed before generation. Signals use only the
current/past price and funding history; no candidate is selected by its outcome.
The evaluator's weight-return model and the paper engine's quote/fill model
are different cost models and are not an exact return cross-check.
"""

import copy
import hashlib
import json
import math
import random
import re

START = 1_988_150_400  # 2033-01-01T00:00:00Z, deliberately synthetic time.
CADENCE_S = 60
ASSETS = ("SYN_A", "SYN_B")
RECIPES = tuple((recipe, lookback) for recipe in
                ("momentum", "reversal", "funding_carry")
                for lookback in (1, 3, 6))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def signals_from_history(recipe, lookback, mids, funding_rates):
    """Return one bounded signal per bar, excluding each bar's closing price.

``mids[i]`` is available at bar i's start. ``mids[i+1]`` and
``funding_rates[i]`` are that bar's outcomes and never enter its signal.
Funding carry uses only completed bars ``funding_rates[:i]``. The last
closing price is therefore unused by all returned signals.
"""
    if recipe not in ("momentum", "reversal", "funding_carry"):
        raise ValueError("unknown recipe")
    _integer(lookback, "lookback", 1, 1000)
    if not isinstance(mids, (list, tuple)) or not isinstance(funding_rates, (list, tuple)):
        raise ValueError("price and funding histories must be sequences")
    if len(mids) != len(funding_rates) + 1 or not 1 <= len(funding_rates) <= 1000:
        raise ValueError("one closing price is required after the last bar")
    if any(not _number(value) or value <= 0 for value in mids):
        raise ValueError("mid prices must be finite positive numbers")
    if any(not _number(value) for value in funding_rates):
        raise ValueError("funding rates must be finite numbers")
    values = []
    for i in range(len(funding_rates)):
        if recipe == "funding_carry":
            rates = funding_rates[max(0, i - lookback):i]
            raw = -math.fsum(rates) / len(rates) / 0.0001 if rates else 0.0
        elif i == 0:
            raw = 0.0
        else:
            raw = (mids[i] / mids[max(0, i - lookback)] - 1.0) / 0.01
            if recipe == "reversal":
                raw = -raw
        if not math.isfinite(raw):
            raise ValueError("signal calculation is not finite")
        values.append(min(1.0, max(-1.0, raw)))
    return values


def _market(seed, bars):
    rng = random.Random(seed)
    market = {}
    for j, asset in enumerate(ASSETS):
        mids = [100.0 + 60.0 * j]
        rates = []
        for i in range(bars):
            # Small bounded toy innovations, never sampled from market data.
            change = 0.00015 * math.sin(i / 13 + j) + rng.uniform(-0.003, 0.003)
            mids.append(mids[-1] * (1 + change))
            rates.append(0.00002 * math.sin(i / 7 + j) + rng.uniform(-0.00006, 0.00006))
        market[asset] = dict(mids=mids, funding_rates=rates)
    return market


def build_demo(study_id="demo", seed=52, bars=120, candidates=9):
    """Build 1–9 predeclared toy candidates and their immutable input content.

No approval is created. The enclosing runner decides what is authorized,
persists the plan and applies joint multiple-testing decisions after all jobs.
"""
    if (not isinstance(study_id, str) or len(study_id) > 128
            or re.fullmatch(r"[A-Za-z0-9_-]+", study_id) is None):
        raise ValueError("study_id must be 1–128 ASCII letters, digits, '_' or '-'")
    if type(seed) is not int:
        raise ValueError("seed must be an integer, not bool")
    _integer(bars, "bars", 1, 1000)
    _integer(candidates, "candidates", 1, len(RECIPES))
    market = _market(seed, bars)
    study = dict(schema_version=1, study_id=study_id, mode="synthetic",
                 created_at=START - CADENCE_S, alpha=0.05, q_fdr=0.1,
                 source=dict(kind="synthetic", seed=seed), candidates=[])
    for recipe, lookback in RECIPES[:candidates]:
        signal_key = f"{recipe}_l{lookback}"
        candidate_id = study_id + "_" + signal_key
        universe = {asset: dict(listed_from=START, delisted_at=None) for asset in ASSETS}
        protocol = dict(recipe=recipe, lookback=lookback, signal_key=signal_key,
                        rule="clip1", cost_bps=6.0, funding=True,
                        window=dict(start=START, end=START + bars * CADENCE_S),
                        cadence_s=CADENCE_S, universe=universe)
        signals = {asset: signals_from_history(recipe, lookback, data["mids"], data["funding_rates"])
                   for asset, data in market.items()}
        observations, events = [], []
        for i in range(bars):
            ts = START + i * CADENCE_S
            for asset in ASSETS:
                data = market[asset]
                mid, next_mid = data["mids"][i:i + 2]
                signal = signals[asset][i]
                rate = data["funding_rates"][i]
                observations.append(dict(ts=ts, asset=asset, ret=next_mid / mid - 1,
                    funding=rate, signals={signal_key: dict(value=signal, avail_ts=ts)}))
                # A two-bp quoted spread; execution pays the appropriate side.
                events.append(dict(key=f"{candidate_id}:{asset}:{ts}", ts=ts, asset=asset,
                    bid=mid * 0.9999, ask=mid * 1.0001, quote_ts=ts,
                    signal=signal, avail_ts=ts, funding_rate=rate))
        fixture = dict(fixture_id=candidate_id, cadence_s=CADENCE_S, alpha=study["alpha"],
            q_fdr=study["q_fdr"], window=copy.deepcopy(protocol["window"]),
            universe=copy.deepcopy(universe), hypotheses=[dict(hid=candidate_id,
                family=recipe, signal_key=signal_key, rule=protocol["rule"],
                cost_bps=protocol["cost_bps"], funding=protocol["funding"])],
            observations=observations, ledger_requests=[])
        protocol_input = {key: fixture[key] for key in
                          ("cadence_s", "window", "universe", "hypotheses", "alpha", "q_fdr")}
        fixture["lock"] = dict(protocol_sha256=_digest(protocol_input),
                               data_sha256=_digest(observations))
        paper_plan = dict(protocol_id=candidate_id, initial_cash=100000.0,
            max_gross_fraction=0.3, max_asset_fraction=0.1, fee_bps=5.0,
            max_drawdown_fraction=0.1, max_quote_age_s=60, allowed_assets=list(ASSETS))
        study["candidates"].append(dict(candidate_id=candidate_id, family=recipe,
            protocol=protocol, fixture=fixture, paper_plan=paper_plan, paper_events=events,
            terminal_marks={asset: market[asset]["mids"][-1] for asset in ASSETS}))
    # This also fails closed if a future change accidentally emits IEEE values.
    _canonical(study)
    return study
