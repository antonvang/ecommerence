# 14/11-parathed — F2/C1, A (n6), B (n4), HFC-1, STRAKS, PAR, S1, F3 (direktørordre 52 P1)

**Skrevet 2026-11-06 kl. 14:38 UTC (15:38 lokal). Intet er hentet, låst, signeret eller aktiveret.** Dokumentet
samler, hvad de låste tekster allerede siger. Det ændrer ingen protokol. Hvor teksterne er uklare eller strider mod
hinanden, står det som **AMBIGUITY** (afsnit 11). Uklarhederne er ikke løst her. Det er ejerens eller direktørens
afgørelse, i en ny dateret tekst før data.

Ledsagefiler: `research/desk/GATE_MATRIX.json` (alle gates til 28/11), `research/desk/DATA_CONTRACT_F2_C1.md`,
`research/desk/OWNER_DECISIONS_NOV14.md`, `research/tools/nov14_readiness.py` (syntetisk kontrol) og
`tests/test_research_nov14_readiness.py`.

Hvad der er læst til dette notat:
- Kun tekst og kode i repoet.
- Produktionsdatabasen er åbnet to gange med `mode=ro` og `PRAGMA query_only=ON`, kun til aggregerede tal fra
  rækker ≥ 2026-10-27: starttider for `lane.started` (straks, pairs, carry90) og antal census/1-snapshots pr. UTC-døgn
  siden 11-01 (24/24 hvert døgn 11-01..11-05).
- Cachen `data/lab/market/klines` er kun læst som filnavne, for F2's 20 mønter og månederne 2020-03..2023-12. Ingen
  fil er åbnet, og ingen 2024+-navne er talt.

## 1. Samlet dom

| Undersøgelse | Åbner (UTC) | Dom | Hovedårsag |
|---|---|---|---|
| F2 (kalibrering i explore0) | 2026-11-14 00:00 | **NOT_READY** | Ingen kalibreringsspec og ingen kode. RV-definition, opvarmning og dækningsregel er tvetydige (AMB-02..08). Det står ikke, hvem der godkender kalibreringen (AMB-09). |
| F2 (bekræftelse) | ingen dato | **NOT_READY** | Evalueringsvinduet er ikke godkendt (direktøren 06/11). Der er ingen ejernøgle og derfor ingen verificeret skabelongodkendelse. W0-rangering mangler. |
| C1 (journal) | ingen dato | **NOT_READY** (forbliver READY_NOT_ACTIVE som syntetisk infrastruktur) | Beslutning (a) siger 1h-klines, men koden er census-markPrice (`c1_config/1`). Der er ingen godkendt fremadrettet 1h-kline-kilde (AMB-12..14). |
| A n6 (X1/X2) | 2026-11-14 00:00 | **READY til lås** (betinget af ejerens bekræftelse), **NOT_READY til kørsel** | Låsetekst og afvisende kode findes, og testene er grønne. Indlæseren skrives bevidst først efter låsen. Låseteksten er fordelt på 6b og 7d (AMB-15). |
| A n6 (X3) | 2026-11-28 00:00 | **NOT_READY** (først 28/11) | COIN-M-gaten. Låses sammen med A den 14/11. |
| B n4 | 2026-11-14 00:00 | **NOT_READY** | Låsetekst 6c punkt 1 bygger universet på den karantænerede parliste. Den kan derfor ikke indsættes ordret (AMB-18), og der findes ingen erstatningstekst. |
| HFC-1 3 d | 2026-11-08 00:00 | **NOT_READY** (værktøjshul, kan lukkes før fristen) | Data og regel findes. `hfc1_daily.py outcomes` giver kun N 1.000 og én samlet gruppe, og "uden spotpar" tæller dér som "manglende". Protokollen og ordre 46 kræver C0, C0+ og de beståede adskilt, N 1.000 og 5.000, og manglende og frafald hver for sig (AMB-22/23). |
| STRAKS 7 d | 2026-11-12 17:01:51 | **NOT_READY** (værktøjshul) | `net_report.py` har intet dataskæringstidspunkt, ingen opdeling pr. markedsklasse og ingen sprungne eller afviste signaler (41a punkt 4). 41b-flagene findes. |
| PAR 19/11 | 2026-11-19 20:41:09 | **NOT_READY** (værktøjshul) | `net_report.py` har intet skæringstidspunkt og ingen opdeling på udgangsårsag (43 punkt 7). Udgangsårsagen registreres i `lab/pairs.py`. |
| S1 | 2026-11-20 09:55:07 | **READY** | Kører hver time. Kæde og dækningsrapport findes. Udfaldet bliver sandsynligvis INSUFFICIENT_OBSERVATION (0 nye overgange indtil nu). |
| F3 | 2026-11-28 00:00 | **NOT_READY** | DEFERRED. Observationsenheden er ikke fastlagt. Ingen verificeret godkendelse. W0-rangering mangler. |
| Genstart af værten | 2026-11-28 00:00 | (drift) | Regel B gælder til og med 11-27 (AMB-26). Kræver ejerens egen beslutning. pm_lp's egne trin kommer først. |

"READY" betyder, at den første handling på åbningsdagen kan udføres, som teksterne kræver, når de nævnte
ejerhandlinger foreligger. Det er aldrig en forudsigelse af et resultat.

## 2. Protokolidentitet (sha256 af filen i dette worktree; commit = `git log -1 --format=%h -- <fil>`)

`nov14_readiness.py verify-hashes` kontrollerer, at tabellen er lig `GATE_MATRIX.json` og lig filerne i repoet.
Ændres en fil efter i dag (fx når lås A tilføjes PROTOCOL_V3), giver kontrollen `HASH_MISMATCH`. Det er meningen:
tabellen skal så udgives i en ny version, med den nye hash og en henvisning til låse-committen.

Undtagelse (2026-11-09): `HFC1_PROTOCOL` er et levende dokument. Reglerne er de første 3178 bytes (regelhashen,
som HFC-1-værktøjerne allerede fastlåser), og resten er tilføjede driftsnoter. For den række er sha256 regelhashen
(`prefix_bytes` 3178 i `GATE_MATRIX.json`). Den er bekræftet identisk med låse-committen `368eaec`. En ændring af
reglerne giver stadig `HASH_MISMATCH`; en ny driftsnote gør ikke.

<!-- protocol-identities:start -->
| id | fil | commit | sha256 |
|---|---|---|---|
| `PROTOCOL_V3` | `research/PROTOCOL_V3.md` | `ec91280` | `0a09b3e954d92c8294e1b15f27b12fbc344187562bc73f393d2dd892b2ce6c80` |
| `READINESS_1114` | `research/studies/READINESS_2026-11-14.md` | `dba9bda` | `33de9d7bcd485ea36e548e4e2c01b101fc524726ead634fad81736bce6f74f5e` |
| `MISSION27_3` | `research/studies/MISSION27_3_2026-11-02.md` | `586a34d` | `103fd0afe3e2fd47a1aa289c83b549b625b1046814d68e27873682fecf252fd8` |
| `N6_TOOL` | `research/tools/n6_funding.py` | `7012c2b` | `e481a43cf1b47488ac4d18a125ad6d9bcfa7e1acfe2e5708982163b1c5989709` |
| `N4_TOOL` | `research/tools/n4_kimchi.py` | `8fac269` | `c0e42309017725aee0d3406c023122eb187d7a96d614659dd1d09c7f73b533c4` |
| `FACTORY_P2` | `research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md` | `b54cb3c` | `6dd1ca82934419c0913bccb3a8962f5e5e5154d678eee59179292a7694ae5f43` |
| `C1_DESIGN` | `research/desk/C1_FORECAST_DESIGN.md` | `80fb255` | `530a86d5bb56ec62f6d5f900456c608f67f3964ad7ff2d141e0ad12ec91ff994` |
| `C1_TOOL` | `research/tools/c1_forecast.py` | `80fb255` | `5bedfb002fb1c1fb1fb6453dcbe2fe85d0c2b7c363838c95d6422e0242275c10` |
| `HFC1_PROTOCOL` | `research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md` | `368eaec` | `cd1b6fc66000544f6e58a5e202f4c3f0c2d10913c3882f3eda6b8d06cdfe53c6` |
| `HFC1_TOOL` | `research/tools/hfc1_daily.py` | `5a62465` | `5893a526d8482b4a0c446a53ef61dbd0c6d037774df41fb1573d8e1073135347` |
| `STRAKS_CODE` | `lab/straks.py` | `814ef8b` | `7a110f1fa20fb7d28b76269fc039eec4c75ddfa7353602f2f8824490b722a542` |
| `PAIRS_CODE` | `lab/pairs.py` | `b1ef7a6` | `5c9b60a4314a40a5e4d517427c4960220682b8f6179a445a5554903180ce1219` |
| `NET_REPORT` | `research/tools/net_report.py` | `7b49afd` | `9370876d006b9bd98bd94d45cc8fd092eb53ad2577a01f63b9e42876d507c70b` |
| `S1_TOOL` | `research/tools/factory_s1.py` | `003a8a2` | `e18278f4827dd2d0288bba2c39243d99e6aa29114f57930fc2fc5e8a0cb20f5d` |
| `S1_P0` | `research/studies/FACTORY_S1_P0_2026-11-06.md` | `7a395e3` | `0bd0f5db7ffb8e082fd7b08615100bbb165ed1b68dd2c37ee8f181e676a08af1` |
| `QUARANTINE` | `research/data/QUARANTINE.json` | `8fac269` | `7e98e1b38c552ef962aa0adfb97862fb94be79302580521bf2dd479ea966d117` |
| `LINUX_DRIFT` | `research/LINUX_DRIFT.md` | `6e25c9c` | `659fc33159085b8a196907c03b423b86f0de341bd67a04a994a80f7c43987d58` |
| `GATES_TOOL` | `research/tools/gates.py` | `8fac269` | `7f5050805714ccd206e2cae2d32d0c0124ef320bc0e47b6605447d6e40089558` |
| `STREAM_REGISTRY` | `research/desk/stream_registry.json` | `2e23f52` | `e4b564f11b5b28bb927ff2bbc003e237d0ce3779d1acab0631eb5893f3ebcc5b` |
| `PROTOCOL_SHORTLIST` | `research/desk/PROTOCOL_SHORTLIST.md` | `f624184` | `4012fb71d07fa35d56d870e4bc17b35774cdfda318a7a3b2375bafb33edbe4d8` |
| `OWNER_APPROVAL_P0` | `research/studies/OWNER_APPROVAL_P0_2026-11-06.md` | `ea91152` | `fd759c4af25f464b9297d3aecec74257b70dda01fe49d8d111d87c7ba4a3f03f` |
| `FACTORY_MIGRATION_P1` | `research/studies/FACTORY_MIGRATION_P1_2026-11-06.md` | `6b69703` | `2fbb81f014435ebb69e4c6b0e428e7569335477edcb1732456d5e308b1fb08c9` |
| `LIQPROXY1` | `research/desk/protocols/LIQPROXY1_v1.md` | `f624184` | `f882d1e253e435498944eb213534bc27ffd13f3aef91eca4f0bf53a1fa9a1f01` |
| `FUNDFRAG1` | `research/desk/protocols/FUNDFRAG1_v1.md` | `f624184` | `840ec54ec45eaa234bb1c568aba0ce36a13a530f0005a9f716a547f8779eaf0d` |
<!-- protocol-identities:end -->

PROTOCOL_V3 i produktionens checkout (`/home/anton/ecommerence/copybot`, gren `claude/why-cant-we-do-this-wh3ohb`) har
samme sha256 som dev (`0a09b3e9…`). n6/n4 læser PROTOCOL_V3 i det checkout, de køres fra. Låsen skal derfor stå
dér, hvor kørslen sker.

**Godkendelser, der findes i dag (gælder alle undersøgelser):**
- Alle historiske skabelongodkendelser i laboratoriet (29 skabelonhændelser plus fcarry-familien) har status
  **UNVERIFIED_ORIGIN** (FACTORY_MIGRATION_P1, OWNER_APPROVAL_P0 punkt 6). De bruges aldrig som bevis for ejerens
  godkendelse og genbruges ikke.
- Der er ingen registreret ejernøgle (FACTORY_SECURITY_P1, ejerhandling 1-3 står åbne). Derfor kan ingen ny skabelon
  i dag få en verificeret godkendelse.

## 3. F2 (volatilitet, HAR-RV mod EWMA) og C1 (prognosejournal)

**Identitet:**
- F2: `FACTORY_P2_PROTOCOLS_2026-11-06.md` afsnit F2 (linje 78-123) og direktørens afgørelser (linje 194-205),
  commit `b54cb3c`.
- C1: `C1_FORECAST_DESIGN.md` og `c1_forecast.py` (commit `80fb255`; DEFAULT_CONFIG sha256 `8a6fb2c3…`).
- Direktørens beslutning (a) 06/11 15:02 (INBOX linje 35-40): C1 er F2's prognosejournal og bruger F2's 1h-klines.
  F2 er uændret. Ingen bagudrettede prognoser og ingen automatisk aktivering.

**Navnekollision (AMB-01):** "F2" i PROTOCOL_V3 (ændring 8/10b: hypotesefamilien F2, kohorte senest 11-30, "F2's
embargo") er ikke FACTORY-F2. Det samme gælder F1 og F3. Gates må ikke citeres på tværs.

**Datovinduer (PROTOCOL_V3 afsnit 2 og 10c):**

| Vindue | Periode | Brug for F2 |
|---|---|---|
| explore0 | 2020-03-01..2021-12-31 | kalibrering: kun effektstørrelse og varians; udviklingsinformation; aldrig bevis |
| train3 ∪ validation3 | 2022-01-01..2023-12-31 | foreslået bekræftelse; **ikke godkendt** (direktøren: et separat godkendt evalueringsvindue kræves) |
| 2024 | slut-test | aldrig |
| 2025-01-01 → | reserveret | aldrig, heller ikke som estimationsinput til fremadrettede prognoser |

**Opvarmning (AMB-03/04):** HAR kræver 365 regressionsrækker plus 30 lag, altså 395 sammenhængende komplette døgn
(C1's læsning). Med PROTOCOL_V3 afsnit 2 ("Der overføres ikke historik mellem vinduerne"):
- explore0: første HAR-mål 2021-03-31, højst 276 måldøgn. For SOL og AVAX først 2021-10-01, DOT 2021-08-31, DOGE
  2021-07-31 og FIL 2021-10-31 (cachens første månedsfil, kun filnavne).
- bekræftelse: første mål 2023-01-31, højst 335 måldøgn, ikke 730 som i F2's styrketabel. Styrken er derfor
  overvurderet, hvis opvarmningsreglen gælder. Det er en uklarhed, ikke en rettelse.
- Sidste mål skal ligge i vinduet: 2021-12-31 i explore0 og 2023-12-31 i bekræftelsen. En prognose lavet på
  vinduets sidste dag peger ind i næste vindue (for bekræftelsen 2024) og skal udelades. Det står ikke i F2 (AMB-10).

**Univers og eksklusioner:**
- Fast liste med 20 USD-M-perps (BTC ETH BNB XRP ADA SOL DOGE DOT LTC LINK BCH ETC TRX AVAX ATOM XLM VET FIL EOS
  XTZ), valgt i 2026. Det er en liste, ikke en point-in-time-regel, og den bærer derfor **SURVIVORSHIP_UNKNOWN**
  (FACTORY_MIGRATION, direktørens krav 2). Det ændres ikke.
- "En mønt uden fuld dækning udgår mekanisk; færre end 10 → UNTESTABLE." Om "fuld" betyder 100 % eller PROTOCOL_V3
  afsnit 3's ≥ 99 %, og om det gælder pr. vindue eller pr. døgn, er uklart (AMB-05).
- Cachen har filnavne for alle 20 mønter i alle 24 måneder af train3 + validation3.
- I explore0 har 15 mønter alle 22 måneder. SOL har 16, AVAX 16, DOT 17, DOGE 18 og FIL 15. De fem står derfor
  sandsynligvis uden fuld dækning i explore0, og kalibreringen får sandsynligvis 15 mønter.

**Primær estimand:** gennemsnitlig d = QLIKE(EWMA) − QLIKE(HAR), puljet over mønt-dage. Ensidet DM med Newey-West 5
lags på det "tværsnitsvægtede" daglige middel-d. Vægtene er ikke angivet (AMB-08). K = 1, Holm, α 0,05 i den
historiske fase. Falsifikator: middel-d ≤ 0, eller HAR dårligere i mere end halvdelen af mønterne.

**Omkostningsmodel:** ingen. Estimanden er et prognosetab, ikke et afkast. En PASS er bedre risikoprognose, ikke en
handelsstrategi.

**Alfa og slægt:**
- Historisk fase: α 0,05 pr. vindue (ændring 2), ikke W0.
- En senere fremadtest (C1 brugt bekræftende) trækker α_F 0,0125 fra W0. Den konkurrerer med F3, LIQPROXY1 og
  FUNDFRAG1 om 0,0375 (afsnit 10 og OWNER_DECISIONS).
- Slægt `betting_against_beta` (via `volatility_managed_exposure`, `low_volatility_anomaly`).
- Ændring 8's styrkekrav (styrke ≥ 0,5 ved Sharpe 3,0) passer ikke på en QLIKE-estimand (AMB-11).

**Eksponering:** train3 og validation3 1h-klines for de 20 mønter er brugt af tidligere screeninger (32
lab-screeninger, herunder `vol`-proxyen i P1). Selve HAR-mod-EWMA-spørgsmålet er ikke testet. Det skal stå i en
eventuel rapport.

**Godkendelser:**
- F2: direktørens CONDITIONAL (06/11 08:53). Ingen ejergodkendelse og ingen skabelon.
- C1: READY_NOT_ACTIVE (direktør 06/11 15:02). Strømmen `fwd_vol_forecast_register` er
  PROPOSED_NEEDS_SEPARATE_APPROVAL.

**Ejerhandlinger:** se OWNER_DECISIONS D3, D4, D5, D6 og D7.

**Første handling 14/11 (kun hvis D3 foreligger):**
1. `date -u`.
2. Skriv en kalibreringsspec før data og commit den. Den skal angive estimanderne (sd(d), autokorrelation, ρ_c, e),
   RV-konventionen, dækningsreglen, opvarmningen og output-mærket `development_only`. Den løser ingen uklarhed selv;
   den citerer ejerens eller direktørens afgørelse.
3. Skriv identitetsmanifestet (DATA_CONTRACT afsnit 6) og commit det, før nogen fil åbnes.
4. Skriv indlæseren og test den på syntetiske data, med hele suiten grøn.
5. Én kalibreringskørsel.

Der skal ikke ske nogen netværkshentning: filerne ligger i cachen. Kalibreringen er aldrig en F2-test.

**Dom:** F2 **NOT_READY**. C1 **NOT_READY** til aktivering. Første mulige C1-prognose er under DATA_CONTRACT afsnit 8:
EWMA tidligst mål 2027-01-04 og HAR tidligst mål 2027-12-15. Begge forudsætter en godkendt kilde og et hulfrit løb fra
2026-11-15.

## 4. A — H27-F, metode n6 (lås som ændring 44)

**Identitet:**
- Låsetekst: `MISSION27_3_2026-11-02.md` punkt 6b (linje 295-340) med rettelserne i 7d (linje 439-450). Planen står
  i 7e (linje 452-465). Commit `586a34d`.
- Værktøj: `n6_funding.py` (commit `7012c2b`). Det nægter, indtil PROTOCOL_V3 har en overskrift `^## Ændring … metode
  n6` og datoen er ≥ 2026-11-14 (UTC).
- READINESS_2026-11-14 afsnit 6.

**Datovinduer:**
- explore0 med uger fra mandag 00:00 UTC: 95 uger 2020-03-02..2021-12-20 og n = 94 par (M_t, M_{t+1}).
- X1/X2 fra 2026-11-14 00:00 UTC.
- X3 (COIN-M-basis) låses samtidig, men køres først fra 2026-11-28 00:00 UTC, på de samme uger og med det samme
  udfald.

**Univers og eksklusioner:**
- Alle Binance USD-M `<mønt>USDT`-perps med funding i explore0. Mønterne findes ud fra fundingRate-mappen på
  data.binance.vision (7e punkt 1).
- En uge er gyldig med ≥ 20 perps, der har ≥ 18 af 21 noteringer. Cachen har kun 15-17 mønter i 2020-03..05, så der
  bliver færre uger. Testen ændres ikke.
- X3 kræver ≥ 52 gyldige par, ellers "ikke testbar".
- Tillægsrapport med et fast 15-mønters panel; den afgør intet.

**Primær estimand:** b_k i M_{t+1} = a + c·M_t + b_k·X_k,t + e, med OLS og Newey-West HAC (Bartlett, 4 lags) og
Student t med n − 3 frihedsgrader. PASS_k kræver p ≤ 0,005, samme fortegn i begge halvdele og placebo (X_k,t−4) med
|t| < 2. 3 tests, samlet α ≤ 1,5 %.

**Omkostning:** ingen. Udfaldet er funding, ikke et afkast.

**Alfa og slægt:**
- +3 forsøg til DSR, hver ved α 0,005. De ligger uden for W0.
- Slægten i desk-ledgeren er ikke angivet; funding peger på `cross_venue_perp_gap` (AMB-16).
- En PASS giver kun lov til en ny dateret hypotese med egen fremadtest.

**Godkendelser:**
- Ejeren 2026-11-04: "I behøver ikke spørge mig gør alt" (READINESS afsnit 5). Det er en generel instruks.
- Efter OWNER_APPROVAL_P0's regler (delegering, "gør alt", en generel instruks tæller aldrig) har den samme klasse
  som UNVERIFIED_ORIGIN.
- Direktøren 06/11: "ingen automatisk lås/signatur". Om en PROTOCOL_V3-lås (ikke en skabelon) kræver en verificeret
  signatur, står ingen steder (AMB-29). Fail-closed: et udtrykkeligt ja fra ejeren den 14/11 (D1).

**Første handling 14/11 (kun med D1):**
1. `date -u`.
2. Indsæt 6b og 7d ordret som næste ledige ændring under én niveau-2-overskrift med "metode n6" (AMB-15: ingen
   omformulering), og commit.
3. Indlæser efter 7e med syntetiske tests og hele suiten grøn.
4. Identitetsmanifest for funding- og spot-filerne (cachens sha256 som POST_HOC_IDENTITY plus værtens `.CHECKSUM` som
   CHECKSUM_SAME_SOURCE), committet før filerne åbnes.
5. Én kørsel og commit af resultatet uanset udfald.

**Dom:** **READY til lås** (betinget af D1). **NOT_READY til kørsel**, indtil indlæseren findes og er testet. Den
skrives bevidst efter låsen.

## 5. B — N4, metode n4 (lås som ændring 45)

**Identitet:**
- Låsetekst: `MISSION27_3` punkt 6c (linje 342-385), rettet i 7d og punkt 10.
- PROTOCOL_V3 ændring 38 B (linje 4258-4270), 40 punkt 3 og 5.
- `n4_kimchi.py` (commit `8fac269`), QUARANTINE.json.

**Datovinduer:**
- explore0-dage. Upbit-candlen for dato d (00:00 UTC) lukker kl. 00:00 dag d+1.
- Indgang ved 1 t-klinen kl. 01:00 UTC dag d+1 og udgang samme klokkeslæt dag d+2.
- Upbit tidligst 2026-11-14 og kun efter låsen.

**Univers og eksklusioner (AMB-18/19):**
- 6c punkt 1 siger "de 232 par i" parlisten fra 11-02. Den liste er i karantæne (ændring 40; forbudt i "any lock
  text"), og 38 B punkt 4 kræver et nyt `market/all`-kald efter låsen. Teksten kan altså ikke indsættes ordret.
- En erstatningsformulering af punkt 1 findes ingen steder.
- Krydsningen med Binance-perps har ingen fastlagt kilde eller as-of (nutidens exchangeInfo eller arkivindekset med
  afnoterede).
- Overlevelsesskævheden, Upbit-afnoteringer før kaldet, er erklæret i 6c.
- BTC og stablecoins er udeladt. En dag er gyldig med ≥ 40 mønter.

**Primær estimand:** r_d = middel-y i øverste minus nederste femtedel efter s. SCREEN_PASS kræver p ≤ 0,005, middel
over gulvet 0,46 %/dag, samme fortegn i halvdelene og uden de 2 største dage, og placebo (s fra d−7) med |t| < 2.

**Omkostning:** gulvet 0,46 % pr. dag (21i) står for omkostningen. y er bruttoafkast mod BTC.

**Alfa og slægt:** 1 test ved α 0,005, +1 forsøg til DSR, uden for W0. Beslægtet med M3 (præmiekonvergens,
forkastet), slægt `cross_venue_perp_gap`.

**Godkendelser:**
- 38 B: brugerens "Begge" 11-02, en dateret tekst. Dækker værten.
- Låsen: som A (AMB-29).

**Datakilder:**
- Upbits offentlige API kun med `market/all` og `candles/days`, én forespørgsel ad gangen, ≥ 0,2 s imellem, kun
  explore0-rækker. Upbit-historikkens længde er ukontrolleret (AMB-20).
- Binance 1h-klines fra cachen eller data.binance.vision, højst 2 samtidige.

**Første handling 14/11 (kun med D2, ejerens formulering af punkt 1, og ja til låsen):**
1. `date -u`.
2. Indsæt 6c med ejerens formulering af punkt 1 og commit.
3. Ét nyt `market/all`-kald.
4. Indlæser med syntetiske tests.
5. Identitetsmanifest.
6. Én kørsel.

**Dom:** **NOT_READY.** B kan ikke låses ordret, før ejeren har afgjort punkt 1. Uden D2 sker der intet med B, og
Upbit-gaten forbliver lukket.

## 6. HFC-1 — første 3 d-udfald (cohort 2026-11-04)

**Identitet:** `HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md` (commit `368eaec`) og `hfc1_daily.py` (commit
`5a62465`).

**Datovinduer:**
- Kohorte d dannes ved dagens slutning.
- 3 d-udfaldet bruger snapshots med ts i [d+1 00:00, d+4 00:00).
- Cohort 11-04: [2026-11-05 00:00, 2026-11-08 00:00). Tidligst 2026-11-08 00:00 UTC; foreslået ≥ 00:35 UTC, når
  sidste snapshot er landet (snapshots lander 0-503 s efter timen).
- Cohort 11-05 åbner 11-09.
- 14 d-udfaldet for cohort 11-04 åbner 2026-11-19 00:00.
- Opsummeringer 11-28 og 12-09.

**Univers:**
- C0 = USDT-perps med 72 t-middel-APR ≥ 12,5 % (lastFundingRate × 1095, ≥ 24 snapshots). C0+ ≥ 18,8 %.
- Filtrene F1-F6 rapporteres som frafald.
- Cohort 11-04 har 120 rækker. Hver række bærer `drop` (filtertrin), `m2` (C0+), `cost_1000`/`cost_5000` og
  `covered_*`. Kun nøglerne er læst.

**Udfald:**
- Realiseret funding = middel af lastFundingRate i vinduet × 9 perioder × N.
- Manglende medlem eller > 25 % manglende snapshots → "manglende", tælles som "ikke dækket", aldrig som succes.
- Andel dækket ex post og median dækningsgrad, separat for C0, C0+ og de beståede.

**Omkostning:** bogens gennemgang (VWAP mod mid, ind og ud) + taker 0,001 + slippage 0,0002 pr. side, spot + perp.

**Alfa:** ingen. Beskrivende; afgør intet.

**Godkendelser:** direktør 11-04 og 11-06. Ingen ejerhandling.

**Værktøjshul (AMB-22/23):**
- `outcomes` regner kun N = 1.000 og én gruppe.
- Rækker uden omkostning (ingen spotpar eller tom bog) falder i "missing_or_no_cost". Ordre 46 P2 kræver alle
  C0-kandidater, også uden spotpar, med manglende data og frafald hver for sig.
- Rapportskabelonen nedenfor kan udfyldes read-only fra kohortefilen og census/1. Den kræver et nyt read-only script
  (en ny fil). Det er ikke skrevet i denne opgave.

**AMB-21:** Protokollen siger "Evalueres først efter 14/11", mens direktørens milepæl er 3 d-udfaldet 08/11.
Fail-closed læsning: 08/11 er en beskrivende opgørelse af udfaldet; ingen evaluering, ingen konklusion og ingen ny
udvælgelsesregel før beslutningsnotatet efter 11-28.

**Rapportskabelon 08/11 (read-only, ingen værdier i dag):**

| Felt | C0 alle | C0+ | bestod F1-F6 | uden spotpar (F1-frafald) | andet frafald (F2-F5) |
|---|---|---|---|---|---|
| medlemmer | | | | | |
| udfald manglende (afnoteret/omdøbt eller > 25 % huller) | | | | | |
| realiseret funding pr. 1.000 USDT (median, min, maks) | | | | | (ingen omkostning) |
| omkostning kendt (antal) | | | | 0 | |
| dækket ex post ved 1.000 / 5.000 (antal af kendte) | | | | n/a | |
| median dækningsgrad ved 1.000 / 5.000 | | | | n/a | |
| ex ante dækket (fra kohortefilen) mod ex post | | | | | |

Plus: kørselstid, census-snapshots i vinduet (forventet 72), filens sha256 og sætningen "3 dage siger intet om
langsigtet profit". Kendt begrænsning: 4 t-fundingintervaller undervurderes.

**Dom:** **NOT_READY**, fordi værktøjet mangler den krævede opdeling. Data, regel og vindue er klar. Hullet kan
lukkes med et nyt read-only script før 2026-11-08 00:35 UTC.

## 7. STRAKS — første beskrivende opgørelse (7 dage)

**Identitet:** PROTOCOL_V3 ændring 41 (linje 4309-4339), 41a (linje 4341-4362) og rettelse 41b (linje 4445-4453),
`lab/straks.py` (commit `814ef8b`) og `net_report.py` (commit `7b49afd`, `FLAG_41B = {58416, 58417, 58591}`).

**Konti:** STRAKS-FØLG `LANE_35f39bb233` og STRAKS-MOD `LANE_a751c1f595`, startet 2026-11-05 17:01:51 UTC
(`lane.started`, aggregeret).

**Vindue (AMB-24):** "2026-11-12 (7 dage)". Fail-closed: dataskæring 2026-11-12 17:01:51 UTC (7 × 24 t), rapport
derefter. Positioner, der er åbne ved skæringen, rapporteres urealiserede til seneste timemærkning før skæringen.

**Univers:** de 12 markeder i ændring 41 punkt 2 (Binance-perps; ikke-krypto er TradFi-perps). Signal = hver
`opportunity.move` efter kontostart, højst 2 t gammel.

**Estimand:** ingen; beskrivende. Aldrig bevis, ingen kandidat, alfa eller LÅS.

**Omkostning:** taker 0,001, slippage-tillæg 0,0002 pr. side, spread-reference 0,002, 1.000 USDT pr. position, ud
efter ≥ 24 t, funding bogført.

**Godkendelse:** ejeren 11-05 ("start straks-bog", kun handelsfiltrene; datagrænser uændrede). Ingen ejerhandling.

**Værktøjshul:** `net_report.py` mangler tre ting. Uden dem kan 41a punkt 4 ikke opfyldes:
- dataskæring (den rapporterer til "nu");
- opdeling pr. markedsklasse;
- sprungne og afviste signaler (`straks.skipped`) og markedets bevægelse efter signalet adskilt fra det simulerede
  resultat.

**Rapportskabelon 12/11:**

| Felt | FØLG | MOD | FØLG uden 41b | MOD uden 41b |
|---|---|---|---|---|
| signaler set / handlet / sprunget (årsag) / afvist (bog) | | | | |
| handler (rundture), åbne ved skæring | | | | |
| brutto (prisbevægelse), netto | | | | |
| gebyrer, bog, tillæg, funding | | | | |
| største eksponering, største fald | | | | |
| pr. klasse: krypto / metaller / energi / aktieindeks / FX | | | | |
| markedets 24 t-bevægelse efter signalet (samme signaler) | | | | |

Hertil: "FØLG og MOD er ikke spejlbilleder", "24 t, 1.000 USDT og retningsreglen ændres ikke" og de tre
41b-signaler (move 58416, 58417, 58591; seks ordrer pr. konto).

**Dom:** **NOT_READY**, fordi værktøjet mangler skæring, klasse og sprungne signaler. Data registreres. Hullet kan
lukkes med et nyt read-only script før 2026-11-12 17:01 UTC.

## 8. PAR-BOG — diagnostisk opgørelse 19/11

**Identitet:** PROTOCOL_V3 ændring 43 (linje 4423-4443) og 43a (linje 4455-4466), `lab/pairs.py` (commit `b1ef7a6`;
udgangsårsag `normal`/`stop`/`tid`). PAR-BOG `LANE_68b8b6feb9`, startet 2026-11-05 20:41:09 UTC.

**Vindue (AMB-25):** "2026-11-19 (diagnostisk)". Fail-closed: 14 × 24 t, altså skæring 2026-11-19 20:41:09 UTC.

**Univers:** BZ/CL, ETH/BTC, QQQ/SPY og XAG/XAU (USD-M-perps). Lot-trin og fuldt fyld efter 43a.

**Estimand:** ingen; udforskning. Fast 2 / 0,5 / 4 / 72 t / 720 t.

**Omkostning:** banekontienes model med spread-reference 0,002, begge ben, funding på begge ben.

**Godkendelse:** Claude under ejerens mandat 11-05. Ingen ejerhandling.

**Rapportskabelon pr. par:** antal handler, brutto, netto, gebyrer, bog, tillæg, funding, udgangsårsag (normal / stop
/ tid), "ikke sendt: bog for tynd" og BLOCKED (ukendt lot-trin), samlet og pr. par.

**Dom:** **NOT_READY** (værktøjshul: skæring og opdeling på udgangsårsag). Data registreres.

## 9. S1 — tidligste evaluering 2026-11-20 09:55:07 UTC

**Identitet:** `factory_s1.py` (commit `003a8a2`), `FACTORY_S1_P0_2026-11-06.md` (commit `7a395e3`) og
`research/data/factory_s1/` (kæde, runs.jsonl, summary.md).

**Status 06/11 14:13 UTC:** 12 kørsler, længste hul 1,19 t, 0 MONITORING_GAP, 0 nye overgange, baseline 179.

**Estimand:**
- Fabrikkens ALLOW/BLOCK mod laboratoriets beslutning pr. ny overgang.
- Hændelsesdækning og tidsdækning rapporteres hver for sig.
- Få nye overgange → INSUFFICIENT_OBSERVATION, aldrig automatisk PASS.

**Godkendelse:** direktør (ordre 48/49). S2 kræver en ny ejerbeslutning; Claude aktiverer aldrig S2.

**Rapportskabelon 20/11:**
- forventede og gennemførte kørsler, længste hul, MONITORING_GAP-perioder;
- nye overgange, BLOCK/ALLOW pr. årsag, uforklarede forskelle og falske blokeringer;
- legacy-kompatibilitet, ressourcer, fejl (errors.jsonl), kædeintegritet og testdækning;
- anbefaling.

**Risiko:** S1 kører kun, når assistentens timetjek kører. En stillestående session giver huller.

**Dom:** **READY.**

## 10. F3 og genstart (28/11)

**F3:**
- Identitet: `FACTORY_P2` afsnit F3 (linje 125-185) og afgørelserne (linje 201-205).
- Data: COIN-M-filer kun fra data.binance.vision fra 2026-11-28 00:00 UTC (`dapi.binance.com` er ikke tilladt).
- Univers: kvartaler med fuld dækning, antal UNKNOWN; under 4 coins → UNTESTABLE.
- Estimand: annualiseret netto carry på allokeret kapital, med klyngerobust SE pr. udløb.
- Omkostning: spot 0,10 % + COIN-M 0,05 % + slip 0,02 % pr. side.
- Alfa: α 0,05 historisk; senere fremadtest α_F 0,0125 fra W0.
- Kalibrering på de første 2 udløb tæller i regnskabet og skal være adskilt fra evalueringen.
- Observationsenheden er ikke fastlagt (AMB-27).
- **NOT_READY.** Første handling 28/11 er kun `date -u` og ingenting andet, indtil D8 foreligger.

**A X3 (28/11):**
1. `date -u`.
2. Hent BTCUSD-kvartalernes dagsklines for explore0 fra data.binance.vision (cm-stien).
3. Identitetsmanifest.
4. Én kørsel på de samme uger.

Kræver, at lås A er committet 14/11.

**Genstart:**
- LINUX_DRIFT regel B: ingen planlagt genstart eller systemopdatering "til og med 2026-11-27". PROTOCOL_V3 10b punkt
  5 siger "før 2026-11-28". Tidligst 2026-11-28 00:00 UTC.
- Kun på ejerens egen beslutning (D9). pm_lp's egne trin (slå enheden fra før holdout) er pm_lp's og røres ikke her.
- Efter enhver genstart: collector først, derefter deploy-check.

## 11. AMBIGUITY (ikke løst; kræver ejerens eller direktørens daterede afgørelse før data)

| id | Undersøgelse | Tekst | Uklarhed |
|---|---|---|---|
| AMB-01 | F2/F3 | PROTOCOL_V3 8/10b ("F2's embargo") mod FACTORY_P2 | Samme navne F1/F2/F3 for forskellige ting; gates må ikke citeres på tværs |
| AMB-02 | F2/C1 | FACTORY_P2 linje 98: "summen af kvadrerede 1-times log-afkast pr. UTC-dag" | 24 afkast (inkl. grænseafkastet fra forrige døgns sidste close) eller 23 (inden for døgnets 24 closes)? C1 brugte 23 med embargo |
| AMB-03 | F2 | "OLS på de foregående 365 dage" | 365 regressionsrækker (395 døgn data) eller 365 døgn data (335 rækker)? |
| AMB-04 | F2 | PROTOCOL_V3 afsnit 2 (ingen historik mellem vinduer) mod styrketabellen (730 d) | Gælder opvarmningen i vinduet? Så 335 måldøgn i bekræftelsen og 276 i explore0 |
| AMB-05 | F2 | "En mønt uden fuld dækning udgår mekanisk" | 100 % eller afsnit 3's ≥ 99 %? Pr. vindue eller pr. døgn? 5 mønter er noteret efter 2020-03 |
| AMB-06 | F2 | EWMA λ 0,94 | Startværdi og indkøring er ikke angivet (C1: første RV, indkøring 50) |
| AMB-07 | F2 | HAR-prognose | En prognose ≤ 0 gør QLIKE udefineret; behandlingen er ikke angivet |
| AMB-08 | F2 | "tværsnitsvægtede daglige middel-d" | Vægte ikke angivet (lige vægt?); dage med manglende mønter |
| AMB-09 | F2 | "Aktivering kræver approve-template" mod "kalibrering fra 14/11" før godkendelse | Hvem godkender kalibreringens dataadgang? Fail-closed: ejerens kvittering (D3) |
| AMB-10 | F2 | vinduesgrænser | En prognose på vinduets sidste dag peger ind i næste vindue (2024 for bekræftelsen); udeladelsen står ikke i teksten |
| AMB-11 | F2/W0 | ændring 8 linje 625-626 (styrke ≥ 0,5 ved Sharpe 3,0) | Passer ikke på en QLIKE-estimand; W0-reglen for F2's fremadtest er udefineret |
| AMB-12 | C1 | beslutning (a) mod `c1_config/1` (census markPrice, registret: 00:05) | Koden og registret følger ikke beslutningen; config v2 er nødvendig før aktivering |
| AMB-13 | C1 | ingen fremadrettet 1h-kline-strøm | `dup_universe_1h_klines` er REJECTED_DUPLICATE; dagsarkiver kommer efter døgnet. Ingen tilladt kilde til prognoser for t+1 |
| AMB-14 | C1/F2 | "Prognose for RV_{t+1} lavet ved dagens slutning" mod "låst før target-vinduet" | Med 24 closes efter åbningstid er sidste close = målstart; kræver embargo-konventionen, som kan afvige fra F2 |
| AMB-15 | A | "indsættes ordret" mod tekst fordelt på 6b + 7d | Hvordan sættes de sammen uden omformulering? Forslag: begge ordret under én overskrift |
| AMB-16 | A | 6b punkt 10 | Desk-ledgerens slægt for n6 er ikke angivet |
| AMB-17 | A/B | `locked()`-regex | Tjekker kun en niveau-2-overskrift, ikke at committen kom før dataadgang eller teksten er 6b. Det er en svaghed, ikke en regel |
| AMB-18 | B | 6c punkt 1 ("de 232 par i" karantænefilen) mod 38 B punkt 4, 40 punkt 5 og QUARANTINE "any lock text" | Låseteksten kan ikke indsættes ordret; der findes ingen erstatningstekst |
| AMB-19 | B | "krydset med Binance-perps" | Kilde og as-of for krydsningen er ikke angivet; point-in-time er umuligt for Upbit (market/all er nutidens liste) |
| AMB-20 | B | 38 B punkt 2 "kun rækker inden for explore0 gemmes" | candles/days-svar kan rumme rækker uden for vinduet; de kasseres ved indlæsning. Historikkens længde er ukontrolleret |
| AMB-21 | HFC-1 | "Evalueres først efter 14/11" mod milepælen 08/11 | Læses her som beskrivende opgørelse 08/11, evaluering efter 11-28 |
| AMB-22 | HFC-1 | "andel dækket … ved N" | Medlemmer uden spotpar har ingen omkostning; koden tæller dem som manglende, men direktøren vil have dem separat |
| AMB-23 | HFC-1 | N 1.000 og 5.000; C0, C0+, beståede | Koden regner kun 1.000 og én gruppe |
| AMB-24 | STRAKS | "2026-11-12 (7 dage)" | Kalenderdato eller 7 × 24 t fra 17:01:51 UTC? Fail-closed: det sidste |
| AMB-25 | PAR | "2026-11-19 (diagnostisk)" | Kalenderdato eller 14 × 24 t fra 20:41:09 UTC? Fail-closed: det sidste |
| AMB-26 | genstart | milepæl "27/11" mod "til og med 2026-11-27" / "før 2026-11-28" | Teksterne er enige om, at genstart tidligst sker 2026-11-28 00:00 UTC; "27/11" er fristens sidste dag |
| AMB-27 | F3 | observationsenhed; ændring 8 punkt 17 | Enheden er ikke fastlagt. Om FACTORY-udkast er "kode for ændring 8" er uafklaret (samme dato 28/11) |
| AMB-28 | A/B | numrene 44/45 | Kommer en anden ændring først, flytter numrene (regexen er ligeglad); READINESS opdateres, ikke protokollen |
| AMB-29 | alle | ejerens "gør alt" (11-04) mod OWNER_APPROVAL_P0 ("en generel instruks tæller aldrig") og "ingen automatisk lås/signatur" | Kræver en PROTOCOL_V3-lås (ikke en skabelon) en verificeret signatur? Fail-closed: et udtrykkeligt ja pr. lås |

## 12. Tidslinje (UTC) og første handling

| Tid | Handling | Forudsætning |
|---|---|---|
| 2026-11-08 00:35 | HFC-1 3 d cohort 11-04, read-only | nyt rapportscript (afsnit 6) |
| 2026-11-12 17:01:51 | STRAKS 7 d, read-only | nyt rapportscript (afsnit 7) |
| 2026-11-14 00:00 | `date -u`; lås A (D1); lås B (D2); F2-kalibreringsspec (D3) | ejerens ja pr. punkt |
| 2026-11-14 efter låsene | identitetsmanifester, indlæsere, syntetiske tests, suite, én kørsel A (X1/X2), B, F2-kalibrering | låse-commits |
| 2026-11-19 00:00 | HFC-1 14 d for cohort 11-04 bliver mulig (beskrivende) | — |
| 2026-11-19 20:41:09 | PAR diagnostisk, read-only | nyt rapportscript |
| 2026-11-20 09:55:07 | S1-evaluering | S1 har kørt hver time |
| 2026-11-28 00:00 | COIN-M: A X3 én kørsel; F3 kun med D8; genstart kun med D9 | lås A; D8; D9 |

## 13. Kontrolværktøj og tests

- `python3 research/tools/nov14_readiness.py validate`: strukturen, datogulvene (11-14, 11-28, 11-28) og n6/n4's
  `EARLIEST` (læst som tekst). Status pr. 2026-11-06 14:38:27 UTC skal stemme, og en timevis gennemgang til 28/11
  med alle flag sat må ikke finde en gate, der åbner før sin dato.
- `verify-hashes`: denne tabel = matrixen = filerne.
- `check --now … --action … --study … --flag …`: tilladt eller blokeret med årsager. Ukendt handling, gate eller
  undersøgelse, en naiv tid eller et manglende flag giver blokering.
- Flagene er simulerede input. Værktøjet sætter dem aldrig selv og skriver intet.
- Test: `python3 -m unittest tests.test_research_nov14_readiness tests.test_research_gates tests.test_lab_safety`.
