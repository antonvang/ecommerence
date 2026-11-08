# ORB-15: kildekontrol af ORB-litteraturen (direktørordre 57, P4)

**Status:** DESIGN-ONLY. Kun dokumentationssider og PDF'er er læst. Ingen markedsdata er hentet.
**Skrevet:** 2026-11-09 ca. 00:02 lokal (2026-11-08 ca. 23:02 UTC), tid tjekket med `date`.
**Metode:** Primærkilder først (forfatter-PDF, universitetsrepositorium, forlagets eller RePEc's abstract). SSRN's
abstractsider gav HTTP 403, så SSRN er ikke åbnet direkte. To PDF'er er hentet med WebFetch og konverteret lokalt med
`pdftotext` i scratchpad (`/tmp/claude-1000/-home-anton-copybot-dev/511b8354-e362-45ef-ba07-489e27e68460/scratchpad/orbpdf/`).
Højst ét kort citat pr. kilde; resten er omskrevet. Tal er gengivet, som forfatterne skriver dem.

**Status pr. kilde:** VERIFIED = selve kilden er læst. ABSTRACT = kun abstract/metadata er læst. UNVERIFIED = kilden kunne
ikke åbnes; oplysningen kommer fra en anden kilde.

## 1. Design (én række pr. kilde)

| # | Kilde | Type | Marked | Range | Regler (indgang, stop, mål, exit) | Periode | Gearing | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | Zarattini & Aziz, "Can Day Trading Really Be Profitable? …" SSRN 4416622. Første version 2023-04-24, denne version 2025-09-22. PDF: https://concretumgroup.com/wp-content/uploads/2026/02/Can-Day-Trading-Really-Be-Profitable.pdf | Working paper (ikke peer review) | QQQ og TQQQ | **5 min** | Retning = første 5-min-lys (doji: ingen handel). Indgang ved åbningen af lys 2. Stop ved lys 1's low (long) eller high (short). Mål 10R, ellers lukning ved dagens slutning. 1 % risiko pr. handel. Variant: stop = 5 % af 14-dages ATR. | 2016-01-01 til 2023-02-17 | Højst 4x; TQQQ giver 3x oveni | VERIFIED (forfatter-PDF) |
| 2 | Zarattini, Barbon & Aziz, "A Profitable Day Trading Strategy For The U.S. Equity Market", SSRN 4729284, 2024-02-16. PDF: https://www.alexandria.unisg.ch/server/api/core/bitstreams/3c2989c4-688d-4d78-8a71-f02690990d51/content | Working paper (Swiss Finance Institute-serie; ikke peer review) | > 7 000 US-aktier; "Stocks in Play" | **5 min** (hoved); også **15**, 30, 60 min | Filtre: kurs > $5, 14-dages snitvolumen > 1 mio., ATR14 > $0,50, relativ volumen ≥ 100 %, top 20 efter relativ volumen. Stop-ordre ved rangens high/low i lys 1's retning. Stop 10 % af ATR fra indgang. Exit ved dagens slutning. 1 % risiko pr. position. | 2016-01-01 til 2023-12-31 | Højst 4x | VERIFIED (universitets-PDF) |
| 3 | Krueger, "The opening-range breakout paper, replicated on five indices: gross reproduced, net zero", MQL5-blog 2026-09-25. https://www.mql5.com/en/blogs/post/776235 | **Praktiker-blog** (uafhængig replikation, ikke peer review) | CFD'er på NQ, SPX, Dow, DAX, FTSE (kontantsession) | **5 min** | Samme regler som #1: retning af lys 1, indgang ved lys 2's åbning, stop på modsat side af lys 1, mål 10R eller lukning. Mindste risiko = 2 × rundturens omkostning. | 2015-01 til 2026-06 (2 899-2 937 sessioner pr. marked) | Opgjort i R (ingen gearing nødvendig) | VERIFIED (blogsiden) |
| 4 | Tsai, Wu, Syu, Lei, Wu, Ho & Wang, "Assessing the profitability of timely opening range breakout on index futures markets", *IEEE Access* 7:32061-32071 (2019). DOI 10.1109/ACCESS.2019.2899177. Abstract: https://scholars.lib.ntu.edu.tw/handle/123456789/429807 | **Peer-reviewed** | Indeks-futures: DJIA, S&P 500, NASDAQ, HSI, TAIEX | "Timely ORB": den bedste "probing time" findes pr. marked; kort i USA, længere i Asien. Præcis længde: UNVERIFIED | Futures' aktive timer afstemmes efter aktiemarkedets åbning. Stop/mål: ifølge #2 brugte de hverken stop eller mål (UNVERIFIED, fuldtekst ikke læst) | 2003-2013, 1-minutdata | UNVERIFIED | ABSTRACT (NTU-repositorium; Crossref-metadata) |
| 5 | Holmberg, Lönnbark & Lundström, "Assessing the profitability of intraday opening range breakout strategies", *Finance Research Letters* 10(1):27-33 (2013). DOI 10.1016/j.frl.2012.09.001. https://ideas.repec.org/a/eee/finlet/v10y2013i1p27-33.html | **Peer-reviewed** | Råolie-futures (nøgleord; abstractet nævner ikke markedet direkte) | Ikke en fast tidsrange: indgang, når kursen passerer en forudbestemt tærskel fra åbningen (volatilitets-ORB) | Tærskel fra en model med normalfordelte afkast; bygger på den fælles fordeling af open, high, low og close. Resten: UNVERIFIED | 1983-2011 ifølge #2 (UNVERIFIED) | UNVERIFIED | ABSTRACT (RePEc og SWoPEc). Working paper-PDF på econ.umu.se gav certifikatfejl: ikke åbnet |
| 6 | Gao, Han, Li & Zhou, "Market intraday momentum", *Journal of Financial Economics* 129(2):394-414 (2018). DOI 10.1016/j.jfineco.2018.05.009. https://econpapers.repec.org/RePEc:eee:jfinec:v:129:y:2018:i:2:p:394-414 | **Peer-reviewed**; beslægtet, **ikke ORB** | SPY + 10 andre ETF'er | Første halve time (fra forrige dags lukning) forudsiger sidste halve time | Ikke en breakout-regel | 1993-2013 | Ikke relevant | ABSTRACT |
| 7 | Toby Crabel, *Day Trading with Short Term Price Patterns and Opening Range Breakout*, Traders Press 1990 (ISBN 0934380171 ifølge en boghandlerliste) | **Praktiker-bog** | Futures (UNVERIFIED) | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | Kun bogens eksistens er bekræftet (boghandlere, Wikipedia). Indholdet: **UNVERIFIED** |
| 8 | Lundström, "Day trading returns across volatility states", Umeå Economic Studies 861 (2013, revideret 2017) | Working paper | Råolie- og S&P 500-futures (ifølge #2) | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | **UNVERIFIED** (kun citeret i #2) |

## 2. Omkostninger, prøvetype, tal og interessekonflikter

| # | Brutto/netto | Omkostningsantagelser | IS / OOS / fremad | Rapporterede tal (som angivet) | Interessekonflikter |
|---|---|---|---|---|---|
| 1 | Netto for kommission; **brutto for spread og slippage** | Kommission $0,0005 pr. aktie. Citat: "We assumed no slippage in fills." Startkapital $25 000. | **Kun in-sample.** Ingen OOS, ingen fremad-test. Parametersweep (stop og mål) på samme data. | QQQ: samlet 676 %, 33 % pr. år, Sharpe 1,13, MDD 22 % (tabel 2). 1 795 handler, hitrate 24 %, gennemsnit 0,13R pr. handel. Alfa 33 % p.a. netto for kommission (p = 0,0025). TQQQ: 1 484 %, 48 % pr. år, Sharpe 1,19, MDD 28 %. ATR-varianten: alfa 93 % og $25 000 → $6,4 mio.; forfatterne kalder den selv muligvis urealistisk, fordi slippage er sat til 0. Buy-and-hold QQQ: 169 %. | Aziz: Bear Bull Traders og Peak Capital Trading (tradinguddannelse/-fællesskab og prop-firma). Zarattini: Concretum Research (forskning og strategier til kunder; "Trading Lab" på hjemmesiden) og grundlægger af R-Candles.com (backtester). |
| 2 | Netto for kommission. Slippage: ordet forekommer ikke i PDF-teksten (søgt med grep); behandlingen er **UNVERIFIED** | Kommission $0,0035 pr. aktie (IBKR Pro, laveste trin). $25 000 start. | **Kun in-sample.** Valg af top 20 og relativ volumen er gjort på samme data. | Top 20 Stocks in Play, 5 min: samlet 1 637 %, IRR 41,6 %, Sharpe 2,81, MDD 12 %, alfa 35,8 %. Basisstrategi uden relativ volumen: 29 %, Sharpe 0,48. **15 min: 272 %, IRR 17,4 %, Sharpe 1,43, MDD 11 %, alfa 16,9 %.** 30 min: 21 %, Sharpe 0,21. 60 min: 39 %, Sharpe 0,40. S&P 500: 198 %. Forfatterne kalder årsagen til 5 minutters forspring uklar. | Samme som #1 (Aziz, Zarattini). Barbon: University of St. Gallen og Swiss Finance Institute (akademisk). |
| 3 | **Begge**, side om side | Spread + slippage pr. handel som andel af risikoen: NQ 2,5 point, SPX 0,8, Dow 4,0, DAX 2,5, FTSE 1,5. Kommission ikke angivet. | Ingen formel OOS. Forfatteren kalder 2021-2026 "uden for papirets periode". Data er forfatterens egne minutdata; kilden er ikke angivet. | NQ: brutto +0,131R (t 2,9), netto +0,002R (t 0,0). SPX netto −0,081R, Dow −0,081R, DAX −0,038R, FTSE −0,079R. Intet marked er signifikant positivt netto. 2015-2017: negativ i alle markeder. NQ 2021-2026 netto højst ca. +0,06R. Hitrate på NQ 23,2 %. | Forfatteren sælger værktøjer til prop-firma-konti (sælgerside linket). Ingen ORB-produkt promoveres i indlægget. |
| 4 | UNVERIFIED (abstractet nævner ikke omkostninger) | UNVERIFIED | Abstractet nævner ikke OOS | Årligt afkast over 8 % med p under 3 % i alle fem markeder. TAIEX: 20,28 % pr. år. | Ingen kendte. |
| 5 | UNVERIFIED | UNVERIFIED (abstractet nævner ikke omkostninger) | Bootstrap-test (nøgleord). OOS: UNVERIFIED | Afkast "signifikant over nul" og en hitrate over et fair spil (omskrevet fra abstractet). Ifølge #2 kom gevinsten mest i 2000-2011 (UNVERIFIED). | Ingen kendte. |
| 6 | Abstractet nævner ikke omkostninger: UNVERIFIED | UNVERIFIED | Ikke en handelstest i abstractet | Forudsigelsen er statistisk og økonomisk signifikant; stærkere på volatile dage, dage med høj volumen, recessionsdage og dage med store makrotal. Ingen talværdier i abstractet. | Ingen kendte. |
| 7 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | Praktiker; bogen sælges brugt til høje priser (sekundært). |
| 8 | UNVERIFIED | UNVERIFIED | UNVERIFIED | Ifølge #2: ORB-gevinsten vokser med volatiliteten. UNVERIFIED | Ingen kendte. |

**Note om en relateret kilde:** Lab'ets studie `research/studies/ONLINE_EDGES_2026-11-05.md` §9 citerer Zarattini, Aziz &
Barbon, "Beat the Market" (SFI WP 24-97): 19,6 % p.a. netto, Sharpe 1,33 (2007-2024) på SPY. Det er intradag-momentum
("Noise Area"), ikke ORB. Det er ikke genverificeret i denne ordre.

**Note om videoen:** @jamiedoestradez viser én handel (ORB_Long 1 @ 29517, "+$1,000") i NinjaTrader. På NQ er $1 000 = 50
point. Det er en anekdote, ikke en stikprøve. Om kontoen er live, simuleret eller en afspilning: **UNKNOWN**.

## 3. Hvad litteraturen støtter, og hvad den ikke støtter

### Støtter (med forbehold)

1. **En lille bruttofordel ved en 5-minutters ORB på amerikanske indeks i 2016-2023.** Kilde #1 finder 0,13R pr. handel på
   QQQ in-sample. Kilde #3 reproducerer det samme tal uafhængigt på en NQ-CFD (+0,131R, t 2,9).
2. **Peer-reviewed støtte til ORB på indeks-futures, inklusive NASDAQ-futures, i 2003-2013** (#4). Den bedste range var
   kort i de amerikanske markeder. Omkostningerne er ukendte, og perioden er gammel.
3. **En beslægtet mekanisme:** intradag-momentum fra dagens start til dagens slutning i SPY (#6, peer-reviewed).

### Støtter IKKE

1. **Ingen fundet kilde tester en 15-minutters ORB på NQ eller QQQ.** Kilde #1 tester kun 5 minutter. Det eneste
   15-minutters tal (#2) gælder udvalgte enkeltaktier, er in-sample og er klart svagere end 5 minutter (Sharpe 1,43 mod
   2,81). 30 og 60 minutter er svage (Sharpe 0,21 og 0,40).
2. **Ingen out-of-sample- eller fremad-evidens for en nettogevinst.** #1 og #2 er in-sample-backtests. Den eneste
   uafhængige replikation med omkostninger (#3) finder netto ≈ 0 på NQ (+0,002R) og negativt på de fire andre indeks.
3. **Ingen kilde med realistiske omkostninger for NQ-futures.** #1 sætter slippage til 0. #3 bruger CFD-omkostninger
   (2,5 point på NQ). En NQ-future koster formentlig mindre (arbejdsantagelse i venue-matrixen: ca. 0,7-1,0 point pr.
   rundtur inkl. 1 tick slippage pr. side; børsgebyret er UNVERIFIED). Det er et argument for at teste, ikke evidens
   for en fordel. Og det gælder 5 minutter, ikke 15.
4. **Overskrifternes store afkast kommer fra gearing** (4x og TQQQ), ikke fra en større fordel pr. handel.
5. **Påstanden "the real moneymaker" har ingen støtte.** Én handel i en video er ingen evidens.
6. **Interessekonflikter:** de to mest citerede ORB-papirer har en medforfatter, der driver en tradinguddannelse
   (Bear Bull Traders) og et prop-firma (Peak Capital Trading). Begge er working papers uden peer review.

### Konsekvens for designet

- Nulhypotesen bør være "netto = 0", ikke "ORB virker". Evidensen peger på en brutto-fordel af samme størrelse som
  omkostningerne.
- 15 minutter er det svageste punkt: litteraturen favoriserer 5 minutter. En test af ORB-15 tester videoens påstand,
  ikke den bedst dokumenterede variant. En 5-minutters ORB må kun med som en separat, forhåndsregistreret sammenligning.
- Omkostningerne afgør resultatet: på Binance' QQQUSDT (8-10 bp pr. rundtur) skal den gennemsnitlige risiko pr. handel
  være mindst ca. 62 bp, før en bruttofordel på 0,13R dækker gebyret (8 bp / 0,13). Det er ren regning, ingen data.

## 4. Kilder, der ikke kunne åbnes

| URL | Problem |
|---|---|
| https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4416622 | HTTP 403 (forfatter-PDF brugt i stedet) |
| http://www.econ.umu.se/DownloadAsset.action?contentId=196616&languageId=3&assetKey=ues845 | Certifikatfejl. Ingen omvej forsøgt |
| https://ieeexplore.ieee.org/document/8641124/ | Tom side (NTU-repositoriet brugt til abstractet) |
| https://www.bohrium.com/paper-details/… (Tsai m.fl.) | WAF-udfordring |
| https://www.cmegroup.com/… (NQ-specifikationer og gebyrnotits) | Timeout. Ingen omvej forsøgt |
