# pmcal_v1 results: prediction-market calibration on Polymarket (16.10.2026)

## Verdict: **FAIL**

Under PMCAL_SPEC §7, the frozen configuration's validation mean was ≤ 0 (−3.43 % per event). The holdout was opened
once for the record and **failed every gate**: D, and G1 through G6.

## Chronology (commits)

| Step | Commit |
|---|---|
| Proposal and feasibility | `22bf3cf` |
| Binding spec | `07dcdd5` |
| Engine and tests, before any data | `140c190` |
| Development and validation run at `140c190`; frozen (F1, n_req none) | `cc24d21` |
| Holdout fetched (refused by code before the freeze) and run once at `cc24d21` | — |

Results:
- Development and validation: `data/research/results/pmcal_v1_dev.json`.
- Holdout: `data/research/results/pmcal_v1.json`, including every event row.

Data hashes:

| File | SHA-256 |
|---|---|
| markets_dev | `356580102e3d58cd…f77e1` |
| markets_val | `b7d184bd13f20ace…962ba7` |
| histories_dev | `7bee8e5b74eccb3c…1574b1` |
| histories_val | `65395001a97a3eb9…eed045` |
| markets_holdout | `6e02513bb70c102c56e8909f08b7186e14e49c2553f2736b575ce241b87b125a` |
| histories_holdout | `005d84ecb5e36f7375842ee25ae207b2a89eec841bc7a6660239f8b78a297eda` |

The full development and validation hashes are in `PMCAL_FROZEN.md`.

## Development → validation → holdout, frozen config F1

F1 = buy the favourite side (0.80–0.95) 1 day before the scheduled end. Values are net return per $1 per event.

| | Development 2024–25 | Validation 2026-H1 | **Holdout 2026-07-01 → 10-16** |
|---|---|---|---|
| Events | 2,179 | 3,050 | **2,518** (16 weeks) |
| Mean net r | +0.27 % | −3.43 % | **−8.68 %** |
| 99.5 % LB (week clusters) | −1.42 % | −5.51 % | **−10.92 %** |
| Win rate / mean price | 88.9 % / 0.875 | 84.8 % / 0.869 | **81.1 % / 0.880** |
| Thirds | +3.3 / +1.5 / +1.0 | −17.7 / −41.0 / −45.8 | **−75.9 / −86.9 / −55.8** |
| Random-side baseline (same events) | – | −4.15 % | **+23.2 %** |
| High-cost scenario | – | – | −9.91 % |

Holdout calibration of the favourite side:

| Bucket | Implied | Observed | n |
|---|---|---|---|
| 0.80–0.85 | 82.2 % | 76.5 % | 778 |
| 0.85–0.90 | 87.3 % | 81.2 % | 664 |
| 0.90–0.95 | 92.6 % | 84.7 % | 1,076 |

In the holdout, favourites were heavily **over**priced.

## Holdout gates

| Gate | Result |
|---|---|
| D data check ≥ 90 % | ❌ 79.7 % (14,156 / 17,760) |
| G1 total net > 0 | ❌ −218.6 (per $1 per event, summed) |
| G2 99.5 % LB > 0 | ❌ −10.9 % |
| G3 events ≥ n_req | ❌ n_req none |
| G4 > random side | ❌ −8.7 % vs +23.2 % |
| G5 high costs | ❌ |
| G6 2 of 3 thirds positive | ❌ 0 of 3 |

## Not selected, reported only (holdout)

| Config | Events | Mean net r | Development mean |
|---|---|---|---|
| F7 | 1,502 | −3.8 % | −0.58 % |
| L7 | 1,502 | +12.1 % | −15.96 % |
| L1 | 2,518 | +56.5 % | −23.95 % |

The longshot configurations, which lost heavily on development, won on the holdout. **This is not a finding to act
on.**
- The sign of the bias flipped between periods: longshots were overpriced in 2024–25 and underpriced in
  Jul–Oct 2026.
- L1's holdout mean comes from about 19 % winners at about 0.12, a few hundred winning events over 16 weeks.
- Picking it now would be selection after seeing the holdout, which is exactly what the procedure forbids.

What the data says is that tail mispricing on Polymarket is **unstable in sign** across periods. A fixed rule
chosen in advance does not capture that.

Other splits (holdout, F1):
- Crypto-tagged: 37 events, −1.1 %.
- Other: 2,481 events, −8.8 %.
- Volume ≥ $1k sensitivity: 7,150 events, −4.9 %.

## Limitations

- **Entry prices are daily history points plus an assumed 0.5-cent half-spread, not executable quotes.** Forward
  paper testing on live books was never reached because the verdict was already FAIL.
- **Data coverage.** Data check D was 94.7 % on development, 73.2 % on validation and 79.7 % on the holdout: many
  2026 markets lack two daily points before entry. The excluded markets could differ from the included ones.
- **Unresolved markets.** Markets whose scheduled end lies in the holdout but that were still unresolved at fetch
  time are not returned by the `closed=true` query, so they are absent rather than counted.
- **Look-ahead in the scheduled end.** `endDate` is today's value and may have been edited. Final-volume filtering
  is also look-ahead (§3.1). Neither can make a negative rule positive, but they limit what the numbers mean.

## Conclusion

The favourite–longshot hypothesis, tested pre-registered on about 7,700 Polymarket events, fails: no tail
configuration chosen in advance survived costs out of sample. This adds a 16th idea to the portfolio, and the third
FAIL in a row from a pre-registered procedure. No strategy in this project has met its pre-registered standard.
