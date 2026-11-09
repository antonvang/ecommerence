# FAPI_DESIGNS_76B: fem mekanismer på Binance USD-M (direktørordre 76-B)

**Status: UDKAST, IKKE LÅST.** Ingen lås, ingen alfa, ingen statusændring, ingen ledger-række. Ingen data er hentet.

**Skrevet:** 2026-11-09 kl. 23:35 lokal (22:35 UTC, læst med `date`).

**Hvad jeg har gjort og ikke gjort:**
- Læst kode og noter (afsnit 13). Web kun til litteratur; ingen Binance-vært er kaldt. Status VERIFIED/ABSTRACT/UNVERIFIED står ved hver kilde.
- Ingen markedsdata, ingen historisk forespørgsel, intet nyt endpoint, ingen stream eller collector. `lab.db`, `pm_lp.db` og holdouts er ikke åbnet. Filen med N4-parrene og karantænemappen er ikke rørt.
- Alle tal for spredning, hændelsesrate, omkostning og "plausibel effekt" er **ANTAGELSER** skrevet før data. De må aldrig rettes efter data.
- Kode: `fapi_power_76b.py`, `fapi_evaluators_76b.py`, `fapi_designs_76b.py` (kun syntetiske data). Test: `tests/test_fapi_designs_76b.py`.

**Register:** `SNAPSHOT_v1.json`, sha256 `311ceb39a1ca9e6dc581f908ad678fcf76fb0c58d8ddfad58a8b837288657105` (regelversion 1). 19.438 varianter er et **konservativt minimum, ikke et endeligt N**. N_eff, DSR og PBO er `MISSING_INPUT`. Max-z er kun diagnostik.

## Kort svar

| # | Mekanisme | Design | Dom | Hvorfor |
|---|---|---|---|---|
| 1 | P1 volatilitetsregimer | **CB1_VOL** kompression + udbrud + volumen → volatilitet over HAR | **OVERLEVER_BESKRIVENDE** (α = 0) | Kan testes på census, MDE 0,057 log; antagelsesfølsom |
| 1 | P1 volatilitetsregimer | **CB1_DIR** samme hændelse → fortsættelse i kursen | **AFVIST** (EFFECT_REACHABLE) | MDE 0,92 % pr. 3 døgn netto mod plausibel 0,14 % |
| 2 | P1 funding og perp-prisdannelse | **PR1** premium-henfald: likvide mod tynde perps | **OVERLEVER_BESKRIVENDE** (α = 0) | Billigst; ingen ny stream; ingen handelspåstand |
| 3 | P2 likviditet | **LD1** kursledt mod likviditetsledt bogforstyrrelse | **AFVIST** (DISTINCT, EFFECT_REACHABLE) | Ligger inden for LQ1/LIQREC1; kan kun være sekundær analyse under LQ1 |
| 4 | P2 ekstreme bevægelser | **FL1** 4σ-fald med OI-flush | **AFVIST** (DISTINCT, VALIDATION_PLAN, EFFECT_REACHABLE) | M2 har testet det; ingen fremadrettet OI |
| 5 | P3 tidsmønstre | **TS1** US-session i højvol-regime | **AFVIST** (MECHANISM, DISTINCT, EFFECT_REACHABLE) | Regimet ligger i forseglede vinduer; afviste kalenderdesigns |

**Ingen af de to overlevende er en strategi, og ingen af dem er en ny, uafhængig opdagelse.** En PASS giver kun lov til at skrive en dateret risiko- eller omkostningsregel. Ingen tjener penge på CB1_VOL eller PR1.

**Bemærk ved "overlever":** dommen hviler på antagelser om spredning og antal. Ved den registerbrede grænse (Bonferroni, N ≥ 19.440, diagnostik) klarer ingen af dem deres plausible effekt: CB1_VOL kræver 0,101 mod 0,08, PR1 kræver 0,104 mod 0,10.

## 0. Fælles for alle fem

**Hurtig falsifikation (mekaniske gates, `fapi_designs_76b.GATES`).** Falder én gate, er designet AFVIST:

| Gate | Krav |
|---|---|
| MECHANISM | Kan formuleres med faste regler, og mekanismen kan testes med godkendte data |
| DATA_ALLOWED | Alle primære kilder er kørende eller cachet og åbnes fra 14/11; ingen blokeret eller ugodkendt kilde |
| DATA_REALISTIC | Mindst 40 klynger og højst 24 måneder |
| DISTINCT | Kan skelnes fra afviste designs og ligger ikke inden for et andet udkasts mekanismegrænse |
| EFFECT_REACHABLE | MDE (α_F = 0,0125 ensidet, 80 % styrke) ≤ plausibel nettoeffekt |
| VALIDATION_PLAN | Fremadrettet vindue efter låsen med godkendt datakilde |

**Datavinduer:**
- Fra 14/11 må `explore0` (2020-03..2021-12), `train3` (2022-01..2023-06) og `validation3` (2023-07..2023-12) kun bruges efter en LÅS, og de er **ikke uafhængige**: lab'et har kørt mange forsøg på dem. Holdout 2024 og reserveret 2025+ røres ikke (G03, G04).
- Uafhængig validering kan kun ske på observationer **skabt efter låsen**. G05 forbyder at bruge egne fremadrettede rækker (≥ 10-27) til at kalibrere eller vælge før låsen. Læst konservativt som i FUNDFRAG1: heller ikke som opvarmning.

**Omkostninger (citeret, ikke valgt efter data):** taker 5 bp pr. side (21i punkt 1). Bog: RT_est(V) = exp(0,8999) · V^(−0,454) for 5.000 USD (21i punkt 2, estimat fra ét snapshot). Screeningsgulv 46 bp pr. handel (21i punkt 2). Lab'ets banemodel 24 bp rundtur (ændring 42 punkt 2). Funding er en omkostning for longs.

**Multipel test:** alle tests er forhåndsregistrerede med K = 1 pr. endepunkt, testniveau 0,0125 ensidet og α = 0 beskrivende, medmindre ejeren beslutter andet (W0 er optaget, G20). Registerbar: Bonferroni z ≈ 4,56 ved N = 19.440 (α 0,05 ensidet, kun diagnostik, ikke kalibreret, N sænkes aldrig). `check_multiple_testing` kaldes med `n_tested = 19.438 + K`.

**Uafhængig validering (samme for alle overlevende):** (1) låsetekst og evaluator committes før første tællende observation; (2) evaluatoren åbner `lab.db` med `mode=ro` og `query_only`; (3) én kørsel ved fristen af en anden session end forfatteren med den låste commit; (4) før fristen rapporteres kun antal; (5) resultatet committes uanset udfald; (6) en PASS kræver genfinding i et nyt fremadrettet vindue, før der siges mere end "målt i ét vindue".

**Fælles begrænsning i census:** `census/1` viser ikke afnoteringer (FORWARD_DATA_PLAN fund 2), og huller ligger i stressede timer (MISSION27_4). Manglende timer udfyldes aldrig. Afnoteringer læses fra news/1 via `gates.news_rows`.

---

## 1. CB1: kompression, derefter udbrud med deltagelse (P1)

**Det, en chartlæser ser:** en coil, hvor dagsintervallerne bliver smallere, og derefter et lukke uden for intervallet på usædvanlig volumen.

**Økonomisk forklaring.** I kompression samler stop-ordrer sig lige uden for intervallet, og gearede positioner lægges op med lav volatilitet som gearingsgrundlag. Et brud udløser stop og tvungen lukning, og modparter, der havde solgt volatilitet eller stillet likviditet i smalle intervaller, må dække. Taberne er stop-placerede positioner og risikomodeller, der bruger lav volatilitet (EWMA) til gearing. Det forsvinder ikke helt, fordi volatilitet klumper sig på flere horisonter (HAR, Corsi 2009), og gearingsbegrænsninger binder i omslaget (Brunnermeier & Pedersen 2009). **Modsat:** den mekanisme forklarer en volatilitetsændring, ikke nødvendigvis en retning.

**Hvorfor anderledes end de falsificerede timetrendregler:** tsmom_v1 og L03 holdt positioner kontinuerligt på timebarer. CB1 er hændelsesbetinget (ca. én hændelse pr. coin pr. kvartal, ANTAGELSE), på dagsbarer, med en betingelse om kompression og en volumenbetingelse. Den ændrer ikke, at trendlitteraturen efter korrektion er svag (X066: Sharpe 2,08 → 0,01; Bajgrowicz & Scaillet 2012), og derfor tælles retning som et særskilt endepunkt, der skal bære sin egen styrke.

**Faste regler (ingen variantgitter).** Dagsbar fra census 00:00 UTC: 24 t-ticker (high, low, last, quoteVolume) med registreret forskydning op til 10 min. Univers pr. dag: quoteVolume ≥ 1 mio. USD, set ≥ 30 d (census), ingen kendt afnotering.
- **Kompression ved D:** gennemsnit af ln(H/L) over de 7 dage til og med D−1 er strengt under 15 %-fraktilen af samme mål over de 90 foregående værdier (mindst 60), kun data før D−1.
- **Udbrud på D:** lukke over den højeste high (eller under laveste low) i de 20 foregående dage.
- **Deltagelse:** volumen på D ≥ 2 × medianen af de 20 foregående dages volumen.
- **Afklipning:** højst én hændelse pr. mønt pr. 14 dage. Side s = ±1.
- **CB1_VOL (risiko, ingen retning):** g = ln(RV de næste 3 dage) − log-HAR-prognosen, med HAR på 1, 7 og 30 dage og OLS på rækker, hvis mål var kendt på D. y = g − medianen af g for coins samme dag i samme HAR-decil, som **også er komprimerede** og ikke havde hændelse de seneste 14 dage (mindst 5, ellers udgår hændelsen, tælles). **Det isolerer udbruddet fra ren volatilitets-tilbagevenden efter kompression.**
- **CB1_DIR (retning):** indgang ved første timelukke ≥ 1 t efter dagens lukke, hold 72 t. Netto = s · ln(exit/entry) − omkostning. Ingen stop. Indgår i dommen; se dom nedenfor.
- **Test:** ensidet t på UTC-døgnklyngers middel, H0 ≤ 0, α_F 0,0125. **OI:** kun sekundært og beskrivende på train3/validation3 (OI findes kun dér, se afsnit 8).

**Overlap (ingen af det er "nyt"):**

| Kilde | Forhold |
|---|---|
| L14 tsmom_v1, L03 sol_trend_hourly, tsmom_v2, Donchian (ikke kørt, INSUFFICIENT POWER) | Samme slægt `cross_sectional_momentum` (trend_following, time_series_momentum). CB1 bruger dagsbarer og hændelser |
| E_oi_confirmed_return_p3, E_oi_growth_p3, E_leverage_cycle_p3 | OI + kurs, ugentligt tværsnit. CB1 bruger OI kun beskrivende |
| high_volume_return_premium (E_xs_high_volume_p2, illiquidity) | Volumen → afkast. CB1 er hændelsesbetinget |
| C4 (ændring 33) | Volumen **uden** kurs → volatilitet. CB1 kræver netop kursbruddet; udelukker hinanden, deler census-rækker |
| FACTORY F2 | HAR-prognose er null-modellen her. F2's mekanismegrænse: "alle modeller, der forudsiger RV ud fra fortidig RV". CB1_VOL tilføjer udbrud og volumen, som FUNDFRAG1 tilføjede funding; **placering er et åbent punkt** |
| VB1, FUNDFRAG1, C3 | Volatilitetsbrud som exit-regel (HL), funding → volatilitet, halebredde. Andre udløsere og data |
| K3, K1/K2 | Ingen fælles statistik; CB1 læser ikke K3's rækker |

**Tidligere eksponering:** census-rækkerne er set i drift (kun antal); de bruges først efter låsen (G05). `explore0` har ikke dette regelsæt. Litteraturen om breakout er kendt (Hudson & Urquhart 2021 positivt, men ingen forudsigelighed i BTC uden for stikprøven; Bajgrowicz & Scaillet 2012 negativt).

**Data:** census/1 (hourly mark og 24 t-ticker). Ingen ny kilde. Sekundært metrics-arkivet (train3/validation3). G19: der findes ingen fremadrettet 1 t-kline-stream, derfor bruges census.

**Omkostninger (CB1_DIR):** 2 × 5 bp + bog ca. 6 bp + funding ca. 15 bp over 3 døgn = 31 bp (ANTAGELSE); gulv 46 bp. CB1_VOL handler ikke og har ingen omkostning; en senere risikoregel skal have sin egen protokol.

**Styrke (ANTAGELSER, afsnit 9):** CB1_VOL: sd 0,25, 180 hændelsesdøgn pr. 12 mdr., MDE 0,057 log (5,9 % mere volatilitet), plausibel 0,08, styrke 0,98 ved plausibel. CB1_DIR: sd 4,0 %, MDE 0,92 % netto pr. 3 døgn, plausibel 0,14 %, styrke 0,04; bruttoeffekt krævet ca. 123 bp.

**Stopkriterier før resultatadgang:** < 40 klynger ved fristen → UNTESTABLE; dækning < 90 % af census-timer → INVALID; ingen mellemkig (kun antal); udfald sættes ikke, hvis en mønt mangler timer (tælles). Ingen ændring af fraktil, kanal, volumenfaktor, horisont, efter låsen.

**Uafhængig validering:** afsnit 0. Vindue efter låsen; hændelser først efter 90 dages opvarmning inde i vinduet (planlægningsdato 2026-12-07, hændelser fra 2027-03-07 til 2028-03-05, ANTAGELSE). Dom tidligst 2028-03-09. Replikation i nyt vindue kræves for mere end "målt én gang". Kontrolkrav: de kontrolgrupper, der indgår i y, er samme census-dag, så markedsvolatilitet går ud.

**Dom:** CB1_VOL **OVERLEVER_BESKRIVENDE**. CB1_DIR **AFVIST** på EFFECT_REACHABLE; den køres ikke. Hvis plausibel nettoeffekt reelt var ≥ 0,92 %, skulle en ny, dateret lås gøre det.

---

## 2. PR1: premium-henfald over en fundingperiode, likvide mod tynde perps (P1)

**Det, en chartlæser ser:** perpen handler over index; funding bider, og premium løber ind igen, men langsommere, hvor markedet er tyndt.

**Økonomisk forklaring.** Funding overfører penge fra den ene side til den anden, indtil prisen er bragt tilbage (Ackerer m.fl.; He m.fl.). Hvor stærkt det sker, afhænger af arbitragekapital. Tilbagevenden er stærkest, hvor kapitalen er rigelig (BTC, ETH), og svagest i tynde perps. Taberne er carry-indtrædere, der ekstrapolerer et premium eller tror, det er nemt at høste i tynde perps. Det forsvinder ikke, fordi det er kontraktens konstruktion plus begrænset kapital: det er ingen anomali og kan ikke handles væk.

**Faste regler.** Rækker: census timevis, p = ln(mark/index). Hændelse: |p_t| ≥ 10 bp i to på hinanden følgende timer med samme fortegn (filter mod enkeltobservationsstøj), højst én pr. mønt pr. 8 t. D = andelen af premium væk efter 8 t: D = (|p_t| − sign(p_t)·p_t+8)/|p_t|. Pr. UTC-døgn: terciler af hændelsernes 24 t-volumen (≥ 1 mio. USD); y = middel D (øverste tercil) − middel D (nederste tercil), mindst 3 hændelser pr. side.
- **Test:** ensidet t for y > 0, α_F 0,0125, og middel D (likvid) ≥ 0,5, ellers INCONCLUSIVE. FALSIFIED hvis ȳ ≤ 0.
- **Værdien 10 bp er design:** dobbelt clamp-bredde (±5 bp, Binance-formlen er UNVERIFIED her). 8 t = én standard-fundingperiode.

**Overlap:** samme slægt `cross_venue_perp_gap` (tag `perp_premium_convergence`).

| Kilde | Forhold |
|---|---|
| M3 (L22) | Handelstest på BTC, premium ≥ 5-20 bp: konvergens reel inden for 6-75 min, men +0,6 til +2,4 bp brutto mod 34 bp. **Handlen er afvist** |
| SPOTPERP_m21i | Spot fører perp med 1 t: ikke handelbart |
| HFC-1, CARRY90, fcarry | Funding-persistens og carry. PR1 måler premium, ikke funding |
| He m.fl. 2022 | Afvigelser falder over tid. Arbitragens Sharpe falder kraftigt med omkostninger (afsnit 13) |

PR1 er derfor **ikke** et bevis på profit og ikke en "ny" uafhængig opdagelse. Det nye er kun tværsnittet likvid mod tynd på en fundingperiode. M3 har allerede vist fortegnet på BTC.

**Tilvalgt arbitrage-regnestykke (hvorfor handlen er død):** en premium på 10-50 bp giver højst 10-50 bp bruttokonvergens. To ben koster mindst 34 bp (M3) og ofte 48 bp. Selv ved D = 1 skal premium være over ca. 50 bp i en tynd perp, hvor bogens rundtur også er højere.

**Data:** census/1. Ingen ny datalinje; ingen `premiumIndexKlines`. Fremad kun: historisk minutpremium er ikke godkendt.

**Omkostninger:** ingen (måling uden ordrer). Ingen handelspåstand.

**Styrke:** sd 0,25, 170 døgn, MDE 0,059 for y; plausibel 0,10 (ingen kildetal; ANTAGELSE), styrke > 0,99 ved plausibel.

**Stopkriterier:** < 40 døgn → UNTESTABLE; dækning < 90 % → INVALID; ingen ændring af 10 bp, 8 t eller tercilerne.

**Uafhængig validering:** afsnit 0. Vindue 2026-12-07..2027-06-05 (ANTAGELSE), dom tidligst 2027-06-07.

**Dom:** PR1 **OVERLEVER_BESKRIVENDE**. Forhåndssandsynlighed for PASS ca. 50 % (ANTAGELSE). Selv ved PASS er informationsværdien begrænset: tilbagevenden er indbygget i kontrakten, og resultatet bruges kun til at dæmpe forventninger til carry-entréer i tynde perps.

---

## 3. LD1: kursledt mod likviditetsledt bogforstyrrelse (P2)

**Økonomisk forklaring.** Efter et informationschok er modparterne informerede, og likviditet vender langsomt (lageromkostning, adverse selection). Et rent likviditetsbrud uden kursbevægelse bør normaliseres hurtigere. Taberne er market takers, der krydser under normaliseringen.

**Faste regler.** Hændelser som LQ1 (RT_t ≥ 3 × baseline, 12 markeder, samme rækker). Kursledt hvis |z_1h| ≥ 3, likviditetsledt hvis |z_1h| < 2. S = ½(RT_t − RT_t+1). Kontrast: middel S (likviditetsledt) − middel S (kursledt).

**Overlap:** samme rækker og hændelser som **LQ1** (registreret som beslægtet med LIQREC1). Inden for **LIQREC1's mekanismegrænse** ("enhver måling af spread- eller dybdegenopretning efter stress ... er samme mekanisme"). `maker_adverse_selection_measurement` er ikke i snapshot-lineage-kortet (ingen ledger-række). `orderflow_imbalance` og taker_pressure er REJECTED (retning, ikke omkostning).

**Styrke:** LQ1's 60 klynger delt 24/36 giver n_eff 14,4; sd 10 bp; MDE 8,1 bp (plausibel 3 bp, ANTAGELSE); styrke 0,14.

**Dom:** LD1 **AFVIST** (DISTINCT, EFFECT_REACHABLE). Regnes ikke som selvstændig hypotese. Hvis LQ1 en dag låses, kan fordelingen rapporteres som beskrivende sekundær analyse, uden egen test.

---

## 4. FL1: 4σ-fald med OI-flush, hold 24 t (P2)

**Økonomisk forklaring.** Tvunget salg overskyder, og likviditetsudbydere får betaling for at købe (Brunnermeier & Pedersen 2009, Nagel 2012). OI-faldet skal skille tvangssalg fra informeret salg. Taberne er likviderede longs.

**Faste regler (kun for at gøre afvisningen præcis).** 1 t-afkast ≤ −4 × sd af de foregående 720 timer (mindst 600). OI-fald i samme time ≤ −2 %. Højst én hændelse pr. mønt pr. 6 t. Long fra næste times lukke, hold 24 t. BTC-hedge som sekundær. Univers 30v3, der hvor metrics findes (train3 og validation3).

**Overlap:**

| Kilde | Forhold |
|---|---|
| **M2 (L21)** | Testede netop OI-fald ≥ 0,5-2 % og kursbevægelse. Alle 18 varianter netto negative. Hold ≥ 60 min gav **negativ brutto**. FL1 er samme mekanisme med længere holdeperiode |
| m21c / DROP4S | 4σ-fald set **efter** data i explore0 (+3,9 % på hændelsesniveau, +1,6 % på klyngeniveau; bullmarked). Kan ikke screenes rent i explore0 |
| m21h, daily_reversal | Reversal efter store bevægelser, SCREEN_FAIL / REJECTED |
| Straks-bogen | Handler flag på de 12 markeder |
| Nagel 2012, L17 Hyperliquid | Likviditetspræmien tilfalder makers, ikke takers |

**Omkostninger:** 2 × 5 bp + stresset bog ca. 30 bp = 40 bp (ANTAGELSE). Screeningsgulv 46 bp.

**Styrke:** sd 5 %, 45 hændelsesdøgn på train3 ∪ validation3, MDE 2,30 % netto (ved α 0,0016 som 21c's note kræver: 2,82 %). Plausibel net 0,20 %, styrke 0,02. Brutto krævet ca. 270 bp.

**Stop og validering:** ingen fremadrettet OI: metrics efter låsen kræver data.binance.vision, som er DNS-blokeret lokalt (ordre 61; omgås ikke), og OI fra fapi er en ny, ugodkendt datalinje. Historiske vinduer er ikke uafhængige.

**Dom:** FL1 **AFVIST** (DISTINCT, VALIDATION_PLAN, EFFECT_REACHABLE). Skal ikke genoplives uden ny dateret begrundelse og fremadrettet OI-kilde.

---

## 5. TS1: US-session i højvol-regime (P3, betinget)

**Økonomisk forklaring (svag).** ETF-flow og US-handelstid kunne samle købspres i 13:00-20:00 UTC, når volatiliteten er høj. Taberne er uklare.

**Faste regler (kun for at gøre afvisningen præcis).** BTCUSDT-perp. Session 13:00-20:00 UTC. Regime ON, hvis variansen af de 24 timer før 13:00 er ≥ medianen af samme mål over de 30 foregående døgn, fastlagt ved 13:00. Lang i sessionen, netto én rundtur.

**Overlap:** `hour_of_day_p1`, `day_of_week_p1` og `turn_of_month_p2` er afvist. K1/K2 er weekend-omkostning. K3 ejer funding-urene, og TS1 må ikke læse K3-rækker. Baur m.fl. 2019: tidsbestemte afkast "don't persist".

**Data:** census; men det relevante regime (spot-ETF fra 2024) ligger i forseglede vinduer (2024 og 2025+). Altså kan mekanismen ikke testes historisk.

**Styrke:** BTC-session sd 1,36 % (50 % årlig volatilitet, 7 t), 125 ON-sessioner pr. år, MDE 0,375 %, krævet brutto ca. 48 bp mod et bruttoskøn på 4 bp (ANTAGELSE). Omkostning 11 bp.

**Dom:** TS1 **AFVIST** (MECHANISM, DISTINCT, EFFECT_REACHABLE). "Betinget" tilføjer gafler, ikke en mekanisme.

---

## 6. Falsifikationsmatrix (format som ordre 61)

| Hypotese | Primært endepunkt | Kill-regel | Data til rådighed? | Godkendelser | Tidligste dom | Anbefaling |
|---|---|---|---|---|---|---|
| **CB1_VOL** | ȳ = middel af g − median(g matchede, komprimerede kontroller), døgnklynger | ȳ ≤ 0 → FALSIFIED; < 40 klynger → UNTESTABLE; dækning < 90 % → INVALID | Ja (census). Opvarmning 90 d efter låsen | lås + dateret ejer-ja; D5 for VERIFIED; α = 0 | 2028-03-09 (ANTAGELSE) | **2. Betinget GO, beskrivende.** Afhænger af antagelsen om klynger og sd |
| **CB1_DIR** | netto 3 d-afkast med udbruddet | – | Data ok; effekt uden for rækkevidde | – | – | **NO-GO** (EFFECT_REACHABLE) |
| **PR1** | ȳ = D(likvid) − D(tynd), krav D(likvid) ≥ 0,5 | ȳ ≤ 0 → FALSIFIED; < 40 døgn → UNTESTABLE; < 90 % → INVALID | Ja (census), ingen ny stream | lås + dateret ejer-ja; α = 0 | 2027-06-07 (ANTAGELSE) | **1. Betinget GO, beskrivende.** Billigst; ingen handelspåstand |
| **LD1** | S(likviditetsledt) − S(kursledt) | – | Ja, LQ1's rækker | – | – | **NO-GO** som selvstændig; sekundært under LQ1 |
| **FL1** | 24 t netto efter OI-flush | – | Delvis: historik cachet, fremad blokeret | – | – | **NO-GO** |
| **TS1** | netto US-session i højvol-regime | – | Census; regimet er forseglet | – | – | **NO-GO** |

## 7. Overlap-audit (samlet)

**Ingen af de fem er en ny, uafhængig opdagelse.** Hver har en lineage i snapshot v1 (eller er markeret, hvor den mangler):

| Design | Lineage (snapshot) | Status | Nærmeste afviste / beslægtede |
|---|---|---|---|
| CB1 | `cross_sectional_momentum` (10 varianter) | IN_SNAPSHOT | L14 tsmom_v1, L03, E_oi_*; relateret `betting_against_beta` (F2) |
| PR1 | `cross_venue_perp_gap` (26) | IN_SNAPSHOT | M3 (L22), fcarry, HFC-1 |
| LD1 | `maker_adverse_selection_measurement` | NOT_IN_SNAPSHOT (ingen ledger-række) | LIQREC1, LQ1 |
| FL1 | `liquidation_cascade_reversal` (5) | IN_SNAPSHOT | M2 (L21), m21c, DROP4S |
| TS1 | `calendar_day_of_week` (6) | IN_SNAPSHOT | hour_of_day, day_of_week, turn_of_month |

V2-poster (i kode, ikke persisteret): `fapi_designs_76b.v2_record(did)`. Alle er FUTURE, `variants_tested` er `MISSING_INPUT` (afventer kørsel), `data_quality` er `NOT_CHECKED`, `deviations` er `[]`, `register_snapshot` peger på SNAPSHOT_v1. `independent_discovery_claim` er falsk.

## 8. Datakildeafhængigheder

| Kilde | Status | Bruges af |
|---|---|---|
| `census/1` (bn_census), timevis, alle perps | EXISTING_ACTIVE, kun efter låsen (G05) | CB1, PR1, TS1 |
| `abnormal_move/1` (book_rt, 12 markeder) | EXISTING_ACTIVE | LD1 (som LQ1) |
| 1 t-klines, funding: data.binance.vision-arkiv | Cachet (G01: fra 14/11); vinduer som afsnit 0 | FL1 |
| metrics/OI (5 min), 30 mønter | Cachet, kun train3/validation3 | FL1, CB1 sekundært |
| metrics efter låsen | **Blokeret:** data.binance.vision er DNS-blokeret lokalt (ordre 61); omgås ikke | FL1 (validering) |
| OI-endepunkt på fapi | **Ikke godkendt** (ny datalinje) | – |
| `premiumIndexKlines`, `markPriceKlines` | **Ikke godkendt.** Kun set i `research/m3.py` for BTC | – |
| Likvidationsfeed | **Ikke godkendt.** Giagkiozis & Said 2024: OI og forced trades er upålidelige på tværs af børser | – |
| 1 t-klines fremad | Ingen godkendt stream (G19) | – |

## 9. Power og omkostninger

MDE ved 80 % styrke, ensidet. Alle sd, n og plausible effekter er ANTAGELSER (`fapi_power_76b.ENDPOINTS`). Registerbaren er Bonferroni ved N = 19.438 + K, diagnostik.

| Endepunkt | Enhed | sd | n (n_power) | MDE α_F 0,0125 | MDE registerbar | Plausibel netto | Styrke ved plausibel | Brutto krævet (realistisk omk.) |
|---|---|---|---|---|---|---|---|---|
| CB1_VOL | log | 0,25 | 180 | 0,057 | 0,101 | 0,08 | 0,98 | – |
| CB1_DIR | netto/3 d | 4,0 % | 180 | 0,92 % | 1,61 % | 0,14 % | 0,04 | 123 bp |
| PR1 | andel | 0,25 | 170 | 0,059 | 0,104 | 0,10 | 1,00 | – |
| LD1 | bp/side | 10 | 60 (14,4) | 8,1 bp | 14,2 bp | 3 bp | 0,14 | – |
| FL1 | netto/24 t | 5,0 % | 45 | 2,30 % | 4,03 % | 0,20 % | 0,02 | 270 bp |
| TS1 | netto/session | 1,36 % | 125 | 0,375 % | 0,66 % | −0,07 % | 0,00 | 48 bp |

**Følsomhed (MDE ved α_F, ANTAGELSE):**

| CB1_VOL sd \ n | 60 | 120 | 180 |
|---|---|---|---|
| 0,20 | 0,080 | 0,056 | 0,046 |
| 0,25 | 0,100 | 0,070 | 0,057 |
| 0,35 | 0,139 | 0,099 | 0,080 |

| PR1 sd \ n | 85 | 170 | 340 |
|---|---|---|---|
| 0,15 | 0,050 | 0,036 | 0,025 |
| 0,25 | 0,084 | 0,059 | 0,042 |
| 0,35 | 0,117 | 0,083 | 0,059 |

CB1_VOL består gaten ved sd 0,20 uanset n, ved sd 0,25 fra n ≈ 120, og ved sd 0,35 ikke (MDE 0,0804 ved n = 180, tabellen afrunder). Ved 60 klynger og sd ≥ 0,25 falder den. Monte Carlo (`sim_power`): styrke 0,81 ved MDE (CB1_DIR, normal), 0,83 ved t(3); størrelse under H0 0,011.

**Omkostninger samlet:** CB1_DIR 31 bp (realistisk), 46 bp (gulv). FL1 40 bp. TS1 11 bp. PR1 og CB1_VOL handler ikke. `check_costs` giver FAIL på CB1_DIR (45 bp brutto mod gulv 46 bp) og TS1 (4 bp); FL1 giver INCONCLUSIVE (60 bp brutto, overlever ikke 2 × stress). Samlet `assess_design`: CB1 og TS1 FAIL (omkostningstjek), PR1, LD1 og FL1 MISSING_INPUT; ingen PASS, som det skal være før data.

## 10. Skitser, der aldrig blev fulde designs (tæller ikke som hypoteser)

| Skitse | Afvist fordi |
|---|---|
| Premium-konvergens som handel | M3: +0,6-2,4 bp brutto mod 34 bp; aritmetik |
| Funding → volatilitet | FUNDFRAG1's mekanismegrænse |
| Regimegated carry | fregime blokeret af ændring 8 punkt 3 |
| Funding-kontrarian, tværsnits-funding | E_funding_contrarian REJECTED, m21h SCREEN_FAIL, E42 |
| Vol-styret BTC-eksponering | E_vol_managed_long p1/p2 REJECTED; L04-L06 |
| Dybdegenopretning efter stress | LIQREC1 parkeret (INSUFFICIENT_POWER) |
| Perp/spot lead-lag | m21i SCREEN_FAIL; minutdata fremad findes ikke |
| Likviditetsforsyning i stress | Ingen ko-data, maker-fyld kan ikke papirsimuleres (K12, X025) |
| Ren kalendereffekt | REJECTED |

## 11. PRIORITERET anbefaling

1. **PR1** beskrivende (α = 0), hvis direktøren vil have en måling på funding-mekanismen. Billigst, hurtigst, ingen ny stream. Forvent lav informationsværdi.
2. **CB1_VOL** beskrivende (α = 0), kun hvis direktøren accepterer, at dommen ligger i 2028, og F2's mekanismegrænse afklares. Den tætteste chartkobling og det mest usikre udfald.
3. **CB1_DIR, FL1, LD1, TS1: NO-GO.** Ingen af dem bør køres eller varieres. Afvisningen er gyldigt resultat og lukker disse veje for nu.
4. **Ingen af de fem kan bære en strategi** med de data, der er godkendt nu. Det samlede resultat er i tråd med `PROFIT_SEARCH_2026-11-09`: ingen kandidat har både evidens og målbar nettomargin.

## 12. Åbne punkter

1. **F2's mekanismegrænse:** ligger CB1_VOL inden for? Jeg følger FUNDFRAG1-præcedensen, men det er direktørens afgørelse.
2. **Ægte hændelsesrater og sd** er ukendte. CB1's 180 klyngedøgn er et skøn. En tælling på train3 (kun antal) kræver, at den først låses, og G05 forbyder en tælling på census før låsen.
3. **Binance-formlen** (funding, clamp ±5 bp, mark-pris) er UNVERIFIED her; Binance-værter må ikke kaldes. Skal verificeres i dokumentationen før en lås. PR1's 10 bp kan ændres før lås, aldrig efter.
4. **Afnoteringer i census:** se afsnit 0. Survivorship-tjekket kræver news/1 eller `fwd_universe_versions`.
5. **Opvarmning i CB1** er 90 dage for at holde G05 (census før låsen tælles ikke). Det skubber dommen til 2028.
6. **OI fremad** findes ikke uden ny datalinje eller ophævet DNS-blokering. Alle designs med OI som primær kilde er dermed AFVIST indtil da.
7. **Lås og alfa:** lås kræver dateret ejer-ja (ordre 53), D5 for VERIFIED; W0 er optaget, derfor α = 0.

## 13. Kilder

**Lokale:** `ORIGINAL_DESIGNS_ORDER69.md`, `LITERATURE_REVIEW_ORDER69.md`, `FALSIFICATION_MATRIX_ORDER61.md`, `PROFIT_SEARCH_2026-11-09.md`, `EVIDENCE_REPORT_75.md`, `RESEARCH_EVIDENCE_ENGINE_75.md`, `REGISTER_SNAPSHOT_PROCEDURE_74.md`, `order69_power.py`, `research/tools/validation_engine.py`, `research/tools/register_v2.py`, `register_snapshots/SNAPSHOT_v1.json`, `protocols/FUNDFRAG1_v1.md`, `LIQREC1_v1.md`, `LIQPROXY1_v1.md`, `lq1/LQ1_PROTOCOL_DRAFT.md`, `FORWARD_DATA_PLAN.md`, `stream_registry.json`, `GATE_MATRIX.json`, `research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md`, `FUNDING_m21h.md`, `MOVESCREEN_m21c.md`, `SPOTPERP_m21i.md`, `DONCHIAN_POWER_P1_2026-11-06.md`, `research/MISSION3_FAST_SCREEN.md`, `research/PROTOCOL_V3.md` (§2, 10c, 21i, 22, 33), `research/families/drafts/fregime.json`, `research/data/factory/registry.md`, `lab/engine/catalogue.py`, `lab/engine/data.py`.

**Web (kun litteratur):**
- He, Manela, Ross & von Wachter, "Fundamentals of Perpetual Futures", arXiv 2212.06888. **VERIFIED** (HTML, tabel 4-5): gennemsnitlig afvigelse i annualiseret ρ fra 52 % (BTC) til 90 %; signeret middel før 2022 0,69 (BTC), efter 2022 0,17; arbitrage-Sharpe uden omkostninger 11,65 (BTC, tabel 5). Introduktionen angiver 3,35 med høje detailomkostninger (ikke verificeret mod tabel). Stikprøve 2020-01..2024-03. https://arxiv.org/abs/2212.06888
- Ackerer, Hugonnier & Jermann, "Perpetual Futures Pricing", arXiv 2310.11771. ABSTRACT. https://arxiv.org/abs/2310.11771
- Giagkiozis & Said, "Reconciling Open Interest with Traded Volume in Perpetual Swaps", Ledger 2024, arXiv 2310.14973. ABSTRACT: nogle børsers OI er upræcis, og forced trades kan forsinkes. https://arxiv.org/abs/2310.14973
- Bajgrowicz & Scaillet (2012), JFE 106(3). UNVERIFIED (søgeresumé af abstract): tekniske regler overlever ikke lave omkostninger. https://econpapers.repec.org/RePEc:eee:jfinec:v:106:y:2012:i:3:p:473-491
- Hudson & Urquhart (2021), Annals of OR 297. UNVERIFIED (søgeresumé): ca. 15.000 regler, profitabelt i krypto; ingen forudsigelighed i BTC uden for stikprøven. https://ideas.repec.org/a/spr/annopr/v297y2021i1d10.1007_s10479-019-03357-1.html
- Corsi (2009), J. Financial Econometrics 7(2). UNVERIFIED (søgeresumé). https://econpapers.repec.org/RePEc:oup:jfinec:v:7:y:2009:i:2:p:174-196
- Brunnermeier & Pedersen (2009), RFS 22(6). UNVERIFIED (søgeresumé). https://econpapers.repec.org/RePEc:cpr:ceprdp:6179
- Baur, Cahill, Godfrey & Liu (2019), FRL 31. UNVERIFIED (søgeresumé). https://econpapers.repec.org/RePEc:eee:finlet:v:31:y:2019:i:c:p:78-92
- Bessembinder & Seguin (1993), JFQA 28(1). UNVERIFIED (søgeresumé). https://econpapers.repec.org/RePEc:cup:jfinqa:v:28:y:1993:i:01:p:21-39_00
- Ingen peer-reviewed timestudie af OI-flush og reversal fundet i søgningen (kun branchekilder); intet er brugt som evidens.
