# Event farm fremadrettet papirtest: protokolændring (UDKAST, IKKE ANVENDT)

**UDKAST, IKKE LÅST, IKKE AKTIVERET.** Claude skrev udkastet 2026-11-12 kl. 13:36 lokal tid efter direktørordre 100
("GO: DESIGN ONLY").
- Ændringens nummer og dato sættes først ved godkendelse.
- Teksten i afsnit 3 er det, som ejeren skal underskrive med D5, byte for byte.
- Intet kører, før gate-posten i `EVENT_FARM_FORWARD_GATE_ENTRY_DRAFT_100.json` er anvendt og alle dens flag er sat.
- Et ja i chatten tæller ikke.

Kode (ny og isoleret): `research/tools/event_farm_forward.py`.
Tests: `tests/test_event_farm_forward.py` (19 tests, kun syntetiske data).
Motoren `event_farm.py` er frosset på f686c9a, sha256 `7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76`.

## 1. Hvorfor, og hvad det ikke er

Ejeren vil se motoren "handle på charts" som i videoerne. Det sker her som **papirsimulering fremad i tid**:
- ingen rigtige ordrer, nøgler eller konti (G27);
- ingen alfa, ingen LÅS, ingen kandidat;
- ingen påstand om en fordel.

Den syntetiske null viser, at mønstrene opstår i ren støj (275 hændelser og 4,5 setups pr. instrument-dag), og at
setups dér ikke tjener noget (`EVENT_FARM.md` afsnit 4). Med lab'ets papiromkostninger på 28 bps pr. rundtur
forventes netto at være klart negativ (afsnit 7).

## 2. Hvad der allerede er bygget (kun syntetisk testet)

`ForwardBook` er en papirbog, der arbejder bar for bar, er idempotent og tåler genstart. Den skriver kun i sin **egen**
SQLite-fil:
- filen skal hedde `event_farm_forward*.db`;
- `lab.db`, `pm_lp.db`, produktionsstier, `research/data` og karantæne afvises, før noget åbnes.

Barer kommer **kun** fra en injiceret kilde (`provenance` + `fetch(symbol, since_ts)`):
- Modulet har ingen netværkskode.
- Live-tilstand rejser `NotActivated` uden et godkendende aktiveringsobjekt. Intet i lab'et laver et sådant i dag.
- Live-tilstand kræver præcis `BTCUSDT`, `ETHUSDT` og `FROZEN_CONFIG`.

Testene viser:
- bar for bar giver det samme som motoren offline;
- batching ændrer intet;
- en genstart midt i forløbet og et crash inde i et trin (rollback) giver den samme bog;
- huller, forsinkede, ikke-lukkede, ugyldige og reviderede barer håndteres;
- et integritetsbrud standser bogen permanent;
- omkostninger, variantstop og Register V2-planen er korrekte.

## 3. Ændringstekst (til godkendelse og D5-underskrift)

> **Ændring [nr.] ([dato] kl. [tid] lokal, før kode aktiveres og før nogen fremadrettet bar er hentet): event farm
> fremadrettet papirbog. Kun simulering, beskrivende.**
>
> 1. **Formål:** Event farm-motoren (`research/tools/event_farm.py` @ f686c9a, sha256 7c4dec89…a8524c76) kører fremad
>    i tid på lukkede 5m-barer for BTCUSDT og ETHUSDT (Binance USD-M perp). Den papirhandler hvert setup fra de 12
>    registrerede varianter (`event_farm.VARIANTS`: anker fvg/ob × 1/2/3 R × midte-limit/marked). Indgang, stop og mål
>    fastlægges ved known_ts efter motorens regler. Det er beskrivende udforskning og aldrig bevis.
> 2. **Kode:** `research/tools/event_farm_forward.py` (`ForwardBook`, `FROZEN_CONFIG`) og en separat, godkendt
>    kildeadapter. Begges sha256 skrives her, før de aktiveres. Ingen parameter ændres efter aktivering.
> 3. **Data:** kun `GET https://fapi.binance.com/fapi/v1/klines?symbol={BTCUSDT|ETHUSDT}&interval=5m` som beskrevet i
>    `EVENT_FARM_FORWARD_AMENDMENT_DRAFT_100.md` afsnit 5. Værten er allerede tilladt. Strømmen er ny og registreres i
>    `stream_registry.json`. Der hentes ingen historik før aktiveringen (ingen backfill). Opvarmning sker på de første
>    288 fremadrettede barer pr. symbol. Den er ikke unødvendig, fordi pools og FVG'er udløber efter 288 barer.
> 4. **Fills og omkostninger:**
>    - motorens regler gælder uændret: stop først på en bar, der rammer både stop og mål; på fyldbaren tæller kun
>      stop; limit fyldes ved berøring til sin pris; gap gennem stop lukker ved åbningsprisen; timeout efter 48 barer;
>    - omkostningerne er lab'ets papirbog (`lab/lane.py` COSTS): taker 0,001 + slippage 0,0002 + halv spread 0,0002
>      pr. fyld, også for limit-indgange. Det giver 28 bps pr. rundtur;
>    - notional er 1.000 USDT pr. handel, og handler kan overlappe;
>    - hver variant har en konto på 10.000 USDT og tager ikke nye handler ved 8.000 USDT eller derunder.
> 5. **Data mangler:**
>    - en manglende bar ventes på, til en lagret bar ligger 600 s efter den manglende; derefter registreres et hul;
>    - en bar, der kommer for sent, logges og behandles aldrig;
>    - handler, hvis vindue rummer et hul, er `gap_affected`. De udelades af den primære opgørelse og bogføres som stop
>      i værste-falds-opgørelsen;
>    - dækning under 95 % af de seneste 288 barer stopper nye handler for det symbol;
>    - reviderede barer logges, og den første værdi beholdes.
> 6. **Stop:** se afsnit 8 i udkastet, uændret.
> 7. **Evaluering:**
>    - rapporter efter 14, 28 og 90 dage, kun beskrivende;
>    - sammenligning med den faste null (seed 83, 5m, 3 × 60 dage);
>    - multiple testing med N ≥ 19.765 (19.438 i registret + 315 event farm-tests + de 12 her);
>    - intet resultat fra bogen er evidens for en fordel. En senere påstand kræver en ny, låst bekræftende protokol med
>      styrkeberegning før data;
>    - bogens observationer må efter G05 ikke bruges til at kalibrere eller vælge en ny hypotese.
> 8. **Ikke:** rigtige penge, ordrer eller nøgler; ændring af motor eller parametre efter start; flere symboler eller
>    timeframes; backfill; pm_lp; brug af holdout- eller 2025+-data; omgåelse af DNS-filteret.
>
> **Beslutning:** direktørens skriftlige godkendelse [ordre og linje] og ejerens D5-underskrift på sha256 af denne
> tekst [sha256, signaturfil].

## 4. Register V2-plan (i kode, ikke persisteret)

`event_farm_forward.v2_plan_records(start, slut)` laver 12 FUTURE-poster, én pr. variant (`EVENT_FARM_FWD_<variant>`).
Alle er validerede (`v2.validate` = []):
- universet er de 12 varianter;
- `variants_tested` er MISSING_INPUT indtil kørslen;
- klassifikationen er RELATED_MECHANISM uden selvstændig lineage og uden uafhængighedspåstand, som ordre 90.

**Reference-N:**

| | N |
|---|---:|
| registret (`REGISTER_COUNTS`) | 19.438 |
| + de 315 event farm-tests (talt med, selvom explore0 ikke er kørt) | **19.753** (ordrens minimum) |
| + 12 fremadrettede varianter | **19.765** (bruges i diagnostikken) |

Ved N = 19.765 og α = 0,05 er den ensidede Bonferroni-grænse z = 4,56. Det er en diagnostik, ikke en beslutningsregel.

**Datoer:** start og slut sættes ved godkendelse, og slut er start + 90 dage. Posterne skrives først til en kæde, når
ændringen er committet.

## 5. Datakilde og ressourcebudget (kun beskrevet; ingen kode og intet kald)

**Endepunkt:** `GET /fapi/v1/klines` på `fapi.binance.com`.
- Værten er allerede tilladt (`stream_registry.json` hosts.allowed_lab). Kun GET, ingen nøgle.
- Parametre: `symbol`, `interval=5m` og `startTime=<seneste lagrede open_time + 300 000 ms>`.
- `limit=3` i normal drift og `limit=499` ved indhentning.

**Vægt og kald:**
- **Normal drift:** ét kald pr. symbol pr. 5m-bar, dvs. 2 kald pr. 5 minutter = 0,4 kald i minuttet.
  `limit` < 100 har vægt 1, så det giver vægt 0,4 i minuttet af Binances 2.400 pr. IP (< 0,02 %).
- **Indhentning efter afbrydelse:** højst ét kald pr. symbol pr. gennemløb med `limit=499` (vægt 2), dvs. op til 41,6
  timer pr. kald. En længere afbrydelse indhentes over flere gennemløb. Der er aldrig flere end 2 kald pr. gennemløb.
- **Tidspunkt:** gennemløbet starter 20 s efter hver 5m-grænse (UTC).
- **Kun lukkede barer:** en række tages kun med, hvis open_time + 300 s ≤ lokal UTC-tid. Rækker med closeTime ≥
  svarets serverTime droppes. Bogen afviser desuden ikke-lukkede barer (`not_closed`).
- **Svarlog:** adapteren skal gemme UTC-tid, HTTP-status, antal rækker og sha256 af svaret for hvert kald, men ikke
  rå svar. Det sker i en tabel i bogens fil, som adapteren tilføjer. Den er ikke bygget, og `ForwardBook` har den ikke
  i dag.

**Disk:**
- 2 × 288 barer om dagen giver ca. 60 KB/dag;
- omkring 550 hændelser om dagen med payload giver ca. 200 KB/dag;
- handler og log fylder under 50 KB/dag.

I alt ca. 0,3 MB/dag og ca. 30 MB over 90 dage i én separat fil uden for `lab.db`. Ingen rå svar gemmes. Målt på
syntetiske data: 3 dage × 2 symboler fyldte 472 KB, dvs. ca. 0,16 MB/dag.

**CPU:**
- Under 0,1 s pr. gennemløb i drift; motoren arbejder trinvist.
- Ved genstart afspilles alle behandlede barer igen. Efter 90 dage er det ca. 26.000 barer pr. symbol, og det tager
  sekunder.
- Målt på syntetiske data: 2 × 864 barer bar for bar tog 2,2 s i alt (ca. 1,3 ms pr. bar), og genåbning tog 0,03 s.

**Proces:** en separat systemd `--user`-timer eller -enhed. Den skal være adskilt fra pm_lp (G12) og fra lab'ets
eksisterende supervisor, der laver deploy. Den genstarter ikke værten (G11).

**Huller og forsinkede barer:**
- afbrydelse, DNS-svigt eller HTTP-fejl giver ingen bar. Indhentning sker via `startTime` ved næste gennemløb;
- når en senere bar ligger ≥ 600 s efter en manglende, registreres hullet, og en senere ankomst logges som `late_bars`.
  Den behandles ikke, fordi motoren ikke spoler tilbage;
- 429/418-svar standser adapteren til næste gennemløb (ingen nye forsøg i samme gennemløb).

**DNS-filteret:** Det besluttes af husets netværksejer (2026-11-09) og **omgås aldrig**. Det gælder ikke anden DNS,
VPN, hosts-fil, DoH eller hotspot.
- `fapi.binance.com` er ikke testet her. Ingen GET er foretaget.
- Svarer værten ikke, bliver resultatet huller, en dækningspause og til sidst stop (afsnit 8). Der laves ingen
  omvej.

## 6. Dokumentation af tidsstempler, mangler og simuleringsusikkerhed

**Tidsstempler pr. bar:**
- `ts` (open, UTC, s);
- lukketid = ts + 300;
- gennemløbet, der modtog baren (`received_step`), og dets væguret (`steps.wall_ts`).

**Tidsstempler pr. hændelse og setup:**
- `ts` (mønstret) og `known_ts` (lukketid for den bar, setuppet blev kendt på);
- bogføringstrin, væguret og `booking_delay_s` = væguret − known_ts. Forsinkelsen rapporteres som maks og fordeling.

**Kontroller i koden:**
- en hændelse skal have known_i = den behandlede bar og known_ts = dens lukketid;
- en limit-fyld før known_ts standser bogen (IntegrityHalt).

**Mangler:**
- dækning pr. symbol og døgn (behandlede barer / slots);
- huller (antal og barer);
- for sene barer (og om de lå i et registreret hul);
- reviderede barer (og om de allerede var behandlet);
- afviste rækker pr. årsag (`not_closed`, `off_grid`, `ohlc`, `shape`);
- `gap_affected`-handler pr. variant.

**Simuleringsusikkerhed:**
- **Rækkefølgen inde i en bar er ukendt.** Bogen bruger stop først. Andelen af handler med en bar, der rammer både
  stop og mål (`both_hit`), rapporteres pr. variant.
- På **fyldbaren tæller kun stop**. Det er pessimistisk.
- **Berøringsfyld** (low = indgang ved long) er optimistisk. Andelen rapporteres (`touch_only`).
- Ingen kø, latenstid eller delvis fyldning. Alle fyld regnes som taker med slippage.
- **Huller:** den primære opgørelse er uden `gap_affected`, og værste-falds-opgørelsen regner dem som stop.
- På syntetiske data betød stop først næsten intet (4 af 5.429 handler). På rigtige 5m-barer måles det og rettes ikke.

## 7. Forventning skrevet før data

Ved 28 bps pr. rundtur og typiske stopafstande på 0,5–1 ATR koster omkostningerne alene ca. 0,8–1,4 R pr. handel.
Grundlaget er nullen, hvor 1 bps kostede 0,03–0,05 R, og den syntetiske røgtest, hvor `fvg/rr2/market` gik fra +0,37
R brutto til −0,76 R netto.

Forventningen er derfor:
- netto R pr. handel er negativ for alle 12 varianter;
- setupfrekvensen ligger nær nullens 4,5 pr. instrument-dag;
- bruttoresultatet er tæt på nul.

Afviger det, beskrives det. Der tilpasses intet.

## 8. Foruddefinerede stop- og evalueringskriterier

**Stop af hele bogen** (permanent, intet bogføres mere):
- IntegrityHalt: en hændelse eller et setup, der ikke er kendt på sin bar, dobbelt bogføring, fyld før known_ts eller
  ændret identitet (motorens sha256, config, symboler, varianter, kilde);
- direktørens eller ejerens stop (`lane-off` eller en skriftlig ordre);
- G27/G12-brud.

**Pause uden stop:**
- dækning under 95 % af de seneste 288 barer giver ingen nye handler for symbolet (`not_taken_coverage`);
- svarer kilden ikke i 24 timer, vurderer direktøren gaten igen;
- 3 eller flere reviderede, allerede behandlede barer inden for 24 timer giver manuel gennemgang.

**Variantstop:** når kontoen er ≤ 8.000 USDT (lukkede handler med udgang før setuppets known_ts), tager varianten ingen
nye handler.

**Slut:** 90 dage efter første behandlede bar tages ingen nye handler. Åbne handler afvikles efter reglerne.

**Rapporter** (kun beskrivende, mærket "PAPIR / SIMULERING", uanset udfald):

| dag | indhold |
|---|---|
| 14 | datakvalitet, dækning, hændelsesfrekvens, setupfrekvens, statusandele og fill-usikkerhed. Ingen R-konklusion |
| 28 | som dag 14 plus R pr. variant i et bilag |
| 90 | slutrapport: primært frekvenser, statusandele, fill-usikkerhed og dækning mod nullen. R brutto, netto (lab) og nullens omkostningsgitter (0/1/5/8 bps) står i bilag, uden rangordning |

**Null:** `event_farm.null_run(seed=83, instruments=3, days=60)` ved 5m, uændret. Nullen trækkes ikke om.

| | null |
|---|---:|
| hændelser pr. instrument-dag | 274,7 |
| setups pr. instrument-dag | 4,5 (standardkæden) |
| R brutto, puljet over alle varianter | −0,020 |
| netto ved 5 bps | negativt for alle 12 |

**To ugers observation er ikke dokumentation for en fordel.**
- Med ca. 4,5 setups pr. instrument-dag og 2 symboler giver 14 dage ca. 126 setups pr. variant. Heraf fyldes cirka
  40–100 % (limit eller marked), dvs. ca. 50–125 handler.
- Standardfejlen på middel-R er ca. 1/√n ≈ 0,09–0,14 R.
- At påvise +0,1 R pr. handel ved N = 19.765 (z = 4,56) med 80 % styrke kræver ca. ((4,56 + 0,84)/0,1)² ≈ 2.900
  handler pr. variant. Det svarer til år, ikke uger.
- Ingen 14-, 28- eller 90-dages rapport kan derfor vise en fordel. Den kan kun beskrive frekvenser, datakvalitet og
  simuleringsusikkerhed.

## 9. Krav før aktivering (fail-closed, se gate-posten)

1. Direktørens skriftlige godkendelse af afsnit 3.
2. Ændringen committet i `PROTOCOL_V3.md` før nogen fremadrettet bar hentes.
3. D5 forankret uafhængigt (`OWNER_KEY_GUIDE_D5.md` afsnit 5) og ejerens underskrift på sha256 af afsnit 3's endelige
   tekst. Den er i dag PENDING_INDEPENDENT_ANCHOR, så gaten er lukket.
4. Strømmen er godkendt i `stream_registry.json` med vært, endepunkt, takt og budget som i afsnit 5. G19 dækker kun
   1h og gælder ikke automatisk.
5. Kildeadapteren og `event_farm_forward.py` er committet med grønne tests, og deres sha256 står i ændringen.
6. Værten svarer uden omgåelse.

Claude underskriver aldrig, laver aldrig nøglen og aktiverer ikke (G28).
