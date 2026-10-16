# pmcal_v1: frozen before the holdout is fetched (16.10.2026)

Development and validation were run with `python -m research.pmcal dev` at commit `140c190`. The result is in
`data/research/results/pmcal_v1_dev.json`.

Data hashes (manifest_dev):

| File | SHA-256 |
|---|---|
| markets_dev | `356580102e3d58cd7a36852b54f3d165315cb225691938b43ef4aea8a97f77e1` |
| markets_val | `b7d184bd13f20acec77391e1a5239fad71db0edbc0765674db7d368a89962ba7` |
| histories_dev | `7bee8e5b74eccb3c4b044dc5d73ebb60812601d0a26be1a894ee3671ee1574b1` |
| histories_val | `65395001a97a3eb959743f133983905f6c0d0d00416ac0df9dd83bfcd5eed045` |

## Development (scheduled end 2024-01-01 → 2025-12-31): net r per event

| Config | Events | Mean | 99.5 % LB | Win rate | Mean price |
|---|---|---|---|---|---|
| F7 | 1,628 | −0.58 % | −3.12 % | 88.3 % | 0.878 |
| **F1** | 2,179 | **+0.27 %** | −1.42 % | 88.9 % | 0.875 |
| L7 | 1,628 | −15.96 % | −31.66 % | 11.5 % | 0.122 |
| L1 | 2,179 | −23.95 % | −36.28 % | 11.2 % | 0.125 |

Chosen by the spec rule (highest development mean):

config: F1

## Validation (2026-01-01 → 2026-06-30), F1

| Measure | Value |
|---|---|
| Events | 3,050 |
| Mean net r | **−3.43 %** |
| 99.5 % LB | −5.51 % |
| Thirds | −17.7, −41.0, −45.8 (all negative) |
| Random-side baseline | −4.15 % |

Development + validation mean: −1.89 %, s.d. 38.8 %. The mean is ≤ 0, so:

n_req: none

## Consequence, stated before the holdout is fetched

Under PMCAL_SPEC §7, validation mean ≤ 0 means **FAIL**. The holdout (2026-07-01 → 2026-10-16) is still fetched and
run once, unchanged, for the record; G3 cannot pass with n_req none.

Other observations from development, not gated:
- The 0.05–0.10 longshot bucket resolved YES 4.5–5.7 % of the time against an implied 7.1–7.3 %. That is a
  favourite–longshot pattern, but its mirror image on the favourite side did not cover costs and reversed on
  validation (0.90–0.95: observed 90.1 % vs implied 92.5 %).
- Data check D was 94.7 % on development for F1 but 73.2 % on validation: many 2026 markets lack the required daily
  points. This is reported for the holdout as gate D.
