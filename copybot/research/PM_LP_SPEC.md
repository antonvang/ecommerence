# pm_lp_v1: binding specification for an observational study of Polymarket liquidity-provision economics

Written and committed 16.10.2026, approved by the user ("write and commit the binding PM_LP_SPEC.md for pm_lp_v1
(observational, no orders), plus code and tests before any data collection"). The background is
`STRATEGIC_OPPORTUNITY_REVIEW.md` §3 A1. Before this commit only these were examined:
- API capabilities;
- two order-book snapshots of reward markets (`research/pm_rewards_snapshot.py`);
- a handful of trade and reward records, checked for their format.

No study data has been collected. Not edited after commit; changes are dated amendments below, made before the data
they affect is examined.

**No orders are placed. No account, wallet, key or money is used.** The study simulates a hypothetical small
passive maker from public data. A PASS would not authorise trading: real money additionally requires the user's legal
check (Danish law, Polymarket terms) and a separate approval.

## 1. Question and hypothesis

Can a small passive maker quoting 100 shares per side earn positive net income from Polymarket's liquidity-rewards
programme, after the losses from being filled (adverse selection, inventory, resolution)?

H1: the mean net P&L per market-day of the rule in §4 is > 0. The prior expectation is FAIL: rewards are probably
competed away or exceeded by adverse selection.

## 2. Data (public, read-only, collected forward)

All raw API responses that the simulation uses are stored in `data/research/pm_lp/pm_lp.db` (SQLite). A SHA-256 of
each daily export is written to a manifest.

| Data | Source | Cadence |
|---|---|---|
| Reward configuration (`total_daily_rate`, `rewards_max_spread`, `rewards_min_size`) | `GET clob.polymarket.com/rewards/markets/current` | Every 60 min |
| Market status, tokens, resolution (`winner`) | `GET clob.polymarket.com/markets/{condition_id}` | At selection, then every 6 h |
| YES order book (mirrors NO, checked 16.10.2026) | `POST clob.polymarket.com/books` | Target every 60 s |
| Taker trades | `GET data-api.polymarket.com/v2/trades?condition=…&taker_only=true&start=…` | Every 5 min, 120 s overlap, de-duplicated |
| All trades | Same with `taker_only=false` | Every 5 min |
| Reward payouts of observed maker wallets | `GET data-api.polymarket.com/v2/activity?user=…&type=REWARD` | Once per split, after it ends |

- Maker records are the `taker_only=false` records not present in `taker_only=true`. The key is
  (transaction hash, wallet, token, size, side).
- Book snapshots store per market:
  - time, best bid, best ask;
  - the competing scores Q₁ (bids) and Q₂ (asks): the sum over price levels with size ≥ `rewards_min_size` and
    distance from the mid < v, of ((v − s)/v)² × size;
  - the reward configuration in force.
- The full book is kept every 15th minute for audit.

## 3. Panel and calendar

- **D0** = the first full UTC day after the collector starts. It is recorded in `research/PM_LP_START.md`, committed
  when collection starts.
- **Panel: 200 markets.**
  - Eligible at selection:
    - listed in the rewards endpoint with `total_daily_rate` ≥ 5;
    - CLOB market active, not closed, accepting orders, with two tokens;
    - mid in [0.10, 0.90];
    - `end_date_iso` at least 3 days after selection.
  - Selection: sort the eligible `condition_id`s, shuffle them with `random.Random(20261017 + day_index)`, and take
    them in order.
  - At each 00:00 UTC, markets that are closed, no longer accept orders, or have left the rewards list stop quoting.
    They keep any inventory until resolution. They are replaced from that day's eligible set, so 200 markets quote.
- **Periods** (UTC days, market-days assigned by the day they occur):

  | Period | Days |
  |---|---|
  | Development | D0 … D0+6 |
  | Validation | D0+7 … D0+13 |
  | **Holdout** | **D0+14 … D0+27** |
  | Resolution tracking (no quoting) | to D0+41 |

- The `dev` command refuses data after D0+13. The `holdout` command requires a committed, unmodified
  `research/PM_LP_FROZEN.md`.

## 4. Simulated maker (one fixed configuration, no parameters selected on data)

For each panel market and each book snapshot k (valid until snapshot k+1, at most 180 s):

1. **Mid and quotes.**
   - mid = (best bid + best ask)/2 of the YES book. With an empty side: no quote, no reward, no fills.
   - v = `rewards_max_spread`/100, tick = the book's tick size.
   - Bid b = floor_tick(mid − v/2), ask a = ceil_tick(mid + v/2), size Q = 100 shares each.
2. **Inventory limit.** I is the YES inventory (negative = short YES, equivalent to long NO).
   - The bid is active only if I < +500.
   - The ask is active only if I > −500.
3. **Our reward score** (published rule, `docs.polymarket.com/programs/liquidity-rewards`, 16.10.2026):
   - q₁ = S(v, mid − b)·Q if the bid is active; q₂ = S(v, a − mid)·Q if the ask is active; S(v, s) = ((v − s)/v)² for s < v, else 0.
   - q = max(min(q₁, q₂), max(q₁, q₂)/3) if mid ∈ [0.10, 0.90], else min(q₁, q₂).
4. **Competing score:** C = Q₁ + Q₂ from the snapshot. This is an upper bound on the competitors' summed scores,
   because per-maker attribution is unknown, so it is conservative.
5. **Reward for the sample:** `total_daily_rate`/1440 × q/(q + C). The daily reward is the sum over that day's
   snapshots, so missing minutes earn nothing.
6. **Fills (base: trade-through).** Each taker trade in (t_k, t_{k+1}] is converted to YES terms:
   - a NO buy at p is a YES sell at 1 − p;
   - a NO sell at p is a YES buy at 1 − p.

   | Taker trade | Fills our | Condition | Price |
   |---|---|---|---|
   | YES buy at p | Ask | p > a | a |
   | YES sell at p | Bid | p < b | b |

   Fill size is min(trade size, remaining quote size for that side in the interval); the quote size is restored at each snapshot. Inventory limits apply within the interval.
   - Sensitivity "at-or-through": p ≥ a and p ≤ b.
7. **Costs.** Makers pay no fees (published). Maker rebates are **not** counted, which is conservative.

## 5. P&L and unit of observation

- Cash flows: a bid fill pays b·x; an ask fill receives a·x. Mark-to-market value = cash + I × mark.
  - mark = mid of the last snapshot;
  - mark = payout (1, 0 or 0.5 for 50-50) once the market has resolved; inventory is then settled.
- **Unit: market-day.** Net P&L = rewards that day + change in mark-to-market value that day, in USD. It counts every
  day a market quotes or holds inventory.
- Capital per market = Q × (1 − v), the cost of funding both resting orders. Reported only as a yield.
- **Holdout resolution tail.**
  - The value change of holdout inventory between D0+27 and its resolution (by D0+41) is added to the holdout total as a "tail" term.
  - Inventory unresolved at D0+41 is marked at the last mid, and also at the worst case (long → 0, short → 1) for G8.

## 6. Statistics

- **Mean and lower bound:** mean net P&L per market-day. One-sided 99.5 % lower bound by cluster bootstrap over
  markets (10,000 draws, seed 5).
- **Sample size:** `n_req = ceil(((2.5758 + 0.8416) × sd / mean)²)` market-days, from development + validation (none
  if the mean is ≤ 0).
- `PM_LP_FROZEN.md` records n_req and the development/validation summary. It is committed before the `holdout`
  command can run.
- No configuration is selected on data. Development serves data-quality checks and n_req only.

## 7. Gates (holdout, including the tail)

| Gate | Requirement |
|---|---|
| D1 | Mean snapshot coverage ≥ 90 % of 1,440 per quoting market-day, and ≤ 1 % of trade polls failed after retries |
| D2 | ≥ 50 % of maker wallets seen in panel fills during the holdout have ≥ 1 REWARD record in the holdout window (the programme pays) |
| G1 | Total net P&L > 0 |
| G2 | 99.5 % lower bound of mean net P&L per market-day > 0 |
| G3 | Market-days ≥ n_req |
| G4 | Total net > 0 with rewards × 0.5 (uptime, size-adjusted midpoint, sampling) |
| G5 | Total net > 0 with at-or-through fills |
| G6 | Net positive in ≥ 2 of 3 chronological thirds (by day) |
| G7 | Median daily reward per quoting market-day ≥ $1.00 (capacity) |
| G8 | Total net > 0 with unresolved inventory marked at the worst case |

Reported, not gated:
- reward income vs fill P&L (adverse-selection ratio);
- fills per market-day; inventory;
- results by category and by reward-rate tier;
- maker-wallet REWARD totals;
- the alternative competing score max(Q₁, Q₂);
- rebates not counted.

## 8. Verdict

| Verdict | Condition |
|---|---|
| **PASS (observational)** | D1, D2 and G1–G8 all hold |
| **FAIL** | Development + validation mean ≤ 0, or validation mean ≤ 0, or G1 or G2 fails |
| **INSUFFICIENT** | Otherwise |

A PASS means only that a small maker could plausibly earn this. It does not prove our own fills would behave the
same way, which would need real orders and is out of scope.

## 9. Order of work

1. Commit this spec.
2. Commit `research/pm_lp.py` and its tests.
3. **Ask the user before starting the collector process.**
4. Commit `PM_LP_START.md`.
5. After D0+13, run `dev` and commit `PM_LP_FROZEN.md`.
6. After D0+41, run `holdout` once; write `RESULTS_pm_lp_v1.md`.

Commands from `copybot/`: `python -m research.pm_lp collect | dev | holdout`.

## Amendment 1 (16.10.2026, before any data was collected)

Changes, made while implementing:
- **Selection order (§3).** Checking every reward market for eligibility at each midnight would take thousands of
  requests and halt the snapshots. Instead:
  1. All markets with `total_daily_rate` ≥ 5 that were never in the panel are sorted and shuffled with the same seed
     (`random.Random(20261017 + day_index)`).
  2. Each one is checked for the remaining eligibility conditions, in that order, until the panel has 200 markets.

  The selection stays random, deterministic and independent of any outcome.
- **Trades (§2).** The `start` parameter of `v2/trades` is not applied by the server (checked 16.10.2026). Pages are
  read newest-first and cut at the start time on our side.
