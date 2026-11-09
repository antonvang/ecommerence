# Litteraturgennemgang, direktørordre 69 P2: regimer, likviditet, planlagte hændelser, overfitting og omkostninger

Skrevet 2026-11-09 ca. kl. 17:00 lokal (16:00 UTC) i dev-worktree. Ikke committet.

**Kun litteratur.** Ingen markedsdata, ingen børs-API, ingen kurser. lab.db er ikke åbnet. N4-filen og
`/home/anton/copybot-dev/quarantine/` er ikke læst. Web er kun brugt til papirer: arXiv, NBER, NY Fed, Fed Board,
IDEAS/EconPapers, forfatter- og universitetssider, AQR og Dagstuhl. SSRN er ikke forsøgt (403 i alle tidligere sessioner).
Blokerede sider står som UNVERIFIED. Der er ikke brugt omveje.

**Status-koder:**
- **VERIFIED:** jeg har læst selve teksten (PDF via `pdftotext` eller fuld HTML). Tal kommer fra teksten.
- **ABSTRACT:** kun abstract eller udvidet abstract er læst. Tal kommer kun fra abstractet.
- **UNVERIFIED:** siden var blokeret, eller der var intet abstract. Indhold kun fra søgeresumé eller fra almen viden.
  Bruges ikke som evidens.

Resuméerne er mine egne ord. Højst ét kort citat pr. kilde. En statistisk effekt er ikke en handelsfordel.

**Dubletter.** Jeg har først læst `evidence_registry.json` (E01–E44), `evidence_registry_ext.json` (X001–X075),
`LITERATURE_MAP.md`, `LITERATURE_MAP_EXT.md` og `studies/ONLINE_EDGES_2026-11-05.md`. Ingen af de nye kilder nedenfor står
i registrene. Fire står allerede andre steder i repoet:

| Kilde | Hvor den står i forvejen | Hvad der er nyt her |
|---|---|---|
| Makarov & Schoar (JFE 2020) | E30 og X049 i registrene | Ikke genåbnet. Kun en henvisning |
| McLean & Pontiff (JF 2016) | `ONLINE_EDGES` og `PROFIT_SEARCH` (faktor 0,65) | Arbejdspapiret er læst. Tallene afviger fra den publicerede version |
| Lucca & Moench, Kurov m.fl. | `ONLINE_EDGES` afsnit 13 | Lucca & Moench er læst i fuld tekst |
| Andersen m.fl. 2003, Benigno & Rosa 2023 | `US_MACRO_0830_DESIGN.md` afsnit 7 (begge ABSTRACT) | Benigno & Rosa er nu læst i fuld tekst (VERIFIED) |

## Optælling

| Emne | Studier | VERIFIED | ABSTRACT | UNVERIFIED |
|---|---|---|---|---|
| 1. Volatilitetsregimer og strukturbrud | 10 | 2 | 7 | 1 |
| 2. Likviditet og mikrostruktur | 7 | 1 | 5 | 1 |
| 3. Planlagte økonomiske hændelser | 8 | 2 | 5 | 1 |
| 4. Overfitting og multipel testning | 8 | 4 | 4 | 0 |
| 5. Realistiske omkostninger | 6 | 1 | 5 | 0 |
| **I alt** | **39** | **10** | **26** | **3** |

Negative resultater og fejlede replikationer: 15 af de 39 (markeret **NEG** i oversigterne).

---

## 1. Volatilitetsregimer og strukturbrud

### Oversigt

| # | Studie | Marked og periode | Hovedresultat | Netto/brutto | Status |
|---|---|---|---|---|---|
| L01 | Hamilton 1989 | US BNP, efterkrigstiden | Skjulte regimeskift i vækstraten kan estimeres | ikke relevant | ABSTRACT |
| L02 | Bai & Perron 1998 | metode | Test af antal og placering af flere brud | ikke relevant | ABSTRACT |
| L03 | Moreira & Muir 2017 | US-faktorer 1926–2015, FX-carry | Volatilitetsstyring giver stor alfa | brutto, siger robust over for omkostninger | VERIFIED |
| L04 | Cederburg m.fl. 2020 **NEG** | 103 US-aktiestrategier, 1926–2016 | Slår ikke den ustyrede version i realtid | brutto | VERIFIED |
| L05 | Liu, Tang & Zhou 2019 **NEG** | US-aktiemarkedet | Look-ahead i den gængse version; drawdown 68–93 % | brutto | ABSTRACT |
| L06 | Barroso & Detzel 2021 **NEG** | US-faktorer | Efter omkostninger: alfa ≈ 0 undtagen for markedet | netto | ABSTRACT |
| L07 | Thies & Molnár 2018 | BTC | Hyppige brud i middelafkast og volatilitet | ikke relevant | ABSTRACT |
| L08 | Koki, Leonardos & Piliouras 2020 | BTC, ETH, XRP | 4-tilstands HMM giver bedste 1-trins prognose | ingen handel | ABSTRACT |
| L09 | Koch, Jeleskovic & Younas 2024 **NEG** | BTC dagligt | MS-GARCH slår ikke stokastisk volatilitet; simpel GARCH kan vinde | ingen handel | ABSTRACT |
| L10 | Grobys, Kolari m.fl. 2025 | kryptomomentum 2016–2023, ugentligt | Volatilitetsstyring dæmper crash | UNKNOWN | UNVERIFIED |

### L01. Hamilton (1989), "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle"

- **Spørgsmål:** kan man estimere sjældne, skjulte skift i en tidsseries vækstrate?
- **Data:** amerikansk real-BNP efter krigen.
- **Metode:** Markov-regimeskift. Filtrering af de skjulte tilstande og maksimum likelihood.
- **Resultat:** skiftet fra vækst til fald går igen i hver konjunktur. En typisk recession giver et varigt fald på ca. 3 % i
  BNP-niveauet.
- **Begrænsninger:** abstractet nævner ingen. Modellen forudsætter, at antallet af tilstande er kendt.
- **Reproducerbarhed:** offentlige BNP-data. Ingen kode nævnt.
- **Copybot:** grundmetode for `families/drafts/fregime.json` og E39 (MS-GARCH). Metoden virker også 24/7, men krypto har
  kort historik og få regimeskift at estimere på.
- **Status:** ABSTRACT. Econometrica 57(2):357–384. https://econpapers.repec.org/RePEc:ecm:emetrp:v:57:y:1989:i:2:p:357-84

### L02. Bai & Perron (1998), "Estimating and Testing Linear Models with Multiple Structural Changes"

- **Spørgsmål:** hvordan tester og estimerer man flere ukendte brudpunkter i en regression?
- **Data:** ingen (teori og metode).
- **Metode:** asymptotisk teori. Test af l brud mod l+1 brud. Brudpunkter estimeres ét ad gangen. Tillader seriel
  korrelation og delvise brud.
- **Resultat:** konvergensrate og grænsefordeling for brudpunkterne. En "specifik-til-generel" procedure for antallet af
  brud.
- **Begrænsninger:** lineær model. Kræver nok observationer mellem brud.
- **Reproducerbarhed:** standardmetode. Bai & Perron (2003) beskriver beregningen. Ingen kode set her.
- **Copybot:** et formelt brudtest før man slår historik fra 2020–2021 sammen med 2023+. Relevant for R3 og alle
  backtests, der spænder over flere markedsfaser.
- **Status:** ABSTRACT. Econometrica 66(1):47–78. https://econpapers.repec.org/RePEc:ecm:emetrp:v:66:y:1998:i:1:p:47-78

### L03. Moreira & Muir (2017), "Volatility-Managed Portfolios"

- **Spørgsmål:** giver det højere Sharpe at skalere eksponeringen ned, når den nylige volatilitet er høj?
- **Data:** US-markedet og fem til seks aktiefaktorer (bl.a. værdi, momentum, profitabilitet) samt valuta-carry. Markedet
  fra 1926 til 2015.
- **Metode:** vægt = c / forrige måneds realiserede varians. Spanning-regression af den styrede faktor på den ustyrede.
- **Resultat (brutto, med omkostningstest):** markedet giver alfa på 4,86 % om året og ca. 25 % højere Sharpe end
  købe-og-hold. Nytten for en middel-varians-investor svarer til ca. 65 %. Forfatterne siger, at strategien overlever
  realistiske omkostninger og gearingsgrænser (deres tabel 4).
- **Begrænsninger:** konstanten c sættes med hele stikprøven. Forfatterne skriver, at den ikke påvirker Sharpe. Den
  påvirker dog gearing og drawdown (se L05). Alfa falder, når ombalanceringen sker sjældnere.
- **Reproducerbarhed:** offentlige faktordata (Ken French). Ingen kode i teksten.
- **Copybot:** `volatility_managed_exposure`, vol-target i `studies/DONCHIAN_POWER_P1_2026-11-06.md` og `../lab/risk.py`.
  Mekanismen kræver, at volatilitet stiger mere end forventet afkast. Det er ikke vist for krypto-perps.
- **Status:** VERIFIED (NBER WP 22208, fuld tekst). JF 72(4):1611–1644. https://www.nber.org/papers/w22208

### L04. Cederburg, O'Doherty, Wang & Yan (2020), "On the performance of volatility-managed portfolios" — NEG

- **Spørgsmål:** kan en investor i realtid høste gevinsten fra L03?
- **Data:** 103 US-aktiestrategier (9 faktorer og 94 anomalier). Fra 1926, 1963 eller 1967 til 2016.
- **Metode:** gentager L03's spanning-test. Bygger derefter realtidsporteføljer med kun data, der var kendt på
  tidspunktet. 10 års træning, udvidende vindue, gearingsgrænse 5.
- **Resultat (brutto):** in-sample har 77 af 103 positiv alfa, heraf 23 signifikant. I realtid slår kombinationen kun den
  ustyrede strategi i 45 af 103 tilfælde på Sharpe og 31 af 103 på sikkerhedsækvivalent. Signifikant bedre og signifikant
  værre er lige mange (7 mod 7). Årsagen er ustabile regressionskoefficienter over tid.
- **Begrænsninger:** handelsomkostninger er ikke modelleret. Efter omkostninger ville resultatet blive værre for
  volatilitetsstyringen, som handler mere.
- **Reproducerbarhed:** offentlige data (French, Hou-Xue-Zhang). Ingen kode nævnt.
- **Copybot:** en volatilitetsregel må kun bruge realtidsparametre. Den skal slå den ustyrede version direkte uden for
  sample, ikke kun i en spanning-regression.
- **Status:** VERIFIED (forfatterens PDF). JFE 138:95–117. https://www.lehigh.edu/~xuy219/research/COWY.pdf

### L05. Liu, Tang & Zhou (2019), "Volatility-Managed Portfolio: Does It Really Work?" — NEG

- **Spørgsmål:** holder L03 for markedet uden look-ahead?
- **Data:** US-aktiemarkedet. Perioden står ikke i abstractet.
- **Metode:** gentager strategien med en skaleringskonstant, der kun bruger fortidige data. Tester tre alternative
  volatilitetsregler.
- **Resultat (brutto):** maksimal drawdown bliver 68–93 % i næsten alle tilfælde. Strategien slår kun markedet under
  finanskrisen. De tre alternativer slår heller ikke markedet.
- **Begrænsninger:** kun abstract læst. Tallene er ikke kontrolleret mod teksten.
- **Reproducerbarhed:** offentlige data. Kode ukendt.
- **Copybot:** samme lektie som L04. En gearing, der er kalibreret på hele stikprøven, er en form for look-ahead.
- **Status:** ABSTRACT. JPM 46(1):38–51. https://profiles.wustl.edu/en/publications/volatility-managed-portfolio-does-it-really-work/

### L06. Barroso & Detzel (2021), "Do limits to arbitrage explain the benefits of volatility-managed portfolios?" — NEG

- **Spørgsmål:** overlever volatilitetsstyring handelsomkostninger og short-begrænsninger?
- **Data:** US-faktorer. Perioden står ikke i abstractet.
- **Metode:** fratrækker omkostninger og tester seks måder at sænke dem på.
- **Resultat (netto):** for andre faktorer end markedet giver volatilitetsstyring alfa omkring nul efter omkostninger og
  lavere Sharpe. Den styrede markedsportefølje beholder sin alfa. Den virker kun, når sentiment er højt.
- **Begrænsninger:** kun abstract læst. Omkostningsmodellen er ukendt for mig.
- **Reproducerbarhed:** ukendt.
- **Copybot:** det tætteste analog til "markedet" er BTC-eksponering. Volatilitetsstyring af long/short-bøger (f.eks.
  tværsnitsmomentum) bør regnes som død efter omkostninger, til lab'et selv viser andet.
- **Status:** ABSTRACT. JFE 140(3):744–767. https://econpapers.repec.org/RePEc:eee:jfinec:v:140:y:2021:i:3:p:744-767

### L07. Thies & Molnár (2018), "Bayesian change point analysis of Bitcoin returns"

- **Spørgsmål:** har BTC strukturbrud i middelafkast og volatilitet?
- **Data:** BTC-kurser. Perioden står ikke i abstractet.
- **Metode:** Bayesiansk change-point-model. Segmenter med ens egenskaber slås sammen til regimer.
- **Resultat:** brud er meget hyppige. Flere regimer har positivt middelafkast, ét har negativt. Det mest volatile regime
  er det eneste med negativt afkast.
- **Begrænsninger:** kun abstract. Et senere papir siger 48 brud og 7 regimer; det er ikke kontrolleret.
- **Reproducerbarhed:** offentlige kursdata. Kode ukendt.
- **Copybot:** backtests over 2020–2023 blander sandsynligvis flere regimer. PBO fanger ikke brud uden for stikprøven
  (se L33).
- **Status:** ABSTRACT. FRL 27:223–227. https://econpapers.repec.org/RePEc:eee:finlet:v:27:y:2018:i:c:p:223-227

### L08. Koki, Leonardos & Piliouras (2020), "Exploring the Predictability of Cryptocurrencies via Bayesian Hidden Markov Models"

- **Spørgsmål:** kan skjulte Markov-modeller forudsige kryptoafkast?
- **Data:** BTC, ETH og XRP. Perioden står ikke på siden.
- **Metode:** flere HMM'er, også ikke-homogene med finansielle og kryptospecifikke forklarende variable.
- **Resultat:** en 4-tilstands ikke-homogen model giver den bedste prognose ét skridt frem for alle tre mønter og slår en
  random walk på prognosetæthed. For BTC er den hyppigste tilstand et bjørneregime med høj volatilitet.
- **Begrænsninger:** ingen handel og ingen omkostninger. Siden siger ikke klart, at testen er uden for sample.
- **Reproducerbarhed:** ukendt.
- **Copybot:** regimeklassifikation til `fregime`. Ikke evidens for en handelsfordel.
- **Status:** ABSTRACT (arXiv 2011.03741). https://arxiv.org/abs/2011.03741

### L09. Koch, Jeleskovic & Younas (2024), "Modelling and Predicting the Conditional Variance of Bitcoin Daily Returns" — NEG

- **Spørgsmål:** forudsiger Markov-switching GARCH BTC-volatilitet bedre end stokastisk volatilitet?
- **Data:** daglige BTC-afkast. Perioden står ikke i abstractet.
- **Metode:** sammenligning uden for sample af MS-GARCH og SARV-modeller.
- **Resultat:** SV-modeller, især SARV, slår MS-GARCH. En simpel, persistent GARCH kan i nogle tilfælde slå MS-GARCH.
- **Begrænsninger:** kun abstract. Kun BTC og daglig frekvens.
- **Reproducerbarhed:** ukendt.
- **Copybot:** modsiger delvist E39 (Ardia m.fl.: MS-GARCH bedst på 1-dags VaR). Regimemodeller er ikke automatisk bedre
  end en simpel volatilitetsmodel. Lab'et bør bruge den simple model som nulmodel.
- **Status:** ABSTRACT (arXiv 2401.03393). https://arxiv.org/abs/2401.03393

### L10. Grobys, Kolari, Sandretto, Shahzad & Äijö (2025), "Cryptocurrency momentum has (not) its moments"

- **Spørgsmål:** dæmper volatilitetsstyring kryptomomentums crash?
- **Data (ifølge søgeresumé):** ugentlige data 2016–2023, store mønter.
- **Resultat (ifølge søgeresumé):** de styrede strategier øger det ugentlige råafkast med over 200 %. Halerisikoen
  (power-law-eksponenten) er uændret.
- **Begrænsninger:** ikke læst. Omkostninger UNKNOWN. Springer sendte til login, og universitetets arkiv havde en
  bot-mur. Ingen omvej forsøgt.
- **Copybot:** ville være den eneste kryptospecifikke kilde til `volatility_managed_exposure`. Bruges ikke, før den er læst.
- **Status:** UNVERIFIED. FMPM 2025. https://link.springer.com/article/10.1007/s11408-025-00474-9

---

## 2. Likviditet og markedsmikrostruktur

### Oversigt

| # | Studie | Marked og periode | Hovedresultat | Netto/brutto | Status |
|---|---|---|---|---|---|
| L11 | Amihud 2002 | NYSE-aktier | Illikviditet giver højere forventet afkast | brutto | ABSTRACT |
| L12 | Kyle 1985 | teori | Prispåvirkning λ fra informeret ordreflow | ikke relevant | UNVERIFIED |
| L13 | Cont, Kukanov & Stoikov 2014 | 50 S&P 500-aktier, april 2010 | OFI forklarer samtidig kursændring, R² 65 % | ingen handel | VERIFIED |
| L14 | Nagel 2012 | US-aktier | Reversal er betaling for likviditet; stiger med VIX | brutto | ABSTRACT |
| L15 | Dyhrberg, Foley & Svec 2018 | BTC på 3 US-børser | Spreads lavere end på store aktiebørser | omkostningsniveau | ABSTRACT |
| L16 | Sensoy, Akyildirim & Corbet 2023 | Bitfinex | Adverse selection ≈ 10 % af effektiv spread | omkostningsniveau | ABSTRACT |
| L17 | Jia, Moallemi, Wang & Zeng 2026 **NEG** | Hyperliquid-perps, 03-2025 til 06-2026 | Manuelle (detail-)tradere taber 1,11 mia. USD netto | netto | ABSTRACT |
| (E30) | Makarov & Schoar 2020 | tværbørs BTC | Står allerede i registret | – | (E30) |

### L11. Amihud (2002), "Illiquidity and Stock Returns: Cross-Section and Time-Series Effects"

- **Spørgsmål:** forklarer illikviditet aktieafkast over tid og på tværs?
- **Data:** NYSE-aktier. Søgeresuméet siger 1964–1997; ikke set i den læste tekst.
- **Metode:** illikviditet = gennemsnit af |dagsafkast| / dollarvolumen.
- **Resultat (brutto):** forventet markedsilliquiditet øger det fremtidige merafkast. Mindre likvide aktier giver højere
  afkast. Effekten er størst for små selskaber.
- **Begrænsninger:** målet er groft og afhænger af prisniveau og volumen. E17 viser, at det rangerer niveauer og børser
  godt i krypto, men følger tidsvariation dårligere.
- **Reproducerbarhed:** kun daglige kurser og volumen. Let at genskabe.
- **Copybot:** `illiquidity_premium` og LIQPROXY1 (`protocols/LIQPROXY1_v1.md`). Krypto-volumen er forurenet af wash
  trading (E23), så målet er mindre pålideligt end i aktier.
- **Status:** ABSTRACT (NYU-arbejdspapir 2000). JFM 5:31–56. https://archive.nyu.edu/handle/2451/27420

### L12. Kyle (1985), "Continuous Auctions and Insider Trading"

- **Indhold (almen viden, ikke læst):** teori, hvor en informeret handler skjuler sig blandt støjhandlere. Prisen flytter
  lineært med ordreflowet med hældningen λ.
- **Copybot:** λ er det teoretiske grundlag for E17's Kyle-Obizhaeva-mål og for kvadratrodsloven (X028).
- **Status:** UNVERIFIED. IDEAS har intet abstract, og JSTOR kræver login. Econometrica 53(6):1315–1335.
  https://ideas.repec.org/a/ecm/emetrp/v53y1985i6p1315-35.html

### L13. Cont, Kukanov & Stoikov (2014), "The Price Impact of Order Book Events"

- **Spørgsmål:** hvad driver kortsigtede kursændringer: handler, limitordrer eller annulleringer?
- **Data:** 50 tilfældige S&P 500-aktier, TAQ-data, én måned (april 2010). Intervaller på 10 sekunder.
- **Metode:** regression af midtkursændring på ordreflowubalancen (OFI) ved bedste bud og udbud.
- **Resultat:** sammenhængen er lineær. Gennemsnitlig R² er 65 %. Hældningen er omvendt proportional med dybden. Samlet
  volumen forklarer kursen dårligere end OFI.
- **Begrænsninger:** sammenhængen er **samtidig**, ikke en prognose. Kun én måned og kun level 1-data.
- **Reproducerbarhed:** TAQ via WRDS (betalt). Ingen kode.
- **Copybot:** `orderflow_imbalance`. X026 genfinder formen på BitMEX. En høj samtidig R² er ikke en handelsfordel; L20
  og taker_pressure er REJECTED i lab'et.
- **Status:** VERIFIED (arXiv 1011.6402v3). J. Financial Econometrics 12(1):47–88. https://arxiv.org/abs/1011.6402

### L14. Nagel (2012), "Evaporating Liquidity"

- **Spørgsmål:** hvorfor forsvinder likviditet i uro?
- **Data:** US-aktier, kortsigtede reversal-porteføljer og brancheporteføljer. VIX som uromål.
- **Metode:** afkastet fra reversal bruges som mål for afkastet ved at stille likviditet.
- **Resultat (brutto):** afkastet til likviditetsforsyning svinger meget og kan forudsiges af VIX. Det steg kraftigt i
  2007–09. Selv branchereversal, der normalt giver lidt, giver højt afkast, når VIX er høj.
- **Begrænsninger:** kun abstract. Reversal-afkastet er før omkostninger. Det tilfalder den, der stiller likviditet, ikke
  den, der krydser spread.
- **Reproducerbarhed:** offentlige aktiedata og VIX.
- **Copybot:** `short_term_reversal_liquidity`, `liquidation_cascade_reversal` og LIQREC1 (`protocols/LIQREC1_v1.md`).
  Mekanismen passer med lab'ets negative takerresultater (L21 REJECTED, X022): præmien går til makers.
- **Status:** ABSTRACT. RFS 25(7):2005–2039. https://www.nber.org/papers/w17653

### L15. Dyhrberg, Foley & Svec (2018), "How investible is Bitcoin?"

- **Spørgsmål:** hvad koster det at handle BTC?
- **Data:** handler og kurser fra tre amerikanske kryptobørser. Perioden står ikke i abstractet.
- **Metode:** quoted og effektiv spread. Intradagmønstre.
- **Resultat:** spreads er lavere end på store aktiebørser. BTC er billig at handle i detailstørrelse. Aktivitet og spread
  følger amerikansk børstid.
- **Begrænsninger:** spotbørser fra før 2018. Gebyrer og prispåvirkning ved større ordrer er ikke med.
- **Reproducerbarhed:** ukendt.
- **Copybot:** for en lille aktør er spread ikke hovedomkostningen; gebyret er. Det stemmer med lab'ets model (taker
  0,10 % + slippage 0,02 % pr. side).
- **Status:** ABSTRACT. Economics Letters 171:140–143. https://econpapers.repec.org/RePEc:eee:ecolet:v:171:y:2018:i:c:p:140-143

### L16. Sensoy, Akyildirim & Corbet (2023), "Adverse selection in cryptocurrency markets"

- **Spørgsmål:** hvor stor er den informationsdrevne del af spread, og forudsiger den noget?
- **Data:** ordrer og handler fra Bitfinex. Mønter og periode står ikke på siden.
- **Metode:** spread opdeles i en adverse-selection-del og resten.
- **Resultat:** adverse selection er i gennemsnit ca. 10 % af den effektive spread. Den bruges som prædiktor for
  volatilitet, likviditet og afkast.
- **Begrænsninger:** kun abstract. Én børs.
- **Reproducerbarhed:** ukendt.
- **Copybot:** `maker_adverse_selection_measurement`. Modsiger ikke X025 (maker-fills er dårlige), fordi X025 måler
  afkastet efter fill, ikke spreadens sammensætning.
- **Status:** ABSTRACT. J. Financial Research 2023. https://repository.bilkent.edu.tr/items/470c2264-4455-41c7-afeb-fe4e59775f24

### L17. Jia, Moallemi, Wang & Zeng (2026), "Who Loses and Why? Market Microstructure of Perpetual Futures" — NEG

- **Spørgsmål:** hvem taber og hvem vinder på en perp-børs?
- **Data:** hele on-chain-ordre- og handelsloggen for Hyperliquids ti mest handlede kontrakter, 27-03-2025 til 30-06-2026.
- **Metode:** wallets deles i market makers, manuelle "front-end"-tradere og algoritmiske takers. P&L pr. handel måles mod
  midtkursen 2 timer senere, minus gebyrer.
- **Resultat (netto):** front-end-tradere taber 1,11 mia. USD. Market makers tjener 208 mio. USD. Algoritmiske takers
  går ca. i nul. Tabet kommer fra aggressive ordrer, tvangslikvidationer og gebyrer i de højeste trin.
- **Begrænsninger:** kun det udvidede abstract (3 sider) er læst. Én børs og én horisont. At front-end betyder detail, er
  forfatternes antagelse.
- **Reproducerbarhed:** data fra Allium. Ingen offentlig kode eller data nævnt.
- **Copybot:** direkte relevant for en lille taker på perps. Takerstrategier skal have en stor bruttokant. Makersiden
  (HLP, K04 i `PROFIT_SEARCH`) er der, hvor overførslen havner. Ikke i registrene i forvejen.
- **Status:** ABSTRACT. AFT 2026, LIPIcs 395, 36:1–36:3. https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.AFT.2026.36

### Henvisning: Makarov & Schoar (2020)

Står som E30 (JFE 2020) og X049 (on-chain). Ikke genåbnet. E30 finder store gab mellem børser og at en fælles komponent i
signeret volumen forklarer 80 % af BTC-afkastet. Se `LITERATURE_MAP.md` afsnit 9.

---

## 3. Reaktioner på planlagte økonomiske hændelser

### Oversigt

| # | Studie | Marked og periode | Hovedresultat | Netto/brutto | Status |
|---|---|---|---|---|---|
| L18 | Andersen, Bollerslev, Diebold & Vega 2003 | USD-valutakurser, 6 år | Overraskelser giver straks spring; dårlige nyheder vejer mest | ingen handel | ABSTRACT |
| L19 | Lucca & Moench 2015 | S&P 500 1994–2011 | +49 bp i 24 t før FOMC | brutto | VERIFIED |
| L20 | Kurov, Wolfe & Gilbert 2021 **NEG** | S&P 500 til 2019 | Driften forsvandt efter 2015 | brutto | ABSTRACT |
| L21 | Benigno & Rosa 2023 **NEG** | BTC 2017–2022, 30 min | BTC reagerer ikke på makro, undtagen CPI | ingen handel | VERIFIED |
| L22 | Corbet m.fl. 2020 | mange kryptoaktiver | Reaktion på FOMC afhænger af aktivtype | ingen handel | ABSTRACT |
| L23 | Pyo & Lee 2020 | BTC dagligt | Abstractet giver intet resultat | – | ABSTRACT |
| L24 | An, Dilts Stedman & Lusompa 2025 | US-renter | Daglige pengepolitiske overraskelser ≈ 30-min-overraskelser | metode | ABSTRACT |
| L25 | Block Scholes (praktiker) | BTC og CPI, 6 år | CPI-sammenhængen svækket 2024–25 | – | UNVERIFIED |

### L18. Andersen, Bollerslev, Diebold & Vega (2003), "Micro Effects of Macro Announcements"

- **Spørgsmål:** hvordan reagerer valutakurser i realtid på makrotal?
- **Data:** seks års realtidskurser for USD mod DEM, GBP, JPY, CHF og EUR, med forventninger og faktiske tal.
- **Metode:** overraskelse = faktisk tal minus forventning. Betinget middelværdi omkring udgivelsen.
- **Resultat:** overraskelser giver straks et spring i kursen. Effekten afhænger af timing og fortegn. Dårlige nyheder
  flytter mere end gode.
- **Begrænsninger:** kun abstract. Valuta, ikke krypto.
- **Reproducerbarhed:** kræver konsensusforventninger (betalt kilde i studiet).
- **Copybot:** designskabelon for R3, U4 og `US_MACRO_0830_DESIGN.md`. Overraskelsen kræver en kilde til
  konsensusforventninger. Det er en ny datalinje og kræver datagate. Krypto handles 24/7, så vinduet omkring 08:30 ET er
  rent (ingen lukket børs). Det er en fordel.
- **Status:** ABSTRACT. AER 93(1):38–62. https://www.aeaweb.org/articles?id=10.1257/000282803321455151

### L19. Lucca & Moench (2015), "The Pre-FOMC Announcement Drift"

- **Spørgsmål:** stiger aktier før planlagte FOMC-beslutninger?
- **Data:** S&P 500 og internationale indeks. Fra 1994 (offentliggørelse kl. 14:15) til 2011. Også 1980–1994.
- **Metode:** afkast i 24 timer før annonceringen.
- **Resultat (brutto):** siden 1994 steg S&P 500 i gennemsnit 49 bp i de 24 timer før. Det svarer til ca. 80 % af det
  årlige merafkast. Strategien havde en årlig Sharpe over 1,1. Ingen effekt i statsobligationer. Andre makrotal giver ikke
  drift før udgivelsen.
- **Begrænsninger:** forfatterne kan ikke forklare effekten med standard prisfastsættelsesteori. Få hændelser (8 om året).
- **Reproducerbarhed:** offentlige indeksdata.
- **Copybot:** se L20. Lab'ets FOMC er kun en integrationstest.
- **Status:** VERIFIED (NY Fed SR 512, rev. 2013). JF 70(1):329–371. https://www.newyorkfed.org/research/staff_reports/sr512.html

### L20. Kurov, Wolfe & Gilbert (2021), "The disappearing pre-FOMC announcement drift" — NEG

- **Spørgsmål:** findes L19 stadig efter 2011?
- **Data:** forlænger L19's stikprøve til december 2019.
- **Metode:** samme estimand, opdelt efter møder med og uden pressemøde.
- **Resultat:** driften optrådte først ved møder med pressemøde og forsvandt stort set efter 2015 ved alle møder.
  Forfatterne foreslår mindre usikkerhed som forklaring.
- **Begrænsninger:** kun abstract. Kun aktier.
- **Reproducerbarhed:** offentlige data.
- **Copybot:** et klassisk eksempel på forfald efter offentliggørelse (L31). Pre-FOMC skal ikke genoplives som kandidat.
- **Status:** ABSTRACT. FRL 40:101781. https://ideas.repec.org/a/eee/finlet/v40y2021ics1544612320315956.html

### L21. Benigno & Rosa (2023), "The Bitcoin–Macro Disconnect" — NEG

- **Spørgsmål:** reagerer BTC på makro- og pengepolitiske nyheder som andre amerikanske aktiver?
- **Data:** 5-minutters data. Andre aktiver 2000–2022, BTC kun 2017–2022.
- **Metode:** hændelsesstudie. Ændring fra 5 minutter før til 25 minutter efter. Standardiserede overraskelser.
  Overraskelser over 5 standardafvigelser fjernes.
- **Resultat:** BTC er "orthogonal to monetary and macroeconomic news". Eneste undtagelse er CPI. Guld, sølv, S&P 500 og
  valuta reagerer stort og signifikant. BTC reagerer ikke på overraskelser i den korte rente.
- **Begrænsninger:** forfatterne skriver, at der mangler mere evidens. Stikprøven for BTC er kort (6 år).
- **Reproducerbarhed:** konsensusdata fra Bloomberg (betalt).
- **Copybot:** R3, U4 0830 og `US_MACRO_0830_DESIGN.md`. Prior for en handelbar BTC-reaktion er lav; CPI er den eneste
  kandidat. Status opgraderes fra ABSTRACT (i designnotatet) til VERIFIED.
- **Status:** VERIFIED (fuld PDF). NY Fed SR 1052. https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr1052.pdf

### L22. Corbet, Larkin, Lucey, Meegan & Yarovaya (2020), "Cryptocurrency reaction to FOMC Announcements"

- **Spørgsmål:** reagerer forskellige kryptoaktiver forskelligt på FOMC- og QE-annonceringer?
- **Data:** mange kryptoaktiver i tre grupper: valutaer, protokoller og dApps. Perioden står ikke på siden.
- **Metode:** GARCH-modeller for volatilitetsspillover.
- **Resultat:** valuta-mønter viser egne spillovers lige efter annonceringen. Protokoller og dApps er stort set upåvirkede.
  Minebare aktiver er mere følsomme.
- **Begrænsninger:** daglige data (ifølge L21). Volatilitet, ikke retning. Ingen handel.
- **Reproducerbarhed:** ukendt.
- **Copybot:** et univers af perps er ikke homogent. Resultater for BTC kan ikke overføres direkte til alts.
- **Status:** ABSTRACT. J. Financial Stability 46:100706. https://ideas.repec.org/a/eee/finsta/v46y2020ics1572308919306576.html

### L23. Pyo & Lee (2020), "Do FOMC and macroeconomic announcements affect Bitcoin prices?"

- **Spørgsmål:** påvirker FOMC og makrotal BTC-prisen?
- **Data og metode (ifølge L21):** daglige data og dummyvariable for udvalgte annonceringer.
- **Resultat:** abstractet på IDEAS giver intet resultat.
- **Copybot:** ingen brugbar evidens. Daglige data kan ikke adskille hændelsen fra resten af døgnet.
- **Status:** ABSTRACT (uden resultat). FRL 37:101386. https://ideas.repec.org/a/eee/finlet/v37y2020ics154461231930159x.html

### L24. An, Dilts Stedman & Lusompa (2025), "How High Does High Frequency Need to Be?"

- **Spørgsmål:** kan daglige data erstatte 30-minutters data til at måle pengepolitiske overraskelser?
- **Data:** amerikanske renteinstrumenter omkring FOMC.
- **Metode:** sammenligner daglige og intradag-overraskelser. Tester for forurening fra andre nyheder.
- **Resultat:** de to er ens fordelt og ofte stærkt korrelerede, især for længere renter. Ingen tegn på forurening.
- **Begrænsninger:** kun abstract læst. Renter, ikke krypto. Gælder måling af overraskelsen, ikke aktivets reaktion.
- **Reproducerbarhed:** offentlige renter. Intradagdata er betalte.
- **Copybot:** lab'et kan bruge daglige renteændringer som mål for selve FOMC-overraskelsen. BTC's reaktion skal stadig
  måles intradag (L21).
- **Status:** ABSTRACT (abstract læst i PDF). KC Fed RWP 25-03. https://www.kansascityfed.org/documents/10867/rwp25-03-anstedmanlusompa.pdf

### L25. Block Scholes (praktiker), "Is Bitcoin showing greater sensitivity to US CPI releases again?"

- **Indhold (kun søgeresumé):** over seks år faldt hældning og forklaringsgrad for BTC mod CPI-overraskelser i slutningen af
  2024 og i 2025. Der er tegn på en genkomst i 2026.
- **Copybot:** hvis det holder, er L21's CPI-undtagelse ustabil over tid. Ikke åbnet, kun praktiker.
- **Status:** UNVERIFIED. https://www.blockscholes.com/institutional-research/is-bitcoin-showing-greater-sensitivity-to-us-cpi-releases-again

---

## 4. Backtest-overfitting og multipel testning

### Oversigt

| # | Studie | Felt | Hovedresultat | Status |
|---|---|---|---|---|
| L26 | Bailey, Borwein, López de Prado & Zhu, PBO | metode | CSCV estimerer sandsynligheden for overfitting; random walk gav PBO ≈ 55 % | VERIFIED |
| L27 | Bailey & López de Prado, DSR | metode | Sharpe korrigeret for antal forsøg, ikke-normalitet og længde | VERIFIED |
| L28 | Harvey, Liu & Zhu 2016 **NEG** | 316 aktiefaktorer | Kræv t > 3,0; 80–158 af 296 er falske | VERIFIED |
| L29 | McLean & Pontiff 2016 **NEG** | 82 (WP) / 97 (JF) prædiktorer | Afkastet falder efter offentliggørelse | VERIFIED (WP) |
| L30 | Hou, Xue & Zhang 2020 **NEG** | 447 anomalier | 64 % insignifikante ved 5 %; 85 % ved t > 3 | ABSTRACT |
| L31 | Jensen, Kelly & Pedersen 2023 | faktorer i 93 lande | Modsvar: de fleste faktorer kan replikeres | ABSTRACT |
| L32 | Chen & Welch 2026 **NEG** | ca. 200 anomalier | Median 7 bp/md. efter 2005 i likvide aktier | ABSTRACT |
| L33 | Gort m.fl. 2022 **NEG** (svag) | 10 mønter | PBO brugt på RL-agenter; testvindue kun 8 uger | ABSTRACT |

### L26. Bailey, Borwein, López de Prado & Zhu, "The Probability of Backtest Overfitting"

- **Spørgsmål:** hvor sandsynligt er det, at den strategi, der var bedst i sample, er under medianen uden for sample?
- **Data:** simulerede random walks og én rigtig strategi (eksempler).
- **Metode:** Combinatorially Symmetric Cross-Validation (CSCV). Afkastmatricen (T tidspunkter × N konfigurationer)
  deles i S blokke. Alle kombinationer af halvdelen bruges som træning og resten som test. PBO er andelen af
  kombinationer, hvor den bedste i træning ligger under medianen i test (via logits).
- **Resultat:** en månedlig sæsonregel med 8.800 parameterkombinationer på 1.000 dage random walk fik in-sample Sharpe
  1,27 og en PSR-statistik på 2,83. Alligevel var PBO ca. 55 %, og ca. 53 % af Sharpe uden for sample var negative. Andre
  eksempler giver PBO 74 % og 0,04 %. Forfatterne foreslår at afvise modeller med PBO over 0,05.
- **Begrænsninger (forfatternes egne):**
  - Alle forsøg skal med. Skjulte forsøg undervurderer overfitting.
  - Metoden tjekker ikke, om backtesten er rigtig (forkerte omkostninger eller look-ahead).
  - Brud uden for datasættet fanges ikke.
  - Stærk autokorrelation gør opdelingen dårlig, når S er stor.
  - Høj PBO kan skyldes mange lige gode strategier.
  - PBO må ikke bruges som mål for at vælge strategi.
- **Reproducerbarhed:** algoritmen er fuldt beskrevet. Ingen kode i teksten.
- **Copybot:** kan bruges pr. lineage, hvor mange varianter deler tidsakse (f.eks. explore0 med 19.182 kandidater og
  m17:margin med 20). Kræver gemte afkastserier pr. variant. Se afsnittet "Hvad betyder det for Copybot".
- **Status:** VERIFIED (forfatterens PDF, rev. feb. 2015). https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf

### L27. Bailey & López de Prado (2014), "The Deflated Sharpe Ratio"

- **Spørgsmål:** hvornår er den bedste Sharpe blandt mange forsøg signifikant?
- **Data:** ingen (metode med talteksempel).
- **Metode:** DSR = sandsynligheden for, at den sande Sharpe overstiger den forventede maksimale Sharpe under nul. Input:
  antal uafhængige forsøg N, variansen af Sharpe på tværs af forsøg, længden T, skævhed og kurtosis.
- **Resultat:** i eksemplet har en strategi Sharpe 2,5 over 5 års daglige data (T = 1.250). Efter korrektion er der kun
  ca. 90 % sandsynlighed for, at den sande Sharpe er over nul. Den afvises ved 95 %. Ved N = 46 forsøg ville den være
  bestået (0,9505). Fede haler og negativ skævhed gør tærsklen højere.
- **Begrænsninger:** N skal være antal **uafhængige** forsøg. Forfatterne foreslår at interpolere mellem 1 og antallet af
  forsøg M med den gennemsnitlige korrelation. Testning bør planlægges på forhånd.
- **Reproducerbarhed:** formlerne står i teksten. Let at kode.
- **Copybot:** lab'ets "luck bar" (E[max z] ≈ 2,775 for N = 206) er DSR's første ingrediens. Den fulde DSR kræver også
  Sharpe-varians, skævhed og kurtosis pr. forsøg. Registret har dem ikke (`PAPER_DASHBOARD_V2.md`).
- **Status:** VERIFIED (forfatterens PDF, juli 2014). JPM 40(5):94–107. https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf

### L28. Harvey, Liu & Zhu (2016), "…and the Cross-Section of Expected Returns" — NEG

- **Spørgsmål:** hvilken t-værdi skal en ny faktor have, når hundredvis er testet?
- **Data:** 316 publicerede faktorer fra 1967 til ca. 2012.
- **Metode:** Bonferroni, Holm og BHY (falsk opdagelsesrate). Simulering af korrelerede tests og af utestede forsøg.
- **Resultat:** en ny faktor bør have t over 3,0 (p ≈ 0,27 %). Af 296 publicerede signifikante faktorer er 158 falske
  efter Bonferroni, 142 efter Holm, 132 efter BHY 1 % og 80 efter BHY 5 %. Forfatterne mener, at "most claimed research
  findings in financial economics are likely false".
- **Begrænsninger (forfatternes egne):** faktorer fra teori kan fortjene en lavere tærskel. Testene er ubetingede; en
  faktor kan være vigtig i nogle regimer. Antallet af upublicerede forsøg er ukendt, så 316 er for lavt.
- **Reproducerbarhed:** faktorlisten ligger som regneark på forfatterens side.
- **Copybot:** lab'ets egen registrering af alle forsøg (206) løser netop problemet med ukendt antal forsøg. HLZ's
  tærskel 3,0 er tæt på lab'ets E[max z] 2,78 for 206 forsøg.
- **Status:** VERIFIED (Duke PDF). RFS 29(1):5–68. https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF

### L29. McLean & Pontiff (2016), "Does Academic Research Destroy Stock Return Predictability?" — NEG

- **Spørgsmål:** hvad sker der med en anomalis afkast efter stikprøven og efter offentliggørelse?
- **Data:** arbejdspapiret fra maj 2013 bruger 82 karakteristika fra publicerede studier. Den publicerede version bruger 97.
- **Metode:** sammenligner afkast i sample, efter sample men før offentliggørelse og efter offentliggørelse.
- **Resultat (arbejdspapiret, brutto):** forfald efter stikprøven ca. 10 % (ikke signifikant). Forfald efter
  offentliggørelse ca. 35 %. Efter offentliggørelse stiger volumen, short interest og korrelationen med andre publicerede
  anomalier. Forfaldet er størst, hvor arbitrage er billig.
- **Den publicerede version (UNVERIFIED):** et søgeresumé siger 26 % lavere efter stikprøven og 58 % lavere efter
  offentliggørelse. Jeg har ikke kunnet åbne JF-teksten (Wiley 403; en kopi på en tredjepartsside blev afvist).
- **Begrænsninger:** aktier. Brutto.
- **Reproducerbarhed:** offentlige aktiedata (CRSP er betalt).
- **Copybot:** `PROFIT_SEARCH_2026-11-09.md` bruger faktor 0,65. Det svarer til arbejdspapirets 35 %. Hvis den publicerede
  version er rigtig, er den samlede reduktion efter offentliggørelse nærmere 58 %, dvs. faktor 0,42.
- **Status:** VERIFIED (arbejdspapir 2013, Western/Ivey-seminarkopi). JF 71(1):5–32. https://ivey.uwo.ca/media/3775549/pontiff.pdf

### L30. Hou, Xue & Zhang (2020), "Replicating Anomalies" — NEG

- **Spørgsmål:** hvor mange publicerede anomalier overlever en ensartet replikation?
- **Data:** 447 anomalivariable i US-aktier.
- **Metode:** NYSE-brudpunkter og værdivægtning, så mikroaktier ikke dominerer.
- **Resultat:** 286 (64 %) er insignifikante ved 5 %. Ved t > 3 er det 380 (85 %). 95 af 102 likviditetsvariable fejler.
- **Begrænsninger:** kun abstract. Nogle kritiserer, at værdivægtning er for streng.
- **Reproducerbarhed:** forfatterne har et offentligt datasæt (ikke kontrolleret her).
- **Copybot:** krypto-resultater fra ligevægtede porteføljer med mange små mønter skal behandles på samme måde. X042, X070
  og X071 viser netop, at fordele ligger i illikvide mønter.
- **Status:** ABSTRACT. RFS 33(5):2019–2133. https://www.nber.org/papers/w23394

### L31. Jensen, Kelly & Pedersen (2023), "Is There a Replication Crisis in Finance?"

- **Spørgsmål:** er de fleste faktorer falske?
- **Data:** et nyt datasæt for 93 lande. Faktorerne grupperes i 13 temaer.
- **Metode:** Bayesiansk model for replikation.
- **Resultat:** de fleste faktorer kan replikeres og virker uden for sample. Det store antal faktorer styrker evidensen,
  fordi de kan grupperes.
- **Begrænsninger:** kun abstract. Brutto. Siger ikke noget om omkostninger eller om krypto.
- **Reproducerbarhed:** kode på GitHub (bkelly-lab/GlobalFactor) og data på forfatterens side.
- **Copybot:** modsvar til L28 og L30. Pointen er, at temaer, ikke enkelte varianter, er den rigtige enhed. Det passer med
  lab'ets lineages: forsøg i samme lineage er korrelerede og skal ikke tælles som uafhængige.
- **Status:** ABSTRACT. JF 78(5):2465–2518. https://www.nber.org/papers/w28432

### L32. Chen & Welch (2026), "What Useful Alphas?" — NEG

- **Spørgsmål:** har publicerede anomalier været brugbare for porteføljeforvaltere efter 2005?
- **Data:** ca. 200 long/short-porteføljer fra Chen & Zimmermann (2022).
- **Metode:** deler op i før og efter 2005 og i mikro- og ikke-mikroaktier.
- **Resultat (brutto):** median 48 bp om måneden til 2005. Efter 2005 19 bp. Kun ikke-mikroaktier efter 2005: 7 bp.
  Forfatterne mener, at selv beskedne tillæg for held eller omkostninger fjerner resten.
- **Begrænsninger:** kun abstract. Aktier.
- **Reproducerbarhed:** Chen & Zimmermann-data er offentlige.
- **Copybot:** den samme opdeling (likvidt univers, nyeste periode) bør være standard i lab'ets haircut af
  litteraturtal. Kryptotal fra 2017–2021 er fra en periode med færre arbitrageurer.
- **Status:** ABSTRACT (arXiv 2607.06502, juli 2026). https://arxiv.org/abs/2607.06502

### L33. Gort m.fl. (2022), "Deep Reinforcement Learning for Cryptocurrency Trading: Practical Approach to Address Backtest Overfitting"

- **Spørgsmål:** kan man sortere overfittede RL-agenter fra med en PBO-test?
- **Data:** 10 mønter. Testperiode 1. maj til 27. juni 2022 (to krak).
- **Metode:** overfitting formuleres som en hypotesetest. Agenter med høj sandsynlighed for overfitting afvises.
- **Resultat:** de mindst overfittede agenter gav højere afkast end de mest overfittede og slog et ligevægtet indeks.
- **Begrænsninger:** testvinduet er kun 8 uger. Omkostninger står ikke på siden. Det viser, at en PBO-procedure ikke
  hjælper, hvis testperioden er for kort.
- **Reproducerbarhed:** forfatterne er tilknyttet FinRL (open source); ikke kontrolleret.
- **Copybot:** brug PBO som filter, men aldrig som eneste bevis. Testperioden skal have nok uafhængige observationer.
- **Status:** ABSTRACT (arXiv 2209.05559). https://arxiv.org/abs/2209.05559

---

## 5. Realistiske omkostningsmodeller

### Oversigt

| # | Studie | Marked | Hovedresultat | Netto/brutto | Status |
|---|---|---|---|---|---|
| L34 | Frazzini, Israel & Moskowitz 2018 | aktier i 21 lande, 19 år, 1,7 bio. USD handler | Faktiske omkostninger en størrelsesorden lavere end antaget | omkostningsniveau | ABSTRACT |
| L35 | Almgren & Chriss 2000 | teori | Effektiv front mellem eksekveringsomkostning og risiko | ikke relevant | ABSTRACT |
| L36 | Novy-Marx & Velikov 2016 **NEG** | US-aktier 1963–2013 | Anomalier med omsætning over 50 %/md. overlever sjældent | netto | VERIFIED |
| L37 | Patton & Weller 2020 **NEG** | US-investeringsforeninger | Fonde får lidt værdi og intet momentum efter omkostninger | netto | ABSTRACT |
| L38 | Chen & Velikov 2023 **NEG** | 120 (WP) / 204 (JFQA) anomalier | Gennemsnitlig anomali giver 8 bp/md. netto | netto | ABSTRACT |
| L39 | Deng 2025/26, "AutoQuant" | BTC, ETH, SOL, AVAX-perps | Backtests med kun gebyr eller nul omkostning puster resultatet op | metode | ABSTRACT |

### L34. Frazzini, Israel & Moskowitz (2018), "Trading Costs"

- **Spørgsmål:** hvad koster det reelt for en stor investor at handle, og hvordan ser prispåvirkningen ud?
- **Data:** over 1,7 billioner USD i faktiske handler fra en stor kapitalforvalter (AQR) i 21 udviklede aktiemarkeder over
  19 år.
- **Metode:** en model for prispåvirkning kalibreres på de faktiske omkostninger. Den testes uden for sample mod andre
  modeller og mod realiserede omkostninger i indeksfonde.
- **Resultat:** de faktiske omkostninger er "an order of magnitude smaller than previous studies suggest". Faktorstrategier
  kan derfor have større kapacitet end antaget.
- **Begrænsninger:** kun AQR's resumé er læst. Dataene er forfatternes egne handler med algoritmisk eksekvering. Det er en
  stor institution med lave kommissioner. Tal for kapacitet og pr. faktor er ikke set.
- **Reproducerbarhed:** data er ikke offentlige.
- **Copybot:** overføres **ikke** til en lille aktør på krypto-perps. Her er prispåvirkningen lille, men gebyr og spread
  dominerer (L15, L17). Lab'ets taker 0,10 % + 0,02 % pr. side er langt over FIM's niveauer og bør ikke sænkes med
  henvisning til FIM.
- **Status:** ABSTRACT (AQR-side). https://www.aqr.com/Insights/Research/Working-Paper/Trading-Costs

### L35. Almgren & Chriss (2000), "Optimal execution of portfolio transactions"

- **Spørgsmål:** hvordan afvikler man en stor ordre, så omkostning og risiko balanceres?
- **Data:** ingen (teori).
- **Metode:** midlertidig og permanent prispåvirkning. Effektiv front mellem forventet omkostning og usikkerhed. Valg via
  kvadratisk nytte eller VaR.
- **Resultat:** med lineær påvirkning kan fronten beregnes eksplicit. Giver "likviditetsjusteret VaR".
- **Begrænsninger:** lineær påvirkning. X028 viser, at påvirkningen i praksis følger en kvadratrodslov.
- **Reproducerbarhed:** lukket formel.
- **Copybot:** relevant for papirmotorens fyldmodel (20 niveauer), hvis ordrestørrelsen vokser. For lab'ets nuværende
  små ordrer er det ikke den vigtigste omkostning.
- **Status:** ABSTRACT. J. Risk 3(2):5–39. https://econpapers.repec.org/RePEc:rsk:journ4:2161150

### L36. Novy-Marx & Velikov (2016), "A Taxonomy of Anomalies and Their Trading Costs" — NEG

- **Spørgsmål:** hvilke anomalier overlever omkostninger, og hvilke teknikker sænker omkostningerne?
- **Data:** US-aktier, juli 1963 til december 2013.
- **Metode:** effektiv spread estimeret med Hasbroucks (2009) Bayesianske metode. Test af flere omkostningsdæmpende
  teknikker. Kapacitet over for ny kapital.
- **Resultat (netto):**
  - De fleste anomalier med en månedlig omsætning under 50 % giver signifikant nettospread, når de er bygget til at spare
    omkostninger. Få med højere omsætning gør.
  - Den bedste teknik er et købs-/holdebånd: strengere krav for at åbne en position end for at beholde den.
  - Omkostninger mindsker altid profitten. Det øger bekymringen for data snooping.
  - Ligevægtede resultater er misvisende, fordi små aktier er dyre at handle.
- **Begrænsninger:** effektiv spread indeholder ikke prispåvirkning. Den undervurderer altså omkostningen for store ordrer.
- **Reproducerbarhed:** Hasbroucks SAS-kode er offentlig. CRSP er betalt.
- **Copybot:** et købs-/holdebånd er en billig regel for alle bøger, der ombalancerer (Donchian, straks, carry90, pairs).
  Kryptoresultater med høj omsætning eller ligevægtning i små mønter skal have et stort haircut.
- **Status:** VERIFIED (forfatterens PDF, aug. 2015). RFS 29(1):104–147. https://mysimon.rochester.edu/novy-marx/research/ToAatTC.pdf

### L37. Patton & Weller (2020), "What you see is not what you get: The costs of trading market anomalies" — NEG

- **Spørgsmål:** hvor stor er forskellen mellem papirafkast og det, investorer faktisk opnår?
- **Data:** investeringsforeningers afkast og faktoreksponeringer.
- **Metode:** udvidet Fama-MacBeth. Sammenligner papirafkastet for en eksponering med det, fondene opnår. Ingen
  parametrisk mikrostrukturmodel.
- **Resultat (netto):** efter omkostninger får typiske fonde lidt ud af værdi og intet ud af momentum.
- **Begrænsninger:** kun abstract. Fonde er store; resultatet gælder dem.
- **Reproducerbarhed:** offentlige fond- og aktiedata.
- **Copybot:** modsiger L34. Uenigheden viser, at omkostningsniveauet afhænger meget af, hvem der handler og hvordan.
  Lab'et bør måle sin egen omkostning fremad (costreport, H_SPR1/H_SPR2) frem for at låne et tal.
- **Status:** ABSTRACT. JFE 137(2):515–549. https://econpapers.repec.org/RePEc:eee:jfinec:v:137:y:2020:i:2:p:515-549

### L38. Chen & Velikov (2023), "Zeroing in on the Expected Returns of Anomalies" — NEG

- **Spørgsmål:** hvad er den forventede nettoafkast af en anomali i dag?
- **Data:** 120 anomalier i Fed-arbejdspapiret (204 i JFQA-versionen ifølge søgeresumé).
- **Metode:** fratrækker effektive spreads. Justerer for forfald efter offentliggørelse og for den moderne handelsæra
  (fra start-2000'erne). Korrigerer for data mining.
- **Resultat (netto):** den gennemsnitlige anomali giver "a measly 8 bps per month". De stærkeste giver kun 10–20 bp efter
  korrektion for data mining.
- **Begrænsninger:** prispåvirkning er udeladt, så tallet er snarere for højt. Søgeresuméet siger 72 % forfald efter 2005
  i JFQA-versionen; det er ikke kontrolleret.
- **Reproducerbarhed:** bygger på offentlige anomalidata.
- **Copybot:** lab'ets regel om, at R ≤ 1 giver SCORE 0 (`PROFIT_SEARCH` afsnit 2), er i tråd med dette. Litteraturtal skal
  korrigeres for både omkostning, forfald og data mining, ikke kun én af dem.
- **Status:** ABSTRACT (Fed FEDS 2020-039). JFQA 58(3):968–1004. https://www.federalreserve.gov/econres/feds/zeroing-in-on-the-expected-returns-of-anomalies.htm

### L39. Deng (2025/2026), "AutoQuant: An Auditable Expert-System Framework for Execution-Constrained Auto-Tuning in Cryptocurrency Perpetual Futures"

- **Spørgsmål:** hvordan gør man parameter-tuning på perps revisionsbar og omkostningsrealistisk?
- **Data:** BTC-, ETH-, SOL- og AVAX-USDT-perps. Perioden står ikke i abstractet.
- **Metode:** Bayesiansk søgning med to-trins screening på tværs af vinduer og omkostningsscenarier. Regler for
  eksekveringstidspunkt, synlighed af funding og omkostninger. Lineære omkostninger.
- **Resultat:** backtests med kun gebyr eller nul omkostning puster resultatet væsentligt op i forhold til kørsler med
  funding og slippage. To-trins screeningen giver ikke højere afkast, men oftere lavere drawdown.
- **Begrænsninger:** ingen tal i abstractet. Simulering for små konti uden prispåvirkning. Én signalfamilie.
- **Reproducerbarhed:** forfatteren eksporterer deterministiske artefakter; kode ikke kontrolleret.
- **Copybot:** støtter lab'ets praksis: funding og slippage skal altid med, og fundingtidspunktet skal være kendt på
  handelstidspunktet.
- **Status:** ABSTRACT (arXiv 2512.22476v3). Expert Systems with Applications 2026. https://arxiv.org/abs/2512.22476

---

## Overførbarhed til krypto-perps og 24/7-markeder

| Fund | Overføres? | Hvorfor |
|---|---|---|
| Volatilitetsstyring virker ikke i realtid for de fleste faktorer (L04–L06) | Sandsynligvis ja | Krypto har højere omsætning og omkostninger, så det bliver værre, ikke bedre |
| Volatilitetsstyring af markedet overlever omkostninger (L06) | Uafklaret | BTC er tættest på "markedet", men ingen læst kilde har testet det |
| Hyppige strukturbrud (L07) | Ja | Direkte målt på BTC |
| OFI forklarer samtidig kurs (L13) | Ja (X026) | Samme mekanik i en limitordrebog. Stadig ikke prognose |
| Likviditetspræmie til makers (L14, L17) | Ja | L17 er målt på en kryptoperp |
| Pre-FOMC-drift (L19) | Nej | Forsvundet i aktier (L20). BTC reagerer ikke på pengepolitik (L21) |
| Makrooverraskelser (L18, L21) | Svagt | Kun CPI for BTC. 24/7 giver et rent vindue |
| Multipel testning (L26–L28) | Ja | Statistik, ikke marked |
| Forfald efter offentliggørelse (L29, L32) | Ja, og stærkere | Kryptolitteraturen er ung og fra rallyperioder |
| Lave institutionelle omkostninger (L34) | Nej | Lab'et er lille og betaler detailgebyrer |

---

## Hvad betyder det for Copybot

### 1. Registret kan ikke beregne DSR eller PBO i dag

- `PAPER_DASHBOARD_V2.md` siger, at registret ikke har z- eller Sharpe-værdier pr. forsøg. Uden dem kan hverken DSR (L27)
  eller PBO (L26) beregnes. Lab'ets "luck bar" er kun den første ingrediens i DSR.
- **Forslag:** tilføj disse felter pr. forsøg i factory-registret: teststørrelse, Sharpe pr. periode, antal perioder T,
  skævhed, kurtosis, antal varianter og lineage. Gem afkastserien pr. variant (net af omkostninger) på en fælles tidsakse.
  Det kræver kun kodeændringer i `research/tools/factory.py`, ingen nye data.

### 2. DSR på de 206 forsøg: to grænser, ikke ét tal

Beregnet her med Bailey & López de Prados formel for forventet maksimum af N uafhængige standardnormale:

| N | E[max z] | Bonferroni (α 0,05, ensidet) |
|---|---|---|
| 47 | 2,25 | – |
| 206 (forsøg) | 2,78 | 3,49 |
| 1.000 | 3,26 | – |
| 19.438 (varianter) | 4,02 | 4,56 |

- Det sande antal uafhængige forsøg ligger mellem antal lineages (43 i `research/data/factory/registry.md`, E[max z] ≈ 2,22) og antal varianter (19.438). L27 foreslår at bruge den
  gennemsnitlige korrelation til at interpolere. L31 peger samme vej: temaer, ikke varianter, er enheden.
- **Forslag:** rapportér DSR både med N = antal forsøg og med N̂ fra den målte korrelation. Et "bedste af backtests"-krav
  skal bestå med N̂. Lab'ets låste fremadtest med α_F 0,0125 (z ≥ 2,24) er rimelig, fordi den bruger nye data efter en
  lås. Men den må ikke bruges til at vælge blandt flere fremadkørsler uden ny korrektion.

### 3. Hvad z ≥ 2,24 kræver i Sharpe

Med uafhængige perioder er z ≈ årlig Sharpe × √år. Beregnet her:

| Fremad-horisont | Krævet årlig Sharpe for z 2,24 | for z 2,78 |
|---|---|---|
| 3 måneder | 4,5 | 5,6 |
| 6 måneder | 3,2 | 3,9 |
| 1 år | 2,2 | 2,8 |
| 2 år | 1,6 | 2,0 |

En kort fremadtest kan kun bekræfte meget store effekter. Litteraturens nettotal (L32, L38) er langt fra de niveauer.
Det forklarer lab'ets gentagne INSUFFICIENT POWER og bør stå i hver låsetekst før data.

### 4. PBO/CSCV pr. lineage

- Brug CSCV, hvor mindst ca. 10 varianter deler tidsakse. Kandidater: explore0 (19.182 kandidater; registret siger "never evidence", men PBO måler netop kvaliteten af en søgeproces) og m17:margin (20). cross_venue_perp_gap (26) samler otte tags (bl.a. carry og basis), så varianterne deler næppe tidsakse.
- Kør det på **nettoserier**. L26 siger selv, at metoden ikke opdager forkerte omkostninger eller look-ahead.
- Brug forfatternes tærskel PBO > 0,05 som **diagnose** først, ikke som gate, til lab'et har set fordelingen på egne data.
- PBO må ikke bruges til at vælge den næste variant (L26's advarsel om misbrug).
- Om explore0's afkastserier pr. variant findes på disk: UNVERIFIED (lab.db ikke åbnet).

### 5. Haircut på litteraturtal

- `PROFIT_SEARCH_2026-11-09.md` ganger med 0,65 (McLean & Pontiff). Det svarer til arbejdspapirets 35 % (L29). Den
  publicerede version siger muligvis 58 % (UNVERIFIED). **Forslag:** kør følsomhed med 0,42. En kandidat, der kun
  overlever ved 0,65, er svag.
- Ret litteraturtal i denne rækkefølge: (1) kun likvidt univers og værdivægtning (L30, L36), (2) nyeste periode (L32), (3)
  forfald (L29), (4) lab'ets egne omkostninger, (5) data mining (L28, L38).
- FIM's lave omkostninger (L34) må ikke bruges til at sænke lab'ets omkostningsmodel. L17 viser, at små takers på perps
  betaler mest.
- Backtests skal altid have funding og slippage, ikke kun gebyr (L39).
- **Forslag:** tilføj et købs-/holdebånd (L36) som standardvariant i bøger med ombalancering. Det er en ren
  omkostningsregel og ændrer ikke signalet.

### 6. Volatilitet og regimer

- En volatilitetsregel må kun bruge parametre, der var kendt på handelstidspunktet. Gearing kalibreret på hele
  stikprøven er look-ahead (L03, L05).
- Den skal slå den ustyrede version direkte uden for sample og efter omkostninger (L04, L06). Spanning-alfa er ikke nok.
- Størst chance: BTC-eksponering (analog til "markedet" i L06). Mindst chance: long/short-bøger.
- I registret ligger `volatility_managed_exposure` under lineage `betting_against_beta` (4 forsøg, 8 varianter).
- Regimemodeller skal slå en simpel GARCH som nulmodel (L09).
- Brud er hyppige i BTC (L07). Backtests over flere markedsfaser bør have en brudtest (L02) eller deles op.

### 7. Planlagte hændelser (R3, U4 0830, US_MACRO_0830)

- Pre-FOMC skal ikke genoplives (L20, L21).
- BTC reagerer kun på CPI i 2017–2022 (L21), og forholdet er måske ustabilt (L25, UNVERIFIED). Låseteksten bør antage en
  lille effekt og beregne styrke ud fra det.
- Et overraskelsesdesign (L18) kræver konsensusforventninger. Det er en ny datalinje og kræver datagate.
- FOMC-overraskelsen kan måles med daglige renter (L24). BTC's reaktion skal måles intradag.
- Alts reagerer anderledes end BTC (L22). Resultater for BTC må ikke generaliseres til hele universet.

### 8. Likviditet

- Samtidig OFI-forklaring (L13) er ikke en prognose. `orderflow_imbalance` skal måles som prognose og netto.
- Reversalafkast er betaling for likviditet (L14). Det tilfalder makers. Det stemmer med L21 REJECTED, X022 og L17.
- LIQREC1 bygger på samme mekanisme som L14 (likviditetsforsyning efter stress). L14 giver kildestøtte, men ingen
  kryptotal.

---

## De 5 mest beslutningsrelevante fund

1. **Registret mangler felterne til DSR og PBO** (L26, L27). Med N = 206 er luck bar 2,78. Med 19.438 varianter er den
   4,02. Det sande tal ligger imellem. Tilføj Sharpe, T, skævhed, kurtosis og nettoserier pr. variant, før lab'et påstår
   noget om "bedste forsøg".
2. **Korte fremadtests kan kun se meget store effekter.** z 2,24 på 3 måneder kræver årlig Sharpe ca. 4,5. Nettoafkast i
   litteraturen efter 2005 er næsten nul (L32: 7 bp/md.; L38: 8 bp/md.). Fremadhorisonten skal planlægges ud fra det.
3. **Haircut 0,65 er måske for mildt** (L29). Arbejdspapiret siger 35 % forfald, den publicerede version muligvis 58 %
   (UNVERIFIED). Brug 0,42 som følsomhed, og kræv likvidt univers og nyeste periode (L30, L32, L36).
4. **Volatilitetsstyring virker ikke i realtid efter omkostninger** for de fleste faktorer (L04, L05, L06). Kun
   markedseksponering har en chance. `volatility_managed_exposure` bør kun testes på BTC-eksponering og kun med
   realtidsparametre.
5. **Små takers på perps taber netto** (L17: −1,11 mia. USD på Hyperliquid; makers +208 mio.). Sammen med L14 og lab'ets
   egne REJECTED-takerresultater peger det på, at en eventuel nettofordel for lab'et skal komme fra makersiden eller fra en
   strukturel præmie, ikke fra takersignaler.

---

## Ikke-verificerede spor fra denne runde

| Spor | Status |
|---|---|
| McLean & Pontiff, publiceret JF-version (26 %/58 %) | Wiley 403. En kopi på en tredjepartsside blev afvist af værktøjet. Ikke omgået |
| Grobys, Kolari m.fl. 2025 (FMPM) | Springer-login og bot-mur på universitetsarkivet |
| Kyle 1985 | Intet abstract på IDEAS; JSTOR kræver login |
| Chen & Velikov, JFQA-tal (204 anomalier, 4 bp, 72 % forfald efter 2005) | Kun søgeresumé |
| Frazzini m.fl., tal for kapacitet og S&P 500-omkostning (4,81 bp) | Kun sekundære resuméer. SSRN ikke forsøgt |
| Block Scholes om BTC og CPI 2024–2026 | Praktiker, ikke åbnet |
| En nyere Fed-artikel om ca. −30 bp pr. 1 sd CPI-overraskelse (fra `US_MACRO_0830_DESIGN.md`) | Ikke fundet i denne runde |
| Ben Omrane m.fl. 2025 (IREF) om BTC/ETH og makrotal | Står allerede som ABSTRACT i `US_MACRO_0830_DESIGN.md`. Ikke genåbnet |
