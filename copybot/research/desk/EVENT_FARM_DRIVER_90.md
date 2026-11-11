# Event farm: syntetisk driver (direktørordre 90)

Skrevet 2026-11-11 kl. 18:04 lokal tid (17:04 UTC) af Claude.
- Kode: `research/tools/event_farm_driver.py`.
- Tests: `tests/test_event_farm_driver.py` (21 tests).

Status: **UDKAST, IKKE LÅST.** Driveren læser kun syntetiske data. Intet er låst, ingen alfa er brugt, ingen ledger-række
er skrevet, og intet er aktiveret.

## P0: register

- **Studie-ID:** `EVENT_FARM`, klassificeret `RELATED_MECHANISM` uden selvstændig lineage og uden påstand om uafhængighed.
- **Beslægtede lineages:**
  - `liquidation_cascade_reversal`: `MOVESCREEN_m21c`, `E_daily_reversal_p1`, `L21_m2_liquidation_reversal`;
  - `cross_sectional_momentum`: `L03_sol_trend_hourly`, `L14_tsmom_v1`, `E_donchian_trend_p1/p2`.
- **To FUTURE-poster i kode** (`v2_records()`, ikke persisteret):
  - `EVENT_FARM_EXPLORE0_SETUPS`: 39 tests;
  - `EVENT_FARM_EXPLORE0_EVENTS`: 276 tests.

  Begge har `trial_universe.size` = 315. `all_tests()` opregner de 315 tests: 3 opløsninger × (13 setup-tests + 92
  hændelse × horisont). `variants_tested` er MISSING_INPUT, fordi intet er kørt på markedsdata. Datakilden er den
  planlagte fra `EVENT_FARM_PLAN_88.md`. Den er kun beskrevet, ikke åbnet.

## P1: driver

- **Motor:** `event_farm.py` skal være commit f686c9a med sha256
  `7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76`. Hashen tjekkes før import. Afviger den, rejses
  `EngineMismatch`.
- **Fail-closed indlæsning.** Trinene kører i denne rækkefølge, og der åbnes ingen fil, før alle tidligere trin er
  bestået:
  1. Manifestet er en dict med præcis de kendte nøgler og `source == "synthetic"`.
  2. Stien tjekkes som streng:
     - ingen forbudte dele (produktionscache, `data/lab/`, klines, databaser, karantæne, `research/data`, arkiver);
     - filnavnet er `synthetic_<navn>.json` og er det navn, manifestet angiver;
     - stien ligger under en tilladt rod (`research/desk/synthetic_fixtures` eller systemets temp-mappe).
  3. Symlinks opløses, og stien tjekkes igen.
  4. Filen åbnes:
     - sha256 skal svare til manifestet;
     - den indlejrede provenance skal svare til manifestet;
     - instrumentnavne skal starte med `SYN`.

  Der findes ingen kontakt, der lukker markedsdata ind.
- **Aggregering:** 1m → 5m og 15m. Spanden er floor(ts / bs) · bs; o er første minuts open, h er max, l er min, c er
  sidste minuts close og v er summen. En spand uden alle sine minutter droppes og tælles. ts uden for minutgitteret,
  dubletter og forkert rækkefølge afvises.
- **known_ts-reglerne** (plan 88 afsnit 6) tjekkes for hver hændelse og hvert setup. Trunkeringstesten
  (`check_lookahead`) kører på op til tre udsnit pr. instrument og opløsning. Ethvert brud standser kørslen, før der
  kommer resultater.
- **Fill-usikkerhed:** for hver variant opgøres andelen af handler med en bar, der rammer både stop og mål, og andelen
  af fyld, der kun skete ved berøring. Desuden genafspilles hvert 5m- og 15m-setup på 1m fra første minut efter
  `known_ts`, med vinduer ganget med bs/60, og statusskiftene opgøres.
- **Output:** deterministisk, med `provenance` (kilde, manifest, motorens commit og sha256, driverens sha256) og
  `result_sha256`.
- **Null:** `null_reference()` kører motorens null med seed 83. Seed er ikke en parameter.

## Eksempel: kun syntetisk

2 instrumenter × 5 dage 1m random walk (seed 901/902), standardparametre:

| opløsning | known_ts-brud | lookahead | hændelser pr. instrument-dag | setups pr. instrument-dag |
|---|---:|---|---:|---:|
| 1m | 0 | PASS | 1.616 | 21,2 |
| 5m | 0 | PASS | 268 | 4,0 |
| 15m | 0 | PASS | 80 | 1,4 |

- 1m-genafspilningen ændrede ingen status ved 5m eller 15m.
- Multiple testing med N = 315 var INCONCLUSIVE.
- Tallene beskriver støj og er ikke evidens.

## Hvad driveren ikke gør

- Den læser ikke explore0 eller andre markedsdata. Det kræver gates og godkendelse efter plan 88: tidligst
  2026-11-14, direktørens ja og en committet ændring før data. Det kræver også et nyt, godkendt indlæsningsmodul.
- Den skriver ingen filer, bortset fra `write_fixture` til syntetiske fixtures i en tilladt rod.
- Den bruger intet netværk og ingen produktionscache.
- Den ændrer ikke `event_farm.py`.
