# Mission 4: autonomous trading research engine — technical proposal (17.10.2026)

Status: **proposal only.** No structural change has been made. Verified against the repository at `b2fa447` and the
running processes on 17.10.2026. The design keeps three non-negotiables:
- no real orders and no leverage;
- pm_lp_v1 is untouched;
- no automatic promotion past any gate.

---

## 1. Current architecture (verified)

### 1.1 Processes running now

| PID | Process | Started | Must not be touched |
|---|---|---|---|
| 11588 → 29500 | `py -u copybot.py paper` (paper copy bot, autostart via Startup `.vbs`) | 16.10 20:24 | ✔ |
| 33740 → 29004 | `py -u -m research.pm_lp collect --approved` (pm_lp_v1 collector) | 16.10 22:02 UTC | ✔ (study) |
| 19436 | `keepawake.ps1` (holds the PC awake while the collector lives) | 16.10 22:02 UTC | ✔ |

### 1.2 Code (Python 3.14, standard library only, about 7,500 lines incl. tests; 102 tests pass)

| Area | Files | What is reusable |
|---|---|---|
| Storage | `store.py` | `Store`: SQLite in WAL mode, a kv table, thread-safe connection. **Reuse as is.** |
| Paper bot | `paper.py`, `engine.py`, `market.py`, `swaps.py`, `solana_rpc.py`, `net.py` | `single_instance()` lock (msvcrt/fcntl); heartbeat in kv; the engine's "fire after N losses" streak logic (`engine.py` l. 289–291); `net.py` retry. |
| Live paper side tests | `funding.py`, `sniper.py` | Own SQLite files (`funding.db`, `sniper.db`), background threads, x·y = k buy/sell, Hyperliquid info client |
| Dashboard | `server.py`, `report.py`, `dashboard.html` | `ThreadingHTTPServer` on 127.0.0.1 with port fallback and `/api/state` (JSON); a 512-line single-page HTML polling every 3 s; `report.research_state()` already lists experiments and verdicts from `data/research/results/*.json` |
| Research | `research/{launch_data, simulate, experiment(_v2), arb, carry, tsmom, pmcal, pm_lp, prelim, m3, …}.py` | Per-experiment fetch → cache (SHA-256 manifests in carry, tsmom, pmcal) → dev → freeze → holdout. Holdout seals: `frozen()` / `frozen_committed()` / `committed_values()` (git-tracked + clean). Fetch-before-freeze refusal (pmcal, pm_lp). Statistics: `block_lb`, `cluster_lb`, `day_lb`, `n_req`, `psr`. The `Maker` simulator in `pm_lp.py`, with a trade-through fill rule, inventory limits and resolution. |
| Records | `research/*.md` (26 files) | 4 binding spec files + `HYPOTHESES.md` (launch, smart, arb), 3 frozen files, 6 RESULTS files, proposals, prelim/mission reports, `STRATEGIC_CANDIDATES.json` (machine-readable register for one review) |
| Monitoring | `daily_check.py` + scheduled task `copybot-daglig-status` (09:00) | A daily read of the paper, funding and sniper databases |

### 1.3 Weaknesses the engine must fix

1. **No single registry.** Verdicts live in markdown, results JSON and dashboard heuristics: `report.py` infers FAIL
   from gate-name prefixes.
2. **Seals are re-implemented per module**, with three different `n_req` z-values and three bootstrap variants.
3. **No program-level multiple-testing ledger.** 22 ideas and ~150 variants have been tested so far, and α has been
   set by hand each time.
4. **Data provenance is local and partial.** `data/` is git-ignored, the SQLite datasets have no manifests, and some
   APIs are mutable (Polymarket `endDate`).
5. **No lifecycle state.** Nothing stops a script from running a holdout twice, apart from a convention plus
   `frozen()`.
6. **Paper strategies share nothing.** Each live test (paper, funding, sniper) has its own database, ledger and
   dashboard card logic.

---

## 2. Proposed modules and data flow

A new package, **`copybot/lab/`**, standard library only, which **does not import or modify** the running bot or
pm_lp. Existing research modules are wrapped, not rewritten.

```text
            ┌─────────────┐  candidates   ┌──────────────┐  register (before data)  ┌──────────────┐
 public ──▶ │  scanner    │──────────────▶│  registry    │◀────────────────────────▶│  human (CLI/ │
 data APIs  │ (templates) │               │ (lab.db,     │   approvals, freezes     │  dashboard)  │
            └─────────────┘               │  append-only)│                          └──────────────┘
                   │ dedupe vs graveyard  └──────┬───────┘
                   ▼                             │ allowed windows
            ┌─────────────┐   data requests ┌────┴─────────┐   runs, results   ┌──────────────┐
            │ data gateway│◀────────────────│ screen/test  │──────────────────▶│  registry    │
            │ (seal +     │────────────────▶│ engine       │                   └──────────────┘
            │  manifest)  │   cached data   └──────────────┘
            └─────────────┘                        │ only for PAPER_TRADING strategies
                   ▲ live data                     ▼
                   │                        ┌──────────────┐  fills/positions  ┌──────────────┐
                   └────────────────────────│ paper engine │──────────────────▶│ risk monitor │─▶ PAUSE / FAIL-CLOSED
                                            └──────────────┘                   └──────────────┘
                         supervisor: single instance, workers, heartbeats, recovery
                         web: read-only API + dashboard (separate port), guarded control endpoints
```

| Module | Responsibility | Reuses |
|---|---|---|
| `lab/registry.py` | Experiments, versions, transitions, datasets, runs, results, α-ledger, candidates, events. Append-only, hash-chained. | `Store` |
| `lab/lifecycle.py` | State machine (§4); every transition guarded and logged | — |
| `lab/data.py` | **Data gateway.** Every read names (experiment, split). Refuses reserved windows until a FROZEN event exists. Content-addressed cache + manifest per fetch. | carry/tsmom/pmcal fetch + SHA-256 code; `net.py` |
| `lab/stats.py` | One implementation of the bootstrap LBs (block, cluster, day), n_req, PSR/DSR, drawdown, turnover, capacity proxy, cost sensitivity | Ported from research modules, with the old tests |
| `lab/screens/` | Screen templates: a function + a fixed grid + cost model + gates. Wrappers expose existing experiments as legacy, read-only. | m3, prelim, pmcal |
| `lab/scanner.py` | Runs **detectors** (§3.1). Emits candidates with fingerprint, source, timestamp, mechanism tag and reason. Never evaluates profit. | pm_rewards_snapshot, pm_feasibility |
| `lab/paper/` | Per-strategy isolated ledgers; fee, spread and slippage models; maker fills (trade-through), taker fills (walk the book), markouts | `pm_lp.Maker`, `sniper.buy/sell`, `simulate.py` |
| `lab/risk.py` | Circuit breakers (§5), global fail-closed | Idea of `engine.py`'s streak |
| `lab/supervisor.py` | Single instance; worker threads; heartbeats; restart with backoff; recovery (§8) | `paper.single_instance` |
| `lab/web.py` + `lab/dashboard.html` | Read-only JSON API + UI on its own port (default 8770). Control endpoints go through `lifecycle.py`. | `server.py` pattern, `dashboard.html` style |
| `lab/cli.py` | `python -m lab register / approve / freeze / status / import-legacy / verify` | — |

---

## 3. Scanner, registry and deduplication

### 3.1 Detectors (explainable templates, not anomaly hunting)

| Detector | Trigger (stored with source and timestamp) | Example candidate |
|---|---|---|
| `venue_subsidy` | New or changed incentive programmes, e.g. Polymarket reward configs (`/rewards/markets/current`) or maker rebates | "Reward pool > $X/day in a market class with < Y competing score" |
| `pricing_constraint` | A structural identity is violated at the best levels after fees: negRisk sums, YES + NO ≠ 1, spot vs perp beyond the funding bound | Logged as an observation only. Repeated observations above threshold → candidate. |
| `new_data` | A new dataset or instrument becomes available (e.g. a new Binance archive, a new Hyperliquid listing) | "Data now exists for an untested registered mechanism" |
| `literature` | Manual entry of a paper (DOI) with its mechanism | Human-only |

**A detector output is never a trade signal.** It creates a `DISCOVERED` candidate with a fingerprint:

`fingerprint = sha256(mechanism_tag, instrument_family, horizon_bucket, execution_style)`

**Deduplication and graveyard.**
- A candidate whose fingerprint, or whose mechanism tag plus execution style, matches a `REJECTED` experiment is
  stored as `SUPPRESSED`, with a pointer to the rejection.
- It can only be revived by a human, with a written "materially different because …" justification that is logged.
- The 22 historical ideas are imported as rejected fingerprints, so "taker on liquid crypto at minute horizon" is
  suppressed from day one: the cost wall, `MISSION3_FAST_SCREEN.md`.

### 3.2 Registration before data

`REGISTERED` requires a complete record. The registry refuses missing fields:
- hypothesis and mechanism, with source links;
- datasets, with provenance and the declared windows: dev, validation, reserved holdout, forward;
- methodology and fixed grid;
- baseline;
- cost and execution model, with version;
- acceptance and rejection criteria, as machine-readable gates;
- α allocation from the ledger;
- code hash (git blob SHA of the screen module) and the commit.

The record is serialised to `research/registry/<exp_id>/SPEC.json` (+ `.md`) and **committed before** the gateway
releases any evaluation window. This is the same rule as today, enforced by code.

**Templates.** A human approves a template once: mechanism family, grid, costs and gates. Instances of an approved
template, e.g. "the same screen on a new instrument", can then auto-register: code hash, windows and α are recorded
automatically before data access. Anything outside an approved template needs a human.

### 3.3 Immutability

- Append-only tables use SQLite triggers (`BEFORE UPDATE/DELETE … RAISE(ABORT)`).
- Every row carries `prev_hash` and `hash = sha256(prev_hash ‖ canonical_json(row))`.
- `python -m lab verify` re-walks the chain and checks every SPEC/FROZEN/RESULT file hash against git.
- **A result can only be superseded by a new version with a reason. The old row stays and remains visible.**

---

## 4. Lifecycle state machine

```text
DISCOVERED ──(human or approved template)──▶ REGISTERED ──(spec committed)──▶ SCREENING
     │                                          │                             │
     └──▶ SUPPRESSED (duplicate of rejected)    └──▶ WITHDRAWN (before data)  ├─ gates fail ─▶ REJECTED (final)
                                                                               └─ gates pass ─▶ SCREEN_PASSED
SCREEN_PASSED ──(human approves + FROZEN params committed)──▶ VALIDATION (holdout opened once)
VALIDATION ── fail ─▶ REJECTED (final) │ pass ─▶ VALIDATED ──(human approves)──▶ PAPER_TRADING
PAPER_TRADING ── breaker ─▶ PAUSED ──(revalidation criteria met + human)──▶ PAPER_TRADING
PAPER_TRADING ── formal criteria fail ─▶ REJECTED (final) │ planned end ─▶ RETIRED (final, with result)
PAUSED ── formal criteria fail / human ─▶ REJECTED
```

| Rule | Detail |
|---|---|
| Automatic transitions | Only **downward or sideways**: SCREENING→REJECTED, SCREENING→SCREEN_PASSED, VALIDATION→REJECTED/VALIDATED, PAPER_TRADING→PAUSED, any→FAIL_CLOSED (global). |
| Human-only transitions | Every promotion: →VALIDATION, →PAPER_TRADING, PAUSED→PAPER_TRADING, SUPPRESSED→DISCOVERED. Each needs an `approval` event with actor, reason and a time-limited confirmation code issued by the CLI or dashboard. |
| Forbidden | There is **no LIVE state** in the code. Paper strategies have no credential field. The paper engine has no network write path. A test asserts that no module imports an order-signing or exchange-order API. |
| Final states | REJECTED, RETIRED and WITHDRAWN cannot be left. A revived idea is a **new** experiment linked to the old one. |
| Logging | Every transition is an append-only event: ts, from, to, actor, reason, evidence hash. |

pm_lp_v1 is imported as **`EXTERNAL`**: a read-only mirror of its own files. The lab never writes to its database,
its files or its process.

---

## 5. Risk and pause logic

Configured per strategy in its SPEC. Values are fixed at registration and changing them creates a new version.

| Breaker | Default | Effect | Kind |
|---|---|---|---|
| Consecutive simulated losses | 2 | Warning + **temporary pause** of new entries | Circuit breaker, **not** a rejection: 2 losses are not evidence |
| Drawdown | e.g. 10 % of strategy paper capital | Immediate pause | Circuit breaker |
| Data stale / missing / inconsistent | Age > 3 × cadence, gap, crossed book, price jump > k·σ | Block new entries for that strategy; open positions are marked as `UNRELIABLE` | Data guard |
| Abnormal execution assumption | Spread > 3 × the registered model, or fill rate outside the expected band | Flag for investigation; pause after N occurrences | Model guard |
| Exposure mismatch | Ledger position ≠ position recomputed from the fill log | **Global FAIL_CLOSED**: all strategies stop entering until a human clears it | Integrity |
| Heartbeat stale | Worker heartbeat > 3 × interval | Alert; supervisor restarts; strategy paused until its first fresh tick | Liveness |

- **Formal rejection** happens only through the registered acceptance or rejection criteria (e.g. "after n_req paper
  trades the LB ≤ 0"). The pause reason and the original rules are stored separately. Gates are never edited.
- **Resumption** requires the revalidation criteria declared at registration, e.g. "data guard green for 24 h, model
  guard reset by a human, and a fresh forward window of N signals evaluated under the original rules". **Never** "a
  trade would have been profitable meanwhile". Counterfactual P&L during a pause is recorded for transparency and
  explicitly excluded from any resume decision.

---

## 6. Database and event schema (`data/lab/lab.db`, WAL)

```sql
-- append-only (UPDATE/DELETE blocked by triggers); every row: prev_hash, hash
CREATE TABLE events(id INTEGER PRIMARY KEY, ts INTEGER, kind TEXT, actor TEXT, exp_id TEXT, payload TEXT,
                    prev_hash TEXT, hash TEXT);
CREATE TABLE experiments(exp_id TEXT, version INTEGER, template TEXT, fingerprint TEXT, mechanism_tag TEXT,
                         spec_json TEXT, spec_path TEXT, spec_commit TEXT, code_hash TEXT, alpha REAL,
                         created_ts INTEGER, prev_hash TEXT, hash TEXT, PRIMARY KEY(exp_id, version));
CREATE TABLE transitions(id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, from_state TEXT, to_state TEXT,
                         actor TEXT, reason TEXT, evidence_hash TEXT, prev_hash TEXT, hash TEXT);
CREATE TABLE datasets(ds_id TEXT PRIMARY KEY, source_url TEXT, fetched_ts INTEGER, window_start INTEGER,
                      window_end INTEGER, sha256 TEXT, path TEXT, rows INTEGER, quality TEXT);  -- insert-only
CREATE TABLE runs(run_id TEXT PRIMARY KEY, exp_id TEXT, version INTEGER, split TEXT, started_ts INTEGER,
                  ended_ts INTEGER, git_commit TEXT, code_hash TEXT, datasets TEXT, status TEXT);
CREATE TABLE results(run_id TEXT, variant TEXT, metrics TEXT, gates TEXT, label TEXT,  -- EXPLORATORY|VALIDATION|PAPER
                     prev_hash TEXT, hash TEXT, PRIMARY KEY(run_id, variant));
CREATE TABLE alpha_ledger(id INTEGER PRIMARY KEY, exp_id TEXT, alpha REAL, ts INTEGER, prev_hash TEXT, hash TEXT);
CREATE TABLE candidates(cand_id TEXT PRIMARY KEY, ts INTEGER, detector TEXT, fingerprint TEXT, source TEXT,
                        observation TEXT, reason TEXT, status TEXT);  -- status changes are events
-- mutable operational state (derived; rebuildable from events + fills)
CREATE TABLE state(exp_id TEXT PRIMARY KEY, lifecycle TEXT, since_ts INTEGER, pause_reason TEXT);
CREATE TABLE heartbeats(worker TEXT PRIMARY KEY, ts INTEGER, pid INTEGER, detail TEXT);
-- paper engine (per strategy, isolated by exp_id)
CREATE TABLE sim_orders(order_id TEXT PRIMARY KEY,  -- deterministic: exp_id|signal_ts|seq (idempotent)
                        exp_id TEXT, ts INTEGER, side TEXT, instrument TEXT, qty REAL, limit_px REAL, style TEXT,
                        status TEXT);
CREATE TABLE sim_fills(fill_id TEXT PRIMARY KEY, order_id TEXT, ts INTEGER, px REAL, qty REAL, fee REAL,
                       slippage REAL, book_snapshot_ref TEXT);  -- insert-only
CREATE TABLE sim_equity(exp_id TEXT, ts INTEGER, equity REAL, cash REAL, exposure REAL, PRIMARY KEY(exp_id, ts));
CREATE TABLE risk_events(id INTEGER PRIMARY KEY, exp_id TEXT, ts INTEGER, rule TEXT, value REAL, threshold REAL,
                         action TEXT, cleared_ts INTEGER, cleared_by TEXT);
```

**Event kinds:** `candidate.discovered | candidate.suppressed | exp.registered | exp.spec_committed | data.fetched |
data.refused | run.started | run.finished | gate.evaluated | lifecycle.transition | approval.granted |
freeze.committed | holdout.opened | paper.signal | paper.order | paper.fill | risk.breach | risk.cleared |
system.fail_closed | worker.heartbeat_stale | worker.restarted`.

---

## 7. Dashboard layout (`lab/dashboard.html`, port 8770, light/dark, phone-responsive)

| Section | Content (from stored data only) |
|---|---|
| Top bar | System health (workers, last heartbeat age, FAIL_CLOSED banner), disk, chain-verify status, **"PAPER ONLY — no real orders"** |
| Pipeline | Columns per lifecycle state with counts. Each card shows mechanism, label (**EXPLORATORY / VALIDATED / PAPER / REJECTED / EXTERNAL**), age, next gate. |
| Candidates | DISCOVERED and SUPPRESSED, with detector, source link, timestamp, reason, and the graveyard match |
| Experiment detail | SPEC (hypothesis, windows, costs, gates) with commit links; runs; every variant; gate table; α spent; reproducibility hashes; full transition history |
| Paper trading | Per strategy: net simulated equity curve vs baseline; drawdown; fees, spread and slippage paid; fill counts; markouts; consecutive wins/losses; open exposure. Labelled "simulated". |
| Risk | Breaches with rule, value, threshold, action, cleared-by; current pauses with the revalidation criteria still to meet |
| Data quality | Per source: freshness, gaps, coverage %, guard status |
| Audit log | Append-only events, filterable; hash-chain status |
| Programme | Ideas tested; ideas rejected and why (failure-pattern counts); α ledger |

Controls (approve, pause, clear) call the same lifecycle guards as the CLI and require the confirmation code. There
is no control for resuming a strategy without its criteria, editing gates, or anything live.

---

## 8. Crash recovery

1. **Single instance.** The supervisor takes `data/lab/lab.lock` (the `paper.single_instance` pattern). A second
   start exits.
2. **Durable first.** Every action is written as an event or row inside a transaction before its side effect.
   Simulated orders use deterministic ids, so a replay after a crash cannot duplicate them (primary key conflict =
   already done).
3. **Startup.**
   1. `verify` the hash chain (on failure → FAIL_CLOSED);
   2. rebuild `state` from transitions and positions from fills, and compare with the stored derived state (on a mismatch → FAIL_CLOSED for that strategy);
   3. all PAPER_TRADING strategies start **paused-for-warmup** until fresh data passes the guards. Recovery never changes rules or lifecycle beyond logged breaker actions.
4. **Workers.** Each worker writes a heartbeat. The supervisor restarts a stale worker with exponential backoff and
   logs `worker.restarted`. After K restarts in an hour it marks the worker failed and alerts.
5. **Autostart.** A Windows Startup entry, as for the paper bot, **only with the user's approval**.

## 9. Testing plan

| Level | Tests |
|---|---|
| Unit | State-machine table: every allowed/forbidden transition, including "no path to PAPER_TRADING without approval events". Trigger immutability: UPDATE/DELETE raise. Hash chain. Gateway refuses reserved windows before FROZEN. Each breaker. Stats against known values (port the existing 102 tests). |
| Property | Randomised event sequences never reach a promotion without approval, and never leave a final state |
| Integration | Re-run tsmom_v1 dev and pmcal dev through the lab (data hashes + metrics must match stored results); import legacy experiments and check that verdicts equal the RESULTS files |
| Crash | Kill the supervisor mid-run (fixture), restart, assert no duplicate orders or fills, state equal, strategies paused-for-warmup |
| Safety | A static test that no module contains order-placing endpoints or credential handling; the paper engine has no network write path |
| UI contract | `/api/*` responses come only from DB queries on a fixture DB; snapshot test that labels (EXPLORATORY etc.) are always present |

## 10. Implementation stages (each verified before the next; nothing touches pm_lp or the paper bot)

| Stage | Deliverable | Acceptance |
|---|---|---|
| **S1** | Registry + immutability + lifecycle + CLI; legacy import (22 ideas as rejected fingerprints; pm_lp as EXTERNAL) | Tests pass; `verify` green; imported verdicts equal the RESULTS files |
| S2 | Data gateway + seals + manifests; `stats.py` consolidation | tsmom_v1 and pmcal dev reproduce exactly through the lab |
| S3 | Scanner (2 detectors: venue_subsidy, pricing_constraint) + dedupe/graveyard | Duplicate and graveyard tests; candidates visible in the CLI |
| S4 | Paper engine (isolated ledgers, fee/spread/slippage, maker trade-through, taker book-walk) + risk breakers | Crash and duplicate tests; breaker tests |
| S5 | Supervisor, heartbeats, recovery | Kill-and-restart test on this PC |
| S6 | Dashboard | UI contract tests; reviewed by the user |
| S7 | Scheduled automation (templated screens on new data) | Only after S1–S6 have run cleanly for ≥ 7 days |

Estimated effort for S1–S6: about 6–10 working sessions. This is an estimate; S1 alone is about one session.

## 11. Risks and unresolved questions

**Risks.**
- **The engine makes research faster, not edges likelier.** Across 22 ideas the binding constraint was the economics:
  the cost wall, competition and speed. Automation raises the risk of false discoveries unless the α ledger and the
  graveyard are enforced. Expect the engine mostly to **reject faster**.
- Multiple testing grows with automation: a programme-level α budget is mandatory (proposal: α-investing or fixed
  Bonferroni per template family).
- Paper maker fills cannot be validated without queue data. Paper results for maker strategies stay labelled
  "simulated, fill model unverified".
- Operations: one Windows PC that must stay awake; API rate limits; disk growth (estimate 1–3 GB/month with books);
  Python 3.14 on Windows only.

**Questions for the user.**
1. Should the lab run as its own background process on port 8770 (recommended), or be merged into the paper bot's
   dashboard later?
2. Who approves promotions: you via the CLI, dashboard buttons with a confirmation code, or both?
3. Which detectors first? I recommend `venue_subsidy` (it fits pm_lp's line of evidence) and `pricing_constraint`.
4. Autostart on Windows for the lab: yes or no?
5. Go-ahead for **S1 only** (registry, lifecycle, CLI, legacy import), with nothing else changed?
