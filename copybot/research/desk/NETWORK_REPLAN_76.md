# NETWORK_REPLAN_76: forskning uden de fem blokerede værter (direktørordre 76 P0–P3 og P5)

Skrevet 2026-11-09 kl. 23:19 lokal (22:19 UTC). **Kun plan. Ingen lås, alfa, statusændring, ledger-række eller aktivering.**

Mærker: **[F]** = fakta fra kode, protokol eller lab.db (aggregater). **[V]** = min vurdering. Tal fra lab.db er aflæst
2026-11-09 22:14:05 UTC med `mode=ro` + `query_only`, kun `COUNT(*)`, `MIN(ts)`, `MAX(ts)` pr. detektor/kilde/metric/konto.
Ingen rækkeindhold, nyhedstitler, udfald eller payload. `pm_lp.db` er ikke læst; dens tal er fra `PM_LP_D1_STATUS_72.md`.
Intet netværk. Cache-tal er fra `NOV14_READINESS.md` og `U4_PROVENANCE_POWER_AUDIT.md`; cachen er ikke åbnet her.

**Udgangspunkt [F]:** `clob.polymarket.com`, `gamma-api.polymarket.com`, `docs.polymarket.com`, `data-api.binance.vision`
og `data.binance.vision` er permanent utilgængelige. Det er en bevidst beslutning. Planen indeholder ingen vej uden om
beslutningen. At en vært teknisk svarer, er ikke tilladelse til en ny collector eller stream.

## 0. Tre fund, der haster

1. **Automatisk stop kan give et-benede papirpositioner fra 2026-11-12 04:47 UTC [F].** Seks af de ni STALE-konti har
   stopreglen `source` (funding − gebyrer ≤ 0 efter 14 dage, `lab/lane.py`). Funding bogføres stadig (perp-data), så reglen
   vurderes på friske tal. Hvis en konto stoppes, lukker `paper_runner.close_ledger` ben for ben: perp-benet lukker via
   fapi, spot-benet får `book unavailable` og bliver stående. Tidligste datoer i afsnit 3. Om reglen faktisk udløses, er
   ikke beregnet (kræver udfaldstal).
2. **Der findes i dag ingen kontakt, der fryser de ni uden bivirkninger [F].** `lane-off` stopper alle aktive banekonti,
   også STRAKS og PAR-BOG (`lane.manage`), og ville ødelægge milepælene 12/11 og 19/11. En manuel pause giver stop efter
   24 t (`PAUSE_RETIRE_S`). Arkiveringen kræver derfor en dateret ændring før kode.
3. **Mærkning genoptages af sig selv, hvis en vært svarer [F].** `mark_guarded` prøver igen hver time, og pm_lp-collectoren
   er i genstartsløkke. Det strider mod "ingen automatisk genoptagelse" (afsnit 3).

## 1. Datakildekort (read-only)

### 1a. Kilder uden blokeret vært [F]

Friskhed = `MAX(ts)` UTC, 2026-11-09 medmindre andet står.

| Kilde (kode) | Instrumenter og datatyper | n, første → seneste | Afhængige | Begrænsninger |
|---|---|---|---|---|
| `census/1` (`lab/census.py`, fapi) | Alle USD-M-perps: mark, index, lastFundingRate, 24h-ticker, timevis | 302 snapshots, 10-27 15:00:23 → 22:00:34 | HFC-1-udfald, 28a-hypoteser, census_check | lastFundingRate er ikke afregnet funding. 8 t-antagelse. Afnoteringer ses ikke |
| premium-watch `pricing_constraint/2` (`lab/scanner.py`, fapi) | Forudsagt funding, præmie, medianer, 60 s | `predicted_funding` 440.718, `perp_premium` 213.791, → 22:13:54 | banerne 12e/12i, K3 | Kun flagede rækker og medianer gemmes |
| premium-watch Hyperliquid | Forudsagt funding, gap mod fapi | `hl_predicted_funding` 29.096, → 22:13:54 | HL-baner, scanner | `identity_mismatch_suspected` 10.231 rækker: navne skal matches |
| `funding_settled/1` (fapi) | Afregnet funding, 12 markeder | 912, 10-25 → 20:02:29 | K1/K2 | Kun 12 markeder |
| `abnormal_move/1` (`lab/moves.py`, fapi) | 12 markeder: 1h-klines, z, volumen, spread, 5k-rundtur | `z_1h` 4.881, → 22:02:01 | K1/K2, STRAKS | Kun 12 markeder |
| `k3/1` (fapi) | Mark i S±35 min, bøger | `mark` 336.239, `book` 3.252, → 22:13:54 | K3 | Kun vinduerne |
| `capacity/1`, perp-ben (fapi) | 500-niveau-bøger, rundtur 500–50k | 549 pr. metric, → 06:39:58 | 21v | Spot-delen er blokeret (1b) |
| `benchmark/1` (fapi) | Køb-og-hold pr. bog | 4.171, → 21:40:23 | dashboard | — |
| `hlcensus/1` (Hyperliquid `/info`) | 235 HL-navne: funding, præmie, mark, OI, volumen | 176, 11-02 15:00:01 → 22:00:34 | hlcensus_look | Kun fra 11-02 |
| `news/1` (8 kilder) | Titler med `usable_from`; Binance, Cointelegraph, CoinDesk, CNBC, ECB, BLS, Fed, GDELT | binance.com 7.224 → 06:09:45; GDELT 30 → 10-22 | H5F, H5X, M1F, U1F-kandidater, moves, K10 | Kun via `gates.news_rows` (G06). GDELT i praksis stoppet. 2024+-tilbagefyld er holdout |
| `onchain/1` (CoinMetrics) | BTC/ETH-børsstrømme, first-seen og revisioner | `flow_first` 114, → 09:11:18 | 21q (ingen låst forbruger) | CC BY-NC. PIT kun fra 10-24 |
| CoinMetrics-katalog (`coinbase/1`, `upbit/1`) | Første handel | 254+254 og 54+334 rækker, én gang 10-23/24 | 17g/17h/U1F | Læses én gang ved måling |
| `sim_*` for STRAKS, PAR-BOG, FWD_E×10, SHADOW_E | Papirfyld og mærker via fapi | `sim_equity` → 22:00:43 | 12/11, 19/11, S1 m.fl. | Bog ved ordre; selekteret stikprøve |
| `lab.db` alene | S1 (`factory_s1`) | ingen vært | 20/11 | Kører kun med timetjek |

Tilladte værter står uændret i `tests/test_lab_safety.py`. Listen er en teknisk ramme, ikke en godkendelse af nye strømme.
Nye strømme er stadig `PROPOSED_NEEDS_SEPARATE_APPROVAL`, og G19 gælder.

### 1b. Kilder med blokeret vært [F]

| Kilde (kode) | Datatyper | Sidst OK | Fejl efter | Afhængige |
|---|---|---|---|---|
| `venue_subsidy/1` (`lab/scanner.py`, clob) | Reward-puljer | 11-06 20:02:00 (531) | 93 fejlrækker, seneste 22:02:01 | kun discovery |
| `pricing_constraint/2`, Polymarket (gamma) | negRisk | 11-06 20:02:00 (526) | 98 fejlrækker, seneste 22:02:01 | kun discovery, K05 |
| `research/pm_lp.py` (clob) | Bøger 60 s, belønning, status, `winner` | Sidste data 11-08 06:45 (åbning 06:39–06:45); før det 11-06 20:52 | genstartsløkke | pm_lp_v1 |
| `paper_runner.fetch_book` (`.SPOT`, data-api) | Spot-bog ved ordre og mærke | 11-08 06:40:31 | `mark_guarded`-fejl | 9 STALE-konti, alle nye carry-, scanner- og HL-konti |
| `lane.spot_pairs` (data-api) | Spot-liste | ej målt | beholder sidste liste; `None` efter genstart | filter 19 |
| `capacity/1`, spot-ben (data-api) | Rundtur | 11-06 09:14:11 (225) | 54 fejl, seneste 11-09 06:39:58 | 21v spot |
| `depth500/1`, spot (data-api) | 12g-diagnose | 11-01 08:01:29 | — | kun diagnose |
| `research/tools/hfc1_daily.py` (data-api) | Spot-liste og spot-bog ved kohorte | kohorte 11-05 | ConnectionRefused | HFC-1-kohorter |
| `pilot/exchange.py`, `research/tools/v1_books.py`, `carry_basis.py`, `fetch_recent_funding.py` (data-api) | Spot | — | — | pilot-dry-run, V1's Binance-række, ad hoc |
| `lab/engine/data.py`, `ingest.py`, `r3.py`, `measure_h4.py`, `explore.py`, `families`, `pipeline.py`, `hypogen.py` (data.binance.vision) | Månedsarkiver: klines, funding, spot, metrics, aggTrades, bookDepth, COIN-M | Registrerede læsninger 10-17 → 10-19 (24.112 rækker i `datasets`) | Nye måneder kan ikke hentes | Familier (8), bane (10b/10d), m17, F2-bekræftelse, A_n6, F3, U1F, M1F, H4/H5 |

Også [F]: `lab/automation/copybot-lab.service` venter i `ExecStartPre` på `getent hosts data.binance.vision`. Svarer
filteret `::`, passerer ventetjekket uden at vise forbindelse. Svarer det NXDOMAIN, fejler enheden efter 10 min. Enheden
er markeret "FORBEREDT, IKKE AKTIVERET".

### 1c. Lokal cache: bruges kun, som den er [F]

Cachen gælder kun under G01 (intet før 14/11), G02 (explore0-regler), G03 (2024 aldrig), G04 (2025+ aldrig).
Ingen nye måneder, mønter eller filer kan komme til.

| Datasæt | Status (fra `NOV14_READINESS`/`U4`) | Konsekvens |
|---|---|---|
| USD-M 1h-klines, F2's 20 mønter | train3+validation3: 24/24 for alle. Explore0: 15 mønter 22/22; SOL 16, AVAX 16, DOT 17, DOGE 18, FIL 15 | F2 behøver sandsynligvis intet netværk. Kalibrering på 15 mønter |
| 1m BTC/ETH 2020-03..2021-12 | 44 filer | U4 H1 uden nye data; ikke frisk (R3 har læst dem) |
| Funding, spot-klines, metrics, aggTrades-pilot, bookDepth, DVOL, FRED, DefiLlama, CoinMetrics, pageviews, kalender | Findes efter `lab/coverage.py`, dækning ikke opgjort her | Opgøres pr. protokol før lås |
| COIN-M | Ikke opgjort i repoet | Kan ikke hentes |

## 2. Konsekvensanalyse (ingen retroaktiv ændring)

| Forsøg | Afhængighed | Konsekvens | Status efter ordre 76 |
|---|---|---|---|
| **pm_lp_v1** | clob (bøger, status), Polymarket-data-vært (handler, belønning) | [F] D1 kan ikke nås (`PM_LP_D1_STATUS_72.md`: bedste tilfælde 71,98 % mod ≥ 90 %, fejlede polls ≥ 1,28 % mod ≤ 1 %). [F] `research/PM_LP_FROZEN.md` findes hverken i git eller i produktion, og `holdout` nægter uden den. [F] `payout_check` (D2) laver netværkskald inde i `holdout`, og fejl fanges med `continue`, så en netværksfejl ligner "programmet betaler ikke" | `PASS_UNREACHABLE / PENDING_FORMAL_CLOSE` uændret. Ingen PASS, ingen fordel påstået. Evaluator og data urørt |
| **pm_lp_v2** | Samme | NO-GO (ordre 76). `PM_LP_V2_DESIGN_72.md` står som historik. Dens forudsætning 1 kan ikke opfyldes og foreslås ikke opfyldt | NO-GO |
| **K05 negRisk v2** | gamma, clob, docs | Polymarket: STOP for ny udvikling | Lukket, kun historik |
| **9 STALE-konti** | Spot-ben | Ingen mærker siden 2026-11-08 06:40:31. Funding bogføres stadig | Arkiveres (afsnit 3) |
| **HFC-1** | Kohorte: data-api og fapi. Udfald: census | [F] Protokollen har 21 kohorter 11-04..11-24; 2 er dannet (11-04, 11-05). 11-06..11-08 er registreret som ikke dannet; 11-09..11-24 kan ikke dannes. Udfald på de 2 berøres ikke; omkostninger er gemt i kohortefilerne | De 19: BLOCKED/MISSING uden erstatningspriser, ingen efterdannelse. De 2 følger protokollen |
| **STRAKS** (41) | Kun perp | Upåvirket | Kører |
| **PAR-BOG** (43) | Kun perp | Upåvirket | Kører |
| **S1** | Kun lab.db | Upåvirket | Kører; forventet `INSUFFICIENT_OBSERVATION` |
| **carry90** (42/42a) | Spot-ben fra data-api | STALE. Opgørelse 2027-02-03 og 180 d kan ikke laves som specificeret | Arkiveres |
| **lane/scanner/HL** (11–13, 19) | Spot-ben, spot-liste; HL-kort-ben fra HL, lang spot fra data-api | [F] Indgang kræver begge bøger i `run_one`, `_probe` dropper mønter uden spot-bog. Ingen ny carry-, scanner- eller HL-konto kan handle. Scanner-detektorerne virker | Ingen nye konti. Aktive: kun de ni. Afsluttede konti er historik |
| **H5F** (16d), **H5X** (16f) | `news/1`, `fapi/v1/fundingRate`, HL | [F] Låst tekst bruger ikke blokeret vært | Fortsætter; deadline 2027-06-30 |
| **U1F** (17i), **M1F** (17j) | Udfald fra Binance' månedsarkiver på data.binance.vision | [F] Ingen måling efter låst tekst, heller ikke ved deadline 2027-06-30. Cachen dækker ikke perioden | Foreslået `BLOCKED_DATA_SOURCE_UNAVAILABLE`. En anden udfaldskilde er en ny låst tekst og en ny hypotese; den foreslås ikke her. Nyhedsindsamlingen kører videre |
| **m17-pipelinen** (17/17a) | Månedsarkiver; `sar_*` bruger spotfiler | Kandidater uden cachede filer kan ikke screenes | Kun det, der ligger i cachen |
| **F2/C1** | Cache; C1 kræver G19 | F2 upåvirket af ordre 76, stadig bundet af D3/D4/D5. C1: arkiv-vejen er væk | Uændret |
| **A_n6** | Cache eller data.binance.vision | Dækning er ikke opgjort. Kan låsen ikke opfyldes af cachen, er A_n6 uden data | Uændret; opgøres før eventuel lås |
| **A_n6_X3, F3** | COIN-M kun fra data.binance.vision | Kan ikke gennemføres | Foreslået `BLOCKED_DATA_SOURCE_UNAVAILABLE` |
| **Familier (ændring 8), bane** | Kun data.binance.vision fra 11-28 | Nye filer kan ikke hentes | Kun cache |
| **Pilot** (tør kørsel, pm_lp-pilot) | `pilot/exchange.py` spot-host; pm_lp PASS | Kan ikke køre | BLOCKED (ingen ændring af ejerreglen om rigtige penge) |
| **LIQPROXY1, FUNDFRAG1** | Foreslåede strømme; spot-ben i B1 | B1's spot-ben kan ikke bygges; D1's spot-liste heller ikke | Må evt. omskrives før lås (76-B) |

**[V] pm_lp_v1, formel afslutning.** Direktøren vælger mellem:
(a) afslutte på skrift uden `holdout`-kørsel, med D1 fra den låste formel og diagnostikken begge opgivet, og
(b) skrive `PM_LP_FROZEN.md` nu og køre `holdout`. (b) kræver en udtrykkelig afvigelse, fordi filen skulle være committet
2026-10-31 før holdout (LINUX_DRIFT punkt F), og `payout_check` skal rapporteres som teknisk mislykket. Jeg anbefaler (a).

## 3. Arkiveringsplan for de ni konti

**Status:** `DATA_SOURCE_UNAVAILABLE`. Sættes ikke af denne opgave. Tidligste konti under 14-dages-reglen er angivet.

| Konto | Type | Start (`sim_equity` min) | Sidste mærke | Sidste regulære mærke | Funding-rækker efter mærket (seneste) | `source`-regel fra |
|---|---|---|---|---|---|---|
| `LANE_1c07df98c7` | CARRY90-BTC | 2026-11-05 18:38:56 | 2026-11-08 06:40:31 | 2026-11-06 20:00:00 | 5 (11-09 16:01:23) | ingen (carry90) |
| `LANE_65e2a1f395` | CARRY90-ETH | 2026-11-05 18:38:56 | samme | samme | 5 (11-09 16:01:23) | ingen |
| `LANE_bc12a61803` | CARRY90-GULD | 2026-11-05 20:40:30 | samme | samme | 10 (11-09 20:00:41) | ingen |
| `LANE_53058593e8` | carry_floor | 2026-10-29 04:47:29 | samme | samme | 15 (11-09 16:01:23) | **2026-11-12 04:47 UTC** |
| `LANE_c2d8a7505e` | carry_floor | 2026-10-31 23:42:16 | samme | samme | 10 | 2026-11-14 23:42 UTC |
| `LANE_2df94018bc` | carry_filter_weekly | 2026-11-02 23:09:50 | samme | samme | 15 | 2026-11-16 23:09 UTC |
| `LANE_ce8964dccc` | carry_filter_weekly | 2026-11-03 08:02:20 | samme | samme | 10 | 2026-11-17 08:02 UTC |
| `LANE_9f1dc841b2` | carry_filter | 2026-11-05 20:14:13 | samme | samme | 20 | 2026-11-19 20:14 UTC |
| `LANE_ec1b0457b8` | carry_filter | 2026-11-05 20:25:41 | samme | samme | 10 | 2026-11-19 20:25 UTC |

[F] Ingen fyld efter det sidste mærke på nogen af de ni. Mærket 11-08 06:40:31 er taget inden for en åbning på 6 minutter
før ordre 76. Det ændres ikke, men mærkes særskilt (`mark_in_open_window`).

**Plan (hvert trin kræver sit eget daterede ja; intet er gjort):**

1. **Arkivregister** (fil, append-only): konto-id, type, start, `last_mark_ts`, `last_regular_mark_ts`, `mark_in_open_window`,
   åbne positioner ved mærket, begrundelse (ordre 76) og sha256 af rækkerne. Værdier hentes via det eksisterende
   `net_report --cutoff` (`at_mark`), ikke beregnes på ny.
2. **Rapportlag:** arkiverede konti står i en særskilt sektion med status, mærke-tid og "sidst kendt, ikke aktuel".
   Funding, fyld og mærker efter `last_mark_ts` må aldrig indgå i aktuel P&L. `net_report` adskiller allerede `at_mark` og
   `after_mark`; `portfolio_current_total` forbliver `null`, så længe en konto ikke er FRESH.
3. **Ingen automatisk genoptagelse:** kræver en kodeændring med dateret ændring, grøn suite og deploy i tilladt vindue.
   Mærkning, `_retire_reason` og `close_ledger` skal springe arkiverede konti over. Skal ligge før **2026-11-12 04:47 UTC**.
4. **Åbne ben:** holdes som registreret, lukkes ikke og markeres ikke på anden vis. Ingen erstatningspris.
5. **Ophævelse:** kun ved ny, dateret ejerbeslutning og som et nyt forsøg med ny start. Aldrig genoptagelse af samme konto.
6. **Ikke-brug:** `lane-off` og manuel pause bruges ikke til dette (afsnit 0).

Kohorter og forsøg med status `BLOCKED_DATA_SOURCE_UNAVAILABLE` behandles på samme måde: sidste observation bevares,
intet udfyldes, ingen rapportdato opfindes.

## 4. Prioriteret forskningsplan (ingen aktivering)

**Krav til alt nedenfor (fra PROTOCOL_V3 og ordre 75/76):**

- **Præregistrering** før data: hypotese, estimand, vindue, stopregler, med dateret tekst. Lås kun med verificeret ejer-ja.
- **Proveniens:** hver datakilde med vært, dato og sha256; PIT-regel; G01–G06 respekteres. Ingen ny kilde uden egen ændring.
- **Omkostninger:** taker 0,10 %, slippage 0,02 % pr. side og ben, spread fra målt bog. Spot-ben kan ikke måles fremad.
- **Uafhængig validering:** eget vindue uden for udvikling; explore0 er aldrig validering. Register V2 og valideringsmotoren
  (ordre 75) bruges; DSR/PBO kun med rigtige input, ellers `MISSING_INPUT`.
- **Multipel testning:** 206 forsøg, 19.438 varianter. Ingen alfa uden D6/G20 (W0 0,0375 tilbage).
- **Power før data** (ændring 32): n, effekt, styrke opgjort ex ante; under 80 % er det beskrivende.
- **Stopkriterier** fastlagt før data, inkl. datastop (datakvalitet) og tidsstop.

| Prioritet | Arbejde | Data | Tilladt? | Status | Næste skridt |
|---|---|---|---|---|---|
| 1 | Milepælene 12/11, 14/11, 19/11, 20/11 | Fremad, lab.db | Ja | Klar | Kør efter procedurerne |
| 2 | Arkivering af de ni og pm_lp-afslutning | Egne rækker | Ja, kræver ja | Ikke startet | Afsnit 3 |
| 3 | F2 HAR-RV mod EWMA | Cache | Ja, med D3/D4/D5 | Bedste kandidat [V] | Uændret; intet netværk |
| 4 | 76-B FAPI-mekanismer | fapi, HL | Kun design og syntetik før 14/11 | Parallelt spor | Designs leveres af anden agent |
| 5 | U4 H1 BTC 08:30 | Cache 1m | Ja, efter audit | NO-GO for lås nu | Betingelser i U4-auditten |
| 6 | H5F, H5X | Fremad | Ja | Afventer 20 listninger | Koden skrives, når data findes |
| 7 | FUNDFRAG1 | fapi-strømme | Kræver strøm-ja | Skal omskrives uden spot-liste | Efter 76-B-overlap |
| 8 | K04 HLP-vault | HL `/info` | Ja, designet | Afventer | Kun hvis W0 og strøm godkendes |
| — | U1F, M1F, F3, A_n6_X3, HFC-1-resten, carry, pm_lp, K05, LIQPROXY1 med spot | Blokeret | Nej | Stoppet/BLOCKED | Ingen |
| — | K10 Monitoring Tag som handel | Perp-bøger; evidens fra M1F | Host ja; evidens nej | Venter: M1F kan ikke levere målingen | Ingen |

[V] Ingen kandidat har dokumenteret nettofordel (ordre 75: 0 PASS af 235). Den bedste nære evidens er fortsat F2 og de
beskrivende fremadrettede rapporter. Spot-perp-carry kan ikke længere måles med eksekverbare spotpriser her.

## 5. Milepæle

| Dato (UTC) | Punkt | Kan gennemføres? | Begrundelse |
|---|---|---|---|
| 12/11 ≥ 17:11:51 | STRAKS 7 d | **Ja** [F] | Kun perp; kontiene er mærket til 11-09 22:00:43; rapporten bruger intet netværk |
| 14/11 | Gate-status | **Ja**, men læses med ordre 76 [V] | Værktøjet virker. Teksten "BLOKERET (lokal DNS)/genkontrolleres" er nu forkert framing; `--check-dns` er unødvendig. A_n6 afhænger af cache; G09 og F3 kan ikke åbne for reelle data |
| 19/11 ≥ 00:35 | HFC-1 14 d (11-04) | **Ja** [F] | Kun census; omkostning gemt |
| 19/11 ≥ 20:51:09 | PAR-BOG | **Ja** [F] | Kun perp |
| 20/11 ≥ 00:35 | HFC-1 14 d (11-05) | **Ja** [F] | Kun census |
| 20/11 ≥ 09:55:07 | S1 | **Ja** [F] | Kun lab.db; forventet `INSUFFICIENT_OBSERVATION` |
| 27/11 | pm_lp-hale slut | Delvist [F] | Halen kan ikke observeres efter DNS-hullet; ingen PASS |
| 28/11 ≥ 00:00 | pm_lp holdout | **Nej** (ikke som PASS) [F] | D1 uopnåelig. `holdout` mangler `PM_LP_FROZEN.md`. Formel afslutning: afsnit 2 |
| 28/11 | COIN-M (A_n6_X3, F3, G09) | **Nej** [F] | Kun data.binance.vision |
| 28/11 | Familie-netværk (G10), bane fra 28/11 | **Nej** for nye filer [F] | Samme |
| 28/11 | HFC-1 3 d-opsummering | Ja for 2 kohorter [V] | Afsnit 2. Beslutningsnotat "efter 11-28" står ved magt |
| 28/11 | Genstart (G11, D9) | Ja, ejerens beslutning [F] | Ingen værtsafhængighed. pm_lp's egne trin afgøres først |
| 12-09 | HFC-1 14 d-opsummering | Delvist [V] | Datoen forudsætter 21 kohorter; kun 2 findes. Datoen flyttes ikke her |

## 6. Uafklaret

1. **Polymarket-data-værten** (`pm_lp.py`'s DAPI) er ikke blandt de fem. Dens status er ikke testet (intet netværk) og er
   uden betydning for STOP-beslutningen. Hvis direktøren vil have den med, skal det stå i teksten.
2. **`dev` for pm_lp_v1:** om den er kørt, kan ikke ses (ingen `PM_LP_FROZEN.md`, resultatfilen ligger under `data/`).
3. **Stop-reglens udfald** for de seks: kræver funding og gebyrer. Ikke beregnet.
4. **Køede jobs mod data.binance.vision** (m17, bane): om de fejler og gentages, er ikke målt (jobs-tabellen er uden for
   rammen). Støj fra scanneren og pm_lp-løkken fortsætter, indtil de ændres ved en dateret beslutning.
5. **A_n6 og øvrige datasæt:** cache-dækning er ikke opgjort.
6. **`copybot-lab.service`:** hvordan produktionsversionen ser ud, er ikke tjekket; kun repoets fil.
7. **Ordre 76 P4 (arkivvisning):** kun planlagt her; intet bygget.

## 7. Ikke gjort

Ingen git-skrivning, ingen eksisterende fil ændret, ingen netværkskald, ingen historisk forespørgsel. Ikke rørt:
`pm_lp.db`, karantænemappen, `research/data/N4_KIMCHI_PAIRS_2026-11-02.json`, filer under `data/` og `research/data/`.
