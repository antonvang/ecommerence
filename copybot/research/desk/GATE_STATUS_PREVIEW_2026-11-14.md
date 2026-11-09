# Gate-status pr. 2026-11-14T00:30:00Z (UTC)

> **PREVIEW — genereret 2026-11-09. Dette er IKKE 14/11-statusrapporten.** Den skal genereres igen på dagen (`date -u` først), og DNS skal genkontrolleres med `getent hosts`.

**Ingen automatisk lås. Ingen gate åbnes af dette værktøj.**

Read-only: ingen flag antages, så enhver ejergodkendelse står som manglende, indtil en VERIFIED_OWNER_APPROVAL faktisk foreligger. Et chat-ja er UNVERIFIED_ORIGIN og åbner intet.

Kilder: `research/desk/GATE_MATRIX.json` (gate_matrix/1, as_of 2026-11-06T14:38:27Z, horisont 2026-11-28T23:59:59Z, sha256 `19b87e9af0cf3c97`), `research/desk/NOV14_READINESS.md` (sha256 `bdc320067ad985ac`), `research/desk/OWNER_DECISIONS_NOV14.md` (sha256 `d8852034d4c17856`).

- Pins (`nov14_readiness.verify_hashes`): OK (24/24 filer matcher, tabel = matrix)
- Matrixvalidering (`nov14_readiness.validate`): OK

## 1. Optælling

| Status | Antal gates |
|---|---|
| READY | 6 |
| NEEDS_VERIFIED_OWNER_APPROVAL | 8 |
| NOT_DUE | 6 |
| BLOCKED | 7 |
| WITHDRAWN | 2 |
| i alt | 29 |

READY omfatter 4 begrænsninger (kind `constraint`), der altid gælder og intet åbner.

## 2. Gates

| Gate | Kind | Beskytter | Tidligst (UTC) | Status | Mangler |
|---|---|---|---|---|---|
| `G01_HIST_1114` | date+lock | no historical market-data access (network query or reading historical files already in the cache) before 2026-11-14 00:00 UTC; the owner's rule | 2026-11-14T00:00:00Z | **NEEDS_VERIFIED_OWNER_APPROVAL** | A_n6: lock_A_committed, owner_confirms_lock_A (D1); B_n4: WITHDRAWN; F2: f2_calibration_spec_committed (D3), owner_ack_f2_calibration (D3); C1: ingen handling i matrixen fører C1 gennem G01_HIST_1114 |
| `G02_EXPLORE0_ONLY` | constraint | screenings A/B and the F2 calibration read only explore0 = 2020-03-01..2021-12-31; rows outside are discarded at ingest | — | **READY** | — |
| `G03_HOLDOUT_2024` | never | the sealed final test 2024-01-01..2024-12-31 (incl. news/1 backfill rows published >= 2024-01-01) | — | **BLOCKED** | åbner aldrig i horisonten (kind=never) |
| `G04_RESERVED_2025PLUS` | never | archive data from 2025-01-01 onward is never read (also not as estimation input for forward forecasts) | — | **BLOCKED** | åbner aldrig i horisonten (kind=never) |
| `G05_OWN_FORWARD_OBS` | constraint | own forward observations (lab.db rows >= 2026-10-27) may be read for operations and data quality, never to calibrate, select or test a new hypothesis before its locked protocol and window | — | **READY** | — |
| `G06_NEWS_GATE` | constraint | research tools read news/1 only through gates.news_rows (backfill >= 2024 never reaches Python) | — | **READY** | — |
| `G07_QUARANTINE` | never | files and datasets from documented deviations are never used for a lock, universe or analysis (incl. the 2026-11-02 Upbit pair file) | — | **BLOCKED** | åbner aldrig i horisonten (kind=never) |
| `G08_UPBIT_N4` | date+lock | Upbit's public API (market/all, candles/days) only for N4's research tool, only after N4's lock and from 2026-11-14, one request at a time, >= 0.2 s apart, explore0 rows only | 2026-11-14T00:00:00Z | **WITHDRAWN** | alle undersøgelser trukket tilbage før lås (B_n4); forbliver lukket |
| `G09_COINM_1128` | date+lock | COIN-M files (cm klines, quarterly contracts) only from 2026-11-28 00:00 UTC and only from data.binance.vision; dapi.binance.com is not an allowed host | 2026-11-28T00:00:00Z | **NOT_DUE** | dato 2026-11-28T00:00:00Z; A_n6_X3: lock_A_committed, owner_confirms_lock_A (D1); F3: f3_lock_amendment_committed (D8), f3_observation_unit_locked (D8), owner_key_registered (D5), owner_signed_f3_template (D8) |
| `G10_FAMILY_NET_1128` | date | code for amendment-8 families makes no network request (no HEAD, no download) before 2026-11-28 00:00 UTC; forward data for families only after 2026-11-27 | 2026-11-28T00:00:00Z | **NOT_DUE** | dato 2026-11-28T00:00:00Z |
| `G11_RESTART_1128` | date+owner | no planned host reboot and no system update up to and including 2026-11-27; the pm_lp collector is never stopped on purpose | 2026-11-28T00:00:00Z | **NOT_DUE** | dato 2026-11-28T00:00:00Z; owner_requests_restart (D9) |
| `G12_PMLP` | never | pm_lp, its collector, watcher and systemd unit are never touched by these studies | — | **BLOCKED** | åbner aldrig i horisonten (kind=never) |
| `G13_LOCK_A` | date+owner | lock text A (MISSION27_3 6b with the 7d corrections) is committed as '## Ændring 44 ... metode n6' before any n6 data is read | 2026-11-14T00:00:00Z | **NEEDS_VERIFIED_OWNER_APPROVAL** | owner_confirms_lock_A (D1) |
| `G14_LOCK_B` | date+owner | lock text B is committed as '## Ændring 45 ... metode n4' before any n4 data is read | 2026-11-14T00:00:00Z | **WITHDRAWN** | alle undersøgelser trukket tilbage før lås (B_n4); forbliver lukket |
| `G15_OWNER_SIGNATURE` | owner | a new template / activation needs a verified owner signature; historic template approvals are UNVERIFIED_ORIGIN and never reused | — | **NEEDS_VERIFIED_OWNER_APPROVAL** | owner_key_registered (D5) |
| `G16_F2_WINDOW` | owner | F2 confirmation needs a separately approved evaluation window with sufficient power; the explore0 calibration is never validation | 2026-11-14T00:00:00Z | **NEEDS_VERIFIED_OWNER_APPROVAL** | f2_window_approved (D4) |
| `G17_F2_CALIBRATION` | date+owner | the explore0 calibration may only estimate effect size and variance (sd(d), autocorrelation, cross-section correlation); it is development information, never independent validation, and may not change model, universe or benchmark | 2026-11-14T00:00:00Z | **NEEDS_VERIFIED_OWNER_APPROVAL** | f2_calibration_spec_committed (D3); owner_ack_f2_calibration (D3) |
| `G18_C1_ACTIVATION` | owner | C1 writes no real forecast until a dated PROTOCOL_V3 amendment activates it with a frozen config (v2 for 1h klines), an approved stream and external head anchoring | 2026-11-14T00:00:00Z | **NEEDS_VERIFIED_OWNER_APPROVAL** | c1_amendment_committed (D7); c1_config_v2_frozen (D7); external_anchor_ready (D7); owner_signed_c1_activation (D7) |
| `G19_FWD_KLINE_SOURCE` | owner | there is no approved forward 1h-kline stream; a fapi 1h-kline collector was rejected as a duplicate and daily archive files arrive after the day | — | **NEEDS_VERIFIED_OWNER_APPROVAL** | fwd_kline_stream_approved (D7) |
| `G20_W0_ALPHA` | owner | amendment 8's programme wealth W0 = 0.05; fcarry reserved 0.0125; 0.0375 left = 3 families at alpha_F 0.0125; four claimants; no reclassification of hypotheses as measurements | — | **NEEDS_VERIFIED_OWNER_APPROVAL** | owner_signed_alpha_ranking (D6) |
| `G21_HFC1_3D` | date | the first HFC-1 3 d outcome (cohort 2026-11-04) is computed only after its window [2026-11-05 00:00, 2026-11-08 00:00) has closed | 2026-11-08T00:00:00Z | **READY** | — |
| `G22_STRAKS_7D` | date | the first descriptive straks report covers 7 days from the accounts' start (lane.started 2026-11-05 17:01:51 UTC); fail-closed reading of '2026-11-12 (7 dage)' (AMB-24) | 2026-11-12T17:01:51Z | **READY** | — |
| `G23_PAIRS_1119` | date | the pair-book diagnostic report on 2026-11-19; fail-closed reading = 14 x 24 h from lane.started 2026-11-05 20:41:09 UTC (AMB-25) | 2026-11-19T20:41:09Z | **NOT_DUE** | dato 2026-11-19T20:41:09Z |
| `G24_S1_EVAL` | date | S1 is evaluated only after 14 full days from its actual start 2026-11-06 09:55:07 UTC | 2026-11-20T09:55:07Z | **NOT_DUE** | dato 2026-11-20T09:55:07Z |
| `G25_F3_DEFERRED` | owner | F3 is not activated before its observation unit (dependence between coins, expiries, overlapping positions) and the calibration/evaluation split are fixed | 2026-11-28T00:00:00Z | **NOT_DUE** | dato 2026-11-28T00:00:00Z; f3_observation_unit_locked (D8); owner_signed_f3_template (D8) |
| `G26_S2_S3` | never | S2 needs a new explicit owner decision and is never activated by the assistant; S3 is not approved | — | **BLOCKED** | åbner aldrig i horisonten (kind=never) |
| `G27_NO_REAL_MONEY` | never | research and paper only; no real orders, keys or accounts | — | **BLOCKED** | åbner aldrig i horisonten (kind=never) |
| `G28_NO_ASSISTANT_SIGNATURE` | never | the assistant never signs, never generates or uses the owner's key, never runs approve-template, never locks automatically | — | **BLOCKED** | åbner aldrig i horisonten (kind=never) |
| `G29_LABDB_RO` | constraint | the production lab.db is opened only as file:...?mode=ro with PRAGMA query_only=ON | — | **READY** | — |

## 3. Kræver verificeret ejergodkendelse (NEEDS_VERIFIED_OWNER_APPROVAL)

- `G01_HIST_1114`: A_n6: lock_A_committed, owner_confirms_lock_A (D1); B_n4: WITHDRAWN; F2: f2_calibration_spec_committed (D3), owner_ack_f2_calibration (D3); C1: ingen handling i matrixen fører C1 gennem G01_HIST_1114
- `G13_LOCK_A`: owner_confirms_lock_A (D1)
- `G15_OWNER_SIGNATURE`: owner_key_registered (D5)
- `G16_F2_WINDOW`: f2_window_approved (D4)
- `G17_F2_CALIBRATION`: f2_calibration_spec_committed (D3); owner_ack_f2_calibration (D3)
- `G18_C1_ACTIVATION`: c1_amendment_committed (D7); c1_config_v2_frozen (D7); external_anchor_ready (D7); owner_signed_c1_activation (D7)
- `G19_FWD_KLINE_SOURCE`: fwd_kline_stream_approved (D7)
- `G20_W0_ALPHA`: owner_signed_alpha_ranking (D6)

D-numrene henviser til `research/desk/OWNER_DECISIONS_NOV14.md`. Tidligere godkendelser er UNVERIFIED_ORIGIN og genbruges ikke.

## 4. Undersøgelser (status som registreret i repoets dokumenter)

| Undersøgelse | Status | Note | Matrixhandling på tidspunktet | Kilde |
|---|---|---|---|---|
| F2 | **BLOCKED** | CONDITIONAL; ingen kalibrering eller bekræftelse uden ejerens daterede ja (D3/D4) | `f2_calibration_run` (F2): blokeret — GATE_CLOSED: G17_F2_CALIBRATION missing ['f2_calibration_spec_committed', 'owner_ack_f2_calibration']; MISSING_FLAGS: ['f2_calibration_spec_committed', 'loader_tests_green', 'owner_ack_f2_calibration'] | research/reviews/INBOX.md:297, research/desk/OWNER_DECISION_PACKETS.md:88 |
| A_n6 | **READY_NOT_LOCKED** | kun VERIFIED_OWNER_APPROVAL kan låse; chat-ja = UNVERIFIED_ORIGIN, generel instruks = GENERIC_INSTRUCTION | `lock_commit_A` (A_n6): blokeret — GATE_CLOSED: G13_LOCK_A missing ['owner_confirms_lock_A']; MISSING_FLAGS: ['owner_confirms_lock_A'] | research/reviews/INBOX.md:283, research/reviews/INBOX.md:278 |
| B_n4 | **WITHDRAWN_BEFORE_LOCK** | i forskningsrapporteringen; registret forbliver BLOCKED indtil en ejerautoriseret overgang; ingen N4b | `lock_commit_B` (B_n4): blokeret — GATE_CLOSED: G14_LOCK_B missing ['owner_confirms_lock_B', 'owner_resolves_B_point1']; MISSING_FLAGS: ['owner_confirms_lock_B', 'owner_resolves_B_point1'] | research/reviews/INBOX.md:291, research/desk/OWNER_DECISION_PACKETS.md:54 |
| C1 | **READY_NOT_ACTIVE** | ingen rigtig prognose; ingen godkendt forward-1h-kline-kilde (G19) | `c1_activate` (C1): blokeret — GATE_CLOSED: G18_C1_ACTIVATION missing ['c1_amendment_committed', 'c1_config_v2_frozen', 'external_anchor_ready', 'owner_signed_c1_activation']; GATE_CLOSED: G19_FWD_KLINE_SOURCE missing ['fwd_kline_stream_approved']; GATE_CLOSED: G15_OWNER_SIGNATURE missing ['owner_key_registered']; MISSING_FLAGS: ['c1_amendment_committed', 'c1_config_v2_frozen', 'external_anchor_ready', 'fwd_kline_stream_approved', 'owner_key_registered', 'owner_signed_c1_activation'] | research/desk/GATE_MATRIX.json:26, research/reviews/INBOX.md:362 |
| W0 | **0.0375_LEFT_NO_RANKING_ACCEPTED** | W0 0,0375 tilbage (3 x alpha_F 0,0125); direktøren har ikke accepteret rangeringen; ingen opkrævning | `alpha_charge_w0` (F2): blokeret — GATE_CLOSED: G20_W0_ALPHA missing ['owner_signed_alpha_ranking']; GATE_CLOSED: G15_OWNER_SIGNATURE missing ['owner_key_registered']; MISSING_FLAGS: ['owner_key_registered', 'owner_signed_alpha_ranking', 'w0_rank_includes_F2'] | research/desk/OWNER_DECISION_PACKETS.md:106, research/desk/OWNER_DECISION_PACKETS.md:107, research/reviews/INBOX.md:310 |
| HFC1 | **DESCRIPTIVE** | beskrivende; kohorterne 11-06, 11-07 og 11-08 mangler (ikke dannet, DNS; efterdannes ikke); 11-04 og 11-05 INCONCLUSIVE | `hfc1_report_3d` (HFC1): tilladt | research/reviews/INBOX.md:173, research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md:93, research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md:120, research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md:125 |
| S1 | **OBSERVATION** | read-only shadow-job i observationsfase (INBOX: S1 ACTIVE); evaluering tidligst 2026-11-20 09:55:07 UTC; få nye overgange -> INSUFFICIENT_OBSERVATION, aldrig automatisk PASS | `s1_evaluate` (S1): blokeret — NOT_YET: G24_S1_EVAL opens 2026-11-20T09:55:07Z | research/studies/MISSION27_4_2026-11-02.md:410, research/reviews/INBOX.md:431 |

En status vises kun, hvis alle dens kildelinjer findes i filerne nu; ellers UNVERIFIED_SOURCE (fail-closed). Hvor kilden kun er INBOX-tekst, er INBOX-linjen citeret.

## 5. DNS- og datadækningsafhængigheder

Statisk liste: den lokale DNS (192.168.1.3) svarede `::`/0.0.0.0 for disse værter, observeret 2026-11-06..09 (MISSION27_4 afsnit 17-24). Den skal genkontrolleres med `getent hosts <vært>` på dagen (`--check-dns`). Værktøjet laver ingen netværkskald og omgår ikke filteret.

`getent` ikke kørt (standard). Status for værterne er den statiske observation, ikke dagens.

| Punkt | Omfang | Gates | Værter | DNS-berørt | Datadækning | Kilde |
|---|---|---|---|---|---|---|
| A_n6 | matrix | `G01_HIST_1114`, `G13_LOCK_A` | data.binance.vision: BLOKERET (lokal DNS) | JA | indlæseren skrives først efter låsen; dækningen for n6's explore0-data er ikke opgjort i repoet | research/desk/GATE_MATRIX.json:233 |
| A_n6_X3 | matrix | `G09_COINM_1128` | data.binance.vision: BLOKERET (lokal DNS) | JA | COIN-M cm-sti, tidligst 2026-11-28; dapi.binance.com er ikke tilladt | research/desk/GATE_MATRIX.json:451 |
| B_n4 | matrix | `G08_UPBIT_N4`, `G14_LOCK_B` | upbit (kun N4; vært navngives kun i n4_kimchi.py): ikke på DNS-listen | nej | WITHDRAWN_BEFORE_LOCK: ingen adgang; Binance-krydsningens kilde er ikke fastlagt (AMB-19); den karantænerede parliste bruges aldrig | research/desk/GATE_MATRIX.json:419 |
| F2 | matrix | `G01_HIST_1114`, `G17_F2_CALIBRATION`, `G16_F2_WINDOW` | data.binance.vision: BLOKERET (lokal DNS) | JA | lokal cache (kun filnavne talt): i explore0 har 15 af 20 mønter alle 22 måneder (SOL 16, AVAX 16, DOT 17, DOGE 18, FIL 15); manglende måneder kræver data.binance.vision | research/desk/GATE_MATRIX.json:233, research/desk/NOV14_READINESS.md:137 |
| C1 | matrix | `G18_C1_ACTIVATION`, `G19_FWD_KLINE_SOURCE` | ingen vært | nej | ingen godkendt forward-1h-kline-strøm (vært, endpoint og kadence ikke besluttet); daglige arkivfiler kommer efter døgnet | research/desk/GATE_MATRIX.json:751 |
| HFC1 | matrix | `G21_HFC1_3D` | data-api.binance.vision: BLOKERET (lokal DNS); fapi.binance.com: ikke på DNS-listen | JA | kohortedannelse kræver spotbogen (data-api.binance.vision); 11-06, 11-07 og 11-08 ikke dannet (ConnectionRefused, DNS); udfald læses read-only fra lab.db census | research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md:7, research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md:127 |
| STRAKS | matrix | `G22_STRAKS_7D` | fapi.binance.com: ikke på DNS-listen | nej | ren perp-bog (fapi), mærkes normalt; rapporten læser lab.db read-only | research/studies/MISSION27_4_2026-11-02.md:422 |
| PAIRS | matrix | `G23_PAIRS_1119` | fapi.binance.com: ikke på DNS-listen | nej | ren perp-bog (fapi), mærkes normalt; rapporten læser lab.db read-only | research/studies/MISSION27_4_2026-11-02.md:422 |
| S1 | matrix | `G24_S1_EVAL` | ingen vært | nej | kun lab.db (mode=ro); S1-hullet er registreret (MONITORING_GAP) | research/studies/FACTORY_S1_P0_2026-11-06.md:20, research/reviews/INBOX.md:174 |
| F3 | matrix | `G09_COINM_1128`, `G25_F3_DEFERRED` | data.binance.vision: BLOKERET (lokal DNS) | JA | DEFERRED; COIN-M tidligst 2026-11-28; observationsenhed ikke fastlagt | research/desk/GATE_MATRIX.json:451 |
| LIQPROXY1 | matrix | `G20_W0_ALPHA` | fapi.binance.com: ikke på DNS-listen; data-api.binance.vision: BLOKERET (lokal DNS) | JA | kræver nye strømme fwd_tob_universe og fwd_spec_journal (PROPOSED_NEEDS_SEPARATE_APPROVAL) | research/desk/protocols/LIQPROXY1_v1.md:211, research/desk/stream_registry.json:699 |
| FUNDFRAG1 | matrix | `G20_W0_ALPHA` | fapi.binance.com: ikke på DNS-listen; data-api.binance.vision: BLOKERET (lokal DNS) | JA | kræver ny strøm fwd_spec_journal (PROPOSED_NEEDS_SEPARATE_APPROVAL) | research/desk/protocols/FUNDFRAG1_v1.md:207, research/desk/stream_registry.json:666 |
| OPS | matrix | `G11_RESTART_1128` | ingen vært | nej | ingen værtsafhængighed | — |
| pm_lp (collector) | uden for matrixen | — | clob.polymarket.com: BLOKERET (lokal DNS) | JA | DEGRADED; urørt (G12_PMLP: aldrig rørt af disse undersøgelser) | research/PM_LP_SPEC.md:32, research/reviews/INBOX.md:173 |
| lane/carry90 spotben (9 konti) | uden for matrixen | — | data-api.binance.vision: BLOKERET (lokal DNS) | JA | ingen equity-mærkning siden 2026-11-08 06:40:31 UTC -> STALE i net_report | research/desk/STALE_EQUITY_59C.md:73 |
| K05 negRisk v2 (kun design) | uden for matrixen | — | gamma-api.polymarket.com: BLOKERET (lokal DNS); clob.polymarket.com: BLOKERET (lokal DNS) | JA | design alene (ordre 60 E); ingen data eller strøm | research/desk/PROFIT_SEARCH_2026-11-09.md:124 |

## 6. Statusværdier

- READY: gaten er åben efter matrixens egne betingelser (dato nået og alle flag til stede), eller en begrænsning, der altid gælder. Aldrig mere åben end `nov14_readiness.gate_status`.
- NOT_DUE: `earliest_utc` er ikke nået; datoen og flagene står som manglende.
- NEEDS_VERIFIED_OWNER_APPROVAL: datoen er nået (eller der er ingen dato), men mindst ét ejerbeslutningsflag (D-tabellen) mangler.
- BLOCKED: `never`-gate, malformet gate, ingen matrixhandling for undersøgelsen, eller kun ikke-ejerflag mangler.
- WITHDRAWN: alle gatens undersøgelser er registreret trukket tilbage før lås; forbliver lukket.

**Ingen automatisk lås. Ingen gate åbnes af dette værktøj.**
