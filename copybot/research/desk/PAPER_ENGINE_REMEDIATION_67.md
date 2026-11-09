# Papirmotoren: udbedring (direktørordre 67)

Dato: 2026-11-09 (UTC). Gren `claude/66b-engine-audit`, kun lokalt: ikke pushet, ikke deployet. Alt nyt ligger bag
flag, der som standard er **slået fra**. Med standardflagene opfører aktive bøger sig som før.
`lab/straks.py` (`7a110f1f…`), `lab/pairs.py` (`5c9b60a4…`) og `research/tools/net_report.py` (`e8cac57c…`) er byte for
byte uændrede. Ingen pin, ingen protokol og ingen eksisterende ledger-række er ændret. Grundlaget er
`PAPER_ENGINE_QUALITY_REPORT.md` (ordre 66B). Tests: `tests/test_lab_engine_remediation_67.py` (20 tests) og
`tests/test_lab_engine_audit_66b.py`. Analyserne af den rigtige DB er skrivebeskyttede (`mode=ro`,
`query_only`, `unshare -rn`); de gav kun optællinger og blev kørt ca. 14:40–15:10 UTC. Databasen er levende, så
tallene vokser en smule mellem kørslerne.

**Rettelse til 66B:** `sim_exec.book_age_s` er ikke 0. Den ligger i intervallet (−1, 0) i alle 3918 rækker, fordi
den regnes som `int(now) − now` (passets eget ur). Tallet siger altså intet om bogens alder.

## Status pr. fund

| # | Fund | Bekræftet | Implementeret i dev | Kræver protokolændring | Kan påvirke eksisterende resultater | Test der stadig fejler (xfail) |
|---|---|---|---|---|---|---|
| 5 | Bogens alder (P0-A) | ja | `Book.observed` (vægur ved læsning), `risk.book_age`, `BOOK_AGE_MODE` = off/measure/guard; standard off | ja for guard (godkendelse); measure ændrer kun `sim_exec` | nej (se analysen) | `test_confirmed_stop_book_and_fill_times_are_the_pass_clock_not_the_read_time` (standard off) |
| 3 | Manglende UTC-dag (P0-B) | ja | `lane.daily_observation`, `DAILY_RETURNS_MODE` = legacy/strict; standard legacy | **ja**, udkast nedenfor | z-input for 6 aktive lane-konti; ingen regel skifter i dag | `test_confirmed_stop_a_missing_utc_day_is_merged_into_one_daily_return` |
| 6 | Funding går i stå i det stille (P0-C) | ja | `FUNDING_MISSING_MODE` = legacy/fail_closed; hændelser `paper.funding_missing`/`paper.funding_unavailable` og statusfelt `funding_status`; standard legacy | aktivering kræver godkendelse | nej (0 tilfælde) | `test_confirmed_stop_a_missing_middle_bar_stalls_funding_silently` |
| 4 | Tavse mærkefejl i STRAKS og PAR (P1) | ja | patch `research/desk/patches/66_straks_pairs_mark_guard.diff`, testet på midlertidige kopier | nej, men filerne er frosne til 20/11 | nej (bøgerne er byte-identiske i testen) | `test_confirmed_stop_straks_mark_failure_is_silent` |
| 7 | Basis ved fortegnsskift (P1) | ja | reference `research/tools/basis_ref.py` (ny, ikke kaldt af rapporten) | ny pin af net_report, hvis den skal skifte | 0 tal i net_report i dag | `test_confirmed_stop_net_report_keeps_the_old_basis_through_a_flip` |
| 10 | Mærkeproveniens (P2) | skemafakta | design og prototype `lab/markprov.py` (ikke koblet på) | ja (ny tabel) | nej | – |
| 11 | Dagsgrænse 00:00:00 (P2) | ja, karakteriseret | test `DayBoundary` | nej | 0 rækker | – |
| 12 | Sen funding (P2) | kortlagt | – | nej | nej (0 mangler) | – |

Uændret fra 66B: rettelserne af `close_ledger`, `reportcheck` og `on_trade` (commit `2968ad8`).

## P0-A: bogens alder

**Implementering.** `fetch_book` sætter nu `Book.observed`, som er vægurets tid lige efter læsningen.
`Book.ts` er stadig passets ur, og `observed` indgår ikke i lighedssammenligninger. Bogens alder regnes som
`risk.book_age(book, exec_wall) = exec_wall − observed`, hvor `exec_wall` er vægurets tid, når ordren afgives.
Flaget `lab/risk.py BOOK_AGE_MODE` har tre værdier:

- `off` (standard): som i dag. Tjekket `data_max_age_s` bruger `now − book.ts`, og `sim_exec` er uændret.
- `measure`: `sim_exec` får desuden `book_observed_wall`, `exec_wall` og `book_age_exec_s`. Ordrer, fyld, mærker og
  funding er byte-identiske; testen sammenligner hash-kæderne.
- `guard`: indgangskontrollen bruger den reelle alder. En bog, der er mere end 60 s gammel ved udførelsen, giver BLOCK
  `data_stale` og `paper.refused`. Ordren gemmes ikke, og samme ordre-id prøves igen i næste pas i samme time. En bog
  uden `observed` falder tilbage til den gamle regel.

**Sådan ville guard ændre adfærden.** Lane, carry, HL, FWD/SHADOW/E og lukkevejen læser bogen lige før ordren. Der er
alderen én HTTP-læsning (sekunder), så de blokeres praktisk talt aldrig. Kun STRAKS og PAR-BOG kan genbruge en bog,
som et andet regnskab læste tidligere i samme pas (`books`-cachen). For dem kan en ordre blive udskudt til næste pas.
Mærker berøres ikke af guard. Ordre- og fyldtid forbliver passets ur, ellers ville de bogførte tidsstempler ændre sig.

**Analyse af den rigtige DB.** Dokumenteret og estimeret er holdt adskilt.

*Dokumenteret:*
- 3918 rækker i `sim_exec`. Alle har en `paper.order`-hændelse med vægur-tid. Skævheden (vægur − passets ur) er
  p50 8 s, p90 28 s, maks. 168 s.
- 5910 ordrer, heraf 35 med en skævhed over 60 s: 14 lane, 19 FWD og 2 PAR-BOG, alle fyldt, i alt 5833,66 USD.
  25 af de 35 har en `sim_exec`-række (lane 4, FWD 19, pairs 2).
- 3836 rækker kommer fra vejen, hvor bogen læses lige før ordren. 33 af de 35 ligger her. For dem er skævheden tid
  inde i passet, ikke bogens alder: bogen blev læst sekunder før ordren.
- 82 rækker kan have brugt cachen (STRAKS 74, PAR 8). I 37 af dem har en tidligere ordre i samme pas og på samme
  instrument nøjagtig samme bog-fingeraftryk (spread, dybde og niveauer), så genbruget er sikkert. Den nedre grænse for
  alderen er i disse tilfælde 0–2 s. **0 rækker kan dokumenteres som forældede (over 60 s).**

*Estimeret:*
- De 2 PAR-ordrer over 60 s har ingen dokumenteret kilde til bogen. Alderen ligger mellem 0 s og skævheden
  (61–168 s); vi kan ikke afgøre, om de var forældede.
- Effekten på resultaterne kan ikke måles, fordi den friske bog ved udførelsen aldrig blev gemt. I ingen af tilfældene
  findes en senere frisk læsning i samme pas at sammenligne med (0 rækker). Det rimelige skøn er derfor ingen målbar
  effekt; den øvre grænse er prisbevægelsen over højst 168 s på 2 ordrer.

Analysen er ikke brugt til at justere nogen strategi.

## P0-B: en manglende UTC-dag er ugyldig

**Implementering.** `lane.daily_observation` kræver, at de daglige lukninger (det sidste timemærke i hver afsluttede
UTC-dag) ligger på to dage i træk. Et spænd over en manglende dag registreres som `INVALID` med de manglende datoer og
holdes uden for beregningen. Det omregnes aldrig. Dækningen er gyldige dagpar delt med kalenderdagpar. Med
`DAILY_RETURNS_MODE = "strict"` returnerer `lane.stats` en `observation` (status, dækning, ugyldige spænd). Hvis
dækningen er under `COVERAGE_MIN` (udkast: 0,8), er status `INCONCLUSIVE`, og `z = None`, så hverken 'edge' eller
'promising' afgør noget. Standarden `legacy` er uændret.

**Aktive konti** (skrivebeskyttet, DB-stand ca. 14:40 UTC; alle 9 mangler 2026-11-07):

| Konto | Kilde | Dage legacy→strict | z legacy→strict | Dækning | Status | z-regler gælder |
|---|---|---|---|---|---|---|
| LANE_53058593e8 | lane carry_floor | 9→8 | −1,12→−1,05 | 0,80 | OK | ja |
| LANE_c2d8a7505e | lane carry_floor | 7→6 | −0,80→None | 0,75 | INCONCLUSIVE | ja |
| LANE_2df94018bc | lane carry_filter_weekly | 5→4 | −1,09→None | 0,67 | INCONCLUSIVE | ja |
| LANE_ce8964dccc | lane carry_filter_weekly | 4→3 | −0,86→None | 0,60 | INCONCLUSIVE | ja |
| LANE_9f1dc841b2 | lane carry_filter | 2→1 | −1,13→None | 0,33 | INCONCLUSIVE | ja |
| LANE_ec1b0457b8 | lane carry_filter | 2→1 | −1,48→None | 0,33 | INCONCLUSIVE | ja |
| LANE_1c07df98c7, LANE_65e2a1f395, LANE_bc12a61803 | carry90 | 2→1 | None | 0,33 | INCONCLUSIVE | nej (carry90 har ingen z-regel) |

Ingen regel skifter udfald i dag: 'edge' kræver z ≤ −3 efter 7 dage, og 'promising' kræver 30 dage. Med én manglende
dag ligger to dagpar uden for beregningen, så kontoen er `INCONCLUSIVE`, indtil den har mindst 10 kalenderdagpar. For
de 5 INCONCLUSIVE lane-konti ville 'edge' og 'promising' altså være sat ud af kraft i nogle dage. Kun lane-konti
(kilde lane) har z-regler. `command.edge` (dashboardet, afgør intet) har samme mønster og er ikke ændret.

**Udkast til ændring (ikke dateret, ikke aktiv):**

> *Amendment [nr.], [dato]: Daglige afkast i lane-reglerne (11 'edge' og 'promising').* Et dagligt afkast er
> forholdet mellem det sidste timemærke på to på hinanden følgende afsluttede UTC-dage. Mangler en dag ethvert
> timemærke, er spændet over den ugyldigt: det er utilstrækkeligt observeret, indgår ikke i middelværdien, i n eller i
> z, og det omregnes aldrig (ingen skalering eller fordeling over dagene). Dækningen er antallet af gyldige dagpar
> delt med antallet af kalenderdagpar fra første til sidste mærkede dag. Er dækningen under 0,8, er kontoens
> dagbaserede status INCONCLUSIVE: 'edge' og 'promising' afgør intet, og alle andre stopregler gælder uændret. De
> ugyldige spænd og dækningen vises med kontoens statistik. Gælder fra [dato og tid UTC] for alle aktive og nye
> lane-konti; allerede skrevne `lane.retired`- og `lane.promising`-hændelser røres ikke.

## P0-C: manglende funding giver fejl, ikke stilhed

**Implementering.** `lab/paper.py FUNDING_MISSING_MODE` har to værdier:

- `legacy` (standard): bogføringen er som før.
- `fail_closed`: en afregning, hvor positionen var åben, og hvor 1 t-baren mangler, mens senere barer findes, er en
  synlig fejl. Den giver én `paper.funding_missing` pr. konto, instrument og afregning, og passets resultat får
  `funding_status = "ERROR"` med detaljer.

I begge tilstande bogføres intet fra den afregning og frem for det instrument: ingen afregning springes over, opfindes
eller estimeres. Bøgerne forbliver i balance. Ventes der kun på den nyeste bar, er status `WAITING` (ingen fejl). Kan
funding-data ikke hentes i pause- eller lukkevejen, skrives `paper.funding_unavailable` højst én gang pr. konto og
klokketime, og status bliver `ERROR`. I `legacy` kendes tilstanden kun i hukommelsen (`eng.funding_status`), og
resultatet får ingen nye felter. Aktivering kræver en særskilt godkendelse. Rest-risiko: en manglende sats midt i
funding-serien kan ikke opdages uden kendskab til intervallet.

## P1

**#4 STRAKS/PAR.** `research/desk/patches/66_straks_pairs_mark_guard.diff` erstatter den tavse `try/except` om
`_mark_hourly` med 59-D's `mark_guarded`. Returværdien er uændret. Testen anvender patchen strengt (konteksten skal passe
præcist) på midlertidige kopier og kører dem i stedet for modulerne:

- STRAKS: én `paper.mark_failed` og én `paper.mark_recovered`; ordrer, fyld, mærker og funding er byte-identiske med den
  frosne version.
- PAR: én `paper.mark_failed` (klasse dns), hvor den frosne version intet skriver.

Kan anvendes efter 20/11 med en ny pin af `STRAKS_CODE`/`PAIRS_CODE`.

**#7 basis.** `research/tools/basis_ref.py` er en referenceimplementering: basis nulstilles ved fortegnsskift, og
afslutningen af den gamle tur tæller som én tur. Den er lig motoren og lig net_report, når der ikke sker noget
fortegnsskift.

| Syntetisk forløb | net_report (pinnet) | basis_ref |
|---|---|---|
| køb 1@100, sælg 2@110, køb 1@100 | realiseret 10, 1 tur, retning long | 20, 2 ture, short (= motoren) |
| køb 2@100, sælg 3@90, sælg 1@95, køb 1@80 | realiseret −2,5, åben basis 97,5, long | −7,5, åben basis 92,5, short (= motoren) |

På den rigtige DB afviger kun 2 instrumenter, og begge ligger i FWD-konti, som net_report ikke medtager:

- `FWD_E_daily_reversal_p1` LINKUSDT: realiseret 17,48 → 125,37; ture 2 → 3.
- `FWD_E_xs_momentum_p2` DOTUSDT: realiseret 315,43 → 385,51; ture 1 → 2; retning long → short.

## P2

**#10 mærkeproveniens (design, ingen skemaændring).** En fremtidig append-only tabel med hash-kæde som de øvrige sim_*:
`sim_marks(exp_id, ts, equity_id, instrument, qty, mark_px, bid, ask, book_ts, book_observed, source)`. Der skrives én
række pr. åben position i samme transaktion som `sim_equity`-rækken. To krav skal holde: kontanter + Σ qty·mark =
equity, og Σ |qty|·mark = eksponering. Prototypen `lab/markprov.py` (`rows`, `check`) bygger og kontrollerer sådanne
rækker i hukommelsen og er ikke koblet på motoren. Testen viser, at et forkert mærke afsløres på equity, eksponering og
mid.

**#11 dagsgrænse.** Med syntetiske rækker stemplet præcis 00:00:00 UTC (testen `DayBoundary`) tæller net_report
(`ts <= cutoff`) mærket og funding med i den afsluttede dag. Lane-rapporten, reportcheck og `straks_report`
(`ts < slut`) lader dem gå til næste dag. I eksemplet viser net_report værdien 10 050 med funding −0,10, mens de tre
andre viser 10 000 med funding 0. Den rigtige DB har 0 sådanne rækker (sim_equity, sim_fills og sim_funding).
STRAKS-cutoff ligger kl. 17:01:51 og PAR-cutoff kl. 20:41:09, så en midnat er aldrig skæringen dér.

**#12 de 98 sene funding-rækker (kun læst, intet ændret).**

| Antal | Årsag | Afregning (UTC) |
|---|---|---|
| 45 | runner/vært nede (ingen konto skrev noget i mellemtiden) | 2026-10-19 08:00 (FWD 39, SHADOW 6) |
| 25 | konto på pause (data_fetch), intet mærke i mellemtiden: data utilgængelige | 10-30 20:00, 10-31 08:00, 10-31 12:00 |
| 16 | konto på pause (max_drawdown), intet mærke i mellemtiden: data utilgængelige | 10-31 08:00 (FWD) |
| 12 | konto på pause (data_fetch), mærket i mellemtiden, men funding-data hentedes ikke | 10-31 08:00 (FWD) |

Alle 98 blev bogført senere: maks. 6,4 t forsinket, 0 mangler, satserne er lig `funding_settled/1`. Netværksudfaldet
30–31/10 forklarer 53, og værtsstoppet 19/10 forklarer 45. I `fail_closed` ville de 53 have givet
`paper.funding_unavailable`.

## Milepæle under de oprindelige protokoller

Ingen af ændringerne er aktive i produktionen, og ingen pinnet fil er ændret. Derfor:

- **STRAKS 12/11:** kan vurderes som planlagt. `straks.py` og `net_report.py` er uændrede; 0 fortegnsskift og 0 rækker
  ved midnat. Af STRAKS' 74 rækker, der kan have brugt cachen, har ingen en dokumenteret alder over 2 s.
- **HFC-1 14 d:** kan vurderes som planlagt. Værktøjerne læser ingen sim_*-tabeller.
- **PAR-BOG 19/11:** kan vurderes som planlagt. Forbehold: 2 PAR-ordrer har en udokumenteret bogalder på højst
  61–168 s; det bør nævnes som en datakvalitetsnote.
- **S1 20/11:** kan vurderes som planlagt. Værktøjet læser ingen sim_*-tabeller.

Følgen af den manglende dag 2026-11-07 (fund 3) rammer kun lane-kontiernes z-regler, ikke milepælsværktøjerne.

## Flag (alle slået fra som standard)

| Flag | Fil | Standard | Aktivering kræver |
|---|---|---|---|
| `BOOK_AGE_MODE` | `lab/risk.py` | `off` | godkendelse (`measure`); godkendelse og pausepolitik (`guard`) |
| `DAILY_RETURNS_MODE`, `COVERAGE_MIN` | `lab/lane.py` | `legacy`, 0,8 | dateret ændring (udkast ovenfor) |
| `FUNDING_MISSING_MODE` | `lab/paper.py` | `legacy` | særskilt godkendelse |
