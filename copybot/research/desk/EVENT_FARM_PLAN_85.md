# Event farm på explore0: analyseplan (UDKAST, IKKE LÅST)

**UDKAST, IKKE LÅST.** Skrevet 2026-11-11 kl. 17:38 lokal tid (16:38 UTC) af Claude efter direktørordre 85 P1, før
nogen dataadgang. Planen er ingen lås, ingen PROTOCOL_V3-ændring og ingen godkendelse. Et chat-ja låser den ikke (D5).
**Den køres ikke nu.** Tidligst 2026-11-14 00:00 UTC, og kun når alle gates i
`research/desk/EVENT_FARM_GATES_85.md` er PASS. I dag er samlet dom BLOCKED.

Motor: `research/tools/event_farm.py` (beskrivelse i `research/desk/EVENT_FARM.md`). Ordren ændrer intet i motoren.

## 1. Formål: kun beskrivende

Spørgsmålet er, om mønstrene identificeres konsistent i virkelige data. Det er ikke, om de tjener penge.

| # | Spørgsmål | Mål |
|---|---|---|
| D1 | Hvor mange hændelser og setups? | antal pr. type pr. instrument-dag og pr. 1.000 barer; setups og kædeudfald (`chain_stats`) pr. instrument-dag |
| D2 | Er tidsstemplerne konsistente? | antal brud på known_ts-reglerne (afsnit 5), resultat af trunkeringstesten |
| D3 | Hvor mange fills er tvetydige? | andel setups med en bar, der rammer både stop og mål; andel limit-fyld kun ved berøring; statusskift ved genafspilning på 1m |
| D4 | Hvor følsomt er det over for baropløsning? | D1–D3 ved 1m, 5m og 15m |
| D5 | Hvilke data mangler? | manglende minutter, ufuldstændige 5m/15m-spande, udelukkede måneder |
| D6 | Hvordan adskiller det sig fra den syntetiske null? | forholdet virkelig/null for hver størrelse i D1–D3 med interval |

**Ikke formål:** optimering af afkast, valg af "bedste" variant, påstand om edge, papirbog, aktivering, alfa eller LÅS.
explore0 er altid udforskning og aldrig bevis (PROTOCOL_V3 ændring 10 punkt 6).

## 2. Data (fastlagt før adgang)

- **Filer:** de 44 cachede `BTCUSDT-1m-YYYY-MM.zip` og `ETHUSDT-1m-YYYY-MM.zip`, 2020-03..2021-12 (Binance USD-M perp,
  `data.binance.vision`, hentet 2026-10-27 under ændring 24a). Ingen andre filer, symboler, måneder eller kilder.
- **Sted:** de læses på stedet og kun til læsning fra produktionens cache
  (`/home/anton/ecommerence/copybot/data/lab/market/klines_1m/`). Intet kopieres, intet hentes, intet netværk.
- **Navnefilter før åbning:** kun navne, der matcher `^(BTC|ETH)USDT-1m-20(20-(0[3-9]|1[0-2])|21-(0[1-9]|1[0-2]))\.zip$`.
  Alt andet afvises uåbnet. Et navn med 2024 eller 2025+ standser kørslen (afsnit 9).
- **Identitet før parsing:** navn, størrelse og sha256 pr. fil skrives i et manifest og sammenlignes med
  `research/studies/R3_m24_verify.json`. Ved afvigelse er resultatet BLOCKED. Filen hentes ikke igen og erstattes
  ikke.
- **Bar:** `(ts, o, h, l, c, v)` med ts = open_time / 1000 (millisekunder i 2020–21), o/h/l/c = kolonne 2–5, v =
  kolonne 6 (basisvolumen). En overskriftsrække springes over, som i `lab/r3.py`. Rækker uden for filens måned
  kasseres og tælles.
- **Serie:** én sammenhængende serie pr. instrument over hele explore0 (2020-03-01 00:00 til 2021-12-31 23:59 UTC,
  671 dage). Ingen opvarmning fra før vinduet (PROTOCOL_V3 afsnit 2). De første barer er tavse, indtil ATR findes.
- **Opløsninger:** 1m som de er. 5m og 15m aggregeres deterministisk fra 1m:
  - spand = floor(ts / bs) · bs;
  - o = første minuts open, h = max, l = min, c = sidste minuts close, v = sum;
  - **en spand kræver alle sine minutter** (5 eller 15). Ellers droppes den og tælles som hul. Intet interpoleres.

  Aggregering er en afledning af samme filer, ikke en ny kilde. Der findes ingen 5m-filer i cachen.
- **Primær opløsning:** 5m (motorens standard og videoens opløsning). 1m og 15m er følsomhedsanalyser.

## 3. Kode og parametre (frosset nu)

- **Motor:** `research/tools/event_farm.py`, commit f686c9a, sha256
  `7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76`. Den køres uændret.
- **Driver:** skal skrives senere, før data, som et nyt modul. Det må kun indlæse, filtrere, aggregere og kalde
  motorens funktioner uændret (`detect`, `build_setups`, `setup_outcome`, `event_outcome`, `study`, `null_run`,
  `lookahead_signal`) samt `validation_engine`. Driveren testes på syntetiske zip-filer i samme format, og dens
  sha256 skrives i den daterede ændring før data.
- **Parametre:** `DEFAULTS` uændret. Den eneste forskel pr. opløsning er `bar_seconds` (60, 300, 900). Det er
  barernes egenskab, ikke en tuningparameter.
- **Kendt konsekvens:** alle vinduer er talt i barer. `pool_lookback` og `fvg_max_age` (288) er derfor 4,8 t ved 1m,
  1 døgn ved 5m og 3 døgn ved 15m. `mss_window` (24), `fill_window` (12) og `max_hold` (48) skaleres på samme måde.
  D4 måler altså opløsning og tidsskala sammen. Det rettes ikke bagefter. Det rapporteres.
- **Omkostningsgitter** (kun til rapportering): 0, 1, 5 og 8 bps rundtur. 0–5 er nullens gitter. 8 bps = 2 × 0,040 %
  er explore0-gebyret pr. side i `lab/costreport.py`.

## 4. Varianter og slægt (som i `event_farm.py`, uændret)

**Setup-familien, `VARIANTS` (12):** anker {fvg, ob} × rr {1, 2, 3} × indgang {mid, market}:
`fvg/rr1/mid`, `fvg/rr1/market`, `fvg/rr2/mid`, `fvg/rr2/market`, `fvg/rr3/mid`, `fvg/rr3/market`,
`ob/rr1/mid`, `ob/rr1/market`, `ob/rr2/mid`, `ob/rr2/market`, `ob/rr3/mid`, `ob/rr3/market`.

**Standardkæden** (`DEFAULTS`: anker `fvg_then_ob`, rr 2, mid) bruges til tællingerne i `study()`. Dens udfald
rapporteres også og tælles derfor som en 13. setup-test.

**Hændelsesfamilien (92):** 23 typer × horisont {1, 3, 6, 12} barer. De 23 typer er de 20 basistyper i `BASE_KINDS`
plus `session_open_asia`, `session_open_london` og `session_open_ny`.

**Optælling til registret:** den primære familie ved 5m er 12 + 92 = 104, som i `v2_records()`. Alt, der rapporteres,
er 3 opløsninger × (13 + 92) = **315 tests**. Alle tælles. Ingen udelades, fordi de ser dårlige ud.

**Slægt:** i koden `event_farm/ICT-SMC-mærkning (beskrivende, null)`. Driveren bruger samme slægtsnavn med "explore0"
i stedet for "null" og to nye FUTURE-poster, `EVENT_FARM_EXPLORE0_SETUPS` og `EVENT_FARM_EXPLORE0_EVENTS`. Hvordan
slægten forholder sig til `liquidation_cascade_reversal` og `cross_sectional_momentum` i registret, afgør direktøren
(gate 12).

**Ikke med:** BOS-kæder (`chain_breaks=("bos",)` er en ekstra variant, der ville kræve en ny plan), `edge`-indgang,
`stop_buffer_atr` > 0, inducement og manipulation leg (de er ikke defineret) samt 1h-data.

## 5. Detektordefinitioner og known_ts-regler

Det autoritative er docstringen i `event_farm.py` og tabellen i `EVENT_FARM.md` afsnit 2 ved den commit, der er
fastlagt ovenfor. Kort:
- ATR(14) før og ved baren;
- swing-fraktal k = 3 (kendt ved j + 3);
- pool ved 2 swings inden for 0,10 ATR;
- sweep = væge forbi et kendt niveau og luk tilbage inden for 1 bar;
- BOS/MSS = luk forbi seneste ubrudte modsatte swing; MSS er mod trenden;
- displacement = krop > 1,2 ATR;
- OB = sidste modsatte bar blandt de 5 før en displacement;
- FVG = 3-bar-gab ≥ 0,10 ATR, med inversion ved luk igennem;
- sessionsåbninger asia 00:00, london 07:00 og ny 13:30 UTC (sommertid ikke modelleret);
- rejection = range ≥ 1 ATR og væge ≥ 60 %.

**known_ts-regler, som driveren tjekker for hver hændelse og hvert setup (D2):**
1. `known_ts` = ts for bar `known_i` + `bar_seconds`. Ved 5m/15m er det spandens slutning.
2. `i` ≤ `known_i`, og `ts` ≤ `known_ts` − `bar_seconds`.
3. For setups: `sweep_known_i` ≤ `break_known_i`, `anchor_known_i` ≤ `break_known_i` og `anchor_known_i` ≥
   sweepens `pierce_i`.
4. For udfald: en limit fyldes først på en bar efter `known_i`, og udfald bruger kun barer efter `known_i`.
5. Trunkering: `validation_engine.check_lookahead` med `lookahead_signal` (20 snit) på tre faste udsnit à 2.000 barer
   pr. instrument og opløsning: seriens start, midte og slutning. Udsnittene er valgt efter position, ikke efter
   dato eller marked.

Ethvert brud standser kørslen (afsnit 9).

## 6. Kæden sweep → MSS → FVG/OB → setup (uændret)

1. `sweep_low` (eller `sweep_high` spejlet) gemmes som seneste sweep på siden.
2. Det første `mss_bull` inden for 24 barer (målt mellem known_i) fra sweepen udløser kæden. En sweep føder højst én
   kæde.
3. Anker = seneste `fvg_bull` (anker fvg), `ob_bull` (anker ob) eller fvg ellers ob (`fvg_then_ob`), kendt mellem
   sweepens gennembrudsbar og bruddet. Uden anker tælles `no_anchor`.
4. Indgang:
   - zonens midte (mid) eller bruddets luk (market);
   - en limit på eller gennem lukket bliver market.
5. Stop = sweepens yderpunkt. Mål = indgang ± rr · risiko. Risiko under 0,25 ATR forkastes og tælles som `bad_risk`.

## 7. Fill-usikkerhed og konservative antagelser (D3)

**Reglerne i `setup_outcome`, uændret:**
- rammer en bar både stop og mål, regnes det som stop;
- på fyldbaren tæller kun stop;
- en limit fyldes til sin pris ved berøring;
- når målet nås før fyld, er setuppet `missed`;
- gap gennem stop lukker ved åbningen, gap gennem mål lukker ved målet;
- timeout efter 48 barer;
- manglende barer giver `incomplete`, som ikke tælles med.

**Hvad der rapporteres pr. variant og opløsning:**
- andel handler med mindst én bar, der rammer både stop og mål;
- forskellen i brutto R mellem `stop_first` og parentesen `target_first`;
- **andel fyld kun ved berøring** (long: barens low = indgang; short: high = indgang). Det er en optimistisk antagelse,
  fordi en rigtig limit kræver handel igennem prisen. Den rapporteres, men rettes ikke;
- **genafspilning på 1m:** hvert 5m- og 15m-setup afspilles på 1m-barerne. Indgang, stop og mål er de samme. Start er
  første minut efter spandens `known_ts`, og `fill_window` og `max_hold` ganges med bs/60, så tiden er den samme.
  Der rapporteres andelen af setups, hvis status skifter, og ændringen i brutto R. Det sker i driveren og ændrer ikke
  motoren;
- statusfordeling: mål, stop, timeout, ingen fyld, misset og ufuldstændig.

**Konservativ fortolkning:** stop-først er pessimistisk, mens berøringsfyld og manglende kø, latenstid og
delvis fyldning er optimistiske. Ingen af delene korrigeres efter data. Brutto og netto R rapporteres for alle 13
setup-tests ved hvert omkostningsniveau, og de rangordnes ikke. Ingen variant vælges til opfølgning.

## 8. Sammenligning med den syntetiske null (D6)

- **Fast null:** `null_run(seed=83, instruments=3, days=60)` uændret ved 5m. Ved 1m og 15m:
  `null_run(seed=83, instruments=3, days=60, p={"bar_seconds": bs})`, også uændret. σ pr. bar er 11 bps uanset
  opløsning. Detektorerne er ATR-skalerede, så antallene kan sammenlignes. Omkostninger i bps kan derimod ikke
  sammenlignes på tværs af opløsninger. Ved 1m og 15m sammenlignes derfor kun antal, andele og brutto R.
- **Mål:** forholdet virkelig/null pr. type (pr. instrument-dag og pr. 1.000 barer), setups pr. instrument-dag,
  kædeudfald, statusandele, andel tvetydige fyld og brutto R pr. variant. Interval: blok-bootstrap over UTC-dage (999
  træk, seed 85) på den virkelige side. Nullen er fast og trækkes ikke om.
- **Diagnostik som i `validate_null`** (lookahead, multiple testing over de 12 med max-t-blok-bootstrap, omkostninger
  ved 8 bps-gulvet). Det er beskrivelse, og intet afgøres af det.
- **Forventning skrevet før data:**
  - de ATR-skalerede typer (swing, FVG, displacement, OB, MSS/BOS) ligger inden for 0,5–2 × nullen;
  - pools og sweeps ligger højere end i nullen, fordi ens toppe er hyppigere med tick-størrelse og runde tal;
  - displacement og rejection ligger højere, fordi fordelingen har tykke haler;
  - netto R ved 8 bps er negativ for alle 12 varianter.

  Afviger det, beskrives det, men intet tilpasses.
- **Ikke med:** en hårdere null (GARCH, døgnmønster, omrøring af afkast) kræver en ny plan før data.

## 9. Datakvalitet og stopkriterier

**Kvalitet (D5), rapporteres pr. instrument og måned:**
- manifestet stemmer (punkt 2);
- `check_bars` består: endelige tal, h ≥ max(o, c), l ≤ min(o, c) og stigende ts;
- ts er et multiplum af 60 s og ligger i filens måned;
- ingen dubletter;
- dækning ≥ 99 % af måneden (PROTOCOL_V3 afsnit 3). Ellers udelukkes måneden med årsag (forventet 100 % ifølge
  R3-kontrollen);
- antal barer med h = l, antal med volumen 0 og antal med range > 20 ATR (de tælles og fjernes ikke);
- antal ufuldstændige 5m/15m-spande.

**Stop før resultater (intet tolkes, ingen delresultater bruges, intet gentages med ændrede parametre):**
- en gate er ikke PASS, eller `date -u` er før 2026-11-14 00:00;
- motorens eller driverens sha256 afviger fra den låste værdi, eller en parameter afviger fra afsnit 3;
- et filnavn ligger uden for explore0 eller nævner 2024 eller 2025+;
- manifestet afviger, en bar fejler `check_bars`, eller der er dubletter;
- et brud på known_ts-reglerne eller en trunkeringsfejl (afsnit 5);
- en undtagelse eller en afbrudt proces.

  En afbrudt proces må køres igen med samme kode og samme input (den er deterministisk), og det logges.

**En fejl i koden** kræver en dateret afvigelsestekst før en ny kørsel. Begge kørsler rapporteres.

**Afvikling:** én kørsel, lokalt og uden netværk, med `nice`, ingen samtidige tunge job, ingen deploy og ingen
genstart. pm_lp og produktionens services røres ikke.

## 10. Hvad der ikke ændres efter resultatadgang

Følgende ændres ikke: parametre, varianter, opløsninger, aggregeringsregel, omkostningsgitter, null, metrikker,
udsnit til trunkeringstesten og rapportformat. Ingen variant vælges, tilføjes eller fjernes på baggrund af et tal.
En ny idé fra resultaterne kræver en ny plan, og den kan ikke testes i explore0 som bevis.

## 11. Leverance (efter kørslen, ikke nu)

- `research/studies/EVENT_FARM_EXPLORE0_<dato>.md` og `.json`, mærket EXPLORATORY;
- indhold: manifest, kode-sha'er, D1–D6-tabeller og alle 315 tests;
- det committes uanset udfald, og registret opdateres med FUTURE→udført-posterne;
- ingen papirbog, ingen aktivering, ingen alfa og ingen LÅS.

## 12. Åbne punkter for direktøren

1. Gate 1, 1a og 1b i `EVENT_FARM_GATES_85.md`: hvem godkender, om R3's filer må bruges, og om D5 kræves.
2. Gate 12: slægtens placering i registret.
3. Skal brutto- og netto-R overhovedet rapporteres? Alternativet er kun statusandele og antal. Det skal afgøres før
   låsning.
4. Om planen skal låses som en dateret PROTOCOL_V3-ændring (forslag), og om driveren skal skrives før 14/11.
