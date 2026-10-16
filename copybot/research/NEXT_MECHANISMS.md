# Independent market-inefficiency research: audit, candidates, feasibility, proposal (16.10.2026)

Repository verified at `c336c48f2e92e558eeeafc9d281de6a580078ea1` (= origin, clean tree). No previous result,
specification, frozen file or dataset was changed. **No strategy was implemented and no price was joined to any
outcome for this document.** Feasibility numbers reproduce with `python -m research.pm_feasibility` from `copybot/`.
Tool note: the web-search tool was unavailable; sources were verified through the Crossref API (DOI, title,
abstract where deposited) and official documentation pages. Statements marked "summary (mine)" are from my
knowledge of the paper and were not re-read today.

## 1. Portfolio audit

### Status of every experiment

| # | Idea | Status | Valid test? |
|---|---|---|---|
| 1 | Copy KOL wallets | Failed agreed criteria (14-day backtest, −6.5 %/trade even at 0 s, 0 fees) | Exploratory, not pre-registered; result too clear to matter |
| 2 | Self-found traders, copy 2 s later | Failed (−7 %) | Exploratory |
| 3 | SOL hourly trend | Failed (costs) | Exploratory |
| 4 | Buy pump.fun graduations | Failed (443 coins) | Exploratory |
| 5 | Graduation sniper | Failed: pre-registered 60 s rule on 279 unseen pools, then 149 live paper trades/rule | **Valid** (pre-registered rule + live) |
| 6 | Short new Hyperliquid listings | Negative mean, n = 23 | **Not validly tested** (too small) |
| 7–8 | Funding carry v0, leverage | Invalid test (survivorship, no spot leg) | Superseded by carry_v1 |
| 9 | Stop-when-ahead | No change in expectancy | Exploratory |
| 10 | launch_v1 (flow features) | REJECTED on validation | **Valid** |
| 11 | smart_v2 (early buyers' record) | REJECTED on holdout | **Valid** |
| 12 | arb_v1 (SOL/USDC pools) | REJECTED, 0 opportunities | **Valid** for that pair/venue |
| 13 | carry_v1 (delta-neutral, HL spot) | FAIL (development mean ≤ 0) | **Valid** |
| 14 | tsmom_v1 (BTC/ETH/SOL weekly) | FAIL (G2, G3) | **Valid** |
| 15 | tsmom_v2 (diversified) | Stopped at feasibility | **Not testable** with available data |

### Common causes of failure

1. **Speed races against professionals** (2, 5, 12).
2. **Adverse selection in new tokens** (1, 4, 10, 11).
3. **Turnover × costs** (3, 13).
4. **Overfitting / non-persistence** (5, 10).
5. **Too little independent data.** This one is new.
   - Every crypto time-series idea is driven by one common market factor, so 9 years of data is about 450 weekly observations of essentially one bet.
   - tsmom showed the result: n_req ran from hundreds to more than a thousand weeks (14, 15).
6. **Data limits.** No free historical order books, vesting schedules, or quotes (7, 15).

Implication: the next candidate must have **many independent outcomes per week**, no speed requirement, costs that
can be read from live order books, and a holdout that has never been examined.

## 2. Candidate mechanisms

### A. Probability misperception in prediction markets (Polymarket binary contracts)

- **Hypothesis.** Traders misjudge probabilities: they overweight longshots or overreact to news, and arbitrage
  capital is limited. If so, contracts at a given price and horizon resolve YES at a rate that differs from the price
  by more than the cost of trading.
  - Unlike any earlier idea, each contract has a known terminal value (0 or 1).
  - Events are largely independent of each other and of crypto prices.
- **Evidence for:**
  - Favorite–longshot bias in betting markets: Thaler & Ziemba 1988, https://doi.org/10.1257/jep.2.2.161. Snowberg & Wolfers 2010, *JPE*, https://doi.org/10.1086/655844 (summary, mine: the bias is best explained by misperception of probabilities, not risk-love).
  - Page & Clemen 2013, *Economic Journal*, https://doi.org/10.1111/j.1468-0297.2012.02561.x. Summary (mine): prediction markets are well calibrated near expiry but show a longshot bias for events far in the future.
  - Wang 2026, SSRN, https://doi.org/10.2139/ssrn.6624899. A wallet panel; the abstract says the dominant profitable pattern is "resolution-edge holding" (median event-level win rate 93 %), not arbitrage.
- **Evidence against:**
  - Reichenbach & Walther 2026, SSRN, https://doi.org/10.2139/ssrn.7552098. 1.5 billion trades across 779,000 Polymarket markets. Prices are "highly informative", with "no general market-level longshot bias".
    - Instead, low-probability outcomes are "initially underpriced before reversing late"; "default outcomes are persistently overpriced".
    - These are published (decay expected; McLean & Pontiff 2016, https://doi.org/10.1111/jofi.12365), and the direction conflicts with Page & Clemen.
  - Wolfers & Zitzewitz 2004, *JEP*, https://doi.org/10.1257/0895330041371321, and Berg, Nelson & Rietz 2008, *IJF*, https://doi.org/10.1016/j.ijforecast.2008.03.007: prediction markets are accurate forecasters.
  - Wang 2026: 67 % of top wallets are at least partly automated, so the venue is professionalised.
- **Data:**
  - Gamma API (market metadata, scheduled end, event grouping, resolution) and CLOB `prices-history`. For resolved markets this is daily fidelity only; checked: 60-minute history returns 0 points, daily returns full life.
  - data-api trade prints (offset-capped) and live order books (`/book`).
  - Coverage of resolved markets with ≥ $10k volume, an order book, a life of at least 2 days, and not short crypto up/down markets:

    | Half-year | Markets | Distinct events |
    |---|---|---|
    | 2024-H1 | 1,507 | 804 |
    | 2024-H2 | 6,550 | 2,831 |
    | 2025-H1 | 12,122 | 5,031 |
    | 2025-H2 | 30,738 | 11,528 |
    | 2026-H1 | 85,912 | 30,914 |
    | 2026-H2 (to 16.10) | 62,592 | 22,685 |

    Over the last 20 full weeks, a median of **1,549 distinct events resolved per week** (min 933, max 1,818).
- **Costs (measured / published 16.10.2026):**
  - Current books, 318 sampled active markets: median spread 1 cent for mids 0.1–0.9; 0.1–0.8 cent at the extremes (tick 0.001). So the half-spread is about 0.5 cent.
  - Taker fee = rate × p × (1 − p) per share. The rate is 0.07 for crypto, 0.05 for sports and most categories, 0.04 for politics, finance, tech and mentions, and 0 for geopolitics. Makers pay no fee (docs.polymarket.com/trading/fees).
  - Buying at 0.90 costs ≈ 0.86–1.13 cents (≈ 1 % of price); at 0.50, ≈ 1.5–2 cents.
  - Historical fees were lower (most markets were fee-free before the current schedule), so using today's fees is conservative.
- **Execution:**
  - Horizons of days. No speed requirement, no leverage, fully collateralised.
  - Capacity per market is small: a median of $56–$1,700 at the best ask. Size must stay small, or impact must be modelled.
- **Bias risks:**
  - **Look-ahead:** `closedTime` reveals early resolution, `endDate` may be edited after the fact, and the filter on final volume uses future information. Defences: enter only at a horizon defined from the scheduled end as recorded at entry, use a liquidity filter measured at entry in the forward test, and run a sensitivity check with a $1k volume filter.
  - **Selection:** multi-outcome events contain many correlated longshots. Use one contract per event, chosen deterministically.
  - **Multiple testing:** a small grid, fixed in advance (§5).
- **Falsification:** the net event-level return of the frozen rule has a 99.5 % lower bound ≤ 0 on the holdout, or it fails on executable forward prices.
- **Obtainable without money:** yes. Public read-only APIs, no account, no wallet.
- **Access and legal (unresolved):**
  - Denmark is not on Polymarket's restricted list today (docs.polymarket.com/developers/CLOB/geoblock). DE, FR, BE, IT, PL and GB are close-only.
  - Whether Danish gambling law (Spillemyndigheden) permits use is **not verified**. It must be checked before any real money, but it does not block paper research.
  - Oracle risk: Abid 2026, https://doi.org/10.2139/ssrn.6670638, reports more than $250M of markets settled by disputed governance votes in 2025.

### B–M. Rejected candidates

| Candidate | Mechanism / evidence | Rejection reason |
|---|---|---|
| B. Crypto variance risk premium (sell BTC/ETH options) | Carr & Wu 2009, *RFS*, https://doi.org/10.1093/rfs/hhn038; Alexander & Imeraj, *J. Alt. Investments*, https://doi.org/10.3905/jai.2021.pa447; against: Dew-Becker & Giglio 2025, "The Decline of the VRP", https://doi.org/10.21033/wp-2025-17 | Short options = leverage/margin (outside constraints); historical bid/ask quotes not free (trade prints only); about one independent observation per monthly expiry → tsmom-style power problem; crash risk |
| C. Token dilution / unlock premium | Guo 2026, SSRN, https://doi.org/10.2139/ssrn.6636258 (long–short 25–32 %/yr, concentrated in first-year tokens) | Point-in-time vesting/supply data not free; requires shorting new small tokens (our short-listing test: tail risk); 2020–26 overlaps seen periods; unreplicated working paper |
| D. Locked supply / staking share | Khoja 2026, SSRN, https://doi.org/10.2139/ssrn.7314420 | Historical staking shares not free point-in-time; monthly cross-section → power |
| E. Passive DEX liquidity provision | Against: Milionis, Moallemi, Roughgarden & Zhang, arXiv:2208.06046 (loss-versus-rebalancing; not re-verified today, arXiv rate-limited); Kovalenko 2026, https://doi.org/10.21203/rs.3.rs-11118453/v1 (passive panel −5.72 % APR) | Evidence says LPs lose to arbitrageurs; same race as arb_v1 |
| F. Stablecoin de-peg reversion | Lyons & Viswanath-Natraj 2023, *JIMF*, https://doi.org/10.1016/j.jimonfin.2022.102777 | A handful of events; no sample |
| G. Tether issuance → BTC | Griffin & Shams 2020, *JF*, https://doi.org/10.1111/jofi.12903 | Episode-specific (2017–18); one asset → power |
| H. Exchange-listing announcements | — | Speed race (pattern 1) |
| I. Seasonality, futures expiry, ETF flows | Low-quality evidence (SSRN notes, e.g. https://doi.org/10.2139/ssrn.4779669); ETF data since 2024 | Single series → power; weak evidence |
| J. Perp return predictors | Cao et al. 2026, https://doi.org/10.2139/ssrn.6365329 (170 predictors, two factors explain them) | Multiple testing; explained by basis and price-volume factors → overlaps carry/momentum |
| K. Copy Polymarket "smart money" | Wang 2026 | The copy pattern failed three times; data from a third-party aggregator |
| L. Sports-exchange longshot bias (Betfair) | Same literature as A | Needs an account for historical data (we create none); commission 2–5 % |
| M. Kalshi | Same mechanism, US-regulated venue | Not for trading (access from Denmark not verified), but its public API returns settled markets with bid/ask fields (checked) → **independent replication venue** for A |

## 3. Feasibility gate

| Requirement | A (Polymarket) | B–M |
|---|---|---|
| Timestamped data for development, validation and an untouched holdout | Yes: ~65,000 resolved events since 2025-07 (none examined by us), plus about 1,500 new events per week forward | No, or only with the power problem |
| Measurable costs and executable prices | Live books and published fees: yes. Historical: daily price + measured half-spread (assumption, checked forward) | Mostly no |
| Sample-size plan | See below | — |
| Independent baseline | Price-implied probability (zero gross edge); random side at the same horizon | — |
| Test without reusing examined data | Forward paper test with order-book snapshots after the spec commit | — |

Required independent events (one-sided, 80 % power):

| Price bought | Net edge | n_req at α = 0.005/3 | n_req at α = 0.05 |
|---|---|---|---|
| 0.90 | 0.5 pp | 51,352 | 22,258 |
| 0.90 | 1.0 pp | 12,838 | 5,565 |
| 0.90 | 2.0 pp | 3,210 | 1,392 |
| 0.80 | 1.0 pp | 22,823 | 9,893 |

At 1,549 events per week, if 10–30 % have a contract in the tested bucket at entry (assumption; to be measured on development), 150–450 qualify per week. That means:
- **1 pp net:** about 30–85 weeks forward.
- **2 pp net:** about 7–21 weeks forward.

Historically, ~22,700 events in 2026-H2 alone. This passes the gate. By contrast, tsmom needed 1,000+ weeks. Effects below about 1 pp net cannot be confirmed in a reasonable time and would not survive costs anyway.

## 4. Ranking and recommendation

| Rank | Candidate | Evidence | Feasibility | Cost sensitivity | Scalability |
|---|---|---|---|---|---|
| **1** | **A. Prediction-market calibration** | 3/5 (classic, but recent Polymarket evidence partly against) | 4/5 | 3/5 (≈ 1 cent per trade vs an edge that must be ≥ 2 pp gross) | 2/5 (thin books) |
| 2 | C. Token dilution | 2/5 | 1/5 | 2/5 | 2/5 |
| 3 | B. Crypto VRP | 4/5 | 1/5 | 2/5 | 4/5 |
| — | D–L | — | rejected | — | — |

**Recommendation: A only**, as one pre-registered experiment `pmcal_v1`. It is meaningfully different from every
previous attempt:
- **No crypto price exposure and no common factor:** thousands of independent outcomes each month, which fixes cause 5.
- **No speed race:** horizon of days.
- **Costs readable from live books:** no need to estimate.
- **Holdout:** there is a historical period nobody here has examined, plus a forward test that cannot be contaminated.

**Honest prior: FAIL is likely.** The largest and most recent study finds no general longshot bias, the venue is
professionalised, and a net edge of ≥ 1 pp after ≈ 1 cent costs is demanding. Even if it passes, capacity is small
(hundreds of dollars per market), so it cannot produce "video-like" returns.

## 5. Proposed pre-registration plan (draft for review; not binding, nothing implemented)

1. **Unit.** One binary contract per event, chosen without reference to prices or outcomes (lowest market id among
   the event's markets that are open at entry). Entry at **T − h** before the scheduled end, h ∈ {7 days, 1 day};
   the contract must have traded during the prior 24 h.
2. **Rule family (4 configurations).** Buy the favourite side if its price is in [0.80, 0.95], or buy the longshot
   side if its price is in [0.05, 0.20], at h = 7 d or 1 d. Hold to resolution; payout 1/0. Annulled or 50-50
   resolutions are paid as resolved.
3. **Costs.**
   - Historical: daily price + 0.5 cent half-spread + today's category taker fee.
   - High-cost scenario: half-spread 1.5 cents.
   - Forward: actual best ask and size from a live book snapshot, plus fee.
4. **Splits (by scheduled end date).**
   - Development: 2024-01-01 → 2025-12-31.
   - Validation: 2026-01-01 → 2026-06-30.
   - **Untouched historical holdout:** 2026-07-01 → 2026-10-16.
   - **Forward paper holdout:** contracts entered after the spec commit.
   - The configuration is chosen on development, must be positive on validation, and is then frozen with n_req.
5. **Statistics.**
   - Event-level net return.
   - Week-block bootstrap (resolution week) for the 99.5 % one-sided lower bound.
   - n_req from development + validation (α = 0.005/3 for the selection, 80 % power).
   - Per-category results are reported but not gated.
6. **Gates (holdout).**
   - G1: net total > 0.
   - G2: lower bound > 0.
   - G3: events ≥ n_req.
   - G4: beats the random-side baseline.
   - G5: net > 0 in the high-cost scenario.
   - G6: positive in 2 of 3 chronological thirds.
   - D (data): ≥ 90 % of sampled markets have daily history at entry, and a forward check that the daily price lies within the live spread.
7. **Verdict.** PASS only if the historical holdout passes **and** the forward paper test reaches n_req events (and at
   least 8 weeks) with a lower bound > 0 on executable prices. Otherwise FAIL or INSUFFICIENT EVIDENCE.
8. **Order.**
   1. Commit the spec.
   2. Commit the code and tests.
   3. Fetch data.
   4. Run development and validation, then freeze.
   5. Open the historical holdout once.
   6. Run the forward paper test.
9. **Out of scope.** Real money, wallets, accounts, and maker orders: maker fills cannot be backtested honestly.

**Stopped here for review.** Nothing will be implemented before the plan is approved, and possibly amended, and
committed as a binding spec.
