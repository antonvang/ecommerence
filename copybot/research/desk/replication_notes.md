# Replikationsnoter: holder evidensen på tværs af stikprøver, perioder og børser? (2026-11-06)

Grundlag: `evidence_registry.json` (E01–E44) og `evidence_registry_ext.json` (X001–X075). Kun mekanismer med mindst to
verificerede kilder er medtaget. **Ingen strategiforslag.**

Mærker:

- **[E22+]**: data efter 2022.
- **[NETTO]**: kilden sammenligner selv med handelsomkostninger.
- "Replikerer": samme fortegn og en effekt af samme størrelsesorden i uafhængige stikprøver, perioder eller børser.
  Samme forfattergruppe på overlappende data tæller ikke som uafhængig.

## Overblik

| # | Mekanisme | Kilder | Replikerer? | Efter 2022 | Netto efter omkostninger |
|---|---|---|---|---|---|
| 1 | Carry-niveau og fundingpræmie | E04, X001, E05, E08, E42, E03, X004 | **Ja, i fortegn.** Niveauet falder over tid | E08, E42, X001, X004 | E03 positiv (WP), E42 praktiker. Ingen fagfællebedømt |
| 2 | Persistens og prædiktion af funding | E40, E41, E42 | **Ukendt.** Kun BTC og ikke fagfællebedømt | E40 | nej |
| 3 | Basis og cash-and-carry kun i dislokationer | E04, E06, X005, E03 | Ja (kvalitativt) | E03 | E03 |
| 4 | Likvidationer, kaskader, varsling | E16, X009–X015 | Skala ja. **Varslingssignaler nej** | X012, X013, X014, X015 | — |
| 5 | Kursadfærd efter tvangssalg | X016, X027, X010, E16 | **Ikke testet direkte** | — | — |
| 6 | Kortsigtet reversal | E14, E15, X020, X021, X022, X023, X042 | **Ja**, altid i illikvide mønter | X022, X042 | **X022 negativ** (1,3 bp mod 5 bp) |
| 7 | Momentum og trend | E09, E10, E11, E12, E13, E22, E01, E43, X065–X069 | **Nej, modstridende** | X066, X067 | X066 negativ, X069 positiv risikojusteret |
| 8 | ML og tværsnitsanomalier | E01, E02, X070, X071, X072 | Brutto ja. Netto kun i illikvide | X071 | X070 (illikvide), E01 mest negativ |
| 9 | Ordreflow og OFI | E18, E19, X024, X025, X026, X027 | Samtidig sammenhæng ja. Prædiktion ny | X024, X025 (E19: periode UNKNOWN) | X024 delvist. BTC svagt |
| 10 | Intradagmønstre | X030, X031, X005, X036, E19 | **Ja, og stærkere over tid** | — (E19: periode UNKNOWN) | — |
| 11 | Omkostninger, gebyrer, fragmentering | E17, X032, X033, X034, X035, X028 | Ja | X034 | er selv omkostningsmålinger |
| 12 | Arbitrage på tværs af børser | E30, E34, X058, X059, X063, X064, X035, X037 | Gab ja. **Udnyttelse nej efter 2018** | X059 | X058 og X064 negative eller koncentrerede |
| 13 | Kimchi-præmien | E31, E32, E33, X060–X063 | Eksistens ja. **Forklaringen strides** | — | — |
| 14 | Stablecoin-udstedelse og BTC-kurs | E26, E24, X044–X047, X051 | **Modstridende** og afhængigt af horisont | — | nej |
| 15 | Børsstrømme og hvaler | E24, E25, X049, X050, X053 | Delvist. Ingen størrelser | X050 | nej |
| 16 | Listningsafkast | E20, E21, X039, X040, X043 | Kortsigtet positivt ja. Efter listning negativt | X043 | nej |
| 17 | Overlevelse og handlelighed | E22, X042, X066, X067, X038 | **Ja** | X042, X066, X067, X038 | X042, X066, X038 |
| 18 | Implicit volatilitet og VRP | E27, E28, E29, E44, X055, X007, X057 | IV-information ja. **VRP-størrelse ukendt** | X007, X057 | nej |
| 19 | Prognose af realiseret volatilitet | E36–E39, E44, X055 | Ja | — | nej |
| 20 | Prispåvirkning fra DeFi-likvidationer | X016–X019, X052 | Ja (mekanismen) | — | — |

---

## 1. Carry-niveau og fundingpræmie

- **Replikerer i fortegn:**
  - Positiv carry findes på Binance (E05), i BIS' futures-spot-data (E04/X001) og i E08's faktorstudie.
  - E42 (praktiker) viser det samme, og E03 for BTC/ETH perp mod spot.
  - X004 viser **efter 2022** en implicit USD-rente på cirka 8 % p.a. på Deribit (2023–2026).
- **Niveauet replikerer ikke:**
  - E04 sagde op til 60 % p.a. X001 (CEPR 2025, samme forfattere) siger "nogle gange over 40 %".
  - E08: Sharpe 6,45 i 2020–2025 og 4,06 fra 2024, negativ i 2025.
  - E03: afvigelserne falder cirka 11 % om året. v7 (arXiv 2212.06888v7, åbnet) gentager "aftager over tid".
  - **Konklusion: effekten aftager konsistent i alle kilder.**
- **Netto:**
  - E03 giver Sharpe 1,8 med detail-gebyrer, men er ikke fagfællebedømt.
  - X008 (2026, DeFi): eksekveringskiler er betydelige, og resultatet styres af fundingregimet. Ingen tal.
  - Ingen fagfællebedømt nettokilde efter 2022.
- **Nye risici, der ikke indgår i Sharpe-tallene:**
  - ADL-tvangslukning af profitable afdækningsben: 45–52 mio. USD i overskydende haircut den 10-10-2025 (X014).
  - Stablecoin-depeg (X048).
  - Likvidationssandsynlighed ved gearing: 5x-shorts over 30 dage har over 60 % (X011).

## 2. Persistens og prædiktion af funding

- Kun E40 (afhandling, BTC på Binance og Bybit) tester persistens uden for sample.
- E41 og E42 (praktikere) finder ingen retningsinformation i funding (R² ≈ 0; IC −0,005).
- Inan's SSRN-version kunne ikke åbnes.
- **Ingen uafhængig replikation og ingen tværsnit på tværs af perps i fagfællebedømt litteratur.** Hullet er uændret.

## 3. Basis og cash-and-carry kun i dislokationer

- De samme kilder peger samme vej:
  - E04: marginspidser og høj carry før crash.
  - X005 (JFM 2022): kvartalsvise cash-and-carry-muligheder især i dislokationer.
  - E06: perps dæmper ekstreme dislokationer.
- Det er konsistent, men alle er beskrivende eller brutto, undtagen E03.

## 4. Likvidationer, kaskader og varsling

- **Skalaen replikerer på tværs af børser og perioder:**
  - BitMEX før 2021: 3,51 % og 1,89 % af OI om dagen (X009). Over 425.000 hændelser, uger op til 1 mia. USD (X010).
  - Flere børser i maj 2021: 8,6 mia. USD på én dag (X011).
  - Hyperliquid og Binance i oktober 2025 (E16, X013, X014).
- **Varslingssignaler replikerer ikke** **[E22+]:**
  - X012 tester 7 kaskader (2022–2025). Intet signal virker i alle.
  - Det signal, der i sample fandtes i oktober 2025, var undtagelsen.
  - Kun en kompression af taker-flowets varians holder, og kun på populationsniveau.
- **Mekanismen:** liquidity-sektoren driver kaskaden (X013, E16), ikke en divergerende multiplikator.
  - 88 % af tvangssalget sker inden for 30 minutter.
  - 63 % absorberes uden for bogen.
- **Datakvalitet går igen i tre uafhængige kilder:**
  - Binances likvidationsdata for maj 2021 var forkerte (X011).
  - OI fejlrapporteres, og likvidationsbeskeder forsinkes (X015, 2023).
  - OI's publiceringstid er ikke verificerbar i offentlige arkiver (X038).

## 5. Kursadfærd efter tvangssalg (likvidationsreversal)

- **Stadig ikke dokumenteret.** Ingen kilde giver afkast efter en kaskade.
- Den indirekte evidens peger **imod** fuld reversal:
  - X016 (DeFi): en permanent prispåvirkning ud over den midlertidige.
  - X027 (Mt. Gox): springene giver varige kursændringer.
  - X010: kausaliteten er uafklaret.
- E16 viser, at spreads normaliseres hurtigt, mens dybden er lang tid om at komme igen. Det handler om likviditet, ikke
  om kurs.

## 6. Kortsigtet reversal

- **Replikerer stærkt:**
  - Samme fortegn i 2015–2019 (X020), 2017–2022 (X021), mere end 3.600 mønter (E14) og Fičura (E15).
  - Også i 2021–2026 på Binance (X022) og i hele historien 2013–2026 (X042).
- **Placeringen replikerer også:** effekten ligger altid i små, illikvide mønter eller par med lav aktivitet (X020, X021,
  E14, E15).
- **Netto:**
  - X022 **[E22+, NETTO]**: statistisk signifikant i 90 % af 183 Binance-par, men bruttokanten (1,3 bp) er under
    omkostningen (5 bp).
  - X042 **[E22+, NETTO]**: decilpræmien på 27,5 % om ugen forsvinder blandt mønter, der handles. Kapaciteten er
    293.000 USD.
  - X023 påstår robusthed over for omkostninger uden tal.
  - Samlet: **reversal replikerer som statistik og fejler konsistent som nettohandel i likvide mønter.**

## 7. Momentum og trend: modstridende

- **For:**
  - E09 og E10 (RFS/JF; data før 2019).
  - X065 (faktormomentum 2014–2022).
  - E12 (TSMOM 2020–25, uden omkostninger).
  - X069 (regler slår buy-and-hold uden for sample efter omkostninger, mest risikojusteret).
- **Imod:**
  - E11 (ingen momentum 2014–18).
  - E22 (forsvinder efter korrektion for overlevelse).
  - X067 **[E22+]**: ingen momentum blandt overlevende 2017–2024, og plain momentum afhænger af trimning.
  - X068: data-snooping-robust i sample, men **ingen BTC-forudsigelighed uden for sample**.
  - X066 **[E22+, NETTO]**: den publicerede CTREND-faktor falder fra Sharpe 2,08 til 0,01. Nettoafkastet bliver −0,87 %
    om ugen efter korrektion af look-ahead og regnskab.
- **Direkte modsigelse:** X068 og X069 er uenige om BTC uden for sample (tekniske regler). Periode og regelmængde er
  forskellige (X069's periode er UNKNOWN).
- **Mønstret:** de positive fund ligger i tidlige data, brede universer eller risikojusterede mål. De negative ligger i
  korrigerede, overlevelsesbevidste eller nyere data.
- **Konklusion: momentum replikerer ikke robust som nettofordel i likvide mønter efter 2022.** Det stemmer med
  `RESULTS_tsmom_v1.md` (FAIL) og `studies/DONCHIAN_POWER_P1_2026-11-06.md` (INSUFFICIENT POWER).

## 8. ML og tværsnitsanomalier

- Bruttopræmier replikerer på tværs af datasæt:
  - X070 (ML).
  - X071 (Sharpe over 1 uden for sample, 2017–2023).
  - X072 (cirka 130 bp om ugen, anchoring).
  - E02 (63 af 170 prædiktorer, men alle forklaret af basis og pris-volumen).
- Nettoversionen afhænger af illikvide mønter:
  - X070: alfa i svært handlelige mønter.
  - X071: illikviditet holder anomalierne i live.
  - E01: mest ikke handlelige.
- **X066 er en advarsel:** en publiceret ugentlig kryptofaktor kollapsede ved kodeaudit. X072's 130 bp er brutto og ikke
  auditeret.

## 9. Ordreflow og OFI

- **Den samtidige sammenhæng replikerer:** OFI eller trade-flow-ubalance forklarer kursændringen lineært på BitMEX
  (X026). Det svarer til aktielitteraturen.
- **Prædiktion:**
  - Mt. Gox: OFI forudsiger spring (X027).
  - Binance 2022–2025: ensartede SHAP-former på tværs af mønter (X024).
  - Binance 6 perps: ubalancen ved kvartersåbningen forudsiger 4–12 timers afkast (E19).
  - Roll og VPIN forudsiger (E18).
- **Netto [E22+]:**
  - X024's taker-test for BTC: 0,13 mod buy-and-hold 0,83. Små mønter og en enkelt crash-dag dominerer.
  - X025 (live-eksperiment): maker-fills udvælges ugunstigt, og gængse maker-strategier er stærkt urentable.
  - Samlet: informationen i ordreflowet replikerer, men **BTC-monetiseringen gør ikke**, og den er ikke latensjusteret.

## 10. Intradagmønstre

- **Replikerer på tværs af perioder:**
  - Mønstre for time, dag og inden for timen før 2018 (X030) og 2017–2021 (X031).
  - Perps (X005, periode UNKNOWN) og Binance-perps (E19, udgivet 2026, periode UNKNOWN).
- X031: mønstrene **bliver stærkere over tid** og hænger sammen med fundingtidspunkter (kvalitativt).
- X036: Binances USDT-perp er centrum for volatilitetsoverførslen.
- Ingen kilde giver nettoøkonomi.

## 11. Omkostninger, gebyrer og fragmentering

- **Konsistent:**
  - Spreads på cirka 3 bp på USD-spot (X032).
  - Likviditeten drives af volatilitet og volumen (X033, E17).
  - Fragmentering koster også små handler (X035).
  - Kvadratrodsloven for prispåvirkning (X028).
- X034 **[E22+]**: nul gebyrer på Binance (juli 2022) **øgede** den samlede omkostning, fordi spreads voksede og dybden
  faldt. Gebyrsatsen alene er en dårlig omkostningsproxy. Det bakker lab'ets målte spread og dybde op
  (`studies/COSTS_2026-10-24.md`).

## 12. Arbitrage på tværs af børser

- **Gab replikerer:**
  - E30 (2017–18): store og tilbagevendende gab.
  - X063: halveringstid 1 dag, standardafvigelse 3,9 %.
  - X059 (2013–2024): gab findes stadig.
- **Udnyttelsen modsiges af nyere data:**
  - X058 (JFM 2023): siden april 2018 kan gabene næppe udnyttes.
  - X064: gevinsten går til få dygtige aktører.
  - X059 **[E22+]**: gab varer længere, når den risikable børs er dyr. Gabet er altså delvis en præmie for
    modpartsrisiko (FTX-typen) og ikke gratis.
  - X037: gas-omkostninger forklarer vedvarende afvigelser mellem CEX og DEX.
- Det stemmer med `RESULTS_arb_v1.md` (0 muligheder netto).

## 13. Kimchi-præmien

- **Eksistensen replikerer:**
  - 4,73 % i gennemsnit 2016–2018 (E31).
  - Top på 20,8 % i 2021 (E32).
  - Langsigtet niveau på 1,24 % (X062). Niveauet er altså faldet markant.
- **Forklaringen er modstridende:**
  - Friktion og kapitalkontrol: E31, E32 og X062. Arbitrage kun uden for et gebyrbånd.
  - Risiko: E33.
  - Spekulation: X060, som X061 afviser (ikke robust over tid).
  - X063 forbinder variabiliteten med kapitalkontrol.
- **Netto:** ingen kilde, og ingen data efter 2022 er verificeret. N4 kan kun spejle niveauet og båndet.

## 14. Stablecoin-udstedelse og BTC-kurs: modstridende og afhængigt af horisont

- **Positiv kortsigtet reaktion:**
  - X044: inden for 24 timer omkring udstedelsen, efter en uges fald.
  - X051: 5–30 minutter efter mint, aftagende efter 60 minutter.
  - X045: timerne omkring store overførsler.
  - E26: Tether-købte opsving i 2017.
- **Ingen effekt eller omvendt kausalitet:**
  - X047: ingen effekt på efterfølgende BTC-afkast, kun på volumen.
  - X046: udstedelsen reagerer på kursen.
- **Fortolkning:** kilderne er ikke nødvendigvis i strid. Effekten lever på minutter eller timer og forsvinder på dag-
  og VAR-horisont. Mønstret "udstedelse efter fald" (X044, E26) går igen.
- Alle data er fra før 2021. **Ingen kilde efter 2022, ingen nettoøkonomi.**

## 15. Børsstrømme og hvaler

- Netto-indstrømning til børser forudsiger:
  - BTC: intet (E24).
  - ETH: negativt (E24).
  - Reserveændringer: negativt (E25).
  - Hvalsmitte efter 6–24 timer (X050).
- X049 advarer om, at 90 % af on-chain-volumen ikke er økonomisk meningsfuld.
- Delvis replikation af fortegnet, ingen størrelser og intet netto. Vendorafhængig adresseklassificering.

## 16. Listningsafkast

- **Kortsigtet positivt replikerer:**
  - 5,7 % på dagen og 9,2 % i vinduet [−3,+3] (E20).
  - 6,51 % og 9,97 % (X040).
  - Cirka 2,2–2,35 % og 9,5 % (X039, 2020–21).
- **Ikke uafhængigt:** E20 og X040 deler forfatter (Ante) og periode. X039 er et speciale.
- Afkastet er **positivt før og negativt efter** listningsdagen (X039), og det varierer stærkt mellem børser (E20, X040:
  op til 34 % mod ubetydeligt).
- **Ingen fagfællebedømt kilde efter 2022 og intet Upbit-specifikt.** Afnoteringsstudier er ikke verificeret.

## 17. Overlevelse og handlelighed

- **Replikerer konsistent:**
  - E22: overlevelsesbias på 62 % p.a. ligevægtet.
  - X042: papirpræmien forsvinder blandt handlede aktiver.
  - X067: momentum forsvinder blandt overlevende.
  - X066: korrektioner af look-ahead fjerner alfa.
  - X038: et revideret punkt-i-tid-arkiv giver positiv IC, men negativ netto-Sharpe.
- **Det er den mest konsistente fællesnævner i den nye evidens efter 2022:** fund i brede eller historiske universer
  overlever ikke, når handlelighed, punkt-i-tid-data og omkostninger håndhæves.

## 18. Implicit volatilitet og VRP

- **IV indeholder information:**
  - IV slår HAR på 7–15 dage (X055).
  - OTM-handel bærer retningsinformation (E28).
  - Jump-præmier forudsiger carry og delta-hedget P&L (X007, uden tal).
  - Skew følger sentiment (X057).
- **VRP-størrelsen er stadig ikke verificeret:**
  - E27 siger kun "højere end S&P 500".
  - Alexander & Imeraj (VIX) gav 403.
  - E44 advarer om, at lav optionslikviditet forvrænger IV.
- Ingen nettokilde.

## 19. Prognose af realiseret volatilitet

- Replikerer (E36–E39 og E44). X055 tilføjer, at en kombination af IV og HAR er bedst på alle horisonter.
- Det er prognosekvalitet, ikke handelsfordel.

## 20. Prispåvirkning fra DeFi-likvidationer

- Mekanismen replikerer på Compound, Aave, MakerDAO og dYdX:
  - Midlertidig og permanent prispåvirkning (X016).
  - Auktionsdesign dæmper den (X017).
  - Designs, der sælger for meget sikkerhed (X018).
  - Stor følsomhed over for små kursfald (X019).
- MEV-værdien tilfalder få aktører (X052).
- Alt er fra før 2022 og NOT_AVAILABLE for lab'et.

---

## Tværgående konklusioner

1. **Evidens efter 2022 med omkostninger (13 X-kilder sammenligner selv med omkostninger):**
   - Negative eller betingede: X022, X038, X042, X058, X064, X066, X025 (kvalitativ), X024 (BTC) og X070 (kun
     illikvide).
   - De eneste positive påstande er X069 (risikojusteret, ingen størrelse) og X023 (ingen tal).
   - **Ingen ny fagfællebedømt kilde viser en nettofordel efter 2022 i et likvidt univers.** Konklusionen i
     `research_gaps.md` A1 står ved magt.
2. **Gentagne modsigelser:**
   - Momentum: E09, E10, X065 og X069 mod E11, E22, X066, X067 og X068.
   - Stablecoin-effekt: X044, X051 og E26 mod X046 og X047.
   - Forklaringen på kimchi: X060 mod X061, og E31 mod E33.
   - Arbitrage, der kan udnyttes: E30 mod X058.
3. **Effekter aftager over tid:** carry (E03, E08, X001), arbitrage (X058), kimchi-niveauet (E31 4,73 % mod X062 1,24 %) og
   mobilitetsasymmetrien (X042, −70 %).
4. **Datakvalitet er en selvstændig, replikeret risiko:** wash trading (E23), forkerte likvidationsfeeds (X011),
   fejlrapporteret OI (X015) og huller i offentlige arkiver (X038).
5. **Stadig åbne huller:**
   - Funding-prædiktion på tværs af perps (fagfællebedømt).
   - Afkast efter kaskader.
   - Tick size.
   - VRP-størrelse.
   - Upbit-listninger og afnoteringer.
   - Kimchi efter 2022.
