# pmcal_v1: binding specification for prediction-market calibration on Polymarket

Written and committed 16.10.2026, approved by the user as drafted in `NEXT_MECHANISMS.md` §5, **before** any
historical price was joined to any outcome. Only market metadata counts, current order books and API capabilities
were examined (`research/pm_feasibility.py`). Not edited after commit; changes are dated amendments below, made
before the data they affect is examined.

Precisions relative to the draft (made now, before data):
- "Traded during the prior 24 h" cannot be observed for resolved markets (daily price history only). It is
  replaced by: a daily price point within 36 h before entry and another at least 20 h before that one.
- The draft used α = 0.005/3 for n_req, but the rule family has 4 configurations, so α = 0.005/4 is used. This is
  stricter.

## 1. Hypothesis

At a fixed horizon before the scheduled end, binary Polymarket contracts in the tails are mispriced by more than
the cost of trading: either favourites (0.80–0.95) resolve YES more often than their price implies, or longshots
(0.05–0.20) do. Evidence and evidence against: `NEXT_MECHANISMS.md` §2A. The prior expectation is FAIL.

## 2. Data (public, read-only, no account)

- Gamma API `markets/keyset` (closed markets, filtered on the scheduled `endDate`), with fields `id`, `question`,
  `outcomes`, `outcomePrices` (final), `clobTokenIds`, `createdAt`, `closedTime`, `endDate`, `volumeNum`, and the
  first event's `id`, `title` and `slug`.
- CLOB `prices-history?market=<token 0>&interval=max&fidelity=1440` (daily points).
- Every raw response is cached with its SHA-256 in a manifest.
- Data for the holdout period is fetched only after `PMCAL_FROZEN.md` is committed.

## 3. Universe and unit

1. Markets with exactly two outcomes, an order book (`clobTokenIds`), and `volumeNum` ≥ $10,000.
   - Final volume is a known look-ahead filter. A sensitivity run with ≥ $1,000 is reported for the holdout and not gated.
2. Exclude short-duration price markets where the question matches the regex
   `up or down|\bup/down\b|price of .* (above|below) .* on|bitcoin above|ethereum above` (case-insensitive).
3. For a horizon h, the entry time is t_e = `endDate` − h.
4. A market is **open at entry** only if all three hold:
   - `createdAt` ≤ t_e − 24 h;
   - `closedTime` > t_e (a missing `closedTime` excludes it);
   - the history has a daily point p₁ with t_e − 36 h < t(p₁) ≤ t_e, and a point p₀ with t(p₀) ≤ t(p₁) − 20 h.

   The entry price is the price of p₁ for outcome 0. The other outcome is priced as 1 − p₁.
5. **One contract per event:** among the event's markets that pass 1–4, the one with the lowest numeric market id.
   This choice is made without reference to price or outcome. If its price is outside the configuration's bucket,
   the event contributes nothing to that configuration.
6. The final payout of each side is its value in `outcomePrices` (1, 0, or 0.5 for 50-50).
   - A market is excluded and counted if its final value is not within 0.01 of 0, 0.5 or 1.
   - A market is also excluded and counted if it is still unresolved at fetch time.

## 4. Rule family (4 configurations)

| Config | Horizon h | Side bought |
|---|---|---|
| F7 | 7 days | Favourite side if its price ∈ [0.80, 0.95] |
| F1 | 1 day | Favourite side if its price ∈ [0.80, 0.95] |
| L7 | 7 days | Longshot side if its price ∈ [0.05, 0.20] |
| L1 | 1 day | Longshot side if its price ∈ [0.05, 0.20] |

The favourite side is the outcome with price ≥ 0.5. Equal stake per event; held to resolution.

## 5. Costs and returns

- Cost per share c = q + s + f·q·(1 − q), where q is the side's entry price and s is the half-spread.
  - Base case: s = 0.005 (measured median spread 1 cent, 16.10.2026).
  - Fee rate f: 0.07 if the question, event title or slug matches `bitcoin|btc|ethereum|\beth\b|solana|crypto|xrp|doge`, else 0.05. Current published taker fees; conservative, because historical fees were lower.
- High-cost scenario: s = 0.015 and f = 0.07 for all.
- Net return per event per dollar staked: r = (Y − c) / c, where Y is the side's final payout.
- Baseline (random side): for the same selected events, the side bought is chosen by
  `sha256(event_id) mod 2` (0 = outcome 0), with the same costs.
- Reference (price-implied null): gross mean edge 0.

## 6. Periods (by scheduled `endDate`, UTC)

- Development: 2024-01-01 → 2025-12-31.
- Validation: 2026-01-01 → 2026-06-30.
- **Untouched historical holdout: 2026-07-01 → 2026-10-16.** Opened once after `PMCAL_FROZEN.md` is committed.
- Forward paper holdout: contracts entered after the code for it is committed, with live order-book prices (§9).
  It is specified in an amendment before it starts.

## 7. Selection, freezing and sample size

- On development, the configuration with the highest mean net r is chosen. If its mean is ≤ 0, the verdict is FAIL
  (the remaining steps still run for the record).
- Validation must have mean net r > 0 for the chosen configuration, else FAIL.
- `n_req = ceil(((z_{1−0.005/4} + z_{0.80}) × sd / mean)²)` events, with z = 3.0233 + 0.8416, from development +
  validation net r of the chosen configuration (none if the mean is ≤ 0).
- `PMCAL_FROZEN.md` records the configuration and n_req and is committed before the holdout is fetched.

## 8. Gates (holdout, net)

| Gate | Requirement |
|---|---|
| D | ≥ 90 % of markets that pass §3 items 1–3 and are open by dates (`createdAt`, `closedTime`) have the required daily points (§3.4) |
| G1 | Total net return > 0 |
| G2 | One-sided 99.5 % lower bound of the mean net r > 0 (cluster bootstrap over resolution weeks, 10,000 draws, seed 5) |
| G3 | Holdout events ≥ n_req |
| G4 | Mean net r > the random-side baseline's mean net r |
| G5 | Total net > 0 in the high-cost scenario |
| G6 | Net total positive in at least 2 of 3 chronological thirds (by `endDate`) |

Reported without gating:
- Results per configuration on the holdout (all four, labelled as not selected).
- Per-category split (crypto regex vs other).
- The $1k volume sensitivity.
- Win rate, mean entry price, calibration (observed vs implied) per bucket.
- Weekly P&L series, max drawdown on a cumulative per-event sum.
- Exclusions by reason.

## 9. Verdict

PASS only if D and G1–G6 hold on the historical holdout **and** a forward paper test with executable order-book
prices reaches ≥ max(n_req, 8 weeks) events with a lower bound > 0. Before the forward test, the best status is
INSUFFICIENT EVIDENCE. FAIL if the development or validation conditions in §7 fail, or if G1 or G2 fails.
No real money, wallet, account or order is part of this experiment.

Reproduction from `copybot/`: `python -m research.pmcal fetch dev`, `python -m research.pmcal dev`, then after
the freeze `python -m research.pmcal fetch holdout` and `python -m research.pmcal holdout`.
