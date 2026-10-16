# Pre-registered hypotheses: launch selection (v1, written 16.10.2026 before any result was seen)

Question: can information observable shortly after a pump.fun graduation select a subset of launches with positive
expected return **after realistic execution costs**?

## Data and split

- All pump.fun graduations (PumpSwap pool, ≥ 50 SOL at migration) in the 14 days before the build, evenly sampled
  in time (every k-th graduation), target 600 pools. Built by `research/launch_data.py`.
- Chronological split by graduation time: **train** = first 50 %, **validation** = next 25 %, **test** = last 25 %.
  The test period is not looked at until the rules are frozen after validation.

## Execution model (same for every hypothesis)

- Decision at `D` seconds after graduation, using only pool events with block time `< grad_ts + D`.
- Entry: buy `size` SOL against the pool reserves of the last event with block time `<= grad_ts + D + delay`
  (x·y=k, pool fee on input). Default `size` 0.25 SOL, `delay` 2 s.
- Exit: sell all tokens against the pool reserves just before `grad_ts + H` (last transaction with block time `< t`).
- Costs: pool fee 0.30 % per side (**estimated**: PumpSwap LP + protocol + creator fee), network + priority fee
  0.0005 SOL per transaction (**estimated**). Returns in SOL (SOL/USD drift ignored).
- Not modelled (reported as uncertainty): other transactions in the same slot ahead of ours, failed transactions,
  MEV sandwiching beyond the fee estimate.
- Missing exit snapshot: excluded and counted; a pessimistic variant counts it as −100 %.

## Hypotheses

| ID | Name | Decision time | Entry rule (thresholds are quantiles fitted on train only) |
|---|---|---|---|
| H0 | Baseline | 60 s | Buy every graduation (reference, no selection) |
| H1 | Broad organic demand | 60 s | unique buyers ≥ train q75, top-3 buyers' share of buy volume ≤ train q50, net SOL flow > 0 |
| H2 | Dump absorbed (reversal) | 120 s | price multiple since graduation ≤ train q25 and net SOL flow in the last 30 s > 0 |
| H3 | No dominant early whale | 60 s | largest single buyer holds < 25 % of the pool's initial tokens (net) |

Exit horizon `H` ∈ {300, 900, 1800, 3600} s is chosen per hypothesis on **train** (highest mean net return). That
is 3 selection hypotheses × 4 exits = 12 variants examined on train (H0 is reported for all 4 exits, not selected).

## Decision procedure

1. Fit thresholds and pick the exit on train.
2. Validation: a hypothesis continues only if its validation mean net return > 0 and profit factor > 1.
3. Test (opened once, after step 2): report all metrics. A hypothesis is **out-of-sample validated** only if the
   test mean is > 0 and the bootstrap lower bound of the mean is > 0 at the 98.3 % level (95 % with a Bonferroni
   correction for 3 hypotheses). Otherwise it is **INCONCLUSIVE** (positive but uncertain) or **REJECTED**.
4. Always reported: n, mean, median, win rate, average win/loss, profit factor, max drawdown, mean without the 3
   largest wins, bootstrap CI, and sensitivity to delay (0/2/5/10 s), size (0.1/0.25/1/2 SOL) and a high-cost
   scenario (fee 0.5 %/side, 0.002 SOL per transaction).
5. Anything that passes goes to a live paper forward test before any discussion of real money.

---

# Pre-registered hypotheses: smart money (v2, written 16.10.2026 after v1, before any v2 number was computed)

Question: does the **track record of the early buyers** (computed only from earlier launches) select launches with
positive expected return after costs?

## Wallet score (no look-ahead)

For a launch L decided at `grad_ts(L) + 60 s`, a wallet's score uses only earlier launches L' whose outcome was
already known: `grad_ts(L') + 3600 <= grad_ts(L) + 60`. For each such L' where the wallet bought in the first 60 s,
take the baseline outcome of L' (H0: buy at 62 s, sell at 15 min, net of costs). Score = mean of those
outcomes; a wallet needs at least 3 of them to count. History comes from every launch in the dataset.

## Data and split

- Development: the 600 launch_v1 pools. v2 train = first 75 % in time (02.10–12.10), v2 validation = last 25 %.
- **Holdout (untouched):** a second, disjoint chronological sample of 600 other graduations from the same 14 days
  (`sampled = 2`), fetched after this file is committed and opened once, after validation.
- Then a live paper forward test before any discussion of real money.

## Hypotheses (decision at 60 s, entry 62 s, same execution and cost model as v1)

| ID | Name | Entry rule (thresholds = quantiles on v2 train) |
|---|---|---|
| H4 | Smart money present | number of early buyers with score > 0 (≥ 3 launches) ≥ train q75 |
| H5 | Smart money weight | SOL-weighted mean score of early buyers with ≥ 3 launches ≥ train q75 |
| H6 | Little bad money | share of early buy SOL from wallets with score < −0.3 (≥ 3 launches) ≤ train q25 |

Exit ∈ {5, 15, 30, 60} min chosen on train. Validation gate: mean > 0 and PF > 1. Holdout verdict: OUT-OF-SAMPLE
VALIDATED only if mean > 0 and the bootstrap lower bound > 0 at 98.3 % (Bonferroni, 3 hypotheses); positive but
uncertain = INCONCLUSIVE; otherwise REJECTED. Same reporting and sensitivity as v1.
