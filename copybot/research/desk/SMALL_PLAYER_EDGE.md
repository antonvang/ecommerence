# Hvor kan en LILLE aktør have en varig, lovlig fordel? (litteraturgennemgang, 2026-11-06)

**Kun litteratur.** Der er ikke hentet markedsdata. Der er ikke kaldt nogen børs eller API, og der er ikke oprettet konti
eller logget ind. Alle 49 kilder er åbnet i denne session (abstractside, dokumentationsside eller PDF-tekst). URL og dato
står i `small_player_registry.json` (felterne `url_opened` og `date_opened`). Tal er kun gengivet, når de står i den åbnede
tekst. Ellers står der UNKNOWN. Citater er højst ca. 15 ord og står kun i registret, når teksten er ordret.

Henvisninger til `evidence_registry.json` (E01, E03, E08 og E34) er interne krydshenvisninger. De er ikke genåbnet her.

**Prognosemarkeder er kun en forskningskategori.** Der oprettes ingen konti, der handles ikke, og alders- og
jurisdiktionsregler omgås ikke. Platformenes adgangsregler står som begrænsninger (S011, S012). `pm_lp` er ikke læst
eller rørt.

**Datagates for alt, der foreslås målt:**
- ingen forespørgsler på historiske markedsdata før 2026-11-14;
- ingen COIN-M før 2026-11-28;
- aldrig 2024-holdout;
- nye eksterne værter kræver host-gate-tjek i PROTOCOL_V3;
- api.upbit.com er forbudt, bortset fra N4.

Litteratur med 2024 i sit sample (fx S027) citeres kun som litteratur. Lab'et må aldrig replikere den på egne 2024-data.

**Klassifikation af fordele (direktørtillæg).** Hver vinkel får én af tre klasser:
- **(1) DOKUMENTERET:** en økonomisk fordel efter gebyr, spread og funding, med kilde.
- **(2) TEORETISK:** kun en mulig fordel for lille kapital. Effekten er brutto, eller nettoeffekten er ikke vist.
- **(3) FORSVINDER:** fordelen forsvinder efter gebyrer, spread eller adgangsbegrænsninger.

---

## Resumé

### Top 5 vinkler, rangeret efter evidens × gennemførlighed for en lille aktør

| # | Vinkel | Evidens | Klasse | Kort begrundelse |
|---|---|---|---|---|
| 1 | **Prognosemarkeder: vær den tålmodige side, undgå longshots** | moderat | (1) smalt, ellers (2) | S001: på Kalshi 2021–apr 2025 tabte Makers −9,64 % og Takers −31,46 % efter gebyr. Makers, der købte ≥50c, tjente +2,6 %. Kontrakter <10c tabte >60 %. S002 finder samme mønster på Polymarket brutto, men fortegnet er ustabilt. |
| 2 | **Betalt for tålmodighed: likviditet i tynde ordrebøger (ikke AMM)** | moderat for mekanismen, svag for netto | (2); passiv AMM-LP er (3) | S018: reversal-afkast (proxy for likviditetsforsyning) ligger i de mindst handlede par, men vægtet efter værdi er intet signifikant netto. S009 (blog): Polymarket-makers har positive markouts i alle decilgrupper. S032/S033: passive AMM-LP'er taber til adverse selection. |
| 3 | **Langsomme, kalenderlagte udbudschok: unlocks, listninger, airdrops** | svag (praktikere med interessekonflikt) | (2) | S026: unge tokens faldt i median −16,02 % mod størrelsesmatchede peers måneden efter et unlock (n=77). Modne tokens: −2,57 %, ingen klar effekt. S025: fald starter ca. 30 dage før store unlocks. Horisonten er dage til uger, så latency betyder ikke noget. |
| 4 | **Vær ikke opmærksomhedskøberen, og test om man kan fade** | stærk for "køberen taber", svag for en handlebar fade | (2), (3) hvor short ikke kan lade sig gøre | S045: 5-dages abnormt afkast efter Robinhood-herding var −3 % (−6 % ved ekstrem herding). S042: efter pumps lå prisen −38 til −41 % lavere. S041 (JFQA): formue flyttes fra outsidere til insidere. S044: retail handler momentum i krypto. |
| 5 | **Kapacitetsbegrænsede anomalier i mellemlikvide coins med lav omsætning** | svag i krypto | (3) for mikro-caps, (2) for mellemlikvide med lav omsætning | S020 (AQR): kortsigtet reversal er den mest kapacitetsbegrænsede faktor, også for store fonde (aktier: >$9 mia. US). S022: anomalier, der er svære at arbitragere, forfalder mindre efter publicering. S018 og E01: i krypto ligger effekten i mikro-caps, hvor spreadet æder den. |

**Den ærlige konklusion.** Kun én kilde (S001) dokumenterer et positivt nettoafkast for en klart defineret adfærd:
Kalshi-makers, der købte ≥50c. Afkastet er lille (+2,6 %), og det stammer fra et gebyrregime, der er ændret siden
(Kalshi tager gebyr af makers efter april 2025). Alle andre "små aktør"-fordele er klasse (2) eller (3).

Det stærkeste og mest robuste fund er negativt. Den lille aktørs fordel ligger i høj grad i at **undgå** at være:
- den utålmodige taker,
- longshot-køberen,
- opmærksomhedskøberen,
- den, der vinder backtesten.

Det er ikke en kilde til alpha i sig selv.

### De 3 mest almindelige fælder

1. **Brutto er ikke netto, og gebyrstigen går imod den lille.**
   - Basistrinnet koster 4,5/1,5 bp (taker/maker) på Hyperliquid (S037) og 5/2 bp på Binance USDⓈ-M (S038).
   - Store konti betaler 0 bp som maker eller får rebate (−0,1 til −0,3 bp, kun ved >0,5–3 % af den samlede
     maker-volumen).
   - Kalshi-takers tabte −31,46 % (S001). Reversal i små coins overlever ikke værdivægtning netto (S018).
   - E03: retail-omkostninger giver Sharpe 1,8 mod 3,5 for en market maker uden gebyr.
2. **Overfitting og publikationsforfald.**
   - Afkastet efter publicering falder ca. 35 % (S022).
   - Nye faktorer bør have t > 3 (S023).
   - Backtest-Sharpe forklarer under 2,5 % af variationen uden for sample (R² < 0,025) på 888 retail-algoritmer (S024).
3. **At være den utålmodige eller opmærksomhedsdrevne modpart, plus haleristici, som ingen backtest viser.**
   - Basisrater: 69,2 % af retail-konti på Polymarket ligger under break-even, mens bots tjente $246,8 mio. (S010).
     97 % af brasilianske daytradere tabte (S048). Under 1 % af taiwanske daytradere er forudsigeligt profitable (S047).
     Et flertal af krypto-app-brugere tabte på bitcoin (S046).
   - Haleristici: resolution-angreb (S015, $7 mio.-marked uden refusion), market maker-aftaler med lån og call-optioner i
     små tokens (S028), og at primærmarkedsarbitrage er lukket land (S030: 6 agenter pr. måned hos Tether).

---

## Vinkel 1: Kapacitetsbegrænset alpha

**For.**
- S019 (AER 2004): fondsafkast falder med fondsstørrelse, mest i illikvide segmenter. Skalaulemper findes.
- S022: anomalier i porteføljer med høj idiosynkratisk risiko (dyre at arbitragere) forfalder mindre efter publicering.
- S018: likviditetsforsyning betaler mest i små, volatile og illikvide par. Lige vægtet giver reversal 1,26 %/dag ved lav
  volumen mod 0,54 % ved høj (brutto). Efter et fast gebyr på 30/40 bp er den stadig 1,68 %/dag.

**Imod.**
- S018: værdivægtet er ingen strategi positiv og signifikant netto, og alphaerne mister signifikans. Det antagne gebyr på
  30/40 bp er sandsynligvis for lavt for mikro-caps, hvor halvspreadet kan være større. Det er min vurdering, ikke kildens.
- S020 (AQR): reelle institutionelle omkostninger er under en tiendedel af de akademiske estimater. Størrelse, værdi og
  momentum skalerer til $52–103 mia. Kun kortsigtet reversal er hårdt begrænset (ca. $9 mia. US). Store aktører er altså
  billigere, end man tror.
- S021: kun strategier med under 50 % månedlig omsætning overlever omkostninger.
- E01 (ikke genåbnet): størrelses- og volumenanomalier i krypto stammer fra mikro-caps uden økonomisk betydning.

**Vurdering.**
- **Klasse (3)** for mikro-cap-reversal. **Klasse (2)** for designs med lav omsætning i mellemlikvide coins.
- Mulig størrelse ved $1k–50k: UNKNOWN. Ingen kilde måler netto ved realistiske retail-spreads.
- Kapacitet: meget lille, fordi effekten ligger hvor dybden er lav.
- Risici: spread og slippage, wash-volumen (E23: >70 % på uregulerede børser), delisting og overlevelsesbias.
- Data: reelle bid/ask- og dybdeserier for små par. Kan samles fremad (`fwd_tob_universe`, `bn_depth500_diag`).
  Historik kan først hentes efter 2026-11-14.
- **Falsifikation:** en præregistreret papirbog med fremadrettet top-of-book. Hvis lige vægtet reversal i
  lavvolumen-par efter faktisk halvspread og takergebyr er ≤ 0 over ≥ 60 handelsdage, er vinklen død.

## Vinkel 2: Institutionelle begrænsninger, kalenderstrømme og tvungne sælgere

**For.**
- S025 (Keyrock, market maker): ca. 90 % af 16.000+ unlocks i 40 tokens viser negativt prispres. Fald starter ca. 30 dage
  før store unlocks og stabiliserer sig ca. 14 dage efter. Team-unlocks er værst (ca. −25 %, vinduet er uklart).
  Investor-unlocks er "kontrollerede", fordi de afdækkes eller sælges OTC.
- S026 (Tokenomist, datasælger): unge tokens −16,02 % i median mod peers (n=77), modne −2,57 % (n=144).
- S027 (RockawayX, VC): Binance-listninger i 2024 gav en kortvarig stigning på dag 1–2, der var væk inden dag 7.
  Bybit viste et run-up før listningen.
- S035: op til 66 % af airdroppede tokens sælges hurtigt.

**Imod.**
- Ingen af kilderne er fagfællebedømte, og ingen tester signifikans.
- S025 og S026 har direkte interessekonflikt: de sælger market making eller data til netop disse begivenheder.
- S025 siger selv, at sofistikerede modtagere afdækker på forhånd. Fordelen er altså allerede delvist høstet af store
  aktører.
- At shorte unge tokens kræver en perp-listning og funding, som kan være ekstrem.
- S028: market maker-aftaler med lån og call-optioner kan dominere prisdannelsen i små tokens.
- Ekspirering af optioner og rebalancering af indeks: ingen åbnet primærkilde. Evidens: **ingen**.
- Funding-afregningstider: se E-registrets Quarter-Hour-kilde (ikke genåbnet).

**Vurdering.**
- **Klasse (2).** Evidens: svag.
- Størrelse: UNKNOWN netto. Kapacitet: lille, men horisonten er dage til uger, så den lille aktør konkurrerer ikke på
  latency.
- Data: unlock-kalendere (ny ekstern vært, kræver host-gate-tjek: UNKNOWN), listningsdatoer (`cm_listing_catalog`,
  `dup_listing_collector`) og daglige priser og funding (fremad, AVAILABLE_FORWARD).
- **Falsifikation:** præregistrer de næste ≥ 30 store cliff-unlocks (≥ 1 % af cirkulerende udbud) i tokens med perp.
  Hvis relativt afkast mod størrelsesmatchede peers i [−30 d, 0] efter funding og gebyr ikke er < 0 med t > 2, er
  vinklen død. En ren dato-test kræver ingen historik før 11-14.

## Vinkel 3: Prognosemarkeder (kun forskning)

**For.**
- S001 (UCD, WP 2026) er den eneste kilde med nettotal for et klart defineret segment. Kalshi, >300.000 kontrakter:
  - gennemsnitligt afkast ca. −20 % før gebyr;
  - <10c taber >60 % efter gebyr;
  - Makers −9,64 % mod Takers −31,46 %;
  - Makers, der købte ≥50c, fik +2,6 %;
  - der er tegn på, at biasen aftager over tid.
- S013 (JPE 2010): favourite-longshot-bias skyldes misopfattelse af sandsynligheder (prospektteori). Det er en
  adfærdsmekanisme, som kan tale for, at biasen er holdbar.
- S002 (arXiv 2026, 588 mio. handler på Polymarket): køb <10c taber 19,3c pr. dollar, køb ≥90c tjener 0,83c (brutto).
- S003: politiske markeder er underconfident (prisen presses mod 50 %).
- S010: bots tjente $246,8 mio., mens 69,2 % af de menneskelige konti tabte.
- S009 (blog): maker-markouts er positive i alle decilgrupper. Det er markouts, ikke PnL.
- S008: Polymarket giver belønninger for hvilende, tosidede ordrer tæt på midten.

**Imod.**
- S002: når kontrakter grupperes pr. begivenhed, vender longshot-resultatet fortegn (+4,1c). I sport findes mønsteret ikke.
- Gebyrerne er ændret efter sample-perioden:
  - Kalshi tager gebyr af makers efter april 2025 (S001).
  - Polymarket har takergebyr i de fleste kategorier: feeRate 0,04–0,07 gange p(1−p), med 15–25 % rebate til makers
    (S007). I de hurtige kryptomarkeder er der takergebyr på op til ca. 3 % (S017).
- Professionelle market makers er på vej ind. Jump laver ifølge rapporter market making på Kalshi og Polymarket for
  egenkapital (S016). "Store firmaer gider ikke" holder altså ikke længere.
- Arbitrage på tværs af markeder: S005 finder afvigelser på 2–4 %, men "semantisk ikke-fungibilitet" betyder, at samme
  begivenhed afgøres forskelligt. S006 siger, at vinduerne lever sekunder til minutter. S004 anslår ca. $40 mio.
  udtrukket på Polymarket, men hvem der fik det, er UNKNOWN.
- Resolution- og oracle-risiko: S015 ($7 mio.-marked afgjort YES efter et påstået UMA-hvalangreb, ingen refusion).
- Metodefælde: S014 viser, at det offentlige feed giver forkert handelsretning i ca. 40 % af tilfældene. On-chain fills
  er nødvendige.

**Adgangsregler (begrænsninger, ikke noget, der skal omgås):**
- S011, Polymarket international: 7 sanktionerede regioner er blokeret. Ca. 37 jurisdiktioner er close-only, herunder
  US, UK, FR, DE, IT, PL, BE, AU og SG. Danmark er ikke på listen.
- S012, Kalshi: adgang uden for USA følger Member Agreement. Siden har ingen landeliste, og Danmark er ikke nævnt.
- Lab'et er under alle omstændigheder kun papir og forskning.

**Vurdering.**
- **Klasse (1)** kun for Kalshi-makers, der købte ≥50c, i 2021–apr 2025 under det gamle gebyrregime.
- **Klasse (2)** for resten: Polymarket-FLB brutto, makerbelønninger netto for adverse selection, og underconfidence i
  politiske markeder.
- **Klasse (3)** for arbitrage på tværs af platforme og taker- og latencystrategier i hurtige markeder.
- Evidens: moderat. Størrelse: få procent pr. kontrakt-dollar i favoritsegmentet. Kapacitet: lille og konkurreres nu af
  professionelle.
- Data: Polymarket-bøger findes (`pm_lp_collector`, `pm_scanner_detectors`), men brugen er underlagt pm_lp-holdout-reglerne
  og er ikke læst her. On-chain fills og resolution-log er AVAILABLE_FORWARD. Kalshi er en ny vært: UNKNOWN, kræver
  host-gate-tjek.
- **Falsifikation:** se tabellen nedenfor.

| Klasse (2)-hypotese | Hypotesen er død, hvis en papirbog med on-chain fills (ikke feed), efter faktisk feeRate og med optjent rebate og reward viser ... |
|---|---|
| Hvilende køb af YES/NO ≥ 0,50 i ikke-sportsmarkeder | gennemsnitligt nettoafkast pr. dollar ≤ 0 over ≥ 200 afgjorte kontrakter (klyngeinddelt pr. begivenhed) |
| Favoritter vinder oftere, end prisen siger | at kalibreringen for p ≥ 0,5 ikke ligger over 45-graderslinjen |

## Vinkel 4: Likviditetsforsyning, belønningsprogrammer og airdrops

**For.**
- S001 og S009: makers i prognosemarkeder klarer sig bedre end takers.
- S008 og S007: Polymarket betaler belønninger og rebates. Begge deles pro rata mellem makers pr. marked.
- S034: simple LP-strategier er profitable i puljer med næsten ingen volatilitet, men afkastet er beskedent.

**Imod.**
- S032: fees på $199,3 mio. mod impermanent loss på $260,1 mio. i 17 Uniswap v3-puljer. LP'erne endte $60,8 mio. dårligere
  end ved at holde tokens.
- S033: LVR er en strukturel adverse selection-omkostning for passive AMM-LP'er.
- S039: CEX-DEX-arbitrage gav $233,8 mio. til 19 searchers, og 3 af dem tog ca. 75 %. Det er et latency- og
  builder-spil, som en lille aktør ikke kan vinde.
- S037 og S038: gebyrstigen favoriserer volumen. Rebates kræver >0,5 % af den samlede maker-volumen.
- Airdrop-farming på flere konti (Sybil) bryder platformsregler og er udelukket (S036). Økonomien for én ærlig konto er
  UNKNOWN.

**Vurdering.**
- **Klasse (3)** for passiv AMM-LP, MEV og CEX-rebate-jagt.
- **Klasse (2)** for makerbelønninger i prognosemarkeder og LP i stablecoin-puljer.
- Evidens: moderat imod, svag for.
- Data: AMM-puljetilstand on-chain (ny vært, UNKNOWN) og pm-bøger (se vinkel 3).
- **Falsifikation:** hvis en simuleret maker-bog (papir, kun egne hvilende ordrer) har markout efter 10 minutter plus
  reward minus gebyr ≤ 0 over ≥ 1.000 simulerede fills, er vinklen død.

## Vinkel 5: Langsomme nicher (stablecoin-depegs, tværbørsafvigelser, governance)

**For.**
- S029 (JFE 2020): store, tilbagevendende arbitragegab mellem lande, fordi kapitalkontrol begrænser arbitragekapital.
- S031: genoprettelse af et peg sker hovedsageligt via primærmarkedet. Over en ikke-lineær tærskel går genoprettelsen
  langt langsommere.

**Imod.**
- S030: primær arbitrage er centraliseret (Tether: 6 agenter pr. måned). Den lille aktør kan kun købe rabatten i
  sekundærmarkedet. Det er et retningsvæddemål på indløsning, ikke arbitrage.
- S029: gabene kræver adgang til fiat i flere jurisdiktioner, og Upbit er forbudt uden for N4.
- E34 (ikke genåbnet): afregningstiden sætter grænserne for arbitrage.
- Governance-begivenheder: ingen kilde blev åbnet (403). Evidens: **ingen** i denne gennemgang.

**Vurdering.**
- **Klasse (3)** for tværbørsarbitrage og primær stablecoin-arbitrage. **Klasse (2)** for "køb depeg-rabat".
- Evidens: moderat for, at gabene findes. Ingen for netto ved lille størrelse.
- Data: `fwd_stablecoin_supply` og peg-kurser fremad (AVAILABLE_FORWARD). Depegs er sjældne, så N bliver lille.
- **Falsifikation:** præregistrer en regel ("køb ved < 0,98 for top-2 fiat-stablecoins, hold til 0,995"). Hvis de første
  ≥ 5 hændelser ikke giver positivt afkast efter spread, eller hvis én hændelse bryder tærsklen (S031), er vinklen død.
  Ingen historisk test før 11-14.

## Vinkel 6: Alpha-forfald og trængsel

**For og imod.**
- S022: afkastet falder ca. 35 % efter publicering og ca. 10 % af statistisk bias. Forfaldet er mindre, hvor arbitrage er
  dyr.
- S023: hurdle t > 3.
- S024: backtest-Sharpe er næsten uden prædiktiv værdi (R² < 0,025), og flere backtests giver et større gab.
- E08 (ikke genåbnet): carry-Sharpe faldt til negativ i 2025.
- Krypto-specifikt forfald efter publicering blev ikke fundet i en åbnet kilde. Evidens for krypto: **svag/ingen direkte**.

**Implikation for en lille aktør.** Publicerede krypto-anomalier skal antages delvist høstet. En lille aktørs eneste
strukturelle fordel er de anomalier, der er for dyre eller for små til at arbitragere. Netop dem rammer fælde 1 (spread).

**Vurdering.**
- **Klasse:** ikke en fordel. Det er en diskonteringsfaktor på alle andre vinkler.
- **Falsifikation for den sidste påstand:** hvis forward-afkast i lab'ets papirbøger for publicerede signaler ikke er
  lavere end in-sample-estimaterne, kan forfaldsantagelsen lempes.

## Vinkel 7: Adfærdsmæssige fordele

**For.**
- S045: −3 % og −6 % over 5 dage efter herding.
- S042: pumps stiger 2,4–2,6 % i top-75-coins mod 14–16 % i obskure coins. Prisen lå −38 til −41 % lavere efter pumpet.
  Profitabiliteten faldt 50–60 % på seks måneder.
- S041 (JFQA 2025): formue flyttes fra outsidere til insidere. Deltagelse passer med spillepræferencer.
- S044 (JFE 2024): retail handler momentum i krypto, men er kontrære i aktier.
- S043 (JBEF 2024): abnorm Google-søgning følges af højere afkast, kun delvist reverteret, og stærkere i større coins.
- S040 (USENIX 2019): en model, der forudsiger pumps, gav op til 60 % på ~2,5 måneder ved små retail-beløb.

**Imod.**
- S040 og S042 er fra 2018–19, og effekten faldt allerede dengang.
- At handle sammen med manipulation er etisk og juridisk problematisk og er ikke en lab-strategi.
- At fade kræver short: perp-adgang og funding, og at gå short i obskure coins er ofte umuligt.
- S043 peger i modsat retning af fade-hypotesen (opmærksomhed giver vedvarende stigning).
- Ingen kilde tester netto efter omkostninger.

**Vurdering.**
- **Klasse (2)** for at fade spikes i perp-listede coins. **Klasse (3)** for obskure coins (ingen short-adgang).
- Evidens: stærk for, at opmærksomhedskøberen taber. Svag for en handlebar modstrategi.
- Data: `bn_abnormal_move` og `news_watch` fremad (AVAILABLE_FORWARD). Google Trends er en ny vært (UNKNOWN).
- **Falsifikation:** præregistrer "short perp 1 time efter abnorm stigning > X σ uden nyhed, hold 48 timer". Hvis det
  efter funding og takergebyr giver ≤ 0 over ≥ 50 hændelser, er vinklen død.

## Vinkel 8: Hvad der faktisk fejler

- Basisrater: S047 (<1 % netto forudsigeligt profitable), S048 (97 % tabte), S046 (et flertal af app-brugere tabte på
  bitcoin) og S010 (69,2 % af retail på Polymarket).
- Omkostninger: S037 og S038 (gebyrstigen). E03 (ikke genåbnet): Sharpe 1,8 under retail-omkostninger mod 3,5 for en
  market maker uden gebyr.
- Overfitting: S023 og S024.
- Modparts- og infrastrukturrisiko: S015 (resolution), S028 (market maker-aftaler) og S049 (Man skrinlagde oprindeligt
  krypto, fordi børser og AML/KYC var utilstrækkelige).
- Skat og jura (generelt): skattebehandling og rapporteringskrav for kryptogevinster og prognosemarkeder varierer mellem
  jurisdiktioner og kan æde en smal nettofordel. Ingen kilde blev åbnet om dette. Det er en åben post, ikke rådgivning.

**Hvorfor fordele forsvinder** (syntese af kilderne ovenfor):
1. Bruttoeffekten ligger hvor spreadet er størst (S018, E01).
2. Publicering og professionelle aktører høster den (S022, S016).
3. Platformen ændrer gebyrer eller regler (S007, S017; S001 om Kalshi-gebyr for makers).
4. Den lille aktør er strukturelt taker og betaler basisgebyr (S037, S038).

## "Hvad de store firmaer siger, de ikke gør"

**Ingen åbnet kilde indeholder en eksplicit liste fra et stort firma over markeder, det fravælger, fordi de er for små.**
Evidensen er indirekte:

- **Man AHL (S049, CIO, 2024).** Firmaet handler >400 "eksotiske" markeder, men kræver daglig handlebarhed.
  - Catastrophe bonds blev fravalgt til trend-following på grund af sporadisk handel og brede spreads.
  - Krypto blev oprindeligt skrinlagt, fordi børser og AML/KYC var utilstrækkelige. Det betyder, at store firmaer
    fravælger venues og markeder, der ikke opfylder institutionel drift og compliance.
  - Det er også de venues, hvor en lille aktør bærer mest modpartsrisiko.
- **AQR (S020).** Kortsigtet reversal er den faktor, der er mest begrænset af handelsomkostninger. For alt andet har store
  aktører lavere omkostninger end akademiske modeller. Store firmaer kan altså skalere det meste, bortset fra
  højfrekvent likviditetsforsyning.
- **Chen m.fl. (S019).** Store fonde underpræsterer mest i illikvide aktiver. Det er en skalaulempe, ikke et valg.
- **Jump (S016).** Trak sig fra krypto efter Terra, men går nu ind i market making på prognosemarkeder. Nichen "for lille
  til de store" lukker sig, når volumen vokser.
- **MEV og stablecoins (S039, S030).** Hvor fordelen kræver integration med block-builders eller adgang til
  primærmarkedet, tager få store aktører det hele. Her er den lille aktør udelukket.
- **Market makers i små tokens (S028).** De store er til stede i long-tail-tokens, men via aftaler med lån og call-optioner,
  der giver andre incitamenter end ren quoting.

**Samlet læsning.** Store firmaer undgår markeder uden daglig likviditet, venues med svag compliance og strategier, hvis
kapacitet er under deres mindste meningsfulde positionsstørrelse. Det sidste gælder mikro-cap-reversal og enkeltkontrakter
på prognosemarkeder, som de kun handler, når volumen er stor nok.

Det første og andet område er netop der, hvor den lille aktør bærer mest risiko (modpart, resolution, spread). Den eneste
"rene" niche er derfor den tredje: små, lavfrekvente beslutninger med horisont på dage, hvor man er den tålmodige side.

## Hvad lab'et konkret kan måle (inden for gates)

| Hypotese | Klasse nu | Data | Status |
|---|---|---|---|
| Hvilende favoritkøb (≥0,5) på prognosemarkeder netto efter feeRate og reward | (2) | pm-bøger og on-chain fills | AVAILABLE_FORWARD, men pm_lp-regler gælder: kræver separat godkendelse |
| Unlock-pres før store cliff-unlocks i perp-listede, unge tokens | (2) | unlock-kalender (ny vært) og priser/funding | UNKNOWN (host-gate) / AVAILABLE_FORWARD |
| Fade af abnorme stigninger uden nyhed i perp-listede coins | (2) | `bn_abnormal_move`, `news_watch` | AVAILABLE_FORWARD |
| Reversal i lavvolumen-par med reelt spread | (3) indtil modbevist | `fwd_tob_universe`, `bn_depth500_diag` | AVAILABLE_FORWARD; historik AVAILABLE_AFTER_2026-11-14 |
| Køb af depeg-rabat | (2) | `fwd_stablecoin_supply` og peg-kurser | AVAILABLE_FORWARD (sjældne hændelser) |

Alle forslag kræver en separat protokol eller godkendelse før måling. Denne fil aktiverer intet.
