# Event farm: P0-gates før dataadgang (direktørordre 85)

Skrevet 2026-11-11 kl. 17:37 lokal tid (16:37 UTC) af Claude. **Kun metadata:** filnavne, størrelser og datoer
(`ls`, `find -printf`) samt committede tekster og artefakter. Ingen markedsfil er åbnet, læst, hashet, pakket ud eller
kopieret. Intet netværk. Ingen 2024- eller 2025+-fil er listet (navnefilter før listning). Karantænemappen
`/home/anton/copybot-dev/quarantine/` er ikke rørt. Plan: `research/desk/EVENT_FARM_PLAN_85.md` (UDKAST).

## Samlet dom: **BLOCKED**

Analysen må ikke køres nu. Den kan tidligst køres 2026-11-14 00:00 UTC, og kun når gate 1 er bestået (direktørens
afgørelse, en dateret PROTOCOL_V3-ændring før data og en post i GATE_MATRIX). Ingen alternativ kilde erstatter en
blokeret gate.

## Tjekliste

| # | Gate | Dom | Kilde og begrundelse |
|---|---|---|---|
| 1 | Godkendelse til at læse explore0 til event farm | **BLOCKED** | `research/desk/GATE_MATRIX.json` `rule`: "an action or gate not listed here is BLOCKED". Handlingen `historical_fetch` har kun studierne A_n6, B_n4 og F2. G01 og G02 nævner ikke event farm. `research/PROTOCOL_V3.md` har ingen ændring om event farm (`git grep` finder kun `EVENT_FARM.md`, `VIDEO_TRIAGE_2026-11-08.md`, koden og testen). Ejerens "Ja" (`EVENT_FARM.md`, sidste afsnit) er et chat-ja = UNVERIFIED_ORIGIN (`GATE_STATUS_PREVIEW_2026-11-14.md` linje 7) og åbner intet. |
| 1a | Må R3's 44 filer bruges til et andet studie? | **UNCLEAR** (fail-closed = BLOCKED) | PROTOCOL_V3 ændring 24 punkt 2 ("ingen andre symboler, måneder eller kilder") og 24a ("undtagelsen gælder kun ændring 24's 44 filer") handler om hentningen. Ingen tekst tillader eller forbyder anden brug af de cachede filer. Direktøren afgør. |
| 1b | Kræves verificeret ejergodkendelse (D5/G15)? | **UNCLEAR** | G15 gælder ny skabelon eller aktivering. En beskrivende explore0-kørsel er ingen af delene, men ingen tekst siger det. Direktøren afgør. |
| 2 | G01_HIST_1114: ingen historiske data før 2026-11-14 00:00 UTC (også læsning af cachen) | **BLOCKED** | GATE_MATRIX G01: `OPENS_AT` 2026-11-14 00:00 UTC, "the date alone opens nothing". I dag er 2026-11-11. |
| 3 | Findes 1m- eller 5m-barer for explore0 i cachen? | **PASS** (kun 1m, kun BTC og ETH) | Cachen er `data.CACHE` = `<checkout>/data/lab/market` (`lab/engine/data.py` linje 45). 1m-filerne ligger i `klines_1m/` (`lab/r3.py` `path()`). I denne checkout (`/home/anton/copybot-dev/copybot/data/lab/market`) er `klines/` og `funding/` tomme, og `klines_1m/` findes ikke. Produktionens cache `/home/anton/ecommerence/copybot/data/lab/market/klines_1m/` har 44 zip-filer, `BTCUSDT-1m-YYYY-MM.zip` og `ETHUSDT-1m-YYYY-MM.zip` for 2020-03..2021-12, 1,62–2,09 MB hver, plus `fetch_log.jsonl` (6.494 B, ikke åbnet). **0 filer med 5m** (og 0 med 3m, 15m, 30m, 4h eller 1d) i hele cachen. Ingen andre instrumenter med 1m. MNQ og lignende: ingen kilde. |
| 4 | Proveniens | **PASS** (metadata) | Hentet 2026-10-27 14:35:30–14:36:44 UTC fra `data.binance.vision` under ændring 24a (`research/studies/R3_m24.md`, commit ab9c201). Filernes mtime er 15:35–15:36 lokal (= 14:35–14:36 UTC), og alle har størrelse > 0. `research/studies/R3_m24_verify.json` (samme commit): 44/44 `fetched`, sha256 = log, CRC ok, 0 rækker uden for måneden, 0 manglende minutter, i alt 966.240 = 671 × 1.440 pr. symbol. **Identiteten er ikke genprøvet nu** (hashing er forbudt før gaten). Det sker som første skridt efter gaten (G01 `actions_at_opening`: identitetsmanifest før parsing). |
| 5 | Manglende måneder | **PASS** | Filnavne: 22 af 22 måneder pr. symbol, ingen huller. Minutdækning 100 % ifølge R3-kontrollen (punkt 4). |
| 6 | G04: 2025+ læses aldrig | **PASS** | `klines_1m/` har 0 filnavne med 2025+. Planen afviser enhver fil uden for 2020-03..2021-12 ud fra navnet, før den åbnes. |
| 7 | G03: 2024-holdout | **PASS** | `klines_1m/` har 0 filnavne med 2024. Andre cachemapper (`klines/`, `spot_klines/`) har filer uden for explore0. De bruges ikke af planen. |
| 8 | G05: egne fremadobservationer (lab.db ≥ 2026-10-27) | **PASS** (ikke berørt) | Planen læser ingen lab.db-række. |
| 9 | G02: kun explore0 | **PASS** som begrænsning | Alle 44 filer ligger i explore0 = 2020-03-01..2021-12-31 (PROTOCOL_V3 ændring 10c). `train3` og `validation3` (2022–2023) bruges ikke. G02's studieliste omfatter ikke event farm (se gate 1). |
| 10 | G07: karantæne | **PASS** | `research/data/QUARANTINE.json` har 3 poster, ingen i markedscachen. Den lækkede 2024-mappe uden for repoet er ikke rørt og bruges ikke. |
| 11 | G11/G12: ingen genstart; pm_lp urørt | **PASS** (ved design) | Kørslen er en lokal læsning uden netværk, ingen deploy, ingen service. |
| 12 | Overlap med tidligere registerforsøg | **UNCLEAR** (konsekvens fastlagt) | Se nedenfor. |

## Overlap med registret (gate 12)

Kilder: `research/desk/register_snapshots/SNAPSHOT_v1.json` (206 forsøg, 43 slægter, 19.438 varianter) og
`research/desk/EVIDENCE_REPORT_75.md`.

- **Samme filer:** `R3_m24` (slægt `unclassified`, 1 forsøg, 1 variant) har læst alle 44 filer i 2026-10-27's ene
  screening. Resultatet var SCREEN_FAIL (p 0,918), og nøglen screenes aldrig igen. Spørgsmålet var minutdrift efter
  makrotal, ikke mønstre. Data er altså ikke "friske": de er set af koden, men der er ikke set mønsterstatistik på dem.
- **Samme vindue:** explore0 er brugt af banen (`explore0`, 19.182 varianter, fcarry/dbasis) og af m17/m21-screeninger.
  explore0 er altid udforskning og aldrig bevis (ændring 10 punkt 6).
- **Vending (reversal):** `liquidation_cascade_reversal` (`MOVESCREEN_m21c`: 4σ-bevægelser på explore0-1h-perps,
  fortsættelse/tilbagevenden, SCREEN_FAIL; `E_daily_reversal_p1` FAIL; `L21_m2_liquidation_reversal` FAIL).
  Sweep → MSS-kæden er en vending efter et likviditetsgreb og er beslægtet.
- **Trend:** `cross_sectional_momentum` (bl.a. `L03_sol_trend_hourly` FAIL og `L14_tsmom_v1`, der åbnede BTC/ETH/SOL's
  2024-holdout). `E_donchian_trend_p1/p2` er SUPPRESSED, uden forsøg. BOS-hændelser er trendbrud og er beslægtede.
- **Konsekvens:** event farm har sin egen slægt i koden (`event_farm/ICT-SMC-mærkning`). Om den skal stå for sig selv
  eller under reversal/trend-slægterne, afgør direktøren (UNCLEAR). Uanset hvad tælles alle 12 setup-varianter og
  alle 92 hændelse × horisont-tests med i registret. Det konservative N er så mindst 19.438 + 104. Intet resultat
  kan bruges som bevis.

## Hvad der skal til, før kørslen

1. Dato ≥ 2026-11-14 00:00 UTC (`date -u` først).
2. Direktørens afgørelse af gate 1, 1a, 1b og 12.
3. En dateret PROTOCOL_V3-ændring "før data", der henviser til den låste plan (eller en direktørordre, som GATE_MATRIX
   anerkender), og en post for event farm i `GATE_MATRIX.json` (`historical_fetch` eller en ny handling).
4. Identitetsmanifest før parsing: navn, størrelse og sha256 pr. fil sammenlignet med `R3_m24_verify.json`. Ved
   afvigelse er resultatet BLOCKED. Ingen ny hentning, ingen anden kilde.
5. Grøn suite på den commit, der kører.
