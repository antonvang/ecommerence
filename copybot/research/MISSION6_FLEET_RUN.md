# Mission 6: first measured fleet run (2026-10-17)

All figures are EXPLORATORY backtests on historical data. Nothing here is paper trading or real-money profit.
**Real account profit: ikke tilgængelig** (no account, broker or live path exists).

## What ran

- **Approvals.**
  - Six catalogue templates were approved for exploratory screening only, on the 2023 train and validation windows. I approved them on the user's behalf, following the Mission 6 instruction to run a continuous research loop.
  - The reason text of every approval says so explicitly. Approvals are bound to the committed `lab/engine/catalogue.py` (commit a3b6ca9).
  - They can be revoked with `py -m lab revoke-template`.
  - Opening a holdout and starting paper trading still require the user's own approval.
- **Fleet.**
  - The fleet was started by hand with `py -m lab fleet --duration 1500` (25 min, manual and bounded), plus `py -m lab web` for the dashboard.
  - No scheduled task and no autostart. The S7 gate is unchanged (closed).
- **Discovery.**
  - The catalogue agent proposed 6 hypotheses.
  - The graveyard suppressed `donchian_trend`, because time-series momentum is already rejected as L14/L15.
  - The strategy agent registered the other 5, which created 30 jobs.

## Measured throughput (from the jobs table and trials ledger)

| | |
|---|---|
| Jobs | 30 done, 0 failed, 0 retries, 0 timeouts |
| Wall time, first claim → last completion | 213.6 s (includes downloading 192 monthly files, 7.4 MB) |
| Tests | 14 (10 variant evaluations + 4 validation runs) → about 3.9 tests/min while active |
| Mean job time | data 34.2 s (first one 118.5 s: download) · backtest 7.5 s · cost 4.6 s · adversarial 14.5 s · validate 1.3 s · report 0.4 s |
| Parallelism | 2 shared compute slots; data, backtest and adversarial ran at the same time |

The bottleneck is the size of the catalogue (5 experiments × 2 variants), not compute. More throughput would need more pre-registered hypotheses, not more workers.

## Results (validation window 2023-09..12; benchmark = equal-weight buy-and-hold of the same 8 perps)

Buy-and-hold over the validation window had net Sharpe 4.07 and net total 65.1 %. It was a strong rally.

| Experiment | Train net Sharpe (selected) | Validation net Sharpe | Validation 95 % CI, mean/day | DSR (as recorded) | Verdict |
|---|---|---|---|---|---|
| vol_managed_long | 0.01 | 4.34 | [0.12 %, 0.75 %] | 0.988 (4 trials) | **SCREEN_PASSED** |
| day_of_week | 0.18 | 2.68 | [0.04 %, 0.71 %] | 0.758 | REJECTED (DSR, below buy-and-hold) |
| hour_of_day | −1.24 (gross 6.30) | — | — | — | REJECTED at cost check |
| funding_contrarian | 1.99 | −0.48 | [−0.13 %, 0.10 %] | 0.051 | REJECTED (5 gates) |
| daily_reversal | 1.37 | 0.91 | [−0.05 %, 0.11 %] | 0.201 | REJECTED (4 gates incl. adversarial) |

### The one pass is weak

`E_vol_managed_long_p1` passed every pre-registered gate as they were applied. The recorded result is unchanged. But:

1. **DSR depends on run order.**
   - The protocol computes the deflated Sharpe "given all trials recorded so far". When this experiment validated, only 4 trials existed.
   - With all 10 trials of the batch, the same Sharpe gives DSR **0.869**, below the 0.95 gate.
2. **Selection on train was a coin flip.**
   - The selected variant had a train net Sharpe of 0.01; buy-and-hold had 0.42.
   - On train, the block-shuffled placebo beat it 92 % of the time (p = 0.92). Delaying it by one bar turned its Sharpe negative.
3. **It is mostly beta.**
   - It is long-only with 75 % average exposure, during a rally where buy-and-hold made more money (65 % vs 48 % net).
   - Its Sharpe was only slightly higher (4.34 vs 4.07).

My assessment: this is very likely not an edge. The sealed 2024 holdout exists to answer exactly this. Opening it requires the user's approval (`SCREEN_PASSED → VALIDATION`), and I have not requested or opened it.

### A real bug, caught by the adversarial stage

- **Where.** `daily_reversal` started at `i >= 24`, so `bars[i - 25]` wrapped around to `bars[-1]`, the last bar of the window.
- **Effect.** That is look-ahead into the first daily return. It can change only the first z-decision of each symbol (day 31 of a window); on DOGEUSDT it changed one day of positions (24 bars).
- **How it was caught.** The future-poison test flagged it, as designed. Truncation sampling had missed it.
- **Fix.** The family now starts at `i >= 25`.
- **Regression test.** `FamiliesAreCausal` poisons every family at early and late cut points. I verified that it fails on the old code and passes on the fix.
- **Effect on the result.** The recorded rejection stands. It also failed the DSR, lower-bound and benchmark gates.
- **Approvals.** The catalogue changed, so every template approval is invalid until it is approved again (by design).

## Proposed protocol amendment (needs the user's decision; not applied)

PROTOCOL v2 would:
- compute DSR against all trials in the batch, after every experiment in the batch has run its cost step, so the verdict does not depend on order;
- require the selected train variant to beat buy-and-hold net Sharpe on train, and a placebo p < 0.10, before validation.

v1 results stay as recorded. A v2 run would be new experiments (`_p2`) with new approvals.

## PROTOCOL v2 run (2026-10-17, 13:17 UTC)

- **Approval.** The user asked for the approval code for `vol_managed_long` under v2. The first code (12:42 UTC) expired unconfirmed, and the watcher stopped the fleet. A second code was issued at 13:07 UTC. At the user's explicit chat instruction, Claude ran `confirm-template` at 13:17:08 UTC. An `approval.note` event by `agent:claude` records this.
- **Discovery.** The catalogue agent discovered `E_vol_managed_long_p2`. The graveyard suppressed the other five `_p2` instances (day_of_week, hour_of_day, funding_contrarian, daily_reversal, donchian_trend), as stated in advance in PROTOCOL_V2.md.
- **Batch.** `B-d3555a7194bf` = [`E_vol_managed_long_p2`], trial cutoff id 10.
- **Result.** **REJECTED at train gate.**
  - Selected variant (7-day lookback): train net Sharpe 0.0095, against buy-and-hold at 0.415.
  - Both variants' trial Sharpes reproduce the v1 values bit for bit (0.000498 and −0.040738 per day).
  - Adversarial and validation steps were skipped. Validation data reads for p2: **0** (train reads: 128).
- **Prediction.** It matched the prediction committed before the run (PROTOCOL_V2.md, "What this implies right now").
- **Shutdown.** The watcher requested a graceful stop at 13:17:31 UTC, once all 6 jobs were done.

`E_vol_managed_long_p1` keeps its recorded v1 status (SCREEN_PASSED). Under v2 the same strategy does not pass the train gate. Whether to retire or withdraw p1 instead of spending the sealed 2024 holdout on it is the user's decision.

## E_vol_managed_long_p1 closed (2026-10-17, 13:33 UTC)

- **What changed.** At the user's decision, `E_vol_managed_long_p1` moved from SCREEN_PASSED to **REJECTED** through the two-step human approval. The code was requested at 13:25:15 UTC and confirmed at 13:33:00 UTC. At the user's explicit chat instruction, Claude executed the confirmation; an `approval.note` event records this.
- **Why REJECTED.** The lifecycle has no SCREEN_PASSED → WITHDRAWN edge. REJECTED was used rather than changing the locked state machine.
- **Unchanged.** The v1 result record (PASS screen) stays as recorded.
- **Evidence.** The cited evidence is research/PROTOCOL_V2.md and this file.
- **Holdout.** The sealed 2024 holdout was not opened and remains unused for every catalogue strategy.

State of the catalogue after Mission 6: every `_p1` and `_p2` experiment is REJECTED or SUPPRESSED. Nothing is in validation, paper or live.
