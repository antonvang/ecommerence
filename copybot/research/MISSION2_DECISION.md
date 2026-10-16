# Mission 2: fastest path to a real opportunity — decision (17.10.2026)

Baseline: branch `claude/why-cant-we-do-this-wh3ohb`; tests registered in `research/PRELIM_2026-10-17.md` (commit
`d9bb785`) before their data was fetched. pm_lp_v1 was not touched: its collector, methodology and panel are
unchanged, and none of its reserved days exist yet. No orders, no accounts, no spending, no contact with anyone.

**Tool limitation (unchanged):** web search and web fetch were broken in this session. Sources come from direct HTTP
fetches of official pages and from the Crossref, GitHub, Polymarket and Binance APIs. Competitor discovery is
incomplete.

## 1. Short answer

**User decision (17.10.2026): Webshopdoktoren is out of scope.** It is listed in §2 as an asset only.

| | Decision |
|---|---|
| **Primary** | **pm_lp_v1 continues unchanged** (Polymarket liquidity rewards). P3 (§3) gave the earliest available evidence on its main unknown: aggregate passive fills roughly break even before rewards. That does not refute it, so the rewards could still make it net positive. First decisive read after 30.10. |
| **Parallel fallback (Track B)** | **None with verified demand today.** The cheapest decisive software test is a demand probe for the sealed-holdout research kit (B4). It requires publishing and contacting people, which needs the user's explicit approval. Until then Track B is parked. |
| **Longer-term** | Polymarket maker tooling (reward yield + markout analytics), **only if** pm_lp_v1 passes. Free data competitors exist, so the value would be in the maker economics, not the data. |
| **Rejected today** | P1 (15-min BTC model vs market): every variant lost after fees, and the data gate failed. P2 (negRisk arbitrage): 0 opportunities (§3a). |

## 2. Assets found (Phase 1, verified)

| Asset | State |
|---|---|
| `copybot/` | 102 tests pass. 16 trading ideas tested; every rule tested under the pre-registered procedure failed its standard. A research engine with sealed holdouts. pm_lp_v1 collector running (PID 33740) since 16.10 22:02 UTC. Paper bot running (PID 29500). |
| **Branch `webshopdoktoren`** (14–15.10.2026, 12 commits) | `gmc_doktor/`: a working checker (Python standard library only) for Danish Shopify stores against Google Merchant Center rules and Danish webshop information duties. Also: a lead pipeline from public data (Common Crawl → DNS → front page), a call sheet, a call dashboard, a sales site (unpublished), an outreach kit with a lawful-contact policy (phone first, no cold e-mail, SMS or DM; marketing law § 10), and draft B2B terms. **Locked test criterion:** success ≥ 1 paid order (≥ 495 kr.) from a non-relative within 7 days; it requires ≥ 100 call attempts and ≥ 30 decision-maker conversations; otherwise STOP. **Whether it was run is unknown**: no lead data or results exist on this PC, and `FASE15_DECISION.md` is not in the repository. |
| `mt5-bot/` (25.09) | NAS100/US500 MT5 bots. Its own README: "no day-trading rule has a clear advantage after costs". NasDipEA ≈ 4.7 %/yr vs buy-and-hold ≈ 18 %/yr. Not pre-registered. Not a candidate. |
| `freellmapi/` (separate folder) | A third-party open-source project. Not ours to commercialise; not assessed. |
| Constraint documented in the repository | `GUIDE_TIL_DEN_VOKSNE.md` and `OUTREACH_KIT.md` state that the user is a young entrepreneur: an **adult** must own the invoicing business, bank account and contracts. That applies equally to any real-money trading venue. Polymarket's own age rule could not be verified: its terms page is JavaScript-rendered. |
| Budget | No spending approved. Free public APIs only. Disk: 238 GB free. |

## 3. Track A: trading hypotheses

| # | Hypothesis | Mechanism and independent evidence | Data (free?) | Fastest test | Result |
|---|---|---|---|---|---|
| A1 | Polymarket liquidity rewards (pm_lp_v1) | Venue subsidy, documented (docs.polymarket.com/programs/liquidity-rewards). Analog: Albiez 2026 (https://doi.org/10.2139/ssrn.7496818). | Yes, forward only | Running; first read after 30.10 | Pending (unchanged) |
| **P1** | **15-min BTC "Up or Down": random-walk TWAP model vs market price** | Underconfidence: Lee, Lee & Lee 2026 (https://doi.org/10.2139/ssrn.6748186). Resolution is the Chainlink 60-s TWAP vs the start price (market rules). | Yes: Polymarket trade prints, Binance 1-minute klines | Exploration week 1–7.10.2026 (672 markets, 2,009 observations), fees 0.07·p(1−p) + 1 cent | **REJECTED**. All 12 (m, θ) pairs have a negative mean net return: −1.3 % to −17.6 % per trade; best lower bound −8.2 %. Baseline "buy the favourite" also loses: −1.2 % to −3.5 %. **Data gate D failed**: Binance closes reproduce the oracle outcome in only 84 % of windows (required 95 %). Confirmation week not fetched, as registered. |
| **P2** | **negRisk sum-of-prices arbitrage** | Complete mutually exclusive sets must sum to 1. Against: Yang, Cheng & Zou 2026 (https://doi.org/10.2139/ssrn.6624718) found such episodes rare, seconds long, ~15 shares. | Yes: live order books | 3 snapshots, 30 min apart, of all complete negRisk events | Snapshot 1 (22:30 UTC): **0 opportunities in 7,612 events** (23,093 active events). Snapshot 2: also 0. **REJECTED** (§3a). |
| **P3** | **Historical passive fills to resolution** (early evidence on pm_lp's adverse selection; registered in `267f117`) | Glosten & Milgrom 1985; Albiez 2026 (maker markouts on an on-chain book) | Yes: v2 trade prints, resolutions | 200 resolved markets (end 15.09–14.10.2026, ≥ $10k volume, pm_lp panel excluded); taker trades priced 0.10–0.90 in the last 7 days; 164 markets, 9.37 M shares | **Inconclusive.** Maker P&L at resolution −0.39 cents/share (99 % bounds −6.6 / +4.1). At +1 h: +0.22 cents (−1.2 / +2.2). By price bucket from −6.6 cents (0.9x) to +5.4 cents (0.2x), noisy. Aggregate makers, including professionals inside the spread, roughly break even before rewards. This neither confirms nor refutes pm_lp. |
| A4 | Cross-venue funding/basis; crypto pairs; Hyperliquid market making | Covered in `STRATEGIC_OPPORTUNITY_REVIEW.md` | — | — | Rejected there (carry_v1 FAIL; Nefedov 2026; positive maker fee) |
| A5 | NAS100 dip-buying (mt5-bot) | Our own non-pre-registered backtest | Dukascopy | — | Not pursued: 4.7 %/yr vs buy-and-hold 18 %/yr; recycling a weak idea |

What P1 establishes: with public proxies, a simple model cannot beat these markets after fees. Competitors price off
the actual Chainlink stream; our 84 % match rate shows how much information the proxy misses. A fair rerun would need
historical Chainlink TWAP data. It is unclear whether that is freely available, and the evidence does not justify
pursuing it.

### 3a. P2 snapshots

| Snapshot (UTC) | Active events | Complete negRisk events checked | Opportunities | With ≥ $5 profit |
|---|---|---|---|---|
| 16.10 22:30 | 23,093 | 7,612 | 0 | 0 |
| 16.10 23:10 | 23,061 | 7,562 | 0 | 0 |

**P2 REJECTED.** No opportunity even below $5. The registered rule needed ≥ 2 of 3 snapshots with an opportunity,
which could no longer be met. The third snapshot was therefore cancelled: it needs about 3 GB of RAM next to the
pm_lp collector, and the PC had 0.9 GB free. This matches Yang et al. 2026.

## 4. Track B: software and business

| # | Opportunity | Verified problem | Verified competition | Demand evidence | First decisive test | Verdict |
|---|---|---|---|---|---|---|
| B1 | Webshopdoktoren: GMC compliance check + fixed-price fix (495 / 995 kr.) — **excluded by the user, 17.10** | Google suspends Merchant Center accounts "upon detection and without prior warning"; accounts are "only reinstated in compelling circumstances" (https://support.google.com/merchants/answer/6150127) | GitHub: few tools (gmc-mcp 17★; two suspension-audit repos with 1★). The Shopify App Store search page is JavaScript-only, so its apps are unknown. Agencies are unknown (no web search). | **None verified.** The problem exists; whether stores pay is untested. | The existing locked 7-day call test | **Excluded** |
| B2 | Polymarket data or maker analytics | Researchers build their own archives (Dubach 2026; Yang et al. 2026). Resolved markets keep only daily price history (verified). | **Strong free competitors:** Jon-Becker/prediction-market-analysis 3,878★ ("largest publicly available dataset of Polymarket and Kalshi"), warproxxx/poly_data 2,337★, SII-WANGZJ/Polymarket_data 871★ (1.1 billion trades) | None | — | Not now. Only maker analytics, and only if pm_lp passes. |
| B3 | Accessibility (EAA) checker for webshops | The EAA covers e-commerce services from 28.06.2025 (Directive (EU) 2019/882, Art. 2) | Many paid incumbents (not checked in this session) | — | — | **Weakened:** "Microenterprises providing services shall be exempt" (fewer than 10 staff and ≤ €2M turnover), i.e. most small Danish webshops (https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019L0882) |
| B4 | Sealed-holdout strategy-validation kit | Overfitting literature; Nefedov 2026 | Paid robustness tools (StrategyQuant, MlFinLab) | None | Open-source + demand probe | Long shot (see review §4) |

## 5. Ranking (after the user's exclusion of B1)

| Criterion | A1 pm_lp_v1 | B4 validation kit | B2 Polymarket maker tooling |
|---|---|---|---|
| Time to first decisive evidence | 14 days (30.10); P3 gave an early, inconclusive read today | ~2 weeks after a publish/outreach approval | Only after pm_lp |
| Independent evidence | Subsidy verified (docs, API); aggregate fills ≈ break-even before rewards (P3) | Problem verified (overfitting literature); demand none | Free competitors verified on GitHub |
| Cost to test | 0 (running) | ≈ 0 | ≈ 0 |
| Feasibility | Running | Mostly built | Partly built (snapshot script, collector) |
| Economics | Small per market (≈ $2/day gross per 100-share quote); net unknown | Unknown | Unknown |
| Competition | Professional makers | Paid incumbents + free OSS | Strong free OSS |
| Scalability | Limited by reward pools ($191k/day in total) | Moderate | Low–moderate |
| Probability of simply being wrong | High | High | High |
| Safe for existing experiments | — | Yes | Yes |

## 6. Decision and next actions

**Strongest current candidate: A1 (pm_lp_v1)**. That is not because it is likely to work. It is the only live
candidate whose key cash flow is documented, its first decisive result is 2 weeks away, and P3 did not refute it.

| Outcome | Rule |
|---|---|
| **Continue** | Under the frozen spec: development + validation mean > 0 after 30.10, then the holdout gates after 27.11 |
| **Stop** | Validation mean ≤ 0 (FAIL), or holdout G1/G2 fail. Coverage below 90 % makes it INSUFFICIENT. No real money in any case without the legal and age checks (§2). |

**Next three actions:**
1. **Me (automatic):** keep the collector running. After 30.10, run `python -m research.pm_lp dev` and commit
   `PM_LP_FROZEN.md`. Report the verdict that day.
2. **User:** keep the PC on (lid open) until 27.11. Optionally approve adding the collector to Windows startup, so a
   reboot does not create gaps.
3. **User (optional):** decide whether to approve a B4 demand probe: open-sourcing the research kit plus one honest
   write-up, posted from the user's own account. Without that approval, Track B stays parked.

**What remains unknown:**
- pm_lp's net economics (adverse selection at our quote distance, realised reward share);
- Polymarket's age rule and Danish legality;
- demand for any software product.

## 7. Results files

| Path (git-ignored data, reproducible with `python -m research.prelim …`) | Contents |
|---|---|
| `data/research/prelim/p1_explore.json`, `p1_explore_result.json` | P1 data and grid |
| `data/research/prelim/p2_snapshots.jsonl` | P2 snapshots |
| `data/research/prelim/p3_markets.json`, `p3_result.json` | P3 data and result |
