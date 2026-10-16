# tsmom_v1: frozen before opening the holdout (16.10.2026)

Development + validation run: `python -m research.tsmom dev` at commit f8cc467, result
`data/research/results/tsmom_v1_dev.json`. Data check D passed (median Binance/Hyperliquid close gap 0.045–0.055 %).

- Development (2019-10-07 → 2021-12-27, 117 weeks) net Sharpe by lookback: L=1 1.14, L=2 1.89, L=4 2.02.
  Buy-and-hold: 2.04. Chosen by the spec rule (highest development Sharpe):

L: 4

- Validation (2022-01-03 → 2023-12-25) at L=4: sum of weekly net returns +158.3 % (price +183.1 %, funding −22.5 %,
  costs −2.3 %), Sharpe 1.24, max drawdown 56.1 %. Buy-and-hold Sharpe 0.21.
- Development + validation at L=4: mean +2.04 % per week, s.d. 8.85 % per week.
- `n_req = ceil(((2.5758 + 0.8416) × 8.85 / 2.04)²)`:

n_req: 221

Consequence stated before the holdout is opened: the holdout (2024-01-01 → 2026-10-12) has about 146 weeks, fewer
than n_req, so gate G3 cannot be met and the best possible verdict is INSUFFICIENT EVIDENCE. The holdout is still
run once, unchanged, and every gate reported.
