# F2 — ændringsanalyse for AMB-02..AMB-11 (direktørordre 53 P0)

**Version `F2_AMB_PROPOSAL/1`, skrevet 2026-11-06 ca. 15:30 UTC (16:30 lokal). Status: FORSLAG. Intet er ændret,
låst, hentet eller aktiveret.**

- Den låste F2-tekst er uændret: `research/studies/FACTORY_P2_PROTOCOLS_2026-11-06.md`, afsnit F2 linje 78-123 og
  direktørens afgørelser linje 194-205. Fil-sha256 `6dd1ca82…ae5f43`, commit `b54cb3c`.
- Forslaget er skrevet uden at åbne markedsdata eller kline-cachen (G01 gælder til 2026-11-14 00:00 UTC). Der er
  ingen netværkskald og ingen historisk forespørgsel.
- Alle tidspunkter er regnet med kalenderaritmetik i `research/tools/f2_timeline.py`. Hvert forslag har en syntetisk
  test i `tests/test_research_f2_timeline.py`. Konkrete UTC-eksempler står i `research/desk/F2_TIMELINE_TESTS.md`,
  kalibreringsspecifikationen i `research/desk/F2_CALIBRATION_SPEC_DRAFT.md`.

**Klassifikation:**
- **PRÆCISERING:** forslaget er foreneligt med den låste ordlyd og ændrer ikke F2's identitet (model, benchmark,
  univers, målvariabel, QLIKE, primær test).
- **MATERIEL ÆNDRING:** forslaget ændrer målvariablen, kandidatens prognoser, testens styrkegrundlag eller en
  PROTOCOL_V3-regel. Det kræver en ny, versionsstyret protokol (F2 v2) og en separat dateret ejerbeslutning, før data.
- Er klassifikationen tvivlsom, står den som MATERIEL (fail-closed).

**Hovedresultater:**
1. Den eneste konvention, der giver input-cutoff < lås < målstart med en reel margin, er **B23**: 23 afkast pr. døgn
   med en embargotime 23:00-24:00. Den er en **MATERIEL ÆNDRING**, fordi den bogstavelige læsning ("summen af
   kvadrerede 1-times log-afkast pr. UTC-dag") er hele døgnets 24 afkast.
2. Den bogstavelige 24-afkastslæsning (A24) lækker ikke prisindhold, hvis grænse-closet er baren åbnet 23:00. Men
   closet er først endeligt præcis ved målstart, og samme close er både sidste input og målets første basis. Den har
   altså **ingen margin**. Læses "00:00-closet" som baren åbnet 00:00 i måldøgnet (L24), er det et **reelt
   look-ahead-læk**.
3. **Den låste styrketabel er overvurderet.** Med opvarmning inde i vinduet (PROTOCOL_V3 afsnit 2) har bekræftelsen
   334 måldøgn, ikke 730. Ved ρ_c 0,5 og e 0,10 falder styrken fra 0,92 til 0,66, og ved ρ_c 0,8 fra 0,79 til 0,51.
   Selv den låste tabel opfylder ikke F2's egen GO-betingelse (e 0,08 → styrke 0,785 < 0,8 ved ρ_c 0,5).
4. validation3 alene kan slet ikke bære HAR uden overført historik (184 < 395 døgn). En totrinsbekræftelse
   train3 → validation3 er derfor umulig for F2. Kun det samlede vindue 2022-01..2023-12 virker, og det vindue er
   ikke godkendt.

---

## 0. Låst tekst, der citeres (ordret)

- L96-98: "**Primær variant (K = 1):** RV_t = summen af kvadrerede 1-times log-afkast pr. UTC-dag. Kandidat: HAR-RV
  med RV over 1, 7 og 30 dage, OLS på de foregående 365 dage (rullende, point-in-time). Benchmark (fast): EWMA λ =
  0,94 på samme RV-serie. Prognose for RV_{t+1} lavet ved dagens slutning."
- L94: "En mønt uden fuld dækning udgår mekanisk; færre end 10 → UNTESTABLE."
- L100: "**Primær estimand:** gennemsnitlig forskel i QLIKE-tab d = L(benchmark) − L(HAR), puljet over mønt-dage."
- L102-103: "**Nulhypotese og test:** H0 E[d] ≤ 0; ensidet Diebold-Mariano med HAC (Newey-West, 5 lags) på den
  tværsnitsvægtede daglige middel-d; Holm K = 1, α 0,05."
- L105: "**Falsifikator:** gennemsnitlig d ≤ 0, eller HAR dårligere end benchmark i mere end halvdelen af mønterne."
- L107-109: "**Vindue:** kalibrering i explore0 (2020-03..2021-12, udforskning, ingen alfa, aldrig bevis) estimerer
  kun sd(d) og autokorrelationen. Bekræftelse sker i train3 ∪ validation3. Kalibreringen må ikke ændre model, univers
  eller benchmark."
- L119-121: "Udkastet bliver først klar til godkendelse, når explore0-kalibreringen (fra 14/11) viser, at e ≥ 0,08
  giver styrke ≥ 0,8 ved den målte tværsnitskorrelation. Ellers INSUFFICIENT POWER."
- L198-200 (direktøren): "**F2: CONDITIONAL.** Model, benchmark, univers, QLIKE og primær test er låst.
  explore0-kalibreringen må kun estimere effektstørrelse og varians. Bruges den til GO/NO-GO, er den
  udviklingsinformation og aldrig uafhængig validering. F2 kræver et separat godkendt evalueringsvindue og
  tilstrækkelig styrke."
- PROTOCOL_V3 afsnit 2 (L37-38): "**Opvarmning.** Signaler bruger kun data inden for det vindue, der evalueres. Der
  overføres ikke historik mellem vinduerne, så positioner starter først, når et signals tilbagekig er fyldt."
- PROTOCOL_V3 afsnit 3: "dækning ≥ 99 % for klines … ingen dubletter og stigende tidsstempler."
- PROTOCOL_V3 ændring 8 punkt 14 (L625): "Godkendelse nægtes, medmindre styrken er ≥ 0,5 ved sand Sharpe 3,0 (fast,
  ikke selverklæret), α_F/3 og familiens vindueslængde."

## Oversigt

| # | Emne (AMB) | Anbefalet konvention | Klassifikation | Test (`tests/test_research_f2_timeline.py`) |
|---|---|---|---|---|
| 1 | RV-døgn, kline-konvention (AMB-02) | UTC-døgn [D, D+1); bar = `open_time`; close endeligt ved o+1 t | PRÆCISERING | `KlineFacts.*`, `DayDefinition.test_day_bounds` |
| 2 | 23 mod 24 afkast (AMB-02/14) | B23: closes af barer D−1 23:00..D 22:00, 23 afkast, embargotime | **MATERIEL** | `Timeline.test_b23_no_shared_mark`, `test_a24_flagged_…`, `test_l24_off_by_one_is_content_leak`, `test_a23_no_margin` |
| 3 | Sidste tilladte input | bar åbnet D 22:00; endelig D 23:00:00 | følger 2 (MATERIEL under B23) | `Timeline.test_no_input_timestamp_at_or_after_target_start` |
| 4 | Cutoff, lås, målstart, margin (AMB-14) | cutoff D 23:00; lås D 23:30 (≤ 23:55); mål [D+1 00:00, D+2 00:00); reveal ≥ D+2 01:00 | PRÆCISERING givet 2 | `Timeline.test_lock_before_target_start_with_margin`, `test_example_2023_02_01` |
| 5 | HAR(1,7,30)-lags | RV_t, mean(RV_{t−6..t}), mean(RV_{t−29..t}); række τ bruger oprindelse τ−1 | PRÆCISERING | `HAR.test_lags_never_include_target_day`, `test_poisoned_target_never_read` |
| 6 | 365 rækker mod 365 døgn (AMB-03) | 365 regressionsrækker = 395 komplette døgn | PRÆCISERING | `HAR.test_365_rows_need_395_complete_days` |
| 7 | Estimationsvindue og minimumshistorik (AMB-04) | opvarmning inde i vinduet; 395 sammenhængende komplette døgn; ingen udfyldning | PRÆCISERING (overført historik ville være MATERIEL) | `Windows.test_counts`, `test_rv_series_isolation` |
| 8 | Manglende observationer, brudt serie (AMB-05) | 100 % dækning pr. vindue pr. mønt; ellers udgår mønten; døgnregel og genstart som sikkerhedsnet | PRÆCISERING (99 % ville være MATERIEL) | `Windows.test_coin_eligible_full_coverage`, `DayDefinition.test_missing_bar_no_fill`, `EWMA.test_missing_day_restarts_run` |
| 9 | Faktisk styrke | 334 måldøgn (bekræftelse), 275 (explore0) | låst styrke **overvurderet**; en ny styrketabel er MATERIEL for vurderingen | `Power.*` |
| 10 | Klassifikation | se tabellen | — | — |
| A6 | EWMA-start (AMB-06) | s₀ = første RV i løbet; indkøring 50; løbet afkortes til 395 | PRÆCISERING | `EWMA.test_burn_in`, `test_run_truncated_to_har_span` |
| A7 | HAR ≤ 0 (AMB-07) | gulv = mindste positive mål-RV i egne estimationsrækker; markeres; mønt-døgn udelades aldrig | **MATERIEL** | `HAR.test_floor` |
| A8 | Tværsnitsvægte (AMB-08) | lige vægt over mønter med et scoret par samme døgn | PRÆCISERING | `LossAndCrossSection.test_equal_weight` |
| A9 | Hvem godkender kalibreringen (AMB-09) | ejerens udtrykkelige, daterede kvittering med spec-version og sha256 | PRÆCISERING (styring) | — (ejerhandling) |
| A10 | Vinduesgrænse mod 2024 (AMB-10) | sidste mål 2023-12-31; prognose for 2024-01-01 laves aldrig; ingen bar ≥ 2024 | PRÆCISERING | `Windows.test_window_edge_never_reaches_2024`, `test_explore0_isolated` |
| A11 | W0-styrkeregel mod QLIKE (AMB-11) | ingen F2-fremadtest før en dateret regel; forslag: Sharpe af dbar-serien | **MATERIEL** | `Power.test_a8_translation` |

---

## 1. Definition af et RV-døgn (AMB-02, del 1)

**Låst tekst:** "RV_t = summen af kvadrerede 1-times log-afkast pr. UTC-dag" (L96).

**Fakta om klines** (DATA_CONTRACT_F2_C1 afsnit 3-4; Binance-arkivets kolonner):
- En bar identificeres af `open_time` o (UTC, hel time) og dækker handler i [o, o + 3600 s).
- `close_time` = o + 3.599.999 ms. `close` er den sidste handelspris til og med `close_time`.
- Baren er først endelig fra o + 3600 s. PROTOCOL_V3 afsnit 4: kun "bars, der er lukket".

**Læsninger:**
- (a) Døgnet grupperes efter `open_time` (barer åbnet D 00:00..D 23:00).
- (b) Døgnet grupperes efter mærketid m = o + 3600 s (DATA_CONTRACT "konvention B").
- (c) Døgnet grupperes efter `close_time`. Det er det samme som (a), fordi `close_time` ligger 1 ms før næste
  `open_time`.

**Risiko:** en blanding af åbnings- og mærketid er den klassiske fejl, der flytter en pris én time (se punkt 2, L24).

**Forslag:**
- Et UTC-døgn er D = [D 00:00:00, D+1 00:00:00).
- Alle barer navngives entydigt ved `open_time`. "Mærke kl. X" bruges ikke i kode eller lås.
- En bars information er tilgængelig fra o + 3600 s.
- Kun `open_time`, `close` og `close_time` bruges (DATA_CONTRACT afsnit 3).
- Valideringen er fail-closed (`validate_bars`): justeret time, `close_time` = `open_time` + 3.599.999,
  ingen dubletter, stigende tid, `close` endelig og > 0.

**Klassifikation: PRÆCISERING.** UTC-døgnet står i teksten. Kline-konventionen er et datafaktum, ikke et valg.

**Test:** `KlineFacts.test_close_time_and_availability`, `KlineFacts.test_validate_bars_fail_closed`,
`DayDefinition.test_day_bounds`.

## 2. 23 eller 24 observerede afkast (AMB-02, AMB-14)

**Låst tekst:** L96 som ovenfor, plus L98: "Prognose for RV_{t+1} lavet ved dagens slutning."

**De fire konstruktioner (C_h = close af baren åbnet kl. h):**

| Navn | Closes for døgn D | Afkast | Prisbevægelse dækket |
|---|---|---|---|
| A24 (bogstavelig, hele døgnet) | C_{D−1 23:00}, C_{D 00:00}, …, C_{D 23:00} (25) | 24 | [D 00:00, D+1 00:00) |
| A23 | C_{D 00:00} … C_{D 23:00} (24) | 23 | [D 01:00, D+1 00:00) |
| **B23 (forslag)** | C_{D−1 23:00}, C_{D 00:00}, …, C_{D 22:00} (24) | 23 | [D 00:00, D 23:00) |
| L24 (forskudt, negativ kontrol) | C_{D 00:00} … C_{D+1 00:00} (25) | 24 | [D 01:00, D+1 01:00) |

**Hvorfor 24 afkast kræver en close ved målstart:**
- 24 timeafkast for hele døgn D kræver 25 closes. Det sidste er C_{D 23:00}: `close_time` D 23:59:59.999, men først
  endeligt D+1 00:00:00.000.
- For prognosen af RV_{D+1} er D+1 00:00:00 målstarten. Så sidste input bliver tilgængeligt præcis ved målstart.
- Samme close C_{D 23:00} er også basis for målets første afkast ln(C_{D+1 00:00} / C_{D 23:00}). Input og mål
  deler altså et mærke.

**Er 00:00-closet døgn t's sidste pris eller målets første observation?**
- **Læst som C_{D 23:00} (A24): døgn t's sidste pris.** Prisen er dannet af handler før D+1 00:00, så indholdet
  lækker ikke. Men den er først endelig ved målstart, så låsen kan tidligst ligge ved målstart. Margin = 0 (eller
  1 ms, hvis man regner i `close_time`). Fremad er det umuligt: arkivet og strømmen publicerer efter målstart.
  Historisk er det formelt rent, men "lavet ved dagens slutning" falder sammen med målstart, og det kan ikke
  journalføres med en lås før målvinduet (C1 regel 2). **Verdict: NO_MARGIN.**
- **Læst som baren åbnet D+1 00:00 (L24): målets første observation.** Det sker, når "mærket 00:00" oversættes til
  `open_time` 00:00, en almindelig fejl ved indeksering efter åbningstid. Sidste input C_{D+1 00:00} er dannet af
  handler i D+1 00:00..00:59:59.999, altså inde i måldøgnet. Inputtets RV_D indeholder så netop målets første
  timeafkast. **Verdict: LEAK (reelt look-ahead).**
- A23 deler ikke mærke med målet. Men dens sidste close er også C_{D 23:00} (endelig ved målstart), så den har samme
  manglende margin. **Verdict: NO_MARGIN.**
- **B23:** sidste input er C_{D 22:00}, endelig D 23:00:00. Målets closes er C_{D 23:00}..C_{D+1 22:00}. Der er intet
  fælles mærke. Låsen kan ligge i [D 23:00, D+1 00:00), og den ligger før målets første close (D 23:59:59.999).
  Bevægelsen i baren åbnet D 23:00 hører ikke til noget døgn. **Verdict: OK.**
- Et forbehold om B23: ved en lås kl. 23:30 har verden set handler 23:00-23:30. Det er information om basisprisen
  C_{D 23:00}, men ikke om målets afkast (de starter ved basen). Inputtet indeholder dem ikke, fordi inputtet stopper
  ved C_{D 22:00}.

**Risiko ved hver læsning:**
- A24: ingen indholdslæk, men den er uforenelig med en lås før målstart. Den er sårbar over for L24-fejlen, og C1
  kan ikke være F2's journal.
- B23: målvariablen er RV over de første 23 timer, ikke 24. Niveauet er ca. 23/24, og estimatoren er lidt mere
  støjfuld. Begge modeller forudsiger samme størrelse, så sammenligningen er fair. Men det er en anden målvariabel
  end den bogstavelige.

**Forslag:**
- **B23 for hele F2:** historisk kalibrering, bekræftelse og en eventuel fremadtest (C1, `c1_config/2`). Det giver én
  målvariabel i alle faser og en reel margin.
- **Faldbak, hvis ejeren afviser v2:** A24 som F2 v1 med disse værn:
  - grænse-closet er altid C_{D 23:00}, og ingen felter fra baren åbnet D+1 00:00 må indgå i input;
  - prognosetidspunktet defineres som = målstart (ingen margin);
  - kun historisk brug; C1 kan da ikke være F2's journal.
- Under ingen omstændigheder L24.

**Klassifikation: B23 = MATERIEL ÆNDRING.** Den fjerner timen 23:00-24:00 fra både mål og input og ændrer dermed
målvariablen i forhold til den bogstavelige læsning. Den kræver F2 v2 og en ejerbeslutning før data. A24 med værn =
PRÆCISERING. Valget må ikke træffes efter at have set data. Kalibreringen kører kun under den konvention, der er låst
før adgang. Den kører aldrig under begge med et valg bagefter.

**Test:**
- `Timeline.test_b23_no_shared_mark` (alle 609 mål);
- `Timeline.test_a24_flagged_last_close_at_target_start` (cutoff = målstart, fælles mærke = bar 23:00, NO_MARGIN);
- `Timeline.test_l24_off_by_one_is_content_leak` (LEAK);
- `Timeline.test_a23_no_margin`;
- `DayDefinition.test_counts`, `test_b23_movement_inside_utc_day`, `test_rv_value`.

## 3. Sidste tilladte inputtidsstempel

**Låst tekst:** "Prognose for RV_{t+1} lavet ved dagens slutning"; "point-in-time" (L97-98).

**Læsninger:**
- (a) "Dagens slutning" = D+1 00:00 (A24/A23).
- (b) Sidste bar, der er endelig før en lås med margin (B23).

**Risiko:** under (a) er sidste input ≥ målstart i informationstid.

**Forslag (B23):**
- Sidste inputbar er baren åbnet D 22:00 (`close_time` D 22:59:59.999), og den er endelig D 23:00:00.
- Regel: for hver inputbar gælder o + 3600 s < målstart og `close_time` < målstart. En implementering afviser enhver
  bar med o + 3600 s > cutoff.

**Klassifikation:** følger punkt 2. Under B23 er punktet en del af den MATERIELLE ændring. Under A24 er det en
PRÆCISERING (cutoff = målstart).

**Test:** `Timeline.test_no_input_timestamp_at_or_after_target_start`. Den tester alle 275 explore0-mål og alle
334 bekræftelsesmål, både i informationstid og i `close_time`.

## 4. Prognose-cutoff, låsetid og målstart med margin (AMB-14)

**Låst tekst:** som punkt 3. F2 nævner ingen lås. C1 kræver "låst før target-vinduet".

**Forslag (B23):**

| Tidspunkt | Definition | Eksempel, måldøgn 2023-02-01 |
|---|---|---|
| input-cutoff | o_last + 3600 s, o_last = D 22:00 | 2023-01-31 23:00:00 |
| lås (nominel) | cutoff + 30 min; skal være ≤ målstart − 5 min og < målets første `close_time` | 2023-01-31 23:30:00 |
| målstart | D+1 00:00:00 | 2023-02-01 00:00:00 |
| målets data komplette | sidste målbar (D+1 22:00) endelig | 2023-02-01 23:00:00 |
| målslut | D+2 00:00:00 | 2023-02-02 00:00:00 |
| tidligste reveal | målslut + 1 t (C1's regel) | 2023-02-02 01:00:00 |

- Historisk er "låsen" en logisk konstruktion: prognosen beregnes kun af barer med tilgængelighed ≤ cutoff, og
  cutoff/lås/målstart skrives i output, så reglen kan efterprøves.
- Fremad (C1) er den en rigtig journaltid.

**Klassifikation: PRÆCISERING givet punkt 2.** Margin og lås er implementeringsregler, der er forenelige med
"lavet ved dagens slutning". Under A24 findes ingen gyldig margin.

**Test:** `Timeline.test_lock_before_target_start_with_margin`, `Timeline.test_example_2023_02_01`.

## 5. HAR(1,7,30): lagkonstruktion

**Låst tekst:** "HAR-RV med RV over 1, 7 og 30 dage, OLS på de foregående 365 dage (rullende, point-in-time)" (L96-97).

**Læsninger:**
- (a) Corsi: RV_t, mean(RV_{t−6..t}) og mean(RV_{t−29..t}), hvor de tre gennemsnit overlapper hinanden.
- (b) Ikke-overlappende blokke: RV_t, mean(RV_{t−6..t−1}) og mean(RV_{t−29..t−7}).

**Risiko:**
- Begge er fri for look-ahead, hvis oprindelsen er ≤ L. Look-ahead opstår kun, hvis en regressionsrækkes features
  bruger målets døgn, eller prognosens features bruger L+1.
- (b) er en anden parametrisering. Den giver de samme prognoser (en lineær transformation af features), men andre
  koefficienter.

**Forslag:**
- Læsning (a), som i Corsi 2009 og C1.
- Regressionsrækken for måldøgn τ bruger features med oprindelse τ−1.
- Rækkerne har τ ∈ [L−364, L]. Prognosen for L+1 bruger features med oprindelse L.
- "Uden overlap med målet": ingen feature-dag ≥ τ i en række, og ingen feature-dag > L i prognosen.

**Klassifikation: PRÆCISERING.**

**Test:**
- `HAR.test_lags_never_include_target_day`;
- `HAR.test_poisoned_target_never_read`: en RV-ordbog, der kaster en fejl ved læsning af L+1 eller senere, og
  NaN/−1 i måldøgnene. HAR- og EWMA-prognoserne er bitidentiske med de rene.

## 6. 365 regressionsrækker eller 365 kalenderdøgn (AMB-03)

**Låst tekst:** "OLS på de foregående 365 dage".

**Læsninger:**
- (a) 365 regressionsrækker. Det kræver 395 døgn data (rækkerne plus 30 lagdøgn).
- (b) 365 døgn data i alt, altså 335 rækker.

**Risiko:** ingen look-ahead i nogen af dem. Forskellen er opvarmning og antal mål: (b) giver 30 flere mål pr. vindue.

**Forslag: (a).**
- "Dage" i en OLS er observationer, og C1 har allerede valgt (a).
- (b) ville give en ny estimator med kortere vindue (en anden variant).

**Klassifikation: PRÆCISERING.** (b) ville være MATERIEL.

**Test:** `HAR.test_365_rows_need_395_complete_days`. Kravet er 395 sammenhængende døgn; med 394 → `incomplete_span`;
`rows_for_data_days(365)` = 335.

## 7. Estimationsvindue og minimumshistorik inkl. manglende døgn (AMB-04)

**Låst tekst:** "rullende, point-in-time"; PROTOCOL_V3 afsnit 2: "Der overføres ikke historik mellem vinduerne".

**Læsninger:**
- (a) Opvarmningen ligger inde i vinduet.
- (b) Opvarmningen trækkes fra det foregående vindue. For bekræftelsen er det explore0 2021 og giver 730 mål.

**Risiko:**
- (b) er ikke look-ahead (data er ældre), men bryder PROTOCOL_V3 afsnit 2.
- (b) gør explore0-data til estimationsinput for bekræftende prognoser. explore0 er udviklingsdata, og
  kalibreringen har set dem.

**Forslag (a):**
- **Første RV-døgn i et vindue:** under B23 og A24 kræver døgn D baren åbnet D−1 23:00. Vinduets første døgn mangler
  derfor sin basis og udgår. Første RV-døgn er vinduets start + 1 (`first_rv_day`).
- **HAR:** kræver alle 395 døgn [L−394, L] komplette. Rækker springes ikke over, og der udfyldes ikke. Mangler ét
  døgn, er der ingen HAR-prognose, før 395 nye sammenhængende døgn er samlet.
- **EWMA:** genstarter efter et hul (punkt A6).
- **Første mål:**
  - explore0: 2021-04-01, 275 mål;
  - train3 ∪ validation3: 2023-02-01, 334 mål;
  - train3 alene: 150 mål;
  - validation3 alene: 0 mål.
- Under A23 (første RV-døgn = vinduets start) bliver det 276/335, NOV14/C1's tal.

**Klassifikation: PRÆCISERING** (følger PROTOCOL_V3 afsnit 2). (b) ville være MATERIEL og kræve en PROTOCOL_V3-ændring.

**Konsekvens:** totrinsforløbet train3 → validation3 kan ikke bruges for F2 (validation3 giver 0 mål). Kun et samlet
vindue 2022-01-01..2023-12-31 kan bære bekræftelsen. Det er netop det vindue, direktøren kræver særskilt godkendt.

**Test:** `Windows.test_counts`, `Windows.test_rv_series_isolation` (døgn 2022-01-01 udgår, fordi det kræver baren
2021-12-31 23:00).

## 8. Manglende observationer og brudte serier (AMB-05)

**Låst tekst:** L94: "En mønt uden fuld dækning udgår mekanisk; færre end 10 → UNTESTABLE." PROTOCOL_V3 afsnit 3:
≥ 99 %.

**Læsninger:**
- (a) "Fuld" = 100 % af vinduets timebarer, vurderet pr. vindue og mønt.
- (b) ≥ 99 % pr. vindue (afsnit 3), suppleret med en døgnregel.
- (c) Pr. døgn: ufuldstændige døgn udgår, og mønten bliver.

**Risiko:**
- Ingen look-ahead, så længe reglen anvendes, før noget tab beregnes.
- Selektionsrisiko, hvis reglen vælges efter at have set dækningstal: tallene kan ses ved datakvalitetstjekket.
  Derfor låses reglen før adgang.
- (a) kan udelukke mange mønter. I explore0 mangler SOL, AVAX, DOT, DOGE og FIL sandsynligvis (filnavne, NOV14), så
  15 er tilbage. Ét tabt timeslot udelukker en mønt for hele vinduet.

**Forslag (a), den bogstavelige læsning:**
- En mønt er med i et vindue, hvis og kun hvis alle timebarer i [vinduets start, vinduets slut) findes og består
  `validate_bars`. Bestemmes mekanisk før noget RV-tab.
- Med 100 % findes der ingen ufuldstændige døgn for en deltagende mønt. Døgnreglen (et døgn med en manglende bar har
  ingen RV, HAR-spændet brydes, EWMA genstarter) bliver kun et sikkerhedsnet, og den er implementeret og testet.
- **Flade barer** (`count` = 0, O=H=L=C) er formelt til stede og tælles. Et døgn med RV = 0 kan ikke scores (QLIKE
  er udefineret) og behandles som ufuldstændigt. Det rapporteres. Hører under AMB-05, og forslaget er en PRÆCISERING,
  fordi QLIKE ellers ikke er defineret.
- **Paret scoring:** et mønt-døgn scores kun, når både HAR og EWMA har en gyldig prognose, og måldøgnet er komplet.
  Ellers er det void og tælles.

**Klassifikation: PRÆCISERING** for (a). (b) og (c) lemper "fuld" og er MATERIELLE.

**Test:**
- `Windows.test_coin_eligible_full_coverage` (én manglende bar ud af 4.416 → ikke med, selv ved > 99 %);
- `DayDefinition.test_missing_bar_no_fill` (ingen udfyldning; baren åbnet D−1 23:00 er basis for døgn D og ikke del
  af døgn D−1);
- `EWMA.test_missing_day_restarts_run`.

## 9. Faktisk statistisk styrke

**Låst tekst** (L113-117): styrketabel med "train3 ∪ validation3" (730 d) og "train3" (546 d), samt GO-betingelsen
L119-121.

**Beregning:** `p2_power.dm_power` med protokollens antagelser (HAC-faktor 1,5, α 0,05 ensidet, K = 1, 20 mønter,
explore0 også 15). Genberegnet i `f2_timeline.power_table()`. Den låste tabel genskabes eksakt (`Power.test_locked_table_reproduced`).

| Vindue (måldøgn) | Mønter | ρ_c | e 0,02 | e 0,05 | e 0,08 | e 0,10 | MDE (80 %) |
|---|---|---|---|---|---|---|---|
| **Låst:** train3 ∪ validation3 (730) | 20 | 0,5 | 0,15 | 0,451 | 0,785 | 0,919 | 0,082 |
| **Låst:** train3 ∪ validation3 (730) | 20 | 0,8 | 0,124 | 0,338 | 0,624 | 0,790 | 0,101 |
| **Låst:** train3 (546) | 20 | 0,5 | 0,132 | 0,371 | 0,678 | 0,838 | 0,094 |
| Bekræftelse B23 (334) | 20 | 0,5 | 0,109 | **0,269** | 0,501 | **0,661** | 0,121 |
| Bekræftelse B23 (334) | 20 | 0,8 | 0,095 | 0,207 | 0,375 | **0,505** | 0,150 |
| Bekræftelse A23/C1-læsning (335) | 20 | 0,5 | 0,109 | 0,270 | 0,502 | 0,662 | 0,121 |
| Bekræftelse A23/C1-læsning (335) | 20 | 0,8 | 0,095 | 0,208 | 0,376 | 0,506 | 0,150 |
| train3 alene, B23 (150) | 20 | 0,5 | — | 0,170 | — | 0,396 | — |
| train3 alene, B23 (150) | 20 | 0,8 | — | 0,138 | — | 0,297 | — |
| explore0 B23 (275) | 15 | 0,5 | 0,101 | 0,236 | 0,436 | 0,583 | 0,134 |
| explore0 B23 (275) | 15 | 0,8 | 0,089 | 0,186 | 0,329 | 0,443 | 0,166 |
| explore0 A23 (276) | 20 | 0,5 | 0,102 | 0,239 | 0,441 | 0,590 | 0,133 |
| explore0 A23 (276) | 20 | 0,8 | 0,090 | 0,186 | 0,330 | 0,445 | 0,165 |

**Konklusion: den låste styrke er overvurderet.**
- Tabellen regner med 730 måldøgn. Med opvarmning i vinduet er der 334.
- n_eff er dermed 2,19 gange for stor, og z-afstanden 1,48 gange for stor.
- Ved den låste tabels egne scenarier falder styrken:
  - e 0,05, ρ_c 0,5: 0,45 → 0,27;
  - e 0,10, ρ_c 0,5: 0,92 → 0,66;
  - e 0,10, ρ_c 0,8: 0,79 → 0,51;
  - "train3, ρ_c 0,5, e 0,10": 0,84 → 0,40 (150 mål).
- **GO-betingelsen** ("e ≥ 0,08 giver styrke ≥ 0,8 ved den målte tværsnitskorrelation"):
  - ved 334 mål og HAC 1,5 kræver den ρ_c ≤ 0,19 (`rho_max_for_power`);
  - ved 730 mål kræver den ρ_c ≤ 0,48. Selv den låste tabel giver 0,785 < 0,8 ved ρ_c 0,5.
  - Er ρ_c for QLIKE-differencer i krypto omkring 0,3-0,6 (UNKNOWN før kalibrering), bliver udfaldet efter den låste
    regel **INSUFFICIENT POWER**.
- explore0 er ingen test. Tallene for explore0 viser kun, hvor stor en effekt kalibreringen overhovedet kunne skelne
  fra nul: MDE ≈ 0,13-0,17.
- B23's 23 afkast gør RV en smule mere støjfuld. Det kan øge sd(d) en anelse. Størrelsen er UNKNOWN og kan ikke
  regnes uden data.

**Forslag:** styrkevurderingen i en F2 v2 bruger måldøgnstallet fra `window_targets` (334) og ikke vinduets
kalenderlængde. Indtil da står F2's dom "REDESIGN → betinget GO" som skrevet, men med denne kendte overvurdering.

**Klassifikation:** genberegningen er en kendsgerning, ikke en ændring. En ny styrketabel eller GO-tærskel i
protokollen er en **MATERIEL ÆNDRING**. Det samme gælder at indføre overført historik (730 mål), et kortere
HAR-vindue eller et andet vindue. Hver af dem kræver en ejerbeslutning.

**Test:** `Power.test_locked_table_reproduced`, `Power.test_shorter_windows`.

## 10. Samlet klassifikation

| Punkt | PRÆCISERING | MATERIEL ÆNDRING |
|---|---|---|
| 1 RV-døgn og kline-konvention | ✔ | |
| 2 23/24 afkast | A24 med værn (faldbak, ingen margin) | **B23 (anbefalet)** |
| 3 sidste input | under A24 | under B23 (del af B23) |
| 4 cutoff/lås/mål | ✔ (givet 2) | |
| 5 HAR-lags | ✔ | |
| 6 365 rækker | ✔ (a) | (b) 335 rækker |
| 7 opvarmning i vinduet | ✔ (a) | (b) overført historik |
| 8 100 % dækning pr. vindue | ✔ (a) | (b) 99 %, (c) pr. døgn |
| 9 styrke | genberegning = fakta | ny styrketabel / GO-regel |
| A6 EWMA-start | ✔ | |
| A7 HAR ≤ 0 | | **✔ (gulv)** |
| A8 lige vægt | ✔ | anden vægtning |
| A9 godkender | ✔ (styring) | |
| A10 vinduesgrænse | ✔ | |
| A11 W0-styrke for QLIKE | | **✔** |

**Til en ejerbeslutning (F2 v2, én pakke, før data):** B23 (punkt 2-3), HAR-gulvet (A7) og W0-oversættelsen (A11).
Alt andet kan stå som præciseringer af v1, når direktøren har bekræftet dem.

**Hvis ejeren siger nej til v2:**
- F2 v1 kører med A24 og værn, kun historisk;
- C1 kan ikke være F2's journal;
- HAR ≤ 0 har ingen regel i v1. Fail-closed: optræder en HAR-prognose ≤ 0 i bekræftelsen, er udfaldet UNTESTABLE
  (specifikationshul). Mønt-døgnet udelades aldrig.

---

## A6. EWMA-startværdi og indkøring (AMB-06)

**Låst tekst:** "Benchmark (fast): EWMA λ = 0,94 på samme RV-serie."

**Læsninger:**
- (a) s₀ = første RV i løbet, med indkøring 50 (C1).
- (b) s₀ = vinduets eller seriens middel. Det er look-ahead, hvis middelværdien omfatter fremtidige døgn.
- (c) Ingen indkøring.

**Risiko:** (b) er look-ahead. (c) gør de første prognoser afhængige af ét døgn.

**Forslag:**
- s = RV_{første døgn i det sammenhængende løb}; s_t = 0,94·s_{t−1} + 0,06·RV_t; prognose for L+1 = s_L.
- Indkøring: λ^(n−1) ≤ 0,05 ⇒ n ≥ 50.
- Løbet afkortes til de 395 døgn, HAR bruger. Startvægten er 0,94^394 ≈ 2·10⁻¹¹, så det er numerisk uden betydning,
  men giver samme inputidentitet for begge modeller.
- Et hul genstarter løbet.
- Med paret scoring scores EWMA kun på døgn, hvor HAR findes (≥ 395 døgn), så indkøringen binder aldrig i testen.

**Klassifikation: PRÆCISERING.** Benchmarkens formel er uændret, og startværdien er en uspecificeret detalje uden
mærkbar effekt.

**Test:** `EWMA.test_burn_in`, `EWMA.test_missing_day_restarts_run` (håndregnet rekursion fra løbets første døgn),
`EWMA.test_run_truncated_to_har_span`.

## A7. HAR-prognose ≤ 0 (AMB-07)

**Låst tekst:** ingen. QLIKE kræver F > 0.

**Læsninger:**
- (a) Mønt-døgnet udelades.
- (b) Prognosen erstattes med EWMA (d = 0 det døgn).
- (c) Gulv ved en positiv værdi.
- (d) log-HAR.

**Risiko:**
- (a) fjerner HAR's værste døgn og trækker resultatet mod PASS. Den er forbudt.
- (b) fortynder effekten og skjuler fejlen.
- (d) er en anden model (samme slægt) og er udelukket.

**Forslag (c):**
- Gulvet er den mindste positive mål-RV i prognosens egne 365 estimationsrækker. Det er point-in-time og bruger ingen
  data efter L.
- Antallet af gulvede mønt-døgn rapporteres.
- Forhåndsregel: er mere end 1 % af de scorede mønt-døgn gulvede, er F2's udfald INCONCLUSIVE (modellen er
  misspecificeret), uanset t.

**Klassifikation: MATERIEL ÆNDRING** (fail-closed). Enhver regel ændrer kandidatens prognoser på de døgn.

**Test:** `HAR.test_floor`.

## A8. Tværsnitsvægte (AMB-08)

**Låst tekst:** "på den tværsnitsvægtede daglige middel-d" (L102). "puljet over mønt-dage" (L100).

**Læsninger:**
- (a) Lige vægt over mønter med et scoret par samme døgn.
- (b) Invers varians (1/sd_i(d)).
- (c) Markedsværdi eller volumen.

**Risiko:**
- (b): vægte estimeret i explore0 ville være kalibrering, der ændrer testen. Det er forbudt (L108-109).
- (c) kræver eksterne data og point-in-time-vægte.

**Forslag (a):**
- dbar_t = middel af d_{i,t} over de mønter, der er scoret det døgn. QLIKE er skalafri (afhænger kun af RV/F), så
  lige vægt er naturlig.
- Med 100 %-dækningsreglen (punkt 8) er panelet balanceret. Så er "puljet over mønt-dage" og "daglig middel" samme tal.
- Falsifikatorens "mere end halvdelen af mønterne" tælles på møntens middel-d_i < 0.

**Klassifikation: PRÆCISERING.** Al anden vægtning er MATERIEL.

**Test:** `LossAndCrossSection.test_equal_weight`, `LossAndCrossSection.test_qlike`.

## A9. Hvem godkender kalibreringen (AMB-09)

**Låst tekst:** "Aktivering kræver ejerens `approve-template`" (L3-4) mod "explore0-kalibreringen (fra 14/11)"
(L120). Direktørens CONDITIONAL.

**Læsninger:**
- (a) Direktørens CONDITIONAL er nok.
- (b) Ejerens udtrykkelige kvittering kræves (D3, fail-closed i NOV14).

**Risiko:** under (a) åbnes data uden ejerens ja. Ordre 53 kræver et "eksplicit, dateret ejer-ja, der identificerer
den konkrete protokolversion og hash" for låse.

**Forslag (b):**
- Kalibreringens dataadgang kræver ejerens udtrykkelige, daterede ja med navnet `F2_CALIBRATION_SPEC_DRAFT` i den
  version, der godkendes, og filens sha256.
- Dertil: G01 (≥ 2026-11-14 00:00 UTC) og et committet manifest før fortolkning.
- "Gør alt" (11-04) tæller ikke.

**Klassifikation: PRÆCISERING (styring).** F2's identitet berøres ikke.

## A10. Vinduesgrænse mod 2024 (AMB-10)

**Låst tekst:** "Bekræftelse sker i train3 ∪ validation3" og fællesreglen "aldrig 2024-holdout" (L5-6).

**Læsninger:**
- (a) En prognose, der laves på vinduets sidste dag, scores ikke.
- (b) Den laves slet ikke.

**Risiko:** under A24/A23 er bekræftelsens sidste mål (2023-12-31) afhængigt af baren åbnet 2023-12-31 23:00. Den er
data fra 2023, men først endelig 2024-01-01 00:00:00. Den rører altså grænsen i informationstid. Reveal for et
2024-mål ville læse 2024-barer.

**Forslag:**
- Mål ligger i vinduet: det sidste er 2023-12-31 (explore0: 2021-12-31).
- En prognose for 2024-01-01 beregnes aldrig (b).
- Under B23 er den sidste bar, der overhovedet behøves, baren åbnet 2023-12-31 22:00 (endelig 23:00). Ingen bar med
  `open_time` ≥ 2024-01-01 og ingen tilgængelighed ≥ 2024-01-01 00:00. Baren åbnet 2023-12-31 23:00 er embargotime
  og bruges ikke.
- Indlæseren for bekræftelsen afviser enhver række med `open_time` ≥ 2024-01-01 (BLOCK).
- Den samme isolation gælder explore0 → train3: explore0 behøver intet ≥ 2021-12-31 23:00, og bekræftelsens første
  RV-døgn (2022-01-02) behøver intet før 2022-01-01 23:00.

**Klassifikation: PRÆCISERING.**

**Test:** `Windows.test_window_edge_never_reaches_2024` (alle 334 mål, input- og målbarer),
`Windows.test_explore0_isolated`, `Windows.test_a_conventions_touch_the_boundary` (dokumenterer A23's
grænseberøring).

## A11. W0-styrkeregel mod QLIKE-testen (AMB-11)

**Låst tekst:** ændring 8 punkt 14 (L625): "styrken er ≥ 0,5 ved sand Sharpe 3,0 (fast, ikke selverklæret), α_F/3 og
familiens vindueslængde."

**Afgrænsning:** gælder kun en senere F2-fremadtest (C1, α_F 0,0125 fra W0). Den historiske fase bruger α 0,05 pr.
vindue (ændring 2).

**Læsninger:**
- (a) Reglen er uanvendelig på en QLIKE-estimand. Så findes ingen regel, og F2-fremad kan ikke godkendes.
- (b) Oversæt til Sharpe-tallet for den daglige dbar-serie: SR_d = middel(dbar)/sd(dbar)·√365. Brug samme formel som
  `p2_power.a8_check`.

**Tal (b):**
- styrke ved SR_d 3,0 og α_F/3: 6 mdr. 0,297, 9 mdr. 0,476, 12 mdr. 0,633 (`a8_translation`). Det kræver ≥ 12
  måneders scorede døgn.
- SR_d 3,0 svarer til e ≈ 0,11 pr. mønt-døgn ved 20 mønter og ρ_c 0,5 (uden HAC-faktor).
- C1's første HAR-prognose kommer tidligst 2027-12-15 (DATA_CONTRACT afsnit 8).

**Risiko:**
- (b) er en fortolkning, som ejeren ikke har set.
- "Fast, ikke selverklæret" forbyder at vælge en bekvem oversættelse efter data.

**Forslag:**
- Fail-closed (a), indtil en dateret ændring definerer reglen for tab-differens-estimander.
- (b) foreslås som den ændring. Den er ikke hastende: ingen fremadtest kan begynde før 2027-12.

**Klassifikation: MATERIEL ÆNDRING** (ny regel i ændring 8's program).

**Test:** `Power.test_a8_translation` (samme tal som `p2_power.a8_check`).

---

## Ikke afgjort her (uden for P0)

- AMB-01 (navnekollision), AMB-12/13 (C1-kilde) og godkendelsen af evalueringsvinduet (direktøren, G16) er uændrede.
- B23 forudsætter i C1 en fremadrettet 1h-kline-strøm (G19), som ikke findes.
- Eksponering: train3/validation3- og explore0-1h-klines for de 20 mønter er brugt af tidligere screeninger.
  HAR-mod-EWMA er ikke testet. Det skal stå i en eventuel rapport.
- SURVIVORSHIP_UNKNOWN for den faste møntliste er uændret.
