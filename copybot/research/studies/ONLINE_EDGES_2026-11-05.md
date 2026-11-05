# Online-scanning: kendte handelseffekter, der kan overleve realistiske omkostninger (2026-11-05, ca. 19:20 lokal)

**Kun litteratur og praksis. Ingen database, ingen data hentet, ingen lab-kode kørt.** Repoet er kun læst for at se,
hvad der allerede er testet: `research/HYPOTHESES.md`, `DIAGNOSE_HVORFOR_INTET_BESTAAR.md`, `NEXT_MECHANISMS.md`,
`NAESTE_IDEER_UDKAST.md`, `NAESTE_IDEER_RUNDE2_UDKAST.md`, `PROTOCOL_V3.md` (overskrifter og afsnit 5),
`RESULTS_pmcal_v1.md`, `studies/SCREENINGER_OVERSIGT_2026-10-25.md`, `studies/AFVISNINGER_2026-10-26.md` og
filnavnene under `research/studies/`. Alle forslag er papirsimulering. Ingen rigtige penge, ingen API-nøgler.

**Forbehold om kilderne:**
- Mange tal er læst i abstracts eller sekundære resuméer. Hvor jeg ikke selv har set tallet i den primære kilde, står der "(sekundær)".
- **Publikationsbias:** offentliggjorte effekter er i gennemsnit cirka en tredjedel mindre efter offentliggørelsen (McLean & Pontiff 2016, *JF*, doi 10.1111/jofi.12365). Effekter fra praktikere (børsblogs, leverandører) er ofte reklame.
- **Datagate:** før nogen ny ekstern GET skal PROTOCOL_V3 tjekkes for en værts- eller datagate (MEMORY: Data host gates). Det gælder også pm_lp's holdout-regler for Polymarket-værter.

## 0. Hvad lab'et allerede har dækket (bekræftet i repoet)

| Område | Status i repoet |
|---|---|
| Spot-perp funding carry | Testet flere gange: carry_v1 FAIL, lane-carry med 14-dages stop, M2-tærsklen 12,5 %/18,8 % p.a., HFC-1. 14 dages holdetid giver break-even 12,5 % p.a. (0,48 % rundtur × 365/14). |
| Momentum, lav uro, anti-lotteri, lav beta, tæt på toppen, månedsskifte, bedste timer | v2-katalog. 8 af 9 fejlede mod købe-og-holde i rally-valideringen. Månedsskifte var +5,0 % uden for træningsdata, men ikke signifikant. Bedste timer: 77 % brutto blev til −15 % netto. |
| tsmom_v1/v2 (ugentlig, BTC/ETH/SOL) | FAIL på styrke (n_req hundreder til over tusind uger). |
| OI-vækst, OI-bekræftet trend, top-tradere mod flokken, gearingscyklus, VRP-timing (DVOL), stablecoin-flow, BTC-volumenandel, taker-pres | v3-idéerne (afsnit 5). |
| Realrente, udvanding (SplyCur), MVRV | Runde 2. |
| explore0-screeninger | 4σ-bevægelse fortsættelse/vending, BTC-lead, squeeze, funding-crowd squeeze, spot-lead, makro-drift og opmærksomhed: alle SCREEN_FAIL. |
| Polymarket-kalibrering (pmcal_v1) | FAIL: favorit 0,80–0,95 eller longshot 0,05–0,20 ved 7 d / 1 d; validering −3,43 % pr. hændelse. |
| Polymarket maker-belønninger | pm_lp kører. |
| Listninger | H4/H5/H5F/H5X (funding), 17f spot_listing, 17g Coinbase, 17h/17i Upbit, 17j Monitoring Tag. Short af nye HL-listninger n = 23. |
| TradFi-perps | K1 (BTC fører SPY/QQQ, når markedet er lukket), K2 (weekendpræmie/funding), H27-A/A2/M (aktieperps uden for børstid), H27-B (PAXG/XAUT-perp mod XAU-perp). |
| Øvrigt | K3 (pres omkring fundingafregning), R3 (minutreaktion på makro), FOMC-integrationstest, C4 (volumen uden pris), straks-bog (følg/mod efter usædvanlige bevægelser). |

Det betyder, at de fleste "klassiske" effekter allerede er brugt. Nedenfor står de, som litteraturen siger noget om
netto, sorteret efter hvor troværdigt **netto-efter-omkostninger**-beviset er for lab'ets markeder. Hvor lab'et har
testet effekten, står det, og om kilden viser en væsentligt anderledes variant.

---

## 1. Lang-horisont basis-carry på BTC/ETH (og guld via PAXG-spot), holdt ≥ 90 dage uden 14-dages stop

- **Mekanisme:** Binance' fundingformel er F = P + clamp(0,01 % − P, ±0,05 %). Hver gang præmien P ligger inden for båndet, bliver funding præcis 0,01 %/8 t (10,95 % p.a.), som longs betaler til shorts. Gearingsefterspørgsel og begrænset arbitragekapital holder præmien positiv i gennemsnit.
- **Markeder:** Binance spot BTC/ETH (long) + USD-M-perp (short). Variant: PAXGUSDT spot long + XAUUSDT perp short.
- **Holdetid:** 3–12 måneder.
- **Rapporteret netto:**
  - Schmeling, Schrimpf & Todorov, "Crypto carry" (BIS WP 1087, 2023; *Management Science* 2025, doi 10.1287/mnsc.2024.05069): gennemsnitlig carry over 10 % p.a., op til 60 % p.a.; høj carry forudsiger krak. https://www.bis.org/publ/work1087.htm
  - He, Manela, Ross & von Wachter, "Fundamentals of Perpetual Futures" (arXiv 2212.06888, rev. 2024): en simpel arbitragestrategi giver Sharpe 1,92 for BTC med detailomkostninger (tidlig version; sekundær). Afvigelserne er mindsket, efterhånden som markedet er modnet. https://arxiv.org/abs/2212.06888
  - Nyere og vigtigere tegn på at det er aftaget:
    - BitMEX Q3 2025: Binance-middel 0,0057 %/8 t ≈ 6,2 % p.a., og BTC står på 0,01 %-ankeret ca. 31 % af tiden (sekundær via https://www.spark.money/tools/funding-rate-comparison).
    - K33 30.04.2026: 7-dages gennemsnitlig BTCUSDT-funding var negativ for første gang siden 09-2024.
    - Ethena sUSDe: 30-dages gennemsnit 4,74 % i midten af 10-2026 mod ca. 10,3 % siden start (sekundær).
    - BitMEX-blog (04-2026): "the crypto carry trade is dead"; XAUt spot-perp carry ca. 9,67 % annualiseret over 73 dage på BitMEX og 5,99 % på Hyperliquid. Reklame med kort vindue.
- **Omkostninger:** én rundtur på BTC/ETH med taker koster ca. 0,1 % spot + 0,05 % perp pr. side, i alt ca. 0,3–0,5 %. Over 90 dage svarer det til 1,2–2 % p.a.
  - Lab'ets break-even på 12,5 % p.a. kommer alene af 14-dages-horisonten. Ved 90 dage er break-even ca. 2 % p.a.
- **Evidens:** mekanikken er dokumenteret (børsens formel). Afkastniveauet er tidsvarierende og faldende. Realistisk forventning i dag: 4–7 % brutto, 2–5 % netto, altså **omkring den risikofri rente (T-bill ca. 4 %)**. Det er en yield, ikke en alfa.
- **Halerisiko:** marginkald på perp-benet under rally, depeg i PAXG og børsrisiko.
- **Data:** `fapi.binance.com /fapi/v1/fundingRate` (historik) og `/fapi/v1/premiumIndex`, spotbøger fra `data-api.binance.vision`. Begge værter bruges allerede. PAXG-spot: `PAXGUSDT` (findes i scratch-bøgerne).
- **Testet?** Delvist. Carry er testet, men kun med 14-dages stop, bredt møntunivers og høj-funding-udvælgelse. **Væsentligt anderledes variant:** kun BTC og ETH (dybe bøger), fast lang holdetid, ingen stop på funding − gebyrer, og afkastet måles mod T-bill.
- **Hypotese (falsificerbar):** "En papirkonto long BTC+ETH spot / short perp, åbnet én gang og holdt 180 dage, ender med funding − alle handelsomkostninger > 3-måneders T-bill-afkast i samme periode." Variansen er lav, så selv 180 dage giver brugbar styrke.

## 2. Trendfølge med volatilitetsstyring, ensemble af Donchian-kanaler på de ca. 20 mest likvide mønter (daglig)

- **Mekanisme:** langsom informationsspredning og flokadfærd giver tidsseriemomentum. I krypto er det den mest replikerede retningseffekt.
- **Markeder:** Binance spot eller USD-M-perps, top-20 efter volumen.
- **Holdetid:** dage til uger. Signal dagligt.
- **Rapporteret netto:**
  - Zarattini, Pagani & Barbon, "Catching Crypto Trends" (SFI RP 25-80, SSRN 5209907, 2025): net Sharpe > 1,5, ca. 18 % net CAGR og 10,8 % årlig alfa mod BTC ved 0,10 % pr. handel. Også testet ved 0,25 % og 0,50 %. 2015–03/2025. https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/ og https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/
  - Han, Kang & Ryu: tidsseriemomentum er stærkt i krypto, tværsnitsmomentum svagt (sekundær).
- **Evidens:**
  - Omkostninger er modelleret i Zarattini m.fl., men der er ingen ægte out-of-sample. Perioden er domineret af to tyremarkeder.
  - Trendfølge i traditionelle markeder har haft svage år efter offentliggørelse: SG Trend −1,45 % (2023), +2,6 % (2024), over −8 % i H1 2025 (https://www.alternativeswatch.com/2025/06/02/trend-following-hedge-funds-endure-more-pain-societe-generale-indices/).
  - Effekten er ægte i mange studier, men har lav Sharpe pr. uafhængig observation.
- **Data:** daglige klines fra `data.binance.vision` eller `fapi.binance.com/fapi/v1/klines`. Lab'et har dem allerede.
- **Testet?** Ja, tsmom_v1/v2 (ugentlig, 3 mønter) fejlede på styrke, og momentum-bogen fejlede mod købe-og-holde i rallyet. **Varianten er kun delvist anderledes:** flere lookbacks, vol-target og 20 mønter. Det mindsker støjen, men fjerner ikke den fælles markedsfaktor. Styrkeproblemet (diagnosens årsag 5) består.
- **Hypotese:** "Et forhåndsfrosset Donchian-ensemble (lookbacks 20/40/80/160 dage, vol-target 25 %, long/flat, top-20) giver efter 0,1 %+slip pr. handel en højere Sharpe end lige-vægtet købe-og-hold af samme univers over 24 måneders fremadrettet papirhandel." Det kan først afgøres om lang tid.

## 3. Favorit–longshot-bias i prediction markets (sælg longshots / køb favoritter)

- **Mekanisme:** handlende overvurderer små sandsynligheder ("lotterisedler"). Takers betaler for umiddelbarhed.
- **Markeder:** Polymarket. Kalshi som replikation (ikke handelbart fra DK).
- **Holdetid:** til afgørelse.
- **Rapporteret netto:**
  - Bürgi, Deng & Whelan, "Makers and Takers: The Economics of the Kalshi Prediction Market" (UCD/CESifo, 01-2026), https://www.karlwhelan.com/Papers/Kalshi.pdf:
    - Data: 46.282 kontrakter fra 12.403 begivenheder (2021–04/2025) og over 300.000 priser.
    - Kontrakter under 10c taber over 60 %. Kontrakter over 50c giver et lille, signifikant positivt afkast efter taker-gebyr 0,07·P(1−P).
    - Makers klarer sig bedre end takers, og biasen er aftagende over tid.
  - Cardozo & Rivero-Wildemauwe, arXiv 2609.12878 (09-2026), Polymarket med 588 mio. handler, https://arxiv.org/abs/2609.12878:
    - Køb under 10c taber 19,3c pr. dollar; køb ≥ 90c tjener 0,83c pr. dollar **brutto**.
    - Når kontrakter grupperes pr. begivenhed, vender longshot-resultatet til +4,1c.
    - Mønstret er fraværende i sport.
  - Le, arXiv 2602.19520 (2026): politiske markeder er "underconfident", dvs. priserne ligger for tæt på 50 %. Ca. halvdelen af variationen er estimationsstøj.
  - Imod: Reichenbach & Walther (SSRN 2026, i `NEXT_MECHANISMS.md`) finder ingen generel longshot-bias på Polymarket.
- **Netto:** ved 0,90 giver 0,83c brutto minus ca. 0,5c halv spread og ca. 0,36c taker-gebyr (sats 0,04) cirka 0. **For en taker overlever favoritsiden altså næppe omkostningerne.** Kun maker-siden har et dokumenteret netto-plus (Kalshi).
- **Testet?** Ja: pmcal_v1 FAIL (−3,43 %). Kilderne viser ingen væsentligt anderledes taker-variant. Den eneste ægte forskel er maker-varianten, og den kan ikke backtestes ærligt (lab'ets egen regel). Den dækkes af pm_lp.
- **Hypotese (kun hvis man vil prøve "politik-underconfidence"):** "Politiske Polymarket-kontrakter købt som taker ved 0,60–0,85, én pr. begivenhed, 3 dage før planlagt afslutning, har et netto-gennemsnit > 0 på eksekverbare forward-priser." Lav prior.

## 4. Polymarket-rebalancerings- og negRisk-arbitrage (summen af alle udfalds asks < 1)

- **Mekanisme:** i begivenheder med flere udfald skal summen af YES-priserne være 1. Fragmenteret likviditet giver korte huller.
- **Holdetid:** til afgørelse. Risikofrit, hvis alle ben fyldes.
- **Rapporteret netto:**
  - Saguillo, Ghafouri, Kiffer & Suarez-Tangil, "Unravelling the Probabilistic Forest: Arbitrage in Prediction Markets" (arXiv 2508.03474, 08-2025), https://arxiv.org/abs/2508.03474:
    - Data: 04/2024–04/2025, 8.659 enkeltmarkeder og 1.578 negRisk-markeder.
    - Arbitrage blev fundet i 662 af 1.578 negRisk-markeder. Ca. 40 mio. USD blev realiseret.
    - De fleste muligheder giver lille afkast pr. dollar.
  - Praktikerkilder siger, at hullerne nu lukker på sekunder, og at nogle huller er visningsforsinkelse. negRisk-adapteren tillader kun konvertering i én retning før afgørelsen (sekundær; https://tigerpolymarketprediction.substack.com/p/weekly-algorithm-executable-vs-payoff).
- **Evidens:**
  - Mekanisk og veldokumenteret historisk.
  - Konkurrencen er hård (mange bots), og papirfyld er optimistisk, fordi alle ben skal fyldes samtidig.
  - Gebyrer: taker-sats × p(1−p) pr. ben.
- **Data:** `gamma-api.polymarket.com` (begivenheder med negRisk-flag) og `clob.polymarket.com /book` eller `/books`. **pm_lp's holdout-regler og datagaten skal tjekkes først.** Indsamlingen må ikke forstyrre pm_lp-indsamleren.
- **Testet?** Nej. arb_v1 var SOL/USDC-puljer.
- **Hypotese:** "Mindst 20 negRisk-begivenheder pr. uge har en sum af bedste asks inkl. taker-gebyr ≤ 0,99 med ≥ 100 USD dybde på hvert ben i to bogsnapshots 60 s fra hinanden. Den simulerede netto-P&L pr. sådan mulighed er > 0 på 8 ugers forward-data." Udfaldet er først og fremmest en måling af hyppighed og varighed.

## 5. Tværsnits-carry kun på perps (short perps med høj funding, beta-hedget med BTC/ETH-perp)

- **Mekanisme:** som FX-carry. Crowdede longs betaler funding, og den betaling er en risikopræmie.
- **Rapporteret netto:**
  - "The Risk and Return of Cryptocurrency Carry Trade" (Lu m.fl., seminarabstract 2024): ca. 43,4 % p.a., Sharpe 0,74, og en stor del forklares af aktie-VRP. **Ikke selv verificeret. Strategiens fortegn (høj- eller lav-funding long) er tvetydigt beskrevet.** https://dtf.zuel.edu.cn/szjsyxdjr-szjs_tzyg/szjsyxdjr_cont_news/details-40034.html
  - En sekundær omtale af et arXiv-papir fra 2025 siger, at carry-Sharpe er faldet fra 6,45 til 4,06 (fra 2024) og blev negativ i 2025. Ikke verificeret.
- **Hvorfor relevant:** det løser lab'ets flaskehals ("96 % af afvisningerne er mønter uden spotpar"), fordi intet spotben er nødvendigt.
- **Imod:** lab'ets m21h (funding_crowd squeeze, 24 t) fandt 2,2 bp (se 49 bp). Prisen bevæger sig altså ikke systematisk efter høj funding, men variansen er enorm. Funding på 12,5–50 % p.a. over 3 dage er 0,1–0,4 %, mod en rundtur på ca. 0,2–0,3 % pr. ben × 2 ben.
- **Data:** census/1 (lab'ets egen timecensus) og `fapi /fundingRate`.
- **Testet?** Kun som 24-timers prisreaktion (m21h), ikke som carry-portefølje. Varianten er væsentligt anderledes, men evidensen er tynd.
- **Hypotese:** "Ugentligt ombalanceret short af top-10 72 t-funding-perps (≥ 18,8 % p.a.), hedget med BTC-perp efter 30-dages beta, giver funding + pris − omkostninger > 0 over 12 uger fremad."

## 6. Kursfald omkring store, planlagte token-unlocks

- **Mekanisme:** modtagere (team og investorer) sælger, og markedet foregriber det.
- **Rapporteret effekt:**
  - Keyrock, "From Locked to Liquidity: What 16,000+ Token Unlocks Teach Us" (12-2024), https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/: ca. 90 % af unlocks er forbundet med negativt prispres. Faldet starter ca. 30 dage før og stabiliserer sig ca. 14 dage efter. Team-unlocks giver op til −25 %, og store unlocks er 2,4× værre (sekundær).
  - Guo 2026 (SSRN, dilution, i repoet): long/short 25–32 % p.a.
- **Evidens:** praktikerstudie uden omkostninger, uden out-of-sample og uden kontrol for markedet. Overlevelsesbias er sandsynlig. Short via perp koster også funding.
- **Data:** et unlock-kalender-API (Tokenomist er betalt; DefiLlama-emissions muligvis gratis). **Ny vært, så det kræver en datagate-ændring.** Pris fra fapi.
- **Testet?** Nej. "Udvanding" (SplyCur, månedlig tværsnit) er en anden mekanisme, og C (unlock-præmie) blev afvist på datamangel.
- **Hypotese:** "For planlagte cliff-unlocks ≥ 2 % af cirkulerende mængde på mønter med Binance-perp giver short fra T−7 til T+7 dage, BTC-hedget, et netto-afkast inkl. funding < 0 for long (dvs. > 0 for short) over ≥ 60 hændelser fremad."

## 7. Order-imbalance ved åbningen af kvarter/timer forudsiger 4–12 timers afkast på Binance-perps

- **Mekanisme:** periodisk algoritmehandel ved klokkeslæt (1, 5 og 15 min). Ubalancen ved åbningen bærer information eller lagerpres.
- **Kilde:** Kim & Hansen, "The Quarter-Hour Effect" (arXiv 2607.09426, 07-2026), seks Binance-perps på handelsniveau: "Opening returns are predictable out of sample." Effekten gælder over ca. 4–12 timer. https://arxiv.org/abs/2607.09426
  - Beslægtet: "Bitcoin intraday time-series momentum" (Reading, 2021): første halve time forudsiger sidste, også out-of-sample. Ingen omkostninger.
- **Evidens:** nyt, ikke replikeret. Ingen omkostninger og ingen effektstørrelse i bp i abstractet. Ved 4–12 timers hold skal effekten være ≥ ca. 15–25 bp pr. handel.
- **Data:** aggTrades fra `data.binance.vision` (store filer) eller fremadrettet `aggTrade`-stream.
- **Testet?** Nej. Lab'ets "taker-pres" var daglig/ugentlig, og L20 var minut-OFI på BTC.
- **Hypotese:** "Fortegnet af taker-ubalancen i de første 5 min af hver UTC-time på BTC/ETH-perp forudsiger afkastet over de næste 4 t med et gennemsnit > 15 bp i signalets retning over 8 uger fremad."

## 8. Weekendpriser på aktie-/TradFi-perps forudsiger mandagens åbning

- **Kilder:**
  - Tiger Research: retningen ramte 87–93 % (Samsung, SK Hynix).
  - CoinDesk: 89 %.
  - Blockworks (23 HIP-3-markeder, 146 weekender): pre-open-mid lå kun tættere på mandagens åbning end fredagens lukkekurs i 50,7 % af tilfældene, med en median forbedring på 0,4 bp.
  - Crypto.com: short af tech-aktier på negative weekendsignaler tabte penge.
  - Links: https://messari.io/report/weekend-trading-evidence-of-price-discovery-in-hyperliquid-s-weekend-markets og https://blockworks-research.beehiiv.com/p/when-markets-sleep
- **Vurdering:** informationen er allerede **i perpens pris**. Det er prisopdagelse, ikke en handelbar fordel, medmindre perpen halter efter noget andet (lab'ets K1).
- **Testet?** Ja, dækket af K1, K2 og H27-A/A2/M. Ingen ny variant at foreslå.

## 9. Intradag-momentum i SPY ("Noise Area")

- **Kilde:** Zarattini, Aziz & Barbon, "Beat the Market" (SFI WP 24-97, 2024): 19,6 % p.a. netto og Sharpe 1,33 (2007–2024) med ETF-kommission og slippage. https://concretumgroup.com/beat-the-market-an-effective-intraday-momentum-strategy-for-sp500-etf-spy/ Original: Gao, Han, Li & Zhou 2018 (*JFE*).
- **Overførbarhed:** på Binance' SPY/QQQ-perp koster en daglig rundtur ca. 10 bp taker (mod ca. 1 bp i ETF'en). Strategiens netto er ca. 8 bp pr. handelsdag, så **den overlever ikke perp-taker-omkostninger**.
- **Testet?** Nej, men den falder på omkostningerne alene.

## 10. Guld stiger i asiatiske timer og falder i amerikanske

- **Kilder:**
  - WGC H1 2026 (sekundær): guld +12,9 % i asiatiske timer.
  - CBS-speciale (2019): Sharpe op til 1,61 før omkostninger, som skrumper efter omkostninger. https://research.cbs.dk/en/studentProjects/gold-price-dynamics-around-the-clock/
- **Vurdering:** sandsynligvis regimeafhængigt (asiatisk efterspørgsel i 2025–26). En daglig rundtur på XAUUSDT koster ca. 10 bp, altså ca. 25 % p.a. ved daglig handel. XAUUSDT-perpen har kun eksisteret siden 08.01.2026.
- **Testet?** Nej. Lav prior.

## 11. Månedsskifte i aktieindeks (SPY/QQQ-perp)

- **Kilder:** Atlanta Fed fandt effekten forsvundet i S&P-futures efter 1990. I ETF-æraen er den flyttet til første handelsdag (FPA-artikel). Ingen solid 2020–25-test fundet. https://www.financialplanningassociation.org/article/journal/APR11-turn-month-anomaly-age-etfs-reexamination-return-enhancement-strategies
- **Testet?** Lab'et testede månedsskifte i krypto: +5,0 % uden for træningsdata, ikke signifikant. Kun 12 hændelser om året giver samme styrkeproblem. Lav prior.

## 12. Overnight-drift i S&P-futures (02–03 ET)

- **Kilde:** Boyarchenko, Larsen & Whelan, "The Overnight Drift" (NY Fed SR 917; *RFS* 2023): 3,7 % p.a. (1,48 bp/dag) i 1998–2018.
- **Status:** forfatternes egen opfølgning "The Disappearing Overnight Drift" (Liberty Street, 07-2026) siger, at effekten har ligget tæt på 0 siden 2021. https://libertystreeteconomics.newyorkfed.org/2021/05/the-overnight-drift-in-us-equity-returns
- **Vurdering:** støj nu, og 1,5 bp er langt under en perp-rundtur på 10 bp.

## 13. Pre-FOMC-drift

- **Kilde:** Lucca & Moench 2015. Kurov, Wolfe & Gilbert (*FRL* 2021) viser, at den er forsvundet efter 2015. https://ideas.repec.org/a/eee/finlet/v40y2021ics1544612320315956.html
- **Status:** lab'ets FOMC er kun integrationstest. Støj. Skal ikke foreslås.

## 14. Polymarket 5/15-minutters krypto-markeder: latens mod Binance

- **Kilde:** Young, "OpenMarket" (arXiv 2607.26245, 07-2026), 727 mio. rækker, 02–05/2026:
  - En walk-forward-model med 43 mikrostrukturfeatures slår ikke bogens egen sandsynlighed out-of-sample.
  - Simuleret netto er **−0,116 payoff-enheder pr. forsøgt handel**.
  - Polymarket-quotes reagerer efter en median på 347 ms.
- **Polymarkets modtræk:** taker-gebyrer siden 01-2026 og TWAP-afregning fra 07.08.2026. https://arxiv.org/abs/2607.26245
- **Status:** støj, og et hastighedsløb.

## 15. Bitcoin time-på-døgnet og ugedag

- **Kilder:** Quantpedia (21–23 UTC, 37 % p.a., uden omkostninger). Baur m.fl. (*FRL* 2019): anomalierne holder ikke over tid.
- **Status:** lab'ets "bedste timer" gik fra 77 % brutto til −15 % netto. Støj.

---

## Samlet, ærlig vurdering

**Ingen offentliggjort kilde viser en retail-taker-strategi på disse markeder med robust out-of-sample netto-alfa efter
2023.** Mønstret i litteraturen er klart:
- **De effekter, der har fortsat, er strukturelle præmier med lav alfa.** Carry, trend og maker-siden i prediction markets er "betaling for en ydelse" (likviditet, gearing, risikobæring) og er blevet mindre, efterhånden som kapital er kommet til.
- **Rene prismønstre er forsvundet efter offentliggørelse eller drukner i perp-taker-omkostninger på 10 bp pr. rundtur.** Eksempler: overnight-drift, pre-FOMC, døgn- og ugedagsmønstre, intradag-momentum på perps.

**De tre, der er mest værd at teste på papir med forhåndsregistrering (i denne rækkefølge):**
1. **Lang-horisont BTC/ETH basis-carry mod T-bill (#1).** Mekanikken er dokumenteret, den har lav varians og dermed god styrke på 3–6 måneder, og den er væsentligt anderledes end lab'ets 14-dages carry. Forventningen er beskeden: netto omkring T-bill-renten. Et ja/nej her afklarer, om "carry er død", for lab'et. PAXG/XAU-varianten kan køre ved siden af som sekundær.
2. **negRisk-/rebalanceringsarbitrage på Polymarket som forward-måling (#4).** Den er mekanisk, har mange uafhængige hændelser og ingen markedsfaktor. Den kræver pm_lp-sikker indsamling og en datagate-ændring. Forvent at de fleste huller er for korte eller for tynde.
3. **Trend-ensemble med vol-target på top-20 (#2).** Den har det bedst replikerede retningsbevis i krypto. Fordi styrkeproblemet består, skal den forhåndsregistreres som en 24-måneders fremadrettet papirbog, ikke som en hurtig afgørelse.

Hvis lab'et hellere vil have noget nyt med kortere horisont, er **#7 (åbnings-ubalance → 4–12 t)** det mest interessante
nye akademiske fund. Effektstørrelsen er dog ukendt og muligvis under omkostningerne.

**Populære påstande, der ligner støj eller reklame:**
- overnight-drift og pre-FOMC-drift (forsvundet ifølge forfatterne selv eller opfølgere);
- BTC-time/ugedag;
- Polymarket-latensarbitrage i 5/15-min-markeder (null-resultat);
- "TradFi-perps yielder 361,6 %" (BitMEX-reklame, annualiseret fra et kort vindue);
- "89–93 % træfsikkerhed for mandagens åbning" (allerede i prisen; Blockworks: 50,7 %);
- "favoritter ved 0,90+ er gratis penge" (0,83c brutto bliver ca. 0 netto for takers; pmcal FAIL);
- "90 % af unlocks falder" (ingen omkostninger og ingen kontrol, men værd at måle);
- copy-trading af "smart money"-wallets (lab'ets tre fejl; Hyperliquid-wallet-afkast er ikke det, en følger får);
- CME-gap, "max pain" og likvidations-heatmaps. Jeg fandt ingen troværdig netto-evidens for nogen af dem.

**Kilder (ud over dem i teksten):**
- Saguillo m.fl. 2025: https://arxiv.org/abs/2508.03474
- Le 2026: https://arxiv.org/abs/2602.19520
- Zarattini m.fl. (krypto): https://abarbon.com/papers/catching-crypto-trends
- Kurov m.fl.: https://www.skidmore.edu/economics/documents/KurovWolfeGilbert-TheDisappearingPre-FOMC-Announce-Drift-200914.pdf
- Quantpedia BTC: https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/
- BitMEX carry-blog: https://www.bitmex.com/blog/crypto-carry-trade-death
- RockawayX listninger: https://rockawayx.com/insights/bullish-or-bearish-what-really-happens-when-tokens-list-on-a-cex
- Polymarket taker-gebyrer: https://www.theblock.co/post/384461/polymarket-adds-taker-fees-to-15-minute-crypto-markets-to-fund-liquidity-rebates
- Binance XAU/XAG-fundingændring: https://www.theblock.co/news/markets/2026-01-08-binance-gold-silver-perpetual-contracts-usdt-settled-384743
