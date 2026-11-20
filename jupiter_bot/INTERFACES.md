# Interfaces between collector, research, dashboard and execution

Single source of truth for paths and JSON shapes. Every component except the
collector itself only READS what another component writes.

## Paths (defaults; each CLI takes an override)

| What | Path | Writer | Readers |
|---|---|---|---|
| Observation journal | `~/.local/share/jupiter-bot/observations.db` | collector (`jupiter-collect.timer`) | everything, read-only |
| Journal backups | `~/.local/share/jupiter-bot/backups/observations-YYYY-MM-DD.db` | `ops backup` | dashboard |
| Health state | `~/.local/share/jupiter-bot/health-state.json` | `ops health` | dashboard |
| Research output | `~/.local/share/jupiter-bot/research/` | `research.replay`, plan lock | dashboard |
| Forward paper view | `~/.local/share/jupiter-bot/research/forward/<strategy>-<grid_index>.json` | `research.forward` (timer, after lock) | dashboard |
| Verdicts (write-once) | `~/.local/share/jupiter-bot/research/verdicts/<label>-<batch>-<grid_index>.json` | `research.verdict` | execution gate, dashboard |
| Execution mandate | `~/.config/jupiter-bot/mandate.json` | **Anton, by hand** | execution, dashboard |
| Execution ledger | `~/.local/share/jupiter-bot/execution.db` | execution | dashboard |

Times are Unix seconds (float, UTC). Amounts are integer atoms
(USDC 6 decimals, SOL 9 decimals) unless a field name ends in `_usdc_dec`.

## research/plan_lock.json

Written once by `python3 -m jupiter_bot.research.lock` after Anton approves
`jupiter_bot/research/P2_PLAN.md`. Absent = plan is a draft.

```json
{"plan_path": "jupiter_bot/research/P2_PLAN.md", "plan_sha256": "...",
 "code_sha256": {"jupiter_bot/research/strategies.py": "...", "jupiter_bot/research/replay.py": "..."},
 "git_commit": "...", "locked_at": 1795200000.0, "approved_by": "Anton",
 "development": {"start": 0.0, "end": 0.0}, "holdout": {"start": 0.0, "end": 0.0}}
```

## research/evaluations/<run_id>.json (one file per replay run, never rewritten)

```json
{"run_id": "20261211T120000Z-<8 hex>", "created_at": 0.0, "kind": "replay",
 "label": "development" | "holdout" | "synthetic",
 "plan_sha256": "..." | null, "code_sha256": {"...": "..."}, "journal_sha256": "...",
 "period": {"start": 0.0, "end": 0.0},
 "strategy": "name", "params": {}, "delay_s": 60, "extra_cost_bps": 0,
 "trades": [{"decided_at": 0.0, "target_at": 0.0, "filled_at": 0.0, "side": "BUY"|"SELL",
             "quote_id": "...", "in_amount": 0, "out_amount": 0, "status": "FILLED"|"MISSING_QUOTE"}],
 "equity": [[0.0, 0.0]],
 "metrics": {"final_usdc_dec": "0", "return_pct": "0", "max_drawdown_pct": "0",
             "trades": 0, "missing": 0, "exposure_pct": "0"},
 "benchmarks": {"hold_sol_return_pct": "0", "cash_return_pct": "0"},
 "controls": {"random_entries": {"runs": 0, "return_pct_p50": "0", "return_pct_p95": "0",
                                 "share_beating_strategy": "0"},
              "shuffled_signals": {"runs": 0, "return_pct_p50": "0", "share_beating_strategy": "0"}},
 "assumptions": ["..."], "missing": ["..."], "verdict": null}
```

`equity` values are total value in USDC (decimal float is acceptable here;
it is for plotting). `verdict` is always null: evaluation files are never
rewritten. The exact field list is in `research/replay.py` (`_cell_record`).

## research/verdicts/*.json (write-once, `python3 -m jupiter_bot.research.verdict`)

```json
{"label": "development" | "holdout", "verdict": "PASS_DEV" | "PASS" | "FAIL" | "INCONCLUSIVE" | "INCONCLUSIVE_DATA",
 "strategy": "tsmom", "params": {}, "plan_sha256": "...", "batch_id": "...", "grid_index": 0,
 "evaluation_run_ids": ["..."], "created_at": 0.0, "checks": [{"check": "...", "ok": true, "value": "..."}],
 "trades": 0}
```

## research/forward/*.json

A replay record (label `forward`, 120 s, 25 bps, no controls) for each locked
grid entry, replaced every run, plus `grid_index`, `updated_at` and
`now_target` (`LONG`, `FLAT` or `WAIT (...)`). A view for the dashboard, never
an evaluation.

## execution/status (dashboard reads via `python3 -m jupiter_bot.execution status --json`
or directly from execution.db + mandate.json)

```json
{"armed": false, "mode": "DISARMED" | "DRY_RUN" | "LIVE",
 "mandate": null | {"wallet_pubkey": "...", "max_position_usdc": 0, "max_trade_usdc": 0,
                    "daily_loss_limit_usdc": 0, "allowed_mints": ["..."], "expires_at": 0.0},
 "gates": [{"name": "p2_holdout_pass", "ok": false, "detail": "..."}],
 "orders": {"total": 0, "pending": 0, "confirmed": 0, "failed": 0, "unknown": 0},
 "today_realized_pnl_usdc": 0}
```
