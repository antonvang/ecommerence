# Factory S1 shadow report (director order 49)

S1 started 2026-11-06 09:55 UTC; runs 10; last run 2026-11-06 13:29 UTC; chain head `e1da0cd60c4941e2d58ad6f24a921df20887ca441d6e4317ba046fc98c8c726a`.

Baseline: 179 transitions (all that existed at S1 start; not observations).
Observation period (order 49 P3 counts 14 full days from the start): 0 new transitions, 0 unexplained, 0 BLOCK.

Monitoring coverage: 10 successful runs over 4 elapsed hourly slots, 0 failed; longest gap 1.19 h; MONITORING_GAP periods (> 2 h): 0.

Event coverage: few new transitions mean INSUFFICIENT_OBSERVATION at the evaluation, never an automatic PASS.

| Phase | Factory decision : reason | Count |
|---|---|---|
| BASELINE | ALLOW:- | 36 |
| BASELINE | ALLOW:human-verdict | 1 |
| BASELINE | ALLOW:legacy | 25 |
| BASELINE | ALLOW:no-op | 17 |
| BASELINE | ALLOW:propose | 40 |
| BASELINE | BLOCK:delegated-approval | 9 |
| BASELINE | BLOCK:hash-at-access | 32 |
| BASELINE | BLOCK:instruction-cited-approval | 19 |
| BASELINE | BLOCK:universe-asof-unrecorded | 32 |
