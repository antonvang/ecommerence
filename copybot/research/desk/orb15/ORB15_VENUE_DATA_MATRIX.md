# ORB-15: venue- og datamatrix (direktørordre 57, P2)

**Status:** DESIGN-ONLY. Ingen data er hentet. Ingen markedsdata-forespørgsel er lavet (heller ikke på tilladte værter).
Kun lokale filer (read-only) og dokumentationssider (WebSearch/WebFetch) er brugt.
**Skrevet:** 2026-11-08 ca. 23:58 lokal (22:58 UTC), tid tjekket med `date`.
**Kilder i repoet:** `tests/test_lab_safety.py` linje 15-45 (ALLOWED_HOSTS), `research/PROTOCOL_V3.md` (§2, 10b, 16d/16f-
præcisering, 21g, 21h, 24/24a), `research/studies/ONLINE_EDGES_2026-11-05.md` §8-12, `research/studies/COSTS_2026-10-24.md`,
`research/studies/MISSION27_1_2026-11-01.md`, `research/studies/DK_RETAIL_P0_2026-11-06.md`, `research/LINUX_DRIFT.md`,
`lab/sessions.py`, `lab/hlcensus.py`, `lab/r3.py`.
**Lokalt snapshot:** `/tmp/claude-1000/-home-anton-copybot-dev/511b8354-e362-45ef-ba07-489e27e68460/scratchpad/exinfo_1101.json`
(Binance USD-M `exchangeInfo`, `serverTime` 2026-11-01 10:30:24 UTC, 942 symboler: 703 PERPETUAL, 235 TRADIFI_PERPETUAL,
4 leveringskontrakter).

## 0. Faste regler, der gælder for alle rækker

| Regel | Kilde | Betydning for ORB-15 |
|---|---|---|
| Vinduer: træning 2022-01-01..2023-06-30, validering 2023-07-01..12-31, slut-test 2024 (forseglet, menneskelig godkendelse), **reserveret 2025-01-01 → "Læses aldrig"** | PROTOCOL_V3 §2 | Alt, der kun har historik fra 2025, kan ikke testes historisk. |
| TradFi-perps har al historik i den reserverede periode og er UNTESTABLE historisk | PROTOCOL_V3 21c punkt 8 (linje 2318) | Binance-aktieperps: kun fremad. |
| Ingen historiske forespørgsler før 2026-11-14 00:00 UTC | brugerens regel; PROTOCOL_V3 10b, 24a | Tidligste lovlige hentedato er 2026-11-14. |
| Ordre 57: DATA COLLECTION BLOCKED, LIVE TRADING NO-GO | `research/reviews/INBOX.md` 2026-11-08 | Selv efter 11-14 kræves en ophævelse fra direktør/ejer og en dateret lås. |
| Ny datalinje eller ny vært kræver en dateret ændring før data | memory "Data host gates"; PROTOCOL_V3 praksis | Gælder fx 1m-klines for QQQUSDT og Hyperliquid `dex="xyz"`. |
| US-sommertid | `zoneinfo` America/New_York, tjekket lokalt | 09:30 ET = 13:30 UTC i sommertid og 14:30 UTC i vintertid. 2026: sommertid 03-08 til 11-01. 2027: fra 03-14. I dag (11-08) er åbningen 14:30 UTC. |

**ALLOWED_HOSTS (uddrag):** `data.binance.vision`, `fapi.binance.com`, `data-api.binance.vision`, `api.hyperliquid.xyz`,
`www.binance.com` (kun meddelelser) m.fl. Der er **ingen** vært for CME-data og **ingen** vært for amerikanske aktie-/ETF-kurser.

## 1. Findes instrumentet, og hvor kommer data fra?

| Marked | Findes? Evidens | Tilladt datakilde og vært | På ALLOWED_HOSTS? | Tidsopløsning | Historik og tidligste lovlige forespørgsel |
|---|---|---|---|---|---|
| **(a) CME NQ (E-mini Nasdaq-100)** | Ja. $20 × Nasdaq-100, tick 0,25 pt = $5 (CME-specsiden via søgeuddrag; Ironbeam KB https://www.ironbeam.com/knowledge-base/e-mini-nasdaq-100-futures-nq-contract-specifications/). CME's egen side https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.contractSpecs.html gav timeout to gange: **UNVERIFIED direkte**. "NQ 12-26" = december 2026-kontrakten. | Ingen. CME-data kræver leverandør eller konto. | **Nej** | Ikke relevant (ingen kilde) | Ingen lovlig kilde. Ingen dato hjælper. |
| **(b) QQQ ETF** | Ja. Testet af Zarattini & Aziz 2023 (forfatter-PDF, se litteraturtjekket). | Ingen. Lab'et har ingen vært for ETF-kurser. | **Nej** | Ikke relevant | Ingen lovlig kilde. |
| **(c) Binance USD-M TradFi-perps** | Ja, i det lokale snapshot (tabel 1a). **Ingen** indeks-perp på Nasdaq-100: intet symbol med NDX, NAS, US100 eller TECH100. Nasdaq-eksponering findes kun via ETF-perps (QQQ, TQQQ, SQQQ). | `fapi.binance.com` (klines, mark-/indekspris, funding; kun GET) og evt. `data.binance.vision` (om TradFi-symboler ligger i arkivet: **UNVERIFIED**). | **Ja** | 1m-klines findes som interval på fapi (standard). Lab'ets census er kun timebaseret. | Al historik er fra 2026 = reserveret. **Kun fremad.** Fremad-indsamling af 1m kræver en dateret lås og tidligst 2026-11-14, og ordre 57 blokerer indsamling. |
| **(d) Hyperliquid HIP-3 (trade[XYZ])** | Ja ifølge dokumentation: `XYZ100` og `SP500` på HIP-3-deploymentet `xyz` (https://docs.trade.xyz/perpetuals/specifications-and-schedules/specification-index.md; https://docs.trade.xyz/perpetuals.md). Hyperliquid-docs bruger selv `"xyz:XYZ100"` som eksempel (https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint). Lanceringsdato: **UNVERIFIED** (sekundære kilder nævner en hændelse på XYZ100 i december 2025). | `api.hyperliquid.xyz` `POST /info`: `candleSnapshot` med `"xyz:XYZ100"`, `metaAndAssetCtxs` med `dex`. | **Ja (værten)**. Men `lab/hlcensus.py` læser kun standard-dex'en; `dex="xyz"` er en ny datalinje. | 1m til 1M. **Kun de seneste 5 000 candles** (docs): ved 1m ca. 3,5 døgn. | Ingen reel historik. **Kun fremad** og først efter en dateret ændring. |
| **(e) BTCUSDT/ETHUSDT-perps med US-åbningen som tidsreference** | Ja: BTCUSDT PERPETUAL, TRADING, onboard 2019-09-08 17:55 UTC; ETHUSDT PERPETUAL, TRADING, onboard 2019-11-27 07:45 UTC (snapshot). | `data.binance.vision` månedsarkiver (1m). | **Ja** | 1m | Arkiver fra 2019/2020. **Allerede lokalt:** 44 filer 1m BTC/ETH 2020-03..2021-12 (explore0) i produktionens cache `data/lab/market/klines_1m` (hentet til R3, ændring 24/24a). Kun fillisten er set, intet indhold. Træning/validering 2022-2023 i 1m ligger ikke i cachen: hentning tidligst 2026-11-14 og kun efter en lås. 2024 kræver menneskelig godkendelse. 2025+ aldrig. |

### 1a. Lokalt snapshot: symboler med QQQ, SPY, NDX, NAS, US100, TECH100, NVDA, TSLA, XAU

Søgt som delstreng i `symbol`. `onboardDate` er omregnet fra ms til UTC.

| Symbol | contractType | status | underlyingType | underlyingSubType | onboardDate (UTC) |
|---|---|---|---|---|---|
| QQQUSDT | TRADIFI_PERPETUAL | TRADING | EQUITY | TradFi | 2026-04-06 13:30 |
| SPYUSDT | TRADIFI_PERPETUAL | TRADING | EQUITY | TradFi | 2026-04-06 13:40 |
| TQQQUSDT | TRADIFI_PERPETUAL | TRADING | EQUITY | TradFi | 2026-06-29 13:40 |
| SQQQUSDT | TRADIFI_PERPETUAL | TRADING | EQUITY | TradFi | 2026-06-29 13:45 |
| NVDAUSDT | TRADIFI_PERPETUAL | TRADING | EQUITY | TradFi | 2026-03-26 14:40 |
| TSLAUSDT | TRADIFI_PERPETUAL | TRADING | EQUITY | TradFi | 2026-01-28 14:30 |
| XAUUSDT | TRADIFI_PERPETUAL | TRADING | COMMODITY | TradFi | 2025-12-11 08:05 |
| XAUTUSDT | PERPETUAL | TRADING | COIN | RWA, Crypto | 2026-03-26 14:00 |
| BANANAS31USDT | PERPETUAL | TRADING | COIN | Meme, Crypto | 2025-03-22 09:15 (falsk træf på "NAS") |

- NDX, US100, TECH100: **0 træf**. Ingen Nasdaq-100-indeksperp på Binance i snapshottet.
- 197 TradFi-perps har `underlyingType` EQUITY. Den tidligste er TSLAUSDT (2026-01-28 14:30 UTC). IWMUSDT findes også.
- QQQUSDT-filtre: tick 0,01; min. mængde 0,01; markedsordre højst 2 000 stk.; min. notional 5 USDT; PERCENT_PRICE ±3 %;
  `requiredMarginPercent` 5 (højst 20x); `maintMarginPercent` 2,5; `liquidationFee` 1,5 %.
- **Afvigelse at rette senere:** ONLINE_EDGES §10 siger, at XAUUSDT "kun har eksisteret siden 08.01.2026". Snapshottet
  giver `onboardDate` 2025-12-11 08:05 UTC. Ingen af datoerne påvirker ORB-15.

## 2. Handelstider, åbning og omkostninger

| Marked | Handelstid og kalender | Hvordan "åbningen" defineres | Relevante omkostninger (med kilde) |
|---|---|---|---|
| **(a) CME NQ** | Globex søndag-fredag 17:00-16:00 CT med 1 times daglig pause 16:00-17:00 CT (Ironbeam KB; CME-siden UNVERIFIED). RTH for det underliggende: 09:30-16:00 ET. CME-helligdage og tidlige lukninger. | Globex-sessionen åbner kl. 18:00 ET dagen før. Videoens "opening range" er formentlig 09:30-09:45 ET (kontantåbningen), men det står ikke i videoen: **UNKNOWN** (se ORB15_VIDEO_RULE_AUDIT.md). | Point $20, tick 0,25 pt = $5. NFA: $0,01 pr. side fra 2026-07-01, $0,02 fra 2027-07-01 (VERIFICERET: https://www.nfa.futures.org/faqs/members/nfa-assessment-fees.html). Mæglerkommission fx $0,50 pr. side (Topstep Brokerage, https://topstepbrokerage.com/commissions-and-fees; børsgebyr står dér som "varies"). CME børs- + clearinggebyr: **UNVERIFIED** (CME-side timeout; ét udateret sekundært tal $1,33 pr. side). Arbejdsantagelse, ikke verificeret: $2-5 pr. side i alt plus 1 tick slippage pr. side → $14-20 pr. rundtur. Ved 29 517 er notional ≈ $590 340, så rundturen er ca. 0,24-0,34 bp. Videoens "+$1,000" på 1 kontrakt = 50 point = 200 ticks. |
| **(b) QQQ** | Nasdaq/NYSE RTH 09:30-16:00 ET plus før- og eftermarked. NYSE-helligdage. `lab/sessions.py` har kun helligdage fra 2026-11-26 til 2027-06-30 og kalder listen en antagelse. | Åbningsauktionen 09:30 ET. Range = 09:30:00-09:44:59 ET. | Kommission $0,0035 pr. aktie (IBKR Pro, citeret i Zarattini, Barbon & Aziz 2024). Ca. 0,05 bp pr. side ved en kurs omkring $650 (kursen er hentet fra lab'ets egne papirhandler på QQQUSDT i november, ikke fra en ny forespørgsel). Zarattini & Aziz 2023 brugte $0,0005 pr. aktie og ingen slippage. Spread typisk 1 cent ≈ 0,15 bp: **UNVERIFIED** (ingen markedsdata). SEC-gebyr ved salg: **UNVERIFIED**. **Juridisk:** EU-detailkunder kan normalt ikke købe amerikanske ETF'er pga. PRIIPs-KID (SEKUNDÆR: Europa-Parlamentets spørgsmål E-9-2021-004745, https://www.europarl.europa.eu/doceo/document/E-9-2021-004745_EN.html, ikke åbnet). |
| **(c) Binance QQQUSDT (og SPY/TQQQ)** | Perpen handler 24/7. Indekset følger QQQ i normal handelstid. "Orderbook EWMA mode" under den daglige vedligeholdelse, i weekender og på helligdage; meddelelsen giver ingen klokkeslæt (`53bfc176…`, verificeret i PROTOCOL_V3 21g). Før- og eftermarked: **UNVERIFIED**. | Samme klokkeslæt som QQQ: 09:30 ET via `lab/sessions.py` (ET-zone, NYSE-dage). Perpen har ingen egen åbning. | Taker 0,04 %, maker 0 for TradFi "until further notice" fra 2026-03-31 (`a4c3f195…`, PROTOCOL_V3 21g). Standard-taker 0,05 % (PROTOCOL_V3 21h). Binance' gebyrside https://www.binance.com/en/fee/futureFee viste ingen tabel: UNVERIFIED direkte. **Rundtur taker 8 bp (10 bp uden kampagne)**. Bogens rundtur ved $5k: 0,14 bp (MISSION27_1). Funding hver 8. time (00/08/16 UTC); alle 27 observerede TradFi-afregninger var præcis 0 (LINUX_DRIFT). Juridisk: Binance har ingen MiCA-enhed i ESMA-registret (DK_RETAIL_P0). Lab'et er kun papir. |
| **(d) Hyperliquid xyz:XYZ100** | "External" handelstid søndag 18:00 ET til fredag 17:00 ET. Daglig vedligeholdelse 17:00-18:00 ET mandag-torsdag. Følger futures-helligdage. Uden for disse tider er der en intern session, hvor prisen kommer fra perpens egen bog (specification-index). | Ingen egen åbning. 09:30 ET skal sættes som ur-tid. Oraklet skifter ved kontantåbningen: i kontantsessionen er spot-indekset orakelpris; i den udvidede session er det futures-prisen diskonteret med en EMA af basis (https://docs.trade.xyz/perpetuals/markets/equity-indices.md). | Standard HIP-3 på Tier 0: taker 0,090 %, maker 0,030 %, dvs. 2× de validator-drevne perps' 0,045 %/0,015 % (https://docs.trade.xyz/perpetuals/mechanics/fees.md; https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees). Growth mode giver taker 0,009 %/maker 0,003 %, men om den gælder XYZ100: **UNVERIFIED**. Rundtur taker: 18 bp (standard) eller 1,8 bp (growth mode). Max gearing 30x; funding-multiplikator 0,5; fundinginterval **UNVERIFIED** i de læste sider. |
| **(e) BTC/ETH-perps** | 24/7. Ingen kontantåbning. | Ur-tid 09:30 ET på NYSE-handelsdage: 13:30 UTC (sommertid) eller 14:30 UTC (vintertid). `lab/sessions.py` mangler helligdage før 2026-11-26; en historisk test skal have en verificeret NYSE-kalender for 2020-2023. | Taker 0,05 % i dag, 0,04 % i 2019-2021, maker 0,02 % (PROTOCOL_V3 21h). Rundtur taker 8-10 bp. Bogens rundtur ved $5k: BTC 0,01 bp, ETH 0,04 bp (MISSION27_1). Funding 00/08/16 UTC. En position fra US-åbningen til 16:00 ET (20:00/21:00 UTC) krydser afregningen kl. 16:00 UTC. |

## 3. Forskelle, generalisering til NQ og anbefaling

| Marked | Markedsspecifikke forskelle | Generaliserer resultatet til NQ? | Anbefaling |
|---|---|---|---|
| **(a) CME NQ** | Referencemarkedet. Handler næsten døgnet rundt, så kl. 09:30 ET er ikke sessionens start. Natten har allerede prissat meget af nyhedsstrømmen. 1 kontrakt ≈ $590k notional. | Ja, det er NQ. | Målet for påstanden. **Kan ikke testes i lab'et**: ingen vært, ingen data, og konti/nøgler er forbudt. |
| **(b) QQQ** | Samme indeks som NQ. Handler kun i US-tid. En overnight-gap ses først ved åbningen. ETF-pris ≈ 1/41 af indekset (forhold ikke verificeret). | Ja, nærmest: samme underliggende i samme timer. Bruttosignalet bør ligne NQ's RTH-signal. NQ's omkostning i bp er af samme størrelse. | Bedste proxy efter NQ, men **BLOCKED**: ingen tilladt vært. EU-detail kan heller ikke handle den. |
| **(c) Binance QQQUSDT** | Perp på en ETF, ikke på indekset. Tynd bog uden for RTH. EWMA-tilstand i weekender og helligdage. Funding. Gebyrer ca. 25-40 gange NQ's rundtur i bp (8-10 bp mod ca. 0,3 bp). Kun handlet siden 2026-04-06. | **Delvist.** Brutto i RTH (helst målt på indeksprisen, som følger QQQ) kan sige noget om NQ. Netto på perpen siger kun noget om perpen. | **Eneste Nasdaq-nære instrument på en tilladt vært.** Kun fremad. Kræver en dateret lås, en ny datalinje (1m-klines eller indekspris-klines; om `indexPriceKlines` virker for TradFi-par: UNVERIFIED) og ophævelse af ordre 57's indsamlingsblok. Tidligst fra 2026-11-14. |
| **(d) Hyperliquid xyz:XYZ100** | Indeks-perp, hvis orakel bygger på spot-indekset og indeks-futures. Handelstiden følger futures. Egen bog i den interne session. Isoleret HIP-3-dex med egne risici (orakel, deployer, slashing). Gebyrer 2× standard, medmindre growth mode gælder. | Bedre end QQQUSDT i indeksets identitet. Bogen og omkostningerne er perpens egne. | Interessant, men kræver en ny dateret ændring (`dex="xyz"`), og der er ingen historik (5 000 candles). Kun fremad. Lavere prioritet end (c), fordi taker-gebyret er højere og growth mode ikke er bekræftet. |
| **(e) BTC/ETH** | Intet underliggende med kontantåbning. US-åbningen er kun en mulig volumen- og nyhedshændelse i krypto (ikke verificeret her). 24/7, funding, ingen gap. | **Nej.** Det er en anden hypotese: "krypto reagerer på US-åbningen". Et resultat siger intet om NQ. | Mest gennemførlig (data, vært og lovlige vinduer findes; explore0 2020-03..2021-12 ligger allerede i cachen). Kun som en **separat** hypotese med egen lås, mærket som udforskning. Bemærk, at de 44 filer allerede er brugt af R3 (anden regel), så de er ikke helt "usete". |

## 4. Konklusion

**Mest troværdige marked til en test, lab'et kan gennemføre:** Binance **QQQUSDT** fremad fra tidligst 2026-11-14.
Det er det eneste instrument med Nasdaq-100-eksponering på en tilladt vært. Rapportér brutto (målt på indeksprisen i RTH,
det tal der kan overføres til NQ) og netto med perpens gebyrer (8-10 bp pr. rundtur) hver for sig. BTC/ETH ved
US-åbningen kan køres som en separat udforskning på de 1m-filer, der allerede ligger lokalt, men den siger intet om NQ.

**Manglende godkendelser:**

| # | Godkendelse | Hvem |
|---|---|---|
| 1 | Ophævelse af "DATA COLLECTION BLOCKED" i ordre 57 for den konkrete datalinje | Direktør/ejer |
| 2 | En dateret LÅS/ændring i `research/PROTOCOL_V3.md` før data: regler, nøgle, metode, primært estimand, stopregel | Claude under mandat, før data |
| 3 | Ny datalinje: 1m-klines (eller indekspris-klines) for QQQUSDT på `fapi.binance.com` | Dateret ændring; tidligst 2026-11-14 |
| 4 | For (d): `dex="xyz"` på `api.hyperliquid.xyz` | Dateret ændring |
| 5 | For (e): hentning af 1m 2022-2023 tidligst 2026-11-14 efter lås; slut-test 2024 kun efter menneskelig godkendelse | Lås + ejer for 2024 |
| 6 | En verificeret NYSE-kalender for alle testede år (`lab/sessions.py` dækker kun 2026-11-26..2027-06-30) | Før kode |

**Umuligt under de nuværende regler:**

- Enhver test på CME NQ eller QQQ-ETF'en: ingen tilladt vært, og data kræver konti eller nøgler.
- Enhver historisk test af Binance-aktieperps eller HIP-3-perps: al historik ligger i den reserverede periode fra 2025,
  og Hyperliquid giver kun de seneste 5 000 candles.
- At efterprøve videoens ene handel (ORB_Long 1 @ 29517, "+$1,000"): ingen NQ-data. Én handel er en anekdote.
- Live-handel og rigtige penge (ordre 57: LIVE TRADING NO-GO). Desuden: EU-detail har ingen adgang til QQQ-ETF'en
  (PRIIPs, sekundær kilde) eller til Binance (ingen MiCA-enhed).
