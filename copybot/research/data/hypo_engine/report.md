# Hypothesis engine P1 — synthetic falsification report

`research/tools/hypo_engine.py`; data `research/data/hypo_engine/report.json` (sha256 `21529582930cea6ec7519c5f02c6a58bf0afc092ce0d76bafcabd55d3f980ab7`). 24 assets x 500 days, 51 candidates per world (mom 24, rev 8, vol 12, char 6, leak 1), alpha 0.05, BH q 0.1, HAC lags 5. Synthetic data only.

| Scenario | Reps | Per-test type I (net) | FWER raw | FWER Holm [95 % CI] | FWER BH | FWER Bonf(N_eff) | FDP Holm | FDP BH | True found (Holm) | Leak caught | Cost-killed gross hits | Profit-PASS with net<=0 | N_eff |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| null_base | 200 | 0.027 | 0.355 | 0.010 [0.003, 0.036] | 0.075 | 0.010 | 1.000 | 1.000 | — | 1.000 | 0 | 0 | 44.2 |
| null_gauss_calm | 200 | 0.021 | 0.280 | 0.015 [0.005, 0.043] | 0.040 | 0.015 | 1.000 | 1.000 | — | 1.000 | 8 | 0 | 44.3 |
| null_fat_regime | 200 | 0.014 | 0.230 | 0.005 [0.001, 0.028] | 0.015 | 0.005 | 1.000 | 1.000 | — | 1.000 | 3 | 0 | 44.1 |
| signal | 200 | 0.036 | 0.375 | 0.010 [0.003, 0.036] | 0.095 | 0.015 | 0.026 | 0.248 | 74 | 1.000 | 1 | 0 | 44.1 |
| signal_cost_killed | 200 | 0.000 | 0.000 | 0.000 [0.000, 0.019] | 0.000 | 0.000 | — | — | 0 | 1.000 | 724 | 0 | 44.0 |
