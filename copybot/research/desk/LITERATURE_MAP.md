# Litteraturkort: dokumenteret forudsigelighed og markedsstruktur i krypto (direktørordre 50 P0, 2026-11-06)

**Kun litteratur.** Ingen markedsdata, ingen børs-API, ingen kurser, klines eller funding er hentet. Alle kilder er åbnet i
denne session (abstractside eller PDF), og URL'en står i `evidence_registry.json` (felt `url_opened`). Tal er kun
gengivet, når de står i den åbnede tekst. Ellers står der UNKNOWN. Resuméerne er mine egne ord.
**Effekt er ikke handelsfordel.** En statistisk effekt eller en bedre prognose er ikke det samme som et dokumenteret
nettoafkast efter omkostninger. Registret skelner mellem `result_type` forecast, net_trading, descriptive og theory.

## Optælling

| | Antal |
|---|---|
| Verificerede kilder i alt | **44** |
| Kategori 1 funding / 2 basis / 3 momentum / 4 reversal / 5 mikrostruktur | 6 / 4 / 7 / 3 / 3 |
| Kategori 6 listning og overlevelse / 7 on-chain / 8 optioner / 9 tværbørs / 10 volatilitet | 4 / 3 / 3 / 6 / 5 |
| Fagfællebedømt tidsskrift | 18 |
| Working paper (SSRN/arXiv/BIS/NBER/universitet, konferenceabstract) | 21 |
| Afhandling (ph.d./thesis) | 2 |
| Praktiker/blog (kun påstande) | 3 |
| result_type: descriptive / forecast / net_trading / theory | 28 / 11 / 4 / 1 |
| Dataadgang: AVAILABLE_FORWARD / AFTER_11-14 / BLOCKED_TIL_11-28 / NOT_AVAILABLE / UNKNOWN | 20 / 14 / 1 / 7 / 2 |

Kun fire kilder rapporterer noget, der ligner nettohandel efter omkostninger: E03 (perp-afvigelser med gebyrtrin), E01
(anomalier under økonomiske begrænsninger, mest negativt), E42 og E43 (praktikere, kun påstande). **Ingen fagfællebedømt
kilde i registret dokumenterer en nettofordel efter omkostninger i perioden efter 2022 for et likvidt univers.**

Henvisninger til lab'et: tags fra `research/families/VOCABULARY.json`, filnavne relative til `research/`.

---

## 1. Perpetual funding og funding-persistens (E05, E07, E08, E40, E41, E42)

- **Dokumenteret:** short perp mod long spot i samme mønt har historisk tjent store, stabile fundingbetalinger.
  - E05 (Christin m.fl., CMU WP 2022): Sharpe 7–10 i sample på Binance. Bruttotal: omkostninger, margin og gearing er
    udeladt. USDT-afregnede kontrakter gav mere end coin-afregnede.
  - E08 (Borri, Liu, Tsyvinski & Wu, arXiv 2025/26): carry efter Schmeling m.fl. havde Sharpe 6,45 i 2020–2025 og 4,06 fra
    2024, og den blev negativ i 2025. Funding gav i gennemsnit ca. 8 % om året ved 0,8 % volatilitet.
  - Funding-persistens: E40 (Inan, ph.d. 2026) viser, at BTC-funding kan forudsiges uden for sample. Graden varierer over
    tid og mellem børser. Det er en prognose for pengestrømmen, ikke for kursen.
- **Funding som retningssignal er svagt.** E41 (Presto, praktiker) finder prædiktiv R² ≈ 0 for BTC. E42 (praktiker)
  finder rang-IC −0,005 (t −0,89) mellem funding og 7-dages afkast.
- **Evidensstyrke:** ingen fagfællebedømte artikler. Kun working papers, en afhandling og praktikere. E07 (Ackerer,
  Hugonnier & Jermann) er teori.
- **Omkostninger og kapacitet:** Sharpe-tallene er pustet op af fundingens lave volatilitet. Basisrisiko, likvidation og
  stablecoin-depeg indgår ikke (E42 nævner det selv). Niveauet er faldet kraftigt efter 2024 (E08, E42).
- **Copybot:** `delta_neutral_funding_carry` (F1 fcarry, `families/fcarry.json`), `funding_carry`, `funding_carry_leverage`.
  - `RESULTS_carry_v1.md` FAIL: fordelen faldt under omkostningerne. Det stemmer med E08 og E42.
  - HFC-1 (`studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md`) og `studies/CARRY_ECON_DAILY_2026-11-04.md` måler
    persistensen fremad.
  - `funding_crowding_contrarian`: `studies/FUNDING_m21h.md` gav SCREEN_FAIL (+0,02 % pr. døgn). Det stemmer med E41/E42.
  - Fundingregimer: `families/drafts/fregime.json`, `drafts/F3_FUNDING_DYNAMISK_UDKAST.md`.
- **Data:** AVAILABLE_FORWARD for USDT-M funding og spot. Historisk først efter 2026-11-14. Coin-afregnede kontrakter (E05's
  andet ben) er COIN-M og BLOCKED_UNTIL_2026-11-28.

## 2. Spot/perp-basis og terminsstruktur (E02, E03, E04, E06)

- **Dokumenteret:**
  - E04 (BIS WP 1087): carry op til 60 % p.a., i gennemsnit over 10 % om året. Den svinger stærkt over tid og forklares
    med convenience yield: småinvestorer jagter trend, og arbitragekapital er knap. Høj carry går forud for crash.
    Bruttoniveau, ikke et handelsresultat.
  - E03 (He, Manela, Ross & von Wachter): perp-afvigelser fra no-arbitrage-grænsen var i gennemsnit 60–90 % p.a. i
    absolut værdi. Konvergenshandlen gav Sharpe 1,8 med høje detail-gebyrer og op til 3,5 uden gebyrer (BTC). |afvigelse|
    falder ca. 11 % om året (2020-01 til 2024-03). **Den stærkeste omkostningsjusterede kilde**, men den er ikke
    fagfællebedømt, og effekten aftager.
  - E06 (Gornall m.fl., foreløbig): perps reducerer ekstreme dislokationer og arbitragens drawdowns sammenlignet med
    kvartalsfutures.
  - E02 (Luo, Edinburgh-afhandling 2025): 170 prædiktorer, 63 signifikante, alle forklaret af log-basis og pris-volumen.
- **Evidensstyrke:** moderat (BIS, NBER-forfattere, AEA), men ingen fagfællebedømt version er åbnet. Management
  Science-versionen af E04 kunne ikke åbnes (403).
- **Omkostninger og kapacitet:** marginspidser og likvidationer gør cash-and-carry risikabel (E04). Kapacitet er ikke
  kvantificeret nogen steder.
- **Copybot:**
  - `dated_futures_basis_carry`: F2 dbasis i `families/drafts/dbasis.json` og `F2_PLAN.md`, og `../lab/carry90.py` (carry90
    BTC/ETH).
  - `perp_premium_convergence`: `studies/PREMIUM_BANER_REKONSTRUKTION_2026-10-25.md` viste, at bogdybden spiste
    præmiebanerne.
  - `studies/SPOTPERP_m21i.md`.
  - NEXT_MECHANISMS række J (Cao m.fl., 170 prædiktorer) blev afvist for overlap med carry og momentum. Det bekræftes af E02.
- **Data:** perp og spot USDT-M er AVAILABLE_FORWARD. Daterede USD-M-kontrakter har samme status. Coin-margined daterede
  kontrakter er BLOCKED_UNTIL_2026-11-28.

## 3. Momentum og trend (E01, E09, E10, E11, E12, E13, E43)

- **Dokumenteret, men omstridt:**
  - For effekten: E09 (Liu & Tsyvinski, RFS) finder stærk tidsserie-momentum, og opmærksomhedsproxyer forudsiger afkast.
    E10 (Liu, Tsyvinski & Wu, JF) finder tre faktorer: marked, størrelse og momentum.
  - Imod: E11 (Grobys & Sapkota, EL; 143 mønter, 2014–18) finder ingen signifikant momentum. E22 (Ammann m.fl.) finder,
    at momentumpræmien forsvinder, når overlevelsesbias korrigeres.
  - E01 (Fieberg, Liedtke & Zaremba, IRFA 2024): momentum overlever i større mønter, men omkostningerne er betydelige,
    alfa kommer mest fra short-siden, og effekten ligger i tyremarkeder og aftager.
  - E12 (Gbadebo 2026; 8 mønter, 2020–25): TSMOM 31,96 % om året. Omkostninger er ikke oplyst.
  - E13 (arXiv): momentum er stærkest i de mest likvide mønter.
  - E43 (Man Group, praktiker): trend med volatilitetsstyring og omkostninger. Ingen tal. Parvis korrelation ≈ 0,6.
- **Evidensstyrke:** stærk som statistisk regularitet i tidlige data (RFS og JF). Svag som nettofordel efter 2022.
- **Copybot:** `time_series_momentum`, `cross_sectional_momentum`, `trend_following`, `time_series_momentum_diversified`.
  - `RESULTS_tsmom_v1.md` FAIL (styrke og G2). `TSMOM_V2_PROPOSAL.md` blev stoppet.
  - `studies/DONCHIAN_POWER_P1_2026-11-06.md`: INSUFFICIENT POWER. 20 mønter med ρ 0,65 svarer til ca. 1,5 uafhængige,
    hvilket stemmer med E43's korrelation.
  - Straks-FØLG i `../lab/straks.py`.
- **Data:** daglige spot- og perp-kurser er AVAILABLE_AFTER_2026-11-14 historisk og AVAILABLE_FORWARD fremad.

## 4. Kortsigtet reversal og likviditetschok (E14, E15, E16)

- **Dokumenteret:** opdelt efter horisont og likviditet.
  - E14 (Zaremba m.fl., IRFA 2021; mere end 3.600 mønter): reversal fra dag til dag skyldes illikviditet. De største
    mønter viser i stedet daglig momentum.
  - E15 (Fičura WP 2023): ugentlig reversal i små og illikvide mønter (t −7,31) og ugentlig momentum i store og likvide
    (t 2,33). Kun t-værdier, ingen afkaststørrelse.
  - E16 (Lim, JFDA 2026): efter likvidationskaskaden 10-10-2025 på Hyperliquid normaliseredes spreads hurtigt (median
    9,4 bp på toppen). Dybden lå efter 23 dage stadig på 66–79 %. Kursreversal efter kaskaden er **ikke** dokumenteret.
- **Omkostninger og kapacitet:** effekten sidder i de illikvide mønter og har derfor lav kapacitet og høje omkostninger.
  Ingen kilde viser en nettofordel.
- **Copybot:** `short_term_reversal_liquidity`, `liquidation_cascade_reversal`, `illiquidity_premium`.
  - `studies/MOVESCREEN_m21c.md` gav SCREEN_FAIL.
  - Straks-MOD i `../lab/straks.py` og parbogen i `../lab/pairs.py` (spread-reversion).
  - Lab'ets univers af likvide USDT-perps ligger på momentumsiden af opdelingen.
- **Data:** AVAILABLE_AFTER_2026-11-14 (historisk). Hændelser fremad: AVAILABLE_FORWARD.

## 5. Ordreflow, spread og mikrostruktur (E17, E18, E19; se også E23)

- **Dokumenteret:**
  - E17 (Brauneis m.fl., JBF 2021): Corwin-Schultz og Abdi-Ranaldo følger likviditetens udvikling over tid bedst. Amihud
    og Kyle-Obizhaeva rangerer niveauer og børser bedst.
  - E18 (Easley, O'Hara m.fl., SSRN 2024): Roll og VPIN forudsiger dynamik, der er relevant for market making og
    volatilitet. Det er en prognose, ikke P&L.
  - E19 (Kim & Hansen, arXiv 07-2026): ordreubalance ved kvartersåbninger på 6 Binance-perps forudsiger 4–12 timers
    afkast uden for sample. Størrelse og omkostninger er UNKNOWN. Den er meget ny og ikke replikeret.
- **Evidensstyrke:** en stærk målemetode (E17). Prognoseeffekterne er nye working papers.
- **Copybot:** `orderflow_imbalance`, `intraday_seasonality`, `maker_adverse_selection_measurement`.
  - `studies/H_SPR1_INSTRUMENT_SPREAD_2026-11-03.md`, `studies/H_SPR2_TICK_SPREAD_2026-11-04.md` og `studies/COSTS_2026-10-24.md`.
  - K3 ved afregningen: `drafts/K3_INDSAMLING_UDKAST_2026-10-25.md`.
  - E19 står allerede i `studies/ONLINE_EDGES_2026-11-05.md` afsnit 7.
- **Data:** AVAILABLE_FORWARD for bøger og snapshots. E19 kræver handler på trade-niveau. Det er ikke bekræftet, at
  collectoren gemmer dem (UNKNOWN).

## 6. Listning, afnotering og overlevelse (E20, E21, E22, E23)

- **Dokumenteret:**
  - E20 (Ante, BRL WP 2019; 327 listninger på 22 børser): unormalt afkast på 5,7 % på dagen og 9,2 % i vinduet [−3,+3].
    Nogle børser var negative.
  - E21 (Li m.fl., AFT 2025): positivt kortsigtet afkast, størst på Coinbase. Tokens, som Binance selv har investeret i, har
    svagere fundamentals. Tallene 32,8 %/22,7 % er kun set i et søgeuddrag og er **ikke** verificeret.
  - E22 (Ammann m.fl., WP 2022; 3.904 mønter): overlevelsesbias på 0,93 % p.a. værdivægtet og 62,19 % p.a. ligevægtet.
  - E23 (Cong m.fl., Management Science 2023): over 70 % af den rapporterede volumen på uregulerede børser er wash trading.
- **Omkostninger:** listningseffekten er et kapløb om hastighed. Den blev afvist som kandidat i `NEXT_MECHANISMS.md`
  række H. Data er fra før 2020.
- **Copybot:** `short_new_listings`, `memecoin_launch_selection`.
  - Lab'et måler funding på listninger, ikke afkast: `drafts/H4_NOTERING_FUNDING.md`, `drafts/H5_NOTERING_LAV.md`,
    `drafts/H5F_NOTERING_FREMAD.md` og `drafts/M1F_MONITORING_FREMAD.md`.
  - Overlevelse: punkt-i-tid-universet i `studies/FACTORY_SECURITY_P1_2026-11-06.md`. Carry v0 blev erklæret ugyldig pga.
    overlevelsesbias (`NEXT_CANDIDATES.md` #7–8).
- **Data:** listninger fremad er AVAILABLE_FORWARD. Historiske universer AVAILABLE_AFTER_2026-11-14, med status
  RECONSTRUCTED. Wash-trading-data fra mange børser er NOT_AVAILABLE.

## 7. On-chain-strømme (E24, E25, E26)

- **Dokumenteret:**
  - E25 (Hoang & Baur, JBF 2022): ændringer i børsreserverne hænger negativt sammen med nuværende og fremtidige BTC-afkast.
  - E24 (Chi, Chu & Hao, arXiv): USDT-indstrømning forudsiger positivt BTC- og ETH-afkast på 1–6 timer.
    ETH-indstrømning forudsiger negativt. BTC-indstrømning forudsiger stort set intet.
  - E26 (Griffin & Shams, JF 2020): Tether-køb støttede BTC i 2017. Episodespecifikt.
- **Evidensstyrke:** to tidsskrifter, men ingen nettohandel. Abstracts angiver ingen størrelser.
- **Copybot:** `stablecoin_liquidity_flow`, `onchain_value_mvrv` og `smart_money_following`.
  `drafts/ONCHAIN_KILDEAUDIT_2026-10-24.md` er kun en kildeaudit. `NEXT_MECHANISMS.md` række G afviste Tether-mekanismen.
- **Data:** NOT_AVAILABLE. Kræver betalte vendor-data som CryptoQuant eller Glassnode, eller egen node og
  adresseklassificering.

## 8. Optioner: implicit volatilitet, skew og VRP (E27, E28, E29; se også E44)

- **Dokumenteret:**
  - E27 (Almeida m.fl., arXiv): BTC's VRP er højere end S&P 500's. To volatilitetsregimer, hvor BVRP er høj i
    lavvolatilitetsregimet.
  - E28 (Alexander m.fl., arXiv): OTM-optioner på Deribit bærer retningsinformation.
  - E29 (Chi & Hao, arXiv 2020): GARCH slår de simple modeller, og en delta-hedget optionshandel siges at give "robust
    profit", men uden tal.
  - E44: optionsmarkedets lave likviditet kan forvrænge IV.
- **Evidensstyrke:** svag til moderat. Kun working papers er verificeret. Alexander & Imeraj (Bitcoin VIX, JAI 2021) kunne
  ikke åbnes og står under "Ikke-verificerede spor". Ingen kilde giver en VRP-størrelse efter omkostninger.
- **Copybot:** `variance_risk_premium_timing`. `NEXT_MECHANISMS.md` række B blev afvist (salg af BTC/ETH-optioner).
- **Data:** NOT_AVAILABLE. Deribit og andre optionsdata ligger uden for de nuværende værtsgates.

## 9. Prisdannelse og fragmentering på tværs af børser, inkl. kimchi (E30–E35)

- **Dokumenteret:**
  - E30 (Makarov & Schoar, JFE 2020): store, tilbagevendende prisgab, som er større mellem lande end inden for et land og
    vokser i BTC-rally. En fælles komponent i signeret volumen forklarer 80 % af BTC-afkastet.
  - Kimchi:
    - E31 (Choi, Lehar & Stauffer, WP): Korea lå i gennemsnit 4,73 % over USA i 2016-01 til 2018-02.
    - E32 (Lee & Oh, FRL 2022): toppen var 20,8 % den 19-05-2021, og præmien er knyttet til pengeoverførsler til Kina.
    - E33 (Borri & Shakhnov, RAPS 2022): forklaringen er risiko, ikke kun friktion.
  - E34 (Hautsch, Scheuch & Voigt): afregningslatens begrænser arbitrage.
  - E35 (Alexander m.fl., JFM 2020): BitMEX-derivater fører spot på minutniveau.
- **Evidensstyrke:** stærk som beskrivelse (JFE, RAPS, JFM). Handelsfordelen er ikke dokumenteret, fordi arbitragen
  kræver flytning af kapital over grænser, KRW-udbetaling eller konti i flere lande.
- **Copybot:**
  - N4 kimchi: `studies/MISSION27_4_2026-11-02.md` og `drafts/U1F_UPBIT_FREMAD.md`.
  - `cross_venue_perp_gap` (Hyperliquid–Binance-scanneren) og `dex_pool_arbitrage` (`RESULTS_arb_v1.md`: 0 muligheder).
  - `lead_lag_diffusion`: `studies/SPOTPERP_m21i.md` fandt et svagt timesignal for "spot fører perp" og gav SCREEN_FAIL.
  - Børsomkostninger: `studies/V1_DOM_2026-10-29.md` og `studies/VENUE_REGISTER_2026-10-27.md`.
- **Data:** kimchi er AVAILABLE_AFTER_2026-11-14, og kun til N4 via api.upbit.com. Hyperliquid–Binance er AVAILABLE_FORWARD.
  Afregningslatens on-chain: UNKNOWN.

## 10. Volatilitet, regimeskift og prognosekvalitet (E36–E39, E44)

- **Dokumenteret:** HAR-modeller på realiseret volatilitet med spring, semivarians og strukturbrud forudsiger
  volatilitet bedre uden for sample. Det gælder E36 (Shen, Urquhart & Wang, EFM 2020: HARQ-F-J bedst), E37 (Ftiti m.fl.,
  AOR 2021; 4 mønter, 5-minutters data, 2018–2020) og E38 (Hu, Härdle & Kuo). E39 (Ardia m.fl., FRL 2019): Markov-switching
  GARCH slår modeller med ét regime på VaR for 1 dag.
- **Evidensstyrke:** stærk og konsistent, men det er en **prognose af risiko**, ikke af afkast. Hvilken model der vinder,
  afhænger af mønt, horisont og regime (E37). Ingen kilde måler en økonomisk værdi efter omkostninger.
- **Copybot:** `volatility_managed_exposure` og `low_volatility_anomaly`. Volatilitetsstyring i
  `studies/DONCHIAN_POWER_P1_2026-11-06.md`, regimer i `families/drafts/fregime.json` og risiko i `../lab/risk.py`.
- **Data:** AVAILABLE_FORWARD (intradag-klines og bøger). 1m-historik som i R3 er AVAILABLE_AFTER_2026-11-14.

---

## Ikke-verificerede spor (står IKKE i registret)

| Spor | Status |
|---|---|
| "Cryptocurrency Perpetual Futures and Swaps: A Systematic Literature Review" (direktørens kilde, "22 studier") | Søgningen fandt kun en preprint på preprints.org (202607.1592). Siden gav 403. Ingen SSRN-version fundet. Antallet af studier er ikke bekræftet |
| "Anatomy of cryptocurrency perpetual futures returns" (Edinburgh Research Explorer) | Den præcise titel blev ikke fundet, og research.ed.ac.uk gav 403. Nærmeste verificerede kilde er Luo's afhandling (E02). Titlen nævnes sekundært på tradingstrategy.ai uden forfatter |
| "Arbitrage in Perpetual Contracts" (SSRN) | Ikke fundet. Søgningerne gav kun He m.fl. (E03) og Ackerer m.fl. (E07) |
| Dobrynskaya, "Cryptocurrency Momentum and Reversal", J. Alternative Investments 26(1) 2023 / SSRN 3913263 | Kun HSE's nyhedsside er åbnet (ikke artiklen). Den siger ca. 2.000 mønter, 2014–2020, momentum under ca. 1 måned og reversal fra 4–6 uger. SSRN gav 403 |
| Alexander & Imeraj, "The Bitcoin VIX and its Variance Risk Premium", JAI 23(4) 2021 | Sussex, figshare og pm-research gav 403 eller krævede login |
| Bergsli, Lind, Molnár & Polasik, "Forecasting volatility of Bitcoin", RIBAF 59 (2022) | Repository-DNS fejlede, og core.ac.uk gav 403 |
| Han, Kang & Ryu, "Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market" | PDF'en gav 403. Kun et søgeuddrag: TSMOM stærk, XSMOM svag efter omkostninger og likvidation |
| Lu m.fl., "The Risk and Return of Cryptocurrency Carry Trade" (tværsnits-funding) | Seminarsiden gav HTTP 483. Tallene 43,4 % p.a. og Sharpe 0,74 er kun set i et søgeuddrag |
| Schmeling, Schrimpf & Todorov, Management Science (doi 10.1287/mnsc.2024.05069) | 403. BIS-versionen (E04) er verificeret |
| Hautsch m.fl., Review of Finance 28(4) 2024; "121 bp / 91 %" | Tidsskriftsiden er ikke åbnet. Tallene kommer fra et søgeuddrag |
| Zhivkov, MDPI 2026 (26 børser, funding-korrelation og -persistens) | 403 |
| Cao m.fl., SSRN 6365329 (170 perp-prædiktorer) | Citeret i NEXT_MECHANISMS. Ikke genåbnet i dag. Samme tal som E02 |
| Hoang & Baur's tal (CryptoQuant, 20 børser, reserver ca. 12 %) | Kun fra Quantpedia-uddrag. Abstractet (E25) har ingen tal |
| Garcia Seuma, arXiv 2607.27070 og 2608.03616 (likvidationskaskader) | Ikke åbnet |
| Bieganowski, arXiv 2602.00776 (1 s mikrostruktur, Binance Futures) | Ikke åbnet |
| Zulfiqar & Gulzar, Financial Innovation 2021 (BTC IV-skew) | Ikke åbnet |
| Seo, Koo & Yang 2024, Economic Modelling (kimchi, langsigtet 1,24 %) | Ikke åbnet |
| Messari-rapport om listninger på Coinbase og Binance | Ikke åbnet (kun Cointelegraph-referat i søgning) |
