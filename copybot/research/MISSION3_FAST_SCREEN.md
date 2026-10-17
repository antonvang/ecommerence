# Mission 3: fast screens on free historical data (17.10.2026)

| Step | Commit |
|---|---|
| Registration, before evaluation data | `e1af661` |
| Code | `9792ac2` |

Run: `python -m research.m3 dev`. The results are in `data/research/m3/m3_dev.json` (git-ignored, reproducible from
the free archives).

**Time from mission to first decisive evidence: about 1.5 hours.**

## Verdict

**All three candidates are REJECTED at the development stage.**
- All 60 registered variants have a negative mean net return on 2023 data.
- No variant qualified for confirmation, so the 2024 confirmation data was never downloaded.
- 2025–2026 is untouched.

The common cause is a **cost wall**.

| Candidate | Best gross signal | Round-trip cost |
|---|---|---|
| M1 | +0.6 bp | 12 bp |
| M2 | +7.2 bp | 20 bp |
| M3 | +2.4 bp | 34 bp |

Taker strategies on liquid BTC instruments at minute-to-hour horizons cannot pay these costs with these signals.

## Data (verified 17.10.2026, data.binance.vision, free)

| Dataset | Coverage | 2023 completeness |
|---|---|---|
| USDⓈ-M BTCUSDT 1-minute klines (incl. taker-buy volume) | 2020-01 → 2026-09 | 525,600 / 525,600 minutes |
| Spot BTCUSDT 1-minute klines | 2017-08 → 2026-09 | 525,520 |
| Premium index 1-minute klines | 2020-01 → 2026-09 | 524,146 (99.7 %) |
| USDⓈ-M metrics (5-minute open interest) | 2020-09-01 → 2026-10-15 | 105,117 / 105,120 |
| Futures bookTicker (L1 quotes) | 2023-05 → 2024-04 only | Not used (see "Limitations") |
| Liquidation snapshots (BTCUSDT) | Not available | — |

Timestamps are exchange-generated (milliseconds). Klines give open-to-open prices, not executable quotes. The spread
is about 0 bp for the BTC perpetual; the slippage allowances are the registered ones.

## The three candidates

### M1. Order-flow imbalance (microstructure)

| | |
|---|---|
| **Mechanism** | Signed flow moves prices (Kyle 1985; Cont, Kukanov & Stoikov 2014); imbalances predict short-horizon returns (Chordia & Subrahmanyam 2004) |
| **Test** | Imbalance over k ∈ {1, 5, 15} min; tails q ∈ {1 %, 0.1 %}; hold h ∈ {1, 5, 15} min; continuation or reversal; costs 12 bp round trip; 36 variants |
| **Result** | Mean **gross** returns from −0.64 to +0.64 bp on 283–9,762 trades per variant. Net −11.4 to −12.6 bp, no better than the random-entry baseline (−11.4 to −12.7 bp). |
| **Reading** | Once you can act on a minute's flow (next-minute open), its predictive content for BTC is gone. Any price impact is contemporaneous and already in the price. |
| **Reject because** | The signal is ≈ 0 gross; no cost level can save it. |

### M2. Liquidation-cascade reversal (public historical data)

| | |
|---|---|
| **Mechanism** | Forced, price-insensitive selling overshoots, and liquidity providers are paid to absorb it (Brunnermeier & Pedersen 2009) |
| **Test** | 5-minute OI drop ≥ x ∈ {0.5, 1, 2} % with price move ≥ y ∈ {0.5, 1} %; trade against the move; hold h ∈ {15, 60, 240} min; costs 20 bp; 18 variants |
| **Result** | **Gross positive only at h = 15 min with y = 1 %: +4.2 to +7.2 bp** (n = 54–113, win rate 39–43 %). All 18 variants are net negative (−12.8 to −51.1 bp). Longer holds turn gross negative (−4 to −31 bp): the overshoot does not persist. Net was still better than the baseline (≈ −20 bp) at h = 15. |
| **Reading** | There is a small, short-lived reversal after large cascades, too small for taker costs. It is the only signal here with a plausible sign. With n ≈ 50–110 per year it is also statistically weak. |
| **Reject because** | Net < 0; capturing it would need maker execution during cascades, exactly when adverse selection is worst. Not testable honestly without queue data. |

### M3. Perpetual premium convergence (pricing constraint)

| | |
|---|---|
| **Mechanism** | Funding ties the perpetual to the index; large premiums should revert (He, Manela, Ross & von Wachter, arXiv:2212.06888) |
| **Test** | Short perp + long spot when the premium ≥ θ ∈ {0.05, 0.10, 0.20} %; exit at premium ≤ 0 or after H ∈ {60, 480} min; costs 34 bp; 6 variants |
| **Result** | Premiums do revert, usually within 6–75 min (mean hold). But the realised convergence is only **+0.6 to +2.4 bp gross**. Net −31.6 to −33.4 bp (n = 167–2,117), win rate ≤ 2 %. |
| **Reading** | The minute premium index is noisy. The executable spot–perp price gap at entry is already much smaller than the premium index suggests. |
| **Reject because** | Gross convergence is one tenth of the costs. |

## Fees and execution limitations

- Fees use Binance's standard VIP0 rates (futures taker 0.05 %, spot taker 0.10 %). They are **ESTIMATED**: not
  re-verified today, because the web fetch tools failed. Lower VIP tiers or maker rebates would change M2's
  arithmetic, but not M1's or M3's.
- Entry and exit are at 1-minute opens. Real taker fills would pay the spread and slip in fast markets, so the costs
  used are a floor, not a ceiling.
- No queue-position data exists for free. Maker strategies cannot be backtested honestly from these archives, and
  the bookTicker archive (May 2023 – April 2024) gives L1 quotes without queue depth.

## Recommended next experiment and decision point

**No new taker-strategy screen on liquid crypto is recommended.** Across P1, M1, M2 and M3 the gross signals at
minute-to-hour horizons are ≤ 7 bp against 12–34 bp of costs. Searching more variants would only raise the risk of a
false positive.

**The next informative experiment is the one already running: pm_lp_v1.** It is the only candidate whose cash flow
is a venue subsidy rather than a price prediction, which is where the cost wall does not apply in the same way.

**Earliest defensible decision point: 31.10.2026.** That is when pm_lp_v1's development and validation evaluation
can run (validation ends 30.10). A validation mean ≤ 0 means FAIL, and with it the end of the active trading
research.

## Confirmation that pm_lp_v1 was untouched

- **Collector:** still running (PID 33740 / 29004; keep-awake 19436). Last snapshot 19 s old at the time of
  writing. 5,000 of 5,000 trade polls succeeded. Panels for day −1 and day 0, 200 markets each.
- **pm_lp files:** no file was changed (last change `0c86f5c`). Its database was only opened read-only by P3 earlier,
  to exclude panel markets, and not at all by Mission 3.
- **Other processes:** the paper process (PID 29500) was not touched.
