# ORIGINAL_DESIGNS_ORDER69: tre originale, falsificerbare designs (direktørordre 69 P3)

**Skrevet:** 2026-11-09 kl. 17:03 lokal (16:03 UTC, tjekket med `date`).
**Status:** KUN DESIGN. Intet er låst. Ingen alfa. Ingen strategi aktiveres. Intet er committet.

**Hvad jeg har gjort, og hvad ikke:**
- Ingen markedsdata er hentet, åbnet eller hashet. Ingen historisk forespørgsel. Ingen ny vært eller datakilde.
- lab.db er ikke åbnet. Ingen `python3 -m lab`. N4-filen og `quarantine/` er ikke rørt.
- Jeg har kun læst kode og dokumenter: `lab/hlcensus.py`, `lab/census.py`, `lab/k3.py`, `lab/moves.py`,
  `lab/fundsettle.py`, `lab/capacity.py`, `lab/depth500.py`, `tests/test_lab_safety.py` (linje 15-45),
  `tests/test_lab_hlcensus.py`, PROTOCOL_V3 (§2, 10c, 20, 21g-21l, 22, 24, 28, 28a, 32, 33, 38, 42), factory-registret,
  begge evidensregistre, `PROFIT_SEARCH_2026-11-09.md`, `U4_PROVENANCE_POWER_AUDIT.md`, `K10_MONITORING_TAG_DESIGN.md`,
  `FALSIFICATION_MATRIX_ORDER61.md`, `ONLINE_EDGES_2026-11-05.md`, H-SPR-1/2 og HFC-1-protokollen.
- Web kun til papirer og dokumentation. Deribits supportside og MDPI svarede 403. Det, der kun er set i et
  søgeresumé, står som UNVERIFIED.
- Styrke og MDE er regnet analytisk med `research/desk/order69_power.py` (stdlib, ingen data). Syntetiske tests i
  `tests/test_research_order69_power.py` (11 tests, grønne).
- Alle tal for spredning, hændelsesrate og omkostning er ANTAGELSE, skrevet før data. De rettes aldrig efter data
  (ændring 32 punkt 3).

## Kort svar

| # | Design | Hypotese i én linje | Overlap med tidligere arbejde | MDE (80 %, ensidet 0,0125) | Anbefaling |
|---|---|---|---|---|---|
| 1 | **VB1** volatilitetsbrud → carry-exit | Efter et opadgående strukturelt brud i en carry-positiv HL-perps timevolatilitet taber syntetisk carry (kort perp, lang spot) så meget de næste 72 t, at det betaler sig at lukke: B = −c − K > 0 | Carry-slægten (`cross_venue_perp_gap`, mange REJECTED) og `stop_rule_overlay` (L09 REJECTED) er naboer. Ingen delte observationer: kun hlcensus-timer efter låsen | 15,7 bp på B (netto); bruttotab ≥ ca. 53 bp kræves | **3. prioritet. PARKÉR.** Kun beskrivende (α = 0), hvis carry-bøgerne stadig kører, og isolationsundtagelsen gives |
| 2 | **LQ1** forbigående likviditetsbrud → vent en time | Når 5.000-USD-rundturen i et af scannerens 12 markeder er ≥ 3× sin egen 168 t-median, sparer det mere end ét taker-gebyr (5 bp) pr. side at vente én time: S̄ > 5 bp | R1 (21h/21l) og K1/K2 læser de samme `book_rt`-rækker, men kun niveauer, ikke vedholdenhed. H-SPR-1/2 er spread-referencer. Ingen afkastpåstand | 4,0 bp over tærsklen (sand besparelse ≥ ca. 9 bp kræves) | **1. prioritet. Betinget GO** for en beskrivende lås (α = 0). Billigst, størst styrke, tjener alle bøger |
| 3 | **EX1** optionsudløb kl. 08:00 UTC → rekyl | På fredage med Deribit-udløb vender BTC's 30-min-afkast efter afregningen fortegnet fra de 30 minutter ind i afregningen (TWAP-vinduet), netto efter 2 × 5 bp + bog | **Ny hændelsestype**, aldrig undersøgt i lab'et. Ingen delte observationer med U4/R3/J1 (2020-21, 08:30 ET) eller M1F/K10. Deler råe BTC-rækker og klokkeslæt med K3; K3's statistik er upåvirket. Nabo til reversal- og kalenderslægterne | 15,0 bp netto ved 52 fredage (12,1 bp ved 0,05) | **2. prioritet. Betinget GO** kun beskrivende (α = 0). NO-GO alfa. Lav forhåndssandsynlighed |

Ingen af de tre er en ny uafhængig bekræftelse af noget tidligere fund. Alle tre bruger kun fremtidige observationer, som
opstår efter deres egen lås.

## 0. Fælles regler for alle tre

**Omkostninger (citeret, ikke valgt efter data):**

| Post | Værdi | Kilde |
|---|---|---|
| Binance USD-M taker, krypto | 5,0 bp pr. side (standard; verificeret) | PROTOCOL_V3 21i punkt 1 |
| Binance TradFi-perps taker | 4,0 bp pr. side (kampagne "until further notice") | 21g |
| Samlet rundtur | `book_rt` (5.000 USD, spread + slippage) + 2 × taker | 21l punkt 1; måling 21h punkt 3 |
| Bog-skøn uden måling | RT_est(V) = exp(0,8999) · V^(−0,454) | 21i punkt 2 (et 2026-snapshot) |
| Lab'ets bane-model (stress) | taker 0,10 % + slippage 0,02 % pr. side og ben | ændring 42 punkt 2 |
| Screeningsgulv (stress) | 0,46 % pr. handel | 21i punkt 2, 17 |
| Hyperliquid taker, basistrin | 4,5 bp pr. side, **UNVERIFIED i denne session** (kilde i PROFIT_SEARCH: hyperliquid-docs/fees) | – |
| Funding | realiseret eller timevis forudsagt; aldrig en ordreomkostning | 21l punkt 1 |

**Vinduer og holdout:**
- Kun observationer skabt efter låsen. Perioden fra 2025-01-01 til observationsvinduets start forbliver reserveret
  (PROTOCOL_V3 linje 173, ændring 2 A punkt 6). 2024-holdout (G03) og 2025+ (G04) røres ikke. Ingen arkivfil læses.
- G01 (ingen historiske filer før 11-14) er ikke relevant: ingen af designene bruger historik.

**Alfa og status:**
- W0 har 0,0375 tilbage, men den er reserveret til andre (D6). Standard er derfor **α = 0: BESKRIVENDE**.
- Tærsklerne nedenfor bruger α_F = 0,0125 ensidet (ændring 8), så en senere ejerbeslutning ikke ændrer testen.
- Uden D5-nøglen er et ja UNVERIFIED_ORIGIN. Så kan resultatet kun være beskrivende.
- Order 53: ingen A/B-lås 11-14 uden et udtrykkeligt, dateret ejer-ja.

**Uafhængig evaluering (samme for alle tre):**
1. Låseteksten og evaluatorens kode committes før første tællende observation (kode før data).
2. Evaluatoren er et script i `research/tools/`, åbner lab.db med `mode=ro` og `PRAGMA query_only=ON`, og skriver kun
   en artefakt med sha256.
3. Den køres én gang ved fristen af en anden session end forfatteren (fx Codex-miljøet), med den låste commit.
4. Før fristen rapporteres kun antal (hændelser, klynger, dækning). Aldrig et udfald.
5. Resultatet committes uanset udfald. Nøglen screenes aldrig igen.

**Factory-registret:** hvert design tæller som ét nyt forsøg, hvis det låses (206 → op til 209). Med 206 forsøg er den
forventede bedste z fra held ca. 2,78 (PROFIT_SEARCH §1). En PASS her er én låst test på nye data, ikke "den bedste af
mange".

---

## 1. VB1: volatilitetsbrud som exit-regel for delta-neutral carry

### 1.1 Hypotese

**H1 (VB1):** For en likvid, carry-positiv Hyperliquid-perp gælder: når et opadgående strukturelt brud i
timevolatiliteten opdages, er den syntetiske carry over de næste 72 timer så negativ, at det betaler sig at lukke
positionen og åbne igen bagefter.

- **Primært endepunkt:** B_i = −c_i − K_i. Enhed: brøk af nominel pr. ben (1 USD kort perp + 1 USD lang spot).
- **c_i** = Σ timefunding over (t+1 t, t+73 t] − [ln(mark/oracle)_t+73 − ln(mark/oracle)_t+1].
  Kort perp + lang spot til oracle-pris. Funding er positiv for den korte, når longs betaler.
- **K_i** = exit og genindgang af begge ben: 2 × 4,5 bp (HL taker) + 2 × 10 bp (Binance spot, bane-model) + 4 × 2 bp
  slippage = **37 bp**, plus bogens rundtur for begge ben (RT_est(V), 21i). Ved 10 mio. USD omsætning er det ca. 69 bp.
- **Test:** ensidet t-test på UTC-døgnklyngernes middel af B, H0: B̄ ≤ 0. α_F 0,0125.
- **Specificitetsport (skal også holde):** pr. hændelse trækkes én kontrolmønt samme time (carry-positiv, likvid,
  intet brud de seneste 7 døgn; `random.Random(timens ts)` over sorterede navne). D_i = c_kontrol − c_hændelse.
  Ensidet p ≤ 0,05 for D̄ > 0. Uden porten er reglen bare "carry er dårlig", ikke en brudregel.

### 1.2 Mekanisme og litteratur

- Carry-trades krakker, når volatiliteten springer, fordi gearede positioner afvikles (Brunnermeier, Nagel & Pedersen
  2008, valuta). I krypto er carry en "inconvenience yield", drevet af gearede trend-købere (E04, X001).
- Bitcoin-volatilitet har strukturelle brud og regimer (E36 Shen, Urquhart & Wang 2020; E39 Ardia m.fl. 2019).
- Efter en likvidationskaskade kommer likviditeten langsomt tilbage (E16 Lim 2026).
- **Parametre fastlagt af litteraturen eller design, ikke af data:**

| Parameter | Værdi | Begrundelse |
|---|---|---|
| Bruddetektor | κ₁ (Sansó, Aragó & Carrion 2004), ICSS-familien (Inclán & Tiao 1994) | κ₁ retter ICSS for tykke haler |
| Kritisk værdi | 1,358 | asymptotisk 5 % (Inclán & Tiao) |
| Vindue | 168 timeafkast | én uge; fjerner ugemønstret |
| Brudpunktets alder | k* i de seneste 24 t | hændelsen skal være ny |
| Retning | variansen efter k* > før | kun opadgående brud |
| Dedup | højst én hændelse pr. mønt pr. 7 døgn | samme som vinduet |
| Horisont | 72 t | ændring 12g's "3 døgns funding" |
| Carry-positiv | middel af 24 t's timefunding ≥ 0,00125 %/t (0,01 %/8 t) | HL's rentedel; UNVERIFIED i denne session |
| Likvid | `dayNtlVlm` ≥ 10 mio. USD | C2's grænse (28a punkt 4) |
| Forsinkelse | handling ved næste snapshot (t + 1 t) | ingen nul-forsinkelse |

**Syntetisk tjek af detektoren** (`order69_power.py`, ingen data): på i.i.d. t(4)-afkast uden brud giver reglen ca.
0,02-0,03 hændelser pr. mønt-uge. Et permanent spring i sd fanges online inden for 24 t i 25 % (×1,5), 78 % (×2,
median 13 t) og 99 % (×3, median 7 t) af tilfældene. Rigtige afkast har volatilitets-klynger, så den reelle rate bliver
højere. Det er en del af definitionen, ikke en fejl.

### 1.3 Overlap

| Kilde | Hvad | Overlap med VB1 |
|---|---|---|
| Factory: `cross_venue_perp_gap` (funding_carry, delta_neutral_funding_carry; L08, L12, L13, fcarry-filtre REJECTED; L07 CLOSED) | Høst af carry | **Nabo.** VB1 påstår ikke, at carry tjener. Den tester tabssiden som exit-regel. Slægtsstraf ×0,4 (PROFIT_SEARCH §2) |
| Factory: `stop_rule_overlay` (L09 `stop_when_ahead` REJECTED) | Gevinst-stop | Nabo. Anden udløser (volatilitetsbrud, ikke P&L) |
| Factory: `betting_against_beta` (vol_managed_long p1/p2, xs_low_volatility REJECTED), `variance_risk_premium_timing` (REJECTED) | Volatilitet → retning/eksponering | Ingen afkastforudsigelse i VB1. Ikke vol-targeting |
| Ændring 20 (fregime) | Carry pr. funding-port (D2) | Andet signal (fundingniveau). Ingen fælles data |
| Census C3 (28a) og C4 (33) | Halebredde og volumen → BTC/mønt-volatilitet | Volatilitet er der et **udfald**; i VB1 er den **signalet**. Andre data (census/1, Binance) |
| HFC-1 (beskrivende, census/1) | Høj-funding-carry på Binance | Andre data og venue. Hændelser kan ramme samme mønter; overlap i mønter rapporteres |
| Ændring 13 HL-konti | Lang Binance spot / kort HL perp | VB1 er netop en exit-regel for dem. Bogens egne tal bruges ikke |
| hlcensus første kig (MISSION27_3 12b) | Fundingfordeling, kun beskrivende | Lav. Ingen brud eller carry-udfald set. Uanset: kun timer efter låsen |
| PROFIT_SEARCH "Hvad vi ikke gør" | Tværsnits-funding, gearet carry | VB1 er hverken faktor eller gearing |
| Holdout | – | Ingen. Kun fremtidige hlcensus-timer |

### 1.4 Data og dækning

- **Kilde:** `hlcensus/1` (ændring 38 A). Én række i timen med `funding`, `premium`, `markPx`, `oraclePx`, `midPx`,
  `openInterest`, `dayNtlVlm`, `prevDayPx`, `isDelisted` for hver HL-perp. Intet nyt kald, ingen ny vært
  (`api.hyperliquid.xyz` står i `ALLOWED_HOSTS`).
- **Dækning:** første snapshot 2026-11-02 15:00 UTC med 235 perps (MISSION27_3 punkt 573). Antal timer siden er ikke
  talt (lab.db er ikke åbnet).
- **Kendt risiko:** hlcensus kører i premium-watch. Census/1 manglede 17 af 52 timer 10-30..11-02 (MISSION27_3 12a).
  Huller rammer begge.
- **Huller:** afkast kun mellem to på hinanden følgende timer. Vinduet bruger de seneste 168 afkast inden for højst
  192 t, ellers ingen evaluering den time. Funding: mindst 66 af 72 timer, manglende timer sættes til middel af de
  tilstedeværende (mærket). Ellers udgår hændelsen med årsag.
- **Isolation:** `tests/test_lab_hlcensus.py` forbyder ordet "hlcensus" i alle `.py` under `research/` undtagen
  `hlcensus_look.py`. En evaluator kræver en ny, navngiven undtagelse (som `hlcensus_look`: `mode=ro`, ingen skrivning).
  Det er en godkendelse (afsnit 1.9).

### 1.5 Risiko for tidligere eksponering

- Lav for udfaldet. Ingen har beregnet brud eller carry på hlcensus (så vidt repoet viser).
- Fundingniveauer på HL kan være set i første kig (12b) og i HFC-1's census-tal. Derfor kun timer efter låsen.
- Parametrene står i tabellen ovenfor og kommer fra litteratur og lab-regler, ikke fra data.

### 1.6 Evaluering

- **Lås:** dato L. Hændelser tæller kun i [L + 7 d, L + 189 d), så hele signalvinduet ligger efter låsen.
- **Midtvejs (kun futilitet, intet alfa):** ved L + 98 d. Er c̄ for hændelserne ≥ 0 (carry er ikke engang negativ
  brutto), stoppes VB1 som STOPPED_FUTILE.
- **Dom:** én kørsel ved L + 193 d (udfald + 73 t + et døgn).
- **Domme:**
  - PASS: p ≤ α for B̄ > 0 og specificitetsporten holder;
  - PASS_UNSPECIFIC: B̄ består, porten ikke. Ingen brudregel; sagen går til carry-bøgernes egen opgørelse;
  - FALSIFIED: B̄ ≤ 0;
  - INCONCLUSIVE: ellers;
  - UNTESTABLE: < 40 klynger ved fristen;
  - INVALID: hlcensus-dækning < 90 % af timerne i vinduet.
- **Beskrivende:** c̄ (mekanismen), D̄, B med K ved 37 bp og med bog, fordeling pr. mønt, andel fra de 5 største døgn.

### 1.7 Styrke og MDE

| Antagelse | Værdi | Status |
|---|---|---|
| sd af klyngens B | 0,45 % (følsomhed 0,25-1,0 %) | ANTAGELSE: funding-sum over 72 t ca. 0,3 % og basisændring ca. 0,3 % for alts |
| Klynger | 78 på 6 mdr. (følsomhed 40-120) | ANTAGELSE: ca. 13 hændelsesdøgn pr. måned |
| Test | ensidet 0,0125; z 2,241 + 0,842 | ændring 32 punkt 1 |

| sd \ n | 40 | 78 | 120 |
|---|---|---|---|
| 0,25 % | 12,2 bp | 8,7 bp | 7,0 bp |
| **0,45 %** | 21,9 bp | **15,7 bp** | 12,7 bp |
| 1,0 % | 48,7 bp | 34,9 bp | 28,1 bp |

- Med t(77) er MDE 16,0 bp. Simuleret styrke ved MDE: 0,80 (normal) og 0,83 (t(3)-haler).
- **Økonomisk læsning:** B er allerede netto. Et sandt bruttotab efter brud på ca. 37 + 16 = **53 bp** over 72 t kræves for
  80 % styrke. Med bog (10 mio. USD) er det ca. 85 bp.
- Ændring 32-mærke: ikke et afkast-gulv-tilfælde, men "kan kun finde store effekter".

### 1.8 Stop- og kill-kriterier

1. Isolationsundtagelsen gives ikke → VB1 køres ikke (NO_RUN).
2. Dækning < 90 % → INVALID. Ingen forlængelse.
3. Midtvejs c̄ ≥ 0 → STOPPED_FUTILE.
4. < 40 klynger ved fristen → UNTESTABLE.
5. B̄ ≤ 0 → FALSIFIED. Slægten lukkes for volatilitetsbrud-exit; ingen variant af κ, vindue eller horisont.
6. Ingen handel, ingen konto og ingen exit i en kørende bog før en PASS og en ny dateret ændring med ejerens ja.

### 1.9 Godkendelser og tidligste datoer

| Trin | Kræver | Tidligst |
|---|---|---|
| Lås (tekst + evaluator) | direktørbeslutning + dateret ejer-ja; D5 for VERIFIED | 2026-11-16 (ANTAGELSE om ejer-ja) |
| Undtagelse i hlcensus-isolationstesten | ejer/direktør ja; kode før data | samme dag som låsen |
| Alfa | ejerbeslutning om W0; ellers α = 0 | – |
| Deploy | **ingen** (kun offline evaluator) | – |
| Første tællende hændelse | – | 2026-11-23 |
| Futilitetskig | – | 2027-02-22 |
| Dom | – | 2027-05-28 |

### 1.10 Begrænsninger

- Spotbenet er syntetisk: HL's oracle (et vægtet CEX-spotmedian) er ikke en handlebar pris. Lab'ets HL-konti bruger
  Binance spot.
- `funding` i metaAndAssetCtxs er den aktuelle, forudsagte timesats; den afregnede kan afvige lidt (UNVERIFIED).
- Timeopløsning. En kaskade inden for en time ses kun som ét stort afkast.
- Carry-slægten er hårdt ramt. Selv en PASS gør kun carry lidt mindre dårlig.
- Forventning skrevet før data: FALSIFIED eller INCONCLUSIVE er mest sandsynligt. PASS-chance ca. 10 % (ANTAGELSE).

---

## 2. LQ1: forbigående likviditetsbrud, og om det betaler sig at vente en time

### 2.1 Hypotese

**H1 (LQ1):** Når 5.000-USD-rundturen gennem bogen i et af scannerens 12 markeder er mindst 3 gange sin egen
168-timers median, er rundturen en time senere så meget lavere, at det sparer mere end ét taker-gebyr pr. side at
vente én time.

- **Primært endepunkt:** S_i = ½ (RT_t − RT_t+1 t), i bp pr. side for en ordre på 5.000 USD.
- **Netto:** gebyret er det samme i begge arme og går ud. Tærsklen på 5 bp (= én standard-taker, 21i) er prisen for at
  udskyde en ordre: signaltab og prisrisiko. Det er en designbegrundelse, ikke et datavalg.
- **Test:** ensidet t-test på UTC-døgnklyngernes middel, H0: S̄ ≤ 5 bp. α_F 0,0125.
- **Robusthedsport:** mindst 3 markeder bidrager, og S̄ uden markedet med flest hændelser er stadig > 5 bp (punktskøn).

### 2.2 Mekanisme og litteratur

- En ordrebog har "resiliens": efter et chok fyldes den op igen af nye limit-ordrer (Foucault, Kadan & Kandel 2005,
  RFS). Spændet kommer hurtigere tilbage end dybden (E16 Lim 2026: spread inden for 1,2× på dage, dybde langsommere).
- Spread og dybde svinger med volatilitet og omsætning (X033) og med tid på døgnet (X030, X031).
- Påstanden er kun om omkostning. Ingen retning, intet afkast.

| Parameter | Værdi | Begrundelse |
|---|---|---|
| Ordrestørrelse | 5.000 USD | 21h punkt 3 og 21l punkt 1 |
| Brud | RT_t ≥ 3 × baseline | lab'ets alarmkonvention "3 × reference" (H-SPR-1 punkt 5) |
| Baseline | median af markedets 168 foregående brugbare timer (≥ 120), kun efter låsen | én uge |
| Udskydelse | én time (næste scanning) | scannerens takt; kortere kan ikke måles |
| Dedup | højst én hændelse pr. marked pr. 6 t | `moves.DEDUP_S` |
| Tærskel | 5 bp pr. side | standard-taker, 21i punkt 1 |

### 2.3 Overlap

| Kilde | Hvad | Overlap med LQ1 |
|---|---|---|
| R1 (`lab/costreport.py`, 21h/21l) | medianer og 95 %-fraktil af `book_rt` i bevægelsestimer mod normalt | **Samme råe rækker.** R1 viser niveauer, ikke vedholdenhed fra time til time. Kun rækker efter låsen tæller |
| K1/K2 (21y) | `book_rt` i weekend mod åbningstid for TradFi | Samme rækker. LQ1 udelukker EWMA-timerne helt |
| H-SPR-1, H-SPR-2 | spread-reference og tick-bundne spreads | Andre data (`sim_exec`, `capacity/1`) og andet spørgsmål |
| `capacity/1`, `depth500/1` | dybe bøger, diagnostik | Bruges ikke |
| Factory: `maker_adverse_selection_measurement` (L19 CLOSED; pm_lp EXTERNAL) | maker-fyld | LQ1 er taker-timing. pm_lp røres ikke |
| Factory: `high_volume_return_premium` (illiquidity REJECTED), `liquidation_cascade_reversal` (L21 REJECTED), straks (41) | likviditet → afkast | LQ1 har intet afkast-endepunkt. Retningsdrift rapporteres kun og påstås ikke |
| PROFIT_SEARCH "Hvad vi ikke gør": maker på CEX | gebyr = medianspread | LQ1 er ikke maker |
| Holdout | – | Ingen. Kun fremtidige scanninger |

### 2.4 Data og dækning

- **Kilde:** scannerens `book_rt` og `spread` (detektor `abnormal_move/1`, 21h punkt 3), hver time ca. kl. HH:02, for
  de 12 markeder i `moves.WATCH`: BTC, ETH, XAU, XAG, XPT, COPPER, CL, BZ, NATGAS, SPY, QQQ, USDBRL. Payload har
  `off_hours` (21g). Intet nyt kald.
- **Observation:** den tidligste scanning pr. (marked, time), højst 10 min efter timeskiftet (21r, 21y C).
- **Udelukket (tælles):** t eller t + 1 i et EWMA-vindue; første time efter genåbning; manglende scanning ved t + 1.
- **Censur:** en bog for tynd til 5.000 USD har ingen `round_trip`. RT_t censureret → hændelsen tælles, men indgår ikke
  i S̄. RT_t+1 censureret → S_i = 0 (ingen målbar besparelse; konservativt mod H1).
- **Dækning:** ikke talt (lab.db ikke åbnet). Scanner-huller registreres af ændring 23.

### 2.5 Risiko for tidligere eksponering

- **Moderat for niveauer, lav for udfaldet.** R1-rapporterne har vist medianer og fraktiler af `book_rt` pr. marked.
  Ingen har vist, hvor hurtigt et spring falder igen.
- Tærsklerne (3×, 5 bp, 168 t, 6 t) er lab-konventioner eller gebyret. De er ikke valgt ud fra R1's tal.
- Universet er alle 12 markeder. BTC og ETH er dybe og giver små besparelser. Det gør testen konservativ. Jeg har ikke
  fravalgt dem efter R1.

### 2.6 Evaluering

- **Lås:** dato L. Baseline kræver 168 timer efter låsen, så hændelser tæller i [L + 7 d, L + 98 d) (én kvart år).
- **Dom:** én kørsel ved L + 99 d.
- **Domme:**
  - PASS: p ≤ α for S̄ > 5 bp og robusthedsporten holder;
  - FALSIFIED: ensidet 95 %-øvre grænse for S̄ < 5 bp;
  - INCONCLUSIVE: ellers;
  - INCONCLUSIVE_CENSORED: > 20 % af hændelserne har censureret RT_t;
  - UNTESTABLE: < 30 klyngedøgn med hændelser ved fristen;
  - INVALID: < 90 % af de brugbare timer har en scanning.
- **Beskrivende:** S pr. marked; andel af overskuddet, der er væk efter en time, (RT_t − RT_t+1)/(RT_t − baseline);
  retningsdrift s · ln(mark_t+1/mark_t) med s = fortegnet af z_1h ved t (kun rapport; det er m21c/straks' område).

### 2.7 Styrke og MDE

| Antagelse | Værdi | Status |
|---|---|---|
| sd af klyngens S | 10 bp (følsomhed 5-30) | ANTAGELSE: tynde TradFi-bøger svinger meget; tunge haler |
| Klyngedøgn | 60 på 91 dage (følsomhed 30-120) | ANTAGELSE: brud i ca. 1 % af brugbare timer, ca. 2-3 pr. døgn i alt |
| Test | ensidet 0,0125 mod 5 bp | – |

| sd \ n | 30 | 60 | 120 |
|---|---|---|---|
| 5 bp | 2,8 | 2,0 | 1,4 |
| **10 bp** | 5,6 | **4,0** | 2,8 |
| 30 bp | 16,9 | 11,9 | 8,4 |

- Tallene er MDE **over** tærsklen. En sand besparelse på ca. 9 bp pr. side giver 80 % styrke (sd 10, n 60). Med t(59)
  er MDE 4,1 bp. Simuleret styrke: 0,80 (normal), 0,84 (t(3)).
- LQ1 har den bedste styrke af de tre. Den kan finde en effekt på størrelse med ét gebyr inden for et kvartal.

### 2.8 Stop- og kill-kriterier

1. < 30 klyngedøgn ved L + 98 d → UNTESTABLE. Ingen forlængelse uden en ny dateret ændring.
2. Dækning < 90 % → INVALID.
3. > 20 % censur → INCONCLUSIVE_CENSORED.
4. Øvre 95 %-grænse < 5 bp → FALSIFIED. Ingen ny tærskel, størrelse eller udskydelse.
5. Ingen papirmotor, bane eller ordre ændres før en PASS og en ny dateret ændring med ejerens ja. En PASS giver kun et
   forslag til en udførelsesregel ("udskyd én time ved brud") for retningsneutrale ordrer, fx lukning af hedgede par.

### 2.9 Godkendelser og tidligste datoer

| Trin | Kræver | Tidligst |
|---|---|---|
| Lås (tekst + evaluator) | direktørbeslutning + dateret ejer-ja; D5 for VERIFIED | 2026-11-16 (ANTAGELSE) |
| Alfa | ejerbeslutning om W0; ellers α = 0 | – |
| Ny datalinje eller deploy | **ingen** | – |
| Første tællende hændelse | – | 2026-11-23 |
| Dom | – | 2027-02-23 |

### 2.10 Begrænsninger

- Timeopløsning. Brud, der varer få minutter, ses ikke. LQ1 måler kun, om en times udskydelse hjælper.
- Scannerens bog har 100 niveauer (`limit=100`), papirmotoren ser kun 20. Forskellen står i rapporten.
- Én størrelse (5.000 USD). Større ordrer kan opføre sig anderledes (capacity/1 viser kun det beskrivende).
- Prisrisikoen ved at vente er ikke en del af S. Den er nul i middel kun for retningsneutrale ordrer.
- Forventning skrevet før data: TradFi-bøgerne udenfor EWMA er tynde og kommer hurtigt igen. PASS-chance ca. 40 %
  (ANTAGELSE). En PASS er en omkostningsregel, aldrig alfa.

---

## 3. EX1: optionsudløb kl. 08:00 UTC og rekyl efter afregningen

### 3.0 Overlap-audit først (ordrens krav)

**Konklusion:** EX1 bruger en hændelsestype, lab'et aldrig har undersøgt, og ingen observation, som U4, R3, J1, M1F
eller K10 har brugt. Den deler klokkeslæt og råe BTC-rækker med K3. Det er håndteret nedenfor.

| Studie | Hændelser | Data og vindue | Delte observationer med EX1? |
|---|---|---|---|
| U4 H1 (`U4_0830_PREREG_DRAFT.md`, audit) | CPI/NFP 08:30 ET (12:30/13:30 UTC) | 22 BTC 1m-zip fra explore0 2020-03..2021-12, læst af R3 | **Nej.** Andre tider, år og kilde. EX1 rører ingen zip-fil |
| R3 m24 (SCREEN_FAIL, p 0,918) | 58 makroudgivelser | samme 44 1m-filer; fortsættelse efter bar 0 | **Nej.** R3 testede fortsættelse ved makro. Ikke informativ for EX1 |
| J1 m21j (SCREEN_FAIL) | samme makrokalender | 1 t-barer, 24 t-drift | Nej |
| FOMC 2026-10-28 (beskrivende) | ét FOMC kl. 18:00 UTC | – | Nej |
| 14a H1 makrodybde | FOMC/CPI/NFP 2023 | bogdybde | Nej |
| M1F (17j) / K10 | Binance Monitoring Tag, ikke planlagt | alts, 1-7 døgn | Nej |
| **K3** (ændring 22) | fundingafregning hver 4. time, også kl. 08:00 | minut-marks S ± 35 min, inkl. BTCUSDT som markedskorrektion | **Samme råe BTC-rækker og samme klokkeslæt.** K3's statistik d = r_pre(HØJ) − r_pre(KONTROL), og BTC-leddet går ud. At kende BTC's fredagsmønster ændrer derfor ikke K3's test. Fundingafregningen kl. 08:00 sker hver dag og fjernes af EX1's kontroldage |
| `calendar_day_of_week` (hour_of_day p1, day_of_week p1 REJECTED) | ubetingede afkast pr. time/ugedag | explore0 1 t | Nabo. EX1 er en betinget rekyl i et afregningsvindue, minutdata, fremad. Slægtsstraf |
| `short_term_reversal_liquidity` (m21c, daily_reversal, L21, DROP4S) | rekyl efter store bevægelser | explore0 / fremad | Nabo i handelsform (rekyl). Udløseren er en planlagt afregning, ikke en stor bevægelse |
| straks-bogen (41) | følg/mod ved timeflag | `abnormal_move/1` | Nej. Ingen fælles statistik |
| Pipeline-17 (147 nøgler) | listing, margin, staking, airdrop, delisting m.fl. | – | Ingen optionsudløb eller levering |
| ONLINE_EDGES støjliste: "max pain" | retning mod en strike | – | EX1 bruger ingen strikes og ingen retning mod en strike |

`grep` i `research/` efter "expiry", "udløb", "delivery", "max pain": kun støjlisten, `FORWARD_DATA_PLAN.md`'s
`deliveryDate`-felt og instrumentmodellen `spot_delivery_ratio`. Ingen test af udløb.

### 3.1 Hypotese

**H1 (EX1):** På fredage med Deribit-udløb kl. 08:00 UTC vender BTC-perpens afkast i de 30 minutter efter afregningen
fortegnet fra afkastet i de 30 minutter ind i afregningen. Effekten er større end på mandag-torsdag kl. 08:00, og den
er stor nok til at dække omkostningerne.

- **Målinger (K3's regel D punkt 3, Binances tid):** r_pre = ln(m(−1)/m(−31)); r_post = ln(m(+31)/m(+1)); s = fortegnet af
  r_pre (r_pre = 0 udelukkes).
- **Primært endepunkt:** y_net = −s · r_post − c_t. Enhed: brøk pr. handel (én rundtur i BTCUSDT-perpen).
- **c_t** = 2 × 0,05 % + BTC's `book_rt` (5.000 USD) fra scannerens måling kl. 08:0x samme dag (21h punkt 3, 21l
  punkt 1). Mangler den: seneste måling inden for 24 t; ellers udelukkes fredagen (tælles). Typisk ca. 11 bp
  (ANTAGELSE: bog ca. 1 bp).
- **Test:** ensidet t-test over fredage, H0: ȳ_net ≤ 0. α_F 0,0125.
- **Specificitetsport (DiD):** pr. uge δ_w = y_gross(fredag) − middel af y_gross(man-tor kl. 08:00). Ensidet p ≤ 0,05.
- **Placebo:** samme regel samme fredag kl. 10:00 (K3's placebovindue S + 2 t). Tosidet p > 0,05 kræves.

### 3.2 Mekanisme og litteratur

- Deribit afregner udløb kl. 08:00 UTC til en 30-minutters TWAP af indekset 07:30-08:00 (Deribits supportside via
  søgeresumé; siden selv gav 403: **UNVERIFIED**). Fredage har det ugentlige udløb; sidste fredag i måneden og i
  kvartalet er større. Binances kvartalskontrakter leveres også fredag kl. 08:00 (UNVERIFIED).
- Afregningsrelateret ordreubalance kan give et midlertidigt prispres, der vender bagefter. Stoll & Whaley (1987, FAJ;
  1991, FAJ) fandt ca. 0,4 % rekyl efter kvartalsudløb i S&P 500-futures, men ikke for rene indeksoptioner.
- **Modevidens:** Plastun, Khomutenko & Bashlai (2022, JRFM 15(2):92) finder kun svage, insignifikante
  udløbseffekter i daglige BTC-data 2018-2021. Deribits TWAP er netop lavet for at dæmpe pres. Begge dele sænker
  forhåndssandsynligheden.
- **Parametre fastlagt af design:** 30 min før = TWAP-vinduet; 30 min efter = samme længde og K3's eksisterende
  endepunkter; kontrol = man-tor samme klokkeslæt (samme fundingafregning, mindre udløb); placebo = K3's 10:00-vindue.
  Ingen tærskel på r_pre.

### 3.3 Data og dækning

- **Nu:** K3 gemmer BTCUSDT's mark hvert premium-watch-pas i 07:25-08:35 og 09:25-10:35 UTC hver dag
  (`lab/k3.py`: `members.append((BTC, "btc"))` i både real og placebo). Runder, der er `missed`, har ingen marks.
- **Foretrukket:** en lille, selvstændig lagring `ex1/1` af BTC's premiumIndex-række (allerede hentet hvert minut) i de
  samme to vinduer, så EX1 ikke afhænger af K3's livsforløb. Intet nyt kald, ingen ny vært. Det er kode i premium-watch og
  kræver deploy (afsnit 3.8). Indtil da bruges K3's BTC-rækker.
- **Omkostning:** scannerens BTC `book_rt` kl. HH:02 (21h punkt 3).
- **Dækning:** ikke talt. Premium-watch har haft huller (MISSION27_3 12a). Kill ved for få gyldige fredage.

### 3.4 Risiko for tidligere eksponering

- **Lav.** K3's rækker er kun talt (antal), aldrig analyseret; K3's én-kig-regel forbyder det før 60 runder.
- Ingen har set BTC's minutafkast omkring kl. 08:00 på fredage i lab'et.
- Ekstern viden: Plastun m.fl. (dagsdata) og Stoll & Whaley (aktier). De er ikke lab-observationer.

### 3.5 Evaluering

- **Lås:** dato L. Fredage fra første fredag efter L tæller (2026-11-20 med K3-rækker; 2026-12-04 med kun `ex1/1`).
- **Futilitet (intet alfa) ved 26 fredage:** ȳ_gross ≤ 0 → STOPPED_FUTILE.
- **Dom ved 52 fredage:** én kørsel.
- **Domme:**
  - PASS: p ≤ α for ȳ_net > 0, DiD-porten holder og placebo ok;
  - PASS_NOT_EXPIRY: nettotesten består, DiD ikke. Det er en daglig 08:00-effekt (K3's område), ingen udløbspåstand;
  - FALSIFIED: ȳ_net ≤ 0;
  - INCONCLUSIVE: ellers;
  - UNTESTABLE: < 40 gyldige fredage 2027-12-31;
  - INVALID: datakilden ophører uden erstatning.
- **Beskrivende:** dosis-respons (måned/kvartal mod kun-uge), stress med bane-omkostning (24 bp) og 21i-gulvet (46 bp),
  r_pre's fordeling.

### 3.6 Styrke og MDE

| Antagelse | Værdi | Status |
|---|---|---|
| sd af y pr. fredag | 0,35 % (følsomhed 0,25-0,50 %) | ANTAGELSE: BTC 40-50 % årlig volatilitet → 30 min ca. 0,30-0,38 % |
| n | 52 fredage (26 ved futilitet) | kalender |
| Omkostning | 11 bp realistisk; 24 bp bane-model; 46 bp gulv | 21i/21l; ændring 42; 21i punkt 2 |

| sd \ n | 26 | 52 |
|---|---|---|
| 0,25 % | 15,1 bp | 10,7 bp |
| **0,35 %** | 21,2 bp | **15,0 bp** |
| 0,50 % | 30,2 bp | 21,4 bp |

- Med t(51): 15,3 bp. Ved α 0,05 (beskrivende): 12,1 bp. Simuleret styrke ved MDE 0,78 (normal), 0,83 (t(3));
  simuleret størrelse under H0 0,015.
- **Brutto-rekyl, der kræves for 80 %:** 11 + 15 = **26 bp** (realistisk) og 39 bp (bane-model).
- MDE/gulv (ændring 32) = 15,0/46 = 0,33. Mod det konservative 21i-gulv skulle bruttoeffekten være ≥ 46 bp; det er
  usandsynligt.
- DiD-porten (sd × √(1 + 1/4)): MDE 13,5 bp ved α 0,05.

### 3.7 Stop- og kill-kriterier

1. 26 fredage og ȳ_gross ≤ 0 → STOPPED_FUTILE.
2. < 40 gyldige fredage 2027-12-31 → UNTESTABLE.
3. ȳ_net ≤ 0 ved 52 → FALSIFIED. Ingen variant af vinduer, tidspunkter, mønter eller kontraktklasser.
4. K3-rækkerne ophører, og `ex1/1` er ikke deployet → INVALID.
5. Ingen handel, konto eller bog før en PASS og en ny dateret ændring med ejerens ja.

### 3.8 Godkendelser og tidligste datoer

| Trin | Kræver | Tidligst |
|---|---|---|
| Lås (tekst + evaluator) | direktørbeslutning + dateret ejer-ja; D5 for VERIFIED | 2026-11-16 (ANTAGELSE) |
| Brug af K3's BTC-rækker | direktørens ja til at læse en anden detektors rækker (kun BTCUSDT, kun `mark`) | ved låsen |
| `ex1/1`-lagring | dateret ejer-ja til datalinjen; tekst før kode; grøn suite | deploy tidligst 2026-11-30 (ingen genstart før 11-27, pm_lp's trin 11-28 først, uden for K1-K3) |
| Alfa | ejerbeslutning om W0; ellers α = 0 | – |
| Første tællende fredag | – | 2026-11-20 (K3-rækker) / 2026-12-04 (kun `ex1/1`) |
| Futilitet | – | 2027-05-14 / 2027-05-28 |
| Dom | – | 2027-11-12 / 2027-11-26 |

### 3.9 Begrænsninger

- Mark-prisen er ikke en handelspris. Omkostningen bruger den målte bog kl. 08:0x som skøn.
- Deribits regler og datoer er UNVERIFIED i denne session. De tjekkes i dokumentationen før låsen; ingen data.
- Daglige Deribit-udløb (hvis de findes) gør kontroldagene til "små udløb". DiD måler så forskellen i størrelse.
- Én mønt (BTC). ETH er udeladt for at undgå multiple tests.
- Tidshorisont over et år. Regimet kan skifte undervejs.
- Forventning skrevet før data: STOPPED_FUTILE eller FALSIFIED er mest sandsynligt. PASS-chance ca. 5-10 %
  (ANTAGELSE).

---

## 4. Falsifikationsmatrix (format som ordre 61)

| Hypotese | Primært endepunkt | Kill-regel | Data til rådighed? | Godkendelser | Tidligste dom | Anbefaling |
|---|---|---|---|---|---|---|
| **LQ1** forbigående likviditetsbrud: vent én time ved RT ≥ 3× median | S̄ = ½(RT_t − RT_t+1) i bp pr. side, 5.000 USD; H0 S̄ ≤ 5 bp; døgnklynger | øvre 95 % < 5 bp → FALSIFIED; < 30 klynger → UNTESTABLE; > 20 % censur → INCONCLUSIVE_CENSORED; dækning < 90 % → INVALID | **Ja** (scannerens `book_rt`, 12 markeder, kører). Ingen ny linje | lås + dateret ejer-ja (D5 for VERIFIED); α = 0 | 2027-02-23 | **1. Betinget GO, beskrivende (α = 0).** Billigst; MDE 4 bp over tærsklen; tjener alle bøger; ingen alfa-påstand |
| **EX1** rekyl efter Deribit-afregning fredag 08:00 UTC | ȳ_net = −s · r_post − (2 × 5 bp + bog) pr. fredag; DiD mod man-tor; placebo 10:00 | 26 fredage ȳ_gross ≤ 0 → STOPPED_FUTILE; ȳ_net ≤ 0 ved 52 → FALSIFIED; < 40 fredage 2027-12-31 → UNTESTABLE | **Delvis** (K3's BTC-marks kører; egen `ex1/1` kræver deploy) | lås + ejer-ja; ja til K3-rækker; datalinje-ja til `ex1/1` (deploy ≥ 11-30); α = 0 | 2027-11-12 | **2. Betinget GO, beskrivende (α = 0). NO-GO alfa.** Ny hændelsestype uden overlap, men svag forhåndsevidens |
| **VB1** volatilitetsbrud → luk syntetisk HL-carry 72 t | B̄ = −c − K (K ≥ 37 bp), døgnklynger; specificitetsport mod kontrolmønter | midtvejs c̄ ≥ 0 → STOPPED_FUTILE; B̄ ≤ 0 → FALSIFIED; < 40 klynger → UNTESTABLE; dækning < 90 % → INVALID; ingen isolationsundtagelse → NO_RUN | **Ja** (hlcensus kører), men isolationstesten forbyder i dag en evaluator | lås + ejer-ja; undtagelse i `test_lab_hlcensus.py`; α = 0 | 2027-05-28 | **3. PARKÉR.** Kun beskrivende, hvis HL-carry-bøgerne kører; carry-slægten er hårdt ramt; høj K |

**Prioritering (begrundelse):**
1. **LQ1 først.** Den kræver ingen ny datalinje, ingen deploy og ingen undtagelse. Den har den bedste styrke og giver
   en dom inden for et kvartal. Den er cost-arbejde, der tjener hver fremtidig kandidat (ikke én strategi).
2. **EX1 dernæst.** Den er den eneste rene nye hændelsestype og deler ingen observation med U4, R3, J1, M1F eller K10.
   Men den tager et år, og den eksterne evidens er svag.
3. **VB1 sidst.** Data findes, men den er tættest på afviste slægter, kræver en undtagelse i en sikkerhedstest og har en
   høj omkostningsbarriere.

**Fælles blokeringer (uændrede fra ordre 61):** D5-nøglen mangler; W0-alfa er optaget; ingen lås 11-14 uden dateret
ejer-ja; ingen genstart før 11-27; pm_lp røres aldrig.

## 5. Syntetisk test

- `research/desk/order69_power.py`: MDE-formlen fra ændring 32, t-kvantiler (Cornish-Fisher), Monte Carlo-styrke på
  syntetiske data (normal og t(3)), κ₁-detektoren og dens falske hændelsesrate. Kør:
  `python3 research/desk/order69_power.py`.
- `tests/test_research_order69_power.py`: 11 tests. Formel, monotoni, t-kvantiler mod tabelværdier, overskriftstallene
  i denne note, styrke ≈ 80 % ved MDE, størrelse under H0, robusthed mod tykke haler og detektorens opførsel (springer
  op, ned, gamle brud, konstant |r|). Kørt med `python3 -m unittest tests.test_research_order69_power`: **OK, 11 tests,
  ca. 1,3 s.**

## 6. Kilder

**Lokale:** PROTOCOL_V3 (linje 28-40, 173, 878-890, 2168-2200, 2433-2545, 2648-2680, 3213-3345, 3369-3407,
3596-3680, 3887-3957, 4237-4272, 4364-4410); `research/data/factory/registry.json`;
`research/desk/evidence_registry.json` (E04, E16, E36, E39) og `_ext.json` (X001, X030, X031, X033);
`research/desk/PROFIT_SEARCH_2026-11-09.md`; `research/desk/U4_PROVENANCE_POWER_AUDIT.md`;
`research/desk/K10_MONITORING_TAG_DESIGN.md`; `research/desk/FALSIFICATION_MATRIX_ORDER61.md`;
`research/studies/ONLINE_EDGES_2026-11-05.md`; `research/studies/MISSION27_3_2026-11-02.md` (12a, 12b, 18);
`research/studies/H_SPR1_INSTRUMENT_SPREAD_2026-11-03.md`, `H_SPR2_TICK_SPREAD_2026-11-04.md`,
`HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md`; `lab/hlcensus.py`, `lab/census.py`, `lab/k3.py`, `lab/moves.py`,
`lab/fundsettle.py`; `tests/test_lab_safety.py` linje 15-45; `tests/test_lab_hlcensus.py` (Isolation).

**Web (kun papirer og dokumentation):**
- Deribit, Settlement: https://support.deribit.com/hc/en-us/articles/29734325712413-Settlement (403; indhold kun set i
  søgeresumé, UNVERIFIED)
- Plastun, Khomutenko & Bashlai (2022), "Is There Any Witching in the Cryptocurrency Market?", JRFM 15(2):92:
  https://econpapers.repec.org/RePEc:gam:jjrfmx:v:15:y:2022:i:2:p:92-:d:754404 (abstract læst; MDPI-siden gav 403)
- Stoll & Whaley (1987), "Program Trading and Expiration-Day Effects", FAJ:
  https://rpc.cfainstitute.org/research/financial-analysts-journal/1987/program-trading-and-expiration-day-effects
  (kun søgeresumé; 0,4 %-tallet er UNVERIFIED)
- Stoll & Whaley (1991), "Expiration-Day Effects: What Has Changed?", FAJ:
  https://rpc.cfainstitute.org/research/financial-analysts-journal/1991/expiration-day-effects-what-has-changed
  (kun søgeresumé)
- Uden opslag i denne session (kendt litteratur, UNVERIFIED her): Inclán & Tiao (1994, JASA 89:913-923);
  Sansó, Aragó & Carrion (2004, Estadística Española 46:41-64); Brunnermeier, Nagel & Pedersen (2008, NBER
  Macroeconomics Annual 23); Foucault, Kadan & Kandel (2005, RFS 18:1171-1217); Hyperliquids gebyrside
  (https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees, citeret i PROFIT_SEARCH).
