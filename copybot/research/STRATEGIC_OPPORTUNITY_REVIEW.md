# Strategic opportunity review (16.10.2026)

Baseline: commit `8d40c9ec` on `claude/why-cant-we-do-this-wh3ohb` (= origin, clean tree). Only new files were
added by this review:
- this report;
- `research/STRATEGIC_CANDIDATES.json`;
- `research/pm_rewards_snapshot.py`, a read-only measurement script.

No existing file, result, threshold, spec or running process was changed. No holdout was opened. No order was
placed, and no money, key or account was used.

**Method limitation.**
- The web-search and web-fetch tools failed for this whole session.
- Literature was found and verified through the Crossref API (titles, DOIs, abstracts). Product and pricing facts come from direct HTTP fetches of official pages (raw text kept in the session scratchpad), plus the GitHub and Polymarket public APIs.
- Competitor discovery is therefore **incomplete**: I could only check competitors I already knew to look for. Any "no competitor found" below means "none checked", not "none exists".

Labels used below: **[F]** verified fact (source in §11), **[M]** my own measurement (reproducible command given),
**[E]** estimate, **[H]** hypothesis, **[U]** unknown.

---

## 1. Executive conclusion

**No trading strategy and no software product currently has the evidence to justify a build.** One candidate is
worth a bounded, pre-registered, money-free study:

> **Polymarket liquidity provision.** Polymarket pays makers through a published liquidity-rewards program
> and maker rebates.

- **[F]** About **$191–195k per day** of reward pools are configured across about 14,200 markets.
- **[M]** In two independent samples of 286–288 reward markets (pools ≥ $5/day), a hypothetical 100-share two-sided quote at half the maximum spread would have earned a **median gross ≈ 2 % per day** of the quote capital, about $2 per market per day, against the qualifying liquidity already on the book. 26–28 % of sampled markets had no qualifying competing quotes.

This is a subsidy measured from one snapshot, not an edge. It **excludes adverse selection** (being filled just before
news or resolution), uptime, inventory risk and the real daily sampling.

A number this large almost always shrinks or disappears once costs are counted. That is exactly what the study must
establish before anything else.

What makes it different from the 16 failed ideas:
- It does not predict prices. It earns a documented cash flow.
- The cost side (adverse selection) can be measured from public data: the on-chain fills and markout methodology
  used in Albiez 2026 [F].
- Its falsification is cheap.

| Role | Direction |
|---|---|
| **Primary** | Pre-register and run an observational study, `pm_lp_v1`: realised reward payouts and maker markouts on Polymarket. No orders. |
| **Fallback** | Harden the research engine (Track C) into a small open-source "sealed-holdout" research kit, and test demand for it as a product (B1) with near-zero spend. |

**Overall confidence: low to moderate.** The most likely outcome of the primary study is a no-go: adverse selection
or competition absorbs the rewards. Even in the good case, two things must be checked by the user before any real
money: whether Danish law allows it, and whether Polymarket's terms allow automated market making.

---

## 2. Repository audit (read-only, 16.10.2026)

| Item | State |
|---|---|
| Git | 68 commits since 25.09.2026; HEAD `8d40c9e`; branch = origin; clean |
| Tests | `python -m unittest discover -s tests` → **81 tests, OK** |
| Running processes | `py -u copybot.py paper` (PID 11588 launcher → 29500), started 16.10 20:24. Not touched. |
| Dashboard | localhost:8765 → HTTP 200. Paper copy bot $1,041.58 of $1,050 (−0.8 %, 2 trades, "too early"). Funding live test −$0.44 after ~9 h. Sniper stopped: −10 to −15 %/trade over 149 trades/rule. Research card lists 6 experiments. |
| Code size | ~6,300 lines of Python: bot (engine, swaps, market, paper, sniper, funding, report, server) and research (launch_data, simulate, experiment(_v2), arb, carry, tsmom, pmcal, feasibility scripts) |
| Research record | 16 ideas. Pre-registered verdicts: launch_v1 REJECTED, smart_v2 REJECTED, arb_v1 REJECTED, carry_v1 FAIL, tsmom_v1 FAIL, pmcal_v1 FAIL; tsmom_v2 stopped (not testable). Summary in `FORSKNING.md` §1–16. |

### Must be preserved

All `research/*_SPEC.md`, `*_FROZEN.md`, `RESULTS_*.md`, `HYPOTHESES.md` and the commit chain spec → code → frozen
→ results (e.g. pmcal: `07dcdd5` → `140c190` → `cc24d21` → `8d40c9e`).

### Already works

- Pre-registration discipline.
- Per-experiment holdout guards: `frozen()` in tsmom and pmcal, `frozen_committed()` in carry. pmcal also refuses to *fetch* holdout data before the freeze.
- SHA-256 data manifests (carry, tsmom, pmcal).
- Bootstrap lower bounds and n_req power calculations.
- Gate tables; one dashboard card per experiment.

### Missing or weak

- No central registry; verdicts are spread over markdown and JSON.
- No global multiple-testing ledger: α was set by hand to 0.005/10 in tsmom and 0.005/4 in pmcal.
- Statistics are duplicated in 3 modules with different constants.
- **`copybot/data/` is git-ignored**, so cached datasets exist only on this PC, and some APIs return mutable data (Polymarket `endDate`). Reproducibility therefore depends on one disk.
- The launch, smart and arb datasets (SQLite) have no hash manifest.
- `report.py` derives verdicts from gate-name prefixes instead of a stored verdict.

---

## 3. Track A: market inefficiencies

The lesson from 16 tested ideas, independently confirmed:
- Nefedov 2026 [F] audited six standard crypto factors on 137 Binance perpetuals. Under a rigorous protocol "none of the six factors survives deflation".
- Naïve evaluation inflates Sharpe 3.6×, mostly through frictions.

Price-prediction strategies are therefore not pursued further.

### A1. Polymarket liquidity-reward provision (leading candidate)

1. **Mechanism.** The venue pays makers to quote within a maximum spread with a minimum size, using a quadratic
   score ((v − s)/v)², sampled each minute [F]. Makers also receive 15–25 % of taker fees as rebates [F].
   Profit = rewards + rebates + spread captured − adverse selection − inventory losses at resolution.
2. **Why it exists.** It is deliberate: the venue buys liquidity. It is not a mispricing that arbitrage removes.
   - Pools are many and small: median $3/day [M].
   - Small pools may not be worth a professional's operational effort [H].
3. **Competitors.** Automated wallets: 67 % of 273 top wallets are at least partly automated (Wang 2026 [F]). Also
   professional makers and Polymarket's own incentives tuning.
4. **Why it could still exist.** There is a long tail of thousands of markets with $1–20/day pools (12,358 of
   14,241 [M]). It needs per-market operations and carries binary resolution risk [H].
5. **Data.**
   - Reward configs: `/rewards/markets/current`, public [F].
   - Order books: public; YES and NO books mirror each other, checked on 3 markets [M].
   - On-chain `OrderFilled` and `FeeCharged` events with maker and taker [F].
   - **Historical order books are not public** [U], so reward share can only be measured going forward.
6. **Execution realism.**
   - Fills: conservative trade-through rule.
   - Rewards: the published formula.
   - Fees: zero for makers [F].
   - Adverse selection: markouts from real historical fills.
   - Latency is not critical for passive quoting at ≥ 1 tick from the mid, except around news [H].
7. **Independent evidence.**
   - The programme exists, its size and its formula [F].
   - Analog: Albiez 2026 [F] finds on-chain options makers on Derive earn +13.05 USDC per contract at a 30-minute markout (half spread +15.70, adverse selection −2.65; net +8.93 after fees and hedging), with losses concentrated in ten professional wallets.
   - **No independent evidence that Polymarket rewards are net profitable for a small maker** [U].
8. **Falsification.** Over a pre-registered forward window, any of these rejects A1:
   - realised payouts for observed maker wallets are far below the formula's prediction;
   - mean maker markout per filled share at reward-eligible prices exceeds the reward plus rebate per quoted share-day;
   - the net lower bound is ≤ 0.
9. **Minimum viable experiment.** See §8.
10. **Commercially meaningful if** the net yield stays positive at a scale of hundreds to thousands of markets,
    after legal clearance [U].
    - Upper bound: the whole pool is about $70M/yr [F/E], and a small operator would get a small share.
    - Realistic expectations must come from the study, not from this snapshot.

### Rejected or deprioritised

| ID | Candidate | Why not now |
|---|---|---|
| A2 | Short-horizon crypto binaries on Polymarket (variance premium / underconfidence; Lee et al. 2026 [F]: Polymarket VRP ~16× Kalshi's, both venues "systematically underconfident") | One working paper. Crypto taker fee rate 0.07 (1.75 cents at p = 0.5) [F]. Resolved short markets keep only daily price history [M, pmcal], so it is forward-only. Closely related to the failed pmcal. Revisit only if A1's data pipeline exists. |
| A3 | Cross-venue funding/basis (Hyperliquid vs Binance) | carry_v1 FAIL; He et al.: deviations "diminish over time"; the relevant periods are already examined; Nefedov: carry "survives only under optimistic cost assumptions" |
| A4 | Polymarket–Kalshi or intra-Polymarket arbitrage | Yang et al. 2026 [F]: in NBA markets, 7 single-market episodes, median 3.6 s; combinatorial ones limited to ~14.8 shares. Kalshi access from Denmark unverified [U]. Our arb_v1 found 0 opportunities. |
| A5 | Crypto pairs / stat-arb (Fil & Kristoufek 2020 [F]) | Published, crowded, cost-sensitive; Nefedov's audit; same common-factor and cost failure patterns as earlier ideas |
| A6 | Hyperliquid market making | Base maker fee is **positive** (0.015 %) [F]; rebates need large volume tiers; speed competition |
| — | Token unlocks, VRP selling, DEX LP, listings, stablecoins | Rejected with reasons in `NEXT_MECHANISMS.md` (unchanged) |

---

## 4. Track B: products

The problem is real and documented:
- Backtest overfitting: Bailey et al. 2014; Bailey et al. 2016; Harvey & Liu 2015; Suhonen et al. 2017; Arnott, Harvey & Markowitz 2019 [F].
- Inflated crypto strategy claims: Nefedov 2026 [F].
- Bot fraud: the CFTC advisory "AI Won't Turn Trading Bots into Money Machines", reporting claims of "tens of thousands of percent" [F].

**Demand, i.e. willingness to pay for *our* product, is unverified for every option.**

| ID | Product | Who has the problem | Today's solution and price | Our difference | Demand evidence | Verdict |
|---|---|---|---|---|---|---|
| B1 | **Strategy validation / sealed-holdout kit**: pre-registration, frozen parameters, holdout guard, power and DSR, machine-checkable verdict | Retail and semi-pro algo traders; small funds evaluating strategies; strategy sellers who want credibility | StrategyQuant X robustness tests: $1,490 / $2,900 lifetime (sale), $1,790 / $4,900 list [F]. MlFinLab: £100 per user per month commercial [F]. QuantConnect: tiered platform [F]. Free OSS: freqtrade 55k★, backtrader 23k★, Lean 22k★, vectorbt 9.4k★ [F]. pypbo 143★ [F]. | Enforced *process* (sealed holdout + commit chain + automatic rejection) rather than more tests; proven on our own 16 ideas | Weak: comparables charge for robustness tests, but tools focused on overfitting are niche (pypbo 143★). The incentive problem: sellers of hype don't want audits [H]. | Fallback, demand test only |
| B2 | Polymarket maker analytics (reward yield per $ of competing liquidity, markouts) | Polymarket makers and bots (py-clob-client 1.2k★ [F]; 67 % of top wallets automated [F]) | Polymarket's own reward pages [F]; third-party analytics (polydata.pro is cited in Wang 2026 [F]); others **unknown** (no search) | Combines reward share with adverse selection, which raw reward rates don't show | None verified | Only as a by-product of A1 |
| B3 | Retail crypto execution-cost transparency | EU retail: Stotz 2026 [F] measured 123–458 bp all-in costs at six German brokers vs 16–34 bp exchange spreads | Broker disclosures (MiCA) | — | Problem documented; WTP unknown | Reject: measurement needs real orders (outside the rules) |
| B4 | Crypto market-data quality and anomaly detection | Data consumers | Tardis $350–3,000/month, "99.9 % avg. historical data completeness" [F]; CoinAPI $79–599/month [F]; Kaiko, Coin Metrics (no public price) | None material | — | Reject: incumbents own the data |
| B5 | Generic experiment tracking / reproducibility | ML and quant teams | MLflow 28k★ (free), DVC 16k★, W&B free tier and Pro from $60/month [F], Great Expectations 12k★ [F] | None | — | Reject: crowded, free |

**Costs and legal (B1 and B2):**
- Hosting can be zero: open-source plus a static page.
- A paid service needs EU GDPR handling for user data. It must not give personalised investment advice: tools,
  not signals.
- Polymarket data terms must be checked before redistributing data [U].

---

## 5. Track C: research engine

The proposal reuses the existing code and **wraps old experiments read-only; it migrates nothing.**

| Component | Exists today | Gap | Proposed (new code under `research/core/`) | Effort [E] |
|---|---|---|---|---|
| Registry | Markdown files + `data/research/results/*.json` | No single source of truth | `research/registry.json`: id, status, spec / frozen / results commit and SHA-256, verdict, α spent | 0.5 day |
| Holdout seal | `frozen()` (tsmom, pmcal), `frozen_committed()` (carry), fetch guard (pmcal only) | Re-implemented per module | `seal.py`: one guard for fetch and evaluate; refuses unless the spec and frozen file are committed, clean, and hash-listed in the registry | 0.5 day |
| Provenance | SHA-256 manifests (3 experiments) | Data only on this PC; mutable APIs; SQLite datasets unhashed | `manifest.py` + content-addressed archive (zip + hash) outside Git, on a second disk or cloud **only with approval** | 1 day |
| Statistics | `block_lb` ×2, `cluster_lb`, `n_req` ×3 (z = 2.5758 / 2.512 / 3.0233), `psr` | Duplicated, inconsistent | `stats.py`: block and cluster bootstrap, n_req, PSR, DSR; tests ported | 1 day |
| Multiple testing | Hand-set α per experiment | No program-level ledger | α-spending ledger in the registry (e.g. α/k with k = ideas tested; 16 so far) | 0.5 day |
| Costs and baselines | Per experiment | — | `costs.py` interface (fee, spread, impact, funding) + baseline library (cash, buy-and-hold, random side) | 1–2 days |
| Verdict engine | Per-module gates + `report.py` prefix heuristic | Verdict partly re-derived in the UI | `verdict.py` reads the registry; the dashboard shows the stored verdict only | 0.5 day |
| Reports | Hand-written markdown | Not machine-verifiable | JSON result + generated markdown table, with hashes checked against the registry | 1 day |

Estimated total: about 6–8 working days. It is only worth building where a live experiment needs it (A1), or if B1
demand appears.

---

## 6. Opportunity comparison

Scores are 1–10, where higher is better on every axis. For "time/cost to validate", higher means cheaper and faster.
For "false-positive risk", higher means lower risk. A total is deliberately **not** given.

| Candidate | Indep. evidence | Data access | Honest test | Economics after costs | Competition / defensibility | Build feasibility | Customer demand | Scale | Time / cost to validate | False-positive risk | Fatal weakness | Confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **A1 PM liquidity rewards** | 5 | 7 | 6 | 4 | 3 | 7 | n/a | 4 | 8 | 4 | Adverse selection unknown; legality in DK unknown; validation of own fills ultimately needs real orders | Low–moderate |
| A2 PM crypto binaries | 3 | 4 | 5 | 2 | 3 | 6 | n/a | 3 | 5 | 4 | 7 % fee rate; forward-only data | Low |
| A3 Funding/basis cross-venue | 4 | 7 | 4 | 2 | 2 | 7 | n/a | 5 | 6 | 4 | Edge decayed (carry_v1) | Moderate (that it fails) |
| A4 Prediction-market arbitrage | 5 | 5 | 6 | 1 | 2 | 5 | n/a | 1 | 6 | 6 | Rare, seconds-long, ~15 shares | Moderate |
| A5 Crypto pairs | 4 | 8 | 5 | 2 | 2 | 8 | n/a | 4 | 7 | 3 | Frictions (Nefedov) | Moderate |
| B1 Validation kit | 7 (problem) | 8 | 5 | 3 | 3 | 8 | 2 | 4 | 7 | 4 | No demand evidence; buyer incentives | Low |
| B2 PM maker analytics | 4 | 8 | 6 | 3 | 3 | 8 | 2 | 3 | 8 | 5 | Depends on A1; competitors unknown | Low |
| B3 Retail TCA | 7 | 2 | 3 | 3 | 4 | 4 | 3 | 4 | 3 | 6 | Needs real orders | Low |
| B4 Data quality | 4 | 6 | 5 | 2 | 1 | 6 | 3 | 4 | 5 | 5 | Incumbents | Moderate (that it fails) |
| B5 Experiment tracking | 6 | 9 | 6 | 1 | 1 | 8 | 2 | 2 | 6 | 5 | Free incumbents | High (that it fails) |
| C Research engine | n/a | 9 | 8 | n/a | n/a | 9 | n/a | n/a | 8 | n/a | Value only via A1 or B1 | High (feasible) |

Score reasons for the leader: A1's evidence is 5 because the cash flow is documented [F] but its net value is not;
its economics are 4 because the snapshot is gross and capacity per market is about $2/day [M]; its false-positive
risk is 4 because snapshot yields are exactly the kind of number that disappears under costs.

---

## 7. Fatal uncertainties

| Option | Uncertainty most likely to invalidate it |
|---|---|
| A1 | (1) Adverse selection: makers filled before news or resolution lose more than the rewards [U]. (2) Realised payouts below the formula: caps, wash or self-quoting exclusion, uptime [U]. (3) Whether **Danish law and Polymarket's terms** allow it [U]. (4) Validating our own fills needs real orders, which the rules forbid; the study can only measure other makers. (5) Reward programmes can be cut at the venue's discretion ("may change over time" [F]). |
| B1 | Nobody pays. Its natural buyers (strategy sellers) may prefer unaudited claims [H]. |
| C | It has no value on its own; it only pays off if A1 or B1 proceeds. |

---

## 8. Cheapest decisive tests

All are read-only, money-free, and use public data.

1. **Payout reality check (A1), about 1 day.**
   - Find maker wallets in a sample of reward markets: on-chain fills via public Polygon logs, or the Polymarket data API.
   - Compare their on-chain daily reward receipts with the formula's prediction from minute snapshots of the book.
   - No-go if realised payouts are below 25 % of the predicted ones.
2. **Markout test (A1), about 3–5 days, mostly unattended data collection.**
   - For fills at reward-eligible prices in the sample, compute the maker markout at 1 h, 24 h and resolution.
   - Compare it with reward plus rebate per quoted share-day.
   - This is the decisive test.
3. **Legal check (A1), user only, 1–2 hours.** Ask Spillemyndigheden whether Polymarket participation by a Danish
   resident is lawful, and read Polymarket's terms on automated quoting. No-go for real money if it is not clearly
   allowed. Research may continue.
4. **Demand probe (B1), user-driven, about 2 weeks.**
   - Publish the existing write-ups and kit as open source, plus one honest article.
   - Contact 20 people who publish or sell strategies.
   - No-go if fewer than 3 of 20 say they would pay, or if there is no inbound interest in 30 days.
   - I can draft the material; the user decides whether and where to post.

---

## 9. 30-day plan (nothing starts without approval)

| Week | Work |
|---|---|
| 0 (now) | User reviews this report and decides. User does the legal check (test 3). |
| 1 | Write and commit the binding `PM_LP_SPEC.md` for `pm_lp_v1`: observational, no orders.<br>• Splits: development = first 7 days of forward snapshots, validation = next 7, holdout = next 14, sealed by code.<br>• Gates: payout ratio, net maker yield lower bound > 0, n_req.<br>• Minimal `research/core/` (registry + seal + manifest) only as needed.<br>• Code and tests committed before any collection. |
| 1–4 | Run a separate collector process (new; **needs approval**; existing processes untouched): minute book snapshots for a fixed random panel of about 200 reward markets, the public trade feed, and daily reward payouts. |
| 2 | Test 1 (payout check) on development data. Stop early if it fails. |
| 3 | Development and validation markouts. Freeze. |
| 4–5 | Open the holdout once. Verdict PASS, FAIL or INSUFFICIENT, plus a report. In parallel, only if A1 has already failed: start test 4 (demand probe for B1). |

## 10. No-go conditions

**A1** — abandon if any of these holds:
- realised payouts are below 25 % of predicted;
- the holdout net maker yield lower bound is ≤ 0;
- adverse selection is above 75 % of rewards in development and validation;
- capacity is below $1/day for a $100 quote in most markets after competition;
- the legal check is negative (no real money ever);
- the reward programme is materially cut during the study.

**B1** — abandon if fewer than 3 of 20 contacts express willingness to pay, there is no inbound interest within
30 days, or a free tool already does the same.

**C** — do not build beyond the minimum A1 needs unless B1 shows demand.

**Program level** — if A1 fails and B1 shows no demand, the evidence-based conclusion is to **stop investing in
this project**. Keep the paper processes only as long as they are useful as records.

---

## 11. Source register (all accessed 16.10.2026)

| # | Source | What it establishes |
|---|---|---|
| S1 | https://docs.polymarket.com/programs/liquidity-rewards.md | Rewards for resting limit orders; daily payout; quadratic score S = ((v−s)/v)²; two-sided minimum; single-sided ÷ 3 (c = 3.0); per-market max spread and min size; minimum payout $1 |
| S2 | https://docs.polymarket.com/programs/maker-rebates.md | Maker rebates of 15–25 % of taker fees by category, paid daily; rebate % "may change over time" |
| S3 | https://docs.polymarket.com/polymarket-learn/trading/fees (fetched 16.10) | Taker fee = rate × p × (1−p); rates 0–0.07; makers pay no fees |
| S4 | https://docs.polymarket.com/resources/onchain-position-data.md | On-chain `OrderFilled` / `OrdersMatched` / `FeeCharged` events usable to attribute fills |
| S5 | https://clob.polymarket.com/rewards/markets/current (API) | 14,202–14,241 reward markets; configured daily rates summing to $191–195k/day; per-market max spread and min size [M] |
| S6 | https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees | Base perp fees 0.045 % taker / 0.015 % maker; rebates only in higher tiers |
| S7 | Albiez 2026, SSRN, https://doi.org/10.2139/ssrn.7496818 | On-chain options makers: markout +13.05/contract = half spread 15.70 − adverse selection 2.65; net +8.93; losses concentrated in 10 wallets; pre-registered |
| S8 | Wang 2026, SSRN, https://doi.org/10.2139/ssrn.6624899 | 67 % of 273 top Polymarket wallets at least partly automated; profits concentrated |
| S9 | Yang, Cheng & Zou 2026, SSRN, https://doi.org/10.2139/ssrn.6624718 | Polymarket NBA arbitrage: 7 single-market episodes (median 3.6 s); combinatorial median 101 bp but ~14.8 shares executable |
| S10 | Lee, Lee & Lee 2026, SSRN, https://doi.org/10.2139/ssrn.6748186 | 113,338 Kalshi/Polymarket crypto contracts: positive VRP, Polymarket's ~16× Kalshi's; both "systematically underconfident" |
| S11 | Nefedov 2026, SSRN, https://doi.org/10.2139/ssrn.7350238 | Naïve protocols inflate crypto factor Sharpe 3.6×; none of six factors survives deflation; funding carry only under optimistic costs |
| S12 | Stotz 2026, SSRN, https://doi.org/10.2139/ssrn.7540899 | 2,088 real retail orders at 6 German brokers: 123–458 bp all-in costs vs 16–34 bp spreads |
| S13 | Bailey, Borwein, López de Prado & Zhu 2014, *Notices AMS*, https://doi.org/10.1090/noti1105 | Backtest overfitting (title/venue verified; content from my knowledge) |
| S14 | Bailey et al. 2016, *J. Computational Finance*, https://doi.org/10.21314/jcf.2016.322 | Probability of backtest overfitting (verified title/venue) |
| S15 | Harvey & Liu 2015, *JPM*, https://doi.org/10.3905/jpm.2015.42.1.013; Suhonen, Lennkh & Perez 2017, *JPM*, https://doi.org/10.3905/jpm.2017.43.2.090; Arnott, Harvey & Markowitz 2019, *JFDS*, https://doi.org/10.3905/jfds.2019.1.064 | Literature on backtest overfitting and protocols (titles/venues verified) |
| S16 | Glosten & Milgrom 1985, *JFE*, https://doi.org/10.1016/0304-405x(85)90044-3; Malinova & Park 2015, *JF*, https://doi.org/10.1111/jofi.12230 | Adverse selection in quoting; maker–taker fees change quotes but not all-in taker costs |
| S17 | Fil & Kristoufek 2020, *IEEE Access*, https://doi.org/10.1109/access.2020.3024619 | Crypto pairs trading literature exists (title/venue verified) |
| S18 | https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/AITradingBots.html | CFTC advisory: fraudsters tout bots with "tens of thousands of percent" returns |
| S19 | https://strategyquant.com/pricing/ | SQ X lifetime $1,490 (Professional, incl. advanced robustness tests) / $2,900 (Ultimate) sale; list $1,790 / $4,900 |
| S20 | https://hudsonthames.org/mlfinlab/ | MlFinLab Business £100 (+VAT) per month per user |
| S21 | https://www.quantconnect.com/pricing/ | Tiered plans (Researcher, Team, Trading Firm, Institution); consulting from $4,800 |
| S22 | https://tardis.dev/ | Historical data plans $350–3,000/month; claims 99.9 % completeness |
| S23 | https://www.coinapi.io/market-data-api/pricing | $79 / $249 / $599 per month tiers |
| S24 | https://wandb.ai/site/pricing/ | Free tier; Pro from $60/month |
| S25 | https://3commas.io/pricing ; https://www.tradingview.com/pricing/ | Retail bot and charting subscriptions ($15–20/month; DKK 79.95/month) — consumers pay for trading tools |
| S26 | GitHub API (api.github.com/repos/…) | Stars: freqtrade 55,464; nautilus_trader 30,199; mlflow 28,418; backtrader 23,493; Lean 22,034; hummingbot 20,484; dvc 15,925; great_expectations 11,876; vectorbt 9,394; jesse 8,650; mlfinlab 4,941; Polymarket/agents 3,800; py-clob-client 1,227; zipline-reloaded 1,963; pypbo 143 |
| S27 | https://docs.polymarket.com/developers/CLOB/geoblock (`NEXT_MECHANISMS.md`) | Denmark not on the restricted list; DE/FR/BE/IT/PL/GB close-only |

Own measurements:
- **[M1]** `python -m research.pm_rewards_snapshot 300 11` at 2026-10-16 21:45 UTC: 286 markets; gross yield p25 0.32 %, median 1.97 %, p75 7.33 %, p90 19.25 % per day; median $1.85/day on $96 capital; 28 % without competition.
- An earlier identical run (seed 7) gave a median of 2.15 % on 288 markets.
- YES/NO book mirroring was checked on 3 markets.

## 12. Final decision

- **Primary: A1, an observational study of Polymarket liquidity-provision economics (`pm_lp_v1`).**
  - It is the only candidate with a documented, positive cash flow, measurable costs from public data, a cheap and decisive falsification, and no need for money, speed or prediction.
  - It is chosen despite low-to-moderate confidence because the test is cheap and its likely negative result would be informative.
- **Fallback: C + B1, a minimal research engine packaged as an open-source sealed-holdout kit, with a demand probe.**
  - It reuses what demonstrably works here (the discipline, not a strategy).
  - It is robust to A1's main failure mode (adverse selection), costs almost nothing, and gives a clear stop rule.
- **Not chosen:** any new price-prediction strategy (A2–A5), retail TCA (needs real orders), data-quality and experiment-tracking products (incumbents, free alternatives).

Nothing is built until the user approves. The next concrete step after approval is a binding `PM_LP_SPEC.md`,
committed before any data collection.
