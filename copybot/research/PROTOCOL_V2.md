# Screening PROTOCOL v2 (binding, written before any v2 code or data run)

Status: binding for every catalogue experiment with id suffix `_p2`. PROTOCOL v1 and all `_p1` results stay exactly as
recorded. This protocol only adds requirements; it cannot make an experiment pass that v1 rejected.

Motivation (research/MISSION6_FLEET_RUN.md): under v1 the one screen pass depended on run order (DSR 0.988 with the 4
trials recorded at that moment, 0.869 with all 10), its selected train variant did not beat buy-and-hold on train, and
a block-shuffled placebo beat it 92 % of the time on train.

## Unchanged from v1

Universe (8 Binance USD-M perps, 1h), windows (train 2023-01..08, validation 2023-09..12, holdout 2024 sealed,
2025+ reserved), fixed two-variant grids, cost model (taker 0.05 %, half-spread 0.02 % ESTIMATE, slippage 0.02 %
ESTIMATE, settled funding), equal-weight buy-and-hold benchmark, bootstrap (5-day moving blocks, 2,000 draws, seed 7),
alpha ledger 0.005 per experiment, holdout and paper rules (human approvals, holdout opened once).

## Changes

### 1. Train gate (before adversarial and validation)

The selected variant (best train net Sharpe) must have train net Sharpe > 0 **and** above the buy-and-hold benchmark's
train net Sharpe. Otherwise: REJECTED at the train gate. No validation data is read.

### 2. Pre-validation adversarial gate

Before any validation data is read, all of these must hold on train:
- look-ahead truncation test and future-poison test exact for every symbol;
- data coverage >= 99 %, no duplicates, monotonic timestamps (train and validation quality files);
- block-shuffled placebo (24-bar blocks, 60 draws, seed 17): share of placebos with net Sharpe >= the actual
  net Sharpe **< 0.10**.

Otherwise: REJECTED before validation. No validation data is read.

### 3. Batch-level deflated Sharpe (order-independent)

- Experiments are registered in **batches**: every approved DISCOVERED `_p2` instance found in one strategy pass forms
  one batch. The batch is logged as an event `batch.registered` with its experiment ids and a trial cutoff (the highest
  trials-ledger id at registration).
- No validation job of a batch may run until **every** member of the batch has finished its cost step (job
  dependencies). If any member's cost job fails permanently, the whole batch's validation is cancelled (fail-closed;
  an operator re-queues).
- The DSR trial set for a batch member = every trials-ledger row with id <= the cutoff (all earlier batches, including
  all v1 trials on the same data) **plus** every row of the batch's own members. Rows written later by other batches
  are excluded. The trial set is therefore identical for every member and independent of execution order.

### 4. Validation gates (unchanged list, DSR per section 3)

Net mean daily > 0; one-sided 90 % block-bootstrap lower bound > 0; net Sharpe > buy-and-hold; net total > 0 at 2x
costs; DSR probability >= 0.95.

## What this implies right now (stated before running anything)

- The graveyard suppresses `_p2` instances of every mechanism already rejected (day_of_week, hour_of_day,
  funding_contrarian, daily_reversal, donchian_trend). They are not re-tested on the same data.
- Only `vol_managed_long_p2` can be discovered. Its v1 train figures (same code path, same data) were: selected variant
  train net Sharpe 0.01 vs buy-and-hold 0.42, placebo p 0.92. If those figures reproduce, v2 rejects it at the train
  gate. This is stated in advance so the outcome cannot be reinterpreted afterwards.
- New hypotheses added to the catalogue later run under v2.

## Amendment 1 (2026-10-17, before any v2 run on real data; found by the v2 tests)

The text above contradicted itself: section 2 listed validation-file quality as a pre-validation check, while sections
1-2 promise that no validation data is read before the gates pass. In v1 the data step read both train and validation
files for quality checks. Resolution, strictly in the direction of reading less:

- the v2 data step reads and quality-checks **train only**;
- validation files are read for the first time inside the validation step, after the train and pre-validation gates
  passed; their quality (coverage >= 99 %, no duplicates, monotonic) becomes an additional validation gate
  ("validation data quality").

Observation recorded with this amendment (fixture tests, not real data): because the batch trial set pools all members,
very different strategies in one batch widen the dispersion of trial Sharpes and raise the DSR hurdle for every member.
This is the intended, stricter behaviour; it is not adjusted.
