# Kandidat 83: rækkefølge (uanvendt; direktørordre 83)

Ingen af filerne er anvendt. Hver kræver de godkendelser, der står i `research/desk/ORDER83.md`. Tests:
`tests/test_candidate_83.py` og `tests/test_source_completeness_83.py`.

| Trin | Fil | Erstatter | Rører |
|---|---|---|---|
| 1 | `83_candidate_1_observability.diff` | 72 + 81 observability (byte-identisk med dem lagt i rækkefølge) | `lab/ops.py`, `fleet.py`, `mission.py`, `coverage.py`, `risk.py`, `lane.py`, `watch.py` |
| 2 | `83_candidate_2_close.diff` | 82 (80 og 81 v2 bruges ikke; kun én close-version kan anvendes) | `lab/paper_runner.py` |
| 3 | `83_candidate_3_net_report.diff` | ny | `research/tools/net_report.py` (pinnet `e8cac57c`) |

Rækkefølgen er bindende:

- 2 forudsætter dev-motoren (59-D: `mark_guarded`), som produktionen (`85db922`) ikke har.
- 3 læser `paper.close_state` og `funding_id_at_terminal` fra 2. Uden 2 viser den intet nyt og ændrer ingen tal.
- 1 er uafhængig af 2 og 3. Den rører `lab.ops` og `lab.risk`, som pm_lp-collectorens genstart importerer (G12).

`research/tools/source_completeness.py` er et design, ikke en patch. Den kobles først ind ved en godkendt ændring af de pinnede `lab/straks.py` og `lab/pairs.py`.
