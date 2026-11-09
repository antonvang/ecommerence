# U4_PROVENANCE_POWER_AUDIT: offline audit af U4 H1 (direktørordre 62 P1)

**Status:** AUDIT, kun læsning. Ingen lås, ingen ændring af hypotesen, intet committet.
**Skrevet:** 2026-11-09 ca. 13:20 UTC (tjekket med `date -u`).
**Grundlag:** `research/desk/U4_0830_PREREG_DRAFT.md` (commit `de91dd5`) og `research/desk/US_MACRO_0830_DESIGN.md`
(commit `3c75685`).

**Hvad jeg har gjort, og hvad ikke:**
- Ingen markedsdatafil er åbnet, pakket ud eller hashet. Kun navne, størrelser og tider (`ls -l`, `stat`).
- Hashes er kun læst, hvor lab'et allerede har skrevet dem: `fetch_log.jsonl`, `R3_m24.json`, `R3_m24_verify.json` og
  `events` i lab.db.
- lab.db er åbnet som `mode=ro` med `PRAGMA query_only=ON` (G29).
- Kalenderfilerne er ikke åbnet. Kun deres metadata og de hashes, der blev skrevet ved hentningen.
- Ingen netværk, ingen `python3 -m lab`. N4-filen og `quarantine/` er ikke rørt.
- U4's effekt, p-værdi eller nogen afkast- eller volatilitetsstatistik er ikke beregnet. Styrken er regnet analytisk.

## Kort svar

| # | Spørgsmål | Svar |
|---|---|---|
| 1 | Proveniens | 22 BTC-filer findes (plus 22 ETH, i alt 44). Hentet 2026-10-27 14:35:34-14:36:44 UTC under ændring 24/24a. sha256 blev skrevet ved hentningen. "22" er rigtigt for BTC |
| 2 | Vindue | Hele 2020-03..2021-12 er `explore0` (ændring 10c). Den er ikke beskyttet, men allerede brugt meget. Ingen af de 22 er fra 2024 |
| 3 | Kalender | BLS 2020/2021 og FOMC 2020/2021 er cachet med hashes fra hentningen. Lab'ets egne resultater viser 22 CPI + 22 NFP i explore0. Om datoerne er point-in-time, er UNVERIFIED |
| 4 | Tidligere brug | **R3 har læst de samme filer på de samme 08:30-tider med samme placebo-design.** R3 skrev et spredningsmål for 60-min-afkast efter udgivelsen. Det berører især h = 60. H1 er ikke frisk |
| 5 | Styrke | 1,43× er rigtigt efter normalformlen (ændring 32). Med t(19) og G = 20 er det **ca. 1,47×**. Holm er ikke nødvendig, når kun h = 15 afgør |
| 6 | Uden nye data? | **Ja for BTC.** Der mangler ikke markedsdata. Der mangler en tjekket helligdagsliste, et σ_d-grundlag efter ændring 32 og eventuelt et BLS-arkivtjek |
| 7 | Dom | **NO-GO for en lås nu. Betinget GO for en senere formel forhåndsregistrering** (betingelser i punkt 7) |

## 1. Proveniens for de 22 filer

**Placering:** produktionens cache `/home/anton/ecommerence/copybot/data/lab/market/klines_1m/`. Dev-worktreet har ingen
`data/lab/market/klines_1m/`.

**Indhold (kun metadata):** 44 zip-filer og `fetch_log.jsonl`.
- 22 × `BTCUSDT-1m-YYYY-MM.zip` og 22 × `ETHUSDT-1m-YYYY-MM.zip` for 2020-03 … 2021-12. Ingen andre måneder eller symboler.
- BTC fylder i alt 42.835.001 byte, og ETH fylder 40.499.044 byte.
- Alle 44 størrelser på disken er lig med `bytes` i `fetch_log.jsonl`.

| Fil | Byte (disk = log) | mtime (UTC) | sha256 i fetch_log (første 16) |
|---|---|---|---|
| `BTCUSDT-1m-2020-03.zip` | 1.908.886 | 2026-10-27 14:35:34 | `15790b4b031cbc5f…` |
| `BTCUSDT-1m-2020-04.zip` | 1.833.303 | 2026-10-27 14:35:36 | `f45228183c21030f…` |
| `BTCUSDT-1m-2020-05.zip` | 1.917.755 | 2026-10-27 14:35:38 | `bc5bdae217f9ef6a…` |
| `BTCUSDT-1m-2020-06.zip` | 1.790.292 | 2026-10-27 14:35:40 | `91f18492445c0a96…` |
| `BTCUSDT-1m-2020-07.zip` | 1.808.294 | 2026-10-27 14:35:42 | `4cb7dcf6e1adb17e…` |
| `BTCUSDT-1m-2020-08.zip` | 1.883.510 | 2026-10-27 14:35:43 | `7596de0f26df44d7…` |
| `BTCUSDT-1m-2020-09.zip` | 1.816.087 | 2026-10-27 14:35:45 | `9f2d575ffc17a143…` |
| `BTCUSDT-1m-2020-10.zip` | 1.865.118 | 2026-10-27 14:35:46 | `f35bc01dc1bba142…` |
| `BTCUSDT-1m-2020-11.zip` | 1.905.251 | 2026-10-27 14:35:48 | `8eb55b2a547c35d7…` |
| `BTCUSDT-1m-2020-12.zip` | 1.974.734 | 2026-10-27 14:35:49 | `72cfa1e9aeb85187…` |
| `BTCUSDT-1m-2021-01.zip` | 2.057.786 | 2026-10-27 14:35:51 | `ba7aeda6a99e0828…` |
| `BTCUSDT-1m-2021-02.zip` | 1.851.915 | 2026-10-27 14:35:52 | `0a270f354b15b053…` |
| `BTCUSDT-1m-2021-03.zip` | 2.053.085 | 2026-10-27 14:35:53 | `15a2676410d5104f…` |
| `BTCUSDT-1m-2021-04.zip` | 1.971.044 | 2026-10-27 14:35:55 | `d957fcde82f9b5a9…` |
| `BTCUSDT-1m-2021-05.zip` | 2.087.690 | 2026-10-27 14:35:56 | `dcf7c567cbde49a5…` |
| `BTCUSDT-1m-2021-06.zip` | 2.015.140 | 2026-10-27 14:35:58 | `a640c7f935a1136d…` |
| `BTCUSDT-1m-2021-07.zip` | 2.037.166 | 2026-10-27 14:36:00 | `1367b5cd230474b0…` |
| `BTCUSDT-1m-2021-08.zip` | 2.049.960 | 2026-10-27 14:36:02 | `a864bdf38c9d06b7…` |
| `BTCUSDT-1m-2021-09.zip` | 1.970.475 | 2026-10-27 14:36:03 | `6e7bbfe650e6c56e…` |
| `BTCUSDT-1m-2021-10.zip` | 2.040.146 | 2026-10-27 14:36:05 | `4b78dd0174890c97…` |
| `BTCUSDT-1m-2021-11.zip` | 1.963.552 | 2026-10-27 14:36:07 | `67da3342f014166d…` |
| `BTCUSDT-1m-2021-12.zip` | 2.033.812 | 2026-10-27 14:36:09 | `c905c5c8ff36d0df…` |

ETH: 22 filer, mtime 14:36:11-14:36:44 UTC. De fulde sha256 står i `fetch_log.jsonl` linje 1.

**Hvilken ændring tillod hentningen:**

| Kilde | Hvad den siger |
|---|---|
| `research/PROTOCOL_V3.md:3369` | Ændring 24 (2026-10-25): R3, metode m24 |
| `PROTOCOL_V3.md:3379` | Filerne er `…/klines/{BTCUSDT,ETHUSDT}/1m/<SYM>-1m-YYYY-MM.zip` for 2020-03 … 2021-12 (44 filer) |
| `PROTOCOL_V3.md:3381` | "sha256 pr. fil registreres" |
| `PROTOCOL_V3.md:3430-3439` | Præcisering: hver hentning skriver én post i `klines_1m/fetch_log.jsonl` med sha256 og byte |
| `PROTOCOL_V3.md:3570-3594` | Ændring 24a (2026-10-26): brugerens ja til en tidlig hentning, "kun ændring 24's 44 filer" (linje 3574), vindue 2026-10-27 14:35 UTC ≤ t < 10-31 i K3-frie slots (linje 3578). Kontrol: "sha256 på disken = sha256 i `fetch_log.jsonl`" og CRC (linje 3586) |

**Hvornår og med hvilke hashes:**
- `fetch_log.jsonl` linje 1: `ts` 1793111733 = **2026-10-27 14:35:33 UTC**, `status` "ran", 44 fetched, 0 absent, 0 failed.
  Den indeholder sha256 og byte pr. fil. Det er den eneste post i loggen.
- `research/studies/R3_m24_verify.json` (24a punkt 4, kl. 14:37 UTC): expected 44, present 44, alle `sha256_matches_log`
  og `crc_ok` sande, 0 manglende minutter, 0 barer uden for måneden.
- `research/studies/R3_m24.json` `files`: de samme 44 sha256 (lig med fetch_log), `files_sha256` `2d6b9151…`.
  Committet i `ab9c201` (2026-10-27 14:37:55 UTC).
- lab.db `datasets` har **ingen** rækker for 1m-filerne. Deres eneste hash-spor er fetch_log, verify-filen og R3_m24.json.

**Er "22" rigtigt?** Ja. Der blev hentet 44 filer: 22 BTC og 22 ETH. H1 bruger kun de 22 BTC-filer. Udkastet siger det
samme (linje 87-90). Designnotatets "44 cachede BTC/ETH 1m-filer" (linje 141) er også rigtigt.

**Adgang siden R3 (kun metadata):** alle 44 zip-filer har atime 2026-10-27 14:37:01-14:37:09 UTC. Det er R3's
verifikation. Filsystemet bruger `relatime`, så en læsning efter ca. 2026-10-28 14:37 UTC ville have flyttet atime.
Ingen har altså læst zip-filerne siden. (`fetch_log.jsonl` har atime 13:09:47 UTC i dag. Det er min egen læsning af loggen.)

## 2. Vindue og beskyttelse

| Periode | Navn | Kilde | Status for 2020-03..2021-12 |
|---|---|---|---|
| 2020-03..2021-12 | `explore0` | `PROTOCOL_V3.md:885` (ændring 10c; erstatter 2020-01 i 10 punkt 2, linje 782) | **Her ligger hele U4-perioden** |
| 2022-01..2023-06 | træning / `train3` | §2, `PROTOCOL_V3.md:32` | ikke berørt |
| 2023-07..12 | validering | §2 | ikke berørt |
| 2024 | slut-test (holdout) | §2, `PROTOCOL_V3.md:34`; G03 | ikke berørt |
| 2025-01-01 → | reserveret | §2; G04 | ikke berørt |

- explore0 er ikke beskyttet, men det er "aldrig bevis" (ændring 10 punkt 1). Den er brugt af banen og af m21c-m21j, J1
  og R3.
- `PROTOCOL_V3.md:2673` (ændring 21l punkt 3) lukker discovery i explore0: "Ingen ny screening, før en ny datakilde
  eller mekanisme findes." 1m-filerne var den nye kilde til R3. En lås for H1 skal derfor sige, hvorfor H1 er tilladt
  efter 21l punkt 3 (fx at H1 er en måling af en ny størrelse og ikke en screening). Det afgør direktøren.
- G01 (`GATE_MATRIX.json`, `G01_HIST_1114`) gælder stadig: ingen læsning af de cachede historiske filer før 2026-11-14
  00:00 UTC og kun efter en lås.
- **2024-holdout:** karantænemanifestet `research/data/quarantine_holdout_2024_2026-11-09.json` har 192 filnavne. Alle er
  `1h`-filer fra 2024 (kun navnene er læst). Ingen er 1m, og ingen er fra 2020-2021. Ingen af de 22 BTC-filer er fra 2024.
- Designnotatet skriver stadig explore0 = 2020-01..2021-12 (`US_MACRO_0830_DESIGN.md:70` og `:139`). Det er forældet
  efter 10c. Udkastet bruger det rigtige vindue.

## 3. Hændelseskalenderen

**Cachede filer (kun metadata), `data/lab/market/ingest/calendar/` i produktionen:**

| Fil | Byte | mtime (UTC) | Hentet fra (lab.db `events`) | Rækker | sha256 ved hentning | Event-id |
|---|---|---|---|---|---|---|
| `bls-2020.json` | 3.762 | 2026-10-20 16:06:14 | `bls.gov/schedule/2020/home.htm` | 24 | `744a0484…f4b97fb4` | 4472 |
| `bls-2021.json` | 3.762 | 2026-10-20 16:06:44 | `bls.gov/schedule/2021/home.htm` | 24 | `000be2ec…3dc26c30` | 4480 |
| `fomc-2020.json` | 2.265 | 2026-10-20 16:04:13 | `federalreserve.gov/…/fomchistorical2020.htm` | 14 | `77983234…75d0c9ad` | 4437 |
| `fomc-2021.json` | 1.391 | 2026-10-20 16:04:44 | **`federalreserve.gov/monetarypolicy/fomccalendars.htm`** | 8 | `c9aa748e…3e6fc083` | 4444 |

(2022- og 2023-filerne findes også, men H1 bruger dem ikke.)

- Hentningen skete under ændring 14 (`PROTOCOL_V3.md:1342-1376`, kun tidspunkter, intet udfald). Hashes står i
  `ingest.done`-hændelserne (`out_sha256`). En lås kan citere dem i stedet for at hashe filerne på ny.
- **Antal i explore0 er allerede talt af lab'et:** `NEWINFO_m21j.md:17-18` (J1) giver CPI 22, beskæftigelse 22 og FOMC
  14. `R3_m24.json` giver `calendar_events` 58. `R3_MINUTMAKRO_PLAN.md:25` siger, at CPI og NFP ikke falder på samme dag
  i 2020-21. **Altså 44 udgivelsesdage før udelukkelser.** Udkastets "beregnet, ikke talt" (linje 34-35) kan rettes til
  "talt af J1 og R3".
- **Fejl i udkastet:** linje 28-29 siger, at begge FOMC-filer kommer fra `fomchistorical{year}.htm`. `fomc-2021.json` kom
  fra den aktuelle kalenderside (event 4444). Det er en anden side. Om den side har alle ikke-planlagte møder i 2021, er
  UNVERIFIED.
- **COVID-flytninger 2020-21:** jeg kender ingen flytning af CPI eller Employment Situation i 2020-21. Det er
  hukommelse og **UNVERIFIED**. BLS-siderne blev hentet 2026-10-20 og viser den endelige plan, ikke nødvendigvis planen,
  som den så ud dengang. Et point-in-time-tjek mod BLS' arkivlister kræver netværk og direktørens ja (udkastets punkt
  1.4). Ellers skal begrænsningen stå i låsen.
- **Helligdage (kontrolregel):** ingen tjekket liste er cachet. Den kan skrives ud fra reglerne uden netværk, men to ting
  skal afgøres før låsen. Juneteenth blev først en føderal helligdag 2021-06-17 og blev holdt 2021-06-18, så den var ikke
  kendt på forhånd. Og den føderale liste er ikke NYSE-listen. For BTC (24/7) betyder kun den føderale liste noget.

## 4. Påvirkning fra tidligere udforskning (vigtigst)

**Hvad R3 testede** (`PROTOCOL_V3.md:3369-3407`, resultat `R3_m24.md` og `.json`, commit `ab9c201`):
- Samme 44 filer (BTC og ETH) og samme kalender: 22 CPI + 22 NFP kl. 08:30 ET og 14 FOMC kl. 14:00 ET, i alt 58.
- Bar 0 ved T (= 08:30 ET for CPI/NFP): s = fortegnet af ln(C_0/O_0) (linje 3387).
- Udfald y = s · ln(C_61/C_1), altså afkastet fra T+2 til T+62 min (linje 3388).
- Placebo: samme klokkeslæt T − 7 døgn, eller T − 14, hvis det døgn har en kalenderbegivenhed (linje 3392). Det er næsten
  H1's kontrolregel.
- Udfald: SCREEN_FAIL. Middel +0,014 %, p 0,918, 57 klynger.

**Hvad R3 skrev ned, som berører H1:**
- `R3_m24.json` gemmer `se` for hændelsernes y og `placebo.mean` og `placebo.p` for placebodagene.
- Fordi |y| = |ln(C_61/C_1)|, er spredningen af y i praksis størrelsen af 60-min-bevægelsen efter udgivelsen. `se` er
  altså et samlet spredningsmål for 60-min-afkast på udgivelsesdage. Placeboens middel og p giver groft det samme for
  kontroldagene.
- `R3_BLOKERING_2026-10-26.md:31` giver desuden den ubetingede 1 t-spredning i explore0 (0,96 %, alle timer).
- Sammen giver det et groft forhold "60-min-uro efter udgivelsen mod kontroldage". **Jeg har ikke regnet det ud.**
  Ingen bør gøre det før en lås. Det ville være et kig på H1's h = 60.
- Der er ingen tal pr. hændelse i repoet. Hverken `R3_m24.json` eller `NEWINFO_m21j.json` har rækker pr. hændelse, kun
  gennemsnit.

**Andre studier:**

| Studie | Data og vindue | Hvad blev set | Berører H1? |
|---|---|---|---|
| J1 `macro_release\|post_drift_24h\|m21j` (`PROTOCOL_V3.md:2571-2619`, `NEWINFO_m21j.md`) | 1 t-barer, BTC og ETH, explore0, de samme 58 udgivelser | Fortegnet i udgivelsestimen og 24 t-drift. SE for 24 t-drift (± 0,49 %) | Lavt. Timeopløsning og 24 t. Intet om 15 min |
| 14a H1 `makrodybde` (`MAALING_14a_2026-10-21.md:10-19`) | bogdybde ±1 % omkring FOMC/CPI/NFP i **2023** | Dybden var lavere, men placeboen viste et mønster for tid på dagen og ugedag | Lavt. Andet år og anden variabel. Det støtter H1's kontrol på samme ET-tid |
| Ubetinget spredning (`R3_BLOKERING_2026-10-26.md:31`; ændring 32 punkt 4, `power_plan.py`) | 1 t-barer explore0, alle timer | sd for 1 t-afkast (0,96 % gns. BTC/ETH; BTC 0,89 %) | Lavt. Ikke betinget på udgivelser |
| `hour_of_day`, `day_of_week` (banen og fremadtest-konti) | timebarer | afkast pr. time, ikke uro omkring udgivelser | Lavt |
| ORB15 (`orb15/ORB15_VENUE_DATA_MATRIX.md:36`) | – | kun fillisten | Nej |
| Hypotesepipeline 17 (141 `research.hypothesis_screen`-hændelser i lab.db) | – | ingen makro-nøgle (kun listing, margin, staking osv.) | Nej |

**Vurdering af påvirkningen:**

| Vindue | Påvirkning | Hvorfor |
|---|---|---|
| h = 60 | **moderat til høj** | R3's `se` og placebo ligger næsten oven i H1's h = 60 (T+2..T+62 mod T..T+60, samme kontrolregel). Forskelle: gennemsnit af BTC og ETH, 14 FOMC-dage med, |afkast| over 60 min i stedet for summen af kvadrerede 1-min-afkast |
| h = 15 | **lav til moderat** | Intet 15-min-tal findes nogen steder. Men hvis udgivelsens uro er kort, er den en stor del af 60-min-tallet. Den, der kender R3's spredning, ved noget om h = 15 |
| h = 5 | lav | som h = 15, men svagere |
| Data | **ikke friske** | R3's kode har læst alle bar 0 og 1-61 på de 58 dage og deres placebodage. Kun gennemsnit er gemt |

- **Konklusion:** H1 er ikke en frisk test på disse data. Data er læst, begivenhedslisten er brugt, kontrolreglen er
  brugt, og et spredningsmål tæt på h = 60 ligger i repoet. Udkastets linje 141-142 ("R3 og J1 har … brugt de samme
  udgivelsesbarer til retning") undervurderer det. R3 skrev også et spredningsmål.
- Mærket EXPLORATORY (udkastets punkt 7) er derfor nødvendigt og ikke kun en formalitet.
- Forfatterne af designet (ordre 58) og udkastet (ordre 61) har læst R3's resultattekst (designet citerer +0,014 % og 57
  klynger, udkastet hasher `R3_m24.json`). σ_d = 0,7 er kaldt en antagelse "før data". Jeg har ingen tegn på, at den er
  taget fra R3's `se`, men jeg kan ikke udelukke, at forfatteren kendte den.
- **Holm-kobling:** med Holm afhænger h = 15's tærskel af p for h = 5 og h = 60 (se punkt 5). Så det påvirkede h = 60
  kan flytte afgørelsen på h = 15. Det er en grund til at tage h = 60 ud af afgørelsen.

## 5. Styrke og MDE (kun analytisk)

**Udkastets tal passer med normalformlen.** MDE-forhold = exp((z₁₋α′/₂ + 0,842) · σ_d / √n). Ved σ_d = 0,7 og n = 40:
- én test (α 0,05): faktor 2,802 → **1,364×** (udkastet 1,36×);
- Holm, mindste p (α 0,05/3): faktor 3,236 → **1,431×** (udkastet 1,43×).
- Hele udkastets tabel (linje 119-124) regner rigtigt. Udkastets t(21)-faktor 3,46 er også rigtig (jeg får 3,476).

**Med månedsklynger og t(G − 1), G = 20.** Styrken er regnet med den ikke-centrale t-fordeling (kode i Python uden
data):

| α (tosidet) | kritisk t(19) | δ for 80 % styrke | MDE, σ_d 0,7, n 40 | ρ = 0,3 inden for måneden |
|---|---|---|---|---|
| 0,05 (kun h = 15) | 2,093 | 2,954 | **1,387×** | 1,452× |
| 0,025 (Holm, h = 15 som nr. 2) | 2,433 | 3,305 | 1,441× | – |
| 0,0167 (Holm, h = 15 som mindste p) | 2,625 | 3,504 | **1,474×** | 1,556× |

| n | normal, 1 test | t(19), 1 test | normal, Holm | t(19), Holm |
|---|---|---|---|---|
| 30 | 1,431× | 1,459× | 1,512× | 1,565× |
| 36 | 1,387× | 1,411× | 1,459× | 1,505× |
| 40 | 1,364× | 1,387× | 1,431× | 1,474× |
| 44 | 1,344× | 1,366× | 1,407× | 1,447× |

Følsomhed ved n = 40 og t(19): σ_d 0,5 giver 1,26× / 1,32×, og σ_d 1,0 giver 1,60× / 1,74× (1 test / Holm).

- ρ er korrelationen mellem CPI- og NFP-dagen i samme måned (2 hændelser pr. klynge). Designeffekten er √(1 + ρ).
  ρ = 0,3 er et eksempel, ikke et estimat.
- **Er "≈ 1,43×" rigtigt?** Kun med normalformlen, som ændring 32 punkt 1 foreskriver. Med testens egen fordeling, t(19),
  er tallet **ca. 1,47×**. Med korrelation inden for måneden er det ca. 1,5-1,6×. Mærket "ca. 1,4×" bør være "ca. 1,5×".
- **Er Holm nødvendig?** Nej, ikke for afgørelsen. Afgøres H1 kun på h = 15, er der én bekræftende test, og α = 0,05
  holder fejlraten for den ene påstand. Holm over tre vinduer er kun nødvendig, hvis 5 og 60 min også kan give en
  påstand. Med Holm afhænger h = 15's tærskel desuden af de andre p-værdier: α/3, α/2 eller α efter rangen. Den
  koster ca. 0,09 i MDE-forhold (1,39× → 1,47×). Anbefaling: h = 15 alene ved α = 0,05. 5 og 60 min rapporteres kun
  beskrivende, eventuelt med Holm inden for de beskrivende.
- **σ_d = 0,7 og ændring 32:** punkt 1 kræver en sd, der ikke er testens egne data, "eller en anden kilde med
  begrundelse" (`PROTOCOL_V3.md:3887-3919`). Udkastet giver ingen kilde. Et ræsonnement uden data: med 15 normalfordelte
  1-min-afkast er støjen på ln RV ca. √(2/15) ≈ 0,37 pr. vindue, altså ca. 0,52 for en forskel. Dertil kommer forskellen i
  uroniveau mellem to dage med en uges afstand. 0,7 er muligt, men de tykke haler i 1-min-afkast trækker op mod 1,0.
  Låsen bør angive en begrundelse og vise σ_d = 1,0 ved siden af.
- **FAIL-reglen** (øvre 95 %-grænse for exp(d̄₁₅) < 1,25) udløses med t(19), n = 40 og σ_d = 0,7 kun med ca. **47 %**
  sandsynlighed, selv når den sande effekt er 1,0×. Ved 1,10× er det ca. 18 %. Uden effekt er INCONCLUSIVE altså lige
  så sandsynlig som FAIL. Det bør stå i låsen før data.
- n ≈ 40 er en antagelse. Antallet af FOMC-udelukkelser (±1 døgn) og `no_control` er ikke talt, fordi kalenderen ikke er
  åbnet.

## 6. Kan H1 testes uden nye data?

**Ja, for BTC-delen.** Der skal ikke hentes nye markedsdata, og ingen vært skal bruges.

| Del | Findes? | Kilde |
|---|---|---|
| 22 BTC 1m-filer 2020-03..2021-12 | ja, hashes fra hentningen | fetch_log linje 1, R3_m24_verify.json |
| BLS 2020/2021 (CPI, NFP) | ja | events 4472, 4480 |
| FOMC 2020/2021 til udelukkelse | ja (2021 fra den aktuelle kalenderside) | events 4437, 4444 |
| Tjekket føderal helligdagsliste 2020-21 | **nej** | kan skrives uden netværk; Juneteenth 2021 skal afgøres |
| Point-in-time-tjek af BLS-datoer | **nej** | kræver bls.gov og direktørens ja, ellers en skrevet begrænsning |
| σ_d-begrundelse (ændring 32 punkt 1) | **nej** | skal skrives i låsen |
| Dato og lås | **nej** | G01: tidligst 2026-11-14 00:00 UTC og efter låse-commit |
| Ejergodkendelse | **nej** | VERIFIED_OWNER_APPROVAL kræver D5 (ejernøglen) |

XAU-delen kan ikke testes uden en ny 1m-stream. Det er uændret fra udkastet.

## 7. GO / NO-GO

**NO-GO for en lås nu.** Ordre 61 tillader ingen låse, D5 er ikke gjort, og G01 er ikke åbnet.

**Betinget GO for en senere formel forhåndsregistrering** af H1 som EXPLORATORY måling på BTC i explore0, hvis alt
dette er opfyldt:

1. En ny direktørordre beslutter, at H1 bliver en formel hypotese. Den tager stilling til ændring 21l punkt 3 (discovery
   i explore0 lukket).
2. Låsen skriver påvirkningen fra R3 ind før data: R3's `se`, placebo og den ubetingede 1 t-spredning er kendte
   gennemsnit. h = 60 er kun beskrivende og kan aldrig give en påstand. Ingen må regne forholdet fra R3's tal ud før låsen.
3. Kun h = 15 afgør, ved α = 0,05 tosidet med t(G − 1). Holm bruges ikke i afgørelsen (eller låsen skriver, hvorfor den
   bruges, og at tærsklen så afhænger af h = 5 og h = 60).
4. Styrken rettes: MDE ca. 1,39× (1 test) eller 1,47× (Holm) ved σ_d 0,7, n 40, G 20. σ_d 1,0 vises også. Mærket bliver
   "kan kun finde effekter på ca. 1,5× eller mere".
5. σ_d får en begrundelse efter ændring 32 punkt 1.
6. Låsen skriver, at FAIL kun udløses med ca. 47 % sandsynlighed uden effekt, så INCONCLUSIVE er et sandsynligt udfald.
7. Proveniensen rettes: `fomc-2021.json` kom fra `fomccalendars.htm`. Antallet 22 + 22 citeres fra J1 og R3. Designets
   explore0 rettes til 2020-03.
8. Kalenderens hashes citeres fra `ingest.done` (events 4437, 4444, 4472, 4480). Filernes hashes citeres fra
   `fetch_log.jsonl`. Selve sammenligningen med disken sker først efter låsen og tidligst 2026-11-14.
9. En helligdagsliste (føderal, 2020-21, med en regel for Juneteenth 2021) committes før låsen.
10. BLS-arkivtjekket enten godkendes af direktøren eller erstattes af en skrevet begrænsning.
11. Dateret ændring i PROTOCOL_V3 med VERIFIED_OWNER_APPROVAL (D5). Claude låser ikke selv (G28).

Uden punkt 2 og 3 er et PASS næppe meget værd. Et resultat på h = 15 ville stadig være udforskning på brugte data.

## 8. Sikkerhedsafvigelser

- **Ingen nye afvigelser fundet.** Ingen af de 44 zip-filer er læst efter R3's kontrol 2026-10-27 kl. 14:37 UTC (atime,
  `relatime`). R3's hentning og kørsel lå i 24a's vindue (14:35-15:25 UTC, K3-frit).
- Min egen læsning af `fetch_log.jsonl` (lab'ets hashlog, ikke markedsdata) satte dens atime til 13:09:47 UTC.
- **Til orientering (ikke en ny afvigelse):** `R3_BLOKERING_2026-10-26.md:31` (2026-10-26) og ændring 32 punkt 4
  (2026-10-28) regnede ubetingede spredninger på de cachede explore0-timebarer før 11-14. Det var tilladt dengang
  (ændring 10b punkt 2, `PROTOCOL_V3.md:870`: banen læser filer i cachen). G01's nuværende tekst ("reading historical
  files already in the cache" før 11-14) er bredere end ejerens oprindelige regel ("ingen historiske forespørgsler").
  Direktøren bør vide, at G01 er strammere end reglen på det tidspunkt.
