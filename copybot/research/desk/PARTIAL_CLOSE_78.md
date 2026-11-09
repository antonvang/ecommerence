# PARTIAL_CLOSE_78: delvise lukninger, klassifikation af poster og afslutning af datakilder (direktørordre 78)

Skrevet 2026-11-09 kl. 23:53 lokal (22:53 UTC). **Ingen deploy, ingen manuel lukning, stopreglen er uændret. Ingen lås,
statusændring eller ledger-række. Ingen ændring af eksisterende filer.**

Mærker: **[F]** = fakta fra kode, git eller lab.db. **[V]** = vurdering. Fra lab.db er læst skema, `COUNT(*)`, `MIN(ts)` og
`MAX(ts)` pr. konto (`mode=ro`, `query_only`), senest 2026-11-09 22:50 UTC. Ingen beløb, ingen equity-værdier, ingen
udfaldstal, ingen payload.

Nye filer: denne note, `research/tools/partial_close.py` (ren klassifikation, kun `math`) og
`tests/test_partial_close_78.py`.

Ordre 78 afløser to punkter i `NETWORK_REPLAN_76.md`: en kodeændring før 12/11 er ikke tilladt (ingen deploy før 20/11),
og valget mellem to former for pm_lp-afslutning er truffet (afsnit D).

## A. De seks konti, dokumenteret på forhånd

**Stopreglens udfald er ikke evalueret og forudsiges ikke.** Tabellen viser kun, hvornår reglen første gang kan vurderes.

Regel [F]: `lab/lane.py` `_retire_reason`, `source`: funding − gebyrer ≤ 0, tidligst `SOURCE_DAYS` = 14 dage efter start.
Gælder ikke carry90 og ikke STRAKS/PAR-BOG. Kontiene har også reglerne `family`, `expired`, `loss`, `paused` og `edge`.

| Konto | Type | Start (`sim_equity` min, UTC) | Første mulige `source`-stop (UTC) | Sidst registrerede mærke | Sidste regulære mærke | Spot-/perp-fyld (antal) |
|---|---|---|---|---|---|---|
| `LANE_53058593e8` | carry_floor | 2026-10-29 04:47:29 | **2026-11-12 04:47** | 2026-11-08 06:40:31 | 2026-11-06 20:00:00 | 3 / 4 |
| `LANE_c2d8a7505e` | carry_floor | 2026-10-31 23:42:16 | 2026-11-14 23:42 | samme | samme | 2 / 2 |
| `LANE_2df94018bc` | carry_filter_weekly | 2026-11-02 23:09:50 | 2026-11-16 23:09 | samme | samme | 3 / 3 |
| `LANE_ce8964dccc` | carry_filter_weekly | 2026-11-03 08:02:20 | 2026-11-17 08:02 | samme | samme | 2 / 2 |
| `LANE_9f1dc841b2` | carry_filter | 2026-11-05 20:14:13 | 2026-11-19 20:14 | samme | samme | 12 / 8 |
| `LANE_ec1b0457b8` | carry_filter | 2026-11-05 20:25:41 | 2026-11-19 20:25 | samme | samme | 8 / 6 |

Den præcise stoptid er `lane.started`-tiden + 14 d; `sim_equity` min er en nær tilnærmelse.

- **Mærket [F]:** 11-08 06:40:31 er taget inden for en DNS-åbning på ca. 6 minutter før ordre 76 (`STALE_EQUITY_59C.md`).
  Det er en almindelig `sim_equity`-række. Sidste mærke før hullet er 11-06 20:00:00. Begge tider bevares.
- **Afhængighed [F]:** `lab/lane.py` `legs()`: perp fra fapi og `<MØNT>USDT.SPOT` fra `data-api.binance.vision`.
  Værten er permanent utilgængelig.
- **Risiko for delvis lukning [F]:** hvis en konto stoppes (af en hvilken som helst regel), lukker
  `paper_runner.close_ledger` ben for ben. Perp-benet kan lukkes via fapi, spot-benet får `book unavailable` og står åbent.
  Testet i afsnit C. Stoppet sker uændret, og det kan ske før 20/11.

## B. Klassifikation af posterne

Alle rå poster bevares. Intet omskrives, slettes eller erklæres ugyldigt. Klasserne står i `research/tools/partial_close.py`.

| Klasse | Hvad det er | Indgår i aktuel P&L? |
|---|---|---|
| `VERIFIED_HISTORICAL_MARK` | `sim_equity` til og med sidste verificerede mærke | Historik, med tidsstempel |
| `MARK_AFTER_LAST_VERIFIED` | `sim_equity` efter skæringen | Nej, før det er afgjort særskilt |
| `FUNDING_UP_TO_LAST_VERIFIED_MARK` | Funding til og med mærket | Indgår i mærket |
| `SIMULATED_FUNDING_AFTER_LAST_MARK` | Funding efter mærket. **Kan være korrekt registreret simuleret hændelse** (perp-data virker) | Nej: kan ikke kombineres med en spotpris |
| `SIMULATED_FILL_UP_TO_LAST_VERIFIED_MARK` | Fyld til og med mærket | Indgår i mærket |
| `SIMULATED_FILL_AFTER_LAST_MARK` | Fyld efter mærket, fx lukkefyld | Nej: vises særskilt |
| `MISSING_SPOT_MARK` | Timer uden mærke, fordi et åbent spot-ben ikke kan prises. Et fravær, ikke en række | — |
| `PARTIAL_CLOSE` / `CLOSE_INCOMPLETE` | Kontostatus (afsnit C) | Nej |
| `EQUITY_NOT_COMPUTABLE` | Aktuel equity, når et åbent ben mangler et friskt mærke (2 t, som `net_report`). Værdien er `None` | Nej: **ikke aktuel P&L** |

Skæring for de ni STALE-konti: 2026-11-08 06:40:31 UTC [V]. [F] Pr. 2026-11-09 er der 0 fyld efter skæringen på de ni, og
funding-rækker efter skæringen findes på alle (5–20 pr. konto, `NETWORK_REPLAN_76.md` afsnit 3).

Poster efter 8/11 er **ikke** ugyldige som sådan. De klassificeres.

## C. Partial-close-fejlmodel

**Definitioner (`classify_close`, fail-closed):**

- `CLOSE_SUCCESS`: alle ben, der var åbne, er flade; lukkefyldene forklarer hele positionen; et equity-mærke ligger på eller efter sidste lukkefyld. Den eneste status, der betyder "lukket".
- `PARTIAL_CLOSE`: mindst ét ben er lukket eller reduceret, og mindst ét ben er stadig åbent.
- `CLOSE_INCOMPLETE`: alt andet ved en lukning: intet ben er reduceret, benene er flade uden slutmærke, eller tallene passer ikke (fortegnsskift, vokset position, fyld uden forklaring, ugyldigt input).
- `NO_POSITION`: intet var åbent.

**Isoleret test [F]:** den rigtige `lab.paper_runner.close_ledger`, midlertidig DB (`lab.db.DB`), carry90-konto åbnet af den rigtige `lane.run_one`, stoppet syntetisk med `lane.retire`, bøger mocket i `get`. Ingen ændring af `paper_runner`.

| Scenarie | Positioner bagefter | Klasse | Bemærkning |
|---|---|---|---|
| Begge ben kan lukkes | ingen | `CLOSE_SUCCESS` | Slutmærke skrives |
| Spot-ben utilgængeligt | spot åben | `PARTIAL_CLOSE` | `status: "closing"`, intet mærke, `paper.mark_failed` én gang |
| Perp-ben utilgængeligt | perp åben | `PARTIAL_CLOSE` | |
| Begge utilgængelige | begge åbne | `CLOSE_INCOMPLETE` | 0 fyld |
| Tynd bog | ben reduceret | `PARTIAL_CLOSE` | IOC-rest; også hvis begge er tynde |
| Gentaget forsøg | uændret, senere flad | `PARTIAL_CLOSE` → `CLOSE_SUCCESS` | Samme time og næste time: lukket ben lukkes ikke igen |
| Genstart mellem lukninger | som før | `PARTIAL_CLOSE` → `CLOSE_SUCCESS` | Ny DB-forbindelse; tilstand kun fra databasen, ingen dublet |
| Flad uden mærke efter sidste fyld | ingen | `CLOSE_INCOMPLETE` | Aldrig success |

Fund [F]:

- `close_ledger` returnerer altid `status: "closing"`. Ordet siger intet om, hvor langt lukningen er nået.
- Efter en delvis lukning står kontoen i `closing_ledgers`, og forsøget gentages hver time. Med en permanent utilgængelig vært slutter det ikke af sig selv.
- Efter en delvis lukning har kontoen ikke længere et afdækket par; `equity_view` giver `None`.
- `test_success_only_when_every_leg_is_flat_accounted_for_and_marked` gennemløber kombinationer af ben, fyld og mærke. Success kommer kun i det ene tilfælde, hvor alt holder. En mutation, der fjernede `PARTIAL_CLOSE`- og `CLOSE_INCOMPLETE`-grenene, gav 10 fejlende tests. Mutationen er rullet tilbage.

**Forslag til senere fejlhåndtering (ikke lavet; kræver dateret ændring, grøn suite og deploy tidligst efter 20/11):**

1. Læs alle ben i en lukning før første ordre. Mangler ét ben, sendes ingen ordre, og der skrives én `paper.close_blocked`-hændelse pr. episode.
2. Eller: behold lukning ben for ben, men skriv et eksplicit `paper.close_partial` med åbne ben.
3. Lad `close_ledger` returnere `classify_close`-status ved siden af `status`.
4. Vis `PARTIAL_CLOSE` og `CLOSE_INCOMPLETE` i `net_report` og dashboardet, adskilt fra `lane.retired`.

Valg 1 ændrer lukningsadfærd og skal behandles som en regelændring.

## D. PM_LP: proveniens for den manglende `PM_LP_FROZEN.md`

**Fakta [F]:**

| Hvad | Fund |
|---|---|
| `git log --all -- research/PM_LP_FROZEN.md` | Ingen commits. Filen har aldrig været i git |
| Produktion | `research/PM_LP_FROZEN.md` findes ikke (kun `ls`) |
| Forventet ifølge | `PM_LP_SPEC.md` §9 trin 5; `MISSION2_DECISION.md` (`0dd238b`: "Me (automatic) … run … dev and commit"); `LINUX_DRIFT.md` punkt F (`e775e1a`, `ede420e`, 10-19): kør `dev` 2026-10-31 ≥ 01:00 UTC på en kopi og commit filen samme dag, før nogen ser holdout-data |
| Procedurens spor | `~/pm_lp_runs/` og `~/pm_lp_devrun` findes ikke. Der er ingen commit, note eller INBOX-post om, at `dev` er kørt, i `git log` 10-30..11-01 eller i `git grep` over repoet (`research/data/` undtaget) |
| Kode | `research/pm_lp.py` `holdout` nægter uden committet fil (`frozen()`), `dev` kræver dato efter D0+13 |
| Samme dag | 10-31 var en dag med netudfald (`PM_LP_D1_STATUS_72.md`). Om det hænger sammen, er ikke dokumenteret |

**Hvorfor den mangler:** ikke dokumenteret. Det kan konstateres, at det planlagte trin ikke har efterladt noget spor. Årsagen skal ikke gættes.

**Ikke afklaret:** om `pm_lp_v1_dev.json` findes under `data/research/results/` (uden for rammen; ikke åbnet). Filen rekonstrueres ikke, `n_req` beregnes ikke, og `dev` køres ikke.

**Udkast til administrativ afslutning (ikke registreret; koordinator/direktør afgør):**

> **pm_lp_v1: `TERMINATED_DATA_QUALITY_FAILURE / HOLDOUT_NOT_EVALUATED`.** Forsøget afsluttes administrativt, fordi datakravet D1 er uopnåeligt (`PM_LP_D1_STATUS_72.md`) og de nødvendige værter er permanent utilgængelige (ordre 76). Holdout er ikke evalueret og vil ikke blive det. Der er ingen alternativ evaluering. **Forsøget er hverken statistisk forkastet eller valideret.** Der kan ikke udledes noget om en positiv eller negativ handelsfordel. `PM_LP_FROZEN.md` blev aldrig skrevet og rekonstrueres ikke. Data, cutoffs, tærskler og evaluator bevares uændret. Ingen pilot.

Den afløser `PASS_UNREACHABLE / PENDING_FORMAL_CLOSE`, når den registreres. `G12_PMLP` og collectoren berøres ikke af denne note. Hvordan collectoren skal behandles, er uafklaret.

## E. Oversigt og milepæle

| Punkt | Status | Begrundelse |
|---|---|---|
| COIN-M (A_n6_X3, F3, `G09_COINM_1128`, dbasis) | `BLOCKED_DATA_SOURCE_UNAVAILABLE` | Kun tilladt fra data.binance.vision [F] |
| U1F (17i) | `BLOCKED_DATA_SOURCE_UNAVAILABLE` | Udfald kræver Binance' månedsarkiver [F]; kataloget alene er ikke nok |
| M1F (17j) | `BLOCKED_DATA_SOURCE_UNAVAILABLE` | Samme [F]. H5F og H5X berøres ikke |
| HFC-1 | 2 eksisterende kohorter (11-04, 11-05), 19 manglende (11-06..11-24) | Ingen erstatning, ingen efterdannelse [F] |
| F2 (HAR-RV) | Kræver selvstændig gatekontrol | Cachen alene er ikke nok: `G01_HIST_1114`, `G17_F2_CALIBRATION`, `G16_F2_WINDOW`, `G15_OWNER_SIGNATURE`, D3/D4/D5, AMB-02..11, identitetsmanifest før filer åbnes. Filnavne er talt; indholdet er ikke kontrolleret [F] |
| De ni STALE-konti | `DATA_SOURCE_UNAVAILABLE` foreslået; klassifikation efter afsnit B | Ingen deploy før 20/11 |

Bemærk: `research/F2_PLAN.md` handler om familien `dbasis` (COIN-M), ikke F2 HAR-RV. Dens trin 0 (`holdout`) og 1 (HEAD mod COIN-M) falder bort.

**Milepæle:**

| Dato (UTC) | Punkt | Konsekvens |
|---|---|---|
| 12/11 ≥ 04:47 | `source` kan første gang vurderes for `LANE_53058593e8` | Kører uændret. Sker et stop, klassificeres resultatet bagefter; det fremstilles ikke som fuldstændigt |
| 12/11 ≥ 17:11:51 | STRAKS 7 d | Uændret; kun perp |
| 14/11 | Gate-status | Kan køre; COIN-M, U1F og M1F læses med status ovenfor |
| 14–19/11 | `source` for de øvrige fem | Som 12/11 |
| 19/11 ≥ 00:35 og ≥ 20:51:09 | HFC-1 14 d (11-04); PAR-BOG | Uændret |
| 20/11 ≥ 00:35 | HFC-1 14 d (11-05) | Uændret |
| 20/11 ≥ 09:55:07 | S1 | Uændret |
| 20/11 og frem | Tidligste deploy af fejlhåndtering | Kræver dateret ændring |
| 27–28/11 | pm_lp-hale, holdout | Ingen `holdout`-kørsel; administrativ afslutning |
| 28/11 | COIN-M, familie-netværk | Kan ikke gennemføres |
| 28/11 og 12-09 | HFC-1-opsummeringer | Kun 2 kohorter; ingen erstatning |

## Uafklaret

1. Om en af de seks konti faktisk stoppes. Bevidst ikke vurderet.
2. Om `dev` for pm_lp_v1 er kørt, og om resultatfilen findes.
3. Hvem der registrerer status for pm_lp_v1, COIN-M, U1F og M1F, og hvornår.
4. Collectoren og detektorerne, der stadig kalder de blokerede værter (G12 gælder).
5. De aktuelle åbne ben pr. konto. Ikke læst (kræver mængder). En senere read-only rapport kan bruge `sim_orders` med `|close|` i `order_id` og fylde `classify_close`.
6. Om `MARK_AFTER_LAST_VERIFIED` skal behandles særskilt, hvis mærkning sker, fordi en vært svarer.
