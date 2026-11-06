# F2 — tidslinjer og syntetiske regressionstests (direktørordre 53 P0)

**Skrevet 2026-11-06 ca. 15:30 UTC. FORSLAG; ingen data læst.** Alle tider er UTC og regnet med kalenderaritmetik i
`research/tools/f2_timeline.py` (`python3 research/tools/f2_timeline.py examples` giver dem som JSON). Konventionerne
og deres klassifikation står i `research/desk/F2_AMBIGUITY_RESOLUTION_PROPOSAL.md`.

```
python3 research/tools/f2_timeline.py selftest
python3 -m unittest tests.test_research_f2_timeline tests.test_research_gates tests.test_lab_safety
```

## 1. Notation

- Bar `h` = kline med `open_time` h. Den dækker handler i [h, h + 1 t), `close_time` = h + 59:59.999, og baren er
  endelig ved h + 1 t ("tilgængelig").
- C_h = close af bar h.
- **Input-cutoff** = tilgængeligheden af sidste inputbar.
- **Lås** = cutoff + 30 min. Kravet er lås ≤ målstart − 5 min og lås < målets første `close_time`.
- **Målstart/-slut** = UTC-døgnet [D 00:00, D+1 00:00).
- **Tidligste reveal** = målslut + 1 t (C1's regel; historisk er det kun en logisk grænse).

## 2. Måldøgn 2023-02-01 under hver konvention

| | B23 (forslag, MATERIEL) | A24 (bogstavelig) | A23 | L24 (forskudt) |
|---|---|---|---|---|
| sidste inputdøgn | 2023-01-31 | 2023-01-31 | 2023-01-31 | 2023-01-31 |
| inputdøgnets barer | 2023-01-30 23:00 .. 2023-01-31 22:00 | 2023-01-30 23:00 .. 2023-01-31 23:00 | 2023-01-31 00:00 .. 23:00 | 2023-01-31 00:00 .. **2023-02-01 00:00** |
| sidste inputbar | 2023-01-31 22:00 | 2023-01-31 23:00 | 2023-01-31 23:00 | **2023-02-01 00:00** |
| dens `close_time` | 2023-01-31 22:59:59.999 | 2023-01-31 23:59:59.999 | 2023-01-31 23:59:59.999 | **2023-02-01 00:59:59.999** |
| input-cutoff (endelig) | **2023-01-31 23:00:00** | 2023-02-01 00:00:00 (= målstart) | 2023-02-01 00:00:00 (= målstart) | 2023-02-01 01:00:00 |
| lås (nominel) | 2023-01-31 23:30:00 | 2023-02-01 00:30:00 (efter målstart) | 2023-02-01 00:30:00 | 2023-02-01 01:30:00 |
| målstart | 2023-02-01 00:00:00 | 2023-02-01 00:00:00 | 2023-02-01 00:00:00 | 2023-02-01 00:00:00 |
| målets barer | 2023-01-31 23:00 .. 2023-02-01 22:00 | 2023-01-31 23:00 .. 2023-02-01 23:00 | 2023-02-01 00:00 .. 23:00 | 2023-02-01 00:00 .. 2023-02-02 00:00 |
| målets første `close_time` | 2023-01-31 23:59:59.999 | 2023-01-31 23:59:59.999 | 2023-02-01 00:59:59.999 | 2023-02-01 00:59:59.999 |
| målets data komplette | 2023-02-01 23:00:00 | 2023-02-02 00:00:00 | 2023-02-02 00:00:00 | 2023-02-02 01:00:00 |
| målslut | 2023-02-02 00:00:00 | 2023-02-02 00:00:00 | 2023-02-02 00:00:00 | 2023-02-02 00:00:00 |
| tidligste reveal | 2023-02-02 01:00:00 | 2023-02-02 01:00:00 | 2023-02-02 01:00:00 | 2023-02-02 01:00:00 |
| fælles mærke input/mål | ingen | **bar 2023-01-31 23:00** | ingen | **bar 2023-02-01 00:00** |
| input med handler ≥ målstart | nej | nej | nej | **ja** |
| `check_timeline` | **OK** | NO_MARGIN | NO_MARGIN | **LEAK** |

Embargo under B23: bevægelsen i bar 2023-01-31 23:00 (23:00 → 23:59:59.999) hører hverken til input-RV eller til
mål-RV. Dens close er målets basispris. Basisprisen dannes efter låsen (23:30), og målets første afkast er bevægelsen
i bar 2023-02-01 00:00.

## 3. Vinduernes første og sidste mål (B23, opvarmning inde i vinduet)

| | explore0 | train3 ∪ validation3 |
|---|---|---|
| vinduet (halvåbent) | [2020-03-01, 2022-01-01) | [2022-01-01, 2024-01-01) |
| første RV-døgn (basisbaren skal ligge i vinduet) | 2020-03-02 (baren 2020-02-29 23:00 læses ikke) | 2022-01-02 (baren 2021-12-31 23:00 læses ikke) |
| HAR-spænd til første mål (395 døgn) | 2020-03-02 .. 2021-03-31 | 2022-01-02 .. 2023-01-31 |
| første mål | **2021-04-01**: input-barer til 2021-03-31 22:00, cutoff 2021-03-31 23:00, lås 23:30, reveal 2021-04-02 01:00 | **2023-02-01**: se afsnit 2 |
| sidste mål | **2021-12-31**: sidste inputbar 2021-12-30 22:00, cutoff 2021-12-30 23:00, lås 23:30; målets barer 2021-12-30 23:00 .. 2021-12-31 22:00, komplette 2021-12-31 23:00 | **2023-12-31**: sidste inputbar 2023-12-30 22:00, cutoff 2023-12-30 23:00, lås 23:30; målets barer 2023-12-30 23:00 .. 2023-12-31 22:00, komplette 2023-12-31 23:00 |
| højeste bar, der behøves | 2021-12-31 22:00 (endelig 2021-12-31 23:00) | 2023-12-31 22:00 (endelig 2023-12-31 23:00) |
| antal mål | **275** | **334** |
| prognose, der aldrig laves | cutoff 2021-12-31 23:00 → mål 2022-01-01 (train3) | cutoff 2023-12-31 23:00 → mål **2024-01-01 (holdout)** |

Til sammenligning:

| | Mål |
|---|---|
| A23 (første RV-døgn = vinduets start; NOV14/C1's tal) | explore0 2021-03-31 .. 2021-12-31 = 276; bekræftelsen 2023-01-31 .. 2023-12-31 = 335 |
| train3 alene (B23) | 2023-02-01 .. 2023-06-30 = 150 |
| validation3 alene | 0 (184 døgn < 395) |
| med overført historik (MATERIEL) | 730 i bekræftelsen, som den låste styrketabel antager |

A23 og A24 rører grænsen i informationstid: deres sidste bekræftelsesmål behøver bar 2023-12-31 23:00, der først er
endelig **2024-01-01 00:00:00**. Den er stadig 2023-data, men grænsen er nået. B23 behøver aldrig noget, der er
endeligt ≥ 2023-12-31 23:00.

## 4. HAR-række- og lagjustering (eksempel: L = 2023-01-31, prognose for 2023-02-01)

- Prognosens features (oprindelse L):
  - RV_{2023-01-31};
  - mean(RV_{2023-01-25..2023-01-31});
  - mean(RV_{2023-01-02..2023-01-31}).
- Regressionsrækker: mål τ ∈ [2022-02-01, 2023-01-31] (365 rækker). Række τ bruger features med oprindelse τ−1.
  - Den ældste række (τ = 2022-02-01) bruger mean(RV_{2022-01-02..2022-01-31}).
  - Spændet er derfor 2022-01-02 .. 2023-01-31 = 395 døgn.
- Intet feature-døgn ≥ τ i nogen række. Intet døgn > L i prognosen. Måldøgnet 2023-02-01 læses aldrig.

## 5. Brudte serier (syntetiske eksempler fra testene)

| Tilfælde | Følge |
|---|---|
| ét manglende close i døgn D (fx bar D 05:00) | RV_D findes ikke; udfyldes aldrig |
| manglende bar D−1 23:00 (embargotimen) | RV_{D−1} findes stadig; RV_D findes ikke (manglende basis) |
| fladt døgn (alle closes ens, RV = 0) | behandles som ufuldstændigt (QLIKE udefineret), tælles |
| hul ved L−10 | EWMA-løbet starter L−9 (10 døgn < indkøring 50 → ingen prognose); HAR: ingen prognose |
| hul ved L−60 | EWMA-løbet starter L−59 (60 døgn ≥ 50 → prognose, rekursion fra RV_{L−59}); HAR: ingen prognose (395 kræves) |
| 1.000 sammenhængende døgn | EWMA-løbet afkortes til 395 døgn (startvægt 0,94^394 ≈ 2·10⁻¹¹) |
| én manglende bar i vinduet (4.415/4.416 i validation3, > 99 %) | mønten udgår ved 100 %-reglen |

## 6. Testliste (`tests/test_research_f2_timeline.py`, 35 tests)

| Krav (ordre 53) | Test |
|---|---|
| intet inputtidsstempel ≥ målstart | `Timeline.test_no_input_timestamp_at_or_after_target_start` (alle 609 mål; tilgængelighed og `close_time`) |
| lås < målstart (med margin) | `Timeline.test_lock_before_target_start_with_margin`, `Timeline.test_example_2023_02_01` |
| 23-afkasts-konventionen deler intet mærke med målet | `Timeline.test_b23_no_shared_mark` |
| 24-afkastsvarianten markeres, når sidste close tages ved målstart | `Timeline.test_a24_flagged_last_close_at_target_start` (NO_MARGIN, fælles mærke), `Timeline.test_l24_off_by_one_is_content_leak` (LEAK), `Timeline.test_a23_no_margin` |
| 365 rækker kræver 395 komplette døgn | `HAR.test_365_rows_need_395_complete_days` |
| et manglende døgn genstarter EWMA-løbet | `EWMA.test_missing_day_restarts_run`, `EWMA.test_burn_in`, `EWMA.test_run_truncated_to_har_span` |
| vinduesgrænsen når aldrig 2024-01-01 | `Windows.test_window_edge_never_reaches_2024`, `Windows.test_explore0_isolated`, `Windows.test_a_conventions_touch_the_boundary` |
| HAR-lags indeholder aldrig måldøgnets afkast | `HAR.test_lags_never_include_target_day`, `HAR.test_poisoned_target_never_read` |
| øvrige | kline-fakta og validering, RV-værdi, ingen udfyldning, flade døgn, fuld dækning, QLIKE, lige vægt, HAR-gulv, vinduestællinger, styrke (låst tabel genskabt; 334/335/275/276), W0-oversættelse, ingen netværks- eller dataimport, deterministisk output |

Resultat 2026-11-06: `python3 -m unittest tests.test_research_f2_timeline tests.test_research_gates
tests.test_lab_safety` → 47 tests OK.
