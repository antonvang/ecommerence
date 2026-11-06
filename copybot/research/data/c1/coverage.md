# C1 dækningsrapport (census/1, kun optællinger)

Genereret 2026-11-06 13:59:38 UTC af `research/tools/c1_forecast.py coverage`. Kilde: `file:/home/anton/ecommerence/copybot/data/lab/lab.db?mode=ro + PRAGMA query_only=ON`, tabel `observations`, detector `census/1`, metric `snapshot`, felt `markPrice` (og `lastPrice` til sammenligning). Kun rækker fra 2026-10-27. Ingen pris, afkast, RV, modeltilpasning eller tab er beregnet.

## Snapshots (timeslots)

| | |
|---|---|
| første slot | 2026-10-27 15:00:00 |
| sidste slot | 2026-11-06 13:00:00 |
| forventede / tilstede / mangler | 239 / 221 / 18 (92.5 %) |
| dubletter / fejlrækker | 0 / 0 |
| række-ts minus slot (s) | min 0, median 34, max 503 |

Manglende slots:

- 2026-10-30 19:00:00 → 2026-10-31 01:00:00 (7)
- 2026-10-31 04:00:00 → 2026-10-31 06:00:00 (3)
- 2026-10-31 08:00:00 → 2026-10-31 10:00:00 (3)
- 2026-10-31 13:00:00 → 2026-10-31 14:00:00 (2)
- 2026-10-31 18:00:00 → 2026-10-31 19:00:00 (2)
- 2026-10-31 22:00:00 → 2026-10-31 22:00:00 (1)

## Hele UTC-døgn (24/24 marks)

- fulde døgn siden start: 9 (2026-10-28 .. 2026-11-05)
- komplette døgn: 7: 2026-10-28, 2026-10-29, 2026-11-01, 2026-11-02, 2026-11-03, 2026-11-04, 2026-11-05
- ufuldstændige døgn: 2026-10-30, 2026-10-31
- i dag (2026-11-06) indtil nu komplet: True
- nuværende sammenhængende løb: 5 døgn fra 2026-11-01

## Pr. symbol

### markPrice

- symboler: 941 (heraf 6 først set efter start)
- slotdækning: min 0.908, median 0.925, max 0.925; 100 %: 0 symboler
- komplette døgn pr. symbol: min 5, median 7, max 7
- nuværende løb (døgn): min 5, median 5, max 5
- symboler med flere manglende slots end snapshot-hullerne: 0
- løbsstart pr. dato (antal symboler): 2026-11-01: 941

- **BTCUSDT**: 221/239 slots (92.5 %), komplette døgn 7, løb 5 fra 2026-11-01; HAR første måldøgn 2027-12-01, EWMA første måldøgn 2026-12-21
- **ETHUSDT**: 221/239 slots (92.5 %), komplette døgn 7, løb 5 fra 2026-11-01; HAR første måldøgn 2027-12-01, EWMA første måldøgn 2026-12-21

### lastPrice

- symboler: 801 (heraf 6 først set efter start)
- slotdækning: min 0.176, median 0.921, max 0.921; 100 %: 0 symboler
- komplette døgn pr. symbol: min 1, median 7, max 7
- nuværende løb (døgn): min 0, median 5, max 5
- symboler med flere manglende slots end snapshot-hullerne: 801
- løbsstart pr. dato (antal symboler): 2026-11-01: 800, 2026-11-07: 1

- **BTCUSDT**: 220/239 slots (92.1 %), komplette døgn 7, løb 5 fra 2026-11-01; HAR første måldøgn 2027-12-01, EWMA første måldøgn 2026-12-21
- **ETHUSDT**: 220/239 slots (92.1 %), komplette døgn 7, løb 5 fra 2026-11-01; HAR første måldøgn 2027-12-01, EWMA første måldøgn 2026-12-21

## Første gyldige prognose (hvis indsamlingen fortsætter uden huller)

| model | komplette døgn krævet | inputdøgn | første måldøgn | oprettes | første afsløring |
|---|---|---|---|---|---|
| HAR-RV(1,7,30), 365 rækker | 395 | 2026-11-01 .. 2027-11-30 | **2027-12-01** | after the 23:00 mark of 2027-11-30, before 2027-12-01 00:00 | 2027-12-02 01:00:00 |
| EWMA 0,94, indkøring 50 | 50 | 2026-11-01 .. 2026-12-20 | **2026-12-21** | after the 23:00 mark of 2026-12-20, before 2026-12-21 00:00 | 2026-12-22 01:00:00 |

Ethvert nyt manglende timeslot genstarter løbet: datoerne flyttes til (hullets døgn + 1) + 395 / 50 døgn.
