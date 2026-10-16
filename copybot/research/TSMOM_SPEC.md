# tsmom_v1: binding specification for weekly time-series momentum on BTC, ETH, SOL

Written and committed 16.10.2026 **before** any price or return data for this strategy was collected or examined
(only data availability and current spreads were checked; see `NEXT_CANDIDATES.md` §3). Not edited after commit;
changes are dated amendments below, made before the data they affect is examined.

## 1. Mechanism and evidence

Retail trend-chasing and attention make recent crypto returns predict near-future returns (Liu & Tsyvinski 2021,
RFS: "a strong time-series momentum effect"). Expected to be weakened by publication (McLean & Pontiff 2016) and
exposed to crashes (Daniel & Moskowitz 2016).

## 2. Instruments and data

- Signals and P&L: Binance spot daily candles (BTCUSDT, ETHUSDT, SOLUSDT; open/close in UTC days) from the public
  API, cached with SHA-256. SOL enters when its data begins (point in time).
- Funding: Hyperliquid funding where available (from 2023-05-12), Binance USDⓈ-M funding before that.
- Data check (gate D): median |Binance close / Hyperliquid close − 1| over overlapping days < 0.5 % per asset,
  else the experiment stops as INSUFFICIENT DATA.

## 3. Rule

- Rebalance weekly at Monday 00:00 UTC. Signal for each asset = return over the previous L weeks, measured from
  daily closes strictly before Monday. L ∈ {1, 2, 4} weeks (from the literature's horizons); **L is chosen on
  development only** (highest net Sharpe), confirmed on validation, then frozen.
- Position: long if signal > 0, short if signal < 0, 1x notional of capital / 3 per asset (perpetual-style;
  long/flat variant reported, not gated). Capital 10,000 USDC.

## 4. P&L and costs per asset per week

- Entry/exit at Monday daily open. Price P&L = ±notional × (exit/entry − 1).
- Funding: longs pay and shorts receive the hourly (Hyperliquid) or 8-hourly (Binance) funding on current notional.
- Costs on each change of position (flip = close + open): fee 0.045 % per side (Hyperliquid taker, published,
  ESTIMATED) + half-spread = 3 × currently measured (BTC 0.002 %, ETH 0.006 %, SOL 0.015 %; ESTIMATED).
- Delay scenario: entry/exit at Monday close (24 h later). High-cost scenario: costs × 3.
- Missing day: the asset is skipped that week and reported; no value is invented.

## 5. Periods

- Development: weeks starting 2019-10-07 → 2021-12-27.
- Validation: 2022-01-03 → 2023-12-25.
- **Untouched holdout: 2024-01-01 → 2026-10-12.** Opened once after `TSMOM_FROZEN.md` (L and n_req) is committed.

## 6. Baselines

Cash (0 %); buy-and-hold equal weight of the same assets (same costs, funding as a long perp); long/flat variant.

## 7. Sample size

`n_req = ceil(((z_0.995 + z_0.80) × sd / mean)²)` weeks from development + validation weekly net returns at the
frozen L (one-sided α = 0.05/10 for ten ideas tested, 80 % power). If the development + validation mean ≤ 0, the
verdict is FAIL and the holdout is still run once for the record.

## 8. Gates (holdout, net of all costs and funding)

| Gate | Requirement |
|---|---|
| G1 | Total net return > 0 |
| G2 | One-sided 99.5 % lower bound of mean weekly net return > 0 (block bootstrap, 8-week blocks) |
| G3 | Holdout weeks ≥ n_req |
| G4 | Net Sharpe > buy-and-hold net Sharpe of the same assets over the holdout |
| G5 | Total net > 0 with costs × 3 and 24 h delay |
| G6 | Positive in at least 2 of 3 chronological thirds |
| D | Data check (§2) passed |

Reported without gating: max drawdown, worst week, volatility, exposure, turnover, funding vs price vs costs,
deflated-Sharpe style adjustment for the number of trials (Bailey & López de Prado 2014).

## 9. Verdict

PASS only if D and G1–G6 hold **and** a live paper period of ≥ max(8, n_req) weeks has non-negative net return.
Before that, the best status is INSUFFICIENT EVIDENCE. FAIL if the development + validation mean ≤ 0, or G1 or G2
fails. Independent reproduction: `python -m research.tsmom fetch|dev|holdout` from `copybot/`, with data hashes
and commits recorded in the result file; anyone with internet access can re-download the same public data.
