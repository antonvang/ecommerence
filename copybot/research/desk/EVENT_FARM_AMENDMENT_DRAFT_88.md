# Event farm: ændringsforslag til PROTOCOL_V3 (UDKAST, IKKE LÅST)

**ÆNDRINGSFORSLAG, IKKE EN ÆNDRING.** Skrevet 2026-11-11 kl. 17:47 lokal tid (16:47 UTC) af Claude efter
direktørordre 88 P0/P1 ("DESIGN GO, DATA ACCESS BLOCKED"). `research/PROTOCOL_V3.md` og
`research/desk/GATE_MATRIX.json` er ikke ændret. Forslaget låser, godkender og åbner intet. Ingen markedsdata er læst.
Den foreslåede GATE_MATRIX-post står i `research/desk/EVENT_FARM_GATE_ENTRY_DRAFT_88.json`. Planen står i
`research/desk/EVENT_FARM_PLAN_88.md`, og P0-tjeklisten i `research/desk/EVENT_FARM_GATES_85.md`.

## 1. Gates efter deres gældende definitioner

| Gate | Gældende definition | Status nu | Hvad åbner den for event farm |
|---|---|---|---|
| **G01_HIST_1114** | Ingen historiske markedsdata før 2026-11-14 00:00 UTC, også læsning af filer, der allerede ligger i cachen. "The date alone opens nothing" (`GATE_MATRIX.json`). Studier: A_n6, B_n4, F2, C1. | **CLOSED** (OPENS_AT 2026-11-14) | Datoen og et studie, der står på listen med sine flag. Event farm står ikke på listen, så adgangen er BLOCKED, også efter 14/11, indtil posten er indført. |
| **G02_EXPLORE0_ONLY** | Kun explore0 = 2020-03-01..2021-12-31. Der filtreres på filnavn før åbning, og rækker filtreres ved indlæsning. Det er en begrænsning, ikke en åbning. | OPEN (begrænsning) | Overholdes ved design: alle 44 filer ligger i explore0. Event farm skal tilføjes studielisten. |
| **D5** (`OWNER_DECISIONS_NOV14.md` række D5, `OWNER_KEY_GUIDE_D5.md`) | Ejernøglen laves uden for lab-pc'en, fingeraftrykket forankres uafhængigt (fra telefonen til direktøren), og ejeren underskriver. Flag: `owner_key_registered`. | **PENDING_INDEPENDENT_ANCHOR** (`research/owner/D5_REGISTRATION.md` linje 14; INBOX linje 93: "ingen godkendelse fra chatbeskeder") | Ingen verificeret ejergodkendelse er mulig, før D5 er forankret. |
| **G15_OWNER_SIGNATURE** | En ny skabelon eller aktivering kræver en verificeret ejerunderskrift. Historiske godkendelser er UNVERIFIED_ORIGIN og genbruges aldrig. Flag: `owner_key_registered`. | **CLOSED** | Forslaget kræver G15 for event farm (fail-closed). En beskrivende explore0-kørsel er et nyt studie, og ingen tekst undtager den. Direktøren kan afgøre andet, men kun skriftligt og dateret. |

**Chatbeslutninger:**
- Ejerens "Ja" i chatten (`EVENT_FARM.md`, sidste afsnit) er UNVERIFIED_ORIGIN.
- Direktørens "DESIGN GO" (ordre 88) godkender designarbejdet, ikke dataadgang.

Ingen af dem sætter et flag, og ingen erstatter en verificeret ejergodkendelse
(`GATE_STATUS_PREVIEW_2026-11-14.md` linje 7). G28 gælder: assistenten underskriver ikke, låser ikke og bruger aldrig
ejerens nøgle.

**Dom: DATA ACCESS BLOCKED.**
- G01 er lukket til 14/11.
- Event farm står ikke i GATE_MATRIX.
- D5 er ikke forankret, så G15 kan ikke bestås.

## 2. Genbrug af R3's 44 filer (P1)

**Den oprindelige godkendelses rækkevidde.**
- Ændring 24 punkt 2 godkendte hentning af præcis 44 filer (`BTCUSDT`/`ETHUSDT` 1m, 2020-03..2021-12) til R3 (metode
  m24) med "ingen andre symboler, måneder eller kilder".
- Ændring 24a (brugerens udtrykkelige ja 2026-10-26) var en undtagelse for *hentningen* før 14/11 og gjaldt "kun
  ændring 24's 44 filer".
- Punkt 5 i 24a binder R3 til én kørsel, og nøglen `macro_release|minute_drift_60m|m24` screenes aldrig igen.
- Ingen tekst tillader eller forbyder, at de cachede filer læses af et andet studie. Godkendelsen dækker altså
  **ikke** event farm. Genbrug kræver sin egen daterede ændring og gate (punkt 3 herunder).

**Hvorfor genbrug kan forsvares** (efter godkendelse):
- ingen ny forespørgsel, ingen ny vært og ingen ny kilde;
- filerne ligger i explore0, som altid er udforskning;
- identiteten er kontrolleret én gang (`R3_m24_verify.json`: sha256 = log, CRC ok, 0 manglende minutter) og kan
  genprøves uden netværk;
- event farm stiller et andet spørgsmål (mønstertælling, ikke minutdrift efter makrotal) og genbruger ikke R3's nøgle,
  regel eller resultat.

**Tidligere eksponering.**
- R3_m24 har læst alle 966.240 minutter pr. symbol i én screening 2026-10-27. Resultatet var SCREEN_FAIL: 58 hændelser
  i 57 klynger, gennemsnit +0,014 %, p 0,918.
- R3 beregnede kun reaktioner omkring makrotidspunkter. Der er ikke set mønster-, frekvens- eller setupstatistik på
  filerne.
- Filerne er dog åbnet og analyseret af lab'et, og BTC/ETH i 2020–21 er velkendte markedsforløb. Data er derfor
  **tidligere eksponeret forskning**, ikke friske.

**Overlap med reversal- og trendforsøg** (`register_snapshots/SNAPSHOT_v1.json`, `EVIDENCE_REPORT_75.md`):
- sweep → MSS er en vending efter et likviditetsgreb. Den er beslægtet med `liquidation_cascade_reversal`:
  - `MOVESCREEN_m21c`, 4σ-bevægelser på explore0-1h, SCREEN_FAIL;
  - `E_daily_reversal_p1`, FAIL;
  - `L21_m2_liquidation_reversal`, FAIL.
- BOS er et trendbrud. Det er beslægtet med `cross_sectional_momentum` (`L03_sol_trend_hourly` FAIL, `L14_tsmom_v1`)
  og med `E_donchian_trend_p1/p2` (SUPPRESSED).
- Selve explore0-vinduet er brugt af banen (19.182 varianter) og m17/m21-screeningerne.

**Hvorfor resultatet ikke er et uafhængigt holdout:**
1. Filerne er læst før (R3).
2. explore0 er efter ændring 10 punkt 6 aldrig bevis.
3. Beslægtede hypoteser er testet i samme vindue.
4. Motorens definitioner er valgt ud fra videoens påstande og kun prøvet på en syntetisk null. De er ikke uafhængige
   af den forskning, de skal beskrive.
5. Der testes 315 ting samtidig.

Et resultat kan derfor kun være beskrivende. Det kan hverken bekræfte eller afkræfte en edge, og det kan ikke
bruges som valideringsvindue for nogen senere version.

## 3. Foreslået tekst til PROTOCOL_V3 (indsættes kun efter direktørens godkendelse, med dato og klokkeslæt den dag)

> **Ændring NN (dato kl. HH:MM lokal, før data og før driverkode køres på markedsdata): event farm — beskrivende
> ICT/SMC-mærkning på R3's cachede 1m-filer i explore0 (metode ef1)**
>
> **Beslutning:** direktørens skriftlige godkendelse [ordre og linje] og ejerens verificerede D5-underskrift
> [`.sig`-reference]. Et chat-ja er ikke grundlag. Udforskning, aldrig bevis. Ingen LÅS, alfa, papirbog eller
> aktivering.
>
> 1. **Formål:** kun beskrivende, efter `research/desk/EVENT_FARM_PLAN_88.md` (sha256 [indsættes]). De primære mål er
>    hændelsesfrekvens, setupfrekvens, known_ts-konsistens, statusandele og fill-usikkerhed. R er højst en sekundær
>    beskrivelse.
> 2. **Data:** kun de 44 filer fra ændring 24 (`BTCUSDT`/`ETHUSDT` 1m, 2020-03..2021-12). De læses på stedet og kun
>    til læsning fra lab'ets cache. Der filtreres på filnavn før åbning, og et identitetsmanifest sammenlignes med
>    `research/studies/R3_m24_verify.json` før parsing. Ved afvigelse er resultatet BLOCKED. Ingen hentning, intet
>    netværk, ingen anden kilde, aldrig 2022+, 2024 eller 2025+.
> 3. **Kode:** `research/tools/event_farm.py` @ f686c9a (sha256 `7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76`)
>    uændret. Driveren @ [commit, sha256] har grønne tests på syntetiske filer.
> 4. **Opløsninger:** 5m aggregeret fra 1m er primær. 1m og 15m er følsomhedsanalyser. Kun `bar_seconds` varierer.
> 5. **Tests:** 315 = 3 opløsninger × (12 varianter + standardkæden + 92 hændelse × horisont). De registreres samlet
>    som multiple-testing-eksponering i Register V2 under `EVENT_FARM_EXPLORE0_SETUPS` og `EVENT_FARM_EXPLORE0_EVENTS`.
> 6. **Null:** `event_farm.null_run(seed=83, …)` uændret, efter planens afsnit 8.
> 7. **Tidligere eksponering:** R3_m24 har læst filerne. Resultatet er ikke et uafhængigt holdout og bruges aldrig som
>    validering.
> 8. **Én kørsel:** resultatet committes som `research/studies/EVENT_FARM_EXPLORE0_<dato>.md/.json`, mærket
>    EXPLORATORY, uanset udfald. Parametre, varianter og mål ændres ikke efter resultatadgang.
> 9. **Stop:** efter planens afsnit 9. En kodefejl kræver en dateret afvigelsestekst før en ny kørsel.
> 10. **Aldrig:** ordrer, papirkonti, alfa, LÅS, 2024-holdout, 2025+, `train3`/`validation3`, pm_lp, deploy og
>     genstart.

## 4. Hvad der mangler, før data kan læses

1. Dato ≥ 2026-11-14 00:00 UTC.
2. Direktørens skriftlige godkendelse af teksten i afsnit 3. Direktøren afgør også, om G15/D5 kræves. Forslaget kræver
   det.
3. D5 forankret af ejeren selv (`OWNER_KEY_GUIDE_D5.md` afsnit 5) og en gyldig underskrift for event farm.
4. Ændringen committet i PROTOCOL_V3 og GATE_MATRIX-posten indført (af en godkendt commit, ikke af dette udkast).
5. Driveren skrevet og testet, og dens sha256 indsat i ændringen.
