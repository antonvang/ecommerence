# pm_lp_v1: collection start

The read-only collector (`python -m research.pm_lp collect --approved`) was started 16.10.2026 22:00 UTC, after the
user's explicit approval (engine `0fc3667`). It stopped after one snapshot round because of a threading bug. It was
fixed in `f2208c2` (Amendment 2, committed 22:02 UTC, not ~22:10 as written there) and restarted 22:02 UTC. The day −1
panel was resumed, not reselected. It places no orders, uses no account and no key, and runs
as its own process. The existing paper process was not touched.

D0: 2026-10-17

| Period | Dates |
|---|---|
| Development | 2026-10-17 → 2026-10-23 |
| Validation | 2026-10-24 → 2026-10-30 |
| Holdout | 2026-10-31 → 2026-11-13 |
| Resolution tracking | to 2026-11-27 |

- Data goes to `data/research/pm_lp/pm_lp.db`. It is git-ignored; a SHA-256 is recorded with each evaluation.
- The machine is held awake by `data/research/pm_lp/keepawake.ps1` while the collector runs. That script calls
  `SetThreadExecutionState` and changes no settings.
- A reboot, shutdown or closed lid stops collection. Gaps count against gate D1.
