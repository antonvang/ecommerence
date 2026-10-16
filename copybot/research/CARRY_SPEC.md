# carry_v1: binding specification for delta-neutral funding carry on Hyperliquid

Written and committed 16.10.2026 **before** any spot price, basis or pre-2026-04 funding data was collected or
examined (see `research/FUNDING_AUDIT.md` for what had been seen). Decisions approved by the user in chat on
16.10.2026: Hyperliquid-spot universe only; already-seen period = development; 2023-05 → 2026-03 = untouched
holdout; the running live test stays unchanged next to a new spec-compliant paper test. This file is not edited
after commit; any later change is a new, dated amendment below it, made before the data it affects is examined.

## 1. Instruments and data sources

- Venue: Hyperliquid only. Short the **perpetual** and hold the **spot** token (USDC pair) of the same asset.
- Data (Hyperliquid public `info` API, read-only): `fundingHistory` (hourly rates), `candleSnapshot` 1d for the
  perp and for the spot pair (open, close, high, volume), `spotMeta` (pairs).
- Daily resolution throughout (hourly candles only reach ~7 months back; daily reach the full period).
- Raw responses are cached under `data/research/carry/` and their SHA-256 hashes recorded in the result file.

## 2. Universe (point in time, decided at each rebalance from the prior 7 days only)

A coin is eligible in week `w` (starting Monday 00:00 UTC) only if, using data strictly before that Monday:
1. a spot/USDC pair and a perp with the same underlying exist (name `X` or bridged `UX`);
2. **price agreement**: median over the prior 7 daily closes of `|spot_close / perp_close − 1|` < 2 %, with at
   least 6 of 7 days present (guards against name collisions and bad data);
3. funding data covers ≥ 90 % of the prior 168 hours;
4. liquidity: prior 7-day average daily notional volume ≥ $500k on spot and ≥ $5M on the perp (from daily candles).

Delisted perps are included while they were listed. No use of present-day open interest or volume.

## 3. Rule (frozen; nothing is tuned)

- Rebalance weekly, Monday 00:00 UTC. Signal = sum of the prior 168 hourly funding rates.
- Hold the top 5 eligible coins by signal whose annualised signal (×52) is > 10 %; equal weight.
- Capital C = 1,000 USDC. Per coin: buy N = C / 10 = 100 USDC of spot and short N of perp at 1x isolated margin
  (margin N). Unfilled slots stay in cash at 0 %.
- A coin kept from one week to the next is not traded (no cost); entries and exits are charged.

## 4. P&L per coin per week (entry = Monday daily open, exit = next Monday daily open)

- Funding: Σ over each hour h in [entry, exit) of `rate_h × N × perp_close(day of h) / perp_entry`
  (short receives positive rates). Daily close approximates the oracle price: **ESTIMATED approximation**.
- Price: `N × (spot_exit / spot_entry − 1) − N × (perp_exit / perp_entry − 1)` (residual = basis change).
- Trading fees per side: perp 0.045 %, spot 0.070 % (Hyperliquid published base tier; **ESTIMATED**, not measured
  on fills). Spread + slippage per side: spot 0.05 %, perp 0.02 % (**ESTIMATED**).
- Liquidation: if the perp's daily high in the week ≥ 1.9 × perp_entry, the short is liquidated: perp P&L = −N and
  a 0.5 % × N penalty; the spot leg is held to exit (**ESTIMATED** threshold for 1x).
- Missing data: a missing funding hour counts as 0 and is reported; a missing exit price uses the next daily open
  within 3 days, otherwise the coin-week is excluded and reported; entry requires both prices.
- Residual exposure reported per coin-week: basis P&L and |spot move − perp move|.

## 5. Periods

- **Development** (already seen funding): weeks starting 2026-04-13 through 2026-10-05. Used only to check the
  pipeline and to measure noise; no parameter is chosen on it.
- **Untouched holdout**: weeks starting 2023-05-15 through 2026-04-06. Opened once, after `n_req` is frozen.
  Weeks with no eligible coin are cash weeks (0 %). "Active week" = at least one position.
- **Live paper**: a new spec-compliant paper test from Monday 2026-10-19 00:00 UTC (same rule, live prices).

## 6. Sample size (statistical power)

After development and before opening the holdout: `n_req = ceil(((z_0.994 + z_0.80) × sd_dev / mean_dev)²)` from
the development active weeks' net weekly return on capital (α = 0.05/8 one-sided for 8 ideas tested, 80 % power).
`n_req` is written to `research/CARRY_FROZEN.md` and committed before the holdout is opened. If `mean_dev ≤ 0`,
the verdict is FAIL (the holdout is still run once and reported for the record).

## 7. Gates (all on the holdout, net of all costs)

| Gate | Requirement |
|---|---|
| G1 | Total net P&L > 0 |
| G2 | One-sided 99.4 % lower bound of mean weekly net return (block bootstrap, 4-week blocks) > 0 |
| G3 | Active weeks ≥ n_req |
| G4 | Maximum drawdown ≤ 10 % of capital |
| G5 | Worst week ≥ −5 % of capital |
| G6 | Total net P&L > 0 with costs × 3 and 24 h execution delay (entry/exit at Monday close) |
| G7 | Positive in at least 2 of 3 chronological thirds of the active holdout weeks |

Also reported (no gate): gross vs net, funding vs price vs costs, sensitivity to 10 % missed entries, baselines
(cash 0 %; same mechanics on BTC/ETH/SOL only; funding-only gross), liquidations, capital utilisation.

## 8. Verdict

- **PASS** only if G1–G7 hold **and** the live paper test has run ≥ max(4, n_req) weeks with total net > 0 and no
  week below −5 %. Until the live requirement is met, the best possible status is INSUFFICIENT EVIDENCE.
- **FAIL** if `mean_dev ≤ 0`, or G1 or G2 fails.
- **INSUFFICIENT EVIDENCE** otherwise.
- The original live test (`funding.py`, criterion "positive after fees 2 full weeks in a row") is kept unchanged and
  reported separately; it is not evidence for this specification (it has no spot leg).
