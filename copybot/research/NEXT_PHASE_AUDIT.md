# Next phase: audit (16.10.2026)

Repository: `C:\Users\anton\ecommerence`, branch `claude/why-cant-we-do-this-wh3ohb`. The CopyBot project is the
`copybot/` folder (Python 3.9+ standard library only, no third-party packages). `mt5-bot/` is unrelated.
Working tree was clean at the start of this phase (last commit `74069ae`).

## Current architecture

| Layer | Files | What it does |
|---|---|---|
| Data access | `net.py`, `solana_rpc.py`, `market.py` | HTTP with retry/backoff and disk cache; Solana RPC client with fallback servers and Helius `getTransactionsForAddress`; DexScreener (live prices), GeckoTerminal (minute candles) |
| Parsing | `swaps.py` | Wallet-centric swap detection from balance changes (SOL/USDC quote, exits into other tokens, pool size estimate) |
| Copy strategy | `engine.py`, `backtest.py`, `paper.py` | Shadow book (copy every wallet) + account book (one wallet, fire after N losses); backtest replay and live paper loop |
| Sniper (stopped) | `sniper.py` | Live paper buys at pump.fun graduation, prices from pool vaults |
| Funding carry | `funding.py` | Live paper funding carry on Hyperliquid |
| Storage | `store.py` | SQLite (WAL) per mode: `data/paper.db`, `backtest.db`, `sniper.db`, `funding.db` |
| Reporting | `report.py`, `server.py`, `dashboard.html`, `daily_check.py`, `persistence.py` | Dashboard state, localhost dashboard (8765 paper, 8766+ backtest), daily status, week-1 vs week-2 rank test |
| Automation | Windows Startup `CopyBot paper.vbs`; scheduled task `copybot-daglig-status` (09:00) | Paper process auto-start with single-instance lock; daily status run |

## Verified working (tested this session or earlier with real data)

- Helius `getTransactionsForAddress` (full and signatures mode, pagination, status filter). Key in git-ignored `config.local.json`.
- PublicNode for live polling (limit: `getMultipleAccounts` max ~10 accounts, 403 when rate-limited); SolanaVibeStation as archive fallback (~1 req/s); public Solana RPC (~1 req/s, full history).
- Pool-vault price reads for PumpSwap pools (sniper), graduation detection with 100 % coverage after fixes.
- Hyperliquid public API (meta, funding history, daily candles); funding bookkeeping verified 5/5 against Hyperliquid.
- 37 unit tests (`python -m unittest discover -s tests`) pass.

## Broken, incomplete or weak

- **Research is not reproducible.** All analysis scripts and datasets from 15–16.10 live in `%TEMP%\claude\cbdemo`
  (pickles + ad-hoc scripts), outside the repository and outside version control.
- **Old launch dataset has no trader identity** (`snipe_trades*.pkl`: slot, index, time, side, price, size, fee), so
  wallet-based features (buyer diversity, smart money present, concentration) cannot be computed from it.
- **Old launch dataset counts the migration deposit as a trade** (first record is the pool's liquidity, ~150 SOL),
  and prices are SOL×150 rather than per-trade SOL prices. Reserves are not stored, so executable prices for a
  given size were approximated from the initial pool size.
- **Minute candles (GeckoTerminal) are observed prices, not executable prices.** Several earlier graduation tests
  used them; sub-minute entries cannot be evaluated with them.
- Wallet-centric parsing (`swaps.py`) misses buys paid with tokens other than SOL/USDC (sells are detected).
- DexScreener drops dead tokens, so it cannot be used to find pools of old launches (pool address must come from
  the migration transaction).
- Live copy bot: few trades so far (1 closed); the shadow book is the useful metric.

## Available datasets and limitations

| Dataset | Content | Limitation |
|---|---|---|
| `grad_sigs.pkl` | 23,689 successful migration-account transactions, 02.10–15.10 | Not all are graduations (only ~56 % in a sample had a ≥50 SOL pool) |
| `grads.pkl` | 789 sampled migration txs, 443 real graduations (mint, pool, SOL, time) | Random sample; no vault addresses |
| `snipe_trades*.pkl` | First 6 min of trades for 439 pools (~290k trades) | No trader, no reserves, migration counted as trade |
| `pool_buyers.pkl`, `cand_swaps.pkl` | Buyers in 90 pools; 14-day swaps of 139 candidate wallets | Small; wallet swaps lack exact prices for token-to-token exits |
| `funding.pkl`, `listings.pkl` | Hyperliquid funding (40 perps, 25 weeks), daily candles (202 perps) | 32 delisted perps lack candles (survivorship) |
| `data/backtest.db`, `paper.db`, `sniper.db`, `funding.db` | Backtest/paper/live-paper results | Sniper data split into a buggy period (`fejlperiode_sniper.db`) and a clean period |

## Research conclusions to preserve (see `FORSKNING.md`)

1. Copying leaderboard wallets loses after costs, even at 0 s delay and zero fees (−6.5 %/trade).
2. Self-discovered traders have persistent own returns (rank corr. +0.43), but copying them 2 s later loses (−7.1 %/trade).
3. Simple SOL trend rules lose to trading costs.
4. Buying every graduation and holding ≥15 min loses heavily (median −75 % to −95 %).
5. A 60-second sniper rule that looked positive on 160 pools failed on 279 unseen pools and failed live (−10 to −15 %/trade, 149 trades/rule).
6. Shorting new Hyperliquid listings: median win, but rare doublings make the mean negative.
7. Unleveraged funding carry: +8.4–8.6 %/yr historically, live paper test running until 01.11; leverage makes it worse.

None of these rule out that a **subset** of launches, selected by information observable at decision time, has a
positive expectancy. That is the open question for this phase.

## Highest-value next implementation step

A **reproducible, versioned launch-event dataset** with trader identity and exact pool reserves per transaction,
plus an **executable-price simulator** that buys/sells against those reserves (x·y=k, fees, tip, delay) at the
state just before the intended time. Without it, no wallet- or flow-based hypothesis about launches can be tested
honestly. Then: a small set of pre-registered hypotheses with a chronological train / validation / untouched test
split.

Design decisions:
- Code in `copybot/research/` (versioned); data in `copybot/data/research/` (git-ignored, rebuildable).
- Pool-centric parsing: a trade's direction and size come from the change in the pool's own two vaults, which is
  robust to routers and aggregators; the trader is the transaction's fee payer.
- Entry and exit prices come from the pool state immediately before the decision time (`getTransactionsForAddress`
  descending with `blockTime < t`, limit 1), not from candles. Same-slot competition is not modelled and is
  reported as an uncertainty; delay sensitivity is reported instead.

## Status after this phase (16.10.2026 evening)

- Built and tested: launch dataset (2 × 600 graduations, 1.43 M pool trades with trader and reserves, 4,800 exit
  snapshots), executable-price simulator, decision-time features, forward-in-time wallet scores, experiment
  runners v1 and v2, dashboard research card, 50 unit tests.
- launch_v1 (H1–H3, flow at 60–120 s): all REJECTED at validation.
- smart_v2 (H4–H6, early buyers' track records): all REJECTED; none positive even on train; holdout negative.
- No candidate is HISTORICALLY PROMISING, OUT-OF-SAMPLE VALIDATED or LIVE-PAPER VALIDATED.

Next blocker: the dataset only covers the first 3 minutes of each pool, so wallet skill is measured only on
early entries. Testing "smart money that holds for hours" would need each wallet's later sells (full pool
histories, ~10× the data). Before spending that, a specific hypothesis with a reason to expect a different
result is needed; the evidence so far (copying, flow, wallet history, timing) consistently points to no
exploitable edge for a late entrant in pump.fun launches.

## Status after the arbitrage phase (16.10.2026 evening)

- arb_v1 (SOL/USDC, Raydium AMM v4 ↔ PumpSwap, the only verifiable constant-product pair): 0 opportunities above the
  fee band in 13,049 slots and 58,339 transaction-level states; REJECTED.
- Further arbitrage research would need per-slot reconstruction of concentrated-liquidity pool state (Whirlpool
  ticks, CLMM ticks, DLMM bins) from program account data or decoded swap events, verified against real swaps the
  same way. That is a substantial data project; there is no evidence yet that it would find gaps a late entrant can
  take, since professional searchers arbitrage these pools within the slot.
