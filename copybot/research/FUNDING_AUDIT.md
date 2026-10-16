# Funding carry: phase 1 audit (16.10.2026)

Repository `C:\Users\anton\ecommerence`, branch `claude/why-cant-we-do-this-wh3ohb`, audited at commit
`26b9114bb3c9a8328a345295e5c21dca0d266af4`. Working tree clean. No result or locked file was changed by this audit.

## What exists

| Item | Where | Status |
|---|---|---|
| Historical test (6 months, 40 perps, 25 weeks) | `%TEMP%\claude\cbdemo\funding_collect.py`, `funding_test.py`, `funding_lev.py`, `funding.pkl` | **Outside the repository, not committed, not reproducible from Git** |
| Reported result | `FORSKNING.md` sections 7–8 | +8.4 / +8.6 %/yr on capital, 0 of 24 losing weeks; leverage worse |
| Live paper test | `copybot/funding.py` (commit `93e9466`, 16.10 14:42), running since 16.10 14:40 | $1,000 paper, weekly top-5 > 10 %/yr, accrues Hyperliquid hourly funding |
| Live pass criterion | `daily_check.py` in `93e9466`: "positive after fees in at least 2 full weeks in a row" | Committed before live data accrued |
| Funding entry in `research/HYPOTHESES.md` | – | **None** |

## Pre-registration evidence

- **Historical test: NOT pre-registered.** The three rules were written in chat before the run, but nothing was
  committed before the result. Data fetched 14:33, script written 14:34 and edited after its first run (the first
  run covered only 6 weeks because newly listed perps shortened the common window; the fix changed the evaluated
  period). That is a bug fix, but it is a post-result change with no committed record.
- **Live test: partially pre-registered.** Rule and pass criterion were committed at 14:42, two minutes after the
  first live rotation (14:40) and after the historical result was known. No funding had accrued before the commit.

## Biases and missing pieces that can inflate returns

1. **Survivorship / selection.** The 40 perps were chosen by *today's* open interest and volume (≥ $5M). Perps that
   shrank or were delisted (56 of 234 are delisted, and their funding history is still available) are excluded.
2. **The strategy is not implementable as tested.** It assumes a spot leg. **None of the 5 coins the live test
   holds this week (CASHCAT, STRK, VVV, PONS, FIL) has a spot market on Hyperliquid**; only 10 of the 40 tested
   perps do (BTC, ETH, HYPE, ZEC, SOL, PUMP, ENA, WLD, XPL, AVAX). The live test therefore measures funding
   accrual on short perps only, i.e. a directional short position, **not** delta-neutral carry.
3. **No price or basis P&L.** Neither test models the spot–perp price difference at entry/exit, spot and perp
   bid-ask spreads, slippage, notional drift as prices move (funding is paid on current notional), rebalancing
   to stay hedged, or margin calls. The switch cost (0.2 %) is an estimate, not measured.
4. **Liquidation / margin.** The 1x short has liquidation risk on a +100 % move; the leverage test used daily
   highs only (no intraday path, no maintenance-margin detail).
5. **Single regime.** The 25 weeks (Apr–Oct 2026) are one market regime; funding is regime-dependent.
6. **Multiple attempts.** Funding carry is the 8th idea tested; within it, 3 rules plus 7 leverage variants were
   examined on the same data.
7. **Reconciliation is not independent.** Live funding was "verified 5/5 against Hyperliquid", but both sides came
   from the same Hyperliquid API, so it checks the bookkeeping, not the data source.

## Data available for a proper test (read-only checks done)

- Hyperliquid funding history from **2023-05-12**; only ~Apr–Oct 2026 has been examined. **2023-05 → 2026-03 has
  never been looked at** and can serve as an untouched holdout.
- Delisted perps still return funding history, so a point-in-time universe (as listed that week) is possible.
- Hyperliquid spot pairs (318 against stablecoins) with candles, so spot and perp prices for the same coin can be
  compared for the subset that has both.

## Statistical power (from the already-examined series; planning only)

Funding-only weekly return for the top-5 rule: mean 0.165 %, s.d. 0.117 % per week, so ~4 weeks would detect it
at 5 % / 80 % power. **This understates the real noise**: basis, spread and slippage variation is not in the old
data, so the required sample cannot be set until that variance is measured. The live criterion of "2 weeks" is
not based on power.

## Current evidence

- Backtested, funding only, selection-biased universe, not implementable for most coins: +8.6 %/yr. **Not a valid
  test of delta-neutral carry.**
- Live paper: funding accrual on short perps (no spot leg): +$0.05 funding vs $0.50 entry cost after ~5 hours.
- Verified live execution: **none.**

## Blockers needing a decision before phase 2

1. **Universe:** restrict to perps with a spot market on Hyperliquid (one venue, verifiable, genuinely hedged), or
   allow spot on another exchange (needs that exchange's data and transfer/custody costs; not verifiable here).
2. **Splits:** use the already-seen Apr–Oct 2026 as development only, and 2023-05 → 2026-03 (never seen) as the
   untouched holdout, followed by a new live paper period.
3. **The running live test** cannot be a test of the strategy as specified (no spot leg). Keep it unchanged as a
   record of its own pre-committed criterion, and run a separate spec-compliant paper test alongside it, or stop it.

## Outcome (same day)

The decisions in "Blockers" were approved; the binding specification is `CARRY_SPEC.md` and the result is
`RESULTS_carry_v1.md`: **FAIL** (development mean ≤ 0; holdout positive but G3 cannot be met, and the edge has
decayed). The spec-compliant live paper test was not started because it cannot change a FAIL verdict.
