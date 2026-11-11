# Event farm på explore0: analyseplan v2 (UDKAST, IKKE LÅST)

**UDKAST, IKKE LÅST.** Skrevet 2026-11-11 kl. 17:48 lokal tid (16:48 UTC) af Claude efter direktørordre 88 P2
("DESIGN GO, DATA ACCESS BLOCKED"). Planen afløser `EVENT_FARM_PLAN_85.md`, som står uændret som historik. Den er
ingen lås og ingen godkendelse og kører ikke nu. Dataadgang kræver de gates, der er beskrevet i
`research/desk/EVENT_FARM_AMENDMENT_DRAFT_88.md` og `research/desk/EVENT_FARM_GATE_ENTRY_DRAFT_88.json`: tidligst
2026-11-14 00:00 UTC, direktørens godkendelse, en committet ændring før data og verificeret D5/G15. Et chat-ja tæller
ikke.

**Ændringer fra v1 (ordre 88):**
- de primære mål er nu hændelsesfrekvens, setupfrekvens, known_ts-konsistens, statusandele og fill-usikkerhed;
- R er kun en sekundær beskrivelse;
- de 315 tests registreres samlet som multiple-testing-eksponering;
- R3-overlappet behandles som tidligere eksponeret forskning (afsnit 3).

## 1. Formål og mål

Planen er kun beskrivende. Spørgsmålet er, om mønstrene identificeres konsistent i virkelige data.

**Primære mål** (hovedresultatet, rapporteres først):

| # | Mål | Definition |
|---|---|---|
| P1 | Hændelsesfrekvens | antal pr. type (23 typer) pr. instrument-dag og pr. 1.000 barer |
| P2 | Setupfrekvens | setups pr. instrument-dag for standardkæden og de 12 varianter samt kædeudfald (`sweep_break`, `no_anchor`, `bad_risk`, `setup`) |
| P3 | known_ts-konsistens | antal brud på reglerne i afsnit 6 (forventet 0) og trunkeringstestens resultat |
| P4 | Statusandele | andel mål, stop, timeout, ingen fyld, misset og ufuldstændig pr. variant |
| P5 | Fill-usikkerhed | andel med en bar, der rammer både stop og mål; andel fyld kun ved berøring; statusskift ved genafspilning på 1m (afsnit 8) |

**Støttemål:**
- datamangler (afsnit 10);
- følsomhed over for baropløsning (P1–P5 ved 1m, 5m og 15m);
- forholdet til den syntetiske null for P1, P2, P4 og P5 (afsnit 9).

**Sekundær beskrivelse (ikke hovedresultat):**
- brutto og netto R pr. variant;
- R vises kun i et bilag, samlet for alle 13 setup-tests;
- ingen rangordning, ingen fremhævning, ingen "bedste variant" og ingen konklusion om afkast eller edge.

**Ikke formål:** optimering, valg af variant, papirbog, aktivering, alfa eller LÅS. explore0 er aldrig bevis
(PROTOCOL_V3 ændring 10 punkt 6).

## 2. Data (fastlagt før adgang)

- **Filer:** de 44 cachede `BTCUSDT-1m-YYYY-MM.zip` og `ETHUSDT-1m-YYYY-MM.zip`, 2020-03..2021-12 (USD-M perp, hentet
  2026-10-27 under ændring 24a). Ingen andre filer, symboler, måneder eller kilder.
- **Sted:** de læses på stedet og kun til læsning i produktionens cache
  `/home/anton/ecommerence/copybot/data/lab/market/klines_1m/`. Intet kopieres, intet hentes, intet netværk.
- **Navnefilter før åbning:** `^(BTC|ETH)USDT-1m-20(20-(0[3-9]|1[0-2])|21-(0[1-9]|1[0-2]))\.zip$`. Alt andet afvises
  uåbnet. Et navn med 2024 eller 2025+ standser kørslen.
- **Identitet før parsing:** et manifest med navn, størrelse og sha256 sammenlignes med
  `research/studies/R3_m24_verify.json`. Ved afvigelse er resultatet BLOCKED. Intet hentes igen, og intet erstattes.
- **Bar:** `(ts, o, h, l, c, v)` med ts = open_time / 1000, o/h/l/c = kolonne 2–5 og v = kolonne 6. En overskriftsrække
  springes over. Rækker uden for filens måned kasseres og tælles.
- **Serie:** én pr. instrument over 2020-03-01 00:00..2021-12-31 23:59 UTC (671 dage), uden opvarmning fra før
  vinduet.
- **Aggregering til 5m og 15m:**
  - spand = floor(ts / bs) · bs;
  - o = første minuts open, h = max, l = min, c = sidste minuts close, v = sum;
  - en spand kræver alle sine minutter, ellers droppes den og tælles som hul;
  - intet interpoleres.

  Aggregeringen er en afledning af samme filer, ikke en ny kilde.
- **Primær opløsning:** 5m aggregeret fra 1m. 1m (som filerne er) og 15m (aggregeret) er følsomhedsanalyser.

## 3. Tidligere eksponering (R3-overlap)

Filerne er **tidligere eksponeret forskning**. R3_m24 læste dem i én screening 2026-10-27 (SCREEN_FAIL, p 0,918).
explore0 er brugt af banen og m17/m21. Beslægtede reversal-slægter (`MOVESCREEN_m21c`, `E_daily_reversal_p1`, `L21`)
og trend-slægter (`L03`, `L14_tsmom_v1`, `E_donchian_trend_*`) er prøvet i samme vindue eller på samme mønter.
Begrundelsen står i `EVENT_FARM_AMENDMENT_DRAFT_88.md` afsnit 2.

**Konsekvens for planen:**
- intet resultat behandles som et uafhængigt holdout eller som validering;
- R3's nøgle, regel og resultat bruges ikke og ændres ikke;
- rapporten skal i sin første linje sige, at data er tidligere eksponerede, og at resultatet kun er beskrivende;
- der vælges ingen fortsættelse ud fra resultatet. En senere test af en idé herfra kræver nye, ikke-eksponerede data
  og sin egen plan før data.

## 4. Kode og parametre (frosset)

- **Motor:** `research/tools/event_farm.py` @ f686c9a, sha256
  `7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76`, uændret.
- **Driver:** skrives senere, før data, som et nyt modul. Det må kun indlæse, filtrere, aggregere og kalde motorens
  funktioner uændret (`detect`, `build_setups`, `setup_outcome`, `event_outcome`, `study`, `null_run`,
  `lookahead_signal`) samt `validation_engine`. Driveren testes på syntetiske zip-filer, og dens sha256 skrives i
  ændringen.
- **Parametre:** `DEFAULTS` uændret. Pr. opløsning varierer kun `bar_seconds` (60, 300 eller 900).
- **Kendt konsekvens:** vinduerne er talt i barer. `pool_lookback` og `fvg_max_age` (288) svarer derfor til 4,8 t,
  1 døgn eller 3 døgn, og `mss_window`, `fill_window` og `max_hold` skaleres på samme måde. Det rapporteres og rettes
  ikke.
- **Omkostningsgitter** (kun til den sekundære R): 0, 1, 5 og 8 bps rundtur. 8 bps = 2 × 0,040 % explore0-gebyr pr.
  side (`lab/costreport.py`).

## 5. Varianter, slægt og multiple-testing-eksponering

- **`VARIANTS` (12), uændret:** `fvg/rr1/mid`, `fvg/rr1/market`, `fvg/rr2/mid`, `fvg/rr2/market`, `fvg/rr3/mid`,
  `fvg/rr3/market`, `ob/rr1/mid`, `ob/rr1/market`, `ob/rr2/mid`, `ob/rr2/market`, `ob/rr3/mid`, `ob/rr3/market`.
- **Standardkæden** (`fvg_then_ob`, rr 2, mid) giver tællingerne i `study()` og tælles som 13. setup-test.
- **Hændelsesfamilien:** 23 typer (20 `BASE_KINDS` og 3 sessionsåbninger) × horisont {1, 3, 6, 12} = 92.
- **Samlet eksponering: 3 opløsninger × (13 + 92) = 315 tests.** Alle 315 registreres i Register V2 som én samlet
  multiple-testing-eksponering:
  - post `EVENT_FARM_EXPLORE0_SETUPS`: 39 setup-tests;
  - post `EVENT_FARM_EXPLORE0_EVENTS`: 276 hændelsestests;
  - begge med `trial_universe.size` = 315 og samme referenceeksponering.

  Registrets konservative reference-N stiger tilsvarende (fra 19.438 til mindst 19.753). Ingen test udelades, og
  ingen tælles fra efter resultatet.
- **Slægt:** i koden `event_farm/ICT-SMC-mærkning (beskrivende, null)`. Driveren skriver
  `event_farm/ICT-SMC-mærkning (beskrivende, explore0)`. Placeringen i forhold til `liquidation_cascade_reversal` og
  `cross_sectional_momentum` afgør direktøren.
- **Ikke med:**
  - BOS-kæder;
  - `edge`-indgang;
  - `stop_buffer_atr` > 0;
  - inducement og manipulation leg;
  - 1h-data, andre symboler og andre måneder.

## 6. Detektorer og known_ts-regler (P3)

Det autoritative er docstringen i `event_farm.py` og `EVENT_FARM.md` afsnit 2 ved commit f686c9a. Kort:
- ATR(14);
- swing-fraktal k = 3;
- pool ved 2 swings inden for 0,10 ATR;
- sweep = væge forbi et kendt niveau og luk tilbage inden for 1 bar;
- BOS/MSS = luk forbi seneste ubrudte modsatte swing; MSS er mod trenden;
- displacement = krop > 1,2 ATR;
- OB = sidste modsatte bar blandt 5;
- FVG ≥ 0,10 ATR med inversion;
- sessionsåbninger 00:00, 07:00 og 13:30 UTC (uden sommertid);
- rejection = range ≥ 1 ATR og væge ≥ 60 %.

**Regler, som driveren tjekker for hver hændelse og hvert setup:**
1. `known_ts` = ts(bar `known_i`) + `bar_seconds`. Ved 5m og 15m er det spandens slutning.
2. `i` ≤ `known_i`, og `ts` ≤ `known_ts` − `bar_seconds`.
3. For setups gælder `sweep_known_i` ≤ `break_known_i`, `anchor_known_i` ≤ `break_known_i` og `anchor_known_i` ≥
   `pierce_i`.
4. En limit fyldes først efter `known_i`, og udfald bruger kun barer efter `known_i`.
5. Trunkeringstesten: `validation_engine.check_lookahead` med `lookahead_signal` (20 snit) på tre udsnit à 2.000 barer
   pr. instrument og opløsning (start, midte og slutning efter position).

Ethvert brud standser kørslen.

## 7. Kæden sweep → MSS → FVG/OB → setup (uændret)

1. Kæden starter med en sweep.
2. Det første MSS inden for 24 barer (mellem `known_i`) udløser den. En sweep føder højst én kæde.
3. Ankeret er seneste FVG/OB, der er kendt mellem sweepens gennembrudsbar og bruddet. Uden anker tælles `no_anchor`.
4. Indgang:
   - mid eller market;
   - en limit gennem lukket bliver market.
5. Stop = sweepens yderpunkt. Mål = indgang ± rr · risiko. Risiko under 0,25 ATR forkastes og tælles som `bad_risk`.

## 8. Fill-usikkerhed (P4, P5)

**Reglerne i `setup_outcome`, uændret:**
- en bar, der rammer både stop og mål, regnes som stop;
- på fyldbaren tæller kun stop;
- en limit fyldes til sin pris ved berøring;
- når målet nås før fyld, er setuppet `missed`;
- gap gennem stop lukker ved åbningen, gap gennem mål lukker ved målet;
- timeout efter 48 barer;
- `incomplete` tælles ikke med.

**Rapporteres pr. variant og opløsning:**
- statusandele (P4);
- andel handler med en bar, der rammer både stop og mål;
- andel fyld kun ved berøring (long: low = indgang; short: high = indgang). Det er optimistisk og rettes ikke;
- genafspilning på 1m af hvert 5m- og 15m-setup med samme indgang, stop og mål. Start er første minut efter
  `known_ts`, og `fill_window` og `max_hold` ganges med bs/60. Der rapporteres andelen af setups, hvis status skifter,
  og skiftematricen. Det sker i driveren, og motoren ændres ikke.

**Antagelserne går begge veje:** stop-først er pessimistisk, mens berøringsfyld og manglende kø, latenstid og
delvis fyldning er optimistiske. Intet korrigeres efter data.

## 9. Sammenligning med den syntetiske null

- **Fast null:**
  - `null_run(seed=83, instruments=3, days=60)` uændret ved 5m;
  - `null_run(seed=83, instruments=3, days=60, p={"bar_seconds": bs})` ved 1m og 15m.

  Nullen trækkes ikke om.
- **Primær sammenligning:** forholdet virkelig/null for P1, P2, P4 og P5 med blok-bootstrap over UTC-dage (999 træk,
  seed 85) på den virkelige side.
- **Sekundær:** brutto R pr. variant ved siden af nullens, kun i bilaget. Omkostninger i bps sammenlignes kun ved 5m.
- **Diagnostik:** lookahead og multiple testing. `check_multiple_testing` bruger `n_tested` = 315 og
  `n_preregistered` = 315. Det er beskrivelse, og intet afgøres af det.
- **Forventning skrevet før data:**
  - de ATR-skalerede typer ligger inden for 0,5–2 × nullen;
  - pools og sweeps ligger højere (ens toppe ved tick-størrelse og runde tal);
  - displacement og rejection ligger højere (tykke haler);
  - netto R ved 8 bps er negativ for alle 12.

  Afviger det, beskrives det, men intet tilpasses.
- **Ikke med:** en hårdere null (GARCH, døgnmønster) kræver en ny plan før data.

## 10. Datakvalitet og stopkriterier

**Kvalitet, rapporteres pr. instrument og måned:**
- manifestet stemmer;
- `check_bars` består;
- ts er et multiplum af 60 s og ligger i filens måned;
- ingen dubletter;
- dækning ≥ 99 % (PROTOCOL_V3 afsnit 3). Ellers udelukkes måneden med årsag (forventet 100 %);
- antal barer med h = l, med volumen 0 og med range > 20 ATR (de tælles og fjernes ikke);
- antal ufuldstændige spande.

**Stop før resultater** (intet tolkes, intet gentages med ændrede parametre):
- en gate er ikke PASS, eller `date -u` er før 2026-11-14;
- motorens eller driverens sha256 afviger, eller en parameter afviger;
- et filnavn ligger uden for explore0 eller nævner 2024 eller 2025+;
- manifestet afviger, `check_bars` fejler, eller der er dubletter;
- et brud på known_ts-reglerne eller en trunkeringsfejl;
- en undtagelse.

En afbrudt proces må køres igen med samme kode og samme input, og det logges. En kodefejl kræver en dateret
afvigelsestekst før en ny kørsel, og begge kørsler rapporteres.

**Afvikling:** én kørsel, lokalt, uden netværk, med `nice`, ingen samtidige tunge job, ingen deploy og ingen genstart.
pm_lp røres ikke.

## 11. Fastlåst efter resultatadgang

Følgende ændres ikke, når resultaterne er set: parametre, varianter, opløsninger, aggregering, omkostningsgitter, null,
primære og sekundære mål, trunkeringsudsnit, testantal (315) og rapportformat. Ingen variant vælges, tilføjes eller
fjernes på baggrund af et tal.

## 12. Leverance (efter kørslen, ikke nu)

`research/studies/EVENT_FARM_EXPLORE0_<dato>.md` og `.json`, mærket EXPLORATORY og "tidligere eksponerede data".
Rækkefølgen er:
1. manifest og kode-sha'er;
2. P1–P5 pr. opløsning;
3. datamangler;
4. null-sammenligning;
5. bilag med R for alle 13 setup-tests.

Det committes uanset udfald, og begge Register V2-poster opdateres. Ingen papirbog, aktivering, alfa eller LÅS.

## 13. Åbne punkter for direktøren

1. Godkendelse af ændringsforslaget og GATE_MATRIX-posten, og om G15/D5 kræves. Udkastet kræver det (fail-closed).
2. Slægtens placering i registret.
3. Om driveren må skrives og testes på syntetiske filer før 14/11 (ingen dataadgang).
