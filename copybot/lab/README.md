# Research Lab

A pre-registered, append-only research engine with a Mars mission-control dashboard. It is **paper only**: there is no
live state, no order code and no credential anywhere in `lab/`.

## Start and stop

From `copybot/`:

| What | Command | Stop |
|---|---|---|
| Dashboard | `py -m lab web` (http://127.0.0.1:8770; `--duration S` stops it after S seconds) | Ctrl+C |
| Supervisor (workers, heartbeats, recovery) | `py -m lab supervise` (default worker: hourly scanner; `--no-default --worker lab.supervisor:heartbeat_worker` for a no-op check) | Ctrl+C |
| Status and checks | `py -m lab status`, `health`, `verify`, `gate`, `candidates`, `datasets` | — |

Nothing starts automatically.

## Dashboard

- **Header.** PAPER ONLY badge; link state (LIVE STREAM via server-sent events, POLLING fallback, OFFLINE); hash-chain
  status; S7 gate progress; UTC clock.
- **Planet.** A canvas-rendered, procedurally textured Mars. No external assets, so it works offline.
  - Outer ring: one node per pipeline stage, sized by the real number of experiments in it. Click a node to filter
    the pipeline.
  - Inner tilted orbit: one marker per lab worker, coloured by its real state. It moves only while the worker is
    running or scheduled under a live supervisor.
  - Rotation is slow while the supervisor is alive and almost still in STANDBY.
  - New registry events trigger a pulse.
- **System telemetry.** Supervisor and worker states; scanner freshness; external processes (pm_lp_v1 collector, copy-bot
  paper, funding test), whose freshness is read only from file modification times; disk free.
- **Research telemetry.** Counts per lifecycle state, straight from the registry.
- **Pipeline.**
  - Flow DISCOVERY → HYPOTHESIS → REGISTERED → SCREENING → VALIDATION → PAPER TRADING → PAUSED / REJECTED.
  - Per experiment: market, status, latest event, data freshness, number of recorded results, result or reason, and
    the next permitted transitions with who may perform them.
  - Time remaining is shown only where it is calendar-fixed (pm_lp_v1 milestones from its committed start file).
- **Analytics.**
  - Registry throughput per day.
  - Finished holdouts with their recorded net mean and lower bound, plus their verdict.
  - Documented failure patterns.
  - Paper equity, drawdown, costs and win/loss sequences, all labelled SIMULATED. This stays empty until a strategy is
    actually promoted.
- **Candidates, last scan, risk events, data quality, audit log.**
- **Detail drawer.** Full history and guarded controls. Approvals use the same two-step one-time code as the CLI.
  Controls need the page's per-process token and a same-origin request.

## Honesty rules built into the read models (`lab/mission.py`)

- A worker counts as active only if the supervisor itself beat within the last 30 s. A stale heartbeat row never
  shows as active.
- External processes are reported from file write times only. Their databases are not opened.
- No progress percentage or ETA is shown unless it can be derived from fixed calendar dates.
- Simulated results are always labelled PAPER/SIMULATED. Holdout values are shown exactly as recorded (net).

## S7 automation: prepared, not activated

| Part | State |
|---|---|
| Supervisor: heartbeats with status, hourly `system.alive` records, disk guard (FAIL_CLOSED below 2 GB free), JSON-lines logs in `data/lab/logs/` | Implemented and tested |
| `py -m lab gate [--require]` | Computes the gate from the append-only log: ≥ 7 days of hourly alive records with no gap > 2 h and no FAIL_CLOSED, failed worker, failed startup or low-disk event |
| `lab/automation/s7_install_task.ps1` | Registers a Windows scheduled task for the supervisor, but refuses unless the gate is open. **Not run.** |

To open the gate, the supervisor must run under supervision for 7 clean days, started by hand. Only then may the
installer be run, by the user.

## Mission 6: research fleet

### Start, pause, stop (all manual; nothing autostarts)

```
py -m lab approve-template TEMPLATE --reason ".."    # human; prints a one-time code bound to the committed catalogue
py -m lab confirm-template CODE
py -m lab fleet [--duration S]                       # supervisor + 12 agents; holds data/lab/lab.lock
py -m lab pause  --reason ".." | resume --reason ".." | stop --reason ".."
py -m lab jobs [--status running|queued|failed ...]
py -m lab web                                        # Mars Command Center on http://127.0.0.1:8770
```

Pause, resume and stop are events in the hash-chained log. They survive restarts and are idempotent. The dashboard
buttons call the same functions and need the page token. A paused, resource-held, stopping or FAIL_CLOSED lab claims
no new job. Running jobs finish, or time out and are retried. Stop ends the supervisor after its current pass.

### Agents (`lab/fleet.py`)

| Agent | Role |
|---|---|
| data-1 | downloads Binance USD-M 1h klines and funding from data.binance.vision (public), checks coverage, gaps, duplicates |
| discovery-scanner | S3 live anomaly scanner (hourly) |
| discovery-catalogue | proposes catalogue hypotheses; graveyard deduplication applies |
| strategy-1 | registers DISCOVERED instances of human-approved templates; queues holdouts a human approved |
| backtest-1, backtest-2 | grid positions on the train window |
| cost-1 | net and 2x-cost results, trials ledger (every attempt), variant selection on train |
| adversarial-1 | look-ahead truncation, future poison, one-bar delay, block-shuffled placebo |
| validation-1 | frozen variant on validation (DSR over all trials); sealed holdout only in lifecycle VALIDATION |
| report-1 | result record, lifecycle verdict (SCREEN_PASSED or REJECTED), markdown report |
| paper-1 | simulated execution for PAPER_TRADING experiments only (public REST data, idempotent order ids) |
| risk-1 | RAM/disk resource hold, paper reconciliation (mismatch -> FAIL_CLOSED) |

Heavy steps share two compute slots. An agent waiting for a slot reports `queued`. Each agent writes its role,
status, current job and experiment, start time, heartbeat, task/error/retry counts, last result and next action.

### Job queue (`lab/jobs.py`)

Jobs are persistent and keyed by a deterministic id, so enqueueing twice does nothing.
- **Claiming.** A claim is a lease taken atomically under `BEGIN IMMEDIATE`. Only the lease owner can complete it.
- **Retries.** A failed job retries with exponential backoff (10 s · 2^n, at most 600 s). After `max_attempts` it is dead-lettered.
- **Dependencies.** A job waits until the jobs it depends on finish. If one of them fails, it is cancelled.
- **Long jobs.** The agent extends the lease up to the job timeout. After that the lease expires and the queue retries the job.
- **Restart.** At supervisor start, `recover()` turns leases left by a dead process into retries.

### Protocol v2 (current; `research/PROTOCOL_V2.md`, experiment ids `_p2`)

v2 keeps v1 below and adds:
- a train gate: the selected variant must beat buy-and-hold net Sharpe on train;
- a pre-validation gate on train: exact look-ahead and poison tests, data quality, and placebo p < 0.10;
- batch-level DSR: instances registered in one strategy pass form a batch (`batch.registered` event with a trials
  cutoff); no member validates before every member finished its cost step; the DSR trial set is every trial up to the
  cutoff plus the batch's own trials, so it does not depend on run order;
- validation files are read for the first time inside the validation step; their quality is a validation gate.

`_p1` experiments keep their recorded v1 results.

### Protocol v1 (`_p1` experiments)

| Window | Period | Use |
|---|---|---|
| Train | 2023-01..08 | Selection: best net Sharpe in a fixed two-variant grid. |
| Validation | 2023-09..12 | Gates; all must pass (list below). |
| Holdout | 2024 | Only after a human-approved `SCREEN_PASSED -> VALIDATION`, opened once. |
| Reserved | 2025 onwards | Never read: `data.window` raises. |

Validation gates:
- net mean > 0;
- 90 % one-sided block-bootstrap lower bound > 0;
- net Sharpe above equal-weight buy-and-hold;
- net total > 0 at 2× costs;
- deflated Sharpe probability ≥ 0.95, computed against every trial recorded so far;
- exact look-ahead and poison tests.

Paper trading needs a passed holdout and a human `VALIDATED -> PAPER_TRADING` approval.

Costs per unit of turnover:
- taker fee 0.05 %;
- half-spread 0.02 % (ESTIMATE);
- slippage 0.02 % (ESTIMATE);
- plus settled funding, taken from data.

### Dashboard (Mars Command Center)

- **KPI strip.**
  - Supervisor, active/total agents, queued jobs.
  - Tests running and completed.
  - Tests per minute over 15 min: trials ledger rows plus finished validation runs.
  - Errors and retries.
  - Disk, RAM and last data update.
- **Mars.** Ten pipeline stages around the planet. Agent nodes move to the stage of the job they are running; idle agents wait in the dock. Pulses come from the stage of each `job.*` event on the live stream. Red dots mark rejected experiments, with their reason as a tooltip.
- **Experiments.** Filters by market, strategy, worker, status, stage and time; paginated. Each row opens the full experiment record and the two-step approval controls (the only path to paper).
- **Paper.** Uninterpolated step charts of equity and drawdown, realised and unrealised P&L, orders, fills and rejected orders, and reconciliation.
- **Analysis panels.**
  - Result distribution over all trials.
  - Validation estimates with 95 % CI.
  - Costs against benchmark.
  - Rejected strategies with reasons.
  - Job queue, worker log, risk events and audit trail.
- **Missing values** show "ikke tilgængelig". Real-account profit is always "ikke tilgængelig": no real account, broker or live path exists.

## Mission 7: reliability and PROTOCOL v3

- **Start.** `START_LAB.bat` (double-click, user-started) opens the dashboard and runs the fleet in its window.
- **PROTOCOL v3.** Defined in `research/PROTOCOL_V3.md`, with experiment ids `_p3`.
  - Longer windows: train 2022-01..2023-06, validation 2023-07..2023-12, holdout 2024 with BTC/ETH/SOL excluded.
  - Unchanged gates.
  - New data types: open interest and long/short ratios (Binance metrics), taker flow, DVOL (Deribit) and stablecoin supply (DefiLlama, clipped to the window before storing).
- **Resource holds.** risk-1 always runs, so a hold it sets can be lifted again. Heavy agents claim a job only when free RAM covers the 0.5 GB floor plus the largest measured worker peak; otherwise they report "queued: waiting for RAM".
- **Logs.** Agent logs go to `<db dir>/logs`, so test runs no longer write into the production log.
- **Long/short reporting.** Books report gross exposure, turnover and trades.
- **Dashboard speed.** The approvals and audit endpoints are fast: one catalogue lookup, and incremental chain verification with a 10-minute background full walk.
- **Diagnosis.** See `research/DIAGNOSE_HVORFOR_INTET_BESTAAR.md` for why nothing has passed so far.
