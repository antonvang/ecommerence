# Ændring (event farm fremadrettet papirbog, 96 tests): endelig tekst til godkendelse og D5-underskrift

Endelig tekst efter direktørordre 102, skrevet af Claude 2026-11-12 kl. 14:26 lokal tid (13:26 UTC).

- **Hvad der underskrives:** præcis denne fil, byte for byte. Dens sha256 står i
  `EVENT_FARM_FORWARD_AMENDMENT_FINAL_102.sha256`.
- **Ved commit:** filen indsættes uændret i `research/PROTOCOL_V3.md` under en overskrift med ændringens nummer og dato.
  Overskriften ligger uden for den underskrevne tekst. Ændres én byte i filen, kræves en ny underskrift.
- **Status: UDKAST, IKKE LÅST, IKKE AKTIVERET.** Den afløser udkast 100 og tillæg 101, som står uændrede som
  historik.

## 1. Formål og afgrænsning

Event farm-motoren kører fremad i tid på lukkede 5m-barer for BTCUSDT og ETHUSDT (Binance USD-M perp) og papirhandler
96 forhåndsregistrerede tests:
- 12 baseline-varianter;
- de samme 12 filtreret med 7 kontekstfilterkombinationer.

Det er kun simulering og beskrivende udforskning:
- ingen rigtige ordrer, nøgler eller konti (G27);
- ingen alfa, ingen LÅS, ingen kandidatstatus;
- ingen påstand om en fordel;
- bogens observationer bruges ikke til at kalibrere eller vælge en ny hypotese (G05).

## 2. Kode (sha256; enhver afvigelse forhindrer kørsel)

| fil | sha256 |
|---|---|
| `research/tools/event_farm.py` | `7c4dec89891974189af6129139c450b59159070853165cbb5b960b2ca8524c76` |
| `research/tools/event_farm_driver.py` | `4b96e202266e3a5f0c8655e0ec30eefc8c170ba3b183cd97c5bf0815799b5be5` |
| `research/tools/event_farm_forward.py` | `f25feba8f9c2bb86c962dfb56cce765d048919aa921f34429d2192917d32deac` |
| `research/tools/event_farm_filters.py` | `1886b6f311e5eeae0d4c1a7ddbb3ad23fdead761fd0fb8ef6b0a40204aaf787c` |
| `research/tools/event_farm_forward_v2.py` | `ae8e57affae121cfc47148ab18ae211cb1e92ce20da510c2f7b28fa41a38b127` |

- Motoren er commit f686c9a. Bogen er `ForwardBookV2` med `FROZEN_CONFIG` og `FILTER_PARAMS` uændret. Live-tilstand
  kræver præcis BTCUSDT og ETHUSDT. Bogen verificerer selv motorens sha256 før brug.
- **Kildeadapteren** (afsnit 3) er ikke skrevet. Aktivering kræver et dateret tillæg til denne ændring med adapterens
  sha256 og grønne tests. Tillægget kræver direktørens godkendelse og ejerens D5-underskrift på tillæggets egen sha256.

## 3. Datakilde (præcis)

- **Vært og endepunkt:** `fapi.binance.com`, `GET /fapi/v1/klines`. Værten er allerede tilladt i lab'et. Kun GET, ingen
  nøgle, ingen anden vært.
- **Parametre:** `symbol` ∈ {BTCUSDT, ETHUSDT}, `interval=5m`, `startTime` = seneste lagrede open time + 300.000 ms.
  `limit=3` i drift og `limit=499` ved indhentning.
- **Felter i svaret:** hver række er et array.

  | felt | indhold | brug |
  |---|---|---|
  | [0] | open time (ms) | ts = [0] / 1000 |
  | [1]–[4] | open, high, low, close (strenge) | omsat til tal |
  | [5] | volume (base-aktiv) | **volumenfeltet til VWAP (F3)** |
  | [6] | close time (ms) | lukket-kontrol |

  Felterne [7]–[11] (quote-volumen, antal handler, taker-købsvolumen, ignore) bruges ikke og gemmes ikke.
- **Kun lukkede barer:**
  - en række tages kun med, når [6] < svarets servertid og open time + 300 s ≤ lokal UTC-tid;
  - bogen afviser desuden ikke-lukkede barer, barer uden for 5m-gitteret og barer med ugyldig OHLC;
  - mangler [5], eller er den ikke et endeligt tal ≥ 0, afviser adapteren rækken;
  - en volumen på 0 lagres som 0 og blokerer F3 for resten af sessionen.
- **Kald og vægt:**
  - ét kald pr. symbol pr. 5m-bar, startet 20 s efter hver 5m-grænse (UTC). Det giver 2 kald pr. 5 minutter = 0,4
    kald i minuttet;
  - `limit` under 100 har vægt 1, dvs. vægt 0,4 i minuttet af 2.400;
  - indhentning sker med højst ét kald pr. symbol pr. gennemløb og `limit=499` (vægt 2, op til 41,6 timer);
  - ved 429/418 eller netværksfejl: ingen nye forsøg i samme gennemløb.
- **Svarlog:** pr. kald UTC-tid, HTTP-status, antal rækker og sha256 af svaret i bogens fil. Rå svar gemmes ikke.
- **Ingen historik:** ingen backfill før aktiveringen. Opvarmningen er de første 288 fremadrettede barer pr. symbol.
- **Netværk:** DNS-filteret omgås aldrig (ingen anden DNS, VPN, hosts-fil, DoH eller hotspot). Svarer værten ikke,
  bliver resultatet huller og pauser efter afsnit 6.
- **Ressourcer:**
  - disk ca. 0,3 MB/dag (målt syntetisk ca. 0,16 MB/dag for 12 tests);
  - CPU nogle millisekunder pr. bar;
  - separat databasefil `event_farm_forward*.db` uden for `lab.db` og `pm_lp.db`;
  - en separat systemd `--user`-enhed. Den rører ikke pm_lp (G12), og værten genstartes ikke (G11).

## 4. De 96 tests

**Baseline (12):** `event_farm.VARIANTS`, dvs. anker fvg/ob × rr 1/2/3 × indgang mid/market. Kæden er sweep → MSS →
anker. Indgang, stop og mål fastlægges ved known_ts.

**Filtre** (`event_farm_filters`, værdien ved bar k beregnes kun af barer til og med k):

- **F1 (1t-trend):**
  - 1t-barer består af 12 komplette 5m-barer; en manglende 5m-bar gør timen ugyldig;
  - 1t-fraktaler med k1 = 2, bekræftet ved lukket time;
  - trend +1 ved to strengt højere toppe og bunde, −1 ved to lavere;
  - long kun ved +1, short kun ved −1.
- **F2 (gårsdagens high/low):**
  - niveauet kræver mindst 95 % dækning af UTC-dag D−1;
  - breakout = luk forbi niveauet; retest = berøring i bar b+1..b+12 uden luk tilbage; et luk tilbage annullerer;
  - indgangen skal ligge på breakout-siden.
- **F3 (VWAP):**
  - VWAP fra 00:00 UTC med tp = (h + l + c) / 3 og volumen [5];
  - long kræver (VWAP − close) / ATR ≥ 1,0, short spejlet;
  - en manglende bar eller volumen ≤ 0 gør VWAP INCOMPLETE til sessionens slutning, og F3 er BLOCKED. Der beregnes
    ingen erstatning.

**Kombinationer:** de 7 ikke-tomme delmængder af {F1, F2, F3} × 12 = 84. I alt 96 tests.

**Tærskler:** valgt og begrundet før data i tillæg 101 afsnit 3. De ændres ikke. Et filter, der giver nul handler
eller negativt netto, rapporteres sådan.

## 5. Fills og omkostninger

**Fills:** motorens regler.
- Rammer en bar både stop og mål, tæller det som stop.
- På fyldbaren tæller kun stop.
- En limit fyldes ved berøring til sin pris.
- Gap gennem stop lukker ved åbningsprisen, gap gennem mål ved målet.
- Når målet nås før fyld, er setuppet `missed`.
- Timeout efter 48 barer.

**Konti:** hver test har sin egen papirkonto på 10.000 USDT og 1.000 USDT notional pr. handel. Handler må overlappe.

**Omkostninger: 28 bps pr. rundtur er en ANTAGELSE, ikke verificerede fremtidige omkostninger.**
- Det er lab'ets papirbogsmodel: taker 0,001 + slippage 0,0002 + halv spread 0,0002 pr. fyld, også ved limit.
- Rapporten viser desuden netto ved 0/1/5/8 bps.
- Virkelige gebyrer og fyld er ikke målt.

## 6. Datamangler og stop

**Huller:**
- en manglende bar ventes på, til en lagret bar ligger 600 s efter den; derefter registreres et hul;
- for sene barer logges og behandles aldrig;
- reviderede barer logges, og den første værdi beholdes.

**Pause:**
- dækning under 95 % af de seneste 288 barer giver ingen nye handler for symbolet;
- svarer kilden ikke i 24 timer, vurderes gaten igen;
- 3 eller flere reviderede, allerede behandlede barer inden for 24 timer giver manuel gennemgang.

**Handler med hul:** `gap_affected`. De er ude af den primære opgørelse og bogføres som stop i værste-falds-opgørelsen.

**Stop af hele bogen** (permanent):
- IntegrityHalt: en hændelse eller et setup, der ikke er kendt på sin bar, dobbelt bogføring, fyld før known_ts eller
  ændret identitet (kode, config, symboler, tests, kilde);
- `lane-off` eller en skriftlig ordre fra direktør eller ejer;
- brud på G27 eller G12.

**Variantstop:** en test, hvis konto er ≤ 8.000 USDT, tager ingen nye handler.

**Slut:** 90 dage efter første behandlede bar tages ingen nye handler. Åbne handler afvikles efter reglerne.

## 7. Evalueringsmetode

**Rapporter efter 14, 28 og 90 dage**, kun beskrivende, mærket "PAPIR / SIMULERING", uanset udfald.
- **Primært:**
  - hændelses- og setupfrekvens;
  - statusandele;
  - fill-usikkerhed (andel handler med en bar, der rammer både stop og mål, og andel fyld ved berøring);
  - dækning, huller, for sene og reviderede barer;
  - F3-blokeringer.
- **Sekundært (bilag, uden rangordning):** R brutto, netto ved 28 bps og netto ved 0/1/5/8 bps pr. test.

**Null:** den faste null med seed 83 (`event_farm.null_run` og `event_farm_filters.null_with_filters`, 3 × 60 dage, 5m)
står side om side pr. test. Den trækkes ikke om.
- I nullen er netto ved 28 bps negativt for baseline og for alle kombinationer undtagen F2+F3. F2+F3's plus bygger på
  én enkelt handel, talt i 6 varianter. F1+F2+F3 har ingen handler.

**Multiple testing:** familien er 96. Reference-N = 19.849 = 19.438 (registret) + 315 (event farm explore0) + 96. Ved
α = 0,05 er den ensidede Bonferroni-grænse z ≈ 4,56. Det er en diagnostik, ingen beslutningsregel.

**Register V2:** 19 FUTURE-poster (`event_farm_forward_v2.v2_final_records`):
- 12 baseline-poster og 7 kombinationsposter;
- universet er 96, reference-N er 19.849, og klassifikationen er RELATED_MECHANISM uden uafhængighedspåstand;
- de afløser udkast 100's plan som revisioner af samme id'er;
- datoerne sættes ved aktivering.

**To ugers observation er ikke dokumentation for en fordel.** At påvise +0,1 R pr. handel ved N = 19.849 med 80 %
styrke kræver ca. 2.900 handler pr. test, hvilket svarer til år. En påstand kræver en ny, låst, bekræftende protokol med
styrkeberegning før data.

## 8. Krav før aktivering (fail-closed)

1. Direktørens skriftlige godkendelse af denne tekst.
2. Teksten committet i `PROTOCOL_V3.md` før nogen fremadrettet bar hentes.
3. Ejerens D5-underskrift (D5 ANCHORED, beslutning 97) på sha256 i `EVENT_FARM_FORWARD_AMENDMENT_FINAL_102.sha256`,
   verificeret med `owner_approval.py`. G15 vurderes særskilt.
4. Gate G31 anvendt i `GATE_MATRIX.json` med alle sine flag sat.
5. 5m-strømmen godkendt i `stream_registry.json`.
6. Kildeadapteren committet med grønne tests og sit eget godkendte og underskrevne tillæg.
7. Værten svarer uden omgåelse.

Claude underskriver aldrig, laver aldrig nøglen og aktiverer ikke (G28).
