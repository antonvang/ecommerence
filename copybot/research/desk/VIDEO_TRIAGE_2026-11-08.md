# VIDEO_TRIAGE: fem ejervideoer (2026-11-08 23:57 lokal)

Ejeren sendte fem TikTok-videoer med teksten "Pefekt imens for du disse". De er gennemgået som billeder hvert 3. s i
sessionen og er ikke lagt i repo'et. Ingen data er hentet, ingen konto er oprettet og intet link er åbnet.

| # | Konto | Påstand | Testbar regel? | Røde flag | Vurdering |
|---|---|---|---|---|---|
| 1 | @keyzecom | "You can't make a trading bot with Claude". Viser et selvbygget "LTT / DATA FARM"-dashboard: dækning, ordforråd (liquidity sweep m.m.) og daglige "farm studies" | **Nej.** Ingen strategi og ingen performance vises | – | Ingen påstand at teste. Værktøjsidéen svarer til lab'ets egne dashboards |
| 2 | @stickmanxwx | Generel guide: vælg marked (krypto 24/7), TA-Lib, trend/mean reversion/arbitrage, millisekunder | **Nej** | "Comment 'Trade' + your country" for en guide (leadgenerering) | Intet at teste |
| 3 | dansk konto ("Trading er held") | Én TradingView-replay på et indeksdiagram, 17/7/2025 omkring kl. 14:30 (US-datafrigivelse): indgang i en "gap"-zone efter nyhedslyset, target "Data High", "BE" | **Nej.** Skønsbaseret ICT-stil uden faste regler | Én udvalgt historisk replay | NOT_REPLICABLE_FROM_VIDEO |
| 4 | @fvllport | "Day 1 of using trading bot to pass 50K Funded" (FundedNext-udfordring, $299,99). Eget testværktøj: **21 strategier "DEAD"** (fx en kombineret rapport over 9.132 handler: t = −2,19, "no edge to trade"). **3 beholdt: +61,6 % over 2,9 år, maks. drawdown 7,85 %, PF 1,75, Sharpe 1,46** (MetaTrader 5 strategy tester, "real spread + financing") | **Nej.** De tre strategier oplyses ikke | Udvalgt efter cirka 24 forsøg; kun backtest; en betalt prop-udfordring (rigtige penge, alderskrav) | Se note nedenfor |
| 5 | @best.trading.bot | "Mobile bot / automatic trading bot system". MT5-mobil, guld (XAUUSD): saldo 30,72 → 746,11 → 6 × 5,46 lot med +$3.832 flydende | **Nej** | 6 × 5,46 lot guld er cirka 3.300 oz, nominelt cirka $16 mio. på en saldo på $1.732, med "Margin 0,01" og marginniveau 55.642.500 %. Det er ikke muligt på en almindelig konto og ligner demo eller redigering | Klassisk mønster for signalgrupper og ekspertrådgivere. Intet at teste |

**Note til #4.** Den eneste seriøse af de fem. Arbejdsmåden ligner lab'ets: dræb de fleste idéer. Men:
- Med cirka 24 forsøg og 2,9 år er den forventede **bedste** Sharpe blandt rene nul-strategier cirka 1,16. Det er
  Bailey og López de Prados forventede maksimum, med sd(SR) ≈ 1/√2,9 = 0,59.
- 1,46 ligger altså kun lidt over, hvad held alene giver. Der er ingen forward-observation.
- Testen sker i en prop-udfordring, der koster et gebyr, dvs. rigtige penge. Den er udelukket for lab'et under alle
  omstændigheder.

**Konklusion:**
- Ingen af de fem giver en ny, entydigt testbar regel.
- Intet nyt forsøg, ingen ny stream og ingen ny vært.
- Ordre 56 (fomo) og 57 (ORB-15) fortsætter uændret.

## Tillæg (2026-11-09 00:05 lokal): to videoer mere og et GitHub-repo

Ejeren sendte to videoer til og skrev: "The github is called TauricResearch/TradingAgents".

| # | Konto | Påstand | Testbar regel? | Røde flag | Vurdering |
|---|---|---|---|---|---|
| 6 | @ray_fu | "How to build a trading firm with AI agents": nyhedsanalytiker, risikoagent og porteføljeforvalter, der godkender en ordre (fx limit @ $89,50, stop $86,90, target $99,50, 2,1 % af porteføljen). Svarer til repo'et TauricResearch/TradingAgents | Kun som en ramme. Ingen fast regel; LLM-beslutninger kan ikke fryses som en formel | Kræver LLM-API-nøgler og nyheds-/fundamentaldata (nye værter). Forbudt for lab'et | Se TradingAgents nedenfor |
| 7 | @marlonnq | DeepSeek skriver en MQL5-EMA-crossover-EA ("NQBLADE") på "sixty seconds". MT5 strategy tester på NAS100 M3, 2025-01-01 til 2026-04-30, "CONGRATS" | Ja, i princippet (EMA-kryds), men parametrene vises ikke | Én backtest uden omkostningsanalyse og uden fremadtest; kontoen er hos en CFD-mægler | Lab'et har allerede falsificeret trendregler på timebasis (SOL-trend: alle varianter under købe-og-holde) og tsmom_v1 (FAIL). Intet nyt at teste |

**TauricResearch/TradingAgents** (Xiao m.fl., arXiv 2412.20138, revideret 2025-06):
- Sekundære kilder citerer for AAPL cirka 23–27 % kumulativt afkast, Sharpe 8,21 og maks. drawdown under 1 %. Tallene
  er UNVERIFIED: PDF'en er ikke læst i sessionen.
- Testperioden er få måneder i 2024 med 3 aktier. Kilderne er uenige om vinduet (jan–mar 2024 eller jun–nov 2024).
- **Det største problem er look-ahead.** Sprogmodeller trænet på data, der dækker 2024, "kender" udfaldet. En LLM-
  strategi kan kun testes troværdigt **fremad**, efter modellens vidensgrænse.
- Slippage og markedspåvirkning er ikke modelleret. En uafhængig kritik (DEV Community, ikke peer review) påstår, at
  papirets købe-og-holde-benchmark for AAPL har forkert fortegn (−5,23 % mod cirka +9 %).
- **For lab'et:**
  - kræver API-nøgler (forbudt), nye værter (nyheder, fundamentaldata) og løbende API-udgifter (rigtige penge);
  - lovligt kun som et designforslag til en fremadrettet papirtest efter godkendelse;
  - ingen kode hentes eller køres.
- **Vurdering:** interessant arkitektur, men ingen evidens for en fordel. Ikke prioriteret.
- **Opfølgning (ordre 58, LLM_FORWARD_VALIDITY.md):**
  - Papiret er VERIFIED fra arXiv v1 og v7. Testvinduet skiftede fra 2024-06-19..11-19 (v1) til 2024-01-01..03-29 (v7),
    men tabel 1 er identisk (AAPL 26,62 %, Sharpe 8,21).
  - GitHub-issue #203 "Clear look ahead bias" (VERIFIED): datahenterne returnerede realtidsinformation, og alle daglige
    beslutninger var BUY. Fejlen blev rettet 2026-03-29, efter alle papirets versioner.

## Tillæg 2 (2026-11-09 00:11 lokal): videoerne 8–10, et TikTok-link og en LinkedIn-artikel

| # | Kilde | Påstand | Testbar regel? | Vurdering |
|---|---|---|---|---|
| 8 | @dub9287 (sendt to gange, filerne er identiske) | "Deepseek 4.1 Uncensored X Opus 5.5". Skærmen viser et værktøj, der tjekker og "claimer" brugernavne via TikTok-, Instagram- og Discord-endpoints, plus et MT5-vindue | Nej | Ingen handelspåstand. Et brugernavn-claim-værktøj er i strid med platformenes vilkår, og lab'et bygger ikke den slags |
| 9 | @jessepbuilds | "Day 1: Building an agentic trading system" (hollandsk UI "JARVIS / TRADE-BRAIN"). Systemet ser trading-YouTube-videoer, udtrækker begreber (tidsserie-momentum på indeks-futures, displacement, fair value gap, order block, liquidity sweep) i en vidensgraf og har en "paper live"-side | Nej (ingen resultater, "Day 1") | **Idéen er brugbar som værktøj:** en video → påstand → regel → triage-pipeline. Det er præcis det, lab'et har gjort manuelt i aften. Se U6 i VIDEO_USABLE |
| 10 | @cotraderia | "6 years of trading rules in Obsidian … Claude built 7 AI agents. Each one checks a rule I used to break. I don't trade anymore. It does." | Nej (reglerne vises ikke) | Et disciplinlag, ikke en fordel. Lab'et har allerede fail-closed-gates, stopregler og factory-registret |
| – | TikTok-link vm.tiktok.com/ZN8f3LX94 → @dennisbayo.ai, fotoopslag 7665433523653823777 | Kunne ikke læses: siden kræver JS, oEmbed gav HTTP 400, og Chrome-fanen frøs. Der er ikke logget ind og ikke prøvet omveje | – | UNVERIFIED. Ejeren kan sende et skærmbillede |
| – | LinkedIn: Palak Jain, "I use Claude AI for trading every single day" | Claude som produktivitetsværktøj: scannere (Chartink/Screener.in), regnskabsresuméer, Python-backtest på Nifty (fx køb ved RSI < 35, sælg ved > 60), tjeklister | Kun eksempelregler, **ingen resultater** | Artiklen siger selv, at Claude ikke kan forudsige markedet. Den sælger mentorforløb. Ingen evidens |

## Tillæg 3 (2026-11-09 11:42 lokal): @jessepbuilds "Claude trading algorithm" (8-slides karrusel + "Day 12"-video)

| Påstand | Tal i slides | Vurdering |
|---|---|---|
| Agenter: scout, reader, summarizer, "recipe maker", engine og filter | 978 termer, 1.400+ idéer, 21 byggeklodser | Samme arkitektur som lab'et (factory, registre, evaluator). Ingen evidens i sig selv |
| Engine: 2,1 mio. lys, cirka 306 tests/t, 2.101 tests i dag | – | Backtest på **samme** historik hver dag |
| Filter: 2.101 → 388 "unseen data" → 189 "survive costs" → 62 "stable when tweaked" → **6 "beat pure luck"** | 0,3 % | Se nedenfor |
| "Checked again by a second, independent engine. Differences found: 0" | – | Svarer til lab'ets Codex-krydstjek (0 forskelle). Det beviser korrekt regning, ikke en fordel |
| Video "Day 12": equity-vifte (in- og out-of-sample), "First strategies testing ⏳" | 306 / 57 / 2,56 / 1,55 / 56 % | **Ingen forward-test og ingen rigtige handler endnu** |

**Held-tjek (U3):**
- Med N = 2.101 forsøg på én dag giver held alene en forventet bedste z på cirka 3,4. Ved α = 0,3 % pr. test forventes
  cirka 6 falske fund, præcis hans "6 beat pure luck", medmindre "luck"-filtret korrigerer for alle 2.101 (og for
  tidligere dages forsøg).
- "Unseen data" er kun usete første gang. Når tusindvis af strategier testes dagligt mod den samme reserverede periode,
  bliver den brugt op (lab'ets holdout-regel).

**Vurdering:**
- Et godt bygget forskningsværktøj, men slides'ene viser **ingen profit**, kun backtest-overlevere. Testen ville være:
  hvor mange af de 6 overlever fremadrettet på papir, efter omkostninger, med låste regler.
- Brugbart for lab'et: intet nyt; det bekræfter U3 og U6. Lab'et går længere med lås før data, holdout og
  forward-only. Det gør os langsommere, men giver resultater, man kan stole på.

## Tillæg 4 (2026-11-09 11:57 lokal): tre videoer mere

| # | Konto | Påstand | Testbar? | Vurdering |
|---|---|---|---|---|
| 11 | @ai.flow_lab (citerer X-opslag fra @Tec_with_Luis) | "Claude made him $7,625 overnight": "timezone arbitrage" der scanner japanske, europæiske, australske og mellemøstlige nyheder, som "US markets have yet to adjust" | Nej (ingen regel, ingen konto, ingen handler) | **Klassisk lead-funnel:** "Comment 'Guide', Like & RT, Follow … (first 1750 people)". Én påstået nat uden dokumentation. Mekanismen (US halter efter udenlandske nyheder) er lab'ets K1/K2/H27-A-familie og ONLINE_EDGES #8: informationen er allerede i prisen på 24/7-perps. Intet at teste |
| 12 | @buildwithbrock ("BMG Capital") | Værktøj der viser SEC Form 4-insiderhandler (Palantir: Thiel-salg $104,7 mio., 10b5-1-planer) | Ingen handelspåstand | Et datadashboard. 10b5-1-salg er forudplanlagte og bærer ringe information (kendt i litteraturen). Kræver SEC EDGAR (ikke en tilladt vært) og aktier (ingen venue for lab'et). Ikke prioriteret |
| 13 | @eshrobot | "Pure robot intelligence": MT5-historik med ~20 XAUUSD- og BTCUSD-handler, alle +130–140 | Nej | Kun vindende handler vises (tabsrækker er ude af billedet), ingen kontosaldo og ingen periode. Samme mønster som V05 (guld-"mobilbot"). Intet at teste |

**Konklusion:** ingen af de tre giver en ny testbar regel. Held-tjek (U3) er ikke relevant, fordi ingen statistik er
vist. Optællingen er nu 13 videoer, 1 karrusel, 1 artikel og 1 repo; 0 er REPLICABLE.
