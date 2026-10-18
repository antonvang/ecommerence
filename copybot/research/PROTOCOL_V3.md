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
