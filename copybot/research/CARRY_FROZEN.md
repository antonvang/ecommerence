# carry_v1: frozen before opening the holdout (16.10.2026)

Development run: `python -m research.carry dev` at commit 22e4025, result `data/research/results/carry_v1_dev.json`.

- Development period: weeks starting 2026-04-13 → 2026-10-05 (26 weeks, 23 active, 2.6 coins on average).
- Net on capital: −0.079 % total; mean −0.0034 % per active week; s.d. 0.081 % per week.
- Components: funding +1.396 %, basis −0.457 %, fees + spread −1.018 %; 1 liquidation; 0 missing funding hours.
- `mean_dev <= 0`, so by CARRY_SPEC.md §6 and §8 the verdict is **FAIL**, and no sample size can be derived.

n_req: none

The holdout is still run once, unchanged, and reported for the record (CARRY_SPEC.md §6). Baseline (BTC/ETH/SOL
always held, same mechanics) was +0.786 % over the development period; it is a comparison, not the pre-registered
strategy, and is not promoted to a candidate after seeing this result.
