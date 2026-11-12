# Ændring: event farm fremadrettet papirbog (96 tests, 5m BTCUSDT/ETHUSDT) — endelig tekst 104

Claude skrev teksten 2026-11-12 kl. 15:11 lokal tid efter direktørbeslutning 104. Ejeren underskriver præcis denne
fil, hvis sha256 står i `EVENT_FARM_FORWARD_AMENDMENT_FINAL_104.sha256`. Filen indsættes uændret i `PROTOCOL_V3.md`
under en overskrift med nummer og dato; en ændret byte kræver ny underskrift. Afløser udkast 100 og tekst 102 og 103.
Ændret fra 103: kun afsnit 4 (omkostningernes enhed) og 5 (revisioner) er præciseret; kode og hashes er uændrede.

Status: **UDKAST, IKKE LÅST, IKKE AKTIVERET.**

## 1. Hvad

Den frosne event farm-motor kører fremad i tid på lukkede 5m-barer for BTCUSDT og ETHUSDT (Binance USD-M perp) og
papirhandler 96 forhåndsregistrerede tests:
- 12 baseline-varianter;
- de samme 12 med 7 kontekstfilterkombinationer (F1 1t-trend, F2 gårsdagens high/low med retest, F3 VWAP-afstand).

Kun simulering og beskrivende: ingen rigtige ordrer, nøgler eller konti, ingen alfa, lås eller kandidat, ingen påstand
om en fordel. Observationerne bruges ikke til at vælge eller kalibrere en ny hypotese (G05).

## 2. Kode og referencer (sha256; en afvigelse forhindrer kørsel)

| fil | sha256 |
|---|---|
| `research/tools/event_farm.py` (motor, f686c9a) | `7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76` |
| `research/tools/event_farm_driver.py` | `4b96e202266e3a5f0c8655e0ec30eefc8c170ba3b183cd97c5bf0815799b5be5` |
| `research/tools/event_farm_filters.py` | `1886b6f311e5eeae0d4c1a7ddbb3ad23fdead761fd0fb8ef6b0a40204aaf787c` |
| `research/tools/event_farm_forward.py` | `f25feba8f9c2bb86c962dfb56cce765d048919aa921f34429d2192917d32deac` |
| `research/tools/event_farm_forward_v2.py` | `ae8e57affae121cfc47148ab18ae211cb1e92ce20da510c2f7b28fa41a38b127` |
| `research/tools/event_farm_source.py` (adapter) | `05907e03fe75520dacd57f4445295e1090d46996a38787a198b2ce8afa2462b7` |
| `research/desk/EVENT_FARM_FORWARD_FILTERS_DRAFT_101.md` (filterdefinitioner) | `080ca5b071969810b7b058eb1759d9d3fd52441e3b54eff67e16543ea5bb2ef6` |
| `research/desk/EVENT_FARM.md` (motor og null) | `fe11a89b02003c1f3ec677fad30bb429f99bc7c967dbfe35a9fd93576b7ae10e` |

**Kørsel:** `ForwardBookV2` (live, `FROZEN_CONFIG` og `FILTER_PARAMS` uændret) med kilden `KlineSource`. Begge kræver
et godkendende aktiveringsobjekt, ellers `NotActivated` før noget kald. Bogen skriver kun `event_farm_forward*.db`,
adapteren kun en append-only, hash-kædet kald-log `event_farm_source_calls*.jsonl`.

## 3. Datakilde

`GET https://fapi.binance.com/fapi/v1/klines?symbol={BTCUSDT|ETHUSDT}&interval=5m&startTime=<ms>&limit=<3|499>`.
Intet andet: `check_url` afviser andre værter, stier, parametre, nøgler, signaturer og ordre- og kontoendepunkter.

**Felter:** [0] open time (ms), [1]–[4] OHLC, [5] volumen (base) og [6] close time, som skal være præcis [0] +
299.999. Volumen og tidsstempler logges uændret pr. bar.

**Kald:** ét pr. symbol pr. 5m-slot, 20 s efter grænsen, startende ved den senest lagrede bar (så revisioner ses);
`limit=3` (vægt 1), efter en pause `limit=499` (vægt 2); 0,4 kald og vægt 0,4 i minuttet af 2.400. Ingen backfill:
intet før aktiveringsslottet; opvarmning er de første 288 barer.

**Fail-closed:** hele svaret afvises ved transportfejl eller timeout (10 s), status ≠ 200, ugyldig JSON, en fejlformet,
dobbelt, uordnet eller for tidlig række, forkert close time eller ugyldig OHLCV.

Ikke-lukkede barer droppes og hentes senere. 429/418 giver pause i mindst 300 s eller Retry-After.

**Netværk:** DNS-filteret omgås aldrig. Svarer værten ikke, bliver resultatet huller og pauser efter afsnit 5.

## 4. Fills og omkostninger

Motorens regler gælder: en bar, der rammer både stop og mål, tæller som stop; på fyldbaren tæller kun stop; en limit
fyldes ved berøring; gap gennem stop lukker ved åbningsprisen; timeout efter 48 barer.

Hver test har sin egen papirkonto på 10.000 USDT med 1.000 USDT notional pr. handel.

**Omkostninger: 28 bps pr. rundtur er en ANTAGELSE, ikke verificerede fremtidige omkostninger.**
- **Opbygning:** 2 fyld × (taker 10 + slippage 2 + halv spread 2) bps = 28 bps pr. rundtur. Det er lab'ets papirmodel
  (`lab/lane.py` COSTS: taker 0,001, slippage 0,0002, spread 0,0004). Også limit-indgange belastes som taker.
- **I koden** (`event_farm_forward.lab_costs`): gebyr = 0,001 × (indgangs- + udgangsnotional), ugunstig pris =
  (0,0002 + 0,0002) × (indgangs- + udgangsnotional), netto = brutto − gebyr − ugunstig pris. Præcis rundtur = 14 bps ×
  (1 + exit/entry) af indgangsnotional ≈ 28 bps.
- **Følsomhederne 0/1/5/8 bps** er SAMLEDE rundturomkostninger i bps af indgangsnotional. De ERSTATTER de 28 bps; de
  lægges ikke oveni og er ikke ekstra slippage. Formlen er netto R = brutto R − c·10⁻⁴·entry/risk, samme formel som
  motorens `cost_bps` i nullen.
- **Værste fald for hul-handler:** −1 R − 28 bps (2 × 0,0014 × entry/risk).

## 5. Datamangler og stop

**Huller og revisioner:**
- en manglende bar ventes på i 600 s, derefter et hul; for sene barer logges og behandles ikke;
- **revisioner:** en revideret bar (samme ts, andre værdier) ændrer aldrig noget bogført. Første lagrede værdi
  beholdes, revisionen skrives i `conflicts` (med flag for behandlet), og intet genberegnes bagud (hændelser, signaler,
  fills, resultater), heller ikke efter genstart, der afspiller førsteværdierne (`tests/test_event_farm_revisions_104.py`).

**Filtre:** F1 bruger kun 1t-barer med alle 12 5m-barer; F3 er BLOCKED resten af UTC-døgnet efter en manglende bar
eller volumen ≤ 0.

**Pause:** dækning under 95 % af de seneste 288 barer giver ingen nye handler for symbolet; 24 timer uden svar fra
kilden giver ny gatevurdering; 3 eller flere reviderede, behandlede barer på 24 timer giver manuel gennemgang.

**Handler med hul:** `gap_affected`. De er ude af den primære opgørelse og bogføres som stop i værste-falds-opgørelsen.

**Stop af hele bogen:** IntegrityHalt (noget ikke kendt på sin bar, dobbelt bogføring, fyld før known_ts, ændret
identitet: kode, config, kilde), en brudt kald-log, `lane-off` eller en skriftlig ordre, brud på G27 eller G12.

**Test og slut:** en test med konto ≤ 8.000 USDT tager ingen nye handler. Efter 90 dage tages ingen nye handler.

## 6. Evaluering

**Rapporter efter 14, 28 og 90 dage**, beskrivende og mærket PAPIR / SIMULERING, uanset udfald.
Primært frekvenser, statusandele, fill-usikkerhed (bar rammer både stop og mål; fyld ved berøring), dækning, huller,
revisioner, F3-blokeringer og kald-loggens fejl. I bilag R brutto og netto pr. test, uden rangordning.

**Null:** seed 83 (`null_run`, `null_with_filters`, 3 × 60 dage) side om side, trækkes ikke om. Netto ved 28 bps er
negativt for baseline og alle kombinationer undtagen F2+F3 (én handel); F1+F2+F3 har ingen handler.

**Multiple testing:** familien er 96. N = 19.849 (19.438 + 315 + 96). Register V2: 19 FUTURE-poster
(`event_farm_forward_v2.v2_final_records`) med univers 96, RELATED_MECHANISM og uden uafhængighedspåstand. Datoerne
sættes ved aktivering.

**To uger er ingen dokumentation:** +0,1 R ved N = 19.849 og 80 % styrke kræver ca. 2.900 handler pr. test. En påstand
kræver en ny, låst, bekræftende protokol.

## 7. Ressourcer (målt på syntetiske data via loopback)

Pr. døgn: 576 kald (2 × 288), ca. 250 KB kald-log, ca. 220 KB bog og ca. 2 s CPU; under 50 MB over 90 dage i to
separate filer. Kører som systemd `--user`-enhed uden genstart af værten (G11) og uden at røre pm_lp (G12).

## 8. Før aktivering (fail-closed)

1. Direktørens skriftlige godkendelse; teksten committet i `PROTOCOL_V3.md` før noget kald.
2. Ejerens D5-underskrift (D5 ANCHORED, beslutning 97) på denne fils sha256, verificeret med `owner_approval.py`; G15
   vurderes særskilt.
3. G31 anvendt i `GATE_MATRIX.json` med alle flag sat, og 5m-strømmen godkendt i `stream_registry.json`.
4. Koden committet med ovenstående sha256 og grønne tests; værten svarer uden omgåelse.

Claude underskriver ikke, laver ingen nøgle og aktiverer ikke (G28).
