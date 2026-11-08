# US_MACRO_0830_DESIGN: 08:30 ET som fast hændelsestid (direktørordre 58 P2, U4)

**Status:** DESIGN-ONLY. Ingen data, ingen lås, ingen alfa. Ingen ny formel hypotese oprettes (ordre 58 P3).
**Skrevet:** 2026-11-09 ca. 00:40 lokal (2026-11-08 23:40 UTC, tjekket med `date`). **Metode:** Kun officielle kalendersider, dokumentation og papirer (WebFetch/WebSearch). Ingen kurser, ingen klines, intet
API-kald til en børs, lab.db ikke åbnet, `python3 -m lab` ikke kørt. Den lokale exchangeInfo-snapshot (2026-11-01) er
kun læst for symbolernes eksistens og onboard-dato. N4-filen i karantæne er ikke læst.
**Mærker:** VERIFIED = selve kilden er læst. ABSTRACT = kun abstract/metadata. UNVERIFIED = ikke bekræftet.

**Konklusion:** 08:30 ET er et reelt og kendt fokuspunkt for volatilitet. Men lab'et har allerede testet retning
(R3 og J1: SCREEN_FAIL). Kun en beskrivende volatilitetsmåling (H1) er forsvarlig. Den giver ingen handel. Den er
næppe afgørbar inden for et år for BTC, og TradFi-perps kan kun måles fremad.

## 1. Hvilke US-udgivelser ligger 08:30 ET?

| Udgivelse | Kilde (vært) | Tid ET | Pr. år | Næste datoer (læst 2026-11-09) | Tilladt vært? | Status |
|---|---|---|---|---|---|---|
| CPI | BLS, https://www.bls.gov/schedule/2026/home.htm | 08:30 | 12 | 11-10, 12-10 | Ja (ændring 14) | VERIFIED |
| PPI | BLS (samme side) | 08:30 | 12 | 11-13, 12-15 | Ja, men `BLS_KEEP` gemmer kun CPI og Employment Situation | VERIFIED |
| Employment Situation (NFP) | BLS (samme side) | 08:30 | 12 | 11-06 (sket), 12-04 | Ja | VERIFIED |
| Ugentlige jobløshedskrav | DOL/ETA, https://oui.doleta.gov/unemploy/claims_arch.asp ("Thursday morning at 8:30am") | 08:30 | ca. 52 | Torsdag; onsdag 2026-11-25 (Thanksgiving) | **Nej** | VERIFIED |
| Detailsalg, durable goods, boligbyggeri | Census, https://www.census.gov/economic-indicators/calendar-listview.html | 08:30 | 12 hver | UNVERIFIED | **Nej** | VERIFIED (tid) |
| BNP (GDP) | BEA, https://www.bea.gov/news/schedule | 08:30 | 12 (3 estimater pr. kvartal) | 11-25, 12-23 | **Nej** | VERIFIED |
| PCE (Personal Income and Outlays) | BEA (samme side) | **08:30**, ikke 10:00 | 12 | 11-25, 12-23 (samme dag som BNP) | **Nej** | VERIFIED |
| Nyboligsalg (New Residential Sales) | Census | **10:00** | 12 | UNVERIFIED | Nej | VERIFIED (tid) |
| FOMC-erklæring | Fed, https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm | 14:00 | 8 | 2026-12-09; 2027: 01-27, 03-17 … | Ja | VERIFIED (datoer); 14:00 fra `ingest.parse_fomc` |

BEA og Census angiver ikke tidszonen på siden. Vi antager ET (UNVERIFIED for tidszonen alene).
Lab'ets kalender (ændring 14, `lab/ingest.py` `BLS_KEEP`) har kun CPI, Employment Situation og FOMC 2020–2023;
`lab/moves.py calendar()` læser årets og næste års sider live (21a). DOL, BEA og Census er ikke tilladte værter
(`tests/test_lab_safety.py`); de kræver ejerens ja og en dateret ændring.

## 2. Ur, sommertid og helligdage

Beregnet lokalt med `zoneinfo` (kun regler, ingen data):

| Periode | 08:30 ET i UTC | i København | Hvorfor |
|---|---|---|---|
| 2026-01-01 → 03-07 | 13:30 | 14:30 | Begge vintertid |
| 2026-03-08 → 03-28 | **12:30** | **13:30** | US sommertid, EU endnu ikke |
| 2026-03-29 → 10-24 | 12:30 | 14:30 | Begge sommertid |
| 2026-10-25 → 10-31 | **12:30** | **13:30** | EU vintertid, US endnu ikke |
| 2026-11-01 → | 13:30 | 14:30 | Begge vintertid |

- 2027 følger samme mønster (skift 03-14, 03-28, 10-31, 11-07).
- Regel: hændelsen defineres i ET (`America/New_York`) og omregnes til UTC. Aldrig "14:30 dansk tid". I de to gab
  (ca. 3 + 1 uge pr. år) kommer tallet en time tidligere på et europæisk ur.
- Helligdage: BLS, DOL og BEA flytter udgivelser rundt om føderale helligdage (fx krav onsdag 2026-11-25). NYSE-listen
  i `lab/sessions.py` er en antagelse, der skal tjekkes mod NYSE før første måling (21y A).

**Flytninger og shutdown 2025 (VERIFIED, https://www.bls.gov/bls/2025-lapse-revised-release-dates.htm):**

| Udgivelse | Oprindelig | Ny | Status |
|---|---|---|---|
| Employment Situation sep. 2025 | 2025-10-03 | 2025-11-20 08:30 | Flyttet |
| Employment Situation okt. 2025 | 2025-11-07 | – | **Aflyst** (etablissementsdata kom med november) |
| Employment Situation nov. 2025 | 2025-12-05 | 2025-12-16 08:30 | Flyttet |
| CPI okt. 2025 | 2025-11-13 | – | **Aflyst** (data kunne ikke indsamles) |
| CPI nov. 2025 | 2025-12-10 | 2025-12-18 08:30 | Flyttet |
| PPI sep. / okt. / nov. 2025 | 10-16 / 11-14 / 12-11 | 11-25 / aflyst / 2026-01-14 | Flyttet / aflyst / flyttet |

- CPI sep. 2025 kom 2025-10-24 (arkivfilnavn `cpi_10242025`, https://www.bls.gov/bls/news-release/cpi.htm; ABSTRACT).
- Konsekvens: en kalender skal være point-in-time. Den skal gemme både den planlagte tid, revisionens dato og den
  faktiske udgivelse. Ellers bliver en aflyst dag til en falsk "kontroldag". BLS-siden for 2026 er ændret senere
  ("Last Modified" 2026-02-18) uden note. Alt fra 2025 ligger desuden i den reserverede periode og læses ikke.

## 3. Instrumenter på tilladte værter (`fapi.binance.com`, kun GET)

| Symbol | Type (snapshot 2026-11-01) | Onboard | Historik brugbar? | Underliggende kl. 08:30 ET |
|---|---|---|---|---|
| BTCUSDT | PERPETUAL, krypto | 2019-09-08 | Kun `explore0` 2020-01..2021-12 | Handler 24/7 |
| ETHUSDT | PERPETUAL, krypto | 2019-11-27 | Kun `explore0` | Handler 24/7 |
| XAUUSDT | TRADIFI_PERPETUAL, råvare | 2025-12-11 | **Nej**: reserveret (2025-01-01 →). Kun fremad | Guld er åbent (søn 18:00–fre 17:00 ET, 21g): normal indekstilstand |
| QQQUSDT | TRADIFI_PERPETUAL, aktie | 2026-04-06 | **Nej**: reserveret. Kun fremad | Kontantmarkedet er lukket (åbner 09:30). Kun premarket |
| SPYUSDT | TRADIFI_PERPETUAL, aktie | 2026-04-06 | **Nej**: reserveret. Kun fremad | Som QQQ |

- `SPXUSDT` i snapshottet er en **memecoin** (COIN, Meme), ikke S&P 500. Den må ikke forveksles.
- **Hvad aktie-perpens pris viser kl. 08:30 ET: UNVERIFIED.** 21g (Binance 2026-05-13) nævner EWMA-tilstand for aktier
  kun ved vedligeholdelse, weekend og helligdage, uden klokkeslæt. En Binance Square-artikel siger, at indekset står
  fast på sidste værdi uden for åbningstid. Begge kan ikke afgøres uden Binances aktuelle regler.
- Står indekset stille i premarket, er en bevægelse kl. 08:30 kun perpens egen tynde bog uden arbitrage. QQQ/SPY mærkes
  da "perp-bog, ikke QQQ". XAU er det reneste TradFi-instrument.

## 4. Kandidathypoteser (udkast, ikke registreret, højst 3)

**H1 (beskrivende volatilitet efter udgivelsen).** På dage med en planlagt CPI- eller NFP-udgivelse er den realiserede
volatilitet i [T, T+h) større end på matchede kontroldage. T = 08:30 ET. h = 5, 15 og 60 min.
- Mål: ln RV, hvor RV = summen af kvadrerede 1m-log-afkast i vinduet. Parret forskel d = ln RV(udgivelse) − ln RV(kontrol).
- Kontrol: samme ugedag og klokkeslæt, nærmeste uge uden BLS-udgivelse kl. 08:30 og uden FOMC inden for ±1 døgn.
- Enhed: udgivelsesdagen (én værdi pr. dag og instrument). Holm over de 3 horisonter. Retning er irrelevant.
- Litteraturen støtter effekten generelt: Ederington & Lee (1993) finder forhøjet volatilitet i ca. 15 min og svagt i
  timer (renter og FX). For BTC er den usikker: Benigno & Rosa (2023) finder BTC "ortogonal" til makronyheder undtagen
  kerne-CPI; Ben Omrane m.fl. (2025) finder reaktioner, mest **før** udgivelserne.

**H2 (beskrivende volatilitet før udgivelsen).** RV i [T−30 min, T) afviger fra kontroldage (tosidet: markedet
kan vente eller positionere sig). Samme enhed, kontrol og mål som H1. Begrundelse: Ben Omrane m.fl. (2025) finder før-effekter.

**Retning: ingen regel foreslås.** Andersen, Bollerslev, Diebold & Vega (2003) viser, at retningen følger
*overraskelsen* (udfald minus konsensus). Lab'et gemmer ingen udfald og har ingen konsensusdata (ændring 14 punkt 1).
R3 (m24, minutdrift 60 min, 57 klynger) gav +0,014 % mod et gulv på 0,46 % og modsat fortegn 2020/2021. J1 (24 t)
fejlede også. En ny retningsregel ville være at variere en afvist test.

**Hvad et PASS ville betyde:** intet handelbart. H1/H2 måler risiko. Det kan højst blive et risikofilter for andre
bøger (fx ingen indgang kl. 08:25–08:45 ET) efter en senere ændring.

## 5. Forstyrrende faktorer

| Faktor | Problem | Håndtering i designet |
|---|---|---|
| Samtidige udgivelser | CPI, krav, detailsalg og BNP falder ofte på samme dag eller uge | Lag A = CPI og NFP. Kontroldage kan have DOL/BEA/Census-tal, som lab'et ikke kender: skævvrider mod nul (konservativt) |
| Få rene kontroldage | Krav hver torsdag, BEA/Census mange andre dage | Kontrol vælges med samme ugedag; andelen af "rene" dage er UNVERIFIED |
| FOMC-uger | Volatilitet før og efter FOMC (fx CPI 2026-12-10 dagen efter FOMC 12-09) | Udelukkes ±1 døgn; tælles som årsag |
| Kontantåbning 09:30 ET | 60-min-vinduet når ind i åbningen | h = 60 mærkes "inkl. åbning"; 5 og 15 min er primære |
| Weekend/helligdag/EWMA | Aktie-perp uden indeks | Kun hverdage; helligdage fra en tjekket NYSE-liste |
| Funding 16:00 UTC | Ligger 2,5–3,5 t efter T | Uden for 5/15/60 min. Ingen justering |
| Lav TradFi-likviditet før åbning | Store spreads, få handler, tomme 1m-barer | Mangler en bar, udelukkes dagen med årsag. Intet udfyldes |
| Regime | 2020 COVID, 2022 inflationsår, kryptos stigende makrofølsomhed efter 2021 | Ingen pooling på tværs af explore0 og fremad; rapporteres hver for sig |
| Allerede set data | R3 og J1 har brugt de samme BTC/ETH-hændelser i explore0 | Tælles i factory-registret; H1 i explore0 er udforskning, aldrig bevis |

## 6. Data og styrke

**Hændelser pr. år (lag A):** CPI 12 + NFP 12 = ca. 24. Med PPI: ca. 36. Krav (52) kræver en ny vært.

**MDE for volatilitetsforholdet.** d er parret ln RV. MDE = (z_α + z_β) · σ_d / √n, forhold = exp(MDE).
σ_d = 0,7 er en **ANTAGELSE** (ikke estimeret; ingen data læst). α = 0,05 tosidet, styrke 80 % → faktor 2,80;
med Holm over 3 horisonter → ca. 3,23.

| n (udgivelsesdage) | Svarer til | MDE-forhold (1 test) | MDE-forhold (Holm, 3) |
|---|---|---|---|
| 12 | ½ år lag A | 1,76× | 1,92× |
| 24 | 1 år lag A | 1,49× | 1,59× |
| 50 | ca. 2 år lag A, eller explore0 BTC/ETH | 1,32× | 1,38× |
| 100 | ca. 4 år lag A | 1,22× | 1,25× |
| 150 | ca. 6 år | 1,17× | 1,20× |

- En stor effekt (≥ 1,5×) er påviselig efter ca. 1 år fremad; en lille BTC-effekt (1,1–1,3×) er ikke. Med |r| i stedet
  for RV er σ_d ca. 1,5 og MDE ved n = 24 ca. 2,4×. Derfor RV fra 1m-barer.

**Vinduer (PROTOCOL_V3, kontrolleret):**
- BTC/ETH historisk: kun `explore0` = 2020-01..2021-12 (ændring 10 punkt 2). **Ikke 2020–2023**: 2022-01..2023-06 er
  familiernes `train3`, 2023-07..12 er validering, 2024 er holdout, 2025-01-01 → er reserveret.
- De 44 cachede BTC/ETH 1m-filer (2020-03..2021-12, R3) dækker explore0. Kalenderen 2020–2021 har kun CPI, NFP og FOMC.
- Historisk hentning og kørsel først fra 2026-11-14 og efter en dateret lås. TradFi-perps: al historik er reserveret;
  kun fremad, efter lås, fra første session efter deploy.
- En ny fremad-stream (1m-klines for XAU/QQQ/SPY) kræver VERIFIED_OWNER_APPROVAL (ordre 58 U1), også ved alfa 0.
- Om en eksisterende collector allerede gemmer 1m BTC/ETH fremad: UNVERIFIED (lab.db er ikke åbnet).

## 7. Litteratur

| Kilde | Hvad den siger | URL | Status |
|---|---|---|---|
| Andersen, Bollerslev, Diebold & Vega (2003), AER 93(1):38–62 | Overraskelser flytter FX-kursens middelværdi straks; dårlige nyheder vejer tungere | https://www.aeaweb.org/articles?id=10.1257/000282803321455151 | ABSTRACT |
| Ederington & Lee (1993), J. Finance 48(4):1161–1191 | Planlagte tal forklarer det meste af tid-på-dagen-volatiliteten; forhøjet i ca. 15 min | https://ideas.repec.org/a/bla/jfinan/v48y1993i4p1161-91.html | ABSTRACT |
| Benigno & Rosa (2023), "The Bitcoin–Macro Disconnect", NY Fed SR 1052 | BTC reagerer næppe på makro- og pengepolitiske nyheder, undtagen kerne-CPI | https://www.newyorkfed.org/research/staff_reports/sr1052 | ABSTRACT |
| Ben Omrane, Dabbou, Saadi, Savaser & Sebai (2025), IREF 103, 104509 | BTC/ETH-volatilitet (5 min, 2016–2023) reagerer på udvalgte tal, mest før udgivelsen | https://ideas.repec.org/a/eee/reveco/v103y2025ics1059056025006720.html | ABSTRACT |
| En nyere Fed-artikel om styrket kryptoreaktion efter 2021 (ca. −30 bp pr. 1 sd CPI-overraskelse) | Kun set i et sekundært søgeresumé | – | UNVERIFIED |

## Hvad der kræves før lås

1. Direktørens og ejerens beslutning om, at H1 (og evt. H2) skal være en formel hypotese. Ordre 58 tillader det ikke nu.
2. En dateret ændring i PROTOCOL_V3 før data, med mål, kontrolregel, horisonter, Holm, minimumsantal og stopkriterier.
3. Et estimat af σ_d fra en kilde, der ikke er testdata, eller en fast antagelse skrevet i låsen.
4. En point-in-time kalender: planlagt tid, revision og faktisk udgivelse. PPI tilføjes `BLS_KEEP` som kodeændring.
5. Ejer-ja til DOL, BEA og Census som værter, hvis krav, BNP, PCE eller detailsalg skal med (ellers kun som støj i
   kontrollen).
6. Binances aktuelle regel for aktie-perpens indeks i premarket (VERIFIED), før QQQ/SPY indgår.
7. En tjekket NYSE- og føderal helligdagsliste for hele måleperioden.
8. VERIFIED_OWNER_APPROVAL til en ny 1m-stream for TradFi-perps, med alfa 0 (kun beskrivende). Ingen kørsel før
   2026-11-14, ingen deploy i K1–K3; pm_lp, HFC-1, STRAKS, S1 og COIN-M røres ikke.
