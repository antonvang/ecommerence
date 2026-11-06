# Factory shadow run P3 (synthetic + read-only pipeline replay)

`research/tools/factory_shadow.py`; data `research/data/factory_shadow/report.json` (sha256 `7a1cdb1bf0848e9c3b292c79e50626c72b309e5a73da36bb2222453cfbdbba82`).

## A. Pipeline shadow: 179 lab transitions replayed

| Factory decision : class | Count |
|---|---|
| ALLOW:- | 36 |
| ALLOW:human-verdict | 1 |
| ALLOW:legacy | 25 |
| ALLOW:no-op | 17 |
| ALLOW:propose | 40 |
| BLOCK:delegated-approval | 9 |
| BLOCK:hash-at-access | 32 |
| BLOCK:instruction-cited-approval | 19 |
| BLOCK:universe-asof-unrecorded | 32 |

Unexplained differences: 0.

## B. Adversarial suite

Unauthorized ALLOW: **0**. False BLOCK: **0**.

| Case | Expected | Got | Reason |
|---|---|---|---|
| approve: system actor | BLOCK | BLOCK | approval needs a human actor (approve-template stays the owner's) |
| approve: claude actor | BLOCK | BLOCK | approval needs a human actor (approve-template stays the owner's) |
| approve: chatgpt actor | BLOCK | BLOCK | approval needs a human actor (approve-template stays the owner's) |
| approve: human label, reason says Claude on behalf | BLOCK | BLOCK | delegated approval: an AI approving on the owner's behalf is not the owner's approval |
| approve: owner in person | ALLOW | ALLOW |  |
| freeze: estimand missing | BLOCK | BLOCK | pre-registration incomplete: ['estimand'] |
| freeze: dataset without sha256 | BLOCK | BLOCK | every dataset needs a sha256 before freezing |
| freeze: 2024 holdout | BLOCK | BLOCK | protected data: ['syn.zip: overlaps the 2024 holdout'] |
| freeze: COIN-M before 2026-11-28 | BLOCK | BLOCK | protected data: ['syn.zip: COIN-M before 2026-11-28'] |
| freeze: COIN-M after 2026-11-28 | ALLOW | ALLOW |  |
| freeze: survivor universe (fixed at window end) | BLOCK | BLOCK | survivorship: the universe must be fixed as of the window start |
| freeze: universe date not recorded | BLOCK | BLOCK | survivorship: the universe must be fixed as of the window start |
| freeze: point-in-time universe | ALLOW | ALLOW |  |
| test: no ledger charge | BLOCK | BLOCK | no ledger charge for this attempt (every attempt counts) |
| test: charge made before the freeze | BLOCK | BLOCK | no ledger charge for this attempt (every attempt counts) |
| test: data changed after lock | BLOCK | BLOCK | data changed after the lock |
| test: pre-registration changed after lock | BLOCK | BLOCK | pre-registration changed after the lock |
| test: legitimate | ALLOW | ALLOW |  |
| identical re-run charges once | ALLOW | ALLOW |  |
| refund alpha | BLOCK | BLOCK | exception: alpha is never refunded |
| retest a REJECTED hypothesis | BLOCK | BLOCK | H is REJECTED (final); a revived idea is a new hypothesis in the same lineage |
| promote to paper trading | BLOCK | BLOCK | the factory never promotes to paper trading |
| broken ledger (fail-closed) | BLOCK | BLOCK | ledger: ledger broken at entry 0 |
| unknown hypothesis id (fail-closed) | BLOCK | BLOCK | nope does not exist |
| refused move leaves the record unchanged (rollback) | ALLOW | ALLOW |  |
| F1 control: INSUFFICIENT_POWER despite synthetic profit | BLOCK | BLOCK | assessment INSUFFICIENT_POWER: not ready for APPROVED |
| F2 control: CONDITIONAL | BLOCK | BLOCK | assessment CONDITIONAL: not ready for APPROVED |
| F3 control: DEFERRED | BLOCK | BLOCK | assessment DEFERRED: not ready for APPROVED |
| F3 date gate alone, before 2026-11-28 | BLOCK | BLOCK | date gate: data not allowed yet |
| F3 date gate alone, after 2026-11-28 | ALLOW | ALLOW |  |

## C. Factory at scale

| World | ic | Candidates | Raw null hits | Holm null hits | Holm true hits (of 6) | Leak caught | Leak false alarms | Test blocked w/o approval | Ledger entries / tested | Max entries per candidate | Alpha charged | EW all vs survivors (bp/day) | N_eff (1 in 25) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 0.0 | 1002 | 42 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | -57.0 vs -47.3 | 20.2 |
| 1 | 0.0 | 1002 | 73 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | 5.2 vs 16.3 | 19.5 |
| 2 | 0.0 | 1002 | 143 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | -36.9 vs -26.6 | 18.2 |
| 3 | 0.0 | 1002 | 0 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | 4.3 vs 13.1 | 19.1 |
| 4 | 0.0 | 1002 | 0 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | -21.3 vs -10.9 | 18.0 |
| 0 | 0.03 | 1002 | 3 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | -26.5 vs -20.6 | 17.2 |
| 1 | 0.03 | 1002 | 154 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | 25.2 vs 37.3 | 18.4 |
| 2 | 0.03 | 1002 | 0 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | -5.9 vs 1.6 | 21.6 |
| 3 | 0.03 | 1002 | 0 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | 50.1 vs 58.8 | 22.1 |
| 4 | 0.03 | 1002 | 0 | 0 | 0 | True | 0 | 1002 | 1002 / 1002 | 1 | 0.0500 | -17.8 vs -10.6 | 19.2 |
