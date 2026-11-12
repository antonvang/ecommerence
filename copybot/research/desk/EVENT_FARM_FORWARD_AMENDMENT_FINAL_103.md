# Ændring: event farm fremadrettet papirbog (96 tests, 5m BTCUSDT/ETHUSDT) — endelig tekst 103

Claude skrev teksten 2026-11-12 kl. 14:49 lokal tid efter direktørordre 103. Ejeren underskriver præcis denne fil,
hvis sha256 står i `EVENT_FARM_FORWARD_AMENDMENT_FINAL_103.sha256`. Filen indsættes uændret i `PROTOCOL_V3.md` under
en overskrift med nummer og dato. En ændret byte kræver ny underskrift. Teksten afløser udkast 100 og endelig tekst 102.

Status: **UDKAST, IKKE LÅST, IKKE AKTIVERET.**

## 1. Hvad

Den frosne event farm-motor kører fremad i tid på lukkede 5m-barer for BTCUSDT og ETHUSDT (Binance USD-M perp) og
papirhandler 96 forhåndsregistrerede tests:
- 12 baseline-varianter;
- de samme 12 med 7 kontekstfilterkombinationer (F1 1t-trend, F2 gårsdagens high/low med retest, F3 VWAP-afstand).

Det er kun simulering og beskrivende:
- ingen rigtige ordrer, nøgler eller konti;
- ingen alfa, ingen lås, ingen kandidat;
- ingen påstand om en fordel;
- observationerne bruges ikke til at vælge eller kalibrere en ny hypotese (G05).

## 2. Kode og referencer (sha256; en afvigelse forhindrer kørsel)

| fil | sha256 |
|---|---|
| `research/tools/event_farm.py` (motor, f686c9a) | `7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76` |
| `research/tools/event_farm_driver.py` | `4b96e202266e3a5f0c8655e0ec30eefc8c170ba3b183cd97c5bf0815799b5be5` |
| `research/tools/event_farm_filters.py` | `1886b6f311e5eeae0d4c1a7ddbb3ad23fdead761fd0fb8ef6b0a40204aaf787c` |
| `research/tools/event_farm_forward.py` | `f25feba8f9c2bb86c962dfb56cce765d048919aa921f34429d2192917d32deac` |
| `research/tools/event_farm_forward_v2.py` | `ae8e57affae121cfc47148ab18ae211cb1e92ce20da510c2f7b28fa41a38b127` |
| `research/tools/event_farm_source.py` (adapter) | `05907e03fe75520dacd57f4445295e1090d46996a38787a198b2ce8afa2462b7` |
| `research/desk/EVENT_FARM_FORWARD_FILTERS_DRAFT_101.md` (filterdefinitioner og begrundelser) | `080ca5b071969810b7b058eb1759d9d3fd52441e3b54eff67e16543ea5bb2ef6` |
| `research/desk/EVENT_FARM.md` (motorens definitioner og null) | `fe11a89b02003c1f3ec677fad30bb429f99bc7c967dbfe35a9fd93576b7ae10e` |

**Kørsel:** `ForwardBookV2` i live-tilstand med `FROZEN_CONFIG` og `FILTER_PARAMS` uændret, kilde `KlineSource`.
- Begge kræver et godkendende aktiveringsobjekt. Uden det rejses `NotActivated`, før noget kald.
- Bogen skriver kun i sin egen fil `event_farm_forward*.db`.
- Adapteren skriver kun en append-only, hash-kædet kald-log `event_farm_source_calls*.jsonl`.

## 3. Datakilde

`GET https://fapi.binance.com/fapi/v1/klines?symbol={BTCUSDT|ETHUSDT}&interval=5m&startTime=<ms>&limit=<3|499>`.
Intet andet: `check_url` afviser alle andre værter, stier og parametre, nøgler, signaturer og ordre- og kontoendepunkter.

**Felter:** [0] open time (ms), [1]–[4] OHLC, [5] volumen (base) og [6] close time, som skal være præcis [0] +
299.999. Volumen og tidsstempler logges uændret pr. bar.

**Kald:**
- ét pr. symbol pr. 5m-slot, 20 s efter grænsen. Hvert kald starter ved den senest lagrede bar, så revisioner opdages;
- `limit=3` (vægt 1) i drift og `limit=499` (vægt 2) efter en pause;
- det giver 0,4 kald og vægt 0,4 i minuttet af 2.400;
- ingen backfill: intet før aktiveringsslottet. Opvarmning er de første 288 barer.

**Fail-closed:** hele svaret afvises ved:
- transportfejl eller timeout (10 s), status ≠ 200, ugyldig JSON;
- en fejlformet, dobbelt, uordnet eller for tidlig række;
- forkert close time eller ugyldig OHLCV.

Barer, der ikke er lukket, droppes og hentes igen senere. 429/418 giver pause i mindst 300 s eller Retry-After.

**Netværk:** DNS-filteret omgås aldrig. Svarer værten ikke, bliver resultatet huller og pauser efter afsnit 5.

## 4. Fills og omkostninger

Motorens regler gælder:
- rammer en bar både stop og mål, tæller det som stop;
- på fyldbaren tæller kun stop;
- en limit fyldes ved berøring;
- gap gennem stop lukker ved åbningsprisen;
- timeout efter 48 barer.

Hver test har sin egen papirkonto på 10.000 USDT med 1.000 USDT notional pr. handel.

**28 bps pr. rundtur er en ANTAGELSE, ikke verificerede fremtidige omkostninger.** Det er lab'ets papirmodel: taker
0,001, slippage 0,0002 og halv spread 0,0002 pr. fyld. Rapporten viser desuden netto ved 0/1/5/8 bps.

## 5. Datamangler og stop

**Huller og revisioner:**
- en manglende bar ventes på i 600 s; derefter registreres et hul;
- for sene barer logges og behandles ikke;
- reviderede barer går i konfliktloggen, og den første værdi beholdes.

**Filtre:**
- F1 bruger kun 1t-barer med alle 12 5m-barer;
- F3 er BLOCKED resten af UTC-døgnet efter en manglende bar eller en volumen ≤ 0.

**Pause:**
- dækning under 95 % af de seneste 288 barer giver ingen nye handler for symbolet;
- svarer kilden ikke i 24 timer, vurderes gaten igen;
- 3 eller flere reviderede, behandlede barer på 24 timer giver manuel gennemgang.

**Handler med hul:** `gap_affected`. De er ude af den primære opgørelse og bogføres som stop i værste-falds-opgørelsen.

**Stop af hele bogen:**
- IntegrityHalt: noget, der ikke er kendt på sin bar, dobbelt bogføring, fyld før known_ts eller ændret identitet
  (kode, config, kilde);
- en brudt kald-log;
- `lane-off` eller en skriftlig ordre;
- brud på G27 eller G12.

**Test og slut:** en test med konto ≤ 8.000 USDT tager ingen nye handler. Efter 90 dage tages ingen nye handler.

## 6. Evaluering

**Rapporter efter 14, 28 og 90 dage**, beskrivende og mærket PAPIR / SIMULERING, uanset udfald.
- **Primært:** frekvenser, statusandele, fill-usikkerhed (andel med en bar, der rammer både stop og mål, og andel fyld
  ved berøring), dækning, huller, revisioner, F3-blokeringer og kald-loggens fejl.
- **Bilag:** R brutto og netto pr. test, uden rangordning.

**Null:** seed 83 (`null_run` og `null_with_filters`, 3 × 60 dage) står side om side og trækkes ikke om. Netto ved 28 bps
er negativt for baseline og alle kombinationer undtagen F2+F3, hvis plus er én handel. F1+F2+F3 har ingen handler.

**Multiple testing:** familien er 96. N = 19.849 (19.438 + 315 + 96). Register V2: 19 FUTURE-poster
(`event_farm_forward_v2.v2_final_records`) med univers 96, RELATED_MECHANISM og uden uafhængighedspåstand. Datoerne
sættes ved aktivering.

**To uger er ingen dokumentation.** At påvise +0,1 R ved N = 19.849 med 80 % styrke kræver ca. 2.900 handler pr. test.
En påstand kræver en ny, låst, bekræftende protokol.

## 7. Ressourcer (målt på syntetiske data via loopback)

| | |
|---|---|
| kald | 576 pr. døgn (2 symboler × 288 slots) |
| kald-log | ca. 250 KB pr. døgn |
| bogens fil | ca. 220 KB pr. døgn |
| CPU | ca. 2 s pr. døgn |

Over 90 dage giver det under 50 MB i to separate filer. Det kører som en systemd `--user`-enhed uden genstart af værten
(G11) og uden at røre pm_lp (G12).

## 8. Før aktivering (fail-closed)

1. Direktørens skriftlige godkendelse af denne tekst.
2. Teksten committet i `PROTOCOL_V3.md`, før noget kald.
3. Ejerens D5-underskrift (D5 ANCHORED, beslutning 97) på denne fils sha256, verificeret med `owner_approval.py`.
   G15 vurderes særskilt.
4. G31 anvendt i `GATE_MATRIX.json` med alle flag sat.
5. 5m-strømmen godkendt i `stream_registry.json`.
6. Koden committet med de sha256, der står ovenfor, og grønne tests.
7. Værten svarer uden omgåelse.

Claude underskriver ikke, laver ingen nøgle og aktiverer ikke (G28).
