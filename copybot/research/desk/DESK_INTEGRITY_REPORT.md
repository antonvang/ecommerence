# DESK_INTEGRITY_REPORT (direktørordre 51 P3, 2026-11-06)

Status: **desk'en er bygget og testet isoleret og syntetisk. Intet er aktiveret, integreret i produktionen eller testet
på markedsdata.** Ingen strategi, stream eller protokol er godkendt. Der er ikke opkrævet alfa i den rigtige ledger, og
der er ikke foretaget nogen ejerhandling.

## 1. Hvad er bygget

| Komponent | Fil(er) | Formål | Status |
|---|---|---|---|
| Evidensregister | `desk/evidence_registry.json`, `LITERATURE_MAP.md`, `mechanism_graph.json`, `research_gaps.md` | 44 kilder åbnet og verificeret, 10 kategorier | færdig (P0/50) |
| Small-player edge | `desk/SMALL_PLAYER_EDGE.md`, `small_player_registry.json` | 49 kilder. Hver vinkel er klassificeret som dokumenteret, kun teoretisk eller forsvinder efter omkostninger. | færdig (ejerens ordre) |
| Forward data observatory | `desk/FORWARD_DATA_PLAN.md`, `stream_registry.json`, `data_quality_schema.json`, `tools/forward_obs.py` | Audit af 17 streams og 8 foreslåede, der venter på godkendelse | design (P1/50) |
| Natlig fabrik | `tools/desk_factory.py` | Tilstandsmaskine fra idé til afgørelse. Godkendelse kræver ejerens signatur. Gates, ledger og Holm. | prototype (P2/50) |
| Evaluator v1 og v1.1 | `crosscheck/EVALUATOR_SPEC*.md`, `claude_eval.py`, `claude_eval_v11.py`, `compare.py` | Fail-closed evaluator, krydstjekket mod Codex | PASS (P3/50, P0/51) |
| Codex' uafhængige evaluator og red team | `desk/codex/` (ref_eval.py, r2/ med 47 fixtures, ANALYTIC.md) | Uafhængig implementering og blinde angreb | merget fra `codex/crosscheck-r2` |
| C1-prognosejournal | `tools/c1_forecast.py`, `desk/C1_FORECAST_DESIGN.md`, `data/c1/` | F2's prognosejournal. Bagudrettede prognoser er umulige. | READY_NOT_ACTIVE (P1/51) |
| Protokol-shortlist | `desk/PROTOCOL_SHORTLIST.md`, `desk/protocols/` | 30 kandidater og 3 udkast: 2 PROPOSED, 1 PARKED | udkast (P2/51) |
| Syntetisk natkørsel | `tools/desk_night.py`, `data/desk_night/night.json` | Hele kæden med 12 integritetskontroller | 12/12 PASS (P3/51) |

## 2. Testoversigt

| Testfil | Tests | Dækker |
|---|---|---|
| tests/test_research_desk_factory.py | 10 | Godkendelse kun med signatur, gates, ledger, Holm, ugyldigt input uden opkrævning |
| tests/test_research_desk_eval_v11.py | 10 | Validering, embargo, key_conflict, S ≤ 0, lukket form (t = 3,0) |
| tests/test_research_desk_crosscheck.py | 2 | v1: reproducerbarhed og komparator |
| tests/test_research_desk_night.py | 1 | Alle 12 integritetskontroller |
| tests/test_research_forward_obs.py | 31 | 11 indplantede datafejltyper |
| tests/test_research_c1_forecast.py | 33 | Journalintegritet, modeller, QLIKE og DM |
| research/desk/codex/test_ref_eval.py + r2/test_r2.py | 42 (+8) | Codex' egne tests, kørt grønne på denne maskine |
| Hele suiten | 1451 OK | — |

**Krydskontrol**
- Runde 1: 436+ felter på 6 fixtures, 0 afvigelser ud over tolerancen.
- Runde 2: 47 blinde fixtures, 47/47 efter rettelse af 3 fejl hos Claude. Tolerancen er ikke udvidet.

## 3. Integritetskontroller i den syntetiske natkørsel (12/12 PASS)

1. Ingen godkendelse uden ejerens signerede udsagn.
2. Injiceret jobfejl er synlig i rapporten.
3. De rigtige shortlist-udkast når ejer-gaten eller parkeres, men godkendes aldrig af sig selv.
4. Assistentens nøgle og delegerede formuleringer afvises.
5. Godkendte udkast blokeres af gates, fordi vinduet ikke er slut og deres streams kun er foreslået.
6. Ledger-kæden verificeres, og en identisk genkørsel opkræver intet.
7. Alle evalueringer går gennem v1.1.
8. Shortlist-udkast bliver aldrig evalueret.
9. C1-journalen kører og verificeres.
10. Datakvalitetsmodulet bruger hverken netværk eller database.
11. Ingen database åbnes under kørslen (sqlite3 og socket er blokeret). Den låste F2-protokol og S1-beslutningerne har
    uændret sha256. Lab.db er levende, og laboratoriet skriver selv i den, så dens hash beviser intet. Den fejlkilde blev
    fundet og rettet i denne runde.
12. Ingen lab- eller pm_lp-import, kontrolleret via AST.

## 4. Commits (ordre 50–51, kronologisk)

8ff89d9, d080610, a0e307c, 3ff8cf2, 2e23f52, ae2abbf, c3f38bb, 73e4f88, 22240bb, 80fb255, b7cf362, f624184, 55111a1
(Codex), 3c8f778 (merge), 01fad37, 21f900b og denne rapports commit.

## 5. Risikoregister

| # | Risiko | Sandsynlighed | Konsekvens | Afbødning / status |
|---|---|---|---|---|
| R1 | Spec og fixtures deler en blind vinkel (to implementeringer af samme fejl) | middel | forkert evaluering på rigtige data | Codex' blinde fixtures og den analytiske reference. v1.1.1 lukker 5 åbne spørgsmål. |
| R2 | Utilstrækkelig styrke (C1 0,47 efter 365 d; LIQREC1 0,22; mange kandidater < 0,8) | høj | INCONCLUSIVE frem for viden | Styrke ≥ 0,8 kræves før data. Ingen automatisk PASS/FAIL. |
| R3 | Alfa-budget: W0 0,0375 rækker til 3 af 4 kandidater (F2, F3, LIQPROXY1, FUNDFRAG1) | sikker | prioriteringskonflikt | Ejeren rangerer, eller LIQPROXY1 klassificeres som måling |
| R4 | Ejeridentitet er ikke bundet (ingen ejernøgle, intet eksternt anker) | sikker indtil ejeren handler | ingen rigtig godkendelse mulig | De 6 ejerhandlinger venter. Claude udfører dem aldrig. |
| R5 | Datahuller i census (30/10–31/10) og markPrice er ikke en handlet pris | sket | forkert RV | C1 skifter til F2's klines fra 14/11 (direktørens afgørelse) |
| R6 | Foreslåede streams kræver deploy af lab-kode (D1, B1, B2) og kan bryde pm_lp's genstart | middel | driftsstop | Særskilt godkendelse, deploy kun uden for K1–K3, ingen genstart før 27/11 |
| R7 | Overfitting og publikationsforfald (anomalier −35 % efter publikation; backtest-Sharpe forklarer < 2,5 % OOS) | høj | falske fund | K = 1 primær pr. familie, Holm, låst før data, forward-validering |
| R8 | Litteratur med 2024 i sit sample (kun som litteratur, aldrig replikeret på holdout) | lav | brud på holdout | Holdout-reglen og registrets data_availability-koder |
| R9 | Codex' blindhed er kun dokumenteret, ikke teknisk håndhævet | lav | svagere uafhængighed | Commit-rækkefølge og manifest-sha256 er verificeret |
| R10 | Browserbaseret overførsel (ChatGPT/Codex) kan logge ud eller fryse | middel | forsinkelse | Git-branch-overførsel. Ingen login fra Claude. |

## 6. Hele testsuiten

`python3 -m unittest discover -s tests`: **Ran 1451 tests, OK (skipped=1)**, 2026-11-06 (efter alle ordre 50–51-commits til og med 21f900b; tidligere 1404). Codex' 50 tests under research/desk/codex/ køres separat: OK.

## 7. Hvad kræver ejeren

- De 6 nøgle- og signaturhandlinger (ordre 49 P1). Uden dem kan intet godkendes.
- Rangering af alfa-budgettet (R3).
- Aktivering af foreslåede streams og af C1. Hver kræver en særskilt dateret godkendelse.
- Enhver S2-integration (fortsat NO-GO).

## 8. Prioriteret næste plan

1. **EVALUATOR v1.1.1**: luk de 5 åbne spørgsmål (overflow-kode, ekstra lock-nøgler, replay-lighed, filnavn, fejlstier).
   Codex-runde 3 som mutationstest, dvs. bevidst plantede fejl i en kopi af evaluatoren, som testene skal fange.
2. **14/11-forberedelse**: C1 på F2's 1h-klines (explore0 efter F2's protokol), låse A/B (n6/n4) og første
   versionsstyrede forskningsstatus, uden at datagates ændres.
3. **Small-player-sporet som protokoller** (kun udkast): (a) patient side mod impatient taker i dokumenterede
   prediction-market-data (kun forskning; ingen konti eller handler; pm_lp røres ikke; særskilt godkendelse); (b) tidsplan
   for token-unlocks som skemalagt udbudschok (kræver host-gate-tjek i PROTOCOL_V3). Begge skal igennem desk_factory med
   styrke ≥ 0,8, før de går videre.
4. Faste milepæle bevares: 08/11 HFC-1, 12/11 STRAKS, 14/11 A/B og status, 19/11 par, 20/11 S1-evaluering, 27/11 og
   28/11.
