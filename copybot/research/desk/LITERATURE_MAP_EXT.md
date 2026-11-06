# Litteraturkort, udvidelse: 75 nye verificerede kilder (X001–X075, 2026-11-06)

Supplement til `LITERATURE_MAP.md` (E01–E44, uændret). Registret står i `evidence_registry_ext.json`, med samme felter
som `evidence_registry.json` og fem nye felter:

- `copybot_families`: kun tag-id'er fra `research/families/VOCABULARY.json`.
- `supports_ids`, `contradicts_ids` og `extends_ids`: henvisninger til E- og X-numre.
- `post_2022_data`: om kilden selv oplyser data efter 2022-01-01.
- `net_of_cost_evidence`: om kilden selv sammenligner effekten med handelsomkostninger.

**Regler (som i det oprindelige register):**

- Kun kilder, der er åbnet i denne session. URL'en står i `url_opened`: abstract-side (IDEAS/RePEc, arXiv, NBER, BIS)
  eller PDF, der er læst med `pdftotext`.
- Tal er kun gengivet, når de står i den åbnede tekst. Ellers står der UNKNOWN. Resuméerne er mine egne ord.
- Ingen markedsdata, børs-API'er, kurser, funding eller klines er hentet.
- Ingen strategiforslag. En statistisk effekt er ikke en handelsfordel.

SSRN (papers.ssrn.com), ScienceDirect og INFORMS svarede 403 hele sessionen. Kilder, der kun findes dér, står under
"Ikke-verificerede spor".

## Optælling

| | Antal |
|---|---|
| Nye verificerede kilder | **75** |
| Kat. 1 funding / 2 basis / 3 momentum og replikation / 4 likvidation og reversal / 5 mikrostruktur | 3 / 4 / 11 / 15 / 15 |
| Kat. 6 listning og overlevelse / 7 on-chain og stablecoins / 8 optioner / 9 tværbørs og kimchi / 10 volatilitet | 5 / 10 / 5 / 7 / 0 (som sekundær kategori: 6) |
| Fagfællebedømt tidsskrift / konference (WWW, IMC, FC) | 38 / 3 |
| Working paper (arXiv, CEPR, NBER, BIS, BoC) / speciale | 33 / 1 |
| result_type: descriptive / forecast / net_trading / theory | 59 / 6 / 8 / 2 |
| Data efter 2022 i kilden | 24 |
| Kilden sammenligner selv med omkostninger (net_of_cost_evidence ≠ "no") | 13 |
| Dataadgang: AVAILABLE_FORWARD / AFTER_11-14 / BLOCKED_TIL_11-28 / NOT_AVAILABLE / UNKNOWN | 19 / 17 / 0 / 26 / 13 |

**Det vigtigste nye:**

- Netto-evidensen er stadig negativ eller betinget.
- De nyeste replikationer underkender publicerede faktorer:
  - X066: CTREND falder fra Sharpe 2,08 til 0,01. Nettoafkastet bliver −0,87 % om ugen.
  - X038: positiv IC, men negativ netto-Sharpe i holdout.
  - X022: et kant på 1,3 bp mod 5 bp i omkostninger.
- Positive nettopåstande gælder enten illikvide mønter (X070, X042) eller er risikojusterede uden tal (X069, X023).

---

## 1. Funding og funding-arbitrage (X002, X003, X008; se også X001, X004, X014)

- **Nyt:**
  - Teori:
    - X002 (Kim & Park 2025): funding-design, der holder perp-prisen på et mål.
    - X003 (Angeris m.fl. 2022): modelfri funding- og diskonteringsrater, friktionsfrit.
  - X008 (Krestenko m.fl. 2026): DeFi spot-perp-basis med målte eksekveringskiler, både live og i backtest.
    - Kilerne er betydelige og størst, når basis sælges.
    - Resultatet forklares mest af fundingregimet.
    - Abstractet giver ingen afkasttal.
- **Stadig ikke fundet:** en fagfællebedømt kilde om funding-persistens eller -prædiktion på tværs af perps.
  - Inan, "Predictability of Funding Rates" (SSRN 5576424) gav 403. E40 er afhandlingsversionen.
  - Hullet fra `research_gaps.md` B1 består.
- **Copybot:** `delta_neutral_funding_carry`, `funding_carry_leverage`. `studies/CARRY_REALISM_P0P1_2026-11-06.md` og
  `studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md`.
- **Data:** CEX-analogen er AVAILABLE_FORWARD. DeFi-venues indsamles ikke.

## 2. Carry, basis og implicitte renter (X001, X004, X005, X006)

- **Nyt:**
  - X001 (Schmeling, Schrimpf & Todorov, CEPR DP 20719, okt. 2025): den nyeste version af E04. Carry er "nogle gange over
    40 % p.a." (E04 sagde op til 60 %). Samme forklaring: trendjagende gearet efterspørgsel møder knap arbitragekapital.
    Bruttoniveau. Management Science-versionen gav stadig 403.
  - X004 (Bergault m.fl. 2025; Deribit 2023-02 til 2026-02): den derivatimplicitte USD-rente lå i gennemsnit omkring 8 % om
    året og steg i 2024-rallyerne. Implicitte BTC- og ETH-renter ligger nær nul, og der er et vedvarende gab til Aave-renter.
    **Efter 2022.**
  - X005 (De Blasis & Webb, JFM 2022): kvartalsvise cash-and-carry-muligheder findes især under dislokationer. Perps har
    u-formede intradagmønstre.
  - X006 (Shi, JFM 2022): positionering pr. tradertype forudsiger afkast på regulerede BTC-futures. Spekulanter handler
    negativt feedback, detail positivt feedback.
- **Evidensstyrke:** fagfællebedømt for "basis i dislokationer" (X005). Niveauet er stadig brutto.
- **Copybot:** `dated_futures_basis_carry` (F2 `families/drafts/dbasis.json`, `F2_PLAN.md`, `../lab/carry90.py`).
- **Data:**
  - USD-M daterede kontrakter: AVAILABLE_FORWARD.
  - Deribit: NOT_AVAILABLE.
  - Positionsdata af COT-typen: NOT_AVAILABLE.

## 3. Momentum, trend, tværsnit og replikation (X065–X075)

- **Replikationer og kritik (nyt og vigtigt):**
  - X066 (Wang & Pang, arXiv/SSRN 11-2026): kodeaudit af den publicerede trendfaktor CTREND.
    - Efter fuld korrektion falder bruttoafkastet fra 4,07 % til 0,05 % om ugen og Sharpe fra 2,08 til 0,01.
    - Alfa bliver −1,38 % og er insignifikant. Nettoafkastet går fra 2,93 % til −0,87 % om ugen.
  - X067 (Grobys m.fl., FRL 2026; 2017–2024): ingen momentum blandt overlevende mønter. Plain momentum virker kun efter
    trimning og afhænger stærkt af stikprøven.
  - X068 (Hudson & Urquhart, AOR 2021): cirka 15.000 regler holder efter kontrol for data-snooping, men **BTC har ingen
    forudsigelighed uden for sample**.
  - X069 (Deprez & Frömmel, IREF 2024): 75.360 regler udvalgt efter omkostninger og med multipel testning. Porteføljerne
    slår buy-and-hold uden for sample, mest risikojusteret. Tal er UNKNOWN. Modsiger X068 for BTC.
  - X075 (Zhu & Cai, arXiv 2026, review): ingen offentlig evidens for vedvarende, kapacitetsbevidst nettoalfa fra AI.
- **Tværsnit:**
  - X065 (Fieberg m.fl., QF 2023): 34 anomalier replikeret på mere end 3.900 mønter (2014–2022). Faktormomentum findes og
    stammer fra størrelses- og volatilitetsanomalier.
  - X070 (Cakici m.fl., IRFA 2024): ML-strategier er profitable efter omkostninger, men alfa ligger i svært handlelige,
    små og illikvide mønter.
  - X071 (Mercik m.fl., IRFA 2025; mere end 500 mønter, 2017–2023): interaktioner giver Sharpe over 1 uden for sample.
    Illikviditet holder anomalierne i live.
  - X072 (Jia m.fl., JBF 2026): nærhed til 52-ugers-toppen giver cirka 130 bp om ugen, brutto.
- **Adfærdsmekanisme:**
  - X073 (BIS WP 1049): stigende BTC-pris efterfølges af nye detailbrugere. Cirka tre fjerdedele har tabt penge.
  - X074 (BIS Bulletin 69): efter Terra og FTX solgte store investorer, mens detail købte.
  - Begge støtter mekanismen bag E04/X001.
- **Evidensstyrke:** replikationerne er de stærkeste nye kilder. De peger samme vej som E11, E22 og E01: effekterne
  svinder, når look-ahead, overlevelse, likviditet og omkostninger håndteres.
- **Copybot:** `time_series_momentum`, `cross_sectional_momentum`, `trend_following`, `anchoring_to_high`.
  `RESULTS_tsmom_v1.md` og `studies/DONCHIAN_POWER_P1_2026-11-06.md`.
- **Data:** AVAILABLE_AFTER_2026-11-14 (historisk). BIS-appdata: NOT_AVAILABLE.

## 4. Likvidationer, kaskader, ADL og reversal (X009–X023)

- **Likvidationernes størrelse (CEX):**
  - X009 (Cheng m.fl.; BitMEX): tvangslikvidationer udgør dagligt 3,51 % (long) og 1,89 % (short) af open interest.
    Gearingen er cirka 60x.
  - X010 (Soska m.fl., WWW '21): mere end 425.000 likvidationer, op til cirka 1 mia. USD på en uge (nov. 2018).
    Hændelser over 100 mio. USD faldt sammen med kursspring. Long-likvidationer dominerer. Forfatterne siger selv, at
    kausaliteten er uafklaret.
  - X011 (Alexander, Deng & Zou):
    - 19-05-2021 blev der rapporteret 8,6 mia. USD i likvidationer, og Binances data for maj var unøjagtige.
    - Ved 100x ender mere end 95 % af 1-dagspositionerne i likvidation.
- **Kaskadernes forløb (efter 2022):**
  - X012 (Garcia Seuma 2026; 7 BTC-kaskader 2022–2025): intet varslingssignal virker i alle hændelser. Kun en
    kompression af taker-flowets varians overlever, og kun på populationsniveau.
  - X013 (samme forfatter):
    - Oktober 2025 var subkritisk (forgreningsrate 0,1–0,2), og 88 % af tvangssalget faldt inden for 30 minutter.
    - 63 % blev absorberet uden for bogen af venue-backstoppen, og OI faldt 25–70 %.
  - X014 (Chitra 2025): Hyperliquids ADL lukkede 2,1 mia. USD på 12 minutter den 10-10-2025.
    - Overskydende haircut på profitable tradere var 45,0–51,7 mio. USD.
    - Binance siges at bruge ADL mere end Hyperliquid.
    - **Halerisiko for afdækkede carry-ben**, som E05 og E08 ikke prissætter.
- **Datakvalitet:** X015 (Giagkiozis & Said, Ledger 2024): OI fejlrapporteres systematisk af nogle store børser, og nogle
  forsinker likvidationsbeskeder. Se også X011 (Binance) og X038.
- **DeFi:** X016–X019 (Lehar & Parlour BIS 1062; Tian & Zhu BoC; Qin m.fl. IMC; Perez m.fl. FC).
  - Likvidationssalg har en midlertidig og en **permanent** prispåvirkning.
  - Auktioner dæmper prisfaldet, når deltagelsesomkostningen er lav.
  - Et prisfald på 3 % kan gøre mere end 10 mio. USD likviderbart, og mere end 70 % likvideres straks.
- **Reversal:**
  - X020 (Kozlowski m.fl., AEL 2021; 200 mønter, 2015–19): reversal på dag, uge og måned, stærkest i små og illikvide mønter.
  - X021 (Bianchi, Babiak & Dickerson, JBF 2022; 2017–2022): reversal er et afkast for likviditetsforsyning og ligger i
    par med lav aktivitet.
  - X022 (Kitron & Wengrowicz 2026): 15-minutters reversal i 90 % af 183 Binance-par mod 2,7 % af amerikanske aktier.
    Bruttokanten er cirka 1,3 bp pr. handel mod 5 bp i round-trip-omkostning. **Efter 2022, netto negativ.**
  - X023 (Nakagawa & Sakemoto, FRL 2025): ankret reversal skal være robust over for omkostninger. Ingen tal.
- **Hullet "kursadfærd efter kaskader" er stadig åbent.** Ingen kilde giver afkast efter en kaskade. X027 (Mt. Gox) og
  X016 peger på en permanent komponent, ikke fuld reversal.
- **Copybot:** `liquidation_cascade_reversal`, `short_term_reversal_liquidity`, `funding_carry_leverage`.
  `studies/MOVESCREEN_m21c.md` (SCREEN_FAIL stemmer med X022) og `../lab/straks.py`.
- **Data:**
  - Likvidationer pr. ordre: UNKNOWN (som E16).
  - Minutkurser og taker-flow: AVAILABLE_FORWARD.
  - DeFi og on-chain: NOT_AVAILABLE.
  - Reversal-tværsnit: AVAILABLE_AFTER_2026-11-14.

## 5. Ordreflow, omkostninger og mikrostruktur (X024–X038)

- **Ordreflow:**
  - X026 (Silantyev, Digital Finance 2019; BitMEX XBTUSD): trade-flow-ubalance forklarer den samtidige kursændring bedre
    end samlet OFI. Sammenhængen er lineær over lange nok intervaller.
  - X024 (Bieganowski & Ślepaczuk 2026; Binance Futures 1 s, 2022–10-2025): taker-backtestens årlige afkast på kapital.
    - BTC 0,13 mod buy-and-hold 0,83. ETC 5,78 og ROSE 7,00, hvor ROSE især kommer fra 10-10-2025.
    - Latens er ikke modelleret. Det er uklart, hvilke tabeller der er gebyrjusterede.
  - X025 (Albers m.fl., live-eksperiment på Binance BTC-perp): sandsynligheden for maker-fill er negativt korreleret med
    afkastet efter fill. Gængse maker-strategier er stærkt urentable.
  - X027 (Scaillet m.fl.; Mt. Gox): OFI og spreadudvidelse forudsiger spring, og springene giver varige kursændringer.
  - X028 (Donier & Bonart): kvadratrodsloven for prispåvirkning holder over fire dekader.
  - X029 (Barone & Lillo 2026, Hyperliquid): synlige TWAP'er koster mindre og efterlader mindre permanent prispåvirkning
    end skjulte metaordrer.
- **Intradagmønstre:**
  - X030 (Eross m.fl., RIBAF 2019): likviditet og volatilitet følger aktiemarkedernes åbninger.
  - X031 (Hansen, Kim & Kimbrough 2021): mønstre for dag, time og inden for timen er blevet stærkere og hænger sammen
    med algohandel og **fundingtidspunkter**. Det er den eneste verificerede kilde til K3-spørgsmålet, og den er kun
    kvalitativ.
  - X036 (Alexander, Heck & Kaeck): Binances USDT-perp er den primære kilde til volatilitetsoverførsel.
- **Omkostninger:**
  - X032 (Aleti & Mizrach, JFM 2021): spread 0,0298 %. Handler over 1 mio. USD flytter kursen under 1 %. CME fører
    prisdannelsen.
  - X033 (Brauneis, Mestel & Theissen, FRL 2021): likviditet drives af volatilitet, volumen og antal handler.
  - X034 (Galati, JBF 2024): da Binance fjernede gebyrerne i juli 2022, voksede spreads, dybden blev mindre, og kundernes
    samlede omkostning **steg**. **Efter 2022.**
  - X035 (Jeon m.fl., FRL 2021): fragmentering koster også ved små handler.
  - X037 (Barbon & Ranaldo): gas-gebyrer giver vedvarende afvigelser mellem CEX og DEX.
- **Punkt-i-tid:** X038 (Zeng m.fl. 2026; Binance BTCUSDT-arkiver).
  - Det længste hulfri 5-minuttersudsnit af alle strømme var kun 304,57 dage.
  - Audit sænkede falske beståelser fra 0,2910 til 0,0625.
  - I holdout havde alle kørsler positiv IC, men **negativ netto-Sharpe**.
- **Copybot:** `orderflow_imbalance`, `maker_adverse_selection_measurement`, `intraday_seasonality`.
  `studies/H_SPR1_INSTRUMENT_SPREAD_2026-11-03.md`, `studies/H_SPR2_TICK_SPREAD_2026-11-04.md`,
  `studies/COSTS_2026-10-24.md`, `drafts/K3_INDSAMLING_UDKAST_2026-10-25.md` og
  `studies/FACTORY_SECURITY_P1_2026-11-06.md`.
- **Data:**
  - Bøger og spreads: AVAILABLE_FORWARD.
  - Handler på trade-niveau og 1-sekunds bøger (X024): UNKNOWN.
  - Hyperliquid-fills pr. adresse: UNKNOWN.
- **Tick size:** ingen kilde med et naturligt eksperiment fundet. Hullet består.

## 6. Listning, pump-and-dump og overlevelse (X039–X043)

- **Nyt:**
  - X040 (Ante & Meyer, DEF 2021; 250 ICO-krydslistninger, 22 børser): 6,51 % på dagen og 9,97 % over 7 dage. Op til 34 %
    på nogle børser og ubetydeligt på andre.
  - X039 (Laucht, speciale EUR 2022; 390 listninger, 2020–21): 2,35 % på dagen og cirka 9,5 % i vinduet [−3,+3]. Positivt
    før listningen, **negativt efter**.
  - X041 (Dhawan & Putniņš, RoF 2023): 355 pumps gav i gennemsnit 65 % kursforvridning.
  - X042 (Ballis & Ioannidis 2026; 8.970 aktiver, 2013–2026): den nederste decil tjener 27,5 % om ugen på papiret og
    intet blandt aktiver, der faktisk handles. Kapaciteten er 293.000 USD.
  - X043 (Myeong & Kim, EL 2025): positive og neutrale annonceringer på den koreanske platform Xangle giver signifikante
    kumulative afkast.
- **Upbit-specifikt:** ingen verificeret kilde. Messari, The TIE og Klein Labs er kun set som praktikerreferater.
- **Afnotering:** ingen verificeret kilde. Tallene for 101 Binance-afnoteringer (fald på 26,3 % på 24 timer) er kun set i
  et sekundært referat.
- **Copybot:** `short_new_listings`, `memecoin_launch_selection`. `drafts/H5F_NOTERING_FREMAD.md`,
  `drafts/M1F_MONITORING_FREMAD.md` og `drafts/U1F_UPBIT_FREMAD.md`.
- **Data:** listninger fremad er AVAILABLE_FORWARD. Pump-grupper: NOT_AVAILABLE.

## 7. On-chain og stablecoins (X044–X053)

- **Stablecoin-udstedelse og kurs:**
  - X044 (Ante, Fiedler & Strehle, FRL 2021; 565 udstedelser): positivt unormalt afkast inden for 24 timer omkring
    udstedelsen, efter en uge med fald.
  - X045 (samme forfattere, TFSC 2021; 1.587 overførsler): unormal volumen og unormale afkast i timerne omkring.
  - X051 (Saggu): BTC reagerer positivt på USDT-mints i vinduer på 5–30 minutter. Effekten aftager efter 60 minutter.
  - Imod: X047 (Wei, EL 2018) finder ingen effekt på efterfølgende BTC-afkast, kun på volumen. X046 (Kristoufek, FRL 2021)
    finder, at udstedelsen reagerer på kursen, ikke omvendt.
- **Strømme og hvaler:**
  - X049 (Makarov & Schoar, NBER 29396): 90 % af on-chain-volumen er ikke økonomisk meningsfuld. Cirka 75 % af den reelle
    volumen hænger sammen med børser.
  - X050 (Magner & Sanhueza, FRL 2025): BTC-hvalers overførsler smitter især efter 6 og 24 timer. Ingen størrelser.
  - X053 (Herremans & Low): ML-prognose for volatilitetsspring. Ingen tal.
- **Depeg:** X048 (Duan & Urquhart, FRL 2023): stablecoins er ustabile, korrektionshastigheden varierer, og DAI
  konvergerer ikke. Det er relevant for USDT-margineret carry.
- **MEV:** X052 (Qin, Zhou & Gervais): BEV gav 540,54 mio. USD over 32 måneder.
- **Kendte spor fra opgaven:** Griffin & Shams er E26. "Kim et al." om stablecoins er ikke identificeret.
- **Copybot:** `stablecoin_liquidity_flow`, `smart_money_following`, `onchain_value_mvrv`.
  `drafts/ONCHAIN_KILDEAUDIT_2026-10-24.md`.
- **Data:** NOT_AVAILABLE. Undtagelse: stablecoin-spotpriser for depeg (X048) er AVAILABLE_FORWARD.

## 8. Optioner (X054–X057; se også X007)

- **Nyt:**
  - X055 (Hoang & Baur, JFM 2020): Deribit-IV er dårligere end HAR 1 dag frem og bedre 7, 10 og 15 dage frem.
  - X056 (Alexander & Imeraj, QF 2023): smile-justerede deltaer sænker variansen på hedgefejlen med mere end 30 % for
    OTM-puts. Perpen har langt mindre basisrisiko end kalenderfutures.
  - X054 (Hou m.fl., JFEc 2020): springmodellen SVCJ.
  - X057 (Kim, JFM 2025): bearish sociale medier gør skew mere negativ.
  - X007 (Liu, Packham & Sepp 2025): jump-præmier forudsiger futures-carry og P&L på delta-hedgede optioner. Ingen tal.
- **VRP-størrelse:** stadig ikke verificeret. Alexander & Imeraj "Bitcoin VIX" (SSRN 3383734) gav 403, og Sussex-repoet
  svarede 202 med en tom side.
- **Copybot:** `variance_risk_premium_timing`.
- **Data:** NOT_AVAILABLE.

## 9. Tværbørs, arbitrage og kimchi (X058–X064)

- **Arbitrage:**
  - X058 (Crépellière, Pelster & Zeisberger, JFM 2023): mulighederne findes, men blev langt mindre fra april 2018 og kan
    næppe udnyttes efter omkostninger. Det **modsiger, at E30's gab kan udnyttes** i perioden efter 2018.
  - X059 (Guo m.fl., FRL 2025; 16 børser, 2013–2024): gabet varer længere, når den risikable børs har den høje pris.
    Gebyrer og overbelastning på kæden bremser kapitalen. Gabet er altså delvis en præmie for modpartsrisiko.
  - X064 (Saggese m.fl.; Mt. Gox): arbitragegevinsten tilfalder få dygtige brugere.
- **Kimchi:**
  - X062 (Seo, Koo & Yang, EM 2024; tidligere et ikke-verificeret spor): det langsigtede niveau er 1,24 %. Præmien
    mean-reverterer kun uden for et bånd, og båndet stiger med gebyret.
  - X063 (Borri & Shakhnov, JIMF 2023): rabatterne har en halveringstid på 1 dag og en standardafvigelse på 3,9 %. De er
    større ved strammere kapitalkontrol.
  - X060 (Eom, FRL 2021): præmien skyldes spekulation. X061 (Ok, Kim & Kim, FRL 2023) finder, at sammenhængen **ikke er
    robust over tid**.
- **Copybot:** `cross_venue_perp_gap`, `dex_pool_arbitrage`. `RESULTS_arb_v1.md`,
  `N4 kimchi: studies/MISSION27_4_2026-11-02.md` og `drafts/U1F_UPBIT_FREMAD.md`.
- **Data:** kimchi er AVAILABLE_AFTER_2026-11-14, og kun til N4. Tværbørs-gab er AVAILABLE_FORWARD.

---

## Åbnet, men udeladt af registret (for svage eller uden for emnet)

| Kilde | Grund |
|---|---|
| arXiv 1912.03270 (BitMEX funding, GARCH) | studenterpapir, ingen tal |
| arXiv 2601.06084 ("Who sets the range? Funding mechanics") | ingen empiri |
| arXiv 2112.06807 (Matic m.fl., hedging af kryptooptioner) | kun hedge-metode, ingen præmie |
| FRL 57 (2023) 104196 (Chang m.fl., kryptomomentum og VIX-præmie) | tangentielt |
| Digital Finance 2(3) 2020 (Meyer & Ante, ICO-karakteristika) | samme stikprøve som X040, ingen tal |
| arXiv 2110.09429, 2010.15611, 2506.08718, 2609.34510, 2411.08720, 2411.05803, 2202.10265, 2507.22712 | svage, uden tal, eller ikke krypto (2507.22712 er indiske futures) |
| arXiv 2212.06888v7 (He m.fl., revideret 2026-09-17) | samme kilde som E03. Abstractet bekræfter E03 (afvigelserne falder over tid, høj Sharpe). Ikke dobbeltregistreret |
| arXiv 2607.09426 (v2) | er E19 |

## Ikke-verificerede spor (nye, står IKKE i registret)

| Spor | Status |
|---|---|
| Inan, "Predictability of Funding Rates" (SSRN 5576424) | 403. Kun søgereferat (DAR-modeller slår no-change, tidsvarierende) |
| Félez-Viñas, Johnson & Putniņš, "Insider trading in cryptocurrency markets" (SSRN 4184367) | 403. Søgereferaterne er indbyrdes uenige (28–48 % mod 10–25 % af listningerne) |
| Li, Luo, Wang & Wei, "Cryptocurrency Listings on Cryptocurrency Exchanges" (SSRN 4715718) | 403. Sandsynligvis den fulde version af E21 |
| Alexander, Chen, Deng & Wang, "Arbitrage opportunities and efficiency tests in crypto derivatives" (SSRN 4495548) | 403. EconBiz har kun metadata |
| Alexander & Imeraj, "The Bitcoin VIX and its Variance Risk Premium" (SSRN 3383734, JAI 2021) | 403, og Sussex svarede 202 med en tom side |
| Aloosh & Li, "Direct Evidence of Bitcoin Wash Trading" (SSRN 3362153) | ikke åbnet (SSRN blokeret) |
| Le Pennec, Fiedler & Ante, wash trading over 90 % | kun sekundært citat |
| Neubert, Rams & Gruhn, systematisk review af adfærd i perps (SSRN 6658879) | ikke åbnet. Kan være direktørens "systematic literature review" |
| Xuan, funding og ordreflow på Binance XAUUSDT (SSRN 6872638) | 403. Referatet siger "ikke profitabelt efter omkostninger" |
| Studie af 101 Binance-afnoteringer (fald på 26,3 % på 24 timer) og APJFS 2026 om prædiktorer for afnotering | kun sekundært referat (edgex) |
| Schmeling m.fl., Management Science (doi 10.1287/mnsc.2024.05069) | 403 igen. Den nyeste verificerede tekst er X001 |
| BitMEX, analyse af 9 års XBTUSD-funding | siden viste kun blogindekset (BitMEX stoppede handlen 2026-09-23 ifølge banneret) |
| Ante & Fiedler, "Market reaction to large transfers on the Bitcoin blockchain" (FRL 39) | IDEAS-URL'en ramte en anden artikel. Ikke verificeret |
| Zhang & Makgolo (SSRN 6648082) og Proelss m.fl. (SSRN 4824456) om momentum uden overlevelsesbias | 403 eller ikke åbnet |

## Status for tidligere ikke-verificerede spor (fra LITERATURE_MAP.md)

- **Nu verificeret:** Seo, Koo & Yang 2024 (1,24 %), som X062.
- **Stadig ikke verificeret:**
  - Alexander & Imeraj (VIX).
  - Schmeling m.fl. (Management Science). CEPR-versionen er verificeret som X001.
  - Zulfiqar & Gulzar.
  - Dobrynskaya.
  - Han, Kang & Ryu.
  - Lu m.fl.
  - Hautsch m.fl. (RoF).
  - Messari (listninger).
- **Delvist dækket:** Garcia Seuma (likvidationskaskader) er åbnet som X012 og X013. Bieganowski er åbnet som X024.
