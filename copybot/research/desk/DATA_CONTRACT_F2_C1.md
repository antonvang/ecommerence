# Datakontrakt F2 → C1: 1h-klines (direktørordre 52 P1)

**Skrevet 2026-11-06 kl. 14:38 UTC. Ingen data er hentet eller åbnet. Kontrakten ændrer ikke F2.**

Kontrakten beskriver, hvordan C1 (F2's prognosejournal, beslutning (a), INBOX 2026-11-06 15:02) må bruge de 1h-klines,
F2 får lov at bruge.

- Kun det, F2 (`FACTORY_P2_PROTOCOLS_2026-11-06.md`) og PROTOCOL_V3 allerede tillader, er citeret som tilladt.
- Hvor de er tavse eller tvetydige, står det som AMBIGUITY med id fra `NOV14_READINESS.md` afsnit 11.
- C1-siden af kontrakten (en ny config `c1_config/2`) er PROPOSED. Den kræver ejerens godkendelse ved C1's aktivering
  (OWNER_DECISIONS D7), og den gælder ikke før.

## 1. Kilde

**Historisk lag (det eneste, der er tilladt i dag):**
- Binance USD-M månedlige 1h-kline-zip fra `data.binance.vision`, sti
  `data/futures/um/monthly/klines/<SYM>/1h/<SYM>-1h-YYYY-MM.zip`.
- Hjemmel:
  - PROTOCOL_V3 afsnit 4 ("Binance klines (månedlige zip)");
  - 10b punkt 2 og 10d (explore0-filer fra data.binance.vision, højst 2 samtidige downloads i hele lab'en);
  - 8 punkt 17 (familier: kun data.binance.vision gennem cachen og download-koden).
- F2-teksten nævner selv ingen vært (AMB-02-gruppen). Kontrakten antager ingen anden.
- Cache: `data/lab/market/klines/` i produktionens datamappe. Kun filnavne er talt:
  - train3 + validation3: alle 20 mønter har 24/24 månedsfiler;
  - explore0: 15 mønter har 22/22; SOL 16, AVAX 16, DOT 17, DOGE 18 og FIL 15.
  - F2 behøver derfor sandsynligvis ingen netværkshentning. Manglende filer hentes kun gennem lab'ets hentevej (højst
    2 samtidige, `absent_404.json` respekteres).
- Gate G01: ingen adgang før 2026-11-14 00:00 UTC. Det gælder også læsning af cachen.
- Aldrig: `api.binance.com` (handelsvært), `dapi.binance.com` og 2024- eller 2025+-filer (G03, G04).

**Fremadrettet lag (C1's prognoser): ingen tilladt kilde i dag (AMB-13).**

| Kandidat | Hvad teksterne siger | Status |
|---|---|---|
| `fapi.binance.com/fapi/v1/klines` (tilladt lab-vært; papirløberens timebarer, ændring 43 punkt 3) | En strøm af 1h-klines for universet er afvist som dublet (`dup_universe_1h_klines` REJECTED_DUPLICATE) | kræver en separat godkendt strøm (G19) |
| data.binance.vision dagsarkiver | En fil for døgn D kommer først efter D. En prognose for D+1 kan ikke oprettes før D+1's start med D's sidste close | uegnet til t+1 uden ændret horisont, og en ændret horisont ville ændre F2 |
| census/1 markPrice (C1's nuværende kode) | Fravalgt af direktøren (census-varianten) | ikke F2's måling |

Kontrakten vælger ingen af dem. Uden G19 skriver C1 ingen rigtig prognose.

## 2. Univers (point-in-time)

- F2's univers er en **fast liste** på 20 USD-M-perps, låst i F2: BTC ETH BNB XRP ADA SOL DOGE DOT LTC LINK BCH ETC
  TRX AVAX ATOM XLM VET FIL EOS XTZ.
- Det er ikke en point-in-time-regel. Listen er valgt i 2026, og resultatet bærer **SURVIVORSHIP_UNKNOWN**
  (FACTORY_MIGRATION, direktørens krav 2). Kontrakten ændrer den ikke og må aldrig fremstille den som et oprindeligt
  point-in-time-univers.
- Medlemskab låses med F2's lås. Ingen mønt tilføjes eller byttes, heller ikke i C1.
- Eksklusion pr. vindue sker mekanisk, før noget tab eller afkast beregnes: "en mønt uden fuld dækning udgår".
  Tærsklen (100 % eller 99 %) og om den gælder pr. vindue eller pr. døgn er AMB-05. Færre end 10 mønter → UNTESTABLE.
- C1 fremad: samme 20 symboler. Bliver et symbol afnoteret, får det ufuldstændige døgn (ingen RV) og void-reveals. Det
  udfyldes aldrig, og listen erstattes ikke.

## 3. Felter

Kolonnerne i Binance' kline-arkiv: `open_time` (ms), `open`, `high`, `low`, `close`, `volume`, `close_time` (ms),
`quote_volume`, `count`, `taker_buy_volume`, `taker_buy_quote_volume`, `ignore`.

- F2 og C1 bruger kun `open_time`, `close` og `close_time`. `count` og `volume` læses kun til datakvalitet
  (flade barer, se afsnit 5).
- En første række med ikke-numerisk `open_time` (overskrift) springes over deterministisk. Enhver anden
  ikke-numerisk række gør filen ugyldig.
- Tider skal være i millisekunder (13 cifre i perioden). Andre længder gør filen ugyldig.

## 4. Tidskonvention (UTC)

- Kline k med `open_time` o dækker [o, o + 3600 s). `close_time` = o + 3.599.999 ms.
- Dens `close` er prisen ved **mærketiden** m = o + 3600 s og er først kendt, når baren er lukket.
- En bar må først bruges fra m (PROTOCOL_V3 afsnit 4: "kun fra bars, der er lukket").

Hvilke 24 closes hører til UTC-døgn D? F2 siger det ikke (AMB-02/AMB-14). De to mulige læsninger står herunder.
Kontrakten vælger ingen af dem.

| | Konvention A (åbningstid) | Konvention B (mærketid, C1-embargo) |
|---|---|---|
| Døgnets 24 closes | barer med `open_time` i [D 00:00, D 23:00]; mærker D 01:00 … D+1 00:00 | closes med mærketid i [D 00:00, D 23:00]; barer med `open_time` D−1 23:00 … D 22:00 |
| RV_D | 24 afkast: kræver også forrige døgns sidste close (mærke D 00:00); eller 23 uden den | 23 afkast inden for døgnet; afkastet D 23:00 → D+1 00:00 hører ikke til noget døgn |
| Sidste input til prognosen for D+1 | mærke D+1 00:00 = målstart | mærke D 23:00 |
| Kan en prognose oprettes før målstart? | nej (historisk ja, men fremad nej) | ja: oprettes i [D 23:00 + afregning, D+1 00:00) |

Konsekvensen:
- Vælger F2's lås konvention A med 24 afkast, kan C1 fremad ikke både følge F2 og oprette før målvinduet. Så må
  direktøren eller ejeren afgøre det, og C1 må ikke selv vælge.
- Vælges B, er C1 og F2 identiske, og embargoen gælder også historisk i F2.

## 5. Fuldstændighed og manglende data

- Et døgn er **komplet**, når alle 24 closes efter den valgte konvention findes og hver bar opfylder alle krav:
  - `open_time` er justeret til hel time;
  - `close_time` = `open_time` + 3.599.999;
  - `close` er endelig og > 0;
  - ingen dublet-`open_time` og strengt stigende rækkefølge (PROTOCOL_V3 afsnit 3).
- **Aldrig udfyldning:**
  - et manglende close giver et døgn uden RV, der hverken interpoleres, skaleres eller erstattes;
  - et døgn uden RV afbryder HAR-vinduet og genstarter EWMA-løbet (C1: `gap_policy` = restart).
- Dubletter eller faldende tider gør filen ugyldig. Der dedupliceres ikke, og symbol-måneden tæller som manglende.
- **Flade barer** (`count` = 0 og O = H = L = C, typisk ved børsnedbrud) er formelt til stede. De tælles og
  rapporteres, men F2 siger ikke, om de gør døgnet ufuldstændigt. Det er en uklarhed (hører under AMB-05), og
  kontrakten udfylder eller fjerner intet.
- Hver fils sha256 og antallet af kasserede rækker uden for vinduet logges.

## 6. Dataidentitet ved låsen

1. **Før nogen fil fortolkes** committes et manifest. Pr. fil: sti, størrelse, lokal sha256 og hentetidspunkt (fra
   cachens filtid). Dertil en manifest-sha256 over de sorterede linjer.
2. Cachefilerne blev hentet før låsen (filtider i stikprøver: 2026-10-17 og 2026-10-19). Deres lokale hash mærkes **POST_HOC_IDENTITY**. Den
   identificerer, hvad der læses, men er ingen lås før data (FACTORY_MIGRATION).
3. Værtens egen `.CHECKSUM` pr. zip kan hentes ved låsen (≥ 2026-11-14, G01; kun explore0-, train3- og
   validation3-filer). Den sammenlignes med den lokale hash og mærkes **CHECKSUM_SAME_SOURCE**: den beviser
   integritet mod værten, ikke at filen var uændret på låsetidspunktet. Uden et betroet historisk bevis står
   begrænsningen i resultatet (direktørens krav 1).
4. Ved adgang genberegnes sha256. En afvigelse fra manifestet giver BLOCK, og intet læses.
5. Hentning af `.CHECKSUM` er en historisk forespørgsel og følger G01. Den er aldrig for 2024 eller 2025+.

## 7. explore0 og fremadvinduet holdes adskilt

- **explore0 (2020-03-01..2021-12-31) bruges kun til:**
  - F2's kalibrering (effektstørrelse e, sd(d), autokorrelation, ρ_c; G17);
  - udvikling af C1's kode (numerik, kodestier).
- explore0 er udviklingsinformation og fremstilles **aldrig** som fremadvalidering eller som F2-evidens.
- Hvert output fra explore0 bærer `"window": "explore0", "evidence": "development_only"` og gemmes adskilt fra
  journalen.
- **Ingen bagudrettede prognoser:**
  - C1's journal indeholder aldrig en prognose for et døgn, der er begyndt før oprettelsen;
  - en explore0-beregning skrives aldrig i en journal, heller ikke en syntetisk;
  - syntetiske journaler bruger 2033-epoken, og en rigtig journal afviser den (C1 regel 10).
- **train3 ∪ validation3** åbnes for F2 kun efter godkendelse af vinduet (G16).
- **2024 og 2025+** bruges aldrig, heller ikke som estimationsinput til fremadrettede HAR-prognoser. Fremad estimeres
  HAR kun på fremaddata indsamlet efter C1's aktivering.

## 8. HAR-minimumskrav og første mulige prognose

Kravene (C1's læsning af F2; AMB-03 og AMB-06 er åbne):
- HAR: 365 regressionsrækker plus 30 lag, altså **395 sammenhængende komplette døgn** [L−394, L]. Prognosen gælder
  L+1.
- EWMA: indkøring **50** komplette døgn (startvægt 0,94^49 = 0,048 ≤ 0,05). Kravet er C1's, F2 angiver det ikke.

**Historisk** (opvarmning i vinduet, AMB-04):

| Vindue | Første HAR-mål | Antal mål højst | Første EWMA-mål |
|---|---|---|---|
| explore0 | 2021-03-31 (sene noteringer 2021-07-31..10-31) | 276 | 2020-04-20 |
| train3 ∪ validation3 | 2023-01-31 | 335 | 2022-02-20 |

**Fremad (C1):**
- Lad F være det første komplette UTC-døgn efter aktiveringen, tidligst 2026-11-15 ved aktivering 2026-11-14.
- **EWMA:** første mål F + 50 døgn, altså **2027-01-04**. Inputdøgn 2026-11-15..2027-01-03.
- **HAR:** første mål F + 395 døgn, altså **2027-12-15**. Inputdøgn 2026-11-15..2027-12-14.
- **Med konvention B:**
  - input-cutoff = mærket 2027-12-14 23:00:00 UTC (close på baren med `open_time` 22:00);
  - oprettelse i [23:00 + afregning, 2027-12-15 00:00);
  - målstart 2027-12-15 00:00, målslut 2027-12-16 00:00 og tidligste reveal 2027-12-16 01:00.
- **Med konvention A** kan ingen fremadrettet prognose oprettes før målstart (afsnit 4).
- Ét manglende close nulstiller løbet: F bliver (hullets døgn + 1).
- Første sammenlignelige par (HAR og EWMA samme døgn) kommer altså tidligst 2027-12-15.
- Styrken fremad er 0,12 efter 90 døgn og 0,47 efter 365 (C1-design afsnit 9). Der gives ingen automatisk PASS/FAIL.

## 9. Journalens integritet

Kontrakten bygger på `c1_forecast.Journal` uden at ændre den:
- append-only og hash-kædet;
- `entry_hash` = sha256 af den kanoniske linje;
- genesis bærer den fulde config og dens `config_sha256`;
- `.head` (seq + hash) fanger en afkortet hale;
- fuld genverifikation ved hver læsning;
- reveal tidligst `target_end + 3600 s` og kun én gang.

Ændringer, der kræves ved aktivering (som ny version, ikke i dag):
1. **`c1_config/2`:**
   - kilde 1h-kline-`close` (ikke census `markPrice`);
   - tidskonventionen fra afsnit 4, som F2's lås vælger;
   - 24 closes pr. døgn;
   - de samme HAR/EWMA/QLIKE/DM-konstanter som F2.
   - Den nye config-sha256 står i aktiveringsændringen.
2. **`input_sha256`-format `c1-input/2`:**
   `c1-input/2|symbol|close|first_day|last_day` og derefter én linje `open_time_ms,close_time_ms,repr(close)` pr. bar.
3. **Ekstern ankring af head-hashen, mindst dagligt:**
   - en commit i samme dev-repo er ikke rollback-sikker (direktørens svar på ordre 49 P0);
   - ankeret skal ligge, hvor assistenten ikke kan skrive, fx ejerens signerede kontrolpunkt (FACTORY_SECURITY
     ejerhandling 4) eller et sted uden for maskinen;
   - indtil da er journalens tidspunkter kun "værtens ur" (C1 afsnit 11).
4. **Informationstid** for en bar: max(mærketid m, modtagelsestid). En prognose afvises, hvis dens input har
   informationstid > oprettelsestid.

## 10. Hvad C1 aldrig gør

- henter data selv: C1 har intet netværksmodul og læser kun F2's godkendte, manifesterede filer eller en godkendt strøm;
- ændrer F2's model, univers, benchmark, tab, test eller estimand;
- bruger census/1 som F2-data;
- skriver explore0-beregninger som prognoser;
- udfylder huller;
- efterregner prognoser for døgn, der er begyndt;
- giver F2 et PASS.

## 11. Tjekliste før C1's aktivering (alle skal være opfyldt; ellers ingen rigtig prognose)

1. F2's lås har valgt tidskonvention og dækningsregel (AMB-02/05/14 afgjort af ejer eller direktør).
2. En godkendt fremadrettet 1h-kline-strøm (G19) med vært, endpoint og kadence.
3. `c1_config/2` er frosset og hashet i en dateret PROTOCOL_V3-ændring (G18).
4. Ejerens verificerede signatur (G15) på aktiveringen.
5. Ekstern ankring af head-hashen er sat op.
6. Kontrol med `nov14_readiness.py check --action c1_activate …` uden manglende flag.
