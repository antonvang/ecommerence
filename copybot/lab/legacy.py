"""Read-only import of the research history into the registry (ENGINE_PROPOSAL.md §3.1, stage S1).

Each idea is recorded once, with its final state, its verdict as written in the cited documents, and evidence pointers
(path, commit, git blob hash), so that `lab verify` can prove the cited text existed at that commit. Nothing in the
cited files, the running processes or pm_lp_v1 is read for writing or changed. EXTERNAL entries are mirrors only.
"""
from __future__ import annotations

import time

from lab.registry import blob_at, fingerprint, last_commit

ACTOR = "legacy-import"

#  id, title, mechanism_tag, instrument, horizon, execution, final_state, label, verdict, evidence paths
HISTORY = [
    ("L01_copy_kol", "Copy leaderboard (KOL) wallets", "copy_trading", "solana_memecoins", "seconds", "taker_copy",
     "REJECTED", "LEGACY", "FAIL vs agreed criteria: 114 copied trades over 14 days; even at 0 s and zero fees -6.5 %/trade",
     ["FORSKNING.md", "research/NEXT_CANDIDATES.md"]),
    ("L02_self_found_traders", "Self-found profitable traders, copied with delay", "copy_trading", "solana_memecoins",
     "seconds", "taker_copy_delayed", "REJECTED", "LEGACY",
     "FAIL: their own returns persist (rank corr. +0.43) but copying 2 s later loses -7 %/trade",
     ["FORSKNING.md", "research/NEXT_CANDIDATES.md"]),
    ("L03_sol_trend_hourly", "SOL hourly trend rules", "trend_following", "sol_spot", "hours", "taker", "REJECTED",
     "LEGACY", "FAIL: all rules lost to trading costs over 7 months", ["FORSKNING.md"]),
    ("L04_buy_graduations", "Buy pump.fun graduations", "memecoin_launch_selection", "pumpfun_graduations", "minutes",
     "taker", "REJECTED", "LEGACY", "FAIL: 443 coins, all variants negative; median -95 % within one hour",
     ["FORSKNING.md"]),
    ("L05_graduation_sniper", "Graduation sniper (historical + live paper)", "speed_onchain_sniping",
     "pumpfun_graduations", "seconds", "taker", "REJECTED", "LEGACY",
     "FAIL: pre-registered 60 s rule -1.9 to -2.8 % on 279 unseen pools; live paper -10 to -15 %/trade (149 trades/rule)",
     ["FORSKNING.md", "research/NEXT_CANDIDATES.md"]),
    ("L06_short_new_hl_listings", "Short new Hyperliquid listings", "short_new_listings", "hyperliquid_perps", "days",
     "taker", "RETIRED", "LEGACY", "INSUFFICIENT: n = 23; mean -5.6 % (30 d); 7 of 23 doubled", ["FORSKNING.md"]),
    ("L07_funding_carry_v0", "Funding carry, first version (not pre-registered)", "funding_carry", "hyperliquid_perps",
     "weeks", "taker", "RETIRED", "LEGACY",
     "INVALID TEST: not pre-registered, survivorship, no spot leg; superseded by carry_v1",
     ["research/FUNDING_AUDIT.md", "FORSKNING.md"]),
    ("L08_funding_carry_leverage", "Funding carry with leverage", "funding_carry_leverage", "hyperliquid_perps", "weeks",
     "taker", "REJECTED", "LEGACY", "FAIL: 2x +7.2 %/yr, 3x +4.6 %, 5x -1.6 %, 10x -16.4 % (liquidations)",
     ["FORSKNING.md"]),
    ("L09_stop_when_ahead", "Stop-when-ahead overlay on sniper trades", "stop_rule_overlay", "pumpfun_graduations",
     "minutes", "taker", "REJECTED", "LEGACY", "FAIL: reaching the target often does not change the negative expectancy",
     ["FORSKNING.md"]),
    ("L10_launch_v1", "Launch selection from early flow (pre-registered)", "memecoin_launch_selection",
     "pumpfun_graduations", "minutes", "taker", "REJECTED", "LEGACY", "REJECTED: positive on train, collapsed on validation",
     ["research/HYPOTHESES.md", "research/RESULTS_launch_v1.md"]),
    ("L11_smart_v2", "Early buyers' track record (pre-registered, holdout)", "smart_money_following",
     "pumpfun_graduations", "minutes", "taker", "REJECTED", "LEGACY",
     "REJECTED: holdout -4.7 to -25.6 %; no positive hypothesis even on train",
     ["research/HYPOTHESES.md", "research/RESULTS_smart_v2.md"]),
    ("L12_arb_v1", "SOL/USDC Raydium v4 vs PumpSwap arbitrage", "dex_pool_arbitrage", "sol_usdc_pools", "slots", "taker",
     "REJECTED", "LEGACY", "REJECTED: 0 executable opportunities; max gap 0.222 % vs 0.525 % fees",
     ["research/HYPOTHESES.md", "research/RESULTS_arb_v1.md"]),
    ("L13_carry_v1", "Delta-neutral funding carry, Hyperliquid spot + perp", "delta_neutral_funding_carry",
     "hyperliquid_spot_perp", "weeks", "taker", "REJECTED", "LEGACY",
     "FAIL: development mean -0.08 %; holdout +4.35 % but decaying",
     ["research/CARRY_SPEC.md", "research/CARRY_FROZEN.md", "research/RESULTS_carry_v1.md"]),
    ("L14_tsmom_v1", "Weekly time-series momentum BTC/ETH/SOL", "time_series_momentum", "btc_eth_sol", "weeks", "taker",
     "REJECTED", "LEGACY", "FAIL (G2, G3): holdout Sharpe 0.54 vs buy-and-hold 0.32; LB -0.72 %/week; 146 < n_req 221",
     ["research/TSMOM_SPEC.md", "research/TSMOM_FROZEN.md", "research/RESULTS_tsmom_v1.md"]),
    ("L15_tsmom_v2", "Diversified time-series momentum", "time_series_momentum_diversified", "crypto_top20", "weeks",
     "taker", "WITHDRAWN", "LEGACY", "NOT TESTABLE: n_req 93-1,512 weeks vs at most 94 untouched weeks",
     ["research/TSMOM_V2_PROPOSAL.md"]),
    ("L16_pmcal_v1", "Polymarket favourite/longshot calibration", "prediction_market_calibration", "polymarket_binary",
     "days", "taker", "REJECTED", "LEGACY", "FAIL: validation -3.43 %/event; holdout -8.68 %/event; 0/7 gates",
     ["research/PMCAL_SPEC.md", "research/PMCAL_FROZEN.md", "research/RESULTS_pmcal_v1.md"]),
    ("L17_p1_btc15m_model", "15-min BTC up/down: TWAP model vs market", "short_horizon_crypto_binary_model",
     "polymarket_btc_15m", "minutes", "taker", "REJECTED", "EXPLORATORY",
     "REJECTED: all 12 variants negative (-1.3 to -17.6 %/trade); data gate 84 % < 95 %",
     ["research/PRELIM_2026-10-17.md", "research/MISSION2_DECISION.md"]),
    ("L18_p2_negrisk_arb", "Polymarket negRisk sum-of-prices arbitrage", "negrisk_sum_arbitrage", "polymarket_negrisk",
     "instant", "taker", "REJECTED", "EXPLORATORY", "REJECTED: 0 opportunities in about 7,600 events in each of 2 snapshots",
     ["research/PRELIM_2026-10-17.md", "research/MISSION2_DECISION.md"]),
    ("L19_p3_maker_fills", "Historical passive fills to resolution", "maker_adverse_selection_measurement",
     "polymarket_binary", "to_resolution", "maker", "RETIRED", "EXPLORATORY",
     "INCONCLUSIVE: -0.39 cents/share at resolution (99 % bounds -6.6 / +4.1)",
     ["research/PRELIM_2026-10-17.md", "research/MISSION2_DECISION.md"]),
    ("L20_m1_orderflow", "Order-flow imbalance, BTC perp", "orderflow_imbalance", "btc_perp", "minutes", "taker",
     "REJECTED", "EXPLORATORY", "REJECTED: 36 variants net -11.4 to -12.6 bp; gross about 0",
     ["research/MISSION3_REGISTRATION.md", "research/MISSION3_FAST_SCREEN.md"]),
    ("L21_m2_liquidation_reversal", "Liquidation-cascade reversal, BTC perp", "liquidation_cascade_reversal", "btc_perp",
     "minutes", "taker", "REJECTED", "EXPLORATORY", "REJECTED: 18 variants net negative; best gross +7.2 bp vs 20 bp cost",
     ["research/MISSION3_REGISTRATION.md", "research/MISSION3_FAST_SCREEN.md"]),
    ("L22_m3_premium_convergence", "Perpetual premium convergence", "perp_premium_convergence", "btc_perp_spot",
     "minutes", "taker", "REJECTED", "EXPLORATORY", "REJECTED: 6 variants net -31.6 to -33.4 bp",
     ["research/MISSION3_REGISTRATION.md", "research/MISSION3_FAST_SCREEN.md"]),
    # mirrors of things that run outside the lab: never changed by the lab
    ("X01_pm_lp_v1", "Polymarket liquidity-reward provision (observational)", "venue_subsidy_liquidity_rewards",
     "polymarket_reward_markets", "days", "maker", "EXTERNAL", "EXTERNAL",
     "RUNNING outside the lab: D0 2026-10-17; dev/val evaluation after 2026-10-30; holdout to 2026-11-13; tail to 2026-11-27",
     ["research/PM_LP_SPEC.md", "research/PM_LP_START.md", "research/pm_lp.py"]),
    ("X02_copybot_paper", "Copy-bot live paper test (video rule)", "copy_trading", "solana_memecoins", "seconds",
     "taker_copy_live", "EXTERNAL", "EXTERNAL", "RUNNING outside the lab (paper.py); judged by daily_check.py criteria",
     ["paper.py", "daily_check.py"]),
    ("X03_funding_live_v0", "Original funding live paper test (short perp only)", "funding_carry", "hyperliquid_perps",
     "weeks", "taker_live", "EXTERNAL", "EXTERNAL",
     "RUNNING outside the lab (funding.py); not delta-neutral; criterion: positive after fees two full weeks in a row",
     ["funding.py", "daily_check.py"]),
]


def evidence_for(paths):
    out = []
    for p in paths:
        c = last_commit(p)
        out.append({"path": p, "commit": c, "blob": blob_at(c, p) if c else None})
    return out


def import_legacy(db, actor=ACTOR):
    """Idempotent: existing ids are skipped. Returns (imported, skipped)."""
    imported, skipped = [], []
    for (eid, title, tag, instrument, horizon, execution, final, label, verdict, paths) in HISTORY:
        if db.one("SELECT 1 FROM experiments WHERE exp_id=?", eid):
            skipped.append(eid)
            continue
        ev = evidence_for(paths)
        if any(e["blob"] is None for e in ev):
            missing = [e["path"] for e in ev if e["blob"] is None]
            raise RuntimeError(f"{eid}: evidence not committed: {missing}")
        now = int(time.time())
        spec = {"title": title, "instrument": instrument, "horizon": horizon, "execution": execution,
                "sources": paths, "imported": True}
        with db.tx():
            db.append("experiments", exp_id=eid, version=1, created_ts=now, mechanism_tag=tag,
                      fingerprint=fingerprint(tag, instrument, horizon, execution), spec_json=spec,
                      spec_path=paths[0], spec_commit=ev[0]["commit"], code_hash=None, note="legacy import")
            db.append("transitions", exp_id=eid, ts=now, from_state=None, to_state=final, actor=actor,
                      reason="imported from the research record (state as documented)", evidence={"files": ev})
            db.append("results", exp_id=eid, version=1, ts=now, label=label, verdict=verdict, metrics={},
                      evidence={"files": ev}, supersedes=None)
            db.event("legacy.imported", actor, eid, {"state": final, "verdict": verdict})
        imported.append(eid)
    return imported, skipped


def verify_evidence(db):
    """Every cited (path, commit, blob) must still resolve in git. Returns a list of problems."""
    import json
    bad = []
    for r in db.q("SELECT exp_id, evidence FROM results"):
        for e in (json.loads(r["evidence"] or "{}").get("files") or []):
            if blob_at(e["commit"], e["path"]) != e["blob"]:
                bad.append((r["exp_id"], e["path"]))
    return bad
