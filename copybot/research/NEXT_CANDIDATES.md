# Next research candidate: portfolio audit, literature and ranking (16.10.2026)

Repository commit at the start of this review: `e551ebf059b777fe2e3b9afae42622156bc3a52a` (clean tree). No previous
result, specification or locked file was changed. No experiment was run for this document; only data
*availability* and current spreads were checked.

## 1. Portfolio audit: what was tested and why it failed

| # | Idea | Strongest evidence | Rejection reason (primary) |
|---|---|---|---|
| 1 | Copy leaderboard wallets | 114 copied trades, 14 days | Copyable trades lose even at 0 s and zero fees (−6.5 %) → **no signal** in what is copyable |
| 2 | Self-found traders, copy 2–10 s later | 98 wallets, rank corr. +0.43 | Their edge is speed; 2 s later −7 % → **execution / latency** |
| 3 | SOL trend rules (hourly) | 7 months | Lost to trading costs → **costs from high turnover** |
| 4 | Buy pump.fun graduations | 443 coins | Median −95 % within an hour → **adverse selection** |
| 5 | Graduation sniper (historical + live) | 160 + 279 pools, 149 live trades/rule | Looked positive on 160, failed on 279 and live → **overfitting**, then latency |
| 6 | Short new Hyperliquid listings | 23 listings | Rare doublings outweigh many wins → **tail risk**, tiny sample |
| 7–8 | Funding carry (first version), leverage | 40 perps | Not pre-registered, survivorship, no spot leg → **invalid test** |
| 9 | Stop-when-ahead | sniper trades | Does not change expectancy → **no signal** |
| 10 | Launch flow features (launch_v1) | 600 graduations | Positive on train, collapsed on validation → **overfitting / non-persistence** |
| 11 | Smart money (smart_v2) | 1,200 graduations, holdout | No signal even on train → **no signal** |
| 12 | SOL/USDC pool arbitrage (arb_v1) | 13,049 slots | Gap never above fees → **competition already removed it** |
| 13 | Delta-neutral carry (carry_v1) | 152 weeks | Holdout positive, development negative, decaying → **edge shrank below costs** |

### Repeated failure patterns

1. **Competing on speed against professionals** (2, 5, 12): any edge measured in seconds or slots belongs to
   searchers with co-located infrastructure. A home PC on free RPCs arrives late by construction.
2. **Adverse selection in new tokens** (1, 4, 10, 11): early, fast participants and creators sell to later ones.
   Signals visible to a late entrant are already priced or are noise.
3. **Turnover × costs** (3, 13): small edges disappear when positions change often.
4. **Overfitting / non-persistence** (5, 10): rules that looked good on one period failed on the next. The
   pre-registration and train/validation/holdout procedure caught it every time.
5. **Data limits** (7, arbitrage beyond constant-product pools): many tempting ideas cannot be reconstructed with
   free data at the needed resolution.

What this implies for the next candidate: **low turnover, no speed requirement, liquid instruments, a mechanism
documented in peer-reviewed work, and long independent data with an untouched holdout.**

## 2. Sources (verified via Crossref by DOI, arXiv, or the publisher page on 16.10.2026)

Published evidence is quoted from abstracts where available; "summary" lines are my own description of the paper
and are marked as such.

- **Liu & Tsyvinski (2021).** Risks and Returns of Cryptocurrency. *Review of Financial Studies* 34(6):2689–2727.
  https://doi.org/10.1093/rfs/hhaa113 — abstract: "there is a strong time-series momentum effect, and proxies for
  investor attention strongly forecast future cryptocurrency returns."
- **Liu, Tsyvinski & Wu (2022).** Common Risk Factors in Cryptocurrency. *Journal of Finance* 77(2):1133–1177.
  https://doi.org/10.1111/jofi.13119 — abstract: "three factors—cryptocurrency market, size, and momentum—capture the
  cross-sectional expected cryptocurrency returns."
- **Schmeling, Schrimpf & Todorov (2023).** Crypto carry. BIS Working Paper 1087. https://www.bis.org/publ/work1087.htm
  — abstract: carry "can become very large (up to 60% p.a.) and varies strongly over time", driven by
  "trend-chasing and attention by smaller investors" and "the relative scarcity of 'arbitrage' capital".
- **He, Manela, Ross & von Wachter.** Fundamentals of Perpetual Futures. arXiv:2212.06888 — abstract: deviations
  from no-arbitrage prices "are larger than in traditional currency markets, comove across currencies, and diminish
  over time."
- **Makarov & Schoar (2020).** Trading and arbitrage in cryptocurrency markets. *Journal of Financial Economics*
  135(2):293–319. https://doi.org/10.1016/j.jfineco.2019.07.001 — summary (mine): large, recurring cross-exchange
  price deviations, especially across countries, linked to frictions in moving capital.
- **Moskowitz, Ooi & Pedersen (2012).** Time series momentum. *Journal of Financial Economics* 104(2):228–250.
  https://doi.org/10.1016/j.jfineco.2011.11.003 — summary (mine): an asset's own past 1–12-month return predicts its
  future return across asset classes.
- **Jegadeesh & Titman (1993).** Returns to Buying Winners and Selling Losers. *Journal of Finance* 48(1):65–91.
  https://doi.org/10.1111/j.1540-6261.1993.tb04702.x
- **Daniel & Moskowitz (2016).** Momentum crashes. *Journal of Financial Economics* 122(2):221–247.
  https://doi.org/10.1016/j.jfineco.2015.12.002 — summary (mine): momentum suffers rare, severe crashes, notably in
  rebounds after market declines.
- **McLean & Pontiff (2016).** Does Academic Research Destroy Stock Return Predictability? *Journal of Finance*
  71(1):5–32. https://doi.org/10.1111/jofi.12365 — abstract: "Portfolio returns are 26% lower out-of-sample and 58%
  lower post-publication."
- **Hou, Xue & Zhang (2020).** Replicating Anomalies. *Review of Financial Studies* 33(5):2019–2133.
  https://doi.org/10.1093/rfs/hhy131 — summary (mine): most published equity anomalies fail to replicate under
  stricter tests.
- **Harvey, Liu & Zhu (2016).** …and the Cross-Section of Expected Returns. *Review of Financial Studies* 29(1):5–68.
  https://doi.org/10.1093/rfs/hhv059 — summary (mine): with many tested factors, much higher significance thresholds
  are needed (multiple testing).
- **Novy-Marx & Velikov (2016).** A Taxonomy of Anomalies and Their Trading Costs. *Review of Financial Studies*
  29(1):104–147. https://doi.org/10.1093/rfs/hhv063 — summary (mine): trading costs remove most high-turnover anomalies.
- **Bailey & López de Prado (2014).** The Deflated Sharpe Ratio. *Journal of Portfolio Management* 40(5):94–107.
  https://doi.org/10.3905/jpm.2014.40.5.094 — summary (mine): adjusting reported Sharpe ratios for selection bias
  and the number of trials.
- **Daian et al. (2020).** Flash Boys 2.0. *IEEE S&P 2020*:910–927. https://doi.org/10.1109/sp40000.2020.00040 and
  **Qin, Zhou & Gervais (2022).** Quantifying Blockchain Extractable Value. *IEEE S&P 2022*:198–214.
  https://doi.org/10.1109/sp46214.2022.9833734 — summary (mine): on-chain arbitrage/front-running is a competitive
  race won by specialised bots.
- **Cong, Li, Tang & Yang (2023).** Crypto Wash Trading. *Management Science* 69(11):6427–6454.
  https://doi.org/10.1287/mnsc.2021.02709 — summary (mine): reported volume on many venues is inflated by wash
  trading, contaminating volume-based signals.

## 3. Data and cost checks done for this review (availability only, no returns)

- Binance public API: spot daily candles from 2017-08-17, USDⓈ-M funding from 2019-09-10 (independent of Hyperliquid).
- Hyperliquid: daily candles for all sampled perps, including delisted ones (32/32 active, 7/7 delisted in a sample).
- Hyperliquid half-spreads measured now: BTC 0.0006 %, ETH 0.0021 %, SOL 0.0048 % (fee 0.045 % per side dominates).

## 4. Ranked candidates

Scores 1 (worst) – 5 (best). "Turnover / costs" high = low turnover and low cost sensitivity.

| Rank | Candidate | Mechanism | Evidence | Data | Turnover / costs | Overfit / leakage risk | Replication | Capacity | Main evidence against |
|---|---|---|---|---|---|---|---|---|---|
| **1** | **Time-series momentum, BTC/ETH/SOL, weekly** | Trend-chasing and attention of retail (Liu & Tsyvinski; BIS carry) | 4 (RFS 2021, crypto-specific; classic TSMOM) | 5 (Binance 2017+, funding 2019+; HL for costs) | 4 (weekly, liquid) | 4 (few parameters from literature; long untouched holdout) | 5 | 5 | Post-publication decay (−58 %, McLean & Pontiff); momentum crashes; directional risk; our hourly SOL trend failed (different horizon) |
| 2 | Cross-sectional momentum, Hyperliquid perps | Same plus slow diffusion across coins (Liu, Tsyvinski & Wu) | 4 (JF 2022) | 3 (HL only since 2023; delisted coverage to verify) | 3 (weekly, small perps cost more, funding on both legs) | 3 (portfolio choices) | 4 | 3 | Short sample, small-coin costs/spreads, size effect may not survive liquidity filters |
| 3 | Funding as cross-sectional signal | Crowded longs pay, crash risk (BIS) | 3 | 4 | 3 | 3 | 4 | 3 | Overlaps carry (FAIL); crash risk |
| 4 | Cross-exchange arbitrage | Capital-mobility frictions (Makarov & Schoar) | 4 | 2 (needs several exchanges' order books) | 2 | 3 | 2 | 2 | Deviations "diminish over time" (He et al.); needs accounts, capital on several venues |
| 5 | On-chain DEX arbitrage / MEV | Latency races | 4 (that it exists) | 2 | 1 | 3 | 2 | 2 | Won by specialised searchers (Daian; Qin); arb_v1 found 0 |
| 6 | Memecoin launch selection | — | 1 | 3 | 1 | 2 | 3 | 1 | Six rejections; wash trading contaminates volume (Cong et al.) |

## 5. Recommendation

**Candidate 1: weekly time-series momentum on BTC, ETH and SOL**, specified in `research/TSMOM_SPEC.md`. It is the
only candidate that avoids every repeated failure pattern: no speed, low turnover, the most liquid instruments,
peer-reviewed crypto-specific evidence, and ~9 years of independent data with an untouched holdout.

Honest prior: the effect is published (2021), so decay is expected; momentum is directional with crash risk; and
our hourly SOL test lost. A FAIL is a realistic outcome. The experiment is still justified because it is cheap
(free data, a few hours), uses a mechanism with independent evidence, and has a holdout we have not looked at.
If it fails, the evidence would not justify further strategy searches in this environment.

## 6. Missing information and blockers

- Historical spreads are unknown; current measured spreads × 3 are used as an estimate, plus a high-cost scenario.
- Funding before 2019-09 is unavailable, so development starts 2019-10.
- Execution would be on Hyperliquid perps, but history comes from Binance; Hyperliquid's own funding is used where
  it exists (2023-05+). The spec includes a price cross-check between the two sources on overlapping days.
- Binance API access can be region-dependent; it worked from this machine on 16.10.2026.

## 7. Next action (least work)

On approval: implement `research/tsmom.py` and its tests against `TSMOM_SPEC.md`, commit before fetching data, run
development + validation, freeze `n_req` and the lookback, then open the holdout once.
