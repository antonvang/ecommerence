# PROTOCOL v3 — bindende (skrevet 2026-10-17, før nogen data til disse idéer er læst)

**Gælder:** de 8 idéer fra `research/NAESTE_IDEER_UDKAST.md`, med eksperiment-id `E_<skabelon>_p3`.
**Beslutning:** brugeren valgte alle 8 idéer (idé 8 med den begrundelse, der står nedenfor, og idé 7 med volumenandel som
erstatning for dominans). Brugeren gav tilladelse til at fortsætte med anbefalingen i
`research/DIAGNOSE_HVORFOR_INTET_BESTAAR.md`: længere data fra flere markedsregimer.
**Uændret:** v1- og v2-resultater forbliver præcis, som de er registreret.

## 1. Hvad er nyt i forhold til v2 — og hvad er ikke

Kun vinduerne og universet er nye. **Alle krav (gates) er identiske med v2:**
- **Train-gate:** den valgte variant skal have netto-Sharpe > 0 og over købe-og-holde på træning.
- **Før-validerings-gate:** eksakte look-ahead- og poison-tests, datakvalitet, og placebo p < 0,10.
- **Batch-DSR:** held-tjek ≥ 0,95 over alle forsøg til og med batch-cutoff plus batchens egne forsøg.
- **Validerings-gates:** netto-gennemsnit > 0, ensidet 90 % nedre grænse > 0 (5-dages blokke, 2.000 træk, seed 7),
  netto-Sharpe over købe-og-holde, netto total > 0 ved dobbelte omkostninger, held-tjek ≥ 0,95, og
  valideringsdatakvalitet.
- **Slut-test og paper:** slut-test (holdout) og simuleret handel kræver hver en menneskelig godkendelse. Slut-testen åbnes én gang.

Omkostninger pr. omsætning (uændret):
- taker-gebyr 0,05 %;
- halv spread 0,02 % (ESTIMAT);
- slippage 0,02 % (ESTIMAT);
- plus afregnet funding fra data.

Benchmark: lige-vægtet købe-og-hold af idéens eget univers, med samme omkostninger.

## 2. Vinduer

| Vindue | Periode | Brug |
|---|---|---|
| Træning | 2022-01-01 – 2023-06-30 | Valg af variant, train-gate, før-validerings-gate |
| Validering | 2023-07-01 – 2023-12-31 | Validerings-gates |
| Slut-test | 2024-01-01 – 2024-12-31 | Forseglet; kun efter menneskelig godkendelse; én gang |
| Reserveret | 2025-01-01 → | Læses aldrig |

**Opvarmning.** Signaler bruger kun data inden for det vindue, der evalueres. Der overføres ikke historik mellem
vinduerne, så positioner starter først, når et signals tilbagekig er fyldt.

**Ærlig note.** Valget af vinduer er påvirket af, at vi har set, at efteråret 2023 var et rally. Det gælder alle 8 idéer
ens, og ingen idé er tunet på det.

## 3. Univers

**Regel:**
- Samme ordnede kandidatliste som i PROTOCOL v2, ændring 3.
- Tag de første 30 symboler, der har månedlige 1h-klines **og** funding-filer for hver måned 2022-01..2024-12.
- Tjekket kun med HTTP HEAD, uden at læse indhold.

**Resultat 2026-10-17:**
- **Ud:** ICP mangler funding-filer for 2022, og APE blev først listet i marts 2022.
- **Universet er:** BTC ETH BNB XRP SOL ADA DOGE TRX DOT LINK AVAX LTC BCH ATOM ETC XLM NEAR FIL UNI AAVE ALGO VET EOS XTZ
  THETA AXS SAND MANA CRV SNX (alle `USDT`-perps).
- **Undtagelse:** idé 5 bruger kun BTCUSDT og ETHUSDT.

**Datakvalitet:**
- **Fejler et symbol et vindue,** udelukkes det fra eksperimentet i det vindue, før noget afkast beregnes. Kravet er dækning ≥ 99 % for klines, ≥ 95 % gyldige dage for metrics, ingen dubletter og stigende tidsstempler.
- **Mindst 24 af 30 symboler** skal være tilbage, ellers fejler data-gaten.
- **Idé 5** kræver begge sine 2 symboler.
- **Ekstern serie (DVOL, stablecoins):** dækker den færre end 95 % af vinduets dage, fejler data-gaten.

## 4. Data

| Kilde | Hvad | Hvordan |
|---|---|---|
| Binance klines (månedlige zip) | kurser, dollar-volumen (kolonne 8), aggressive køb i dollar (kolonne 11, "taker buy quote volume") | som i dag |
| Binance metrics (daglige zip, 5-min rækker) | `sum_open_interest_value`, `sum_toptrader_long_short_ratio` (top-tradere efter position), `count_long_short_ratio` (alle konti) | Dagsværdi for dag D: open interest = sidste række i D; forhold = gennemsnit over D. En dag er gyldig med ≥ 200 af 288 rækker. Pr. symbol og vindue samles dagene i én fil med SHA-256-manifest over kildefilerne; gatewayen registrerer den samlede fil. |
| Deribit DVOL (gratis offentlig API) | 30-dages implicit volatilitet, BTC og ETH | `public/get_volatility_index_data`, opløsning 1 dag, start- og slut-tid = vinduets grænser. Dagsværdi = lukkekurs. Gemmes pr. vindue. |
| DefiLlama (gratis offentlig API) | samlet stablecoin-mængde i USD | `stablecoins.llama.fi/stablecoincharts/all` returnerer altid hele historikken. **Downloaderen beholder kun rækker inden for det ønskede vindue og kasserer resten, før noget beregnes. Kun vinduets rækker gemmes.** |

**Tidsregel.** En dagsværdi for dag D må først bruges fra D+1 00:00 UTC. Kursdata må kun bruges fra bars, der er lukket.

## 5. De 8 idéer

**Fælles for de tværgående idéer (1, 2, 3, 8):**
- **Hvornår:** ombalancering hver mandag 00:00 UTC.
- **Hvad:** køb de 5 højeste scores (+1) og sælg de 5 laveste (−1). Mindst 10 symboler skal have en score.
- **Vægtning:** porteføljen vægter alle symboler lige.

**Modbevisning:** hver idé er modbevist, hvis den fejler en af gaterne i afsnit 1. Beslutningen registreres automatisk
som et resultat med begrundelse og en livscyklus-overgang (REJECTED eller SCREEN_PASSED).

| # | Skabelon | Mekanisme-tag | Regel | Varianter | Kilde (DOI verificeret i Crossref) |
|---|---|---|---|---|---|
| 1 | `oi_growth` | open_interest_growth | score = open interest-værdi (seneste hele dag) / værdien L dage tidligere − 1 | L = 7 / 28 | Hong & Yogo 2012, JFE, 10.1016/j.jfineco.2012.04.005 |
| 2 | `oi_confirmed_return` | oi_confirmed_trend | r = kursafkast over L dage; g = open interest-vækst over samme L dage; score = r hvis g > 0, ellers −r | L = 7 / 14 | Bessembinder & Seguin 1993, JFQA, 10.2307/2331149 |
| 3 | `smart_vs_crowd` | informed_positioning_divergence | score = gennemsnit over de sidste L gyldige dage af ln(top-traderes forhold) − ln(alle kontoers forhold); kræver ≥ L−1 gyldige dage | L = 7 / 14 | Wang 2003, J. Futures Markets, 10.1002/fut.10056 |
| 4 | `leverage_cycle` | leverage_cycle_timing | dagligt 00:00: G = ln(samlet OI-værdi i dag / for L dage siden) − ln(1 + markedsafkast over L dage). Position for alle symboler: 0, hvis G ≥ 2/3-kvantilen af de foregående 90 daglige G-værdier (kræver ≥ 60); ellers +1 | L = 7 / 14 | Geanakoplos 2010, NBER Macroeconomics Annual, 10.1086/648285 |
| 5 | `vrp_timing` | variance_risk_premium_timing | dagligt 00:00 pr. mønt (BTC, ETH): IV = DVOL (gårsdagens lukning)/100; RV = std. af timelog-afkast over 14 dage × √(24·365); præmie = IV² − RV². +1 hvis præmien er over medianen (A) / 2/3-kvantilen (B) af de foregående 30 daglige værdier (kræver 30); ellers 0 | A / B | Bollerslev, Tauchen & Zhou 2009, RFS, 10.1093/rfs/hhp008 |
| 6 | `stablecoin_flow` | stablecoin_liquidity_flow | dagligt 00:00: g = stablecoin-mængde (i går) / mængde 7 dage før − 1. A: g > 0 → +1 for alle symboler. B: g over medianen af de foregående 30 daglige g (kræver 30) → +1. Ellers 0 | A / B | Griffin & Shams 2020, J. Finance, 10.1111/jofi.12903 |
| 7 | `btc_volume_share` | btc_dominance_rotation | dagligt 00:00: BTC's andel af den samlede dollar-volumen; gennemsnit af de sidste L dage mod de L dage før. Steget → BTC +1 og hver af de andre −1/(n−1); faldet → omvendt; uændret → 0 (dollar-neutral) | L = 7 / 14 | ingen direkte kilde — ren hypotese (brugerens valg); volumenandel er erstatning for markedsværdi-dominans |
| 8 | `taker_pressure` | orderflow_imbalance | daglig andel aggressive køb = Σ taker-køb / Σ dollar-volumen; score = gennemsnit over de sidste F dage − gennemsnit over de 60 dage før | F = 7 / 14 | Chordia & Subrahmanyam 2004, JFE, 10.1016/S0304-405X(03)00175-2 |

Idé 4, 5 og 6 holder kun lange positioner og sammenlignes med købe-og-holde af deres eget univers.

## 6. Idé 8 og graveyard

`orderflow_imbalance` er allerede afvist (L20: ordrestrøms-ubalance på BTC på minut-niveau, afvist på grund af
omkostninger ved den høje omsætning). Graveyard sorterer derfor `E_taker_pressure_p3` fra automatisk.

**Genoplivning.** Den genoplives kun gennem den menneskelige overgang SUPPRESSED → DISCOVERED med denne begrundelse:
"materially different because it is a daily, cross-sectional signal over 30 coins with weekly rebalancing, whereas L20 was a
minute-level order-flow signal on BTC alone that failed on costs at that turnover". Brugeren har godkendt begrundelsen.

## 7. Simuleret handel (paper)

Paper-motoren har endnu ikke live-data for open interest, long/short-forhold, DVOL og stablecoins.
- **Hvis en v3-idé består slut-testen,** bygges og testes live-dataforbindelsen, før en paper-godkendelse kan gives.
- **Indtil da** afviser paper-motoren disse skabeloner uden at handle.

## Ændring 1 (2026-10-17, før nogen v3-data er læst og før nogen slut-test er åbnet)

**Fund.** BTC, ETH og SOL's data for 2024–2026 blev allerede set, da `L14_tsmom_v1` åbnede sin slut-test (derfor var
de udelukket fra det oprindelige 8-mønt-univers). Deres 2024-data er altså ikke usete.

**Regel:**
- **Hvilke mønter.** I slut-testen (2024) for alle eksperimenter med 30-mønt-universer (PROTOCOL v2 ændring 3 og v3) udelukkes BTCUSDT, ETHUSDT og SOLUSDT, før noget afkast beregnes. Kravet om mindst 24 symboler gælder fortsat.
- **Idé 5 (`vrp_timing`, kun BTC/ETH) og idé 7 (`btc_volume_share`, bygger på BTC)** kan derfor ikke få en ren slut-test. Består en af dem valideringen, kan den ikke sendes videre til simuleret handel på grundlag af 2024. Den markeres som "ingen ren slut-test mulig" og afventer data, der er usete (tidligst 2025-data, som er reserveret og kræver en ny, separat beslutning).
- **Træning og validering (2022–2023)** er ikke berørt. Disse år er ikke en slut-test for noget tidligere eksperiment på disse idéer.

## Resultat (kørt 2026-10-17, 19:37–19:47; registreret automatisk, ingen ændringer bagefter)

Batch `B-02bfcefdcd90` = alle 8 idéer, cutoff for forsøg 34 (i alt 50 forsøg i held-tjekket).
- **Kørsel:** 48 jobs, 0 fejl, 0 gentagelser.
- **Data:** 16.380 daglige metrics-filer hentet, og ingen symboler udelukket.
- **Hukommelse:** målt 150–350 MB pr. worker-proces.
- **Benchmark:** købe-og-holde på træning (2022-01..2023-06) havde netto-Sharpe −0,52. Det er et fair benchmark, der omfatter bjørnemarkedet.

| Idé | Valgt variant | Træning netto-Sharpe | Placebo p | Validering netto-Sharpe / netto total (købe-og-holde Sharpe) | Held-tjek | Afgørelse |
|---|---|---|---|---|---|---|
| Åben-interesse-vækst | 7 dage | −0,18 | — | ikke læst | — | Afvist i første test (netto ≤ 0) |
| Ny penge eller short-dækning | 14 dage | −0,45 | — | ikke læst | — | Afvist i første test |
| Smart money mod flokken | 7 dage | 0,55 | **0,100** | ikke læst | — | Afvist før validering (kravet er p < 0,10) |
| Gearings-cyklus | 7 dage | −0,62 | — | ikke læst | — | Afvist i første test |
| Frygtpræmie (BTC/ETH) | øverste tredjedel | 0,57 | 0,033 | 0,94 / +13,3 % (1,26) | 0,046 | Afvist i anden test (under købe-og-holde, held-tjek, nedre grænse ≤ 0) |
| Stablecoin-tilførsel | over median | −0,31 | — | ikke læst | — | Afvist i første test |
| Bitcoin-dominans (volumen) | 7 dage | 0,75 | 0,017 | 0,76 / +0,4 % (2,02) | 0,035 | Afvist i anden test |
| Købspres | 14 dage | −0,10 | — | ikke læst | — | Afvist i første test |

Ingen idé bestod. Slut-testen for 2024 er ikke åbnet, og intet er sendt til simuleret handel.

Hvad vi lærer til næste retning:
- **Positionsdata (open interest, gearing, købspres) gav intet på tværs af mønter** efter gebyrer. Alle fire fejlede allerede i træning.
- **De to idéer, der var positive uden for træning (Frygtpræmie, Bitcoin-dominans), er tidsstyrede eller relative.** De slog ikke købe-og-holde i rallyet i andet halvår 2023, og usikkerheden omfattede nul.
- **Held-tjekket er nu meget strengt (50 forsøg).** Næste runde bør derfor være få, stærkt begrundede idéer frem for mange, ellers kan intet bestå.

## Ændring 2 (2026-10-18): fremadrettet observationstest og 3 nye idéer — før kode og før data

**Beslutning:** brugeren valgte "valg B" i `research/NAESTE_IDEER_RUNDE2_UDKAST.md` og at registrere alle 3 idéer.
**Gælder:** kun eksperimenter, der registreres efter denne ændring. Alle tidligere resultater er uændrede.

### A. Observationstesten (bindende)

1. **Hvem.** Et eksperiment kommer på observationslisten, hvis det består train-gaten, før-validerings-gaten og
   **alle** validerings-krav **undtagen** held-tjekket (deflateret Sharpe ≥ 0,95). Resultatet registreres som
   "OBSERVE (forward test)", og livscyklussen går automatisk SCREENING → OBSERVATION. Fejler noget andet krav, er det
   REJECTED som før.
2. **Vinduet.** Det starter 00:00 UTC den 1. i måneden efter overgangen til OBSERVATION og varer 6 hele kalendermåneder.
   **Data fra vinduet læses ikke, før vinduet er slut.** Evalueringen kører tidligst 7 dage efter vinduets slutning,
   når Binances månedsfiler er offentliggjort. Koden nægter at læse et vindue, der ikke er slut.
3. **Frosset.** Skabelon, den valgte variant og dens parametre, univers (alle symboler; vinduet er uset for alle),
   omkostningsmodel og datakilder er frosset.
4. **Krav i vinduet:**
   - netto-gennemsnit pr. dag > 0;
   - ensidet 90 % nedre grænse > 0 (5-dages blokke, 2.000 træk, seed 7);
   - netto-Sharpe over lige-vægtet købe-og-holde af samme univers;
   - netto total > 0 ved dobbelte omkostninger;
   - datakvalitet efter de sædvanlige regler;
   - **held-tjek fremad:** sandsynlig Sharpe (PSR mod 0, skævhed 0, kurtosis 3) ≥ 1 − 0,05/N. Her er N antallet af
     eksperimenter med samme observationsvindue. N ligger fast, når vinduet starter.
5. **Udfald:** består alt → SCREEN_PASSED. Derefter gælder de sædvanlige menneskelige godkendelser: slut-test 2024
   (uden BTC/ETH/SOL) og simuleret handel. Fejler noget → REJECTED, og resultatet registreres.
6. **Reserverede data.** Perioden fra 2025-01-01 til observationsvinduets start forbliver reserveret og læses aldrig.
7. Alt er simuleret. Ingen rigtige penge.

### B. De 3 idéer

**Fælles:** PROTOCOL v3-vinduer og -krav som før (træning 2022-01..2023-06, validering 2023-07..2023-12, slut-test
2024 uden BTC/ETH/SOL), samme omkostninger. Benchmark er lige-vægtet købe-og-holde af idéens univers.

**CM16-univers:** de 16 mønter, hvor CoinMetrics' gratis community-API har daglige `SplyCur` og `CapMVRVCur` for
2022–2024. Tjekket i API'ets katalog, kun metadata. Mønterne er XRP ADA DOGE LINK LTC BCH ETC XLM UNI AAVE ALGO MANA
CRV SNX BTC ETH (Binance `USDT`-perps). Mindst 12 symboler kræves (i slut-testen 14 uden BTC/ETH). Tværgående bøger
køber de 3 højeste scores og sælger de 3 laveste (eller omvendt, hvor det står). Mindst 6 symboler skal have en score.

| # | Skabelon | Mekanisme-tag | Regel | Varianter | Kilde (verificeret i Crossref) |
|---|---|---|---|---|---|
| 1 | `real_rate_filter` | real_rate_timing | Dagligt 00:00. FRED DFII10 (10-årig realrente); en observation for dato D bruges først fra D + 2 dage. Ændring = seneste værdi minus værdien n observationer før. ≤ 0 → +1 for alle 30 v3-mønter, ellers 0. 0 indtil der er n + 1 observationer i vinduet. | n = 20 / 60 | Bernanke & Kuttner 2005, J. Finance, 10.1111/j.1540-6261.2005.00760.x |
| 2 | `supply_dilution` | supply_dilution | Hver mandag. Udvanding = SplyCur(i går) / SplyCur(L dage før) − 1. Køb de 3 med lavest udvanding, sælg de 3 med højest. CM16. | L = 30 / 90 | Pontiff & Woodgate 2008, J. Finance, 10.1111/j.1540-6261.2008.01335.x |
| 3 | `mvrv_value` | onchain_value_mvrv | Hver mandag. A: score = MVRV(i går). B: MVRV(i går) / gennemsnit af MVRV over de 90 dage før. Køb de 3 laveste, sælg de 3 højeste. CM16. | A / B | Asness, Moskowitz & Pedersen 2013, J. Finance, 10.1111/jofi.12021; Campbell & Shiller 1988, RFS, 10.1093/rfs/1.3.195 |

**Data (gratis, ingen nøgler; alle forespørgsler er begrænset til vinduet):**
- **FRED:** `fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10&cosd=<start>&coed=<slut>`.
- **CoinMetrics:** `community-api.coinmetrics.io/v4/timeseries/asset-metrics`, med `start_time`/`end_time` = vinduet og
  side-opdelt. En CoinMetrics-dagsværdi for dag D bruges først fra D + 1 dag.

**Dækning:** en ekstern serie, der dækker færre end 95 % af vinduets dage (FRED: handelsdage, mindst 90 % af hverdage),
fejler data-gaten for idéen. Et symbol med under 95 % CoinMetrics-dækning udelukkes.

### Registrering (2026-10-18)

- **Godkendelse.** `real_rate_filter`, `supply_dilution` og `mvrv_value` er godkendt til test. Claude bekræftede på brugerens instruks, hvilket er logget som `approval.note`.
- **Registrering.** De tre er registreret som én batch `B-e794bc210975` (cutoff for forsøg 50) med `observation_test` slået til.
- **Data.** Der er ikke læst nogen data. Jobbene står i køen og kører, når flåden startes.

### Resultat for batch `B-e794bc210975` (kørt 2026-10-18, 08:3x–08:52 UTC; registreret automatisk)

- **Kørsel:** 18 jobs, 0 fejl.
- **Data:** ingen symboler udelukket. FRED og CoinMetrics blev læst gennem gatewayen, kun for vinduerne.
- **RAM:** flåden holdt pause for RAM fire gange (sikkerhedsgrænsen virkede som tiltænkt).

| Idé | Valgt variant | Træning netto-Sharpe (købe-og-holde) | Placebo p | Validering netto-Sharpe / netto / max drawdown (købe-og-holde Sharpe) | Held-tjek | Afgørelse |
|---|---|---|---|---|---|---|
| Realrente-filter | n = 60 | 1,30 (−0,52) | 0,000 | 1,29 / +10,8 % / 5,9 % (2,02) | 0,080 | REJECTED: under købe-og-holde, nedre grænse ≤ 0, held-tjek |
| Udvanding | 30 dage | −0,57 (−0,35) | — | ikke læst | — | REJECTED i første test |
| Værdi på kæden (MVRV) | niveau | 1,03 (−0,35) | 0,000 | **2,48 / +9,7 % / 3,0 % (1,44)** | 0,287 | **OBSERVATION**: bestod alle krav undtagen held-tjekket |

**MVRV er det første eksperiment, der har bestået alle andre krav:**
- slog købe-og-holde både i træning og validering;
- positivt efter dobbelte omkostninger;
- nedre usikkerhedsgrænse over 0;
- klart bedre end placebo.

Held-tjekket på 0,287 er langt under 0,95. Efter ændring 2 betyder det:
- **Observationsvindue:** strategien observeres nu på helt nye data, **2026-11-01 – 2027-04-30**.
- **Evaluering:** den kører automatisk tidligst **2027-05-07** (jobbet `observe|E_mvrv_value_p3` står i køen), når flåden kører.
- **Ingen tidlig læsning:** data fra vinduet kan ikke læses før.
- **Holdt tilbage:** intet er sendt til simuleret handel, og 2024-slut-testen er ikke åbnet.

## Ændring 3 (2026-10-18): skyggehandel for kandidater på observationslisten — før kode

**Beslutning:** brugeren bad om simuleret skyggehandel for kandidater på observationslisten (nu MVRV). Den vises tydeligt
mærket i dashboardet og må ikke påvirke de formelle tests.

1. **Hvad.**
   - Et eksperiment i OBSERVATION kan få en separat, simuleret konto ("skyggekonto", id `SHADOW_<eksperiment>`).
   - Kontoen handler den frosne strategi live: samme variant, parametre, univers og omkostninger.
   - Startkapitalen er 10.000 USD (simuleret).
   - Ingen rigtige penge, ingen ordrer til en børs og ingen nøgler.
2. **Hvornår.**
   - Kun efter en menneskelig start pr. eksperiment (`shadow.approved`, actor `human:`); den kan stoppes på samme måde (`shadow.stopped`).
   - Den stopper automatisk, når eksperimentet forlader OBSERVATION.
   - Risiko-breakers (drawdown, data, spread) pauser den som enhver paper-konto.
3. **Ingen effekt på de formelle tests.**
   - Skyggekontoen skriver ingen resultater, livscyklus-overgange eller trials for eksperimentet.
   - Observationstestens evaluering (ændring 2) kører uændret og læser fortsat først vinduets historiske data, når vinduet er slut.
   - Skyggekontoen ser de samme live-markeder undervejs. **Dens resultater må ikke bruges til nogen beslutning om eksperimentet**, hverken at stoppe, ændre eller fremskynde det. Afgørelsen er udelukkende den automatiske observationstest.
4. **Data.**
   - Offentlige Binance REST-data som den eksisterende paper-motor: lukkede 1h-bars, funding og en ordrebog med 20 niveauer.
   - CoinMetrics community-API for de seneste 120 dage frem til i går (dagsværdi for dag D bruges fra D+1).
   - Fejler en datakilde, pauses kontoen (ingen handel).
5. **Visning.**
   - Skyggekonti vises i dashboardets saldo- og paper-dele med mærket "skyggehandel (simuleret, ikke godkendt)".
   - De vises aldrig som godkendt strategi eller som rigtig indtjening. Rigtig konto er fortsat "ikke tilgængelig".

## Ændring 4 (2026-10-18): automatisk promovering gennem én central beslutningsfunktion — før kode

**Beslutning:** brugeren bad om en automatisk kæde fra hypotese til godkendt paper trading uden manuel godkendelse pr.
strategi. Brugeren har givet tilladelse til at slå den til (logget). Ingen tærskel ændres. Beslutningerne bygger
udelukkende på de registrerede resultater af de eksisterende gates.

1. **Politik.**
   - Automatikken er aktiv, når den seneste `policy.autopromote`-hændelse er `on` og er skrevet af en `human:`-aktør.
   - Den kan slås fra igen; så venter alt på menneskelig godkendelse som før.
2. **Én beslutningsfunktion (`lab/promotion.py: decide`).**
   - Det er den eneste kode, der kan udføre de to automatiske overgange nedenfor.
   - Hver beslutning (ja eller nej med årsag) skrives som en `promotion.decision`-hændelse med sin evidens.
   - Ingen worker, CLI, dashboard-knap, shadow- eller paper-runner har en anden vej.
3. **SCREEN_PASSED → VALIDATION** (åbner slut-testen 2024 én gang). Kræver:
   - seneste resultat er en PASS: enten screen-PASS, hvor alle validerings-krav inkl. held-tjek er bestået, eller fremad-PASS fra observationstesten;
   - skabelonen har en ren slut-test (ikke `vrp_timing`/`btc_volume_share`, jf. ændring 1);
   - laben er ikke FAIL_CLOSED, og supervisoren har slået puls inden for 30 s.
4. **VALIDATED → PAPER_TRADING.** Kræver:
   - seneste VALIDATION-resultat er en slut-test-PASS;
   - paper-motoren har live-data for skabelonen (ellers venter den);
   - laben er ikke FAIL_CLOSED, ressourcerne er OK, og alle paper-konti afstemmer.
5. **Lukket gate = vent.** Hvis en betingelse ikke er opfyldt, registreres "venter: <årsag>", og intet sker.
   Observation (ændring 2) og tidsbaserede gates håndhæves fortsat af koden.
6. **Ordre-verifikation.**
   - Paper-runneren åbner kun nye positioner for en godkendt strategi, hvis `promotion.trading_authorized` kan verificere: lifecycle PAPER_TRADING, og overgangen dertil citerer enten en menneskelig godkendelse eller en `promotion.decision`, der var tilladt.
   - Alle risiko-regler gælder som før.
7. **Positionspolitik.**
   - **Pause:** ingen nye positioner; eksisterende beholdes og opgøres hver time; kun reducerende ordrer er tilladt.
   - **REJECTED/RETIRED efter paper:** alle positioner lukkes med reducerende ordrer ved næste kørsel.
   - **Genstart:** konti og ordre-id'er er idempotente, så der opstår ingen dubletter, og positionerne fortsætter efter opvarmning.
8. **Skyggehandel (ændring 3) er adskilt.**
   - Beslutningsfunktionen læser aldrig skyggekonti eller deres resultater.
   - Skyggehandel kan ikke ændre status eller udløse godkendelse.
   - MVRV er fortsat i OBSERVATION og venter på observationstesten.
9. **Ingen rigtige penge, ingen gearing, ingen broker.**

### Ændring 4a (2026-10-18): præciseringer fra produktionsaudit — strammere, ingen tærskel ændret, før kode

Audit af alle veje til en ordre viste, at verifikationen kun lå i paper-runneren. Disse regler gør den bindende overalt:

1. **Én gate for ny eksponering.** Motorens fælles risiko-gate (`Risk.entry_allowed`, som hver simuleret ordre
   passerer, også ved direkte motor-kald) kræver for ikke-reducerende ordrer: verificerbar godkendelse
   (`promotion.trading_authorized`) og supervisor-puls inden for 30 s. Det gælder også skyggekonti (puls-delen).
   Reducerende ordrer kræver ingen af delene, så lukning altid er mulig.
2. **Verificerbar godkendelse.**
   - **Menneskelig:** overgangen citerer en `approval_id`; godkendelsen findes for samme eksperiment og samme
     målstatus, og der findes præcis én `approval.used` for den, skrevet af samme aktør som overgangen.
   - **Automatisk:** overgangen er fra VALIDATED, citerer en tilladt `promotion.decision` for samme eksperiment,
     samme fra- og til-status og samme spec-version og -fingeraftryk. Beslutningen er brugt præcis én gang
     (`promotion.used`), og det citerede resultat er dette eksperiments slut-test-PASS.
   - En beslutning kan kun bruges inden for 60 s og kun én gang. Den kan ikke genbruges til et andet skridt eller
     eksperiment.
3. **Udløb.** En automatisk godkendelse giver kun ny eksponering, mens politikken stadig er slået til. Slås
   `autopromote` fra, holdes og opgøres positionerne og kan reduceres, men der åbnes ingen nye.
4. **Kun PROTOCOL v3.** Den automatiske vej gælder kun eksperimenter registreret under PROTOCOL v3 (hvor ændring 4
   står). Ældre protokoller venter på menneskelig godkendelse som før.
5. **PASS præciseret.** SCREEN_PASSED → VALIDATION kræver, at seneste resultat er netop `PASS (screen)` eller
   `PASS (forward test)`.

## Ændring 5 (2026-10-18): forskningsmotoren — hændelser, diagnoser og et strammere holdout-krav — før kode

Baggrund: en audit (2026-10-18) viste, at laboratoriet er en verificeret batch-screener. Alle 28 skabeloner i
kataloget er brugt, scannerens fund fører aldrig til en registreret beslutning, og der er ingen opfølgning på, hvorfor
tidligere idéer fejlede. Ændringen gør ingen eksisterende regel lempeligere. Afgørelser og resultater for v1–v3 står,
som de er registreret, og frosne artefakter overskrives aldrig.

1. **Strammere slut-test.** Holdout-trinnet får gaten "holdout data quality (min symbols)": slut-testen består kun,
   hvis der er data for mindst `min_symbols` symboler efter udelukkelser (samme krav som i screening). Ingen
   slut-test er åbnet endnu, så intet resultat ændres.

2. **Markedshændelser er registreringer, ikke handler.**
   - Scanneren skriver for hvert forslag en hændelse `market.event` med detektor, instrument, målt værdi i forhold
     til tærsklen, varighed, kilde og datakvalitet, samt en beslutning med begrundelse:
     - `NO_ACTION`: venter på varighed, ligger i kirkegården, er dækket af et aktivt eksperiment, eller datakilden
       fejlede;
     - `INVESTIGATE`: et nyt fingeraftryk, der har varet.
   - Hændelserne ændrer ingen tilstand, starter ingen handel og indgår ikke i nogen gate.
   - En `INVESTIGATE` kan kun føre til en test gennem en senere forhåndsregistreret skabelon. Data fra 2025 og frem er
     reserveret, så scannerfund kan kun testes fremadrettet.
3. **Fejlrettelser i scanneren** (ingen ny regel):
   - En kandidat i tilstanden `SUPPRESSED` behandles som kirkegård på linje med `REJECTED` og `WITHDRAWN`.
   - "Varighed" tæller nu de forskellige klokketimer med flag inden for de seneste 24 timer og for samme instrument,
     når forslaget har et instrument. Før talte den hele historikken, så to ubeslægtede flag kunne opfylde kravet.
4. **Diagnoser er ikke-afgørende.**
   - Et nyt jobtrin `diagnose` analyserer den allerede registrerede daglige nettoserie (`validate.json`, verificeret
     mod sin SHA-256) for afsluttede eksperimenter:
     - stabilitet over tredjedele og halvdele;
     - koncentration på de bedste dage;
     - dybeste tab og længste tabsperiode;
     - eksponering.
   - Trinnet læser ingen markedsdata og ingen nye split, og skriver kun i `artifacts/_diagnostic/`.
   - Det skriver ingen rækker i results, trials eller transitions og ændrer ingen afgørelse. Det registreres som
     hændelsen `research.diagnostic`.
5. **Fejlrettelse i datagatewayen** (ingen ny regel): stier gemmes med `/`, og tidligere læsninger slås op i både `/`-
   og `\`-form. Så gælder kravet "en fil må ikke ændre sig efter første læsning" også for data læst første gang på
   Windows.

## Ændring 6 (2026-10-18): jobkøens robusthed — afbrudte jobs, låst database og trials — før kode

Baggrund: en isoleret verifikation af stopkoden (2026-10-18) viste fem driftsfejl i jobkøen og flåden:
- et planlagt stop, der afbryder et job, blev bagefter registreret som `job.timeout` og brugte et forsøg (to stop
  under et holdout-job kunne gøre det til `job.failed`);
- `jobs.recover` kørte, efter at flådens workers var startet, og kunne udløbe et job, den nye flåde lige havde taget;
- efter at én jobproces var død, fejlede alle senere tunge jobs, indtil flåden blev genstartet;
- en anden proces, der holdt databasens skrivelås i over 30 s, fik flåden til at stoppe med exit 1;
- et cost-trin, der blev kørt igen efter et afbrudt stop, skrev en ekstra trials-række for hver variant.

Ændringen gør ingen gate lempeligere og ændrer ingen registreret afgørelse. Live-databasen har 56 trials-rækker for
56 forskellige (eksperiment, variant, split), så ingen tidligere DSR påvirkes.

1. **Et planlagt stop er ikke en fejl.**
   - Når et stop afbryder et job, lægges det straks tilbage i køen med hændelsen `job.interrupted`, og forsøget
     gives tilbage. Der skrives ingen `job.timeout`, `job.retry` eller `job.failed`, og det tæller ikke som fejl.
   - Det gælder også, når jobprocessen dør først, fordi hele procesgruppen fik SIGTERM (pc'en lukker ned). Flåden
     venter højst 3 s på, at stoppet bliver registreret, før den kalder det en fejl.
   - Kan tilbagelægningen ikke skrives, kører `jobs.recover` jobbet igen efter næste start som før.
2. **Leases ryddes, før workers starter.** `jobs.recover` kører før den første worker. Så udløber kun leases fra en
   død proces.
3. **En ødelagt jobpulje erstattes.** Dør en jobproces uden et stop (fx OOM), får næste tunge job en ny pulje. Det
   afbrudte job tæller som et almindeligt fejlet forsøg (`job.retry`).
4. **En låst database stopper ikke flåden.**
   - Holder en anden proces skrivelåsen længere end SQLite's ventetid (30 s), venter supervisoren og agenterne den
     ud i stedet for at stoppe.
   - Episoden registreres bagefter som `system.db_busy` med varighed. Andre databasefejl behandles som før.
5. **Et trial er én testet variant.** Køres et cost-trin igen, skrives der ingen ekstra trials-række for en variant,
   der allerede er registreret for samme eksperiment og split. Antallet af trials i DSR er dermed antallet af testede
   varianter. Ingen tidligere række ændres eller fjernes.

## Ændring 7 (2026-10-18): fremadtest på papir, pauseregler for simulerede konti og holdout som ét filsæt — før kode

Baggrund: brugeren besluttede 2026-10-18 i sessionen:
- fremadtest-konti for de frosne strategier, der kan handles live i dag, startet nu;
- skyggekonti følger pausereglerne i ændring 3 §2, plus en menneskelig genoptag-kommando;
- holdout-fejlen rettes som en dokumenteret fejlrettelse.

Ingen gate for de formelle tests lempes, ingen tærskel ændres, og ingen registreret afgørelse ændres.

1. **Pauseregler for simulerede konti** (`SHADOW_<eksperiment>` fra ændring 3 og `FWD_<eksperiment>` herunder).
   - Kun drawdown (10 %), data og spread pauser en simuleret konto, som ændring 3 §2 siger. Reglen "2 tab i træk"
     gælder ikke for disse konti. For godkendt papirhandel gælder alle regler uændret.
   - Under pause åbnes intet nyt. Positionerne beholdes og opgøres hver time (ændring 4 §7).
   - Kun et menneske kan genoptage en pauset simuleret konto: `python3 -m lab sim-resume <konto> --reason "..."`
     skriver en CLEAR-hændelse med actor `human:`. Ingen agent kan genoptage.

2. **Fremadtest-konti.**
   - Mekanisk optagelsesregel: hver frosne variant, som paper-runneren i dag kan beregne på live Binance- og
     CoinMetrics-data, undtagen eksperimenter i OBSERVATION (de har deres egen skyggekonto og fremadtest) og eksakte
     dubletter (samme skabelon og parametre; den først registrerede beholdes). Det giver 10 konti:

     | Eksperiment | Skabelon | Frosne parametre | SHA-256 cost.json | SHA-256 backtest.json |
     |---|---|---|---|---|
     | E_vol_managed_long_p1 | vol_managed_long | lookback_days 7, target_vol 0.5 | 88c8bf0a73c503ce185b2f4e8a000720cfd7e132c7d5ad5feba260fe1dd4d1b6 | 04082bdbc350924a788b233a4c8e4091a99bb7b85c0d29b43fff0320a97c264a |
     | E_day_of_week_p1 | day_of_week | mode flat_weekend | 0b3ed84fde00458af08be5240960740b3049f43a92241da07e82d504361274a8 | 511d5d9970b5dc90971b34821416c311f724284b98478aab2b513a7ae76e6df4 |
     | E_hour_of_day_p1 | hour_of_day | k 3 (frosset fit) | 6eb4d899312eea97a8fa3505ba8cd1608464772bce8e239aa02914feab4da004 | ed151ff19a0ba3866566bd717acd7af9dff77fcc6e1c19a0beda4a7b741a89fa |
     | E_funding_contrarian_p1 | funding_contrarian | q 0.95 | f713d01e6ed6025b5f027c462566ab2c7ef935386220988b697f8569303f33aa | 0061c8ca4bbb9c743a91737056fb3356e907c62495477bd6a5c75ac8bd90f9ef |
     | E_daily_reversal_p1 | daily_reversal | z 2.0 | 290c89e69cc98ac74180c3929a5d0c2aba9586aad9b8a6688b56390215f54108 | bc10953b2feeed3f31a0f6cb259a1c6946adadce044ee7de85da7c2cb3c37c26 |
     | E_xs_momentum_p2 | xs_momentum | k 2, lookback_days 7 | 9348a84f7ac1cc60c634c284c3c9be7b97051f88134b371627ab33eae667a281 | 5d8ebbedd5607100952c1891208ac176ea07b20c331f877674571d80a812e572 |
     | E_xs_max_lottery_p2 | xs_max_lottery | k 2, window_days 28 | 5c3c4c7d16d85fb5af8d83f5077e531babbca23d5813b2780c5fa07c4c8f2087 | 713c7f656e5552bddb3b7ef242124fe8ea3a215656554e6374e491462781f9c0 |
     | E_xs_low_volatility_p2 | xs_low_volatility | k 2, lookback_days 28 | ec4bb4bb6d965661b155bf87c864e490336d26586661476e0e737a8d5bd897ab | 17c9ae82f6bc75710fe26a63cf652ea9b209d75ba8f159c82e83cf3aab2134d7 |
     | E_xs_betting_against_beta_p2 | xs_betting_against_beta | k 2, lookback_days 28 | 1b85e44a0122af7e50c1ae45e2ad190d81c119efa77a41575b294ab217a9398a | 503857c886a128eb0171595bfbe1f31bcb3ff3d963c6aea861c0480082c58fb0 |
     | E_supply_dilution_p3 | supply_dilution | k 3, lookback_days 30 | b28aed4201d32acabb72b94398cf37126926854061b31d161d144513d57fa886 | 2b8c44767ce1a3169288438d00c56f4778673062c7519e98645a73f922d0212a |

     Udeladt: E_mvrv_value_p3 (OBSERVATION) og E_vol_managed_long_p2 (samme skabelon og parametre som _p1). Ikke
     beregnelige i dag: skabeloner uden live-kilde (ændring 3 §4 og PROTOCOL_V3 afsnit 7), skabeloner med EOSUSDT
     (afnoteret) og skabeloner med længere historik end 1000 timebars.
   - Kun et menneske starter og stopper: `python3 -m lab forward-start --reason "..."` skriver `forward.approved`
     (actor `human:`) for hver konto på listen; `forward-stop` skriver `forward.stopped`, og positionerne lukkes med
     reducerende ordrer. En konto handler kun, hvis artefakternes registrerede SHA-256 stadig er dem i tabellen.
   - Hver konto er simuleret med 10.000 USD i samme motor, med samme omkostninger, frosne variant og univers som
     skyggekontoen. Ingen rigtige penge og ingen ordrer til en børs.
   - Visning: mærket "FREMADTEST (simuleret, ikke godkendt, ekskl. funding)" i dashboardets eksisterende papir- og
     saldodele. Kontiene holdes uden for overskriftens saldo og P&L og tælles aldrig som godkendt strategi. Live-P&L
     er uden funding.

3. **Ingen virkning på de formelle tests.**
   - Ingen rækker i results, trials, transitions, alpha_ledger, approvals eller experiments, og ingen
     `observation.started`. `promotion.decide` læser dem aldrig.
   - Afviste og SUPPRESSED eksperimenter forbliver afviste; intet genoplives.
   - Fremadtesten indgår ikke i kohorten `fwd202611`, så MVRV's N forbliver 1.

4. **Data.**
   - Live-signalet må læse de seneste 1h-bars (højst 1000), afregnet funding, en ordrebog med 20 niveauer og
     CoinMetrics' seneste 120 dage. Det gælder kun livekontoens signal, aldrig en evaluering (som ændring 3 §4).
   - Live-tal må ikke bruges til nogen beslutning om et eksperiment.

5. **Evaluering** (reglerne ligger fast nu; den kører i 2027).
   - Vindue: 2026-11-01 00:00 UTC til 2027-04-30 23:59 UTC (6 hele kalendermåneder).
   - Den frosne regel genberegnes på arkivdata fra samme kilder som backtesten, tidligst 7 dage efter vinduet og
     inklusive funding (som `step_observe`). De live papirkonti er aldrig evalueringsgrundlag.
   - Krav som ændring 2 punkt 4: netto-gennemsnit pr. dag > 0; ensidet 90 % nedre grænse > 0 (5-dages blokke, 2.000
     træk, seed 7); netto-Sharpe over lige-vægtet købe-og-holde af samme univers; netto total > 0 ved dobbelte
     omkostninger; datakvalitet; PSR ≥ 1 − 0,05/N med N = 10, fastlagt nu.
   - Et symbol, der ikke handles 2026-11-01, udelukkes, og vægten fordeles på resten, hvis mindst `min_symbols` er
     tilbage; ellers giver kontoen "ingen afgørelse". Afnoteres et symbol i vinduet, udelukkes det fra dagen efter.
   - Ingen aflæsning før vinduet er slut.
   - Udfaldet registreres som hændelsen `forward.result` og en artefakt under `artifacts/_diagnostic/`, aldrig som en
     results-række. En PASS er kun evidens: et menneske kan registrere et nyt, forbundet eksperiment, som skal
     igennem alle eksisterende gates.
   - Ærlig forventning: med N = 10 kræves en annualiseret Sharpe på cirka 3,7 over 6 måneder (uden fede haler).

6. **Kobling.** En afstemningsfejl i en fremadtest-konto udløser FAIL_CLOSED som for enhver anden konto, og kontiene
   tæller med i gaten "alle papirkonti afstemmer". Begge dele er strengere, ikke lempeligere.

7. **Netværk.** Bars og funding hentes én gang i timen pr. symbol for alle konti. Ordrebogen hentes én gang pr.
   kørsel pr. symbol for alle konti og igen lige før hver ordre. Flåden cacher DNS-opslag i 300 s. Kontiene dækker
   højst 19 symboler.

8. **Holdout som ét erklæret filsæt (fejlrettelse).**
   - Fejlen: holdout-trinnet læser kursdata og ekstra kilder i separate læsninger, og gatewayen kræver, at senere
     læsninger har samme filsæt som den første. En skabelon med ekstra kilder (fx MVRV med CoinMetrics) kan derfor
     aldrig gennemføre sin holdout.
   - Rettelsen: holdout-trinnet erklærer det komplette filsæt (alle kilder) i én åbning. Hver senere læsning i trinnet
     eller i en kørsel med samme kode-hash skal være en delmængde af sættet med identiske SHA-256. Ingen fil uden for
     sættet må læses.
   - Holdout åbnes stadig kun én gang pr. eksperiment, og intet lempes. Ingen holdout er åbnet endnu, så intet
     resultat ændres.

## Ændring 8 (2026-10-18): hypotesefamilier — forhåndsregistrerede familier af ikke-prisforudsigende mekanismer, alfa-budget og fremadtest — før kode

**Beslutning:** brugeren besluttede 2026-10-18 at genstarte idégenereringen gennem forhåndsregistrerede hypotesefamilier:
- kun mekanismer, der ikke forudsiger priser: struktur, tilskud, carry, flow og likviditetsydelse. Det følger
  `research/STRATEGIC_OPPORTUNITY_REVIEW.md` afsnit 3 ("Price-prediction strategies are therefore not pursued further");
- en AI må skrive udkast til en familie, men kun brugeren godkender den, og han skriver selv godkendelsen i terminalen;
- et alfa-budget håndhæves, og en fremadtest afgør;
- registreringer, der skal hente nye data, venter til efter 2026-11-27. Indtil da bruger pm_lp netværket og DNS.

**Gælder:** kun eksperimenter, der registreres som instanser af en godkendt familie.
- Alle resultater for v1–v3 står, som de er registreret.
- MVRV's kohorte `fwd202611` (N = 1) og fremadtest-familien i ændring 7 (N = 10) ændres ikke.
- `lab/engine/catalogue.py` ændres ikke. De 3 skabelongodkendelser, der i dag er gyldige for katalogets blob
  `cfa04601fd86`, forbliver derfor gyldige: `mvrv_value`, `real_rate_filter` og `supply_dilution`.
- Ingen gate lempes, ingen tærskel ændres, og alt nyt er strengere.
- Tallene mærket (bekræftet) blev bekræftet af brugeren 2026-10-18, sammen med første familie (F1 `fcarry`),
  F2 `dbasis` kun i fase B og accept af oplysningen i punkt 20.

1. **Hvad en familie er.**
   - En familie består af to filer:
     - en committet JSON-fil `research/families/<fid>.json` (skema `lab.family/1`);
     - ét mekanismemodul `lab/families/<fid>.py` med positionsfunktioner, instrumentmodel og attribution.
   - Hver familie har ét kanonisk mekanisme-tag fra det kontrollerede ordforråd `research/families/VOCABULARY.json`.
     - Ordforrådet dækker alle eksisterende tags fra kataloget, legacy og scanneren, hver med klasse og beslægtede tags.
     - Et nyt tag kræver en ændring af ordforrådet. Ordforrådets blob er bundet i godkendelsen, så brugeren ser og godkender ændringen.
   - Instanserne hedder `E_<fid>__<instans>_a8`.

2. **Kun ikke-prisforudsigende mekanismer.**
   - Klassen skal være `carry`, `structural`, `subsidy`, `flow` eller `liquidity_provision`. Klassen `price_prediction` afvises, og alle 28 katalog-tags har den klasse.
   - Positionerne skal være afdækket i samme aktiv (`hedged_same_asset`), fx lang spot og kort perp i samme mønt. Retningsbestemte bøger og uafdækkede lange/korte bøger på tværs af mønter afvises.
   - Afkastkilden skal være en navngiven pengestrøm (funding, låst basis eller belønning). Attributionsgaten i punkt 8 tester den.
   - Denne ændring kan kun køre to instrumentmodeller: `spot_perp_ratio` og `spot_delivery_ratio`. De øvrige klasser står i ordforrådet, men kræver en senere ændring med deres egen instrumentmodel.

3. **Størrelse. (bekræftet)**
   - Højst K = 3 basisinstanser. Hver har præcis 2 faste varianter, og varianten vælges på træning efter den eksisterende regel.
   - Hver basisinstans må have højst 1 forhåndsopregnet efterfølger (punkt 9). Det giver højst 12 trials pr. familie.
   - Tilbagekig er højst 14 dage. Positionerne er 0, indtil tilbagekigget er fyldt inden for vinduet (afsnit 2, "Opvarmning").
   - Beslutninger træffes kl. 01:00 UTC og bruger kun funding, der er afregnet før beslutningen.
     - Grund: motoren krediterer en afregning til positionen i den time, der starter ved afregningen (`lab/engine/data.py:158-163`, `lab/engine/backtest.py:28-38`).
     - En beslutning kl. 00:00 ville derfor give hver indgang en afregning, som den ikke ville få i virkeligheden.
   - Signaler bruger summen af afregnet funding over L dage, annualiseret (× 365/L). Det gør dem uafhængige af afregningsintervallet (8, 4 eller 2 timer).
   - Højst 2 familier pr. kanonisk tag i hele programmet. Højst 1 åben familie pr. tag ad gangen.

4. **Udkast.**
   - En AI må skrive og committe familiefil og modul som udkast (feltet `drafted_by`).
   - Udkastet må ikke beregne afkast eller signaler på data fra noget vindue.
   - Aggregerede tal, der er set under designet, skal oplyses i filen (feltet `drafting_data_access`); se punkt 20.
   - `python3 -m lab family-check FIL` er skrivebeskyttet og bruger intet netværk; alle må køre den. Den viser:
     - skema og ordforråd;
     - blobs;
     - kirkegård og beslægtede tags;
     - hvilke filer der allerede ligger i cachen;
     - budgetvirkning og styrketabel.

5. **Godkendelse — kun brugeren.**
   - Godkendelsen har to trin, som brugeren selv skriver i en interaktiv terminal:
     - `python3 -m lab approve-family <fid> --reason "..."` viser resumé, blobs, styrketabel, budgetvirkning og kirkegårdskvitteringer og giver en engangskode, der gælder i 15 minutter;
     - `python3 -m lab confirm-family` spørger om koden og om de første 8 tegn af familiefilens blob. Begge læses fra prompten, aldrig som argumenter.
   - Begge kommandoer nægter at køre, hvis stdin eller stdout ikke er en terminal, eller hvis en assistent-miljøvariabel (`CLAUDECODE`, `CLAUDE_CODE_*`) er sat. Der findes intet dashboard-endepunkt.
   - En assistent kører aldrig disse kommandoer. Mønstret "Claude bekræftede på brugerens instruks" (ændring 2, registrering) gælder ikke for familier.
   - Ærligt: koden kan ikke bevise, at et menneske skrev. Det er denne regel, der er bindende.
   - Godkendelsen (hændelsen `family.approved`) binder:
     - de committede blobs af familiefilen, modulet, `lab/families/__init__.py` og `VOCABULARY.json`;
     - de tærskler, familien bruger: `PLACEBO_P_MAX` 0,10, `DSR_MIN` 0,95, `COST_HIGH_MULT` 2,0 og bootstrap med 5 dage, 2.000 træk og seed 7.
   - Ændres noget af dette før registrering, er godkendelsen ugyldig.
   - Godkendelsen registrerer, hvilke instanser der er aktive, og hvilke der er droppet.
   - Kun et menneske kan tilbagekalde med `revoke-family`, og kun før registrering.

6. **Kirkegård og lektioner.**
   - Den eksisterende discovery-agent opdager instanserne fra committede, gyldige familiefiler, inklusive efterfølgere.
   - Kirkegården gælder som i dag: samme tag og udførelse, eller samme fingeraftryk. Et match giver SUPPRESSED.
   - Beslægtede tags fra ordforrådet tjekkes også. Hvert match på et eksperiment i REJECTED eller WITHDRAWN skal stå i `graveyard_acknowledged` med:
     - en tekst "materially different because …" på mindst 40 tegn;
     - de lektioner, teksten adresserer. Nøglerne er årsag 1–4 i `DIAGNOSE_HVORFOR_INTET_BESTAAR.md` og lektioner fra `research.diagnostic`.
   - Mangler en kvittering, nægtes godkendelse.
   - En SUPPRESSED instans genoplives kun gennem den eksisterende menneskelige overgang SUPPRESSED → DISCOVERED, med begrundelsen "materially different because …".
     - For familieinstanser kræver `lab confirm` en interaktiv terminal.
     - Genoplivning er et separat skridt og sker før `approve-family`.
   - Kirkegården tjekkes igen ved registrering. Familiens egne søskende tæller ikke som match.

7. **Registrering.**
   - Registreringen går gennem den eksisterende `register_batch`, som strategy-1 kalder i en flåde, et menneske har startet.
   - Basisinstanserne registreres én gang, som én batch: `batch.registered` med familie og trial-cutoff. Validering venter på alle medlemmers cost-trin.
   - Registrering nægtes, hvis:
     - godkendelsen er ugyldig, eller der ikke er reserveret alfa;
     - programmet er stoppet (punkt 15), eller 3 familier allerede er åbne;
     - et ikke-afsluttet eksperiment uden for familien dækker samme tag og udførelse;
     - det er før 2026-11-28 00:00 UTC, og en fil, som screeningen skal læse, ikke allerede ligger i `data/lab/market`.

8. **Screening er kun et filter.**
   - PROTOCOL v3-vinduerne og alle v2/v3-gates gælder uændret:
     - train-gaten;
     - før-validerings-gaten: eksakte look-ahead- og forgiftningstests, datakvalitet og placebo p < 0,10;
     - alle validerings-krav.
   - Ny og strengere gate, **mekanisme-attribution**: pengestrømmen minus alle omkostninger skal være > 0, og basis- og kurs-P&L skal være ≤ pengestrømmen.
   - Købe-og-holde-benchmarket er lige-vægtet købe-og-holde af de samme perps, med katalogets omkostninger.
   - DSR beregnes og registreres, men afgør intet.
   - Hver instans, der består alle andre krav, får "OBSERVE (family forward test)" og går SCREENING → OBSERVATION. Det gælder også ved DSR ≥ 0,95. En familieinstans går aldrig direkte til SCREEN_PASSED.
   - Instrumentet er én kvotientserie pr. mønt, så placebo blander begge ben samlet, og afdækningen bevares.
   - En regel, der næsten altid er aktiv, har ingen timing og fejler derfor placebo. Det er en kendt og accepteret konsekvens.

9. **Efterfølgere.**
   - Efterfølgere skal være forhåndsopregnet. De er kun én generation dybe og kan kun registreres, før kohorten lukkes.
   - En efterfølger registreres som en ekstra batch i familien, og kun hvis forælderens hash-verificerede træningsartefakter (`cost.json`, `adversarial.json`) opfylder den mekaniske udløser i familiefilen.
   - Valideringsresultater, fremaddata, slut-test og live-tal udløser aldrig noget.
   - Efterfølgere, der ikke er udløst, når kohorten lukkes, går DISCOVERED → SUPPRESSED. Det er en eksisterende automatisk kant.
   - En idé, der opstår efter resultaterne, er en ny familie med ny godkendelse og ny alfa.

10. **Kohorte. (bekræftet)**
    - Kohorten lukkes ved det første strategy-pass, hvor alle registrerede medlemmer har et resultat, og ingen efterfølger længere kan udløses.
    - Hændelsen `cohort.fixed` registrerer kohorte-id, medlemmer, M, α_F, α_i = α_F/M og vinduerne. M og α_i genberegnes aldrig.
    - M ≤ 3. Overlever flere end 3, går de 3 med højest validerings-netto-Sharpe videre. Resten får "REJECTED: not selected (family cohort cap 3)".
    - Vinduet starter 00:00 UTC den 1. i måneden efter lukningen, dog aldrig før 2026-12-01, og varer 12 hele kalendermåneder.
    - Vinduet hedder `fwdYYYYMMm12`, og delvinduet hedder `fwdYYYYMMm06`.
    - Den gamle kohortetælling i `step_observe` ignorerer hændelser med en kohortenøgle, så MVRV's N forbliver 1.
    - M = 0 lukker familien som FUTILE_IN_SAMPLE.

11. **Fremadtest (den afgør).**
    - Den frosne variant genberegnes på arkivdata, tidligst 7 dage efter vinduets slutning.
    - Kravene er de samme som i ændring 2 punkt 4:
      - netto-gennemsnit pr. dag > 0;
      - ensidet 90 % nedre grænse > 0 (5-dages blokke, 2.000 træk, seed 7);
      - netto-Sharpe over lige-vægtet købe-og-holde af de samme perps;
      - netto total > 0 ved dobbelte omkostninger;
      - datakvalitet med `min_symbols`.
    - Hertil kommer mekanisme-attribution som i punkt 8.
    - Held-tjek: PSR_kons ≥ 1 − α_i. PSR_kons er den mindste af tre værdier, så den er aldrig lempeligere end i dag:
      - PSR med skævhed 0 og kurtosis 3, som i dag;
      - PSR med stikprøvens skævhed og kurtosis;
      - PSR med effektivt n = n / max(1, 1 + 2·Σ_{k=1..5}(1 − k/6)·ρ_k), aldrig over n.
    - Et symbol uden spot- eller perp-fil for vinduets første måned udelukkes før beregning (ændring 7 punkt 5).
    - PASS → SCREEN_PASSED. FAIL → REJECTED.

12. **Mellemliggende aflæsning — kan kun afvise.**
    - Delvinduet (månederne 1–6) er sit eget erklærede vindue. Det læses tidligst 7 dage efter, at det er slut.
    - Er netto-gennemsnittet pr. dag ≤ 0, eller pengestrømmen minus omkostninger ≤ 0, er udfaldet "FAIL (forward futility)" → REJECTED.
    - Ellers sættes slutevalueringen i kø.
    - Aflæsningen kan aldrig give PASS og ændrer hverken M eller α_i.

13. **Alfa-budget. (bekræftet)**
    - Programformuen er W0 = 0,05 for alle fremadtests under ændring 8 tilsammen.
      - Den er adskilt fra ændring 2 (0,05 pr. vindue) og ændring 7 (0,05 ved N = 10).
      - Laboratoriets samlede fejlrisiko er derfor ikke 0,05. Det står åbent her.
    - Reglen er alfa-forbrug (Bonferroni), ikke alfa-investering.
    - α_F = 0,0125 pr. familie reserveres ved `confirm-family` som en række i `alpha_ledger` (exp_id `family:<fid>`, note "A8 reserve"). Godkendelse nægtes, hvis den resterende formue er under α_F.
    - Ved `cohort.fixed` med M ≥ 1 bruges α_F og fordeles som α_F/M pr. instans.
    - Alfa frigives (med en negativ række, "A8 release") kun, hvis familien tilbagekaldes før registrering, hvis M = 0, eller hvis familien bliver utestbar før lukning.
    - En PASS giver ingen alfa tilbage.
    - Familiefejlraten over alle ændring 8-fremadtests er ≤ 0,05 ved foreningsgrænsen, uden antagelse om uafhængighed.
    - De eksisterende rækker på 0,005 pr. eksperiment (28 rækker, 0,14 i alt) er bogføring af screening og indgår ikke i W0. Familieinstanser får en screening-række på 0.

14. **Styrkekrav før godkendelse.**
    - Godkendelse nægtes, medmindre styrken er ≥ 0,5 ved sand Sharpe 3,0 (fast, ikke selverklæret), α_F/3 og familiens vindueslængde.
    - Med α_F = 0,0125 kræver det 12 måneder: styrken er 0,63, mens 6 måneder giver 0,30.

15. **Futilitet og programstop. (bekræftet)**
    - Familieniveau:
      - M = 0 → FUTILE_IN_SAMPLE.
      - For få symboler eller for lidt data → UNTESTABLE.
      - Begge frigiver alfa.
      - En permanent jobfejl standser familien uden at lukke kohorten.
    - Programmet modtager ingen nye familiegodkendelser, når et af disse gælder:
      - (a) den resterende formue er under α_F;
      - (b) 3 familier i træk er lukket uden en fremad-PASS (FUTILE, UNTESTABLE eller alle FAIL);
      - (c) der er ingen fremad-PASS pr. 2028-06-30.
    - Kun en ny dateret ændring kan genstarte programmet. Kørende fremadtests fortsætter til ende.

16. **Efter en fremad-PASS.**
    - Instansen går til SCREEN_PASSED.
    - Familier følger ikke den automatiske vej i ændring 4, fordi gaten "catalogue experiment" er lukket for dem. Slut-test 2024 og simuleret handel kræver derfor menneskelige godkendelser.
    - Slut-testen åbnes én gang som ét erklæret filsæt, der også rummer spot-filerne. Familiefilens blob er gatewayens kode-hash.
    - Uden en ren slut-test standser instansen på SCREEN_PASSED.
    - Simuleret handel for familier kræver et live spot-feed, som ikke findes i dag, og en senere ændring.

17. **Data og netværk. (bekræftet)**
    - Før 2026-11-28 00:00 UTC foretager koden for ændring 8 ingen netværksforespørgsler: ingen HEAD-tjek og ingen downloads. pm_lp's opfølgning løber til 2026-11-27 (`PM_LP_START.md`).
    - Derefter hentes data kun fra `data.binance.vision`, gennem den eksisterende cache og download-kode og med flådens DNS-cache.
    - Spot-zips har samme filnavne som perp-zips. De gemmes derfor i `data/lab/market/spot_klines/`, og leveringskontrakter i `data/lab/market/cm_klines/`.
    - Hver familiefil angiver filantal og størrelse.

18. **Kode-pin.**
    - Ved registrering skriver specifikationen familiefilens blob, modulets blob og blobs for motorens filer.
    - Ændres familiefilen eller modulet efter registrering, fejler hvert senere trin lukket, også i 2027. En rettelse kræver en dateret ændring.

19. **Sikkerhed.**
    - Alt er simuleret: ingen rigtige penge, ingen nøgler, ingen ordrer.
    - Ingen autostart, cron eller timere. Alt kører i strategy-1's og discovery-agentens pass, i en flåde, som et menneske har startet.
    - Fremadjobs bruger det eksisterende felt `not_before`.

20. **Ærlig forventning og oplysning.**
    - Krævet annualiseret Sharpe (PSR med skævhed 0 og kurtosis 3):

      | Vindue | α_i 0,0125 | α_i 0,00625 | α_i 0,0042 |
      |---|---|---|---|
      | 12 måneder | 2,25 | 2,51 | 2,65 |
      | 6 måneder | 3,21 | 3,58 | 3,78 |

    - Styrke ved 12 måneder med aflæsning ved 6 måneder (simuleret):

      | Sand Sharpe | 2 | 3 | 4 |
      |---|---|---|---|
      | M = 1 | 0,40 | 0,77 | 0,96 |
      | M = 3 | 0,25 | 0,63 | 0,91 |

      Under nulhypotesen stoppes cirka 50 % ved 6 måneder.
    - Autokorrelation: med daglig AR(1), ρ = 0,3, består et nul-eksperiment dagens held-tjek med cirka 0,048 i stedet for 0,0125. PSR_kons giver cirka 0,017, men koster styrke: ved sand Sharpe 3 falder den fra 0,71 til 0,53.
    - Oplysning om data set under designet 2026-10-18:
      - Aggregerede funding-tal for de cachede filer 2022-01..2023-12 blev set: andel afregninger på præcis 0,01 % 0,44; andel negative 0,30; gennemsnit ≈ 0.
      - Der er ikke beregnet strategiafkast.
      - Familiernes gitre er taget uændret fra udkast, der blev skrevet før.
      - Screeningen er kun et filter, så fremadtestens gyldighed påvirkes ikke.

## Ændring 9 (2026-10-18): spot-data før pm_lp-perioden, funding i papirkonti, ikke-afgørende researchjobs fra scanningerne og edge-overvågning — før kode

**Beslutning:** brugeren besluttede 2026-10-18 i sessionen:
- familiernes spot-data for træning og validering må hentes én gang før 2026-10-24, uden for pm_lp's kritiske periode;
- papirkonti bogfører afregnet funding fremover;
- scanningerne fører til ikke-afgørende researchjobs;
- edge overvåges ikke-afgørende nu; afgørende regler kommer som ændring 11.

Ingen gate lempes, ingen tærskel, intet vindue og ingen alfa ændres, og ingen registreret afgørelse ændres.

1. **Spot-data for familier før 2026-10-24.**
   - Ændring 8 punkt 7 og 17 ændres kun sådan: indtil 2026-10-24 00:00 UTC må koden for ændring 8 hente de
     spot-klinefiler (1h, `data.binance.vision`), som en godkendt familie skal screenes på i træning og validering
     (`train3` 2022-01..2023-06 og `validation3` 2023-07..2023-12). Registrering må ske i samme periode.
   - Fra 2026-10-24 00:00 UTC til 2026-11-28 00:00 UTC gælder embargoen i ændring 8 uændret: ingen
     netværksforespørgsler fra koden for ændring 8. Mangler en screening filer ved embargoens start, venter den
     (`family.waiting`) og fortsætter efter 2026-11-28.
   - Holdout-data (2024) og fremaddata hentes kun efter 2026-11-27, som før.
   - Neddrosling: højst 2 samtidige downloads, flådens DNS-cache, filerne i `data/lab/market/spot_klines/`.
     Forventet omfang cirka 720 filer og 25-50 MB.

2. **Funding i papirkonti.**
   - Fra ændringens deploy (hændelsen `paper.funding_started`, tidspunkt T_F) bogfører alle simulerede papirkonti
     afregnet Binance-funding for åbne positioner som en pengestrøm. Det gælder godkendt papirhandel, skyggekonti og
     fremadtest-konti.
   - Beløb = − position × pris ved afregningen × afregnet rate. En lang position betaler en positiv rate, en kort
     modtager den. Prisen er åbningskursen for den timebar, der starter ved afregningen.
   - Rækkerne er append-only og hash-kædede (tabellen `sim_funding`), én pr. konto, instrument og afregning.
   - Afregninger før T_F genberegnes ikke. P&L vises "inkl. funding fra T_F".
   - Fremadtestene i ændring 2 og 7 evalueres fortsat ved arkivgenberegning med funding og påvirkes ikke.
   - Afstemningen udvides: kontant = startkapital + fill-pengestrømme − gebyrer + funding.

3. **Ikke-afgørende researchjobs fra scanningerne** (udvider ændring 5 punkt 4).
   - Et dagligt job `scan_digest` (report-1) læser kun tabellen `observations` for de seneste 24 timer og 7 dage. Pr.
     detektor, metrik og instrument opgør det: målinger, markerede klokketimer, vedvarenhed, størrelse mod tærsklen
     (median og p90), fejlrate og størrelse mod en fast omkostningsreference (katalogets taker-gebyr + halv spread +
     slippage).
   - Det skriver `artifacts/_diagnostic/scanner/<dag>.json` og hændelsen `research.digest` med en registreret
     beslutning: NO_ACTION (intet vedvarende over omkostningerne) eller INVESTIGATE (vedvarende over omkostningerne;
     kandidat til et familieudkast, som kræver en ny familie og brugerens godkendelse).
   - Et job `scan_dossier` (report-1) for hver ny INVESTIGATE-nøgle i `market.event` bruger samme kilder og skriver en
     artefakt og hændelsen `research.dossier`.
   - Jobbene registrerer ingen eksperimenter, handler ikke, ændrer ingen tilstand og henter ingen data.

4. **Edge-overvågning (ikke-afgørende).**
   - For hver aktiv papirkonto vises: dage live, netto pr. dag efter omkostninger (inkl. funding fra T_F) og afstanden
     til valideringsforventningen fra `validate.json` (`daily_net`: gennemsnit og spredning) som en z-værdi. Konti uden
     valideringsserie vises "ingen forventning".
   - Visningen afgør intet, og pauser sker kun efter de eksisterende risikoregler. En kort god periode giver aldrig
     en PASS; afgørelsen er stadig den forhåndsregistrerede fremadtest.
   - Afgørende kriterier for tab af edge skrives som ændring 11, før den første strategi går i godkendt papirhandel.

5. **Saldooversigt (kun visning).**
   - Den formelle saldo er uændret: de konti, der i dag indgår efter gældende regler.
   - Separate felter viser fremadtest-saldoen (startkapital, aktuel værdi, gevinst/tab) og en samlet simuleret oversigt
     (formel + fremadtest), tydeligt mærket som simuleret og ikke godkendt. Intet lægges ind i den formelle saldo, og
     intet tælles to gange.

### Præcisering af ændring 9 (2026-10-19, før deploy)

Ingen regel ændres. De faste tal og detaljer, som koden bruger, skrives her, før koden kører.

- **Punkt 3, scan_digest.** Reglen gælder pr. detektor, metrik og instrument for det afsluttede UTC-døgn:
  - INVESTIGATE, hvis serien er markeret i mindst 6 forskellige klokketimer i døgnet, og medianen af den markerede
    |værdi| er mindst 4 gange omkostningsreferencen (taker-gebyr 0,05 % + halv spread 0,02 % + slippage 0,02 % =
    0,09 %).
  - Faktor 4, fordi en prisforskel kun kan høstes med to ben, der hver åbnes og lukkes: fire taker-handler.
  - Kun prismetrikkerne `cross_venue_gap` og `perp_premium` har en omkostningsreference. Andre metrikker giver altid
    NO_ACTION med begrundelsen "ingen omkostningsreference".
  - Døgnet behandles tidligst kl. 00:30 UTC det følgende døgn. De seneste 7 afsluttede døgn med observationer får
    hver ét job, så en flåde, der har stået stille, indhenter dem.
- **Punkt 3, scan_dossier.** En nøgle, hvis instrument er en familie (fx alle mønter for `cross_venue_gap`), vurderes
  pr. mønt. INVESTIGATE kræver, at mindst én mønt opfylder reglen alene. Samlede tal på tværs af mønter vises kun som
  baggrund.
- **Punkt 3, opfølgning.** Disse ikke-afgørende jobs tæller ikke som fremskridt i hypotese-pipelinen. Watcherens
  besked om "intet research-arbejde" vurderes uden dem.
- **Punkt 2, funding.** En afregning for en åben position, der er ældre end de hentede timebarer (cirka 41 dage), kan
  ikke prissættes. Den registreres én gang som hændelsen `paper.funding_gap` og springes over; senere afregninger
  bogføres som normalt. En afregning, hvor positionen var 0, bogføres ikke og blokerer intet.

## Ændring 10 (2026-10-19): automatisk udforskningsbane — før kode

**Beslutning:** brugeren godkendte 2026-10-19 i sessionen udkastet (`research/drafts/AENDRING10_UDKAST.md`, commit
`103a0be`) og de fem tal mærket [BEKRÆFT] som foreslået ("JA kør alt"). Ønsket: flåden skal søge efter nye idéer hele
tiden. Teksten herunder er udkastet med de præciseringer, koden kræver; intet er lempet.

**Uændret:** ingen gate lempes, ingen tærskel, intet vindue, ingen alfa og ingen registreret afgørelse ændres.
Familier oprettes og godkendes fortsat kun efter ændring 8 (brugeren skriver godkendelsen i terminalen). Kun
ikke-prisforudsigende mekanismer (ændring 8 punkt 2). Udforskning er aldrig grundlag for handel med rigtige penge.

1. **Udforskning er aldrig bevis.**
   - Alt, banen producerer, mærkes `EXPLORATORY_LANE` og tæller aldrig som PASS, aldrig i en gate og aldrig i en
     saldo. Banen registrerer ingen eksperimenter, overgange, resultater eller alfa-rækker, ændrer ingen tilstand og
     handler ikke, heller ikke på papir.
   - Ingen alfa reserveres eller bruges. Banen tæller ikke som en familie i programstoppet (ændring 8 punkt 15).

2. **Eget datavindue, adskilt fra familiernes.**
   - Banen læser kun udforskningsvinduet `explore0` = 2020-01..2021-12, før familiernes `train3` (2022-01..2023-06).
   - Den læser aldrig `train3`, `validation3`, holdout 2024, den reserverede periode fra 2025-01-01 eller
     fremaddata. Koden håndhæver det: banens eneste dataadgang afviser alle andre vinduer, og en test viser det.
   - Datadækningen for 2020-2021 er ukendt pr. mønt og instrument. En mønt, der ikke består den eksisterende
     datakvalitetsregel i `explore0`, udelades mekanisk.
   - Banen evaluerer en familie, når mindst 5 mønter består (samme gulv som F2-designet). Familiernes eget
     `min_symbols` (F1: 24) gælder ikke i banen, fordi mange mønter først fik perps i 2020-2021, og fordi banen intet
     afgør. [BEKRÆFT: tallet 5 er tilføjet under kodningen og skal bekræftes af brugeren.]

3. **Hvad banen søger.**
   - Kun mekanismefunktionerne i `lab/families/<fid>.py` for familier med en gyldig godkendelse efter ændring 8 (i
     dag kun F1 `fcarry`; F2 `dbasis` først efter sin godkendelse). Banen ser derfor aldrig en familie, før brugeren
     har godkendt den, og den kan ikke påvirke en godkendelse, der endnu ikke er givet.
   - Kun de godkendte instrumentmodeller (`spot_perp_ratio`, `spot_delivery_ratio`) og familiens eget univers og
     omkostninger (2× stress). En ny instrumentmodel eller et nyt tag kræver en separat ændring.
   - Parametergitrene står fast i `lab/explore.py` (`GRIDS`) og holder sig inden for familiernes egne grænser
     (tilbagekig højst 14 dage), så et forslag kan blive til en familie uden ændring.
   - Attributionsreglen fra familiens modul beregnes for hver variant.

4. **Omfang og ressourcer.**
   - Højst 500 varianter pr. ISO-uge (UTC). Jobbene har lavere prioritet end alle andre jobs og deler flådens grænse
     for tunge jobs og ressourcereglerne (RAM, disk).
   - Data hentes tidligst 2026-11-28 00:00 UTC (embargoen i ændring 8), gennem familiernes downloadvagt: kun
     `data.binance.vision`, højst 2 samtidige downloads. Før det venter jobbet.

5. **Forslag til brugeren.**
   - Ugentligt skriver report-1 en forslagsliste (`artifacts/_explore/<uge>.json` og hændelsen
     `research.explore_proposals`) med højst 3 kandidater, der opfylder alle:
     - netto Sharpe ≥ 1,0 i `explore0` med 2× omkostninger;
     - familiens attributionsregel holder (mekanismens pengestrøm, ikke prisbevægelse, bærer resultatet);
     - positiv netto i mindst 2 af 3 kronologiske tredjedele af `explore0`.
   - Hvert forslag oplyser antallet af afprøvede varianter i alt (multipel testning).
   - Et forslag bliver kun til en familie, hvis en AI skriver et familieudkast efter ændring 8, og brugeren godkender
     det. Familiefilen skal citere forslaget og antallet af afprøvede varianter.

6. **Hvad banen ikke ændrer.**
   - Alfa-budgettet (W0 = 0,05) og programstoppet gælder fuldt ud for familier, der kommer fra banen.
   - Watcherens og kommandocentralens "pipeline-fremskridt" tæller ikke udforskningsjobs (som `scan_digest` i
     ændring 9).

7. **Rækkefølge.** Ændringstekst (denne) → kode og tests i dev → deploy tidligst efter 2026-11-27 (pm_lp's holdout og
   opfølgning røres ikke; regel B i `research/LINUX_DRIFT.md`) → data hentes fra 2026-11-28.

## Ændring 10a (2026-10-19): bredere og hurtigere udforskningsbane — før kode

**Beslutning:** brugeren besluttede 2026-10-19 i sessionen, at banen skal forske hele tiden og bredt i markedet, ikke
kun i et fast gitter ("Gør alt der bedst ... researchen hele tiden alt market"). Ændring 10 gælder med disse
ændringer. Alt i ændring 10 punkt 1, 2 og 6 er uændret: kun `explore0`, aldrig bevis, ingen alfa, ingen
registrering, ingen handel; familier kun gennem ændring 8 og brugerens godkendelse. Udforskning giver idéer hurtigt;
beviset er stadig den forhåndsregistrerede fremadtest, og den kan ikke gøres hurtigere uden at miste sin værdi.

1. **Automatisk generering i stedet for et fast gitter** (erstatter ændring 10 punkt 3, tredje punkt).
   - Først det faste gitter (`GRIDS`), derefter varianter trukket deterministisk (fast seed) fra et parameterrum pr.
     mekanismefunktion (`SPACES` i `lab/explore.py`), stadig inden for familiernes grænser (tilbagekig højst 14 dage).
   - Hver trukken variant har også en møntkurv: en delmængde af de mønter, der består datakvalitetsreglen i
     `explore0`, med mindst 5 mønter.
   - En variant afprøves kun én gang.

2. **Bredere univers.** Banen bruger foreningsmængden af lab'ens kendte møntlister (`UNIVERSE_30`, `UNIVERSE_30_V3`,
   `UNIVERSE_CM16`, `UNIVERSE`) for familier med instrumentmodellen `spot_perp_ratio`, og familiens kandidatmønter
   for `spot_delivery_ratio`. Ingen ny datakilde og ingen ny forespørgselstype. Markeder uden for Binance-arkivet
   (fx Hyperliquid, Polymarket) kræver en ny instrumentmodel og en separat ændring.

3. **Scannerens fund går ind i banen.** Mønter med markerede `perp_premium`-observationer de seneste 7 dage får
   forrang i møntkurvene for `spot_perp_ratio`. Det er udforskning, ikke en hypotese; ændring 5 og 9 gælder fortsat
   for alt formelt. `cross_venue_gap` kan ikke undersøges på arkivdata og indgår ikke.

4. **Omfang og takt** (erstatter ændring 10 punkt 4, første punkt, og punkt 5, første punkt).
   - Højst 5.000 varianter pr. ISO-uge (UTC). Flåden planlægger højst én gang i timen et job pr. familie med højst 30
     varianter.
   - Forslagslisten skrives dagligt (`artifacts/_explore/<dag>.json`, hændelsen `research.explore_proposals`) med
     højst 3 kandidater efter de samme krav som i ændring 10 punkt 5, og med antallet af afprøvede varianter i alt.

5. **Rækkefølge** som ændring 10 punkt 7: deploy tidligst efter 2026-11-27, data fra 2026-11-28.

## Ændring 10b (2026-10-19): udforskningsbanens data nu og netværk efter pm_lp's holdout — før kode

**Beslutning:** brugeren besluttede 2026-10-19 i sessionen, at banen skal køre nu og ikke vente på pm_lp's
tidsplan, at Claude selv træffer beslutningerne ("tag selv beslutninger og kør"), og at lab'en ikke skal følge pm_lp
længere end nødvendigt. pm_lp's egne regler (perioder, krav, holdout, evaluering tidligst 2026-11-28) ændres ikke.
Ændringen gælder kun banens netværk og deploy-tidspunkt; ingen gate, tærskel, alfa eller familieregel ændres.

1. **Begrundelse.** pm_lp's datakrav D1 gælder kun holdout 2026-10-31..11-13. Fra 2026-11-14 stiller indsamleren
   ikke længere priser (kun status hver 6. time til D0+41), så lab'ens netværk kan ikke skade D1. Før 2026-10-24 er
   pm_lp i udviklingsperioden, hvor dækningen ikke er en gate (samme begrundelse som ændring 9 punkt 1).
2. **Banens netværk** (erstatter ændring 10 punkt 4, andet punkt): banen må hente sine `explore0`-filer (USD-M
   klines og funding, spot-klines) før 2026-10-24 00:00 UTC og igen fra 2026-11-14 00:00 UTC. COIN-M-filer først fra
   2026-11-28 (ændring 8 punkt 17 uændret). Kun `data.binance.vision`, højst 2 samtidige downloads i hele lab'en.
   I mellemtiden læser banen kun filer, der allerede ligger i cachen, og laver ingen forespørgsel.
3. **Deploy** (erstatter ændring 10 punkt 7 og 10a punkt 5): koden må deployes før 2026-10-24, så filerne kan hentes
   i tide. Deploy kræver én genstart af lab'en (flåde og dashboard) og ingen ændring af pm_lp.
4. **F2's embargo flyttes ikke.** Den står i en fil, F1's godkendelse er bundet til (`lab/families/__init__.py`), og
   F2 kan alligevel nå sin kohorte inden 2026-11-30.
5. **Driftsregel B** (`research/LINUX_DRIFT.md`): deploy af lab'en er igen tilladt fra 2026-11-14; ingen planlagt
   genstart af maskinen eller systemopdatering før 2026-11-28, så indsamlerens opfølgning ikke afbrydes.

## Ændring 10c (2026-10-19): udforskningsvinduet starter 2020-03 — før kode

**Beslutning:** brugeren godkendte 2026-10-19 i sessionen ("ja til 10c") efter banens første kørsel i produktionen.
Kørslen (hændelse 2360, artefakt SHA-256 `e49b7878…`) evaluerede 0 varianter: kun 4 mønter (BCH, BTC, ETH, XRP)
bestod den uændrede datakvalitetsregel (dækning ≥ 99 %) i 2020-01..2021-12, fordi ADA, LINK, LTC, EOS, ETC, TRX og
XLM fik deres USD-M perp i løbet af januar 2020 og BNB, ATOM, VET og XTZ i februar 2020.

1. `explore0` = 2020-03..2021-12 (erstatter 2020-01..2021-12 i ændring 10 punkt 2). Alt andet i ændring 10, 10a, 10b og
   11 gælder uændret: kvalitetsreglen, gulvet på 5 mønter, kravene til forslag, netværket, og at intet er bevis.
2. Begrundelse: ændringen gør søgningen mulig. Den lemper ingen regel og vælges ikke efter et resultat: ingen variant
   er evalueret, og ingen afkastserie er set. Vinduet ligger stadig før `train3`, og ingen ny fil skal hentes.
3. Forventet: cirka 15 mønter med fuld dækning (skønnet ud fra filernes første måned i cachen; ikke kørt endnu).

## Ændring 11 (2026-10-19): banekonti — banens kandidater handles automatisk på papir og stoppes automatisk — før kode

**Beslutning:** brugeren besluttede 2026-10-19 i sessionen, at systemet selv skal handle på det, banen finder, og selv
stoppe det, der ikke virker ("når den finder noget ... så handler den på det med det samme og så når det ikke virker
med så fyrer den agtig strategien", "fortsæt med 11", "gør automatisk"). Kun simuleret handel. Ingen rigtige penge,
ingen ordrer til en børs og ingen nøgler; rigtige penge kræver fortsat piloten og brugerens egen beslutning.

**Uændret:** ingen gate lempes, ingen tærskel, intet vindue, ingen alfa og ingen registreret afgørelse ændres.
Ændring 10 punkt 1 gælder fuldt ud: banen og dens konti er aldrig bevis, tæller aldrig som PASS, i en gate, i den
formelle saldo eller i fremadtest-saldoen, og de registrerer ingen eksperimenter, overgange, resultater, trials eller
alfa-rækker. En kandidat bliver kun til noget formelt gennem et familieudkast efter ændring 8 og brugerens
godkendelse. De afgørende kriterier for tab af edge i godkendt papirhandel (ændring 9 punkt 4) skrives som en senere
ændring, før den første strategi går i godkendt papirhandel; ingen er i nærheden i dag.

1. **Hvad.** En banekonto (`LANE_<10 hex>`, de første 10 tegn af SHA-256 af variantens nøgle) er en simuleret konto
   med 10.000 USD, som handler én kandidat fra banen live: samme mekanismefunktion, parametre og møntkurv som i
   `explore0`. Mærket "BANEKONTO (udforskning, simuleret, aldrig bevis)" i dashboardet.

2. **Hvilke kandidater.**
   - Varianter i banens resultater (`artifacts/_explore/<dag>/*.json`), der opfylder alle tre krav i ændring 10 punkt
     5, for en familie, der stadig har en gyldig godkendelse. Bedste netto-Sharpe først (ved lighed nøglen).
   - Kun familier med instrumentmodellen `spot_perp_ratio` (i dag F1 `fcarry`). `spot_delivery_ratio` (F2) kræver
     COIN-M live-data og en separat ændring.
   - En variant handles højst én gang; en stoppet konto startes aldrig igen.

3. **Automatisk start** (actor `system:lane`, hændelsen `lane.started`; i modsætning til ændring 3 og 7 kræver det
   ingen menneskelig start).
   - Højst 3 aktive banekonti, højst én pr. mekanismefunktion, og højst én ny konto pr. klokketime (målt på
     kørslens ur).
   - Ved start hentes ordrebogen for begge ben af hver mønt i kurven (eller i familiens banes univers, når kurven er
     alle mønter). En mønt, hvor et ben ikke kan hentes, udelades og registreres. Er der færre end 5 mønter tilbage,
     registreres `lane.skipped`, og varianten afprøves ikke igen.
   - Hændelsen registrerer nøglen, artefaktens sti og SHA-256, mønterne og forventningen (punkt 6).

4. **Handel.**
   - Signalet beregnes med familiens egen funktion i `lab/families/<fid>.py` på de seneste 1h-bars og den afregnede
     funding fra Binance USD-M (højst 1000 bars og 200 afregninger, som paper-runneren i dag). Beslutningstidspunktet
     01:00 UTC og alle regler er familiens.
   - Position +1 i en mønt = lang spot og kort perp med samme mængde. Ved åbning er mængden kontoens værdi / (2 ×
     antal mønter) / perp-midtkurs pr. ben. Mængden holdes, til signalet går til 0; der rebalanceres ikke. Et ben, der
     kun delvist blev fyldt, bringes op til det andet bens mængde i en senere kørsel.
   - Taker-ordrer går gennem den offentlige ordrebog med 20 niveauer, som i den eksisterende papirmotor. Gebyr 0,10 %
     pr. ben (spot-gebyret, også for perp-benet: forsigtigt), ekstra slippage 0,02 %, forventet spread 0,04 % pr. ben.
   - Funding bogføres for perp-benet efter ændring 9 punkt 2. Spot-benet har ingen funding.
   - Risikoreglerne i ændring 7 punkt 1 gælder uændret (drawdown 10 %, data, spread). Afstemningsfejl giver
     FAIL_CLOSED, og kontiene tæller med i "alle papirkonti afstemmer" (strengere, ikke lempeligere).

5. **Automatisk stop** (hændelsen `lane.retired`, actor `system:lane`; positionerne lukkes med reducerende ordrer).
   En konto stoppes, så snart én af disse gælder:
   - **Edge mangler:** mindst 7 hele dagsafkast live, og z = (live gennemsnit − forventet gennemsnit) / (forventet
     spredning / √n) ≤ −3.
   - **Tab:** kontoens værdi ved seneste opgørelse er mindst 3 % under startkapitalen.
   - **Pause:** kontoen har været sat på pause af en risikoregel i 24 timer.
   - **Kilden betaler ikke:** 14 dage efter start er kontoens bogførte funding minus alle betalte gebyrer ≤ 0
     (familiens attributionsregel "pengestrøm − omkostninger > 0" anvendt live). Det stopper også en konto, der ikke
     har haft en position i de 14 dage, så pladsen går til den næste kandidat.
   - **Familien:** familiens godkendelse er ikke længere gyldig.
   - **Udløb:** 90 dage efter start.
   - **Mennesket:** brugeren slår banekontiene fra (`python3 -m lab lane-off --reason "..."`, i en terminal); så
     stoppes alle aktive konti, og ingen nye startes, før brugeren skriver `lane-on`.
   Et menneske kan genoptage en pauset banekonto inden for de 24 timer med `sim-resume` (ændring 7 punkt 1).

6. **Forventning.** Fra variantens resultat i `explore0` ved 2× omkostninger: gennemsnit = netto total / dage,
   spredning = gennemsnit × √365 / netto-Sharpe. Begge divideres med 2, fordi backtesten regner pr. enhed af det ene
   ben, mens kontoen bruger kapital til begge ben (`capital_per_unit_notional` 2). Live-dagsafkast er ændringen i
   kontoens værdi fra én UTC-dags sidste opgørelse til den næstes, efter omkostninger og inklusive funding.
   - Ærlig forventning: `explore0` er 2020-2021, hvor funding var usædvanligt høj. Mange konti vil derfor blive stoppet,
     oftest af "kilden betaler ikke" eller "tab". Det er reglerne, der virker, ikke en fejl.
   - "Edge mangler" er langsom: ved Sharpe 1-3 kræver en statistisk påvisning måneder af dagsafkast, så reglen fanger
     i praksis kun store, vedvarende tab. Den hurtige regel er "kilden betaler ikke". Med z ≤ −3 tjekket dagligt i
     op til 90 dage stoppes en konto, hvis edge faktisk er som forventet, med en lille sandsynlighed (anslået under
     10 % pga. gentagne kig), men ikke nul.

7. **Lovende konti (ikke-afgørende).** Har en konto mindst 30 dagsafkast, positivt live-gennemsnit og z > −1,
   registreres én gang `lane.promising`. Det er et signal til, at en AI skriver et familieudkast efter ændring 8 for
   brugerens godkendelse; det er aldrig bevis og ændrer intet andet.

8. **Netværk.** Nyt: offentlig Binance spot-ordrebog (`https://data-api.binance.vision/api/v3/depth`, 20 niveauer,
   ingen nøgle) for spot-benet. Værten er Binances vært kun for offentlige markedsdata; den kan ikke modtage ordrer.
   `api.binance.com` (handelsværten) bruges aldrig. Værten tilføjes listen over tilladte værter i
   `tests/test_lab_safety.py`, kun med brugerens godkendelse; alle andre sikkerhedskrav (kun GET, ingen signering,
   ingen nøgler) gælder uændret. Perp-benet bruger paper-runnerens eksisterende forespørgsler og timecache. Bøger
   hentes ved start, ved timens opgørelse og lige før hver ordre; signal og funding fra timecachen. Højst 3 konti.

9. **Rækkefølge.** Ændringstekst (denne) → kode og tests i dev → brugeren deployer (regel B: ikke 2026-10-31..11-13).

## Ændring 12 (2026-10-19): scannerkonti — scannerens fund handles straks på papir — før kode

**Beslutning:** brugeren godkendte 2026-10-19 i sessionen udkastet (`research/drafts/AENDRING12_UDKAST.md`) og bad om
en mere aggressiv udgave: "ja til ændring 12 dog behøver det ikke være så tilbageholdende. Må gerne være aggressiv og
handle med samme på det - kør automatisk". Teksten herunder erstatter udkastet. Kun simuleret handel.

**Uændret:** ændring 10 punkt 1 og ændring 11 gælder: aldrig bevis, ingen formelle rækker, ingen formel saldo, ingen
alfa; rigtige penge kræver piloten og brugerens beslutning. Mekanismen er F1's (lang spot, kort perp i samme mønt,
pengestrømmen er funding; ikke prisforudsigende), men reglen for ind og ud er scannerens, ikke en familiefunktion, så
kontiene kan aldrig blive til en F1-instans eller et forslag til en.

1. **Konto.** En banekonto efter ændring 11 med kilden `scanner` (`LANE_<10 hex>` af nøglen `scan|<mønt>|<time>`),
   10.000 USD, én mønt, mærket "SCANNERKONTO (scannerfund, simuleret, aldrig bevis)". Handel, omkostninger, funding,
   risikoregler, afstemning, `lane-off` og visning som i ændring 11.

2. **Ind (straks).** Scanneren måler én gang i timen. En mønt med Binance spot og USD-M perp åbnes ved den første
   kørsel efter en scanning, hvor dens `perp_premium` (mark/index − 1) er positiv og enten mindst 1 % eller mindst
   0,5 % (scannerens tærskel) i de to seneste scanninger. Mængden er halvdelen af kontoens værdi pr. ben.

3. **Ud.** Positionen lukkes, når mønten ikke er markeret med positiv præmie i de to seneste scanninger. En lukket
   konto åbner igen efter reglen i punkt 2. Er den seneste scanning over 3 timer gammel, åbnes intet nyt, og en åben
   position holdes.

4. **Antal.** Højst 5 aktive scannerkonti, én pr. mønt, ingen timegrænse. De tæller ikke med i ændring 11's 3 pladser.
   En mønt kan få en ny konto 24 timer efter, at dens forrige blev stoppet eller sprunget over.

5. **Automatisk stop.** Ændring 11 punkt 5 med disse tal: tab ≥ 5 % af startkapitalen; 24 timer på pause; kilden
   betaler ikke (funding − gebyrer ≤ 0) 3 dage efter start; ingen position i 2 sammenhængende døgn; udløb efter 30
   dage; brugerens `lane-off`. Der er ingen historisk forventning, så z-reglen og "lovende"-reglen gælder ikke.
   Risikoreglernes drawdown-pause ved 10 % gælder uændret.

6. **Ærlige forbehold.** Mønterne er ofte små med tynde bøger og store spreads; ordren går gennem bogens 20 niveauer,
   så slippage bogføres ærligt, og spread-reglen pauser kontoen. En høj præmie kan betyde forestående afnotering
   eller en presset short; ændringen i spot/perp-forholdet rammer kontoen. Indgang ved første 1 %-måling betaler
   omkostninger også for kortvarige udsving. Reglerne er ikke valgt efter afkast; intet afkast er beregnet.

7. **Netværk.** Ingen nye værter og ingen nye forespørgsler fra scanneren; reglen læser scannerens egne målinger i
   registret. Handlen bruger USD-M som i dag og spot-bogen fra `data-api.binance.vision` (ændring 11 punkt 8). Højst
   5 ekstra mønter.

8. **Rækkefølge.** Tekst (denne) → kode og tests i dev → brugeren deployer (regel B: ikke 2026-10-31..11-13).

## Ændring 12a (2026-10-19): præmien måles hvert minut — før kode

**Beslutning:** brugeren besluttede 2026-10-19 i sessionen: "ja til 12a, kør videre - gerne meget meget meget meget
hurtigere end 1 time ... jeg gider ikke være begrænset af den tid der" (datoen 2026-11-14, som Claude havde foreslået).
Ændring 12 gælder uændret ud over dette.

1. **Ny agent `premium-watch` (hvert 60. sekund).** Den laver præcis scannerens måling (b) (`perp_premium` =
   mark/index − 1 fra `https://fapi.binance.com/fapi/v1/premiumIndex`, kun handlede USDT-perps på krypto, tærskel
   0,5 %) og skriver de markerede mønter og `symbols_compared` som rækker i `observations`. Listen over handlede perps
   (`exchangeInfo`) hentes højst én gang i timen. Agenten skriver ingen `market.event`, opretter ingen kandidater og
   ændrer ingen tilstand; scannerens timevise kørsel med alle detektorer er uændret.
2. **Virkning.** "Scanning" i ændring 12 punkt 2-3 er enhver måling af præmien (scannerens eller agentens). Ind- og
   udreglen gælder derfor pr. minut: ind ved ≥ 1 % i én måling eller ≥ 0,5 % i to i træk; ud, når den er væk i to i
   træk. Regel 3's "over 3 timer gammel" gælder uændret.
3. **pm_lp.** Polymarket og Hyperliquid måles fortsat kun én gang i timen af scanneren. Agenten taler kun med
   `fapi.binance.com` (allerede tilladt, 2 forespørgsler i minuttet ved fuld kørsel, vægt ≈ 11 af Binances 2.400 pr.
   minut), så pm_lp-indsamlerens forbindelser og DNS påvirkes ikke målbart. Deploy før 2026-10-31 (regel B).
4. **Ærlige forbehold.** Med målinger hvert minut kan en kortvarig præmie give ind- og udgang inden for få minutter.
   Hver rundtur koster cirka 0,4-0,5 % af positionen i gebyrer og spread; stopreglerne i ændring 12 punkt 5 (tab
   ≥ 5 %, kilden betaler ikke efter 3 dage) stopper en konto, der taber på det. Scannerens daglige opgørelse
   (ændring 9) tæller fortsat markerede klokketimer, så flere målinger pr. time ændrer ikke dens regel.
5. **Data.** Cirka 1.440 ekstra `symbols_compared`-rækker og nogle tusinde markerede rækker pr. døgn i registret.

### Præcisering af ændring 11 (2026-10-19): kontoen handler de mønter, varianten blev testet på — fejlrettelse

Fundet i produktionen samme aften: den første banekonto (`LANE_d9f91862c8`, `carry_filter` 14 dage / 5 %) havde
kurven "alle mønter" og handlede derfor banens univers (31 mønter med begge bøger), mens varianten kun var evalueret
på de 15 mønter, der bestod kvalitetsreglen i `explore0`. Det følger ordlyden i punkt 3, men ikke testen.

1. Punkt 3 rettes: når kurven er "alle mønter", er kurven de mønter, artefaktet registrerede som evalueret (`coins`),
   ikke banens univers. Mønter uden begge live-bøger udelades stadig, og gulvet er stadig 5.
2. En aktiv konto, der handler mønter, som varianten ikke blev testet på, stoppes automatisk (`lane.retired`, regel
   `basket`) og lukkes reducerende. Varianten afprøves ikke igen (punkt 2); næste kandidat tager pladsen.
3. Strengere, ikke lempeligere: kontoen kan kun handle det, testen dækker.

## Ændring 12b (2026-10-19): endnu mere aggressiv — før kode

**Beslutning:** brugeren bad 2026-10-19 om at gøre systemet "endnu mere aggressiv" og svarede på Claudes forslag til
12b: "Jeg vil gerne have den". Kun simuleret handel; ændring 10 punkt 1, 11 og 12 gælder ud over dette. Stopreglerne
er uændrede, så det, der ikke virker, stoppes lige så hurtigt.

1. **Scannerkonti** (ændring 12 punkt 2 og 4): ind ved den første måling med positiv præmie ≥ 0,5 % (scannerens
   tærskel); højst 10 aktive scannerkonti. Udreglen (væk i to målinger i træk) er uændret.
2. **Banekonti** (ændring 11 punkt 3): højst 6 aktive, højst to pr. mekanismefunktion, højst én ny pr. 10 minutter.
3. **Banen** (ændring 10a punkt 4): højst 60 nye varianter pr. job (stadig ét job ad gangen, højst ét i timen) og
   højst 10.080 varianter pr. ISO-uge, så 60 i timen kan holdes hele ugen.
4. **Ærligt:** flere konti og lavere indgang betyder flere rundture og mere betalt spread i små mønter. Det giver
   hurtigere svar på, hvad der betaler sig, ikke mere bevis. Intet er afkastvalgt.
5. **Netværk:** ingen nye værter. Højst 10 + 6 konti; bøger hentes ved start, ved timens opgørelse og før ordrer.

## Ændring 12c (2026-10-20): scannerkonti holder gennem mindst én funding-afregning — før kode

**Beslutning:** brugeren svarede 2026-10-20 "Ja" på Claudes forslag efter nattens resultater. Kun simuleret handel;
ændring 11, 12, 12a og 12b gælder ud over dette.

**Hvad natten viste (registret, read-only):** tre scannerkonti (EPIC, HOT, MITO) gik ind og ud igen inden næste
funding-afregning; hver endte cirka 0,62-0,69 % under start (gebyrer cirka 20 USD, funding 0-1,70 USD). Præmierne
forsvandt på få timer, så mekanismen (funding) nåede ikke at betale.

1. **Scannerkonti holder gennem mindst én afregning** (ændrer ændring 12 punkt 3). En åben position lukkes først, når
   præmien er væk i to målinger i træk **og** enten en funding-afregning efter indgangen er bogført for perp-benet,
   eller der er gået 12 timer siden indgangen (Binance afregner højst hver 8. time). Indgangen er den seneste fill,
   der åbnede perp-benet fra 0.
2. **12b og 12c deployes samlet.**
3. **Ærligt:** at vente på afregningen kan give højere tab, hvis spot/perp-forholdet bevæger sig imod kontoen;
   tabsreglen (5 %) og risikoreglerne gælder uændret.
4. **Ikke ændret:** pauser genoptages fortsat kun af et menneske (ændring 7 punkt 1).

## Ændring 12d (2026-10-20): daglig rapport over bane- og scannerkonti — ikke-afgørende — før kode

**Beslutning:** Claude lovede brugeren 2026-10-19/20 en daglig rapport, så brugeren kan se, om en konto nærmer sig
pilotudkastets krav (`research/PILOT_BANE_UDKAST.md` punkt 1); brugeren svarede "kør videre automatisk". Rapporten
afgør intet, ændrer ingen tilstand, handler ikke og henter ingen data.

1. **Job.** `lane_report|<dag>` (report-1) for hvert afsluttet UTC-døgn, tidligst kl. 00:30 UTC dagen efter, som
   `scan_digest`. Det skriver `artifacts/_lane/<dag>.json` og hændelsen `research.lane_report` (decisional false).
2. **Indhold pr. konto** (alle `LANE_`-konti, der var aktive i døgnet): kilde (bane/scanner), mekanismefunktion,
   mønter, start, status (aktiv/pause/stoppet med regel), værdi og netto ved døgnets sidste opgørelse, bogført
   funding, betalte gebyrer, funding − gebyrer, største fald fra top og hele døgn live.
3. **Pilotens papirkrav** (udkastet punkt 1, med brugerens 3 døgn): hele døgn live ≥ 3, netto > 0, funding − gebyrer
   > 0, største fald < 3 %, ikke stoppet. Rapporten viser hvert krav som opfyldt eller ej. Slippage-kravet kræver
   en sammenligning med modellen, som ikke er bygget; det vises som "ikke målt".
4. **Ingen virkning.** Et opfyldt krav starter intet. En pilot kræver stadig brugerens tal, nøgle og en dateret
   protokol.

## Ændring 12e (2026-10-20): scannerkonti går efter vedvarende høj funding, ikke præmie — før kode

**Beslutning:** brugeren svarede 2026-10-20 "Ja til 12e" og bad Claude træffe den slags datadrevne beslutninger selv.
Kun simuleret handel; ændring 11, 12, 12a-12d gælder ud over dette.

**Data (registret, read-only, 24 timer til 2026-10-20 ca. 08:15 UTC):** 665 målinger, 87 markerede mønter, 248
episoder med positiv præmie. Median varighed 1 minut; ingen varede 60 minutter. Forventet funding under episoderne:
median 0,04 %, p90 0,25 % pr. afregning. En rundtur koster cirka 0,6 %. Præmien er derfor et dårligt signal; det,
der kan betale, er vedvarende høj funding (kun EPIC havde cirka 0,25 % pr. afregning).

1. **Måling.** `premium-watch` gemmer desuden `predicted_funding` (Binances `lastFundingRate` fra samme
   `premiumIndex`-svar) som markeret række for hver handlet perp med forventet funding ≥ 0,10 % pr. afregning. De
   seneste værdier for alle perps holdes i flådens hukommelse (ingen række), til brug for udreglen. Ingen ny
   forespørgsel.
2. **Ind** (erstatter ændring 12 punkt 2 og 12b punkt 1). En mønt får en scannerkonto, når den seneste måling har
   forventet funding ≥ 0,10 %, og gennemsnittet af de 3 seneste afregnede rater (USD-M `fundingRate`, som i dag) er
   ≥ 0,05 %. En lukket konto åbner igen, når de to seneste målinger begge har forventet funding ≥ 0,10 %.
3. **Ud** (erstatter ændring 12 punkt 3 og 12c punkt 1). En position lukkes, når to målinger i træk viser forventet
   funding under 0,01 % (rentegulvet), og en afregning efter indgangen er bogført eller der er gået 12 timer. Uden en
   frisk måling (højst 5 minutter gammel) holdes positionen.
4. **Uændret:** 10 pladser, én pr. mønt, kun mønter med begge live-bøger, stopreglerne i 12 punkt 5, 24 timers
   pause før en stoppet mønt kan få en ny konto. En mønt, der springes over, fordi fundingen ikke er vedvarende, kan
   prøves igen efter 1 time.
5. **Ærligt:** høj funding følger ofte stærk efterspørgsel efter lange positioner; spot/perp-forholdet kan bevæge sig
   imod kontoen, og en mønt kan blive afnoteret. Tabsreglen (5 %) gælder. Intet afkast er beregnet.

### Præcisering af ændring 12e (2026-10-20): markedets funding vises — ikke-afgørende

Claude efter brugerens mandat 2026-10-20 ("det er beslutninger som denne du også skal tage"), fordi dashboardet ikke
viste, hvorfor scannerkontiene står stille. Ingen regel ændres; intet her starter, stopper eller vælger en konto.

1. `premium-watch` skriver ved hver måling tre ikke-markerede rækker i `observations` (instrument `binance_perps`):
   `funding_median` (median af forventet funding over alle handlede perps), `funding_above_floor` (andelen strengt
   over 0,01 %) og `funding_top` (højeste forventede funding; mønten står i rækkens payload).
2. Forsidens panel viser de seneste tre tal og, når ingen mønt opfylder 12e punkt 2, at systemet venter, og hvorfor.
3. Cirka 4.300 rækker pr. døgn. Ingen ny forespørgsel.

## Ændring 13 (2026-10-20): Hyperliquid-funding-konti — lang Binance spot, kort Hyperliquid perp — før kode

**Beslutning:** brugeren svarede 2026-10-20 "ja til 13 gør alt for at det kan lykkes" på Claudes forslag, efter at
Binance-funding var lav (median 0,005 % pr. afregning, 18 % af perps over rentegulvet). Kun simuleret handel; ingen
ordrer, nøgler eller penge på nogen børs. Ændring 10 punkt 1 og ændring 11 gælder: aldrig bevis, ingen formelle
rækker, ingen saldo, ingen alfa. Mekanismen er F1's (funding modtaget af et kort perp-ben, afdækket med spot i samme
mønt, ikke prisforudsigende), men perp-benet ligger på en anden børs, så kontiene kan aldrig blive en F1-instans.

1. **Konto.** En banekonto (ændring 11) med kilden `hl`: `LANE_<10 hex>` af nøglen `hl|<mønt>|<time>`, 10.000 USD,
   én mønt, mærket "HL-KONTO (Hyperliquid-funding, simuleret, aldrig bevis)". Ben: Binance spot `<MØNT>USDT.SPOT`
   (lang) og Hyperliquid perp `HL:<MØNT>` (kort), samme mængde, halvdelen af kontoens værdi pr. ben.
2. **Data (kun offentlige, ingen nøgle).** Hyperliquid `POST https://api.hyperliquid.xyz/info` (allerede tilladt for
   scanneren, gennem samme funktion): `metaAndAssetCtxs` (forventet funding pr. time for alle perps), `fundingHistory`
   (afregnet funding pr. time), `candleSnapshot` (1h-åbningskurser til at prissætte afregninger) og `l2Book`
   (ordrebog). Spot-bogen fra `data-api.binance.vision` som i ændring 11 punkt 8. Mønter med præfikset `k` eller
   `@` og afnoterede mønter udelades.
3. **Måling.** `premium-watch` henter `metaAndAssetCtxs` hvert minut, skriver `hl_predicted_funding` (forventet funding
   × 8, så tallet kan sammenlignes med Binances 8-timers afregning) som markeret række for mønter ≥ 0,10 %, og holder
   alle værdier i flådens hukommelse.
4. **Ind.** Forventet funding × 8 ≥ 0,10 %, gennemsnittet af de seneste 24 afregnede timer × 8 ≥ 0,05 %, og begge
   bøger (Binance spot og Hyperliquid) kan hentes. En lukket konto åbner igen, når de to seneste målinger begge er
   ≥ 0,10 %.
5. **Ud.** To målinger i træk med forventet funding × 8 under 0,01 %, og mindst 8 timer siden indgangen. Uden en frisk
   måling (højst 5 minutter) holdes positionen.
6. **Omkostninger og funding.** Gebyr 0,10 % pr. ben (Binance spot; forsigtigt også for Hyperliquid, hvis gebyr er
   cirka 0,045 %), ekstra slippage 0,02 %, ordrer gennem bøgernes niveauer. Funding bogføres for `HL:`-benet pr. time
   efter ændring 9 punkt 2 (beløb = − position × pris × rate; prisen er åbningskursen for den time, der starter ved
   afregningen).
7. **Antal og stop.** Højst 10 aktive HL-konti, én pr. mønt, uafhængigt af bane- og scannerkonti. Stopreglerne er
   scannerkontiens (ændring 12 punkt 5): tab ≥ 5 %, 24 timers pause, funding − gebyrer ≤ 0 efter 3 dage, 2 døgn uden
   position, 30 dage, `lane-off`. 24 timers ventetid for en stoppet mønt, 1 time for en mønt, der blev sprunget over.
8. **Ærlige forbehold.** To børser: kursen på Hyperliquid kan afvige fra Binances spot (basisrisiko), og en rigtig
   konto ville kræve kapital på begge børser og overførsler. Hyperliquid kan ændre gebyrer, funding-formel eller
   afnotere. Intet afkast er beregnet.

## Ændring 12f (2026-10-20): tærskel og udregel for scanner- og HL-konti efter et datastudie — før kode

**Beslutning:** Claude efter brugerens mandat 2026-10-20 ("det er beslutninger som denne du også skal tage", "gør alt
perfekt"). Kun simuleret handel. Gælder scannerkonti (ændring 12, 12c, 12e) og HL-konti (ændring 13).

**Data:** cachede Binance-funding-filer i `explore0` (2020-03..2021-12, 32 mønter, ingen netværk; banens eget vindue,
aldrig familiernes). Regel som 12e: ind ved afregnet rate ≥ X og snit af de 3 seneste ≥ X/2; hold til to afregninger
i træk er under 0,01 %; 0,6 % omkostning pr. rundtur. Script: `research/tools/fund_study.py` (committet med denne).

| X pr. 8 t | handler | gns. netto | median | vundet | median hold |
|---|---|---|---|---|---|
| 0,030 % | 250 | +5,1 % | +1,2 % | 67 % | 58 afregninger |
| 0,050 % | 225 | +5,6 % | +1,8 % | 72 % | 67 |
| 0,100 % | 144 | +7,8 % | +3,0 % | 87 % | 86 |
| 0,200 % | 73 | +11,6 % | +6,8 % | 86 % | 89 |

1. **Ind:** forventet funding ≥ 0,05 % pr. 8 timer (HL: × 8), og snittet af de seneste 3 afregninger (HL: 24 timer
   × 8) ≥ 0,025 %. Erstatter 0,10 % og 0,05 % i ændring 12e punkt 2 og 13 punkt 4. `premium-watch` markerer derfor
   forventet funding fra 0,05 %.
2. **Ud:** to afregnede rater i træk under 0,01 % pr. 8 timer (HL: to afregnede timer i træk, × 8), og 12c's
   regel (en afregning efter indgangen eller 12 timer; HL: 8 timer). Erstatter udreglen på to minut-målinger i 12e
   punkt 3 og 13 punkt 5, fordi gevinsten i studiet kommer af at holde i uger.
3. **Udløb:** 60 dage i stedet for 30 (median hold 58-89 afregninger, cirka 3-4 uger; mange længere).
4. **Ærligt:** 2020-2021 havde usædvanligt høj funding; studiet ser bort fra bevægelser i spot/perp-forholdet og fra
   afnoteringer. Det er ikke bevis for 2026; det vælger blot tærsklen og udreglen på data i stedet for skøn.
   Stopreglerne (tab ≥ 5 %, 24 t pause, kilden betaler ikke efter 3 dage, 2 døgn uden position) er uændrede.

## Ændring 10d og 11b (2026-10-20): banen må hente data når som helst; banekonti skal handle nu — før kode

**Beslutning:** brugeren 2026-10-20: "lad vær med at begrænse af pm_lp osv" (10d) og mandatet til datadrevne
papirbeslutninger (11b). Kun simuleret handel og banens eget vindue; F1, F2 og pm_lp's protokol er uændrede.

**10d.** Ændring 10b punkt 2's netværksvindue for banen (før 2026-10-24 og fra 2026-11-14) ophæves: banen må hente
sine `explore0`-filer fra `data.binance.vision` når som helst, stadig højst 2 samtidige downloads i hele lab'en.
COIN-M-filer følger fortsat ændring 8 punkt 17 (fra 2026-11-28), fordi den regel står i en fil, F1's godkendelse er
bundet til.

**11b. Data (produktionens register 2026-10-20 ca. 10:07 UTC):** banen havde evalueret 450 varianter, og 433 opfyldte
de tre krav i ændring 10 punkt 5 (2020-2021 betalte høj funding for næsten alt). 4 af 6 aktive banekonti havde ingen
position, fordi deres regel ikke går ind ved 2026's funding (fx hysteresis kræver 21,9 % APR).

1. **Start (ændrer ændring 11 punkt 3):** en banekonto startes kun, hvis variantens egen funktion på de live data
   (samme som kontoen handler på) giver +1 i mindst én mønt i kurven lige nu. Ellers registreres `lane.skipped` med
   grunden "ville ikke holde noget nu", og varianten kan prøves igen 24 timer senere (ikke permanent).
2. **Stop (tilføjes ændring 11 punkt 5):** en banekonto uden position i 3 sammenhængende døgn stoppes (`flat`), så
   pladsen går til en variant, der handler. De øvrige stopregler er uændrede.
3. **Ærligt:** det vælger varianter efter, at de handler nu, ikke efter, at de tjener nu; kontiene er stadig aldrig
   bevis.

## Ændring 13a (2026-10-20): HL-kontiens tærskel efter et studie af årets data; ingen spread-konto — før kode

**Beslutning:** Claude efter brugerens mandat 2026-10-20 ("byg spread-kontoen hvis den tjener", "deploy det selv når
den tjener"). Kun simuleret handel.

**Data (offentlige, hentet 2026-10-20 med `research/tools/fetch_recent_funding.py`):** Binance USD-M `fundingRate`
(op til 1000 afregninger pr. perp, typisk 2026-07..10; 522 perps) og Hyperliquid `fundingHistory` (60 dage; 172
mønter), plus listen over Binance spot-par. Studierne: `research/tools/recent_study.py`, `spread_study.py`.

1. **Binance-carry (scannerkonti):** reglen fra 12f (0,05 %) gav i år +0,81 % i snit pr. handel (median +0,44 %, 57 %
   vundet, 68 handler på 356 mønter med spot). Den beholdes. Ved rentegulvet (0,01 %) tabte carry (24 % vundet).
2. **Spread mellem Hyperliquid og Binance (perp mod perp):** tabte ved alle tærskler 0,02-0,2 % pr. 8 t, også ved
   0,3 % omkostning (gns. −0,12 til −0,27 % pr. handel, 8-30 % vundet; spreadet lukker inden for cirka et døgn).
   Der bygges ingen spread-konto.
3. **HL-konti (ændrer 13 punkt 4 og 12f punkt 1 for HL):** ind ved forventet funding × 8 ≥ 0,10 % og snittet af de
   seneste 24 afregnede timer × 8 ≥ 0,05 %. Studiet: 56 handler, gns. +0,51 %, median +0,14 %, 61 % vundet, mod
   den gamle regels +0,24 % / −0,02 % / 49 %. Udregel og stopregler uændrede.
4. **Ærligt:** 60-90 dages data, ingen spot/perp-bevægelser og ingen gebyrforskel modelleret; det er valg af regel
   på årets data, ikke bevis.

## Ændring 11c (2026-10-20): banekandidater gennemgås adversarielt, før de må handles — før kode

**Beslutning:** Claude efter brugerens mandat 2026-10-20 ("Sende lovende resultater videre til uafhængig gennemgang",
"Giv agenterne konkret arbejde"). Strengere, ikke lempeligere; kun banekonti (ændring 11) og kun `explore0`.

**Baggrund (registret 2026-10-20):** 433 af 450 evaluerede varianter opfyldte ændring 10 punkt 5, og kandidaterne gik
direkte til papirhandel uden den adversarielle gennemgang, alle formelle eksperimenter får. De tre adversarial-agenter
havde 0 jobs på et døgn.

1. **Job `lane_review|<10 hex af nøglen>`** (adversarial-agenterne) for en kandidat, før den kan blive en banekonto. Den
   læser kun `explore0` (banens eneste dataadgang) og kører den eksisterende motor (`lab/engine/adversarial.py`) på
   kandidatens funktion, parametre og mønter:
   - look-ahead-trunkering og forgiftning (krydssektionelle versioner): skal være eksakte;
   - én bars forsinkelse: netto-Sharpe ved 2× omkostninger ≥ 1,0 (samme krav som kandidaten selv);
   - placebo (positioner blandet i blokke af 24 bars, 60 træk, fast seed): p < 0,10 (`catalogue.PLACEBO_P_MAX`).
2. **Resultat:** artefakt `artifacts/_lane_review/<hex>.json` og hændelsen `research.lane_review` (afgør kun, om
   kandidaten må blive en banekonto; aldrig bevis, ingen formelle rækker).
3. **Kø:** højst 6 gennemgange i kø ad gangen, bedste netto-Sharpe først, hver kandidat én gang.
4. **Start (ændrer ændring 11 punkt 3 og 11b):** en banekonto startes kun for en kandidat med bestået gennemgang.
   Aktive konti berøres ikke.

## Ændring 12g (2026-10-20): scanner- og HL-konti åbnes kun, hvis 3 døgns funding dækker bøgernes omkostning — før kode

**Beslutning:** Claude efter brugerens mandat 2026-10-20. Kun simuleret handel; strengere, ikke lempeligere.

**Data (registret):** scannerkontiene EPIC, HOT og MITO (2026-10-19/20) endte hver cirka 0,62-0,69 % under start; gebyrerne
var cirka 0,2 % og resten spread og slippage i tynde bøger. Stopreglen "kilden betaler ikke" vurderer efter 3 døgn.

1. **Ved start** (ændring 12e punkt 2 og 13a): de to bøger, der allerede hentes for at se, om mønten kan handles,
   bruges til at beregne omkostningen for en rundtur af kontoens faktiske størrelse (halvdelen af 10.000 USD pr. ben):
   gebyrer (0,10 % pr. ben, som kontiene bogfører) plus for hvert ben prisforskellen mellem midten og den
   gennemsnitlige fyldpris ved at gå bogen igennem, købt og solgt (indgang og udgang), plus 0,02 % slippage pr. fill.
2. **Krav:** forventet funding × 9 (3 døgn à 3 afregninger; HL: forventet × 8 × 9) ≥ den beregnede omkostning i
   procent af ét bens værdi. Ellers `lane.skipped` med tallene, og mønten kan prøves igen efter 1 time.
3. **Ærligt:** bogen kan ændre sig, og funding kan falde; kravet sorterer kun handler fra, der er tabt på forhånd.

## Ændring 11d (2026-10-20): banegennemgangens placebo og forsinkelse rettes — før kode

**Beslutning:** Claude efter brugerens mandat 2026-10-20 og ønske om at undersøge, hvorfor 11c altid bestod ("en
kandidat må ikke bestå, blot fordi alle tests bruger den samme fejlbehæftede antagelse"). Kun banens gennemgang
(11c); den formelle pipelines adversarielle trin ændres ikke.

**Data (`research/tools/placebo_study.py`, 5 tilfældige af 667 kandidater, `explore0`, 20 træk):**
- Placebo i blokke af 24 bars: snit −28 til −37 i netto-Sharpe mod kandidaternes 4,1-6,5. Blandingen giver langt
  flere skift og dermed omkostninger; den måler omsætning, ikke timing, og p er altid 0.
- Cirkulær forskydning (samme positioner, omsætning og eksponering, forskudt mindst 7 døgn mod fundingen): snit −1,7
  til 4,6; én af fem fik p = 0,20.
- Forsinkelse 1 time mod 24 timer: næsten ens (reglerne beslutter én gang i døgnet), så 1 time tester intet.

1. **Placebo (erstatter 11c punkt 1, fjerde led):** hver mønts position forskydes cirkulært med et tilfældigt antal
   bars mellem 168 og længden − 168 (60 træk, seed 17); p = andelen af træk med netto-Sharpe ≥ kandidatens ved 2×
   omkostninger; krav p < 0,10.
2. **Forsinkelse (erstatter 11c punkt 1, tredje led):** 24 bars (én beslutningsperiode) i stedet for én; netto-Sharpe
   ved 2× omkostninger ≥ 1,0.
3. **Gennemgange efter den gamle metode tæller ikke:** en kandidat uden en 11d-gennemgang gennemgås igen, før den kan
   blive en banekonto. Aktive konti berøres ikke.
4. **Ærligt:** fem kandidater er en lille stikprøve; ændringen er begrundet i metoden (blokplaceboen er skæv for
   strategier med lav omsætning), ikke i at få færre kandidater.

### Præcisering af ændring 11d (2026-10-20, før kode): markedet forskydes, ikke positionerne; Sharpe pr. beslutningsperiode

Under kodningen viste en kontrol på syntetisk støj-funding (ingen timing at finde), at forskydning af positionerne
stadig var skæv: omslaget giver ét ekstra skift pr. mønt, og opdelingen i UTC-døgn lægger kl. 00:00-afregningen og
skiftet kl. 01:00 i samme døgn. Over 8 støjserier fik en regel med 1 dags tilbageblik p = 0,0 i 7 af 8.

1. Placeboen forskyder hver mønts **marked** (bars og afregnet funding) cirkulært med et tilfældigt antal hele døgn
   (mindst 7, højst længden − 7); positionerne, omsætningen og omkostningerne er uændrede.
2. Sharpe beregnes over **beslutningsperioder** (døgn fra kl. 01:00 UTC, familiernes beslutningstidspunkt) for både
   kandidaten og placeboerne.
3. Kontrol (syntetisk, 20 træk): ægte regimer p = 0,0; konstant funding p = 1,0; støj med 3 dages tilbageblik p fordelt
   over 0,15-1,0 (0 af 8 under 0,10); støj med 1 dags tilbageblik 3 af 8 under 0,10 — de strategier har netto-Sharpe
   omkring −27 og falder på forsinkelseskravet.

## Ændring 12h (2026-10-20): eksekvering måles pr. mønt og ben; usynkroniserede bøger afvises; kandidater klassificeres — før kode

**Beslutning:** Claude efter brugerens mandat 2026-10-20 (prioritet 3: realistisk eksekveringsmodel pr. mønt). Kun
simuleret handel; strengere, ikke lempeligere. Ingen ny datakilde: de to bøger, 12g allerede henter.

1. **Måling ved hvert startforsøg (scanner- og HL-konti):** for hvert ben registreres i hændelsen (`lane.started` eller
   `lane.skipped`, feltet `execution`): kilde, symbol, tidspunkt for hentningen, spread (ask − bid i procent af
   midten), dybde i de 20 niveauer på hver side (USD), gennemsnitlig fyldpris (VWAP) for den planlagte størrelse købt og
   solgt i procent fra midten, samt basis (spot-midte / perp-midte − 1) og tiden mellem de to hentninger. Midten bruges
   kun som referencepunkt, aldrig som fyldpris.
2. **Synkronisering:** er der mere end 5 sekunder mellem de to bøger, afvises forsøget som "usynkroniserede bøger"
   (`lane.skipped`), og omkostningen registreres som UKENDT. En bog, der ikke kan fylde størrelsen, giver UKENDT og
   afvisning (som i 12g).
3. **Observeret dekomponering pr. konto (visning):** for hver bane-, scanner- og HL-konto vises netto opdelt i funding,
   gebyrer, betalt forskel mellem fyldpris og midte (spread og slippage) og resten (pris- og basisbevægelse målt ved
   midten). Delene summerer til netto og tælles kun én gang.
4. **Klassifikation pr. kandidat (visning, afgør intet nyt):** "afvist af omkostninger" (12g), "utilstrækkelige data"
   (tynd eller usynkroniseret bog, eller funding ikke vedvarende), "afventer fremadtest" (en aktiv eller stoppet
   konto) og "klar til formel, menneskegodkendt validering" (en konto, der opfylder pilotudkastets papirkrav og har
   mindst 30 afsluttede handler for samme mekanisme; i dag ingen). Ingen kandidat kaldes profitabel, fordi funding
   overstiger et estimeret spread.
5. **Ærligt:** gebyrerne er VIP0-satser (antaget, ikke målt); dybden er kun de 20 niveauer, børsen viser; basisændring
   gennem holdeperioden måles på aktive konti fra deres opgørelser, ikke forudsagt.

## Ændring 14 (2026-10-20): nye gratis datakilder — handelsstørrelser, historisk bogdybde, opmærksomhed og makrokalender — før kode

**Beslutning:** Claude efter brugerens ja 2026-10-20 ("Lad os klare dette" til nyheds/makrodata og trade-historik).
Kun data; ingen ny strategi, ingen gate ændres, intet handles. Alle kilder er offentlige og gratis uden nøgle;
ingen konto oprettes og intet betales.

1. **Kilder og indhold:**
   - `aggTrades` (data.binance.vision, USD-M, månedlige filer): hver handel med pris, mængde, tid og hvem der tog
     likviditeten. Sammenfattes pr. time og mønt: antal, købt og solgt mængde og notional, købt og solgt notional i
     fire størrelsesklasser (< 1.000, 1.000–10.000, 10.000–100.000, ≥ 100.000 USD), største handel, VWAP. Klines har
     allerede antal og taker-køb pr. time; det nye er størrelsesfordelingen.
   - `bookDepth` (data.binance.vision, USD-M, daglige filer, findes fra 2023-01): samlet dybde i notional ved ±1…5 % fra
     midten, cirka hvert 30. sekund. Sammenfattes pr. time: gennemsnit og minimum pr. niveau og antal øjebliksbilleder.
     Formål: historisk likviditet til omkostningsmodellen i stedet for antagelser.
   - Wikipedia-sidevisninger (wikimedia.org REST, dagligt, menneskelige brugere) for Bitcoin, Ethereum,
     Cryptocurrency og de 8 universmønter. Formål: opmærksomhed som tidsstemplet nyhedsproxy.
   - Makrokalender: FOMC-møders erklæringstidspunkt (federalreserve.gov, historiske sider pr. år) og BLS'
     udgivelsestidspunkter for CPI og Employment Situation (bls.gov, plan pr. år). Kun tidspunkterne; udfaldet (tallene,
     overraskelsen) hentes ikke.
   - GDELT og andre nyhedskilder hentes ikke nu (GDELT tillader én forespørgsel pr. 5 s og dækker ikke 2020–2023
     pålideligt i det gratis API; licenserede nyhedsfeeds kræver nøgle eller betaling og kræver brugerens ja).
2. **Perioder:** kun til og med 2023-12-31. 2024 er holdout, 2025-01-01 og frem er reserveret; begge hentes aldrig af
   denne indsamling, og koden afviser en enhed, der slutter efter 2023-12-31.
3. **Point-in-time:** en timesammenfatning må kun bruges fra timens slutning. En daglig sidevisning for dag D må kun
   bruges fra D+2 00:00 UTC (offentliggøres med op til et døgns forsinkelse; antaget, konservativt). Kalendertidspunkter
   er kendt på forhånd (planerne offentliggøres før året) og må bruges før begivenheden; intet udfald gemmes.
4. **Omfang og budget:** pilot = de 8 universmønter (BNB, XRP, DOGE, ADA, LINK, LTC, AVAX, DOT) for 2023 (train og
   validation): aggTrades cirka 6,5 GB og bookDepth cirka 1,3 GB download (målt i S3-listen 2026-10-20). Et samlet
   downloadbudget på 10 GB håndhæves af koden; derudover kræves brugerens ja (alle 32 mønter 2020–2023 er 151 GB).
5. **Integritet og plads:** hver Binance-fil kontrolleres mod sin `.CHECKSUM` (sha256); en fil, der ikke matcher,
   afvises. Råfilen slettes efter sammenfatning; filens sha256, størrelse og URL registreres i hændelseskæden
   (`ingest.done`). Der hentes kun, når der er mindst 2 GB fri disk ud over filens størrelse. Én fil ad gangen.
6. **Brug:** dataene er ikke bevis for noget. En strategi, der bruger dem, kræver sin egen hypotese skrevet og committet
   før test, og læses gennem datagatewayen som al anden forskningsdata.

## Rettelse 2026-10-21 til ændring 12e, 12f og 13a og til udkastet F3: studiets indtægt var for høj

**Beslutning:** Claude under brugerens mandat 2026-10-21. Kun tekst; ingen regel ændres.

`research/tools/recent_study.py` summerede funding normaliseret til 8 timer i stedet for den betalte rate. Det
fordoblede indtægten for 4-timers mønter og ottedoblede den for Hyperliquid. Tallene "+0,81 % i snit pr. handel
(median +0,44 %, 57 % vundet)" i ændring 12f/13a punkt 1 og i `research/drafts/F3_FUNDING_DYNAMISK_UDKAST.md` er
derfor for høje. Med rettet kode og data hentet 2026-10-21 (`research/studies/CARRY_COST_2026-10-21.md`) er den
gennemsnitlige brutto-funding pr. handel +0,79 % for Binance-reglen (64 handler) og +1,11 % for HL-reglen (36);
netto er positiv ved 0,3 % omkostning (gebyrer alene) og negativ ved den observerede 1,5 %. HL-tallet i 13a punkt 3
kan ikke genskabes fra koden (dagens kode giver en anden stikprøve); det står som ikke-reproducerbart.

Reglerne i 12e, 12f, 12g og 13a beholdes: 12g kræver i forvejen, at 3 døgns forventet funding dækker de live bøgers
omkostning, og stopper netop de tynde mønter, hvor studiet viser tab.

## Ændring 12i (2026-10-21): scanner-kontiens funding-tal regnes pr. 8 timer, som 12f skriver — før kode

**Beslutning:** Claude under brugerens mandat 2026-10-21 ("FJERN TEKNISK GÆLD", "følg dens konsekvenser helt
igennem systemet"). Kun simuleret handel. Ingen tærskel ændres: koden bringes i overensstemmelse med den godkendte tekst.

**Fejlen (verificeret i en uafhængig revision 2026-10-21):** 12e/12f/12g skriver tærsklerne pr. 8 timer (ind ved
forventet funding ≥ 0,05 %, vedvarende snit ≥ 0,025 %, ud under 0,01 %, 3 døgns funding = rate × 3 × 3). Koden
sammenlignede Binance' rå rate pr. afregning med tallene. For mønter med 4-timers afregning (de fleste i 2026) var
indgangen dermed dobbelt så streng, udgangen udløstes allerede ved rentegulvet (0,005 % pr. 4 t = 0,01 % pr. 8 t), og
12g undervurderede 3 døgns funding med faktor 2 (1-timers mønter: faktor 8). Bogført funding (`sim_funding`) brugte
den rå rate og var korrekt. Hyperliquid (× 8) var korrekt.

1. **Afregningsinterval:** Binance' `fapi/v1/fundingInfo` (offentlig, GET, højst én gang i timen) giver hver mønts
   interval; mønter uden for listen har 8 timer. Afregnede rater omregnes med intervallet mellem afregningerne.
2. **Pr. 8 timer:** forventet funding, de afregnede rater i vedvarende- og ud-reglen og 12g's 3-døgns indtægt regnes
   som rate × 8 / interval. Rå rate og interval registreres ved siden af i målingen og i startforsøget.
3. **Ukendt interval** (fundingInfo kan ikke hentes og intet kendt): 8 timer (den hidtidige, strengere adfærd).
4. **Visning:** markedets funding-median og andel over gulvet vises pr. 8 timer, sammenlignelig med HL × 8.
5. **Ærligt:** det rettede studie (`research/studies/CARRY_BASIS_PLAN.md`) viser ingen fordel ved realistiske
   omkostninger; rettelsen gør reglen korrekt, ikke profitabel. 12g stopper fortsat starter, hvis 3 døgns funding ikke
   dækker de live bøgers omkostning.

## Ændring 15 (2026-10-21): statistikken gøres sværere at snyde — streng look-ahead-gate, rettet baneplacebo, adskilt udvælgelse og gennemgang, PSR med autokorrelation — før kode

**Beslutning:** brugeren 2026-10-21 ("Ja, gør alt" til de fem anbefalinger i statistik-revisionen,
`research/studies/STAT_AUDIT_2026-10-21.md` fund 1–4 og 7). Alle punkter er strengere eller neutrale; ingen gate
lempes, ingen tærskel sænkes. Kun simuleret handel. Afgørelser, der allerede er registreret, ændres ikke; punkterne
gælder trin, der køres efter deploy.

1. **Streng look-ahead-test er en gate (fund 1).** Position i tjener bar i's lukke-til-lukke-afkast
   (`backtest.gross`) og må derfor ikke se bar i's lukkekurs.
   - **Testen:** ved et snit i bar i fjernes alle senere barer; bar i beholder kun sin åbningskurs (lukkekurs :=
     åbningskurs); funding afregnet efter bar i's åbning fjernes; timeværdier (volumen, taker) fra barer, der åbner ved
     eller efter snittet, fjernes; daglige værdier for døgn, der ikke er afsluttet ved snittet, fjernes. Positionen i
     snittet må ikke ændre sig (tolerance 1e-12). Én mønt: 40 snit (seed 11). Tværsnit: 20 fælles snit (seed 11).
   - **Hvor:** pipelinens adversarielle trin (katalogskabeloner og familieinstanser screenet af pipelinen) — både i
     "adversarial checks pass" og i v2's "exact look-ahead and poison tests" før validering — og banegennemgangen
     (11c). Den eksisterende trunkerings- og gifttest beholdes ved siden af.
   - **Allerede kontrolleret** (syntetiske data, 2026-10-21): alle 28 katalogskabeloner, alle 8 F1-varianter og
     F2-udkastet dbasis — ingen look-ahead fundet. Ingen tidligere afgørelse ændres derfor.
2. **Baneplaceboen forskyder afkast, ikke prisniveauer, og med ét fælles skift (fund 2 og 3).** Erstatter 11d's
   placebo i banegennemgangen:
   - Pr. placebotræk trækkes ÉT helt antal døgn k, ligefordelt i [7, døgn − 7), fælles for alle kandidatens mønter
     (bevarer samvariationen mellem mønterne).
   - Hver mønts lukke-til-lukke-afkast forskydes cirkulært med k × 24 barer, og en ny prisserie bygges fra møntens
     første lukkekurs med de forskudte afkast (ingen spring ved omløbet; en konstant position får samme samlede
     afkast som i virkeligheden). Afregnet funding forskydes k døgn som i 11d. Positionerne er uændrede.
   - Sharpe over beslutningsperioder (døgn forskudt til 01:00 UTC) som i 11d; 60 træk, seed 17; p = andelen af træk
     med Sharpe ≥ den faktiske; kravet er fortsat p < 0,10.
3. **Banens udvælgelse og gennemgang bruger adskilte data (fund 4).** explore0 (2020-03..2021-12) deles:
   **udvælgelse S = 2020-03-01..2020-12-31** og **gennemgang R = 2021-01-01..2021-12-31**.
   - **Udforskning (metode "15"):** positionerne beregnes på hele explore0 (reglerne er point-in-time; punkt 1 og
     revisionens scanning viser det), men alle tre krav i ændring 10 punkt 5 (net Sharpe ≥ 1 ved 2× omkostninger,
     attributionen, positiv i ≥ 2 af 3 tredjedele) og de viste tal (net Sharpe, netto, dage) regnes kun på afkast i
     S. Varianter, der er udforsket efter en ældre metode, udforskes igen (de tæller i ugeloftet som før).
   - **Kandidater:** kun resultater efter metode "15".
   - **Gennemgang (metode "15"):** look-ahead-testene (inkl. punkt 1) på hele explore0; forsinkelsen (24 barer, net
     Sharpe ≥ 1 ved 2× omkostninger) og placeboen (punkt 2) kun på afkast i R. Gennemgange efter ældre metoder
     tæller ikke.
   - **Forventning (ændring 11 punkt 6):** fra resultatet i S.
   - **Konti, der allerede kører,** fortsætter under deres egne stopregler; ingen ny konto startes fra en kandidat
     eller gennemgang efter en ældre metode.
   - **Ærligt:** med S på 10 måneder og R på 12 bliver der sandsynligvis få eller ingen nye banekonti. Det er den
     korrekte konsekvens af, at udvælgelse og gennemgang på samme data gav 18–21 % falske fund mod nominelt 9,8 %.
4. **PSR i katalogets fremadtest korrigeres for autokorrelation (fund 7).** Held-tjekket i ændring 2 punkt 4 bruger
   PSR med den effektive stikprøve n_eff = n × (1 − ρ̂) / (1 + ρ̂), hvor ρ̂ er første-ordens autokorrelationen i
   fremadvinduets daglige nettoafkast, når ρ̂ > 0 (ellers n). Gælder fremadtest, der læses efter deploy (MVRV's vindue
   starter 2026-11-01). Familiernes PSR_kons (ændring 8) ligger i den frosne F1-kode (`lab/families/__init__.py`) og
   ændres ikke her; revisionen viser, at den undervurderer ved stærk autokorrelation (φ 0,8). En rettelse dér kræver,
   at brugeren ophæver F1-frysningen.
5. **Vagten starter automatisk ved opstart — først når S7 er åben.** `research/LINUX_DRIFT.md` forbyder autostart af
   vagten, før S7-gaten er åben (7 rene dage; 1,94 af 7 den 2026-10-21). S7-reglen ændres ikke. Unit-filen
   `research/systemd/lab-watch.service` lægges klar; brugeren installerer den selv, når S7 er åben (kommandoerne står i
   `LINUX_DRIFT.md`).
6. **Ikke omfattet** (revisionens fund 5 og 6: pipelinens blok-placebo og bootstrap-bloklængden) — de er ikke en del
   af de fem godkendte anbefalinger og kræver eget ja.

## Ændring 14a (2026-10-21): tre målehypoteser på ændring 14's data — H1 makrodybde, H2 og H3 trin 1 — før kode

**Beslutning:** brugeren 2026-10-21 ("Ja, gør alt" til de tre hypoteseudkast). Teksten er udkastet
`research/drafts/AENDRING14_HYPOTESER_UDKAST.md` som committet i bd97063 (git-blob
e7077ad579aaf1bac0a0a582cc8bb6f8bf2ca55c, sha256 93487b5f2bfdddcd1940ffa3e78b9d8d2fe73dd14c0b63cb8d282e9d7337ccc6);
den låses hermed uændret. Intet handles, og intet her ændrer en papirkonto.

1. **Godkendt til én kørsel hver:** H1 `makrodybde` (udkastets H1 punkt 1–9), H2 `opmaerk` trin 1 og H3 `smaahandel`
   trin 1 (punkt 1–4, 6–9 for trin 1). Måling, kontrol, vinduer, point-in-time, minimumsantal, train-gate, test,
   placebo/bootstrap, seeds og stopkriterier er udkastets, uden ændring. Train læses først; fejler train-gaten,
   læses validering aldrig.
2. **Fejlrate:** en ny, separat målefejlrate på 0,05 for de tre tests (α = 0,05/3 ≈ 0,0167 pr. test), uden for W0 og
   alle eksisterende budgetter (ændring 2, 7 og 8). Brugeren har accepteret, at laboratoriets samlede fejlrisiko
   dermed stiger. Testene går ikke gennem katalogets DSR og hæver ingen andens hurdle.
3. **Ikke godkendt:** trin 2 af H2/H3 (en afdækket carry-familie; kræver ændring 8's `approve-family`, skrevet af
   brugeren selv, og tagets sidste plads), mere data (aggTrades 2022, fremadvinduer, wikimedia i familiekoden) og
   brug af H1's udskydelsesregel i papirkontiene (kræver en senere ændring efter et PASS).
4. **Læsning:** ingest-filerne læses gennem en læser i laboratoriets datalag, der afviser alt efter 2023-12-31 og
   alt uden for testens vindue (H1 og H3: `train` 2023-01..2023-08 og `validation` 2023-09..2023-12; H2: `train3`
   2022-01..2023-06 og `validation3` 2023-07..2023-12). Datadækningen kontrolleres før kørslen; mangler data, er
   udfaldet UNTESTABLE efter udkastets regler.
5. **Registrering:** hvert udfald (PASS, REJECTED eller UNTESTABLE) skrives uændret i hændelseskæden og i
   `research/studies/` med kode-commit, inputs og seeds. Et udfald afgør intet for handel.

## Ændring 15a (2026-10-21): pipelinens placebo og bootstrap-bloklængden rettes — før kode

**Beslutning:** brugeren 2026-10-21 ("Ja det skal være perfekt og aggressivt", svar på revisionens fund 5 og 6 i
`research/studies/STAT_AUDIT_2026-10-21.md`). Strengere eller neutralt; ingen gate lempes. Afgørelser, der allerede
er registreret, ændres ikke; punkterne gælder trin, der køres efter deploy.

1. **Pipelinens placebo (fund 5).** Det adversarielle trin bruger samme placebo som banen efter ændring 15 punkt 2
   (afkast forskudt cirkulært med ét fælles helt antal døgn pr. træk, ny prisserie fra første lukkekurs, funding
   forskudt samme antal døgn, positioner uændrede; 60 træk, seed 17) i stedet for blok-ombytning af positionerne.
   Begrundelse: ombytning i 24-timers blokke øger omsætningen og dermed placebosættenes omkostninger, så langsomme
   strategier uden fordel fik 27–40 % falske fund. Sharpe over døgn fra 00:00 UTC (katalogets beslutningstid) og fra
   01:00 UTC for familieinstanser (ændring 8 punkt 3). Kravet er uændret: train placebo p < 0,10 (v2) og rapporteret
   ellers.
2. **Bootstrap-bloklængden (fund 6).** Den ensidede nedre grænse (og 95 %-intervallet) i pipelinens gates — katalogets
   validering og fremadtest, holdout og familiernes fremadtest — bruger blokke på
   **b = max(5, ⌈b̂⌉) døgn**, hvor b̂ er Politis & Whites automatiske bloklængde (2004, rettet af Patton, Politis &
   White 2009) for blok-bootstrap af den daglige nettoserie: flad-top-vindue, m̂ = mindste m hvor |ρ̂(m+k)| <
   2·√(log10 n / n) for k = 1..max(5, ⌈√log10 n⌉), M = 2m̂, b̂ = (2Ĝ² / D̂)^(1/3) · n^(1/3) med D̂ = (4/3)ĝ(0)², højst
   n/3. Aldrig under de hidtidige 5 døgn. Antal træk (2.000) og seed er uændrede. Bloklængden registreres ved
   resultatet.
   - Begrundelse: ved AR(1) φ = 0,8 gav 5-døgns blokke 22 % falske fund mod nominelt 10 %.
   - F1's frosne filer ændres ikke; familiernes fremadtest beregnes af pipelinen, og punktet gælder derfor også dér,
     før F1's vindue (fra 2026-12-01) er læst.

## Ændring 15b (2026-10-21): den nedre grænse kalibreret — 15a punkt 2 alene var ikke nok — før kode

**Beslutning:** Claude under brugerens ja til fund 6 ("perfekt og aggressivt"), før 15a er kodet færdig og deployet.
Strengere end 15a.

1. **Kalibrering (syntetiske AR(1)-serier, 184 døgn, ingen markedsdata):** andel falske fund for "nedre 10 %-grænse
   > 0" ved middelværdi 0 — 5-døgns blokke 14,5 / 16,5 / 26,5 % ved φ = 0 / 0,3 / 0,8; 15a's automatiske blokke
   14,5 / 16,5 / 22,5 % (200 serier). Normalgrænsen med AR(1)-variansfaktor (punkt 2) 9,3 / 9,8 / 9,5 %, og minimum af
   de to 8,2 / 9,3 / 9,3 % (600 serier); styrken ved en ægte fordel på 0,15 sd pr. døgn 0,76 mod 0,78 for 5-døgns
   blokke. Script: `research/tools/lb_calibration.py`.
2. **Reglen:** hvor 15a punkt 2 gælder, er den ensidede nedre grænse **minimum** af (a) blok-bootstrap-grænsen med
   15a's bloklængde og (b) x̄ − z_(1−q) · s · √((1 + ρ̃) / ((1 − ρ̃) · n)), hvor s er stikprøvens standardafvigelse,
   ρ̃ = ρ̂ + (1 + 3ρ̂) / n begrænset til [0; 0,99] (første-ordens autokorrelation, bias-rettet) og q gatens kvantil
   (0,10 eller 0,05). 95 %-intervallet er fortsat bootstrap. Begge grænser registreres ved resultatet.

## Ændring 15c (2026-10-21): placeboens skift gøres eksakt — før deploy

**Beslutning:** Claude under brugerens ja til ændring 15 og 15a, før 15a deployes. Rettelse af en fejl fundet ved
afprøvning; ingen gennemgang efter ændring 15 er nået at køre med den fejlbehæftede udgave (gennemgangsjobbene blev
ikke oprettet, se punkt 3).

1. **Fejlen:** ændring 15 punkt 2 skiftede timeafkastene cirkulært over hele serien (n − 1 afkast, ikke et multiplum
   af 24). Efter omløbet lå døgngrænserne én time forskudt, og alle placebotræk delte den samme omgruppering. På
   syntetiske data fik en konstant position uden timing derfor p = 0,0 (et falsk fund).
2. **Rettelsen (gælder banens placebo, ændring 15 punkt 2, og pipelinens, 15a punkt 1):** kun hele
   beslutningsperioder (24 barer fra beslutningstiden) flyttes, cirkulært med det fælles antal perioder k; hver bar
   får afkastet fra baren på samme plads i kildeperioden, og hver afregning fundingen på samme plads i kildeperioden.
   Ufuldstændige perioder i enderne står uændrede. En simuleret Sharpe inden for 1e-9 af den faktiske tæller som ≥
   (uafgjort går imod strategien). Positioner og omkostninger følger fortsat positionerne.
   - Afprøvning (syntetisk): 40 langsomme tilfældige positioner uden timing bestod p < 0,10 i 2,5 % af tilfældene
     (blok-placeboen: 27–40 % ifølge revisionen); en regime-timet regel består fortsat.
   - En konstant position får ikke nødvendigvis p = 1: dens indgangsomkostning lander i placeboen på et andet døgns
     afkast. Den består gaten med den nominelle sandsynlighed eller mindre.
3. **Banens gennemgangsjob** blev efter ændring 15 givet samme job-id som gennemgangen af samme kandidat efter 11d og
   derfor afvist som dubletter (ingen gennemgang efter metode 15 kørte). Navnet indeholder nu metoden; ældre
   job-rækker og artefakter genbruges eller overskrives aldrig.

## Ændring 16 (2026-10-21): begivenheds- og nyhedsscanner — kun data, intet handles — før kode

**Beslutning:** brugeren 2026-10-21 (direktivet "AGGRESSIVE AUTONOMOUS RESEARCH & MARKET INTELLIGENCE", punkt 2B, og
"JA TIL ALT du har tilladelse til alt"). Kun data; ingen strategi, ingen gate ændres, intet handles. Plan:
`research/PLAN_DIREKTIV_2026-10-21.md`.

1. **Kilder (offentlige, gratis, uden nøgle, kun GET):**
   - Binance' meddelelser (`www.binance.com/bapi/composite/v1/public/cms/article/list/query`): kategorierne nye
     listninger (48), delistninger (161) og Binance-nyheder (49). Udgiverens eget tidsstempel (`releaseDate`).
   - RSS fra Cointelegraph (`cointelegraph.com/rss`) og CoinDesk (`www.coindesk.com/arc/outboundfeeds/rss`).
   - GDELT DOC 2.0 (`api.gdeltproject.org`), forespørgsler om bitcoin/krypto, højst én pr. 6 s og med eksponentiel
     ventetid ved afvisning (429).
2. **Hver post:** kilde, kildens id, URL, titel, publiceringstid (fra kilden), indsamlingstid, kategori, nævnte mønter
   (fundet i titlen efter faste regler) og en hash af kilde og id (dublet-kontrol). Gemmes som observationer
   (`detector` "news/1", `metric` "news_item"); intet udfald eller fortolkning gemmes som fakta.
3. **Point-in-time:** en post må kun bruges fra sin indsamlingstid. Undtagelse: Binance' meddelelser, hvis
   publiceringstid kilden selv sætter, må hentes bagud (én gang, højst 1 forespørgsel pr. 2 s) og bruges fra
   publiceringstiden + 1 time; de markeres `backfill` og med forbeholdet, at en titel kan være rettet senere.
4. **Drift:** en ny agent `news-watch` henter hvert 10. minut (GDELT hvert 15.); hver kilde fejler for sig, og fejl
   registreres (`metric` "news_error") uden at stoppe andet. Dækningspanelet viser kilder, antal, friskhed og fejl.
5. **Brug:** dataene er ikke bevis. En hypotese på dem kræver sin egen præregistrering før test (ændring 8 eller en
   egen ændring), og ingen test må bruge poster fra før hypotesen blev committet som "ny" evidens for den.

## Ændring 16a (2026-10-21): målehypotese H4 `notering` — funding efter nye listninger — før kode

**Beslutning:** Claude under brugerens ja 2026-10-21 ("JA TIL ALT du har tilladelse til alt", direktivet punkt 2C).
Kun måling; intet handles, ingen gate ændres.

1. **Låst tekst:** `research/drafts/H4_NOTERING_FUNDING.md` (git-blob 16c1e6a71bc68033a6d36fb03546b900c8908a67,
   sha256 753b21aef638c72583295ebee570b0365c3c01e20c538175ff5a0581fca0603d), skrevet før nogen funding for nye
   listninger er hentet. Én kørsel.
2. **Fejlrate:** egen målefejlrate α = 0,05 for denne ene test, uden for W0 og alle andre budgetter (som ændring 14a).
3. **Data:** meddelelserne fra ændring 16 og funding-arkiver fra `data.binance.vision` for de listede symboler, kun
   med første afregning i 2022-01..2023-12 og kun afregninger til og med 2023-12-31. Overslag: højst et par hundrede
   små månedsfiler.
4. **Registrering:** udfaldet (PASS, REJECTED eller UNTESTABLE) skrives uændret i hændelseskæden og i
   `research/studies/` med kode-commit, inputs og seed. Et PASS giver kun grundlag for et senere forslag.

## Ændring 16b (2026-10-21): de faste møntregler læser også Binance' futures-listningstitler — før kode og før H4 køres

**Beslutning:** Claude, før Binance-meddelelserne er hentet bagud og før H4 (ændring 16a) er kørt; ingen funding for
nye listninger er hentet eller set. Kun titlernes format er set (fx "Binance Futures Will Launch USDⓈ-M MOVR Perpetual
Contract …", "… Launch RSR & LRC USDT-Margined Perpetual Contracts …"): de nævner tickeren uden parentes, så ændring
16's regler fandt ingen mønt, og H4 ville være blevet UNTESTABLE af en formfejl.

1. **Ny fast regel (ud over parentes- og XXXUSDT-reglen):** i en titel, der indeholder "Futures Will Launch" og
   "Perpetual", læses teksten mellem "Launch" og "Perpetual"; ordene "USDⓈ-M", "USDS-M", "USDT-Margined",
   "USDC-Margined", "Coin-Margined" og "and" fjernes; resten deles ved mellemrum, "&" og ","; hvert stykke, der kun
   består af store bogstaver og cifre (2–15 tegn), er en mønt.
2. **Gælder** `lab/news.py` (mønterne ved hvert opslag) og dermed H4's stikprøve. H4's øvrige regler er uændrede;
   COIN-M-titler ("Coin-Margined") er fortsat uden for H4.

## Ændring 16c (2026-10-21): målehypotese H5 `notering_lav` — kun på data, H4 ikke læste — før kode

**Beslutning:** Claude under brugerens mandat 2026-10-21 ("Kør videre automatisk og tag selv beslutning"). Kun
måling; intet handles.

1. **Låst tekst:** `research/drafts/H5_NOTERING_LAV.md` (git-blob 38e0701cecd1ec622e67fdca6d678d3565709378, sha256 71b6058b6ca29f9e7c2e63309d429b0ccc0b153d34a220173cf7dfbc08a143c6).
2. **Kilde og adskillelse:** hypotesen kommer fra H4's train-data; den testes kun på symboler annonceret i
   2023-07..2023-12, som H4 aldrig læste (H4 stoppede ved sin train-gate). Én kørsel.
3. **Fejlrate:** egen α = 0,05 for denne ene test, uden for alle andre budgetter.

## Ændring 16d (2026-10-21): H5 gentages fremad (H5F) — før data findes

**Beslutning:** Claude under brugerens mandat 2026-10-21 ("Kør videre automatisk og tag selv beslutning"), efter
H5's PASS (`research/studies/MAALING_16c_H5_2026-10-21.md`). Kun måling; intet handles.

1. **Låst tekst:** `research/drafts/H5F_NOTERING_FREMAD.md` (git-blob 3c961925a01a826abd3bab4e8ac8dfc10e889357, sha256 bb2337b6df5a4c7ad9c3735992f8ebfa3207aa30267eb354ce15b743934d4aa3), skrevet før nogen
   listning i stikprøven er annonceret.
2. **Fejlrate:** egen α = 0,05. Koden skrives, når data findes, og må ikke ændre den låste tekst.
3. **Data indsamles allerede automatisk** af `news-watch` (ændring 16); funding hentes én gang efter døgn 60 for det
   20. symbol.

## Ændring 16e (2026-10-21): scanner- og HL-konti undgår mønter, som Binance har annonceret afnotering af — før kode

**Beslutning:** Claude under brugerens mandat 2026-10-21 ("Kør videre automatisk og tag selv beslutning"). Kun
simuleret handel; ingen gate, ingen holdout og intet evalueringskriterium ændres. Reglen gør scannerkontiene mere
forsigtige, ikke mindre.

**Data (registret 2026-10-21, ændring 16's meddelelser mod `lane.started`):** af de 3 scannerkonti, der nogensinde er
startet, stod 2 på mønter med en afnoteringsmeddelelse: EPICUSDT blev startet ca. 24 timer *efter* "Binance Will Delist
EPIC, QUICK on 2026-10-28" og stoppede på pause (spread_anomaly) med −62 USDT; MITOUSDT fik "Binance Futures Will Delist
PTBUSDT and MITOUSDT USDⓈ-M Perpetual Contracts (2026-10-23)" 1,2 døgn efter start. En carry-position på begge ben
kræver, at både spot og perp handler; afnotering af ét af dem slutter positionen til en ukendt pris.

1. **Hvilke meddelelser:** gemte `news_item`-observationer (ændring 16) i kategorien `delisting`, hvis titel begynder
   med "Binance Will Delist", "Binance to Delist", "Binance Futures Will Delist" eller "Binance Futures to Delist".
   Margin-, lån-, Alpha-, staking- og "Notice of Removal"-meddelelser tæller ikke (de fjerner ikke mønten selv eller
   nævner den ikke i titlen).
2. **Mønter (fast regel):** i teksten efter "Delist" er hvert ord af store bogstaver og cifre med mindst ét bogstav en
   mønt; ordene "USD", "USDT", "USDC", "BUSD" og "M" (fra "USDⓈ-M"/"USDT-Margined") fjernes, og et slut-"USDT", "USDC"
   eller "BUSD" på et længere ord skæres af (IPUSDT → IP).
3. **Tidspunkt (point-in-time):** en meddelelse tæller fra sit `usable_from` (aldrig før) og indtil 30 døgn efter
   sit `published_ts` (præciseret før kode: den første hentning gemte også ældre meddelelser med `usable_from` =
   hentetidspunktet; de er allerede gennemført og skal ikke spærre i 30 døgn mere).
4. **Start:** scanneren springer en mønt over, før den bruger et af sine prøveforsøg, og noterer `lane.skipped` med
   årsagen "afnotering annonceret (16e)" og titlen.
5. **Stop:** en aktiv scannerkonto, hvis mønt får en sådan meddelelse, stoppes med reglen `delisting`; positioner
   lukkes reduce-only som ved de øvrige stopregler.
6. **HL-konti (ændring 13)** har Binance-spot som det ene ben: for dem gælder punkt 1–5 kun spot-meddelelserne
   ("Binance Will Delist", "Binance to Delist"); Binance' futures-afnoteringer rører ikke Hyperliquid-perpen.
   **Gælder ikke** banekonti (ændring 11; frosne familiekurve).
7. **Kendte huller:** meddelelser, der ikke nævner mønten i titlen ("Multiple Perpetual Contracts", "Notice of Removal
   of Spot Trading Pairs"), fanges ikke.

## Ændring 16f (2026-10-21): H5X — H5's lave tidlige funding målt mod Hyperliquid i stedet for spot — før data findes

**Beslutning:** Claude under brugerens mandat 2026-10-21 ("Kør videre automatisk og tag selv beslutning"; "Forsæt med
alt du kan"), efter H5's PASS. Kun måling; intet handles.

1. **Låst tekst:** `research/drafts/H5X_NOTERING_TVAERS.md` (git-blob fc330b8a9c6cf6d994dd5e0645be15215a8fa52b, sha256 add256bd724d1c31791581124a8769873d5d8796ec5b3ac830e9f2896b1bccdb), skrevet før nogen
   listning i stikprøven er annonceret.
2. **Fejlrate:** egen α = 0,05, uden for alle andre budgetter (også H5F's).
3. **Data** indsamles allerede af `news-watch` (meddelelserne); funding hentes én gang fra Binance og Hyperliquid
   efter døgn 7 for det 20. symbol. Koden skrives, når data findes, og må ikke ændre den låste tekst.

## Ændring 17 (2026-10-21): automatisk hypotesepipeline — begivenhedstyper × udfald, screening i udforskningsvinduet, låsning før måling; GDELT's adgangsbegrænsning — før kode

**Beslutning:** Claude under brugerens mandat 2026-10-21 ("Tag beslutning osv du bestemmer og gør alt automatisk";
plantrin 3 i `research/PLAN_DIREKTIV_2026-10-21.md`). Hidtil kunne nye observationer ikke blive til forskningsopgaver
uden en hånd. Ingen eksisterende gate, holdout, evalueringskriterium eller godkendelse ændres; intet handles.

1. **Observationer og sporbarhed.** Kandidater dannes af Binance' meddelelser i registret (detector `news/1`,
   kilde binance.com). En begivenhed er (observationens id, mønt, t), hvor t = postens `usable_from` (ændring 16 punkt
   3) og mønterne er `news.coins(titel)` (16/16b). Én begivenhed pr. (type, mønt) pr. 30 døgn: den første.
   **Faste begivenhedstyper** (titlen matcher; ingen andre uden en ny ændring):
   - `spot_listing`: begynder med "Binance Will List" eller "Binance Lists";
   - `innovation_zone`: "Innovation Zone";
   - `futures_listing`: "Futures Will Launch" og "Perpetual", ikke "Coin-Margined";
   - `launchpool`: "Launchpool";
   - `network_swap`: "Network Upgrade", "Hard Fork", "Mainnet", "Token Swap", "Contract Swap", "Migration" eller
     "Redenomination";
   - `delisting`: "Will Delist" eller "to Delist", ikke "Futures";
   - `futures_delisting`: "Futures Will Delist" eller "Futures to Delist";
   - `airdrop`: "Airdrop";
   - `staking`: "Staking", "Savings" eller "Earn";
   - `margin`: "Margin" og ("Will Add", "Adds", "Enabled" eller "Launch"), ikke "Tiers";
   - `margin_tiers`: "Leverage & Margin Tiers" eller "Leverage and Margin Tiers";
   - `funding_interval`: "Funding Rate" og ("Interval", "Frequency" eller "Settlement").
2. **Udfald (faste)** på Binance USD-M-perpen `<mønt>USDT`, fra månedsfilerne på data.binance.vision (1 t-klines og
   fundingRate):
   - `ar_1d`, `ar_7d`: log-afkast af lukkekursen fra den første time ≥ t til t + 1 d / t + 7 d minus BTCUSDT's i samme
     timer;
   - `fund_7d`: gennemsnitlig funding pr. 8 t i (t, t + 7 d] minus i (t − 7 d, t];
   - `vol_3d`: log(realiseret volatilitet af timeafkast i (t, t + 3 d] / i (t − 7 d, t]);
   - `volume_1d`: log(gennemsnitlig timevolumen i quote i (t, t + 1 d] / i (t − 7 d, t]).
   Et vindue skal have mindst 90 % af sine timer; ellers udelukkes begivenheden for det udfald (tælles med årsag).
   En hypotese er (type, udfald) med nøglen `type|udfald|m17`: 12 × 5 = 60 kandidater.
3. **Generering og prioritering (automatisk).** `strategy-1` registrerer hver kandidat én gang som hændelsen
   `research.hypothesis` med dens kilder (antal begivenheder, første og sidste observations-id, sha256 af
   begivenhedslisten) og regner ved hver kørsel en prioritet:
   `2·min(1, n/40) + min(1, n30/5) + 1[n ≥ 15] − min(1, mangler/200) − overlap`, hvor n er begivenheder i
   screeningsvinduet, n30 er samme type indsamlet live de seneste 30 døgn (nyhedsværdi), `mangler` er måneds-filer, der
   ikke er i cachen (beregnings- og downloadomkostning), og overlap = 0,5, hvis samme type allerede er screenet med
   et andet udfald, plus 0,25, hvis samme udfald allerede er screenet med en anden type.
4. **Deduplikering og negative resultater.** En nøgle med et resultat screenes aldrig igen under m17. Alle resultater
   (SCREEN_PASS, SCREEN_FAIL med årsag, UNTESTABLE) gemmes som hændelsen `research.hypothesis_screen` i den
   hashkædede log og vises på dashboardet. `futures_listing|fund_7d` er DÆKKET af H4/H5 (16a, 16c) og screenes ikke.
5. **Screening (automatisk; udforskning, aldrig bevis).** Kun vinduet explore0 (2020-03-01 – 2021-12-31): t og hele
   udfaldsvinduet skal ligge i det. Data kun fra data.binance.vision gennem banens hentevej (10b/10d, de 2 fælles
   pladser og den huskede 404-liste); andre måneder afvises. Højst ét job `hypo_screen|<nøgle>` ad gangen (agenterne
   cost-1 og cost-2, tung opgave under RAM-vagten), højeste prioritet først.
   **Test:** mindst 15 begivenheder, ellers UNTESTABLE. Gennemsnit af y; tosidet fortegnsskift-test (eksakt ved
   n ≤ 20, ellers 20.000 træk, seed 7). Placebo: samme mønter med t − 30 d (inde i vinduet).
   **SCREEN_PASS** kræver: p ≤ 0,005; samme fortegn i 2020 og 2021 (hver med mindst 5 begivenheder); placeboens
   p > 0,05; og for `ar_*` |gennemsnit| ≥ 0,46 % (F1's rundtur). Ellers SCREEN_FAIL med årsag.
6. **Udkast.** En SCREEN_PASS skriver et præregistreringsudkast (påstand med retning, mekanisme, data, baseline,
   placebo, omkostninger, kriterium, risici, plan) som `data/lab/hypotheses/<nøgle>.json` og `.md` og vises på
   dashboardet som "venter på låsning". Udkastet er ikke bevis.
7. **Låsning (det eksisterende krav: dateret ændring før data).** Udkastet kopieres til `research/drafts/auto/` og
   låses af en dateret ændring i denne fil med linjen `LÅS-17 <nøgle> <sha256 af json-filen>`. Først når den
   committede protokol (HEAD) indeholder linjen, og filens sha256 stemmer, oprettes jobbet
   `hypo_measure|<nøgle>` automatisk. Den k'te låste hypotese (rækkefølgen i filen) får α_k = 0,05 · 2^−k; summen
   er under 0,05, et eget målebudget uden for alle andre.
8. **Måling (automatisk efter låsning; agenterne validation-1 og validation-2).** Samme udfald og regler som i
   udkastet. train3 (2022-01 – 2023-06): mindst 15 begivenheder og ensidet p < 0,05 i udkastets retning, ellers
   REJECTED (eller UNTESTABLE ved for få). Kun derefter validation3 (2023-07 – 2023-12): mindst 8 begivenheder og
   ensidet p < α_k → PASS, ellers REJECTED. Læseren afviser måneder uden for fasen og alt fra 2024-01-01 (holdout og
   reserverede data læses aldrig). Resultatet registreres som `research.measurement` (regel 17). PASS er en måling, ikke
   en handelsregel; en papirkonto kræver sin egen daterede ændring.
9. **GDELT.** Målt 2026-10-21: 10 afvisninger (HTTP 429) mellem 13:54 og 20:15 UTC, sidste gemte post kl. 18:33, og
   én enkelt manuel forespørgsel kl. 20:4x blev også afvist. GDELT begrænser altså denne adresse, ikke kun vores
   tempo. Derfor: grundinterval 30 min (var 15), backoff fordobles op til 24 t (var 6 t), en `Retry-After`-header
   respekteres, og backoff-tilstanden overlever genstart (den læses af registret: sidste GDELT-fejl og antal fejl
   siden sidste gemte GDELT-post). Kilden står som begrænset på dashboardet. Binance' 429 kom kun under den bagudrettede
   hentning og klares af dens ventetider; ingen ændring.
10. **Aldrig:** ordrer, papirkonti, familier, alfa-budgetter for familier, holdout 2024, reserverede data fra 2025,
    `pm_lp`. Nye begivenhedstyper, udfald eller tærskler kræver en ny dateret ændring.

### Præcisering af ændring 17 (2026-10-21, før kode og før nogen screening): ord matches som hele ord

En test af typerne viste, at punkt 1 skrevet bogstaveligt lader `margin` fange futures-listninger ("USDT-Margined …
Will Launch …") og `staking` fange "Learn" (via "Earn"). Rettelse, før nogen kandidat er screenet:

1. Alle ord og fraser i punkt 1 matches som **hele ord** (ordgrænse før og efter; "Margin" matcher ikke "Margined",
   "Earn" matcher ikke "Learn"). `spot_listing` er fortsat titlens begyndelse.
2. `margin` kræver desuden, at titlen ikke indeholder "Futures".
Intet andet ændres.

## Ændring 17a (2026-10-22): udfald fra første tilgængelige pris, også på spot — før kode

**Beslutning:** Claude under brugerens mandat ("Tag beslutning … gør alt automatisk"). **Data:** de første 26 screeninger
under 17 (2026-10-21 21:52–22:2x UTC) blev alle UNTESTABLE: spot_listing 0 af 156 begivenheder med data,
innovation_zone 1 af 57, futures_listing 1–5 af 98, staking 3 af 32, airdrop 11 af 37, launchpool 0 af 23. Årsag:
mønterne i disse meddelelser havde typisk hverken perp eller spotmarked før meddelelsen, så udfald med en kurs ved t
eller et før-vindue kan ikke regnes. Ingen tærskel ændres; 17's 60 kandidater og deres resultater står uændret.

1. **Fire nye udfald** (samme 12 typer, 48 nye kandidater, nøglen `type|udfald|m17`):
   - `far_1d`, `far_7d`: perpen `<mønt>USDT`; P0 = lukkekursen for den første time, der åbner ≥ t og senest t + 72 t,
     med en kurs; P1 = lukkekursen 24 t / 7 d senere; y = ln(P1/P0) − samme for BTCUSDT-perpen i de samme timer;
   - `sar_1d`, `sar_7d`: det samme på Binance **spot** `<mønt>USDT` (1 t-klines fra
     data.binance.vision/data/spot/monthly; BTCUSDT spot som marked).
   Findes ingen kurs i (t, t + 72 t], udelukkes begivenheden ("no price within 72 h").
2. Alt andet fra 17 gælder uændret: vinduer (screening i explore0; måling i train3 og validation3 efter LÅS-17),
   prioritet, deduplikering, screeningskriterier (p ≤ 0,005, samme fortegn i 2020 og 2021, placebo t − 30 d med
   p > 0,05, |gennemsnit| ≥ 0,46 % for alle fire, da de er afkast), α_k-rækken og "aldrig"-listen.
3. Spotfilerne hentes gennem banens hentevej (kilden er allerede tilladt for banen, ændring 8 punkt 17 og 10d) og
   lægges i den fælles cache `spot_klines`.

## Ændring 17b (2026-10-22): låsning af den første SCREEN_PASS — `futures_listing|sar_7d|m17` — før data

**Beslutning:** Claude under brugerens mandat, efter ændring 17 punkt 7. Ingen kode ændres.

1. **Screening** (explore0, hændelse `research.hypothesis_screen`, 2026-10-21/22): spotkursen (mod BTCUSDT spot) på
   mønter, som Binance annoncerer en ny USD-M-perp for, faldt i 7 døgn fra første tilgængelige spotpris efter
   meddelelsen: n 91, gennemsnit −15,1 %, median −14,5 %, 27 % positive, p 0,0001; 2020 −20,7 % (45), 2021 −9,6 % (46);
   placebo (t − 30 d) +1,5 %, p 0,65 (n 58).
2. **Kendte forbehold, nævnt før målingen:** det blev valgt blandt 108 kandidater (60 under 17 og 48 under 17a, ikke 60 som
   udkastets "risks" skriver); udkastets "data"-felt nævner kun USD-M-filer, men udfaldet `sar_7d` bruger spotfilerne
   (ændring 17a). Koden måler efter type, udfald og retning; teksten herover gælder.
3. **Ingen 2022–2023-priser er læst** af pipelinen. H4/H5 læste perp-funding for 2022–2023-listninger, ikke spotpriser.
4. **Lås** (α_1 = 0,05 · 2^−1 = 0,025; ensidet, retning negativ):

LÅS-17 futures_listing|sar_7d|m17 1ad14ece81b13db537ed0c0174344d1594a60e5711ecbdd178c01949623541c6

5. Et PASS er en måling, ikke en handelsregel. En papirkonto, der udnytter den, kræver sin egen daterede ændring med
   omkostninger og stopregler.

## Ændring 18 (2026-10-22): datapauser hæves automatisk, når data har virket i en time — før kode

**Beslutning:** brugeren svarede "Ja" 2026-10-22 til at netværksfejl ikke længere skal kræve et menneske. Det er en
lempelse af ændring 7 punkt 1 ("kun et menneske kan genoptage") for én regel, derfor brugerens egen godkendelse.

**Baggrund:** natten til 2026-10-22 (ca. 00:06–03:13 UTC) mistede værten netværket ("No route to host"). 11 simulerede
konti blev sat på pause af reglen `data_fetch` og stod stille i ca. 6 timer, til brugeren skrev `sim-resume` for hver.
Pausen var rigtig (intet blev handlet på manglende data), men genoptagelsen krævede ingen vurdering.

1. **Kun reglen `data_fetch`** (en offentlig datahentning fejlede: Binance eller CoinMetrics), og kun på simulerede
   konti (`SHADOW_`, `FWD_`, `LANE_`, også scanner- og HL-konti). Alle andre pauseregler — drawdown, `data_stale`,
   `data_missing`, `data_inconsistent`, spread — kræver stadig et menneske (`sim-resume`). FAIL_CLOSED er uændret.
2. **Prøvehentning.** Mens en konto står på pause af `data_fetch`, prøver den timevise kørsel den samme fulde
   hentning og de samme kontroller (forældede timebarer, krydset bog), som kontoen handler på. Resultatet skrives som
   en risikohændelse `PROBE` (værdi 1 = alt virkede, 0 = fejl med fejlteksten). En prøve åbner aldrig noget.
3. **Genoptagelse.** Kontoen genoptages (en `CLEAR` med regel `auto_resume`, actor `system:risk`), når den aktuelle
   prøve virker, og en ubrudt række af vellykkede prøver siden pausen begyndte mindst 50 minutter før. Med timevise
   kørsler betyder det: to vellykkede hentninger med en time imellem og ingen fejl ind imellem. Samme kørsel handler
   derefter efter de almindelige regler.
4. **Ingen genoptagelse,** hvis kontoens drawdown er på eller over 10 % (samme kontrol som `sim-resume`), eller hvis
   kontoen allerede er genoptaget automatisk 2 gange inden for 24 timer. Så venter pausen på et menneske, og der
   skrives ingen flere prøver.
5. **Uændret:** en banekonto, der har stået på pause i 24 timer, stoppes stadig (ændring 11 punkt 5); vagten melder
   stadig en pause over et døgn; et menneske kan stadig genoptage når som helst med `sim-resume`. Ingen gate,
   tærskel, holdout, evalueringskriterium eller registreret afgørelse ændres. Konti er simulerede og er aldrig bevis.

## Ændring 17c (2026-10-22): margin-meddelelsernes mønter læses af faste titelregler (metode m17c) — før kode

**Beslutning:** Claude under brugerens mandat (datadrevet forbedring af datadækningen; ingen gate, tærskel eller
periode ændres). Brugerens arbejdspakke 2026-10-22 bad om nye hypoteser fra eksisterende data uden holdout-lækage.

1. **Fejlen.** Ændring 17's mønter kommer fra `news.coins`: tickers i parentes, XXXUSDT/USDC/FDUSD-par og tickers
   mellem "Futures Will Launch" og "Perpetual". Binance' margin-meddelelser skriver mønterne bart ("Cross Margin
   Trading for FIL Enabled on Binance", "Binance Adds RAD & RARE on Isolated Margin"), så 0 af 116 margin-meddelelser
   i explore0 (0 af 61 i train3, 0 af 31 i validation3) fik en mønt. Alle 9 `margin|…|m17`-kandidater blev derfor
   UNTESTABLE med 0 begivenheder; ingen udfaldsværdi for en margin-begivenhed er nogensinde beregnet.
2. **Metode m17c, kun typen `margin`.** Observationernes gemte `coins` ændres ikke (append-only). Pipelinen læser
   titlen igen; en margin-begivenheds mønter er foreningen af `coins` og disse faste regler:
   - en liste efter `(?:Adds|Will Add) (.+?) (?:on|to) (?:Binance )?(?:Isolated|Cross)`;
   - en liste efter `Margin Trading for (.+?) (?:Enabled|Pairs)`;
   - en liste fra titlens start: `^(.+?) (?:Enabled|Now Available) on (?:Binance )?(?:Isolated |Cross )?Margin`;
   - par-baser `XXX/(USDT|BUSD|USDC|BTC|BNB|ETH|DOGE)`.
   En liste deles ved mellemrum, komma, `&`, parenteser og ordet "and"; et led tælles som mønt, hvis det er 2–12 tegn
   af A–Z/0–9 med mindst ét bogstav og ikke står på stoplisten (fiat og stablecoins: USD, USDT, BUSD, USDC, TUSD,
   PAX, USDP, FDUSD, DAI, EUR, GBP, AUD, TRY, BRL, RUB, NGN, UAH, BIDR, IDRT, ZAR, BKRW, VAI, UST; kontekst: BNB, BTC,
   ETH; ord: NFT, API, VIP, UTC, AMA, FAQ, BSC, APY, APR, ETF, OTC, P2P, KYC, DEX, DAO, NEW, AND, ALL). På explore0
   giver det mønter i 109 af 116 meddelelser (train3 58 af 61, validation3 27 af 31; kun titler er talt).
3. **Kandidater.** `margin|<udfald>|m17c` for hvert af de 9 udfald, hvis `margin|<udfald>|m17` er screenet
   UNTESTABLE (i dag alle 9). Ingen anden kandidat genscreenes under m17c; en m17-afgørelse (PASS, FAIL, COVERED)
   screenes aldrig igen. Screening, tærskler, placebo, explore0-vinduet, Reader-grænserne, udkast, LÅS-17-låse med
   alpha_k = 0,05 · 2^−k (k = låsens nummer i filen) og målingen på train3/validation3 er uændrede; målingen af en
   m17c-lås bruger m17c-mønterne.
4. **Ikke med, og hvorfor:** afnotering (typen blander spot-, margin-, staking- og gearede tokens' afnoteringer, og
   validation3 har kun 4 spot-afnoteringer med mønter), airdrop (0 meddelelser i validation3, kan aldrig måles),
   staking (titlerne er mest kampagner; reglerne fandt mønter i under halvdelen). En ny type kræver sin egen ændring.
5. **Forbehold, nævnt før screening:** pipelinen har nu 117 kandidater (108 + 9); reglerne er skrevet efter at have
   læst explore0-, train3- og validation3-titler (kun titler og antal, ingen priser, funding eller udfald).

## Ændring 17d (2026-10-22): låsning af de to SCREEN_PASS under m17c — `margin|far_7d|m17c` og `margin|sar_1d|m17c` — før data

**Beslutning:** Claude under brugerens mandat, efter ændring 17 punkt 7 og ændring 17c. Ingen kode ændres.

1. **Screening** (explore0, hændelser `research.hypothesis_screen`, 2026-10-22; alle 9 margin-kandidater under m17c er
   screenet: 2 PASS, 7 FAIL, ingen gentaget):
   - `margin|far_7d|m17c`: perp-kursen (mod BTCUSDT) 7 døgn fra første perp-pris efter en margin-meddelelse: n 93,
     gennemsnit −7,4 %, median −8,9 %, 28 % positive, p 0,0044; 2020 −15,5 % (36), 2021 −2,3 % (57); placebo
     (t − 30 d) +0,8 %, p 0,71 (n 63). 212 af 318 begivenheder havde ingen perp-pris inden for 72 timer.
   - `margin|sar_1d|m17c`: spotkursen (mod BTCUSDT spot) 1 døgn fra første spotpris: n 287, gennemsnit −2,0 %,
     median −2,7 %, 37 % positive, p 0,0012; 2020 −1,6 % (129), 2021 −2,3 % (158); placebo −0,3 %, p 0,70 (n 198).
2. **Kendte forbehold, nævnt før målingen:** valgt blandt 117 kandidater (heraf 9 under m17c); begge bygger på de
   samme margin-meddelelser og er derfor ikke uafhængige; `far_7d` hviler mest på 2020 (2021 er svag); mønt-reglerne
   (17c) blev skrevet efter at have læst titler og antal i train3 og validation3, men ingen priser, funding eller
   udfald derfra. Et PASS her er en måling, ikke en handelsregel.
3. **Ingen 2022–2023-priser er læst** for margin-begivenheder af pipelinen eller af andre målinger.
4. **Låse** (ensidet, retning negativ; k = låsens nummer i filen, alpha_k = 0,05 · 2^−k: `far_7d` k = 2, alpha 0,0125;
   `sar_1d` k = 3, alpha 0,00625):

LÅS-17 margin|far_7d|m17c 3944d2b5500f505a82f96d57e558777750b4682c43fef139927e2f12176a0f05
LÅS-17 margin|sar_1d|m17c ec4dc33042e28d3daf520e282fb34f984ffa9c7d8f43160f22da226b26be1411

5. En papirkonto, der udnytter et PASS, kræver sin egen daterede ændring med omkostninger og stopregler.

## Ændring 11e (2026-10-22): banegennemgange køes kun, mens en baneplads er fri — før kode

**Beslutning:** Claude under brugerens mandat (datadrevet; maskinens kapacitet). Ingen kontrol, tærskel, rækkefølge
eller startregel ændres.

1. **Data** (registret, 2026-10-21 17:00 til 2026-10-22 15:00 UTC): 1108 gennemgange (job `lane_review`), ca. 12,5
   timers beregning på de adversarielle agenter, og 0 nye banekonti, fordi alle 6 pladser var optaget. Af 1390
   gennemgange i alt havde 1253 bestået, så der lå altid beståede, ikke-prøvede kandidater klar til en fri plads.
2. **Regel:** `enqueue_reviews` køer kun nye gennemgange, mens der er færre end 6 aktive banekonti (ændring 12b's
   pladser; scanner- og HL-konti tæller ikke og gennemgås ikke). Når en plads bliver fri, køes de bedste
   ugennemgåede kandidater igen, højst 6 ad gangen, som før (11c punkt 3).
3. **Uændret:** en kandidat starter kun med en bestået gennemgang (11c); kontrollerne og tærsklerne (11d, 15, 15a);
   rækkefølgen efter netto-Sharpe; en konto pr. 10 min; højst 2 pr. funktion. Gennemgange er stadig aldrig bevis.

## Ændring 19 (2026-10-22): scanner- og HL-konti springer mønter uden Binance-spotpar over, før et prøveforsøg bruges — før kode

**Beslutning:** Claude under brugerens mandat 2026-10-22 ("kør videre automatisk ... tager de bedste beslutninger").
Kun simuleret handel. Ingen gate, tærskel, holdout eller evalueringskriterium ændres; en mønt uden spotpar kan i
forvejen aldrig starte (carry kræver spot-benet, og spot-bogen kan ikke hentes).

**Data (produktionens register 2026-10-22 ca. 19:17 UTC):** de seneste 72 timer brugte scanner- og HL-kontiene 433
prøveforsøg (højst 3 pr. gennemløb, ændring 11/12b); 282 af dem (65 %) endte i `HTTPError 400` på spot-bogen og 3 i
"crossed or empty book" på spot (XMRUSDT, som Binance spot ikke handler). Kontrol samme dag: SIRENUSDT,
BROCCOLIF3BUSDT, JCTUSDT, TACUSDT, AGTUSDT og BTRUSDT giver 200 på perp-bogen og 400 ("Invalid symbol") på spot;
Binance' offentlige `exchangeInfo` (status TRADING) har 1387 spotpar, og af de mønter, scanneren flagede de seneste 24
timer (≥ 0,05 % pr. 8 t), havde kun MITOUSDT, VELODROMEUSDT og THEUSDT et spotpar. Kandidaterne sorteres efter højeste
funding, og de højeste er typisk nye perps uden spot, så de tog prøveforsøgene fra mønter længere nede. 0 scanner- og
HL-starter i 72 timer.

1. **Spotlisten:** Binance' offentlige `GET /api/v3/exchangeInfo?symbolStatus=TRADING` fra markedsdata-værten
   (`data-api.binance.vision`, samme som spot-bøgerne, ændring 11 punkt 8), hentet højst én gang i timen og kun holdt i
   hukommelsen. Mislykkes hentningen, bruges den sidst hentede liste; er ingen liste hentet endnu, springes intet over
   (som før).
2. **Start:** scanneren (`<MØNT>` = USD-M-symbolet, fx `SIRENUSDT`) og HL-kontiene (`<MØNT>USDT`) springer en mønt uden
   spotpar i listen over, før de bruger et prøveforsøg, og noterer `lane.skipped` med årsagen "intet spotpar på
   Binance (19)". Den almindelige ventetid efter et spring (12e punkt 4, en time) gælder uændret.
3. **Uændret:** rækkefølgen efter forventet funding, 3 prøveforsøg pr. gennemløb, alle krav i 12e–12i, 13, 13a og 16e,
   pladserne og stopreglerne. Aktive konti røres ikke. Banekonti (ændring 11) gælder ikke.
4. **Ærligt:** det giver flere prøveforsøg til mønter, der kan handles, ikke flere starter i sig selv; de tre spotmønter
   ovenfor blev i perioden afvist af 12f (funding ikke vedvarende), 12g (tynd bog) og 16e (afnotering).

## Ændring 11f (2026-10-22): en banekonto, der aldrig har haft en position, stoppes efter 24 timer — før kode

**Beslutning:** Claude under brugerens mandat 2026-10-22 ("fortsæt videre aggressivt, så vi kommer i mål"). Kun
simuleret handel; ingen gate, gennemgang, tærskel, holdout eller evalueringskriterium ændres. Reglen stopper konti
tidligere, den starter ingen, der ellers ikke var startet.

**Data (produktionens register 2026-10-22 ca. 19:45 UTC):** 7 banekonti er nogensinde startet. De 3, der har handlet,
fik deres første handel i den første kørsel (0,0 timer efter start). De 4 andre (carry_floor ×2, carry_hysteresis ×2)
har ingen handel efter 2,4–2,8 døgn. Alle 6 aktive konti blev startet 10-19 22:09 – 10-20 08:00 UTC, før 11b punkt 1
(startkravet "giver +1 i mindst én mønt lige nu") blev deployet 10-20 ca. 10:20 UTC; ingen af de 4 flade ville være
startet under 11b. Siden er ingen banekonto startet, fordi alle 6 pladser er optaget, og efter 11e køes ingen
gennemgange, før en plads er fri. De 4 flade frigør først pladserne 10-23 kl. 00:09, 02:09, 09:38 og 09:49 lokal tid.

1. **Stop (tilføjes 11b punkt 2):** en banekonto, der aldrig har haft en handel (ingen `sim_fills`), stoppes 24 timer
   efter start med reglen `flat` og årsagen "ingen position siden start i 24 timer (11f)". En konto, der har handlet,
   følger uændret 11b punkt 2 (3 døgn uden position).
2. **Uændret:** startkravet (11b punkt 1, 11c), gennemgangene (11d, 15), 11e, pladserne, rækkefølgen og de øvrige
   stopregler. Scanner- og HL-konti har deres egne regler (12–13) og røres ikke.
3. **Ærligt:** banekonti er aldrig bevis; reglen bruger pladserne på varianter, der handler nu.

## Ændring 11g (2026-10-22): gennemgange køes kun for funktioner med plads — før kode

**Beslutning:** Claude under brugerens mandat 2026-10-22 ("kør fuldstændig selv hele natten ... du må gøre alt for at
komme videre"). Kun simuleret handel; ingen gate, gennemgang, tærskel, holdout eller evalueringskriterium ændres.
Samme princip som 11e: en gennemgang, der ikke kan føre til en start, køes ikke.

**Data (produktionens register 2026-10-22 20:23–20:48 UTC):** efter 11f er 4 af 6 banepladser optaget: 2
`carry_filter` og 2 `carry_filter_weekly`, dvs. begge funktioner står på loftet "højst 2 pr. funktion" (12b), så
`manage` springer deres kandidater over. På de 25 minutter blev 72 gennemgange færdige; 40 (56 %, 13,2 jobminutter)
var for `carry_filter` (19) og `carry_filter_weekly` (21) — ca. 13 jobtimer pr. døgn uden mulig start, på en maskine,
der har haft hårde nedbrud. Udforskningen tilføjer ca. 45 nye kandidater i timen, så køen tømmes ikke af sig selv.

1. **Regel (tilføjes 11e):** `enqueue_reviews` springer en kandidat over, hvis dens familie og funktion allerede har
   så mange aktive banekonti, som 12b tillader (2). Når en sådan konto stopper, køes de bedste ugennemgåede
   kandidater for den funktion igen, som efter 11e.
2. **Uændret:** en kandidat starter kun med en bestået gennemgang (11c); kontrollerne og tærsklerne (11d, 15, 15a);
   rækkefølgen efter netto-Sharpe; 11b's startkrav; en konto pr. 10 min; højst 2 pr. funktion; 11e.
3. **Ærligt:** som efter 11e kan en lavere rangeret, allerede gennemgået kandidat starte, før en bedre ugennemgået
   for samme funktion er gennemgået; banekonti er aldrig bevis.

## Ændring 11h (2026-10-23): 11b's startkrav tjekkes, før ordrebøgerne læses — før kode

**Beslutning:** Claude under brugerens mandat 2026-10-22 ("kør fuldstændig selv hele natten ... du må gøre alt for at
komme videre"). Kun simuleret handel; ingen gate, gennemgang, tærskel eller startregel ændres, kun rækkefølgen af to
kontroller i en start.

**Data (produktionens register 2026-10-22 20:51–21:51 UTC):** banen prøvede 95 varianter (`carry_hysteresis` 65,
`carry_floor` 31), der alle blev sprunget over med "would hold nothing now (11b)". Hvert forsøg læste først perp- og
spot-bogen for hver mønt i kurven (ca. 2 180 bogopslag i timen, ca. 52 000 i døgnet, på kun 15 forskellige mønter)
og tjekkede derefter 11b på timedata, der i forvejen er cachet pr. mønt og time. Opslagene går over samme
netforbindelse som pm_lp-indsamleren, hvis dækning (D1 ≥ 90 %) holdouten 10-31–11-27 afhænger af.

1. **Rækkefølge:** en start tjekker først 11b punkt 1 (variantens funktion giver +1 i mindst én mønt lige nu) på
   kurvens mønter med de samme timedata som før. Holder den intet, registreres `lane.skipped` med den samme årsag
   ("would hold nothing now (11b)") og samme 24-timers genforsøg, uden at en bog er læst. Holder den noget, læses
   bøgerne og tjekkes MIN_COINS og 11b på de mønter, hvis bøger loader, præcis som før.
2. **Uændret:** hvilke varianter der kan starte, reglen om mindst 5 mønter med begge bøger, rækkefølgen, 3 forsøg pr.
   gennemløb, en konto pr. 10 min, højst 2 pr. funktion, 11e og 11g.
3. **Ærligt:** en variant, der hverken holder noget nu eller har 5 mønter med bøger, får nu 11b's 24-timers
   genforsøg i stedet for det permanente "fewer than 5"-spring; ved genforsøget gælder reglen som før.

## Ændring 11i (2026-10-23): en gennemgang bestilles kun for en kandidat, der holder noget nu — før kode

**Beslutning:** Claude under brugerens mandat ("Optimize safely ... reduces wasted CPU", 2026-10-23). Kun simuleret
handel; ingen gate, gennemgang, tærskel eller startregel ændres, kun hvornår gennemgangen (11c) bestilles.

**Data (produktionens register til 2026-10-23 16:20 lokal tid):** 3 666 gennemgange brugte 170 219 CPU-sekunder
(162 489 s de seneste 72 timer). Af 1 597 kandidater, der bestod gennemgangen efter metode 15, blev 4 startet; 510 blev
bagefter sprunget over med "would hold nothing now (11b)" (alle 510 efter gennemgangen) og 1 083 blev aldrig prøvet.
62 762 CPU-sekunder gik til beståede gennemgange, der aldrig blev til en start (250 s til de 4 startede). Alle 1 124
afviste gennemgange fejlede på placebo-tjekket (legitime afvisninger, ingen tekniske fejl; 2 timeouts).

1. **Rækkefølge:** gennemgangen bestilles af banens startgennemløb (hvert minut, med adgang til markedsdata) i stedet
   for strategiagentens gennemløb. For hver ikke-gennemgået kandidat i den sædvanlige rækkefølge, der ikke er prøvet
   (11b-genforsøg, 24 t) og hvis funktion har plads (11g), tjekkes først 11b punkt 1 med de samme timedata som i 11h
   (ingen ordrebøger). Holder den intet, registreres `lane.skipped` med samme årsag og samme 24-timers genforsøg som i
   dag. Holder den noget, bestilles dens gennemgang.
2. **Mængde:** højst så mange gennemgange i kø eller i gang som ledige banepladser (højst `REVIEW_QUEUE_MAX`), og højst
   20 11b-tjek af ikke-gennemgåede kandidater pr. gennemløb.
3. **Uændret:** en start kræver stadig en bestået gennemgang efter metode 15, 11b på kurven, 5 mønter med bøger og 11b
   på dem (11h); 3 forsøg pr. gennemløb, en konto pr. 10 min, højst 2 pr. funktion, 6 pladser, 11e og 11g; gennemgangens
   indhold (look-ahead, gift, forsinkelse, placebo) og dens data (explore0) er de samme.
4. **Ærligt:** en kandidat får nu sin gennemgang, når den holder noget, i stedet for på forhånd; en start kan derfor
   komme en gennemgang (typisk 20–45 s) senere end før. Effekten kan først måles, når en plads bliver ledig (i dag er
   6 af 6 optaget, og der køes ingen gennemgange).

## Ændring 17e (2026-10-23): placebo fremad for nynoterede mønter (metode m17e) — før kode

**Beslutning:** brugeren 2026-10-23 ("fiks 4", svar på morgenrapportens punkt 4 om placeboens blinde vinkel). Det er
en ændring af et screeningskriterium, besluttet efter at explore0-resultaterne er kendt (se
`research/studies/AUDIT_HYPOTESER_2026-10-22.md`). Målingen på uafhængige data (train3/validation3, ændring 17 punkt
7–8) bruger ingen placebo og ændres ikke.

1. **Fejlen.** Screeningens placebo flytter t 30 døgn *tilbage* (ændring 17 punkt 5). En mønt, der lige er noteret,
   har ingen kurs dengang, så placeboen får n < 15, og tjekket "placebo p > 0,05 (n >= 15)" kan aldrig bestå. 7
   SCREEN_FAIL-nøgler under m17 har placebo-n 0–2: `futures_listing|far_1d`, `futures_listing|far_7d`,
   `innovation_zone|sar_1d`, `innovation_zone|sar_7d`, `spot_listing|sar_1d`, `spot_listing|sar_7d`,
   `staking|sar_7d`. Fire fejler kun på placeboen (`futures_listing|far_7d`, `innovation_zone|sar_1d`,
   `spot_listing|sar_1d`, `spot_listing|sar_7d`); tre fejler også p ≤ 0,005 og kan ikke bestå.
2. **Metode m17e.** Samme nøgle, begivenheder, mønter (m17's), udfald, explore0-vindue, Reader-grænser og tjek som m17
   med én forskel: har placeboen med t − 30 d færre end 15 begivenheder med data, bruges t + 30 d i stedet (samme
   mønter, samme udfald, samme krav n ≥ 15 og tosidet p > 0,05). Begivenhedens vindue (højst t + 72 t + 7 d) og
   placeboens vindue overlapper ikke. Placeboen registreres med sin forskydning (`shift_days` −30 eller +30).
   Hvorfor fremad er en ærlig test: 30 døgn efter er mønten ikke længere ny. Falder nye mønter generelt i de første
   måneder (og ikke på grund af meddelelsen), viser placeboen fremad det samme fald og afviser nøglen.
3. **Kandidater.** `<type>|<udfald>|m17e` kun for m17-nøgler, der er screenet SCREEN_FAIL med placebo-n < 15 (i dag
   de 7 ovenfor). Hver screenes én gang under m17e; ingen anden nøgle genscreenes, og m17-resultaterne står.
4. **Låsning og alfa uændret.** En SCREEN_PASS under m17e kræver som alle andre en dateret LÅS-17-ændring og måles
   med alpha_k = 0,05 · 2^−k (k = låsens nummer i filen; næste lås er k = 4, alpha 0,003125). Forudbestemt nu, før
   screeningen: `futures_listing|far_7d|m17e` låses ikke, selv om den består, fordi train3-data for de samme
   futures-listninger er læst ved målingen af `futures_listing|sar_7d|m17` (ændring 17b, REJECTED).
5. **Forbehold, nævnt før screening:** pipelinen har nu 124 kandidater (108 + 9 + 7); kriteriet er valgt efter at
   have set explore0-resultaterne for netop disse nøgler. Et PASS i screeningen er udforskning og aldrig bevis.

## Ændring 17f (2026-10-23): låsning af `spot_listing|sar_1d|m17e` — før data

**Beslutning:** Claude under brugerens mandat, efter ændring 17 punkt 7 og ændring 17e. Ingen kode ændres.

1. **Screening under m17e** (explore0, hændelser `research.hypothesis_screen`, 2026-10-23; alle 7 m17e-kandidater er
   screenet: 2 PASS, 5 FAIL):
   - `spot_listing|sar_1d|m17e`: spotkursen (mod BTCUSDT spot) 1 døgn fra første spotpris efter en spot-listning: n 117,
     gennemsnit −8,6 %, median −6,9 %, p 0,0001; 2020 −7,4 % (40), 2021 −9,2 % (77); placebo (t + 30 d) +1,7 %,
     p 0,066 (n 110).
   - `innovation_zone|sar_1d|m17e`: n 34, −9,7 %, p 0,0004; placebo (t + 30 d) +3,0 %, p 0,16 (n 33). **Låses ikke:**
     train3 har 14 innovation-zone-begivenheder (kræver 15 med data) og validation3 1 (kræver 8); den kan ikke måles og
     ville kun bruge en alfaplads. Optalt fra titler og antal, ingen priser.
   - FAIL: `spot_listing|sar_7d` (placebo fremad −5,2 %, p 0,014: faldet fortsætter en måned senere),
     `futures_listing|far_7d` (placebo fremad −11,0 %, p 0,0001), `futures_listing|far_1d`, `innovation_zone|sar_7d`
     og `staking|sar_7d` (p > 0,005).
2. **Kendte forbehold, nævnt før målingen:** kriteriet (17e) er valgt efter at have set explore0-resultaterne; valgt
   blandt 124 kandidater; placeboens p 0,066 ligger tæt på grænsen 0,05; innovation-zone-mønterne er for en stor del
   også spot-listninger, så de to PASS er ikke uafhængige. `margin|sar_1d|m17c` (17d, REJECTED p 0,44) målte samme
   udfald på train3/validation3 for margin-meddelelser, hvis mønter delvis overlapper.
3. **Ingen 2022–2023-priser er læst** for spot-listning-begivenheder af pipelinen. Train3 har 29 og validation3 11
   spot-listning-begivenheder (kun titler og antal er talt).
4. **Lås** (ensidet, retning negativ; k = låsens nummer i filen = 4, alpha_k = 0,05 · 2^−4 = 0,003125):

LÅS-17 spot_listing|sar_1d|m17e 5b7a5ebe9071d00913f41c8ab4e834ec97536df1d03e0f6e984e80d9e130f298

5. En papirkonto, der udnytter et PASS, kræver sin egen daterede ændring med omkostninger og stopregler.

## Ændring 17g (2026-10-24): ny begivenhedstype `coinbase_listing` — handelsstart på Coinbase Exchange (metode m17g) — før kode

**Beslutning:** Claude under brugerens mandat (ny nøglefri datakilde, automatisk hypotesegenerering; "Kør efter det
lange prompt", 2026-10-24). Forskningskøen er tom (alle 28 katalogskabeloner har et eksperiment; alle SCREEN_PASS
under 17 er afgjort). Ingen gate, intet vindue, ingen alfa og intet holdout ændres; typen følger ændring 17's regler.

1. **Kilde (nøglefri, kun GET).** `https://api.exchange.coinbase.com/products` (alle produkter, også afnoterede) og
   samme værts `/products/<id>/candles` (dag og time). For hvert produkt med kvotevaluta USD findes den første
   handelstime: findes der dagscandles i de 300 dage før 2020-03-01, er produktet ældre og giver ingen begivenhed;
   ellers den første dag med en candle i [2020-03-01, 2024-01-01), derefter den første timecandle den dag (højst 2
   døgn frem og aldrig fra 2024-01-01). Coinbase-kurserne bruges kun til at finde tidspunktet, aldrig som udfald. Hvert
   produkt gemmes én gang som observation (detektor `coinbase/1`, metrik `cb_listing` med tidspunktet, eller `cb_none`
   med årsagen); en fejl gemmes som `cb_error`, og en ny kørsel springer det gemte over. Kørslen er en engangskommando
   (`python3 -m lab coinbase-listings`) som news-backfillen i ændring 16; højst ét kald pr. 0,25 s.
2. **Begivenhed.** Mønt = produktets basisvaluta som skrevet (fx `CGLD` matcher ikke Binance' `CELO`; sådanne mønter
   får ingen data og udelades). t = første handelstime + 1 time (timen er først kendt, når den er gået). Én begivenhed
   pr. mønt: den tidligste USD-notering; en mønt, hvis første notering lå før vinduet, giver ingen begivenhed.
3. **Kandidater.** `coinbase_listing|<udfald>|m17g` for de 9 udfald i ændring 17 og 17a (ar_1d, ar_7d, fund_7d,
   vol_3d, volume_1d, far_1d, far_7d, sar_1d, sar_7d), målt på Binance som alle andre (data.binance.vision, Reader-
   grænserne uændret). Screening kun i explore0 (2020-03..2021-12) med ændring 17 punkt 5's tjek uændret: n ≥ 15,
   p ≤ 0,005, samme fortegn i 2020 og 2021, placebo med t − 30 d (n ≥ 15, p > 0,05) og |gennemsnit| ≥ 0,46 % for
   afkast. Ingen fremad-placebo (17e gælder ikke m17g).
4. **Låsning og alfa uændret.** Et SCREEN_PASS kræver en dateret LÅS-17-ændring; næste lås er k = 5, alpha 0,0015625.
   Målingen bruger train3 (2022-01..2023-06) og validation3 (2023-07..2023-12) som ændring 17 punkt 8.
5. **Hvad der er set før denne tekst (sonderende, i scratchpad, intet i registret):** 493 USD-produkter; første
   dagscandle i [2020-03, 2021-12] for 121, heraf 96 med et Binance USDT-spotpar og 73 med en USD-M-perp i dag. Kun
   datoer og antal er talt; ingen Binance-kurs omkring en Coinbase-notering er læst, og ingen dato efter 2021 er talt.
   Upbit blev undersøgt samme nat og forkastet (4 meddelelser i explore0; `research/studies/DISCOVERY_2026-10-24.md`).
6. **Forbehold, nævnt før screening:** Coinbase' annoncering kommer typisk før handelsstarten; t måler handelsstarten,
   ikke annonceringen, så en effekt ved annonceringen er allerede i kursen. Produktlisten kan mangle produkter, Coinbase
   har fjernet helt (overlevelsesskævhed). Pipelinen har nu 133 kandidater (124 + 9). Et PASS i screeningen er
   udforskning og aldrig bevis; en papirkonto kræver sin egen daterede ændring.

### Præcisering af ændring 17g (2026-10-24, før kode): kilden er CoinMetrics' katalog, ikke Coinbase' handelsvært

`api.exchange.coinbase.com` er også Coinbase' handelsvært; sikkerhedstestens værtsliste holder handelsværter ude
(som `api.binance.com`), og den liste ændres ikke uden brugerens ja. Punkt 1 erstattes derfor: kilden er
`https://community-api.coinmetrics.io/v4/catalog-all/markets?exchange=coinbase&type=spot` (allerede tilladt vært, ét
GET), som for hvert Coinbase-marked giver tidspunktet for den første handel (`trades.min_time`), også for markeder, der
ikke længere handles. Kun markeder med kvote `usd`; mønt = `base` med store bogstaver. Første handel før 2020-03-01
giver ingen begivenhed, og første handel fra 2024-01-01 gemmes ikke. t = første handel + 1 time (punkt 2 ellers
uændret). Hvert marked gemmes én gang (`coinbase/1`, `cb_listing` eller `cb_none`). Krydstjek i scratchpad før
denne tekst: for 122 USD-produkter med første dagscandle hos Coinbase i 2020–21 giver kataloget samme dato for 116 og
én dag tidligere for 6; kataloget har 121 USD-markeder med første handel i explore0. Ingen Coinbase-vært bruges af
laboratoriet.

## Ændring 17h (2026-10-24): ny begivenhedstype `upbit_listing` — første handel på Upbits KRW-marked (metode m17h) — før kode

**Beslutning:** Claude under brugerens mandat (samme som 17g). Følger 17g og dens præcisering med disse forskelle:

1. **Kilde.** `https://community-api.coinmetrics.io/v4/catalog-all/markets?exchange=upbit&type=spot` (tilladt vært, ét
   GET); kun markeder med kvote `krw` (Upbits egne meddelelser om "KRW-marked tilføjet" er den kendte begivenhed; et
   tidligere BTC- eller USDT-marked på Upbit ændrer ikke, at KRW-tilføjelsen er begivenheden). Detektor `upbit/1`,
   samme metrikker som 17g (`cb_listing`, `cb_none`, `cb_error`). Upbits egen vært (`api.upbit.com`) er en handelsvært
   og bruges ikke.
2. **Dækningsartefakter (forudbestemt, kun metadata).** CoinMetrics' "første handel" springer på dage, hvor kataloget
   begyndte at dække mange markeder på én gang (fx 2020-09-09: 19 på OKX og 21 på Huobi; 2019-03-15: 187 på Upbit). En
   UTC-dag er en dækningsdag, når mindst 10 basisvalutaer har deres første handel den dag talt sammen over
   CoinMetrics' kataloger for `okex`, `huobi` og `kraken` (hver valutas tidligste marked pr. børs; tre GET ved samme
   kørsel). En Upbit-KRW-første-handel på en dækningsdag gemmes som `cb_none` med årsagen. Reglen fjerner også
   omdøbninger, der står som nye markeder alle steder samme dag (fx GNT → GLM 2020-12-10).
3. **Hvad der er set før denne tekst (scratchpad, kun datoer og antal):** Upbits arkiverede meddelelser 2021-10..2026
   (222 mønt-meddelelser med et KRW-marked i kataloget) har samme dato i kataloget ± 2 dage for 211; de 11 afvigere er
   genoteringer eller huller, hvor kataloget viser en senere dato. Explore0: 49 KRW-første-handler, 33 efter reglen i
   punkt 2 (16 på dækningsdage). Ingen Binance-kurs omkring en Upbit-notering er læst; train3/validation3 er ikke talt.
4. **Kandidater, tjek, lås og alfa** som 17g: `upbit_listing|<udfald>|m17h` for de 9 udfald; explore0, ændring 17
   punkt 5's tjek uændret, placebo t − 30 d; lås kræver en dateret LÅS-17-ændring (næste k = 5, alpha 0,0015625).
   Pipelinen har nu 142 kandidater (133 + 9).
5. **Forbehold, nævnt før screening:** Upbits kendte kursspring sker ved annonceringen og i den første handelstime;
   t = første handel + 1 time måler det, der kommer efter. Kataloget kan vise en for sen dato (5 % i valideringen) og
   dermed en falsk ny notering; reglen i punkt 2 er en grov heuristik og kan fjerne rigtige noteringer.

## Ændring 17i (2026-10-24): U1F — Upbit-KRW-noteringernes fald mod BTC gentages fremad — før data findes

**Beslutning:** brugeren 2026-10-24 ("Ja jeg godkender", svar på forslaget i
`research/studies/DISCOVERY_2026-10-24.md`). Kun måling; intet handles.

1. **Låst tekst:** `research/drafts/U1F_UPBIT_FREMAD.md` (git-blob 7eb45722ec1fcf1c4ac15456b0d0d4260985450e, sha256 881c17c86989b3e9c40eab34c9f5b1458b2cb13472928b0c7a76c272444b81e8), skrevet før nogen begivenhed i
   stikprøven findes (første handel ≥ 2026-10-25 00:00 UTC).
2. **Fejlrate:** egen familie-α = 0,05 med Holm over `sar_7d` og `sar_1d`, uden for alle andre budgetter. Ændring 17's
   nøgler `upbit_listing|sar_1d|m17h` og `upbit_listing|sar_7d|m17h` forbliver SCREEN_FAIL og låses ikke.
3. **Data:** CoinMetrics' katalog og Binance' månedsarkiver (begge tilladte værter) læses én gang ved målingen. Koden
   skrives, når data findes, og må ikke ændre den låste tekst. Ingen ny vært, ingen indsamler.

## Ændring 17j (2026-10-24): M1F — kursfald efter Binance' Monitoring Tag, målt fremad — før data findes

**Beslutning:** brugeren 2026-10-24 ("Lås D1", udkast D1 i `research/drafts/DISCOVERY_2026-10-24_UDKAST.md`). Kun
måling; intet handles.

1. **Låst tekst:** `research/drafts/M1F_MONITORING_FREMAD.md` (git-blob dccceba6181520d49ca16adc7e28998dac402a15, sha256 db9924c4f02a9ca7958fa30ede462d76b87fdd7b989817f86460fb19405cb48b), skrevet før nogen
   begivenhed i stikprøven findes (meddelelser med `usable_from` ≥ 2026-10-25 00:00 UTC).
2. **Fejlrate:** egen α = 0,05, uden for alle andre budgetter. Testen vender fortegn pr. meddelelse, fordi mønter i
   samme meddelelse ikke er uafhængige. Programmets fremadtests med egen α (H5F, H5X, U1F, M1F) nævnes ved hvert
   resultat.
3. **Data:** meddelelserne indsamles allerede af `news-watch`; Binance' månedsarkiver læses én gang ved målingen.
   Koden skrives, når data findes, og må ikke ændre den låste tekst. Ingen ny vært, ingen indsamler.

### Præcisering af ændring 16d og 16f (2026-10-24 kl. 13:01, før data): TradFi-perps er ikke nye kryptolistninger

Siden 2026-10-06 lancerer Binance "TradFi USDⓈ-Margined Perpetual Contracts" på aktier og ETF'er (fx 2026-10-21:
CEGUSDT, BACUSDT, IBKRUSDT, MDTUSDT; `fapi/v1/exchangeInfo` `contractType` = `TRADIFI_PERPETUAL`) med meddelelser
af formen "Binance Futures Will Launch … Perpetual". H5 (16c), som H5F og H5X gentager, handler om nye kryptomønter
(mekanismen er afdækning af airdrops og lock-ups); en aktie-perp er ikke en sådan listning.

1. **Præcisering:** et symbol, hvis `contractType` i `fapi/v1/exchangeInfo` (læst ved målingen) er
   `TRADIFI_PERPETUAL`, er ikke med i H5F's eller H5X's stikprøve og tælles som udelukket med årsagen "TradFi".
   Alt andet i de låste tekster er uændret.
2. **Før data:** begge tests har 0 indsamlede kandidater (dashboardets tæller 2026-10-24; Binance' listing-katalog har
   ingen meddelelse efter 2026-10-21 03:31 UTC, og de eneste nye USD-M-perps siden 2026-10-10 er TradFi). Ingen
   funding for nogen kandidat er læst.
3. Dashboardets tæller springer meddelelser med "TradFi" i titlen over; den endelige afgørelse er punkt 1 ved målingen.

## Ændring 20 (2026-10-24): forudregistreret regime-diagnostik af fcarrys fremadvindue — afgør intet — før data

**Beslutning:** Claude under brugerens mandat (brugerens ja til D2 2026-10-24 og ordren om al tilladt forberedende
research). D2/F3 er blokeret af ændring 8 punkt 3 og må efter punkt 4 ikke beregne signaler på noget vindue; denne
diagnostik bruger kun fremtidige data. Ingen gate, alfa, kohorte, tærskel eller bundet fil ændres.

1. **Hvornår:** én gang, når fcarrys fremadtest har afgjort (`observe`) eller er stoppet ved futilitetskigget
   (`observe_interim`), på præcis de fremaddata (filer og hashes), som den afgørende kørsel brugte.
2. **Hvad:** for hvert medlem i kohorten `fcarry:fwd202612m12` (`E_fcarry__floor_a8`, `E_fcarry__hyst_a8`) med
   dets låste parametre: de daglige nettoafkast efter familiens omkostningsmodel, opdelt efter uge (mandag 01:00 UTC til
   næste mandag 01:00 UTC) i "port åben" og "port lukket" efter D2's definition
   (`research/drafts/F3_FREGIME_TESTPLAN.md` punkt 1) for `gate_day` 0,0004 og 0,0005.
3. **Rapport:** pr. medlem og `gate_day`: antal åbne og lukkede uger, nettosum, gennemsnitligt dagligt netto og andel
   af det samlede netto i åbne uger; forskellen i gennemsnitligt dagligt netto (åben − lukket) med et 95 %-interval
   fra blok-bootstrap (5-dages blokke, 2 000 træk, seed 7).
4. **Læsning, fastlagt nu:** D2's præmis **svækkes**, hvis nettosummen i lukkede uger er ≥ 0 for begge medlemmer
   (carry betaler sig også ved gulvet); den **støttes**, hvis den er < 0 og intervallet for forskellen ligger over 0
   for mindst ét medlem. Færre end 4 åbne uger: "uafklaret". Ingen af delene ændrer fcarrys afgørelse.
5. **Pligt:** resultatet skrives i `research/families/drafts/fregime.json` (`drafting_data_access`), før F3 kan
   foreslås til godkendelse.

### Præcisering af ændring 20 (2026-10-24 kl. 13:27, før data): manglende data og porten

Ingen fremaddata findes (fcarrys vindue starter tidligst 2026-12-01); præciseringen ændrer ikke, hvad der måles.

1. **Portens input:** fundingfilerne og mønterne, som den afgørende fremadkørsel brugte (samme hashes); en mønt tæller
   med i medianen for en beslutning, hvis den har afregninger i alle 7 døgn før beslutningen. Har under halvdelen af
   kørslens mønter det, er ugens port "ukendt".
2. **Uger uden data:** en uge, hvor fremadkørslen ikke har et dagligt netto for et medlem, eller hvor porten er
   "ukendt", udelades for det medlem og tælles med årsag i rapporten.
3. **Uger på vinduets kanter:** kun hele uger (mandag 01:00 til mandag 01:00 UTC) inden for fremadvinduet tæller.
4. **Reproducerbarhed:** rapporten angiver kørslens artefakt-SHA-256, listen af fundingfiler med deres SHA-256 og
   antallet af åbne, lukkede, ukendte og udeladte uger pr. medlem og `gate_day`.

## Ændring 21 (2026-10-24): usædvanlige bevægelser på tværs af markeder — detektor `abnormal_move/1` og analyseposter — kun data, før kode

**Beslutning:** brugerens ordre 2026-10-24 kl. ca. 14:00 ("CONTINUOUS MULTI-MARKET OPPORTUNITY HUNTER … følg til punkt og
prikke"). Som ændring 16: kun data og beskrivende analyse; intet handles, ingen kandidat registreres, ingen gate,
alfa eller periode ændres.

1. **Markeder (fast liste, kontrolleret 2026-10-24 i `fapi/v1/exchangeInfo`):** krypto BTCUSDT, ETHUSDT; råvarer
   XAUUSDT (guld), XAGUSDT (sølv), XPTUSDT (platin), COPPERUSDT, CLUSDT (WTI), BZUSDT (Brent), NATGASUSDT;
   aktiefonde SPYUSDT, QQQUSDT; valuta USDBRLUSDT. Alle er **Binance USD-M-perps** (TradFi-kontrakter for alt andet end
   krypto), ikke spotguld, indeks eller interbankvaluta: posterne mærkes sådan, og mark- og indekspris gemmes, så
   forskellen ses. Andre valutapar, renter og indeks har ingen kilde på de tilladte værter med timedata og er
   BLOKERET (FRED har kun dagsdata med forsinkelse).
2. **Kilde:** `fapi.binance.com` (allerede tilladt, kun GET): `/fapi/v1/klines` (1 t, de seneste 722 timer) og
   `/fapi/v1/premiumIndex` pr. marked i hver scanning (hver time); `/fapi/v1/depth` kun for et marked med en flagget
   bevægelse.
3. **Mål pr. marked (observationer):** z_1t = seneste afsluttede times log-afkast / σ, hvor σ er standardafvigelsen af
   de 720 foregående timeafkast; z_24t = de seneste 24 timers log-afkast / (σ · √24); volumenforhold = seneste
   afsluttede times omsætning / medianen af de 720 foregående timers; dataalder = nu − seneste afsluttede times slut;
   præmie = (mark − indeks) / indeks.
4. **Flag (faste, før data):** |z_1t| ≥ 4, |z_24t| ≥ 3 eller volumenforhold ≥ 5. Under 600 gyldige timeafkast: intet
   flag ("for kort historik"). Dataalder over 2 timer: en datafejl for markedet, intet flag. De 720 timer bruges kun
   som skala for en levende tærskel; intet udfald eller signal undersøges på dem.
5. **Analysepost (`opportunity.move`, højst én pr. marked pr. 6 t):** bevægelsen; samtidige z_1t og z_24t for alle
   markeder på listen (hvem bevægede sig også); præmien; omkostning for en rundtur på 5 000 USD gået igennem bogen
   (gebyrer for TradFi-kontrakter er ikke verificeret og indgår ikke); nyheder fra news-watch (ændring 16) i de 3 timer
   før og efter bevægelsens time, hvis titel nævner markedets nøgleord; og næste skridt: kun beskrivende — en test
   kræver sin egen daterede lås, og historik fra 2025 og frem er reserveret og screenes ikke.
6. **Fremadrettet udfald (`opportunity.outcome`):** ved den første scanning mindst 24 timer efter en analysepost gemmes
   markedets log-afkast fra bevægelsens time til +24 t. Det er data til en senere, låst test; ingen kode læser dem til
   en afgørelse før en sådan lås.

### Ændring 21a (2026-10-24 kl. 14:09, før kode): analyseposten får makrokalenderen

Analyseposten (`opportunity.move`, ændring 21 punkt 5) får feltet `macro`: planlagte FOMC-beslutninger og BLS'
CPI- og beskæftigelsesudgivelser, hvis offentliggørelsestidspunkt ligger fra 3 timer før bevægelsens time til dens
slutning, læst med ændring 14's tolkere (`ingest.parse_fomc`, `ingest.parse_bls`) fra
`www.federalreserve.gov/monetarypolicy/fomccalendars.htm` og `www.bls.gov/schedule/<år>/home.htm` (begge allerede
tilladte værter, kun GET), højst én gang i døgnet pr. kørende proces. Kontrolleret 2026-10-24: 8 FOMC-møder og 24
BLS-udgivelser i 2026 tolkes (næste FOMC 2026-10-28 18:00 UTC). En fejl i hentningen skrives i feltet og stopper
intet. Kun beskrivende; intet afgøres eller handles.

### Ændring 21b (2026-10-24 kl. 14:27, før kode): makronyheder i news-watch; to nye nyhedsværter efter brugerens ja

**Beslutning:** brugeren 2026-10-24 ("Jeg siger ja", svar på forslaget om en makronyhedskilde). Kun overskrifter
(RSS, GET); ingen handelsvært, ingen nøgle, ingen betaling.

1. **Kilder (kontrolleret samme dag):** Federal Reserve pressemeddelelser
   `https://www.federalreserve.gov/feeds/press_all.xml` og BLS "Major Economic Indicators Latest Numbers"
   `https://www.bls.gov/feed/bls_latest.rss` (allerede tilladte værter); ECB pressemeddelelser
   `https://www.ecb.europa.eu/rss/press.html` og CNBC Economy `https://www.cnbc.com/id/20910258/device/rss/rss.html`
   (**nye værter** `www.ecb.europa.eu` og `www.cnbc.com`, kun GET, godkendt af brugeren 2026-10-24).
2. **Indsamling:** samme news-watch-gennemløb hvert 10. minut og samme deduplikering som ændring 16; kategorien er
   `macro` (de eksisterende krypto-RSS-kilder beholder `media`). Kun fremad (ingen bagudhentning).
3. **Brug:** ændring 21's analysepost læser alle news-watch-titler med markedets nøgleord, nu også disse. Ændring 17's
   hypotesepipeline læser kun Binance-meddelelser og påvirkes ikke.
4. **Dækningssiden** viser de fire kilder og `abnormal_move` med friskhedsgrænser efter kildernes takt: Fed 30
   døgn, BLS 14 døgn, ECB og CNBC 3 døgn; Binance-klines 3 timer.

#### Præcisering af ændring 21b (2026-10-24 kl. 14:28, før kode): kun de allerede tilladte værter i denne omgang

Ændringen af sikkerhedstestens værtsliste (`tests/test_lab_safety.py` `ALLOWED_HOSTS`) for `www.ecb.europa.eu` og
`www.cnbc.com` blev afvist af assistentmiljøets sikkerhedskontrol og er ikke foretaget. Indtil brugeren selv har
tilføjet de to værter (eller udtrykkeligt bedt om det igen), indsamles kun Fed-pressemeddelelser og BLS' seneste
nøgletal (punkt 1, allerede tilladte værter); ECB og CNBC står som BLOKERET på dækningssiden.

#### Præcisering af ændring 21 punkt 5 (2026-10-24 kl. 14:36): nyheder vælges efter udgivelsestidspunkt

"Nyheder i de 3 timer før og efter bevægelsens time" betyder kildens udgivelsestidspunkt (`published_ts`), ikke
tidspunktet, hvor news-watch gemte overskriften. Fejlen i den første version: ved første hentning af en ny kilde (Fed og
BLS 2026-10-24 14:35) gemmes dens ældre overskrifter med tidspunktet "nu" og ville i 3 timer blive vist som nyheder ved
en bevægelse. En overskrift uden udgivelsestidspunkt bruges ikke. Analyseposten før rettelsen (USDBRL 14:23) havde 0
nyheder og ændres ikke.

#### Præcisering af ændring 21b (2026-10-24 kl. 14:45, før kode): ECB og CNBC tilføjes efter brugerens udtrykkelige ordre

Brugeren gav samme dag den præcise linje til `tests/test_lab_safety.py` `ALLOWED_HOSTS` og bad assistenten skrive den
("Du skriver komandoen"). Værterne `www.ecb.europa.eu` og `www.cnbc.com` er nu tilladt (kun GET), og news-watch
indsamler ECB-pressemeddelelser og CNBC Economy som punkt 1 og 2 beskriver. BLOKERET-rækken på dækningssiden fjernes.

## Ændring 21c (2026-10-24 kl. 15:58, før kode og før nogen beregning): screening af bevægelse → fortsættelse eller tilbagevenden, krypto-perps, explore0 (metode m21c)

**Beslutning:** Claude under brugerens mandat (master follow-up 2026-10-24 kl. ca. 15:55, prioritet 3: "Momentum efter
usædvanlige bevægelser. Mean reversion efter ekstreme prisændringer"). Spørgsmålet er, om ændring 21's flag
(|z_1t| ≥ 4) bærer en retning, der kan handles. Det er udforskning, aldrig bevis; ingen gate, alfa, periode eller
kandidat i andre ændringer ændres. Beslægtede, allerede afviste fund (gentestes ikke): `daily_reversal` (dagsbarer, z 2,0;
PROTOCOL_V2), MISSION3 M2 (BTC, 5 min-likvidationskaskader: kun +4 til +7 bp brutto ved 15 min, negativt ved 1–4 t)
og tsmom_v1 (ugentlig). Denne test er anderledes: timebarer, 4σ-hændelser med detektorens egen skala, hele
krypto-perp-universet, og en realistisk indgang en time efter, at flaget kan ses.

1. **Universe (fast):** hver Binance USD-M-perp `<mønt>USDT`, hvis 1 t-klines for en måned i explore0 (2020-03..2021-12)
   ligger i lab'ens cache (`data/lab/market/klines`, hentet tidligere af banen og ændring 17; ingen ny hentning,
   læseren er `hypogen.Reader("explore0")` uden netværk, som afviser alle andre måneder og alt fra 2024-01-01).
   Undtaget: `BTCDOMUSDT` (et indeks, ikke en mønt). Kørslen registrerer fillisten med sha256.
2. **Hændelse (detektorens regel, ændring 21 punkt 3–4):** time h på mønt c, hvor r_h = ln(C_h / C_{h−1}) (begge barer
   til stede) og σ = standardafvigelsen af timeafkastene i de 720 foregående timer (kun afkast mellem to tilstedeværende,
   på hinanden følgende barer; mindst 600), og |r_h / σ| ≥ 4. Retning s = fortegnet af r_h. Højst én hændelse pr. mønt
   pr. 24 t (den første; senere i de 24 t springes over).
3. **Beslutningstidspunkt og udfald:** flaget ses tidligst ved bar h's slutning (scanneren kører hvert time); indgang
   P0 = lukkekursen for bar h+1 (én times forsinkelse, konservativt). `cont_4h`: y = s · ln(C_{h+5} / P0);
   `cont_24h`: y = s · ln(C_{h+25} / P0). Positiv y = fortsættelse, negativ = tilbagevenden. Rå perp-afkast (ikke mod
   BTC). Mangler en af kurserne: udelukket med årsag. Hele udfaldsvinduet skal ligge i explore0.
4. **Afhængighed:** hændelser samme UTC-døgn er ikke uafhængige (hele markedet bevæger sig sammen). Testen bruges derfor
   på klynger: klyngeværdien er gennemsnittet af y over døgnets hændelser; n er antal klynger.
5. **Test og SCREEN_PASS (som ændring 17 punkt 5, på klynger):** mindst 15 klynger, ellers UNTESTABLE. Tosidet
   fortegnsskift-test af klyngeværdierne (20 000 træk, seed 7). SCREEN_PASS kræver alle: p ≤ 0,005; samme fortegn i
   2020 og 2021 (hver mindst 5 klynger, delt efter klyngens døgn); placebo (samme mønt og retning s, h − 30 døgn, samme
   regler og klynger) med p > 0,05 og mindst 15 klynger; og |gennemsnit af klyngeværdier| ≥ 0,46 % (F1's rundtur).
   Ellers SCREEN_FAIL med årsag.
6. **Kandidater (2):** `abnormal_move|cont_4h|m21c` og `abnormal_move|cont_24h|m21c`. Ingen andre tærskler, horisonter,
   undergrupper eller volumenflag testes under m21c; opdelinger (op/ned, BTC+ETH/øvrige, efter år) må vises
   beskrivende i rapporten og mærkes "ikke testet".
7. **Registrering:** resultatet (begge kandidater, også negative) committes som
   `research/studies/MOVESCREEN_m21c.json` og `.md` med fillistens sha256, hændelseslistens sha256 og kodens commit. En
   nøgle med et resultat screenes aldrig igen under m21c.
8. **Efter en SCREEN_PASS:** intet automatisk. En måling i train3 og validation3 kræver en dateret LÅS-linje i denne fil
   i ændring 17's α_k-række (næste α ≈ 0,0016, jf. effektvæggen) og egen kode. Gyldigheden gælder kun krypto-perps;
   TradFi-perps har al historik i den reserverede periode (fra 2025) og er UNTESTABLE historisk.
9. **Aldrig:** ordrer, papirkonti, familier, alfa, holdout 2024, data fra 2025 og frem, netværk, `pm_lp`.

## Ændring 21d (2026-10-24 kl. 15:58, før begivenheden og før kode): FOMC 2026-10-28 som beskrivende integrationstest af kæden bevægelse + nyheder + kalender

**Beslutning:** Claude under brugerens mandat (master follow-up, prioritet 2). Kun en test af datakæden; én
makrobegivenhed er aldrig bevis for en strategi. Detektor, tærskler og nyhedskilder ændres ikke.

1. **Begivenhed:** FOMC-erklæringen 2026-10-28. Datoen er kontrolleret 2026-10-24 kl. 15:58 på
   `www.federalreserve.gov/monetarypolicy/fomccalendars.htm` ("27-28" oktober). Klokkeslættet 14:00 ET = 18:00 UTC (USA
   har sommertid til 1. november) er Feds faste konvention, kodet i `ingest.parse_fomc`, og står ikke på siden;
   rapporten angiver Fed-pressemeddelelsens egen `published_ts` som den faktiske tid. T = 2026-10-28 18:00:00 UTC.
2. **Markeder:** ændring 21's 12 Binance USD-M-perps (beskrevet som kontrakterne, ikke de underliggende markeder).
3. **Faste vinduer (låst nu):** referencekurs = lukkekursen for timebaren 17:00–18:00 UTC. Afkast til lukkekursen for
   barerne, der slutter T+1 t, T+4 t og T+24 t. Begivenhedstimens (18:00–19:00) z_1t og volumenforhold efter ændring 21
   punkt 3. Desuden scannerens egne observationer og analyseposter (`opportunity.move`) fra T til T+3 t, og deres
   `opportunity.outcome`, når de findes.
4. **Nyhedskæde:** Fed-pressemeddelelser med `published_ts` i [T − 30 min, T + 2 t]: udgivelsestid, gemt tid (news-watch
   hvert 10. min) og forsinkelsen mellem dem. CNBC Economy- og ECB-poster i samme vindue: antal og første forsinkelse.
   En nyhed kobles kun til en bevægelse, hvis dens `published_ts` lå før bevægelsens times slutning. Dubletter (samme
   titel fra flere kilder) tælles.
5. **Kalenderkæde:** om analyseposterne fra T til T+3 t har FOMC-erklæringen i `macro`-feltet.
6. **Manglende data og fejl:** et marked uden kurs i et vindue står som "mangler" med årsag, aldrig udfyldt. Scannerens
   fejl- og "for kort historik"-observationer, news-watch-fejl og forsinkede scanninger (tid fra timens slutning til
   observationen) i [T − 1 t, T + 25 t] rapporteres. Et flag i begivenhedstimen uden samtidig nyhed tælles som "flag
   uden forklaring", ikke som falsk alarm; en falsk alarm er et flag på en datafejl (dataalder, tom bog, prishop uden
   volumen).
7. **Rapport:** `research/studies/FOMC_2026-10-28.md` og `.json`, lavet af et script efter 2026-10-29 19:00 UTC. Det
   læser registret (skrivebeskyttet) og Binance-klines (`fapi.binance.com`, allerede tilladt) og gemmer svarenes sha256.
   Ingen vinduer ændres eller tilføjes bagefter; noget ekstra mærkes "efterfølgende, ikke låst".
8. **Ikke:** ingen konklusion om en strategi, ingen ændring af tærskler på grundlag af denne ene begivenhed, ingen
   ordrer. Testen blokerer ikke andet arbejde.

### Præcisering af ændring 21 punkt 2 (2026-10-24 kl. 16:04, før kode): scanningen ligger 2 minutter efter timeskiftet

**Data (registret, skrivebeskyttet):** `discovery-scanner` kører hver 3600 s regnet fra lab'ens start. Efter dagens
deploys lå scanningerne kl. ca. HH:50 lokal tid. Den sidst afsluttede time blev altså først set 50–51 minutter efter, at
den sluttede (scanningen 14:50:33 så timen, der sluttede 14:00; målt med ændring 21d's script). En bevægelse i FOMC-timen
(18:00–19:00 UTC) ville først blive analyseret ca. kl. 19:50 UTC.

1. `discovery-scanner` kører én gang ved start som før, og derefter ved hvert timeskift + 120 s (HH:02:00 UTC). Ved en
   fejl prøves igen efter højst 60 s som før.
2. Intet andet ændres: samme detektorer, tærskler, dedup og data. En ekstra scanning lige efter en genstart var der også
   før.
3. Målet er tid fra timens slutning til observationen (ændring 21d punkt 6). Det bør være under 3 minutter.

## Ændring 21e (2026-10-24 kl. 16:05, før kode): hver analysepost får en begrundet vurdering (triage)

**Beslutning:** Claude under brugerens mandat (master follow-up, prioritet 1: "Hvis der ikke findes en interessant
mulighed, skal systemet registrere en begrundet afvisning i stedet for at producere en kunstig kandidat"). Kun
beskrivende: intet handles, ingen kandidat oprettes, ingen tærskel i ændring 21 ændres.

1. **Felt `triage` i `opportunity.move`** med faste regler, fastlagt før nogen post er vurderet:
   - `tails_720h`: antal timer blandt de 720 foregående med |afkast / σ| ≥ 4 (hvor almindelige 4σ-timer er i markedet);
   - `explanations` (alle, der gælder): `volume_only` (kun volumenflag og |z_1t| < 2: ingen prisbevægelse);
     `illiquid` (bogen fejlede eller rundturen for 5 000 USD > 0,5 %); `routine_tail` (`tails_720h` ≥ 3);
     `macro_release` (ændring 21a's felt har en udgivelse); `news` (mindst én nyhed udgivet før bevægelsestimens
     slutning); `unexplained` (ingen af de to sidste);
   - `verdict` (den første, der gælder): `REJECT_NOT_DIRECTIONAL` (volume_only); `REJECT_ILLIQUID` (illiquid);
     `REJECT_TESTED` (krypto: m21c, ændring 21c, gav SCREEN_FAIL for 4σ-flag i explore0 ved 4 og 24 t);
     `FORWARD_ONLY` (TradFi: historikken ligger i den reserverede periode; udfaldet efter 24 t indsamles, og en test
     kræver en dateret lås);
   - `reason` og `next` som tekst.
2. **Visning:** feedet viser dommen og forklaringerne ud for "BEVÆGELSE".
3. **Ændres senere kun ved en ny dateret ændring.** En ny screening, der består, kan ændre en `REJECT_TESTED`-regel.

#### Præcisering af ændring 21e punkt 1 (2026-10-24 kl. 16:06, før kode): `REJECT_TESTED` kun for det, m21c testede

m21c testede kun |z_1t| ≥ 4. En kryptopost uden z_1t-flag (kun z_24t, eller volumen med en prisbevægelse) får derfor
`NOT_SCREENED` med `next` = "ikke screenet; en screening kræver en dateret ændring", ikke `REJECT_TESTED`.
Rækkefølgen er: REJECT_NOT_DIRECTIONAL, REJECT_ILLIQUID, REJECT_TESTED, NOT_SCREENED (krypto), FORWARD_ONLY (TradFi).

## Ændring 21f (2026-10-24 kl. 17:40, før kode og før nogen beregning): tre nye hypotesefamilier screenes i explore0 (metode m21f)

**Beslutning:** Claude under brugerens mandat (master follow-up "AGGRESSIVE DISCOVERY, FAST REJECTION" 2026-10-24,
punkt 3: mindst tre reelt forskellige familier). Udforskning, aldrig bevis. Ingen gate, alfa, periode, kandidat eller
lås i andre ændringer ændres. Den efterfølgende 4σ-fald-idé (`research/drafts/DROP4S_BESLUTNINGSOPLAEG.md`) er
**ikke** blandt dem; den venter på brugerens beslutning.

**Fælles regler (som ændring 21c, medmindre andet står):** data kun via `hypogen.Reader("explore0")` (2020-03..2021-12,
kun cache, intet netværk; læseren afviser alt andet og alt fra 2024-01-01). Universe: ændring 21c punkt 1 (de cachede
USD-M `<mønt>USDT`, undtagen BTCDOMUSDT). σ = standardafvigelsen af de 720 foregående timeafkast (mindst 600 afkast
mellem på hinanden følgende barer). Indgang P0 = lukkekursen for bar h+1, udgang = lukkekursen for bar h+25 (24 t).
Klynger pr. UTC-døgn for hændelsestimen h; tosidet fortegnsskift-test på klyngeværdierne (20 000 træk, seed 7).
**SCREEN_PASS** kræver alle: mindst 15 klynger (ellers UNTESTABLE); p ≤ 0,005; samme fortegn i 2020 og 2021 (hver
mindst 5 klynger); placebo (samme mønt/hændelse og retning, h − 30 døgn) med p > 0,05 og mindst 15 klynger;
|gennemsnit af klyngeværdier| ≥ familiens omkostningskrav. Ellers SCREEN_FAIL med årsag.
**Omkostningskrav (strengere end ændring 17's 0,46 %, fordi alt-perps koster mere;
`research/studies/ANALYSE_2026-10-24.md` afsnit 10 målte en rundtur på ~55–65 bp ved 5 000 USD):** én alt-perp
0,65 %; lang/kort-kurv mod BTC 1,11 % (0,65 % + 0,46 %).

1. **Familie A — tværgående (`btc_lead|alt_excess_24h|m21f`).** Hændelse: time h, hvor BTCUSDT har |r_h/σ| ≥ 3; højst
   én pr. 24 t. s = fortegnet af BTC's r_h. For hver anden mønt c med kurs ved bar h+1 og h+25:
   x_c = ln(C_c,h+25 / C_c,h+1) − ln(B_h+25 / B_h+1) (BTC = B). Hændelsens y = s · gennemsnittet af x_c (ligevægtet).
   Spørgsmål: fortsætter alt-mønternes merafkast over BTC i BTC's retning (langsom spredning) eller vender det? Krav
   1,11 %. Mønternes samtidige merafkast i time h vises kun beskrivende.
2. **Familie B — volatilitetsregime (`squeeze_break|cont_24h|m21f`).** Hændelse på mønt c: kompression
   σ_72 / σ ≤ 0,5 (σ_72 = standardafvigelsen af de 72 timeafkast før h, mindst 65) og udbrud |r_h/σ| ≥ 2,5; højst én pr.
   mønt pr. 24 t. y = s · ln(C_h+25 / C_h+1). Spørgsmål: fortsætter et udbrud efter en stille periode? Krav 0,65 %.
   Beslægtet med m21c (fortsættelse efter bevægelser, SCREEN_FAIL). Det nye er betingelsen på det forudgående regime og
   den lavere tærskel; det er klassificeret med information fra før h.
3. **Familie C — katalysator (`catalyst_move|cont_24h|m21f`).** Hændelse: m21c's hændelser (|r_h/σ| ≥ 4, højst én pr.
   mønt pr. 24 t), hvor en Binance-meddelelse i registret (news/1, kilde www.binance.com, alle kategorier) nævner
   mønten (`coins`) med udgivelsestid (`published_ts`) i [h − 24 t, h + 1 t]. Nyheden er altså offentlig før timens
   slutning og før indgangen ved h+2 t (også med bagudhentningens 1 t-forsinkelse, ændring 16 punkt 3).
   y = s · ln(C_h+25 / C_h+1). Spørgsmål: fortsætter bevægelser med en dateret katalysator (underreaktion på nyheder)?
   Krav 0,65 %. Hændelser uden katalysator er næsten m21c's (allerede testet) og testes ikke; deres antal vises.
4. **Registrering:** alle tre resultater, også negative, committes som `research/studies/DISCOVERY_m21f.json` og `.md`
   med fillistens og hændelseslisternes sha256 og kodens commit. En nøgle screenes aldrig igen under m21f.
5. **Efter en SCREEN_PASS:** intet automatisk. En måling kræver en dateret LÅS i ændring 17's α_k-række (næste
   α = 0,05 · 2⁻⁵ = 0,0015625, verificeret i `hypogen.measure_locked`) og brugerens beslutning, fordi rækken næsten er
   brugt op.
6. **Aldrig:** ordrer, papirkonti, familier efter ændring 8, alfa, train3, validation3, holdout 2024, data fra 2025 og
   frem, netværk, `pm_lp`.

## Ændring 21g (2026-10-24 kl. 17:43, før kode): TradFi-perps uden for det underliggende markeds åbningstid; gebyrskemaet er verificeret

**Data (Binance' egne meddelelser, hentet 2026-10-24 via `www.binance.com/bapi/composite/v1/public/cms/article/detail/query`,
allerede tilladt vært, kun GET):**
- `f69c05eb…` (2026-09-15, råvarer XAU, XAG, XPT, XPD, COPPER, CL, BZ, NATGAS): normal handelstid søndag 18:00 ET til fredag
  17:00 ET (indeks fra tredjepartskurser); weekend og helligdage fredag 17:00 ET til søndag 18:00 ET i
  "Orderbook EWMA mode".
- `533eb2f3…` (2026-09-18, USDBRLUSDT, FX): normal tid søndag 17:00 ET til fredag 17:00 ET; weekend fredag 17:00 ET til
  søndag 17:00 ET i "Orderbook EWMA mode".
- `53bfc176…` (2026-05-13, aktiebaserede, SPY og QQQ): "Orderbook EWMA mode" under den daglige vedligeholdelse, i
  weekender og på helligdage. Meddelelsen angiver ingen klokkeslæt.
- `a4c3f195…` (2026-03-27): TradFi-perps fra 2026-03-31 02:00 UTC "until further notice": maker 0,0000 %, taker
  0,0400 % for almindelige brugere (VIP 0–1). Det er en kampagne, ikke standardsatsen.

I EWMA-tilstand følger perpens indeks dens egen ordrebog, ikke det underliggende marked. En bevægelse eller et
volumenflag dér er en bevægelse i perpen, ikke i guld, olie, SPY eller USD/BRL. Dagens flag (USDBRL kl. 14:23 og SPY
kl. 17:02, lørdag) lå i denne tilstand.

1. **Triage (ændring 21e) får forklaringen `off_hours`** for en TradFi-post, hvis bevægelsestimens start ligger i et
   EWMA-vindue efter meddelelserne: råvarer fredag 17:00 ET til søndag 18:00 ET; FX fredag 17:00 ET til søndag 17:00 ET;
   aktier lørdag og søndag (UTC-døgn), fordi meddelelsen ikke giver klokkeslæt. Helligdage og den daglige
   vedligeholdelse kendes ikke og markeres ikke. ET følger amerikansk sommertid. Dommen er fortsat `FORWARD_ONLY`;
   `reason` nævner "uden for det underliggende markeds åbningstid".
2. **Bogens omkostning** i analyseposten får feltet `fees` med kampagnesatsen for TradFi (taker 0,04 % pr. side, maker 0)
   og kilden. For krypto bruges det eksisterende ord "not included". Rundturen i bogen ændres ikke.
3. Ingen tærskel, ingen dedup og intet andet ændres.

## Ændring 21h (2026-10-24 kl. 18:03, før kode og før nogen beregning): rettelse af omkostningstal, omkostningsmåling, weekend-TradFi-plan og en fundinghypotese (metode m21h)

**Beslutning:** Claude under brugerens mandat (master mission "FUNDING EDGE, COST INTELLIGENCE & CONTINUOUS DISCOVERY"
2026-10-24 ca. kl. 18:00). Kun data, beskrivende målinger og én screening i explore0. Ingen gate, alfa, periode eller
lås ændres. 4σ-faldshypotesen indgår ikke; den venter på brugerens beslutning.

1. **Rettelse (fejl i min tekst i ændring 21f og i `research/drafts/DROP4S_BESLUTNINGSOPLAEG.md`).** "~55–65 bp rundtur"
   i `research/studies/ANALYSE_2026-10-24.md` afsnit 10 er en hel rundtur af et **par med 4 ben** (spot og perp, ind og
   ud) inklusive banens gebyr på 10 bp pr. ben. Det er ikke én alt-perp ved 5 000 USD. Målt pr. ben (samme afsnit):
   tynde mønter (HOT, MITO, EPIC) ved 4 600–5 100 $: bog 17,6 bp i median (perp), op til 30 bp; likvide 30v3-mønter ved
   160–500 $: 0,85–1,67 bp. 21f's krav (0,65 % og 1,11 %) står som låst; alle tre 21f-kandidater fejlede på p eller var
   UNTESTABLE, så ingen dom ændres. Oplægget rettes med en dateret note.
2. **Omkostningsmåling nu (beskrivende, ét øjebliksbillede).** Én gennemgang af alle handlede Binance USD-M-perps
   (`fapi/v1/exchangeInfo`: contractType PERPETUAL eller TRADIFI_PERPETUAL, status TRADING, quote USDT): `fapi/v1/depth`
   (limit 100) pr. symbol i højst 4 kald pr. sekund og én `fapi/v1/ticker/24hr`. Allerede tilladt vært, kun GET. Pr.
   symbol: halvt spread, bogens rundtur for 5 000 USD (købs- og salgs-VWAP, samme `moves.walk`), 24 t-omsætning og
   klasse (krypto/TradFi). Rapport: rundtur i omsætningsdeciler, OLS af log(rundtur) mod log(omsætning), andelen over
   0,46 % og 0,65 % inklusive et gebyr på 2 × 5 bp (krypto: labbens eksisterende modelantagelse, ikke verificeret fra en
   kilde) eller 2 × 4 bp (TradFi, verificeret i 21g). Forbehold, der står i rapporten: ét tidspunkt (lørdag aften,
   roligt marked), ingen historik og ingen krisesituation.
3. **Bogmåling hver time for de 12 markeder (fremadrettet).** Scanneren gemmer i hver scanning observationen
   `book_rt` (rundtur for 5 000 USD gennem bogen) og `spread` for alle markeder på ændring 21's liste, ikke kun for
   flaggede. Det er 12 ekstra `depth`-kald pr. time. Formål: omkostning ved flag mod normalt (prioritet B) og i
   weekend mod normal åbningstid for TradFi (prioritet C). Kun data.
4. **Weekend-TradFi, kun fremad (data fra 2026-10-24 og frem; historikken er reserveret og læses ikke).** Sessioner
   efter ændring 21g. Pr. marked og session: |timeafkast|/σ, volumenforhold, `book_rt` og `spread`. Weekendgabet:
   g = ln(kursen ved genåbning / kursen ved lukning fredag 17:00 ET) og reaktionen fra genåbning til + 24 t. Kun
   beskrivende. Klynger er weekender (én klynge pr. weekend, alle markeder sammen), så der kommer ca. 4 klynger pr.
   måned. Ingen test før mindst 12 weekender, og kun efter en ny dateret lås, der fastlægger signal og regel før
   resultatet ses.
5. **Fundinghypotese F1 (`funding_crowd|squeeze_24h|m21h`), screenes i explore0.** Spørgsmål: tilfører funding
   information om en 4σ-bevægelses efterforløb ud over prisbevægelsen selv?
   - Hændelser: m21c's (|r_h/σ| ≥ 4, højst én pr. mønt pr. 24 t) på mønter med fundingfiler i cachen.
   - Signal, kendt før bevægelsen: f = den seneste afregnede funding (`last_funding_rate`) med `calc_time` ≤ h (timens
     start), højst 12 t gammel (ellers udelukket: "no recent funding"). Flokken c = +1 (lange betaler), hvis
     f > 0,0001 (over den neutrale rente 0,01 %/8 t); c = −1, hvis f < 0; ellers neutral (udelukket med årsag).
   - Regel: med flokken (s = c) → position d = s (fortsættelse); mod flokken (s ≠ c, presning/likvidation) →
     d = −s (tilbagevenden).
   - Udfald (netto for funding): v = d · ln(C_h+25 / C_h+1) − d · Σ f_k over afregninger i (h + 1 t, h + 25 t].
     Fordi reglen skifter retning efter funding, ophæves en fælles drift (fx tyrmarkedets) delvist. v måler fundingens
     merinformation.
   - Test som 21c punkt 5: døgnklynger, tosidet fortegnsskift (20 000, seed 7), samme fortegn i 2020 og 2021, placebo
     h − 30 d med samme d (og funding i placeboens vindue), |gennemsnit| ≥ 0,46 % (ændring 17's krav; punkt 1 viser, at
     det svarer til en tynd mønts rundtur ved 5 000 USD med et gebyr på 5 bp). Mindst 15 klynger, ellers UNTESTABLE.
   - Beskrivende, ikke testet: v for "med" og "mod" hver for sig; andelen af de 5 største døgn og de 5 største mønter.
   - **Kendt overlap:** fald mod en lang flok er en stor del af 4σ-faldsmønstret. En SCREEN_PASS her er ikke en afgørelse
     af den hypotese, som venter på brugeren. Beslægtet, afvist: `funding_contrarian` (ubetinget funding-hale, uden
     prisbevægelse; PROTOCOL_V2). Det nye er samspillet mellem funding og en 4σ-bevægelse.
   - Registrering: `research/studies/FUNDING_m21h.json` og `.md` med fil- og hændelses-sha256. Nøglen screenes aldrig
     igen. En SCREEN_PASS kræver brugerens beslutning før en lås (rækken har 0,003125 tilbage).
6. **Aldrig:** ordrer, papirkonti, familier, alfa, train3, validation3, holdout 2024, data fra 2025 og frem i
   screeningen, `pm_lp`.

## Ændring 21i (2026-10-24 kl. 18:32, før kode og før nogen beregning): gebyrer verificeret, fremadrettet omkostningskrav, spot–perp lead/lag (metode m21i) og beskrevne omkostningsregimer

**Beslutning:** Claude under brugerens mandat (master follow-up "SPOT–PERP LEAD/LAG, COST-AWARE DISCOVERY & REGIME
ANALYSIS" 2026-10-24 ca. kl. 18:30). Ingen gate, alfa, periode eller lås ændres; ingen afsluttet screening ændres.
4σ-faldshypotesen indgår ikke.

1. **Gebyrer (verificeret i Binances meddelelser via den tilladte vært, kun GET):**
   - `360037673592` (2019-12-18): USDⓈ-M-futures fra 2019-12-20 08:00 UTC, almindelige brugere maker 0,020 % og taker
     0,040 %. Blandt registrets Binance-meddelelser fra 2020–2021 med "Fee" i titlen er der ingen senere ændring for
     USDT-perps (kun BUSD-kampagner og forsikringsgebyrer). Det gælder explore0.
   - 2026: TradFi-meddelelsen `a4c3f195…` giver almindelige brugere taker 0,0400 % som "20 % rabat" i forhold til
     standardsatsen for USDT. Standard-taker er altså 0,0500 %. Labbens model på 5 bp pr. side er konservativ for
     explore0 og passer til i dag.
2. **Omkostningskrav for screeninger fra og med denne ændring (fremadrettet, aldrig strengere end nødvendigt og
   aldrig lempeligere end ændring 17):** pr. hændelse
   c_i = max(0,46 %, 2 · (2 · 0,040 % + RT_est(V_i))),
   hvor V_i er møntens gennemsnitlige 24 t-omsætning i quote over de 30 døgn før hændelsen (point-in-time fra klines'
   quote volume). RT_est(V) = exp(0,8999) · V^(−0,4540) er bogens rundtur for 5 000 USD fra
   `research/studies/COSTS_2026-10-24.md` (krypto, n 516).
   - **Begrænsning (står i hver rapport):** sammenhængen er målt i 2026 på ét tidspunkt og overføres til 2020–21. Det
     er et ESTIMAT, ikke en observeret historisk omkostning. Faktoren 2 er sikkerhedsmarginen. 0,46 %-gulvet betyder, at
     kravet aldrig bliver lempeligere end ændring 17's.
   - Kravet for en kandidat: |gennemsnit af klyngeværdier| ≥ gennemsnittet af klyngernes c (klyngens c er gennemsnittet
     af dens c_i). Regimespecifikke krav indføres ikke; der er ingen historiske bogdata (punkt 5).
3. **S1 `spot_lead|perp_1h|m21i` (lead/lag i samme mønt).**
   - Data: mønter med både USD-M-perp og Binance-spot `<mønt>USDT` 1 t-klines i explore0 (cachen, `Reader("explore0")`
     kinds `klines` og `spot`). Barerne har samme åbningstid; kun timer, hvor begge findes.
   - x_t = r_spot,t − r_perp,t (log-afkast samme time); σ_x = standardafvigelsen af x over de 720 foregående timer (mindst
     600). Hændelse: |x_t / σ_x| ≥ 3. Alle timer, der opfylder det, tæller (udfaldsvinduerne overlapper ikke).
   - Kendt ved bar t's lukning (begge lukkekurser). y = sign(x_t) · r_perp,t+1 (perpens afkast i næste time; positiv =
     perpen indhenter spot).
   - **Forbehold:** indgang ved bar t's lukning er en nul-forsinkelse. Med timebarer kan en realistisk forsinkelse ikke
     måles, så en SCREEN_PASS er kun information og kræver minutdata før enhver tale om handel. Det står i rapporten.
4. **S2 `perp_led|move_24h|m21i` (hvem førte bevægelsen?).**
   - Hændelser: m21c's 4σ-perp-bevægelser (højst én pr. mønt pr. 24 t) med en spotbar i samme time og fundingfiler.
     e = s · (r_perp,h − r_spot,h): perp-ført, hvis e > 0 (basis udvidet i bevægelsens retning, gearet spekulation);
     ellers spot-ført.
   - Regel: perp-ført → gå imod (d = −s); spot-ført → følg (d = s). v = d · ln(C_h+25 / C_h+1) − d · funding afregnet i
     (h + 1 t, h + 25 t] (som m21h; mindst 2 afregninger, ellers udelukket).
   - Forskel fra m21h: betingelsen er den samtidige spot–perp-forskel i bevægelsestimen, ikke funding før bevægelsen.
     Den er korreleret (funding følger basis); begge registreres.
5. **Test for S1 og S2:** som 21c punkt 5 (døgnklynger, tosidet fortegnsskift 20 000 / seed 7, p ≤ 0,005, samme
   fortegn i 2020 og 2021, placebo samme mønt t − 30 d med samme fortegn/d, mindst 15 klynger) med kravet fra punkt 2
   i stedet for den faste sats. Registrering: `research/studies/SPOTPERP_m21i.json` og `.md`. Nøglerne screenes aldrig
   igen. En SCREEN_PASS kræver brugerens beslutning før en lås.
6. **Omkostningsregimer, kun beskrivende (ESTIMAT, ingen test, ingen dom):** der findes ingen historiske bogdata.
   Spreadet estimeres med Abdi & Ranaldo (2017, RFS 30(12)) fra perpens 1 t-klines i explore0:
   s² = max(0, 4 · (c_t − η_t) · (c_t − η_t+1)), hvor c er log-lukkekursen og η gennemsnittet af log-high og log-low;
   døgnets estimat er √ af gennemsnittet over døgnets 23 par. Rapporten viser estimatet (a) på døgn med en m21c-hændelse
   i mønten mod samme mønt 30 døgn før og (b) efter terciler af døgnets realiserede volatilitet inden for mønten. Det er
   kun til at beskrive, om ekstreme bevægelser ledsages af dårligere eksekverbarhed. Fremadrettet giver ændring 21h
   punkt 3 observerede bogdata; en rapport tidligst efter 7 døgn.
7. **Funding (prioritet D):** ingen ny fundinghypotese i denne ændring. "Funding før et volatilitetsskift" har ingen
   handelsretning, og "funding forklarer omkostninger" har ingen historiske omkostningsdata. `funding_crowd|squeeze`
   screenes ikke igen.
8. **Aldrig:** ordrer, papirkonti, familier, alfa, train3, validation3, holdout 2024, data fra 2025 og frem i
   screeningen, `pm_lp`.

## Ændring 21j (2026-10-24 kl. 18:47, før kode og før nogen beregning): nye informationskilder i explore0 — makroudgivelser og opmærksomhed (metode m21j); lead/lag med forsinkelse afgøres uden beregning

**Beslutning:** Claude under brugerens mandat (master follow-up 2 "FIND REAL EDGES" 2026-10-24 ca. kl. 18:45). Kun
explore0. Ingen gate, alfa, periode eller lås ændres. 4σ-faldshypotesen indgår ikke.

**Datakortlægning (kontrolleret i cachen, ingen udfald set):** open interest og long/short (`metrics`, 30 mønter), DVOL,
MVRV, FRED, aggTrades og historisk bogdybde dækker kun train3 og validation3. De kan **ikke screenes** (UNTESTABLE i
explore0; brug kræver en LÅS). To kilder dækker explore0:
- makrokalenderen `ingest/calendar/{fomc,bls}-{2020,2021}.json` (ændring 14; planlagte udgivelser kendt på forhånd);
- Wikipedia-sidevisninger `ingest/pageviews/*.json` med `available_ts` = D + 2 døgn 00:00 UTC (ændring 14 punkt 3).
Kun rækker inden for explore0 (2020-03-01 – 2021-12-31) bruges; senere rækker i filerne kasseres ved indlæsning.

1. **J1 `macro_release|post_drift_24h|m21j` (makro-efterdrift).**
   - Mekanisme: underreaktion på offentlig makroinformation (post-announcement drift).
   - Hændelser: planlagte FOMC-erklæringer, CPI og Employment Situation med `ts` i explore0. Bar H er timebaren, der
     indeholder `ts`.
   - Retning pr. mønt (BTCUSDT og ETHUSDT perps): s = fortegnet af ln(C_H / C_H−1). y_mønt = s · ln(C_H+25 / C_H+1);
     hændelsens y = gennemsnittet for BTC og ETH. Indgang en time efter reaktionsbaren.
   - Klynge = UTC-døgn. **Placebo:** samme klokkeslæt 7 døgn før (14 døgn, hvis det døgn har en kalenderbegivenhed).
     Det fanger mønstre for ugedag og tid på dagen, som ændring 14a's H1 viste.
   - Beskrivende, ikke testet: gennemsnit pr. udgivelsestype.
2. **J2 `attention_shock|cont_7d|m21j` (opmærksomhedschok).**
   - Mekanisme: opmærksomhed giver midlertidigt købspres, som vender (Da, Engelberg & Gao 2011, J. Finance), eller
     langsom spredning af information, som fortsætter. Tosidet.
   - Artikler → perp: Bitcoin → BTC, Ethereum → ETH, Dogecoin → DOGE, Litecoin → LTC, Polkadot_(cryptocurrency) → DOT,
     Cardano_(blockchain_platform) → ADA, Chainlink_(blockchain) → LINK. Ikke brugt: Binance, Cryptocurrency, Ripple_Labs
     (ikke én mønt) og Avalanche (ingen data i explore0).
   - Uger: ISO-uger fra mandag 00:00 UTC. V_w = summen af ugens 7 dages visninger (alle 7 til stede). Chok:
     V_w / gennemsnittet af de 8 foregående uger ≥ 2 (alle 8 til stede og i explore0).
   - Kendt: søndagens `available_ts` = tirsdag 00:00 UTC. Indgang P0 = lukkekursen for baren, der åbner tirsdag 00:00;
     udgang 168 t senere. s = fortegnet af møntens afkast i uge w (mandag 00:00 → næste mandag 00:00).
     y = s · ln(P1 / P0) (positiv = fortsættelse).
   - Klynge = chokets ISO-uge (alle mønter samme uge er én klynge). **Placebo:** samme mønt 4 uger før med samme s.
3. **Test (J1 og J2):** som 21c punkt 5 (tosidet fortegnsskift 20 000 / seed 7, p ≤ 0,005, samme fortegn i 2020 og
   2021 med mindst 5 klynger hver, placebo-p > 0,05 med mindst 15 klynger, mindst 15 klynger) og
   omkostningskravet fra 21i punkt 2 (pr. hændelse, point-in-time-omsætning; for J1 BTC og ETH, som giver gulvet
   0,46 %). Registrering: `research/studies/NEWINFO_m21j.json` og `.md`. Nøglerne screenes aldrig igen. En SCREEN_PASS
   kræver brugerens beslutning før en lås.
4. **Lead/lag med forsinkelse (brugerens punkt 2) afgøres uden beregning:** S1 (21i) målte spots informationsforspring
   med nul forsinkelse til +0,108 % pr. time mod et krav på 0,465 %. Information om næste time aftager med forsinkelsen,
   så S1 med enhver realistisk forsinkelse ligger under det samme krav: **REJECTED af omkostningsgrænsen**, ingen ny
   screening. Minutdata til at måle forsinkelsen findes ikke i cachen. Banens hentevej må først hente igen fra
   2026-11-14 (ændring 10b): BLOCKED til da, og ikke nødvendig, fordi den øvre grænse allerede ligger under kravet.
5. **Regimeopdelinger af de afsluttede screeninger:** gennemføres ikke. Hver regimeopdeling af explore0-resultater er
   efterfølgende valgt og kan ikke screenes ærligt igen i explore0. Den kan kun føre til en LÅS i α-rækken (0,003125
   tilbage), og den informationsværdi står ikke mål med risikoen for et falsk fund. Fremadrettede regimedata indsamles
   (21h punkt 3).
6. **Aldrig:** ordrer, papirkonti, familier, alfa, train3, validation3, holdout 2024, data fra 2025 og frem, `pm_lp`.

## Ændring 21k (2026-10-24 kl. 19:26, før kode og før nogen beregning): omkostningsrapport (R1), taker-flow afvist som genbrug (R4), beslutningsanalyse for gulvet (R2) og plan for minutreaktion (R3)

**Beslutning:** Claude under brugerens mandat (master follow-up 4 "COST REALITY CHECK" 2026-10-24 ca. kl. 19:25). Ingen
gate, alfa, periode, tærskel, lås eller afsluttet dom ændres. Intet deployes uden brugerens udtrykkelige ok.

1. **R1 — omkostningsrapport (beskrivende, ingen dom).** Programmet `lab/costreport.py` læser registret
   skrivebeskyttet: scannerens `book_rt` og `spread` (ændring 21h punkt 3) og samme scannings `z_1h`-observation for
   markedet.
   - Grupper: klasse (krypto / TradFi) × session (`off_hours` sand/falsk, ændring 21g) og hvert marked for sig.
   - Pr. gruppe: antal observationer, antal uden bog (fejl/tynd), median, 25 %- og 75 %-fraktil, maks, samt et 95 %
     bootstrap-interval for medianen (2 000 træk, seed 7) over **døgn-klynger** (timer samme døgn er ikke uafhængige).
   - Mod 21i-modellen: RT_est(V) med V = 24 · `quote_volume_1h` / `volume_ratio` (24 × medianen af timeomsætningen over
     720 t). Det er median- og ikke gennemsnitsbaseret som i 21i, og det står i rapporten. Forholdet målt / model pr. marked.
   - Omkostning og bevægelse: medianen af `book_rt` i timer med |z_1h| ≥ 2 eller et flag mod øvrige timer, pr. marked.
   - Mærkning: FORELØBIG indtil 7 døgn (2026-10-31 18:21) og mindst 2 weekender. Ingen tærskel ændres på grundlag af
     rapporten; en ændring kræver en ny dateret tekst og brugerens godkendelse.
2. **R4 — taker-købsandel betinget af handelsaktivitet: AFVIST SOM GENBRUG, ingen beregning.** Mekanismen
   ("aggressivt købsflow forudsiger efterfølgende afkast", Chordia & Subrahmanyam 2004) er allerede afvist to gange
   omkring timehorisonten: MISSION3 M1 (BTC, minut-orderflow, nul brutto efter én minuts forsinkelse) og katalogets
   `taker_pressure` (dagligt, tværsnit, REJECTED i train3). En time-version med handelsaktivitet som betingelse er den
   samme mekanisme med en ekstra parameter, ikke en ny mekanisme. Den kan heller ikke på forhånd adskilles fra
   almindeligt momentum og markedsuro: taker-andelen er stærkt korreleret med samtidige afkast, og 4σ-betingelser blev
   afvist i m21c, m21h og m21i. Gennemsnitlig handelsstørrelse som proxy for detailhandel er tæt på ændring 14a H3
   (REJECTED) og `smart_vs_crowd` (REJECTED).
3. **R2 — omkostningsgulvet:** analysen står i `research/drafts/GULV_BESLUTNING_2026-10-24.md`. Ingen regel ændres.
4. **R3 — minutreaktion på makroudgivelser:** planen står i `research/drafts/R3_MINUTMAKRO_PLAN.md`. Ingen data hentes
   før 2026-11-14 00:00 UTC (ændring 10b). Planen bliver en hypotese først ved en senere dateret ændring før data.

## Ændring 21l (2026-10-24 kl. 19:29, før kode): R1 gøres beslutningsklar; et eventuelt C-krav fastlægges på forhånd; discovery i explore0 lukkes

**Beslutning:** Claude under brugerens mandat (master follow-up 5 "COST MODEL STRESS TEST" 2026-10-24 ca. kl. 19:28).
Ingen tærskel, gulv, gate, alfa eller lås ændres. Intet deployes uden brugerens ja.

1. **R1-rapporten (`lab/costreport.py`) udvides, før data er set ud over de 2 første scanninger:**
   - **Enheder:** alle omkostninger vises også i basispoint (bp = 10⁻⁴ af prisen); `book_rt` og `spread` gemmes som
     brøk.
   - **Kombination uden dobbelttælling:** `book_rt` = (købs-VWAP − salgs-VWAP) / mid for 5 000 USD hver vej. Det
     indeholder spread og slippage, men ikke gebyrer. Total rundtur = `book_rt` + 2 × taker-gebyr (krypto 5 bp i 2026,
     TradFi 4 bp kampagne). `spread` vises separat og lægges aldrig oven i `book_rt`. Funding er ikke en ordreomkostning.
   - **Størrelse:** 5 000 USD hver vej er samme størrelse som 21i-modellens RT_est (fra snapshot 2026-10-24).
   - **Manglende bog som censur:** en bog, der er for tynd til 5 000 USD (`book_rt` mangler), er dyr. Rapporten viser
     medianen (a) uden de manglende og (b) med de manglende sat til +∞ (en øvre grænse).
   - **Tidspunkt:** målingen tages kl. HH:02, lige efter en afsluttet time, altså det tidspunkt, hvor scanneren ville
     handle. Den måler ikke midt i en bevægelse. Det står i rapporten.
   - **Tilstrækkelighed pr. marked (fastlagt nu):** en konklusion kræver mindst 7 døgn, mindst 100 timeobservationer
     og mindst 10 "bevægelsestimer" (|z_1h| ≥ 2 eller et flag). Ellers står markedet som "for få data".
   - **Usikkerhed:** bootstrap over døgn-klynger, som ændring 21k.
2. **Hvis brugeren senere vælger mulighed C, er kravet fastlagt nu, før data:** for markeder med 24 t-omsætning
   ≥ 100 mio. USD (24 × medianen af timeomsætningen over 720 t ved hændelsen) er kravet
   2 × (2 × taker-gebyr + 95 %-fraktilen af den observerede `book_rt` i bevægelsestimer for markedet over mindst
   7 døgn), dog aldrig under 2 × (2 × taker-gebyr). For explore0-screeninger (2020–21) findes ingen observeret bog,
   så C kan kun bruges dér med en udtrykkeligt markeret antagelse om, at 2026-fraktilen gælder for 2020–21. Det er
   ikke en regel. Den kræver brugerens ja i en senere dateret ændring og gælder kun fremtidige screeninger.
3. **Discovery i explore0 lukkes.** Resterende felter og kombinationer i explore0 (antal handler, taker-køb,
   high/low-spænd, forholdet mellem spot- og perp-volumen, kalender, sidevisninger) giver kun mekanismer, der allerede
   er afprøvet: orderflow (M1, `taker_pressure`), gearing og spekulation (`leverage_cycle`, `oi_growth`, funding),
   likviditet og volatilitet (`xs_illiquidity`, `xs_high_volume`, `xs_low_volatility`, `vol_managed_long`), kalender
   (`hour_of_day`, `day_of_week`, `turn_of_month`, J1), opmærksomhed (14a H2, J2), momentum og reversal (`xs_momentum`,
   `daily_reversal`, tsmom, m21c) og spot–perp (m21i). Ingen ny screening, før en ny datakilde eller mekanisme findes.

## Ændring 21m (2026-10-24 kl. 19:40, før kode og før beregningen): brugerens beslutninger — 4σ-fald (1a, så drop), mulighed C og deploy

**Beslutning:** brugeren svarede "JA" 2026-10-24 ca. kl. 19:36 og valgte i opfølgningsspørgsmålet: "Deploy
forskningskoden", "4σ-fald: drop (mulighed 3)", "4σ-fald: leave-one-day-out først (1a)" og "R2 mulighed C (lavere krav
for likvide)".

1. **4σ-fald: først 1a, derefter DROPPED.** Leave-one-day-out køres én gang, præcis som beskrevet i
   `research/drafts/DROP4S_BESLUTNINGSOPLAEG.md` (tilføjelsen kl. 18:15, "Hvad den ville måle"): fald-hændelserne efter
   m21c's regel og y = ln(C_h+25 / C_h+1), (a) klyngegennemsnit pr. UTC-døgn med og uden hvert døgn (min, median, maks),
   (b) uden de k største døgn efter antal hændelser, k = 1…10, (c) det samme med ISO-uge-klynger, (d) andelen af døgn
   med positivt gennemsnit, (e) det ubetingede 24 t-afkast (alle mønter, hver 6. time) som sammenligning.
   - Kun explore0 og kun cachen; beskrivende, ingen dom, intet alfa, ingen LÅS, ingen train3 eller validation3.
   - Bagefter registreres hypotesen `abnormal_move_drop|rebound_24h|posthoc` som **DROPPED efter brugerens beslutning**,
     uanset resultatet (brugeren valgte begge). Resultatet gemmes som `research/studies/DROP4S_LOO_m21c.json` og `.md`,
     så det kan findes i research-memory. En senere test kræver en ny mekanisme og en ny dateret ændring.
2. **Mulighed C indføres for fremtidige screeninger** med formlen fra ændring 21l punkt 2, uændret:
   - For et marked med 24 t-omsætning ≥ 100 mio. USD ved hændelsen og en R1-måling med konklusionen "enough data"
     (21l punkt 1): c = max(2 · 2 · gebyr, 2 · (2 · gebyr + q95)), hvor q95 er 95 %-fraktilen af den observerede
     `book_rt` i bevægelsestimer for markedet.
   - Ellers gælder 21i (B) uændret.
   - Indtil R1 har "enough data" for et marked (tidligst 2026-10-31), er C uvirksom. For explore0 bygger C på
     antagelsen, at 2026-fraktilen gælder for 2020–21, og hver rapport skal skrive det.
   - Ingen afsluttet dom ændres. Ingen afsluttet screening køres igen under C.
3. **Deploy:** den testede kode (fuld suite grøn) deployes med de tilladte kommandoer. Kontrol: DEPLOY OK, pm_lp-collectoren
   urørt, scannerens næste kørsel kl. HH:02.

## Ændring 21n (2026-10-24 kl. 20:20, før kode og før nogen beregning): flagrapport, R1-port pr. marked med C side om side

**Beslutning:** Claude under brugerens mandat (master follow-up 6 "MAXIMUM RESEARCH THROUGHPUT WITHOUT GATE WEAKENING"
2026-10-24 ca. kl. 20:18). Kun beskrivende rapporter. Ingen tærskel, gate, alfa, lås eller scanneradfærd ændres, og
intet deployes uden brugerens ja.

1. **Flagrapport (`lab/flagreport.py`, læser registret skrivebeskyttet):**
   - Én række pr. (marked, bevægelsestime `open_s`, metrik); gentagne scanninger af samme time (genstart, deploy)
     tælles som dubletter, ikke som nye flag.
   - Pr. marked og metrik: antal flag og antal observerede timer, flagrate, og fordelingen på weekend/hverdag (UTC) og
     `off_hours` (ændring 21g).
   - **Uafhængige hændelser:** flag i samme bevægelsestime på flere markeder er én hændelse (klynge = `open_s`).
   - **Datakvalitet:** for hvert flag: dataalder, og om den gemte værdi kan genberegnes fra observationens egne felter
     (volumenforhold = `quote_volume_1h` / median).
   - **Efterfølgende omkostning:** for flag med en bogmåling (fra 2026-10-24 18:21): `book_rt` i flag-scanningen mod
     markedets median.
   - **Konklusion:** NO_DECISION, indtil der er mindst 14 døgn og 2 weekender. Først da må en dateret ændring foreslå
     en ny volumentærskel, med begrundelse, forventet effekt, risiko for falske positive og en fremadrettet validering.
     Den gennemføres ikke uden brugerens godkendelse.
2. **R1-porten pr. marked (`lab/costreport.py`):**
   - "enough data" kræver nu også mindst 2 weekender for **det enkelte marked**, med observationer i weekendtimer
     (lørdag eller søndag UTC). Ændring 21l punkt 1's tre krav står uændret.
   - For hvert marked med "enough data" vises side om side: 21i-kravet (B) ved markedets aktuelle V, C-kravet efter
     21l punkt 2 med q95 og dets bootstrap-interval over døgn, og om V ≥ 100 mio. USD.
   - C aktiveres aldrig automatisk. Brugeren afgør pr. marked på grundlag af tabellen. Ingen afsluttet screening
     regnes om.

## Ændring 21o (2026-10-24 kl. 20:32, før kode): flagrapportens identitet og median, R1-beslutningstabel, forslag til målelog og præcisering af R3-udkastet

**Beslutning:** Claude under brugerens mandat (master follow-up 7 "REPRODUCIBLE MEASUREMENTS" 2026-10-24 ca. kl. 20:31).
Ingen scannerændring, tærskel, gate, alfa eller lås. Intet deployes.

1. **Flagrapporten (`lab/flagreport.py`):**
   - Identiteten af en markedstime er (marked, `open_s`, metrik), hvor `open_s` er den afsluttede bars åbningstid i UTC
     epoch-sekunder, som scanneren selv gemmer. Den er uafhængig af scanningstid, genstart og deploy.
   - Mangler `open_s` (ingen z_1h-observation i scanningen), bruges ikke en erstatning. Flaget tælles under
     datakvalitet som "uden markedstime" og indgår ikke i rater eller hændelser.
   - Nævneren er alle observerede markedstimer fra scannerens z_1h-observationer, også timer uden flag.
   - Medianen bag volumenforholdet: rapporten viser den **afledte** median = `quote_volume_1h` / `volume_ratio` pr. flag.
     Det er algebraisk den gemte værdi, **ikke** en uafhængig genberegning; den kræver de 720 timers klines, som ikke
     hentes. Det står i rapporten.
2. **R1-beslutningstabel (`lab/costreport.py`):** pr. marked hvert krav for sig (døgn, observationer,
   bevægelsestimer, weekender) med opfyldt/ikke, antal døgnklynger, samlet rundtur med gebyrer (median og
   bootstrap-interval), manglende og censurerede, B og C (kun ved opfyldte krav), hvilke input der er observeret
   (`book_rt`, `spread`, `volume_ratio`, `quote_volume_1h`) og hvilke der er antaget (gebyrsats, RT_est-sammenhængen,
   overførsel til 2020–21), og en anbefaling: "NO_DECISION", indtil alle krav er opfyldt. Derefter "kan forelægges
   brugeren", aldrig en automatisk aktivering.
3. **Målelog (forslag, ikke implementeret i denne runde):** `research/drafts/MAALELOG_FORSLAG.md`. En implementering
   ændrer scannerens gemte felter og kræver en senere dateret ændring og brugerens ja til deploy.
4. **R3-udkastet præciseres (indhold uændret):** minutbar k åbner ved T + k min. Signal fra bar 0 (kendt ved T + 1 min).
   Indgang ved lukkekursen for bar 1 (tid T + 2 min). Udgang ved lukkekursen for bar 61 (T + 62 min). Holdetiden er
   altså 60 min.

## Ændring 21p (2026-10-24 kl. 21:22, før kode): målelog i scannerens observationer (brugerens ja)

**Beslutning:** brugeren svarede "Ja til deploy osv" 2026-10-24 ca. kl. 21:20 på listen, hvor implementering af
målelogen (`research/drafts/MAALELOG_FORSLAG.md`) stod. Ingen tærskel, gate, alfa eller lås ændres; detektorens
beregning og flag er uændrede.

1. `abnormal_move`'s fælles `payload` (z_1h, z_24h, volumenforhold, præmie) får fra næste deploy disse felter:
   - `window`: første og sidste bar-åbningstid, antal afkast og antal barer;
   - `median_qvol_720`: medianen bag volumenforholdet;
   - `sigma_basis`: antal, Σr og Σr² for σ;
   - `quality`: dataalder og manglende barer i vinduet;
   - `flags`: metrik, værdi, tærskel og regel for hvert flag;
   - `version`: detektor og git-commit, læst én gang pr. proces;
   - `klines_sha256`: sha256 af det rå klines-svar.
2. Ingen rådata gemmes (ca. 0,4 KB pr. observation). Eksisterende felter bevares uændret.
3. Flagrapporten bruger `median_qvol_720`, når feltet findes, og den afledte median ellers.

#### Præcisering af ændring 21 punkt 3 (2026-10-24 kl. 21:31): σ bygger på 719 afkast i den levende scanner

Målelogen (21p) viste ved første deploy: scanneren henter 722 timebarer. 721 er lukkede, og de giver 720 afkast.
σ beregnes på afkastene før den seneste time, dvs. **719** (`window.n_returns`). Volumenmedianen bruger 720 barer.
Teksten "de 720 foregående timeafkast" er altså én for højt for den levende detektor. Screeningerne m21c–m21j brugte
præcis 720 i cachen. Forskellen er ét afkast ud af 720 og ændrer ingen dom. Detektoren ændres ikke; tallet står nu i
hver observation.

## Ændring 21q (2026-10-24 kl. 21:32, før kode): fremadrettet indsamling af on-chain-børsstrømme (point-in-time fra start)

**Beslutning:** brugeren svarede "JA" 2026-10-24 ca. kl. 21:31 på forslaget om en daglig fremadrettet indsamler
(`research/drafts/ONCHAIN_KILDEAUDIT_2026-10-24.md`, konklusion punkt 2). Kun data, aldrig en beslutning. Ingen
historisk forespørgsel: hver kørsel henter kun de seneste 3 døgn.

1. **Kilde:** `community-api.coinmetrics.io/v4/timeseries/asset-metrics` (tilladt vært, kun GET, CC BY-NC 4.0,
   ikke-kommerciel forskning med kreditering), `assets=btc,eth`, `metrics=FlowInExNtv,FlowOutExNtv,SplyExNtv`,
   `frequency=1d`, `start_time` = i dag − 3 døgn. Kontrolleret i kataloget samme dag: alle seks serier er gratis
   (seneste dato 2026-10-23).
2. **Point-in-time:** første gang en (aktiv, metrik, dato) ses, gemmes værdien som observationen `onchain/1` /
   `flow_first` med `fetched_ts` og `usable_from` = `fetched_ts`. Ses en anden værdi senere, gemmes den som
   `flow_revision` med den gamle og den nye værdi. Revisioner måles altså uden at overskrive noget.
3. **Takt:** fra news-watch' gennemløb, højst én gang hver 6. time (3 forespørgsler pr. døgn × 1 kald). En fejl
   gemmes som `onchain_error` og stopper intet andet.
4. **Brug:** ingen før en senere dateret ændring med en hypotese (mekanisme: udbudschok via børsindstrømning). Data
   fra før 2026-10-24 bruges aldrig fra denne kilde (revideret, ikke point-in-time). Dækningssiden viser kilden.

## Ændring 21r (2026-10-24 kl. 21:47, før kode): målingernes integritet — én observation pr. markedstime i R1, on-chain-pollinglog og as-of-rekonstruktion

**Beslutning:** Claude under brugerens mandat (master follow-up 8 "MEASUREMENT INTEGRITY" 2026-10-24 ca. kl. 21:45).
Integritetsrettelser, ingen ny hypotese. Ingen tærskel, gate, alfa, omkostningskrav eller scanneradfærd ændres. Intet
deployes uden brugerens ja.

1. **Fejl i R1 (fundet i dag, skrivebeskyttet optælling):** `costreport` talte en række pr. scanning. Genstarter og
   deploys scannede samme markedstime igen: 96 `book_rt`-rækker, men kun 48 forskellige markedstimer (36 dubleret).
   Kravet "≥ 100 timeobservationer" (21l) betyder forskellige markedstimer.
   - **Rettelse:** R1 bruger én observation pr. (marked, `open_s`): den tidligste scanning af timen (normalt kl. HH:02,
     den planlagte). Antallet af kasserede dubletter vises.
   - Det samme gælder `costrule.observed_q95`. Ingen afgørelse er truffet på de dublerede tal.
2. **On-chain (21q):**
   - Hver indsamling skriver nu observationen `onchain_poll` med hentetid, antal rækker, seneste dato pr. serie,
     antal nye værdier og antal revisioner. Et tomt svar står som 0 rækker, ikke som en værdi. Huller og leverandørens
     forsinkelse kan derfor ses bagefter.
   - Funktionen `onchain.asof(db, t)` rekonstruerer præcis det, systemet kendte på tidspunkt t: første værdier med
     `usable_from` ≤ t, med revisioner hentet ≤ t lagt ovenpå.
   - Ifølge 21q punkt 4 bruges kun datoer fra og med 2026-10-24 (de 18 værdier fra 21.–23. oktober er pilotdata, hentet
     efter at de kunne være revideret).
3. **Målelogens integritet (kontrolleret i dag, ingen kodeændring nødvendig):**
   - Alle registrets tabeller er append-only (triggere afviser UPDATE og DELETE) og hash-kædede, og scannerens
     observationer skrives i én transaktion (en afbrudt scanning efterlader ingen halve rækker).
   - Identiteten er (marked, `open_s`, metrik). Hver flagværdi bærer sin tærskel og regel, og hver observation sin
     commit, så en senere kode- eller tærskelændring ikke kan ændre tolkningen af ældre målinger lydløst.
   - Uafhængig reproduktion kræver de rå klines, som ikke gemmes; kun `klines_sha256`. Uden ny forespørgsel kan man kun
     kontrollere den interne konsistens: z = r/σ fra `sigma_basis`, volumenforhold = q/median og flag = værdi mod
     tærskel.

## Ændring 21s (2026-10-24 kl. 22:06, før kode): papirregnskabet — gebyret ved en positionsvending fordeles forholdsmæssigt

**Beslutning:** Claude under brugerens mandat (master mission "COMPLETE, SELF-CRITICAL MARKET RESEARCH AND
EXECUTION-REALITY SYSTEM" 2026-10-24 ca. kl. 22:00). En regnskabsrettelse. Ingen gate, tærskel, risikoregel, alfa
eller kasse ændres.

1. **Fund (uafhængig orakeltest, `tests/test_lab_paper_oracle.py`):** over tilfældige, seedede fill-sekvenser stemmer
   `PaperEngine` med en simpel gennemsnitsprismodel for kasse, positioner, basis, urealiseret P&L og equity-
   invarianten (equity = kapital + lukket P&L − gebyrer + urealiseret). P&L pr. handel afviger dog ved en
   **positionsvending** (et fill, der lukker en position og åbner den modsatte): hele fill'ets gebyr lægges på den
   lukkede handel, og den nye handel starter uden sin andel. Summen er korrekt; fordelingen mellem de to handler er
   forkert.
2. **Betydning:** `trades` bruges af risikobremsen for tabende handler (`risk.after_trade_closed`). I produktionen er
   der **1 vending ud af 1 972 fills**: `FWD_E_xs_momentum_p2` DOTUSDT (ts 1792368017). Den lukkede handel bar
   0,579 USD for meget gebyr, og den nye handel 0,579 USD for lidt. Kasse, equity og nattens afstemning er
   uberørte.
3. **Rettelse:** gebyret for et vendende fill fordeles efter mængde: lukket mængde / fill-mængde til den lukkede
   handel, resten til den nye. Ledgeren beregnes altid fra fills, så den historiske handel vises fremover med den
   rigtige fordeling. Risikobeslutninger, der allerede er truffet og registreret, ændres ikke (de står i loggen).

## Ændring 21t (2026-10-24 kl. 22:07, før kode): banernes pris-/basis-post kontrolleres uafhængigt

**Beslutning:** Claude under brugerens mandat (master mission 2026-10-24). Kun en kontrol; ingen omkostning, gate eller
P&L ændres.

1. **Fund (skrivebeskyttet, i dag):** `lane.decomposition`'s `price_basis` er en rest-post (net − funding + gebyrer +
   betalt afstand). Uafhængigt beregnet som pris-P&L målt fra midtprisen,
   Σ(−fortegn · mid · mængde) + (equity − kasse) fra samme `sim_equity`-række,
   er den **identisk** for alle 10 bane- og scannerkonti (samlet afvigelse 0,0000). Der er 0 fills uden midtpris,
   0 fills bedre end midtprisen og 0 fills efter seneste mark.
2. **Kontrol fremover:** `decomposition` viser også `price_basis_independent`, `price_basis_gap` og antallet af fills,
   der er bedre end midtprisen eller ligger efter seneste mark. Tre ting kan bryde identiteten:
   - et maker-fill bedre end midtprisen (`abs()` ville regne en forbedring som omkostning);
   - en fill uden midtpris;
   - en mark, der er ældre end det seneste fill.
   En afvigelse over 0,01 USD vises som en advarsel i rapporten og fejler den natlige `reportcheck`.

## Ændring 21u (2026-10-24 kl. 22:23, før kode): tidsrækkefølge og sporbarhed i den natlige rapportkontrol

**Beslutning:** Claude under brugerens mandat (master prompt 2 "MARKET INTELLIGENCE CENTER" 2026-10-24 ca. kl. 22:20).
Kun en kontrol i `reportcheck` (rapport-fejl), aldrig i `PaperEngine.reconcile` (som kan sætte lab'en i FAIL_CLOSED).

1. **Tidsstemplernes betydning (fra koden):**
   - `sim_orders.ts` = indsendelse, `int(now)`.
   - Et taker-fill har `ts` = ordrens `ts` (samme `int(now)`).
   - Et maker-fill har `ts` = handelsprintets tid, som er ≥ ordrens.
   - `book_ts` = lokal hentetid for bogen (float), læst lige før ordren. `risk.entry_allowed` afviser en bog, der er
     ældre end `data_max_age_s` (60 s som standard).
   - `sim_equity.ts` = mark-tid. Et fill efter den seneste mark er lovligt; den næste mark tager det med. "fill ≤ mark"
     er derfor **ikke** en invariant.
2. **Invarianter pr. bane- og scannerkonto i døgnrapporten:**
   - (a) ordre-ts ≤ fill-ts;
   - (b) taker: fill-ts = ordre-ts;
   - (c) floor(`book_ts`) ≤ fill-ts (fill-ts er afkortet til hele sekunder);
   - (d) fill-ts − `book_ts` ≤ 60 s + 1 s afrunding;
   - (e) hver ordre har `signal_ref`;
   - (f) hvert fill har en ordre (dækket af `reconcile`, gentaget her som tal).
   Et brud giver en rapport-fejl med antal og første eksempel, ikke FAIL_CLOSED.
3. **Status i dag (skrivebeskyttet):** 0 brud på (a)–(e) blandt 1 972 fills og 1 776 ordrer i hele produktionen.

## Ændring 21v (2026-10-24 kl. 22:44, før kode og før nogen indsamling): nutidig kapacitetskurve fra dybe ordrebøger

**Beslutning:** brugerens udtrykkelige ja 2026-10-24 ca. kl. 22:43 ("Kapacitetskurve", svar på spørgsmål efter "JA").
Kun offentlige GET-kald til værter, der allerede bruges (`fapi.binance.com`, `data-api.binance.vision`). Ingen ordre,
ingen gate, ingen omkostningsregel og intet papirfill ændres. Forslaget i
`research/drafts/SYSTEMKORT_OG_RISICI_2026-10-24.md` punkt 5 gennemføres med de præciseringer, der står herunder.

1. **Univers:** 
   - de 12 markeder i `moves.WATCH`;
   - hvert perp-symbol med et papirfill de seneste 14 døgn;
   - for hvert spot-ben (`<SYM>.SPOT`) med et fill de seneste 14 døgn: spot-bogen.
   I dag giver det ca. 40 bøger.
2. **Hyppighed:** højst én gang pr. 23 timer, kørt fra `news-watch` på samme måde som on-chain-collectoren (21q). Højst
   4 kald i sekundet.
3. **Bog:**
   - USD-M `fapi/v1/depth?limit=500` (vægt 10);
   - spot `api/v3/depth?limit=500` (vægt 25).
   I alt under 1 000 vægt i døgnet.
4. **Måling pr. bog og størrelse S ∈ {500, 2 000, 5 000, 20 000, 50 000} USD:**
   - køb- og salgs-VWAP gennem bogen;
   - rundtur = (VWAP_køb − VWAP_salg) / mid, uden gebyrer;
   - spread;
   - dybde i USD på hver side;
   - `fits_20_levels`: om de første 20 niveauer alene kan fylde S. Papirmotoren ser kun 20 niveauer
     (`paper_runner.fetch_book`), så en størrelse, der ikke kan fyldes i 20 niveauer, kan papirmotoren ikke handle.
   Kan bogens 500 niveauer ikke fylde S, gemmes værdien som tom og mærkes `censored` (bogen er for tynd). Der gættes
   ikke på en værdi.
5. **Lagring:** én observation pr. (bog, S): detektor `capacity/1`, metric `rt_<S>`. Den er append-only som alle
   observationer.
6. **Sprog og brug:** kurven er **nutidig** og bliver aldrig til en historisk kurve.
   - Kapacitetsstatus pr. papirkonto forbliver `UNTESTABLE_CAPACITY`, så længe kontoen ikke har en dokumenteret
     nettofordel. Kurven vises ved siden af som data.
   - Der beregnes ingen break-even-størrelse, før en fordel findes og er låst.
   - Kurven ændrer ikke omkostningsreglerne B og C (21i/21l). Ønskes det, kræver det en ny ændring og brugerens ja.

## Ændring 21w (2026-10-24 kl. 22:44, før kode): monitor for aftagende fordel med vedtagne tærskler

**Beslutning:** brugerens udtrykkelige ja 2026-10-24 ca. kl. 22:43 ("Tærskler i monitoren"). Monitoren er
**skrivebeskyttet og uden automatisk handling**:
- den skifter ingen livscyklus-tilstand;
- den stopper ingen konto og sætter intet i FAIL_CLOSED;
- den viser en status pr. papirkonto på dashboardet (`/api/research`).
En handling på baggrund af en status kræver en ny ændring og brugerens ja.

**Data:** kun registret (`sim_equity`, `sim_fills`, `sim_orders`, `lane.decomposition`). Ingen nye data. Et døgn er et
afsluttet UTC-døgn. Døgnets netto = sidste equity i døgnet − sidste equity dagen før. For første døgn er basis
kontoens første mark. Vinduet er de seneste højst 28 afsluttede døgn.

| # | Måling | Formel | Mindste stikprøve | "forringelse mistænkt" | "fordel ikke længere støttet" |
|---|---|---|---|---|---|
| M1 | Nettoforventning | t = gennemsnit/(sd/√n) af døgnnetto; ensidet p for gennemsnit < 0 (Students t, n−1 frihedsgrader) | ≥ 14 døgn | gennemsnit < 0 | Holm-justeret p < 0,05 |
| M2 | Udførelse | r = gennemsnitlig realiseret `slippage` / gennemsnitlig modelleret (`expected_spread`/2 + `extra_slippage` fra ordrens `cost_model`), taker-fills i vinduet | ≥ 30 fills | r > 1,25 | r > 2,0 |
| M3 | Omkostning pr. bruttokant | (gebyrer + betalt afstand) / \|pris-/basis-P&L\| fra `lane.decomposition` | ≥ 28 døgn | ≥ 0,5 | ≥ 1,0 |
| M4 | Bogens alder ved fill | p95 af fill-ts − `book_ts`, taker-fills | ≥ 30 fills | > 30 s | > 60 s |
| M5 | Koncentration | (sum af de 3 bedste døgn) / samlet netto; kun når samlet netto > 0 | ≥ 28 døgn | ≥ 0,75 | ≥ 1,0 |

**Kun beskrivende, ingen tærskel:**
- funding pr. døgn;
- signalforsinkelse (ordre-ts − signaltid fra `signal_ref`), da den afhænger af strategiens design;
- datapauser.

**Status pr. konto:**
- den værste af M1–M5 blandt de målinger, der har stikprøve nok;
- "stabil", hvis ingen af dem udløser;
- "utilstrækkelige data", hvis ingen har stikprøve nok.

**Holm:** M1 er den eneste test med p-værdi. Holm over målingerne pr. konto er derfor p selv. Der korrigeres ikke på
tværs af konti, fordi statussen ikke udløser nogen handling. Det skrives ved siden af statussen.

**Status ved start (2026-10-24):** papirkontiene er højst 6 døgn gamle. Alle forventes "utilstrækkelige data" for M1,
M3 og M5. M2 og M4 kan allerede vurderes for de fremadrettede konti.

### 21w præcisering (2026-10-24 kl. 22:47, efter en tørkørsel på en kopi af produktionen, før kode commit og deploy)

Tørkørslen (skrivebeskyttet backup, ingen status vist nogen steder) viste to fejl i 21w's egen definition. Begge er
rettet før første visning.

1. **M2 gælder ikke bane- og scannerkonti (`LANE_`).**
   - Banens indgangsport (12g/12h) regner omkostningen fra den faktisk gennemgåede bog. Ordrens generiske
     `cost_model.expected_spread` (0,04 %) er ikke det, banen antog.
   - Tørkørslen gav forhold på 1,1–8,4 for tynde alt-spot-ben, altså falske alarmer: "fordel ikke længere støttet" for
     LANE_4c87acd9ce og "forringelse mistænkt" for LANE_d9f91862c8.
   - For `LANE_`-konti vises M2 kun beskrivende med status "ikke anvendelig". De fremadrettede og skyggekonti
     (`FWD_`, `SHADOW_`) bruger den generiske model og beholder M2. Forholdet dér var 0,61–0,91, altså under modellen.
2. **"stabil" kræver, at M1 har stikprøve nok.**
   - En konto, hvis nettoforventning (M1) har under 14 døgn, kan ikke kaldes "stabil", fordi intet er målt om fordelen.
   - Statussen er "utilstrækkelige data", medmindre en anden måling med stikprøve nok udløser "forringelse mistænkt"
     eller "fordel ikke længere støttet". En sådan måling vises da med navn.
3. **M4's fortegn:** fill-ts er afkortet til hele sekunder, og `book_ts` er et decimaltal. Små negative værdier (ned
   til −1 s) betyder derfor en bog under 1 s gammel. Tærsklerne bruges uændret.
