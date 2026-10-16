# tsmom_v2 (diversified time-series momentum): audit and research proposal (16.10.2026)

Repository commit at the start: `bee01a92eead5876c698b466c52a8942ac486d21` (clean tree). Nothing in tsmom_v1 — spec,
frozen file, results, data or code — was changed. No return of any new asset in any new period was read.
Numbers below are reproducible with `python -m research.tsmom_v2_feasibility` from `copybot/`.

**Conclusion: STOP before a specification. No available data can support a valid confirmatory test of tsmom_v2.**
The reasons are in §4; what would change it is in §6.

## 1. Phase 1 audit: tsmom_v1 reproduced

- Re-ran `fetch` into a separate directory: every cached file's SHA-256 matches `RESULTS_tsmom_v1.md`.
- Re-ran development, validation and holdout from the cache: all nine reported metrics (total, mean, s.d., Sharpe,
  max drawdown, thirds, lower bound, n_req, gate vector) equal to within 1e-12.
- Hand calculation of the first holdout week (2024-01-01, three positions, fees, spreads, Hyperliquid funding):
  −361.0028 USDC, identical to the engine.
- Verdict stands: **FAIL on G2 and G3** (holdout Sharpe 0.54 vs buy-and-hold 0.32; 99.5 % lower bound −0.72 %/week;
  146 holdout weeks < n_req 221).

## 2. Design research

| Question | Finding |
|---|---|
| Survivorship / delistings | data.binance.vision lists 3,738 spot symbols; 684 USDT pairs (excluding stablecoins and leveraged tokens) still return daily candles from the public API, **including delisted ones** (e.g. BCCUSDT, VENUSDT, LUNAUSDT, FTTUSDT). A point-in-time universe is therefore possible. |
| Point-in-time breadth | USDT pairs with ≥ 5 weeks of history: 5 on 2017-12-25, 10 on 2018-07-02, 20 on 2018-12-24, 68 on 2019-09-30, 307 on 2022-01-03. |
| Instrument identity | Tickers are reused or renamed (BCC→BCH, VEN→VET, LUNA→LUNC/LUNA, UST→USTC). Any spec must map identity by listing dates, not ticker strings. |
| Liquidity / wash trading | Binance volume is the only free point-in-time liquidity measure; reported volume is contaminated by wash trading (Cong et al. 2023), so a volume rank is a weak filter. Historical spreads for small coins are unavailable. |
| Costs | Fee 0.045 % per side (Hyperliquid taker) plus spread; small-coin spreads today are 10–100× BTC's and unknown historically. Costs would be an estimate, not a measurement. |
| Correlation (v1 data, already seen) | Weekly raw returns BTC/ETH/SOL: 0.64 (dev+val), 0.74 (holdout). Per-asset **strategy** returns: 0.29 (dev+val), 0.45 (holdout). |
| Funding | Binance USDⓈ-M funding exists from 2019-09; Hyperliquid from 2023-05. Before 2019-09 only spot exists: no shorting and no funding. |

## 3. How much diversification can help

For n equal-Sharpe strategies with average pairwise correlation ρ, the portfolio Sharpe is the single-asset Sharpe
× √(n / (1 + (n−1)ρ)). With the measured ρ = 0.29–0.45, going from v1's 3 assets to 20 raises the Sharpe by
**×1.15–1.27**, and only if the 17 extra coins are as good after costs as BTC/ETH/SOL (optimistic: they are less
liquid and cost more). The common crypto factor caps the gain.

Required sample (one-sided, 80 % power; α = 0.005 as in v1 for the multiple-testing budget, α = 0.05 shown for
reference), 20 assets:

| Per-asset Sharpe assumed | ρ | Portfolio Sharpe (ann.) | n_req at α = 0.005 | n_req at α = 0.05 |
|---|---|---|---|---|
| As v1 development + validation (0.202/week) | 0.29 | 2.56 | 93 weeks | 50 |
| As v1 development + validation | 0.45 | 2.11 | 137 | 73 |
| As v1 holdout (0.061/week) | 0.29 | 0.77 | 1,026 | 543 |
| As v1 holdout | 0.45 | 0.63 | 1,512 | 801 |

The development-like rows are not a realistic prior: v1's portfolio Sharpe fell from 1.97 (development +
validation) to 0.54 on its holdout. The holdout-like rows are the honest planning case.

## 4. Why no valid test is possible

1. **2019-10 → 2026-10 is not untouched.** All three v1 periods have been looked at for BTC, ETH and SOL. Other
   coins' returns co-move with them (raw correlation 0.64–0.74), and the v1 holdout's market regimes are known. A v2
   result on those weeks would not be independent evidence, and the mission rules forbid reusing v1's holdout as
   unseen evidence.
2. **Pre-2019 data is too short, too narrow, and a different strategy.** At most 94 untouched weeks (2017-12 →
   2019-09) with ≥ 3 assets, 65 with ≥ 10, 40 with ≥ 20. Even under the optimistic development-like Sharpe, n_req is
   93–137 weeks at α = 0.005; under the realistic case it is 1,000–1,500. In that period there were no perpetuals,
   so only long/flat spot could be tested, not the long/short perp strategy that would be run today. Most of it is
   one regime (the 2018 bear market). Quote-currency pairs against BTC would add coins but not weeks.
3. **A forward paper holdout would take 10–30 years** at the realistic Sharpe (543–1,512 weeks), or about 2–3 years
   even under the optimistic Sharpe that v1 already failed to sustain.
4. **Costs for the added coins cannot be measured historically**, so a positive result would rest on an
   assumption about exactly the coins that make v2 different from v1.

Any test I could run now would be underpowered by design: G3 (sample size) could not be met, so the best attainable
verdict would be INSUFFICIENT EVIDENCE, regardless of outcome. Writing a binding spec and opening data for a test
whose outcome cannot change the decision would only spend the remaining untouched data (pre-2019) for nothing.

## 5. What was not done

- No specification was committed for testing, and no development, validation or holdout run of v2 took place.
- No pre-2019 or new-coin return series was downloaded; only listing dates (first candle timestamps) were read.
- The paper copy bot and the original funding live test were not touched.

## 6. What would make a valid test possible

- A **lower bar agreed in advance**: e.g. accept α = 0.05 with a single pre-registered test, still ≈ 540+ weeks at a
  realistic Sharpe — not feasible either.
- A **different question with a larger effect**: only effects with an out-of-sample annual Sharpe of roughly 2 or
  more can be confirmed on ~100 weeks. None of the documented crypto anomalies in `NEXT_CANDIDATES.md` has shown that
  after publication.
- **Data from a different, independent market** (e.g. other asset classes' trend-following, decades of futures
  data) — outside the scope of a crypto bot and of free data here.

## 7. Recommendation

Do not run tsmom_v2. Keep the tsmom_v1 FAIL verdict as the final word on crypto time-series momentum in this
project. Across 14 tested ideas, none passed; the sample-size arithmetic above shows that the remaining candidates
with plausible effect sizes cannot be confirmed with the data available. Continuing to search would mostly add
multiple-testing risk, not evidence.
