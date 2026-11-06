# Fra evidens til protokol: shortlist og højst tre udkast (direktørordre 51 P2, 2026-11-06)

**Kun udkast.** Intet er godkendt, ingen skabelon er godkendt, ingen alfa er opkrævet, og ingen markedsdata er hentet,
læst eller testet. Ingen netværkskald, ingen database. Skrevet ca. kl. 14:55 lokal (13:55 UTC) i dev-worktree ud fra
`LITERATURE_MAP.md`, `evidence_registry.json` (44 kilder), `mechanism_graph.json` (25 knuder), `research_gaps.md`,
`FORWARD_DATA_PLAN.md` + `stream_registry.json`, `families/VOCABULARY.json`, `studies/FACTORY_P2_PROTOCOLS_2026-11-06.md`,
`studies/FACTORY_INTEGRATION_P3_2026-11-06.md` afsnit 3 og lab'ets studie- og ændringstekster (filnavne relative til
`research/`). Styrketal fra `tools/p2_power.py`. Maskinlæsbar version: `desk/protocols/shortlist.json`.

**Resultat:** 30 kandidater vurderet (alle 25 graf-knuder og 5 supplerende). 22 er dækket af eksisterende familier
eller tests, 5 er fravalgt på styrke, data eller som infrastruktur, og 3 er skrevet som udkast:

| Rang | Udkast | Mekanisme (registry) | Primær estimand | Styrke ved plausibel effekt | MDE | Beslutning |
|---|---|---|---|---|---|---|
| 1 | [`LIQPROXY1`](protocols/LIQPROXY1_v1.md) | Abdi-Ranaldo fra dagsbarer sporer målte spreads (E17) | β ≈ partiel r for ΔAR → ΔS ud over ΔRV | **0,864** (r 0,15; 52 uger) | r 0,138 | **PROPOSED** |
| 2 | [`FUNDFRAG1`](protocols/FUNDFRAG1_v1.md) | trængsel ved høj funding → skrøbelighed (E04, E05, E16, E41) | matchet forskel i ln(RV 72 t / RV 168 t) | **0,863** (e 0,15; 270 døgn) | e 0,139 | **PROPOSED** |
| 3 | [`LIQREC1`](protocols/LIQREC1_v1.md) | spread hurtigt, dybde langsomt efter stress (E16) | ln-dybdeforhold D+7 mod placebo | 0,224 (e 0,67; 12 mdr.) | e 2,76 | **PARKED** |

Ingen af de tre er en handelsstrategi. To er målinger (omkostninger og likviditet), én er en risikoprognose. Det følger
direktørens instruks fra 06/11 (svar på ordre 49 P1: "brug ikke ventetiden på at opfinde flere strategier eller
forsøgsfamilier"); ordre 51 P2 beder om udkast, ikke aktivering. Begge PROPOSED-udkast afhænger af foreslåede strømme,
som ikke er godkendt, og de kan ikke begge finansieres af alfabudgettet sammen med F2 og F3 (afsnit 6).

## 1. Fremgangsmåde

1. **Dækning først.** For hver knude: er mekanismen registreret, testet eller afvist i lab'et (F1-F3, fcarry, fregime,
   dbasis, HFC-1, carry/carry90, M2, straks, parbog, N4/n6, H27-A/A2/M/B, Donchian, H-SPR-1/2, K1-K3, C1-C4, R1/R3,
   H4/H5/H5F/H5X/U1F/M1F, explore0-screeningerne og v1-v3-kataloget)? Er den det, står den som **fravalgt: dækket af X**,
   uanset score. Et andet lookback, en anden tærskel eller et nyt navn er ikke en ny mekanisme (FACTORY_P2's regel).
2. **Score 1-5** på syv kriterier (højere er bedre): E uafhængig evidens (fagfællebedømt/replikeret > ét WP >
   praktiker), M økonomisk mekanisme, D data inden for gates (5 eksisterende fremadstrøm, 4 foreslået strøm, 3 historik
   efter 11-14, kun til og med 2023, 2 COIN-M/ny vært, 1 ikke tilgængelig), P styrke ved plausibel effekt, C omkostning
   og kapacitet (5 = ingen handel), A afstand til afviste Copybot-hypoteser, I værdi af et negativt resultat. Scoren
   rangerer kun; den største rapporterede afkaststørrelse giver ingen point.
3. **Effektstørrelser** kun fra registret med id. Hvor registret siger UNKNOWN, står den plausible effekt som en
   antagelse, og styrke og MDE er beregnet ved den.
4. **Styrke** med `p2_power`: Sharpe-estimander med `sr_power`/`sr_needed` (daglige afkast, AR(1) 0,1, kurtosis 8 som
   F1); øvrige estimander med `sr_power(e, n_eff, per_year = 1, α)`, som er en ensidet test af et middel med
   standardiseret effekt e pr. uafhængig observation. Det er præcis det, `desk_factory.check_power` regner ud fra felterne
   `plausible_sr`, `n_planned` og `per_year`. n_eff som i `n_eff_overlap`/`dm_power`. α_F = 0,0125 ensidet, K = 1. Styrke
   < 0,8 ved den plausible effekt giver REDESIGN eller PARKED, aldrig GO.
5. **Datagates** (skrevet før design): kun fremadrettede strømme, der findes eller er foreslået i `stream_registry.json`;
   historik først fra 2026-11-14 og kun til og med 2023-12-31 (2024 er holdout, 2025-01-01 og frem er reserveret,
   PROTOCOL_V3 afsnit 2); COIN-M fra 2026-11-28; Upbit kun N4; forward-observationer siden 10-27 må ikke kalibrere eller
   vælge (direktøren 06/11).

## 2. Rangeringstabel over alle kandidater

Sorteret efter afgørelse og derefter score. "Dækket af" henviser til filer under `research/`.

| # | Kandidat (graf-knude) | Registry | Dækket af / lab-historik | E | M | D | P | C | A | I | Sum | Afgørelse og hvorfor |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C13 | liquidity_measurement_and_volume_quality | E17, E23 | ikke dækket: m21i brugte AR på 1 t-barer, kun beskrivende ("pålidelighed lav", `studies/SPOTPERP_m21i.md`) | 4 | 4 | 4 | 4 | 5 | 5 | 4 | **30** | **UDKAST LIQPROXY1, PROPOSED.** Forudsætning for enhver omkostningsbevidst historisk test fra 11-14 |
| C26 | funding_crowding_fragility (kombination, ikke en knude) | E04, E05, E16, E41 | ikke dækket: m21h testede retning (FAIL), C4 har volumen som udløser, n6 den modsatte retning | 2 | 4 | 4 | 4 | 5 | 3 | 4 | **26** | **UDKAST FUNDFRAG1, PROPOSED.** Direkte relevant for HFC-1's kohorter |
| C12 | post_cascade_liquidity_recovery | E16, E04, E03 | ikke dækket: R1/costreport og straks-fyld måler kun samme time | 3 | 4 | 4 | 1 | 5 | 4 | 3 | **24** | **UDKAST LIQREC1, PARKED:** ca. 6 hændelser/år → styrke 0,22; 26 hændelser kræves |
| C16 | survivorship_and_selection_bias | E22, E01, E23 | `studies/FACTORY_SECURITY_P1_2026-11-06.md` (PIT-regel), strøm fwd_universe_versions | 3 | 3 | 4 | 1 | 5 | 5 | 3 | 24 | **Fravalgt: infrastruktur.** En dataegenskab, ikke en hypotese; bruges som PIT-regel i alle tre udkast |
| C30 | deviation_decay_trend (E03: −11 %/år) | E03 | premium-watch-medianer, ændring 21w (fordelsmonitor) | 2 | 3 | 5 | 1 | 5 | 3 | 1 | 20 | **Fravalgt: styrke.** En trend på 11 %/år kan ikke skilles fra regimestøj på under flere år |
| C17 | exchange_flow_pressure | E24, E25 | strøm onchain_flows (BTC/ETH, ingen låst forbruger), `drafts/ONCHAIN_KILDEAUDIT_2026-10-24.md`, NEXT_MECHANISMS G (nabo) | 3 | 3 | 4 | 1 | 3 | 2 | 2 | 18 | **Fravalgt: styrke.** 2 aktiver dagligt: styrke 0,11 ved r 0,05 på 12 mdr., MDE r 0,154 |
| C04 | cross_sectional_funding_factor | E42 | `studies/ONLINE_EDGES_2026-11-05.md` §5 (kun hypotese), m21h | 1 | 3 | 5 | 1 | 3 | 2 | 2 | 17 | **Fravalgt: styrke.** Kun praktiker (PBO 0,81); ved E42's OOS-netto SR 0,39 er styrken 0,03 på 12 mdr. (MDE SR 3,49; 24 mdr. 2,44); ikke afdækket i samme aktiv (ændring 8 pkt. 2) |
| C14 | orderflow_and_clock_time_imbalance | E19, E18 | L20 (PROTOCOL_V3 afsnit 6), v3 idé 8 taker_pressure (REJECTED), ændring 21k R4, ONLINE_EDGES §7 | 2 | 3 | 2 | 3 | 1 | 1 | 2 | 14 | **Fravalgt: data og omkostning.** Ingen aggTrades-strøm findes eller er foreslået; en 4–12 t-handel skal over 21i's gulv (~46 bp rundtur); E19 er ureplikeret (07-2026); naboer afvist tre gange |
| C20 | option_informed_flow | E28 | – | 2 | 3 | 1 | 1 | 1 | 4 | 1 | 13 | **Fravalgt: data** (ingen optionshandler inden for gates) |
| C24 | realised_volatility_forecast_HAR | E36, E37, E38, E44 | F2 (CONDITIONAL, `studies/FACTORY_P2_PROTOCOLS_2026-11-06.md`), ordre 51 P1 C1-journal | 5 | 4 | 5 | 3 | 5 | 4 | 3 | 29 | **Dækket af F2 + C1.** F2's mekanismegrænse omfatter spring- og semivarians-HAR (E38) |
| C02 | funding_persistence_forecast | E40, E42 | HFC-1 (3 d/14 d-udfald 11-08 og 12-09), CARRY_ECON_DAILY (persistens), n6/H27-F (`studies/MISSION27_3_2026-11-02.md` 6b, lås 11-14, kontrol for M_t), fregime (BLOCKED), M2_FORWARD_LEDGER | 2 | 4 | 5 | 3 | 5 | 3 | 3 | 25 | **Dækket.** En fjerde måling af samme størrelse på samme census-data ville være en omdøbning; tages først op efter HFC-1's 14 d-rapport og n6 |
| C25 | volatility_regimes | E39, E27 | F2's mekanismegrænse (GARCH-familien, regimemodeller), C3 (ændring 28a) | 3 | 3 | 5 | 2 | 5 | 3 | 2 | 23 | **Dækket af F2/C3.** Også VaR-backtest af regime-GARCH er samme slægt |
| C06 | dated_futures_basis_carry | E04, E06 | F3 (DEFERRED til 11-28), `families/drafts/dbasis.json`, carry90 (ændring 42), `studies/CARRY_BASIS_PLAN.md`, n6 X3 | 3 | 5 | 2 | 3 | 3 | 3 | 3 | 22 | **Dækket af F3/dbasis/carry90** |
| C05 | perp_spot_deviation_convergence | E03, E07, E06 | perp_premium_convergence (L22), ændring 12/12a, `studies/PREMIUM_BANER_REKONSTRUKTION_2026-10-25.md`, K3 (ændring 22), m21i | 3 | 5 | 5 | 3 | 2 | 1 | 2 | 21 | **Dækket.** Præmiebanerne blev ædt af bogdybden; E03 er den stærkeste omkostningsjusterede kilde, men lab'et har testet den |
| C21 | cross_venue_premium_capital_controls | E30–E33 | N4 (`studies/MISSION27_4_2026-11-02.md`, `studies/READINESS_2026-11-14.md`, lås 11-14), U1F (17i) | 5 | 4 | 3 | 3 | 1 | 2 | 3 | 21 | **Dækket af N4/U1F** |
| C01 | funding_carry_level | E04, E05, E08, E42, E03 | fcarry (`families/fcarry.json`, fremad fra 12-01), `RESULTS_carry_v1.md` FAIL, lane-carry + M2, HFC-1, CARRY_ECON_DAILY, carry90, CARRY_REALISM | 3 | 4 | 5 | 2 | 2 | 1 | 2 | 19 | **Dækket.** Aftagende niveau (E08: Sharpe 4,06 fra 2024, negativ 2025) stemmer med carry_v1 |
| C28 | perp_vs_dated_contract_design | E06, E04 | F3, dbasis | 2 | 4 | 2 | 2 | 3 | 3 | 2 | 18 | **Dækket af F3** (kræver COIN-M) |
| C08 | time_series_momentum | E09, E12, E43 | `RESULTS_tsmom_v1.md` FAIL, `TSMOM_V2_PROPOSAL.md` stoppet, `studies/DONCHIAN_POWER_P1_2026-11-06.md` INSUFFICIENT POWER, straks-FØLG (ændring 41) | 4 | 3 | 3 | 1 | 3 | 1 | 2 | 17 | **Dækket.** Styrken fejler i lab'et (Donchian MDE ΔSR 1,68–2,33 på 24 mdr.) |
| C15 | listing_announcement_return | E20, E21 | H4, H5, H5F, H5X, 17f/17g/17h, U1F, M1F; NEXT_MECHANISMS H (hastighed) | 3 | 3 | 5 | 2 | 1 | 1 | 2 | 17 | **Dækket** af de låste fremadtests |
| C29 | listing_incentive_conflicts | E21 | H5F, M1F | 2 | 3 | 5 | 1 | 2 | 2 | 2 | 17 | **Dækket** (samme slægt; ingen data om børsernes investeringer) |
| C22 | settlement_latency_arbitrage_bounds | E34, E30 | `RESULTS_arb_v1.md` REJECTED, ændring 13a (perp-perp tabte), cross_venue_perp_gap-scanneren | 3 | 4 | 3 | 2 | 1 | 1 | 1 | 15 | **Dækket og afvist** |
| C09 | cross_sectional_momentum | E10, E11, E13, E01, E22 | v2-kataloget (8 af 9 fejlede, ONLINE_EDGES §0) | 4 | 2 | 3 | 1 | 2 | 1 | 1 | 14 | **Dækket.** E22: præmien forsvinder efter overlevelseskorrektion |
| C11 | short_term_reversal_illiquid | E14, E15 | `studies/MOVESCREEN_m21c.md` FAIL, straks-MOD, parbog (ændring 43), F1 PARKED | 4 | 3 | 3 | 1 | 1 | 1 | 1 | 14 | **Dækket.** Effekten sidder i illikvide mønter uden kapacitet |
| C23 | derivatives_lead_spot | E35 | m21i spot_lead FAIL, NEXT_MECHANISMS mønster 1 | 3 | 3 | 3 | 2 | 1 | 1 | 1 | 14 | **Dækket.** Minutniveau er et hastighedskapløb |
| C03 | funding_directional_signal | E41, E42 | `studies/FUNDING_m21h.md` FAIL | 1 | 2 | 5 | 1 | 2 | 1 | 1 | 13 | **Dækket og afvist** (prædiktiv R² ≈ 0) |
| C07 | basis_factor_cross_section | E02 | NEXT_MECHANISMS J (afvist) | 2 | 2 | 3 | 2 | 2 | 1 | 1 | 13 | **Dækket og afvist** |
| C10 | attention_forecast | E09 | `studies/NEWINFO_m21j.md` attention_shock FAIL | 3 | 2 | 2 | 1 | 3 | 1 | 1 | 13 | **Dækket og afvist** |
| C18 | stablecoin_flow_liquidity | E26, E24 | v3 idé 6 stablecoin_flow (afvist i katalog p3, `studies/SPOTPERP_m21i.md`), NEXT_MECHANISMS G | 3 | 2 | 2 | 1 | 3 | 1 | 1 | 13 | **Dækket og afvist** |
| C19 | variance_risk_premium | E27, E29, E44 | v3 idé 5 vrp_timing (afvist i katalog p3, `studies/SPOTPERP_m21i.md`), NEXT_MECHANISMS B | 2 | 4 | 2 | 1 | 1 | 1 | 2 | 13 | **Dækket.** Selv en ren måling med DVOL har styrke 0,30 på 12 mdr. (e 0,5; MDE 1,05); optioner NOT_AVAILABLE |
| C27 | anchoring_to_high (E15: afstand til 1-ugers top) | E15 | v2-kataloget "tæt på toppen" (ONLINE_EDGES §0) | 2 | 2 | 3 | 1 | 2 | 1 | 1 | 12 | **Dækket** |

Alle 44 registry-id'er er brugt mindst én gang, og alle 25 graf-knuder står i tabellen (tjekket i afsnit 8).

## 3. Sammenligning med familiehistorikken

- **Det, lab'et har lukket:** retningsbestemt prisforudsigelse på time- og dagsniveau (alle ti explore0-screeninger
  SCREEN_FAIL, `studies/SCREENINGER_OVERSIGT_2026-10-25.md`; v1-v3-kataloget; tsmom; Donchian med utilstrækkelig styrke;
  m21h for funding som retning), kryds-venue- og DEX-arbitrage (arb_v1, ændring 13a), præmiekonvergens (præmiebanerne)
  og kopiering af wallets. Litteraturen peger samme vej: kun 4 af 44 kilder rapporterer noget efter omkostninger, og
  ingen fagfællebedømt kilde viser en nettofordel efter 2022 i et likvidt univers (`LITERATURE_MAP.md`).
- **Det, der kører eller er låst:** carry i flere former (fcarry fra 12-01, HFC-1, M2, carry90, CARRY_ECON), F2
  (betinget), F3 (fra 11-28), n6 og N4 (lås 11-14), K1-K3, R3, C1-C4, H27-A/A2/M/B, H5F/H5X/U1F/M1F, straks og parbogen
  (kun diagnostik), H-SPR-1/2.
- **Hvor de nye udkast ligger:** LIQPROXY1 og LIQREC1 ligger i omkostningsmålingens spor (H-SPR, R1, capacity/1), som
  P4-notatet og MISSION27 (H27-F, H27-I) kaldte afgørende for alt andet, men som aldrig har haft en bekræftende test.
  FUNDFRAG1 ligger i carry-sporets risikoside: den bruger samme udløser som m21h og HFC-1, men et udfald (retningsløs
  volatilitet, matchet på egen volatilitet), som ingen test i lab'et har haft. Ingen af de tre genbruger en afvist
  mekanisme under nyt navn; slægterne og mekanismegrænserne står i hvert udkast.

## 4. De tre udkast

### 1. LIQPROXY1 (PROPOSED)

- **Spørgsmål:** sporer Abdi-Ranaldo fra census' dagsværdier (24 t høj, lav, sidste kurs) ugentlige ændringer i den
  målte quoted spread pr. perp ud over ændringer i realiseret volatilitet?
- **Test:** pooled regression af normal-scores inden for ugen (mønt- og ugeeffekter fjernet), uge-klyngede SE, ensidet
  α_F 0,0125, K = 1. Falsifikator β̂ ≤ 0. Brugsregel: kun ved PASS og r̂ ≥ 0,10 må AR foreslås som omkostningsinput.
- **Data:** census (findes) + `fwd_tob_universe` og `fwd_spec_journal` (foreslåede). Vindue 52 uger fra planlægningsdatoen
  2026-12-07.
- **Styrke:** 0,864 ved partiel r 0,15 (antagelse; E17 UNKNOWN), N 250, ρ_c 0,1; MDE r 0,138. Følsom over for ρ_c
  (0,558 ved 0,2), som ikke kan kendes før data.

### 2. FUNDFRAG1 (PROPOSED)

- **Spørgsmål:** har perps med 72 t-funding ≥ 18,8 % p.a. højere fremadrettet volatilitet (72 t) end perps med normal
  funding i samme volatilitetsdecil samme dag?
- **Test:** ensidet t på døgnmidler af matchede forskelle i ln(RVf/RVt), Newey-West 3 lags, α_F 0,0125, K = 1.
  Falsifikator middel ≤ 0.
- **Data:** census (findes) + `fwd_spec_journal` (funding-interval; foreslået). Vindue 270 døgn fra 2026-12-07.
- **Styrke:** 0,863 ved e 0,15 pr. hændelse (antagelse; E04 UNKNOWN) og 5 hændelser/døgn (antagelse ud fra
  CARRY_ECON's antal); MDE e 0,139. 180 døgn er for lidt (0,685).

### 3. LIQREC1 (PARKED)

- **Spørgsmål:** er top-of-book-dybden 7 døgn efter en BTC-3σ-dag stadig under niveauet før (E16's andet regime)?
- **Styrke:** 0,224 ved e 0,67 (antagelse ud fra E16's −0,42..−0,24 for den største kaskade) og ca. 6 hændelser på 12
  mdr.; 26 hændelser kræves. Anbefalet i stedet: beskrivende sporing uden alfa, når `fwd_tob_universe` og
  `fwd_quality_monitor` kører.

## 5. De vigtigste fravalg

1. **Carry, funding-persistens og basis (C01, C02, C05, C06, C28):** den bedst dokumenterede gruppe i litteraturen
   (E03, E04, E05, E08), men lab'et har den dækket fra alle sider. En ny "persistens-protokol" ville måle det samme som
   HFC-1 og n6 på de samme census-data og være en omdøbning.
2. **Tværsnits-funding-faktoren (C04):** den foreslåede løsning på flaskehalsen "ingen spotpar" (ONLINE_EDGES §5). Den
   eneste kilde er en praktiker med PBO 0,81, og ved dens egen OOS-netto-Sharpe på 0,39 har en 12-måneders fremadtest
   styrke 0,03.
3. **Kvartersåbningens ordreubalance (C14):** ny og interessant (E19), men ureplikeret, uden indsamlede handelsdata og
   med en horisont, hvor lab'ets omkostningsgulv på ca. 46 bp pr. rundtur kræver en urealistisk stor effekt.
4. **On-chain-strømme og VRP (C17, C19, C20):** data findes kun for BTC og ETH (onchain/1) eller slet ikke (optioner);
   styrken er 0,11 og 0,30.
5. **Volatilitetsprognoser (C24, C25):** stærkest og mest konsistent evidens (E36-E39), men F2 og C1-journalen dækker den,
   og F2's mekanismegrænse er låst.

## 6. Alfabudget: der er ikke plads til det hele

Ændring 8's programformue W0 = 0,05; fcarry har reserveret 0,0125; **0,0375 tilbage = 3 familier**
(FACTORY_INTEGRATION_P3 afsnit 3). Hvis alt godkendes:

| Kræver α_F 0,0125 | F2 (CONDITIONAL) | F3 (DEFERRED) | LIQPROXY1 | FUNDFRAG1 | I alt |
|---|---|---|---|---|---|
| | 0,0125 | 0,0125 | 0,0125 | 0,0125 | **0,05 > 0,0375** |

Underskuddet er 0,0125. Ejeren må enten prioritere (højst tre af de fire) eller klassificere LIQPROXY1 som en måling uden
W0-træk, som H-SPR-1/2 (ingen handelspåstand, ingen papirbog). Det står ikke åbent for desk-fabrikken at afgøre. Ingen
alfa er opkrævet eller reserveret i dag; LIQREC1 er parkeret og gør ikke krav. Programstoppet i ændring 8 punkt 15 (3
familier i træk uden fremad-PASS) gælder fortsat.

## 7. Hvad der skal ske før aktivering (hver kræver sit eget ja)

1. Godkendelse og deploy af strømmene: `fwd_spec_journal` (begge udkast), `fwd_tob_universe` (LIQPROXY1),
   `fwd_universe_versions` (begge; ellers census' første forekomst). Deploy i tilladte vinduer (ikke K1/K2/K3) og ikke
   noget, der kan genstarte pm_lp-collectoren før 2026-11-27.
2. LIQPROXY1: et nyt VOCABULARY-tag (`liquidity_proxy_validation`), som ejeren ser ved godkendelsen.
3. Ejerens afgørelse om alfabudgettet (afsnit 6).
4. Ejerens verificerede signatur i desk-fabrikken (AWAITING_OWNER_APPROVAL → APPROVED) og frysning før vinduets start.
   Planlægningsdatoen 2026-12-07 flyttes, hvis noget af ovenstående kommer senere; vindueslængderne ændres ikke.

## 8. Kontrol (kun syntetisk, intet skrevet uden for de tre filer)

Udkastenes `protocol_fields` fra `shortlist.json` er kørt gennem `desk_factory.Desk` i hukommelsen med
evidensregistret og strømstatus fra `stream_registry.json`:

| Udkast | Tilstand efter `check_power` | Styrke | Ejergodkendelse uden signatur | Gates i dag |
|---|---|---|---|---|
| LIQPROXY1 | AWAITING_OWNER_APPROVAL | 0,864 | afvist (`approve` → False) | fwd_tob_universe, fwd_spec_journal, fwd_universe_versions ikke aktive |
| FUNDFRAG1 | AWAITING_OWNER_APPROVAL | 0,863 | afvist | fwd_spec_journal, fwd_universe_versions ikke aktive |
| LIQREC1 | PARKED (INSUFFICIENT_POWER 0,224 < 0,8) | 0,224 | – | fwd_tob_universe, fwd_spec_journal ikke aktive |

Ledgeren har 0 poster (intet er evalueret og intet opkrævet). Alle 25 graf-knuder og alle 44 registry-id'er er dækket
af `shortlist.json`.

## 9. Forbehold

- **De plausible effekter er antagelser** (registret har ingen tal for E04 og E17, og E16's tal gælder én ekstrem
  hændelse). Styrkeberegningerne viser, hvor følsomme konklusionerne er (ρ_c for LIQPROXY1, antal hændelser for
  FUNDFRAG1). Ingen effekt eller korrelation er kalibreret på lab'ets data.
- FUNDFRAG1's hændelsestal bygger på antal (ikke udfald) fra CARRY_ECON_DAILY; den eksponering står i udkastet.
  Iagttagelsen i ændring 33 (EPIC, MITO og HOT tabte på pludselige bevægelser) er en motivering, ikke evidens.
- C26 er en kombination af knuder (E04's påstand om crash efter høj carry, E16's kaskader, E41's samtidighed), ikke en
  knude i grafen; den er markeret som sådan.
- Scorerne er mine vurderinger ud fra de citerede filer; de kan ikke give PASS og ændrer ingen regel.
