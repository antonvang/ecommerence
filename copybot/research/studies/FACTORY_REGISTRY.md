# FACTORY_REGISTRY — forskningsregister og testbudget (direktørordre 47 P0, 06/11-09/11)

Kilde: research/reviews/INBOX.md, ordre 47 "Quant Research Factory v1". Kode `research/tools/factory.py`, tests
`tests/test_research_factory.py` (syntetiske data), snapshot `research/data/factory/registry.json` + `registry.md`,
liste over studier uden for databasen `research/data/factory/offdb_studies.json`.

## Hvad det er

Et register **oven på** den eksisterende pipeline. Laboratoriets tabeller (experiments, transitions, trials,
alpha_ledger, approvals, datasets), hypotesepipelinen (ændring 17) og explore-banen forbliver sandheden; registret
læser dem read-only og lægger tre ting til:

1. **Fælles statusord.** Hver hypotese har et ID og én status: PROPOSED → APPROVED → FROZEN → TESTED →
   REJECTED / INCONCLUSIVE / VALIDATED, plus CLOSED (trukket tilbage/udfaset) og EXTERNAL. Laboratoriets
   livscyklus oversættes fast (`LAB_MAP`): DISCOVERED/SUPPRESSED → PROPOSED, REGISTERED → APPROVED,
   SCREENING → FROZEN, SCREEN_PASSED/VALIDATION → TESTED, OBSERVATION → INCONCLUSIVE,
   VALIDATED/PAPER_TRADING/PAUSED → VALIDATED, REJECTED → REJECTED, WITHDRAWN/RETIRED → CLOSED.
2. **Slægtskab.** En slægt er en sammenhængende komponent i `related`-grafen i research/families/VOCABULARY.json.
   Et nyt navn med samme fingeraftryk (mekanisme, retning, univers, estimand) afvises som samme hypotese; en
   beslægtet variant får sit eget ID, men tæller i samme slægt. Omdøbning nulstiller derfor ikke budgettet.
3. **Testbudget-ledger.** Kun tilføjelser og hashkæde. Hvert forsøg tæller, også screeninger, explore-kandidater,
   gamle eksperimenter uden forsøgsrækker (mindst ét forsøg hver) og studier uden for databasen. Negativ alfa
   (tilbagebetaling) afvises; en afvist hypotese kan ikke testes igen under sit eget ID; en ny test af en
   INCONCLUSIVE kræver en ny opkrævning.

## Regler for nye hypoteser (håndhævet i koden, bevist i testene)

| Regel | Test |
|---|---|
| Godkendelse kun af en menneskelig aktør (`human:`); Claude, ChatGPT og systemet kan ikke godkende | `test_approval_needs_a_human` |
| Ingen spring i statusrækken | `test_no_skipping` |
| Frysning kræver fuld forhåndsregistrering (familie, mekanisme, retning, univers, vinduer, kilder, datasæt, parameterfamilie, estimand, benchmark, omkostningsmodel, afvisningskriterier, spec-commit) og sha256 på hvert datasæt | `test_freeze_needs_full_prereg_and_hashes` |
| Ingen beskyttede vinduer: 2024-holdout; COIN-M før 28/11 | `test_protected_windows` |
| Test kræver en opkrævning efter frysningen; endelig status kan ikke testes igen | `test_test_needs_a_fresh_charge` |
| Ændrede data eller ændret forhåndsregistrering efter låsen afvises | `test_changed_data_or_prereg_after_lock` |
| Fabrikken promoverer aldrig til papirhandel | `test_never_promotes_to_paper` |
| Ledger: ingen tilbagebetaling, mindst én variant, manipulation opdages | `test_no_refund_and_every_attempt_counts`, `test_tampering_is_detected` |
| Snapshot tæller alt og er reproducerbart | `test_snapshot_counts_everything`, `test_reproducible` |

`approve-template` og livscyklusgodkendelser forbliver ejerens. Registret godkender, åbner og promoverer intet.

## Første snapshot (06/11, produktionsdatabasen read-only)

Se `research/data/factory/registry.md` for tal og sha256. Hovedtal: 65 laboratorieeksperimenter (47 REJECTED, 3
INCONCLUSIVE, 8 PROPOSED, 4 CLOSED, 3 EXTERNAL; ingen VALIDATED), 197 forsøg i ledgeren, 19.311 varianter, heraf
19.079 unikke explore-kandidater (aldrig evidens), brutto opkrævet alfa 0,349.

## Åbne punkter (UNKNOWN indtil lukket)

- 22 studier uden for databasen er listet, men ikke talt endnu: ledgeren er en **nedre grænse** til de er talt.
  Ændring 17's målinger H1-H5 (MAALING 14a/16a/16c) er allerede talt via lab-events og må ikke tælles igen.
- 18 gamle eksperimenter er testet uden forsøgsrækker; de tæller med ét forsøg hver (nedre grænse).
- Laboratoriets alpha_ledger har én negativ familierække (`family:fcarry` −0,0125, en modpost ved fordeling af
  familiebudgettet). Den rapporteres, men fabrikkens ledger tager kun bruttoopkrævninger.
- Slægter med flere tags navngives efter det alfabetisk første tag; fcarry ligger i slægten `cross_venue_perp_gap`.
