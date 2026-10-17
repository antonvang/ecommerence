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
