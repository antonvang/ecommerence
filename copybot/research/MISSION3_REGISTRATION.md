# Mission 3 fast screens: registration (17.10.2026, before any evaluation data was downloaded)

Only data availability was checked: the S3 listings of data.binance.vision. pm_lp_v1 is untouched. All new data goes
to `data/research/m3/`. No orders, no accounts, no purchases.

None of these repeats an earlier idea:
- tsmom used weekly closes;
- carry measured weekly funding;
- P1 was a TWAP model on Polymarket;
- P2 was negRisk sums.

## Common rules

| Item | Rule |
|---|---|
| Instrument | Binance USDⓈ-M BTCUSDT perpetual (1-minute klines incl. taker-buy volume); spot BTCUSDT for M3 |
| Fees | Futures taker 0.05 %/side; spot taker 0.10 %/side. These are Binance's standard VIP0 rates, not re-verified today (ESTIMATED). |
| Slippage | M1 and M3 0.01 %/side; M2 0.05 %/side (cascades) |
| Development | **2023-01-01 → 2023-12-31** |
| Confirmation | **2024-01-01 → 2024-12-31**. Downloaded only after `MISSION3_CHOICE.md` is committed, and only for candidates with a positive development survivor. |
| Reserved | **2025-01-01 → 2026-10** is not touched. It is kept as a later holdout. |
| Development pass | At least one variant has mean net > 0 with the minimum sample. The best such variant (highest mean net) goes to confirmation. Otherwise the candidate is rejected. |
| Confirmation gates | n ≥ minimum; mean net > 0; one-sided 99 % lower bound > 0 (bootstrap over UTC days, 10,000 draws, seed 5); mean net > baseline |
| Reporting | Every variant, with gross and net values |

**PASS (preliminary)** only triggers a forward paper test plus the reserved holdout, each registered separately.

## M1. Order-flow imbalance (microstructure)

**Mechanism.** Signed order flow moves prices (Kyle 1985; Cont, Kukanov & Stoikov 2014, *J. Financial
Econometrics*). Order imbalances predict short-horizon returns (Chordia & Subrahmanyam 2004, *JFE*). Continuation
follows from persistent flow; reversal follows from temporary impact.

**Signal.** I_k = Σ(2·takerBuy − volume)/Σ volume over the last k minutes, k ∈ {1, 5, 15}.
- Thresholds: the development-period quantiles q ∈ {1 %, 0.1 %} in each tail. They are frozen for confirmation.
- Direction ∈ {continuation, reversal}.
- Entry at the next minute's open; exit at the open h ∈ {1, 5, 15} minutes later; no overlapping trades.

**Costs.** 0.12 % round trip.

**Baseline.** The same number of seeded random entries with the same holding period.

**Minimum sample.** 200 trades. Variants: 36.

## M2. Liquidation-cascade reversal (public historical data)

**Mechanism.** Forced liquidations are price-insensitive. Liquidity providers demand compensation, so prices
overshoot and partly revert (Brunnermeier & Pedersen 2009, *RFS*, "Market Liquidity and Funding Liquidity").

**Event.** A 5-minute metrics bar where the open-interest change ΔOI/OI ≤ −x, x ∈ {0.5 %, 1 %, 2 %}, and the perp
price change over the same 5 minutes is ≤ −y (long liquidations → go LONG) or ≥ +y (short squeeze → go SHORT),
y ∈ {0.5 %, 1 %}.

**Entry and exit.** Entry at the 1-minute open at least 60 s after the metrics timestamp. Exit after
h ∈ {15, 60, 240} min. Non-overlapping.

**Costs.** 0.20 % round trip.

**Baseline.** Same-direction h-minute returns from all development minutes, net of the same costs.

**Minimum sample.** 30 events. Variants: 18.

## M3. Perpetual premium convergence (pricing constraint)

**Mechanism.** No-arbitrage ties the perpetual to the index through funding. Large positive premiums should revert
(He, Manela, Ross & von Wachter, arXiv:2212.06888: deviations "diminish over time").

**Trade.** When the 1-minute premium index close p ≥ θ, θ ∈ {0.05 %, 0.10 %, 0.20 %}: short the perp and buy spot,
equal notional, at the next 1-minute opens.
- Exit when p ≤ 0 or after H ∈ {60, 480} min.
- Positive premiums only, because a negative premium would need a spot short (borrowing). No leverage.

**P&L per $ of one leg.** (spot return − perp return) − 0.34 %, where 0.34 % = perp 2 × 0.05 + spot 2 × 0.10 +
4 × 0.01. Funding received by the short is ignored (conservative).

**Baseline.** 0 (market-neutral).

**Minimum sample.** 30 trades. Variants: 6.

## Multiple testing

60 variants in all. Every one is reported. Development results are exploration only.
