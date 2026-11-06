# CODEX_REVIEW_TASK — uafhængig reference-evaluator (direktørordre 50 P3)

Status: DONE 2026-11-06 — Codex leverede (miljø ecommerence, branch codex-crosscheck); resultat i CROSSCHECK_REPORT.md.

## Opgave til Codex

Du er en uafhængig kontrollant. Byg en reference-evaluator **udelukkende ud fra**
`copybot/research/desk/crosscheck/EVALUATOR_SPEC.md` og kør den på alle fixtures i
`copybot/research/desk/synthetic_fixtures/*.json`.

Regler for uafhængighed:
- Læs IKKE nogen anden kode i repoet. Det gælder især `copybot/research/tools/`, `copybot/lab/`,
  `copybot/research/desk/crosscheck/*.py` og `copybot/tests/`. Fixture-generatoren `make_fixtures.py` må heller ikke
  læses, for den afslører de indplantede fejl.
- Kun Python 3 standardbibliotek. Intet netværk. Ingen markedsdata.
- Ret ikke i specifikationen eller i fixtures. Hvis specifikationen er tvetydig, så vælg den mest bogstavelige læsning,
  og skriv tvivlen i `copybot/research/desk/codex/SPEC_QUESTIONS.md` med afsnitsnummer.

Leverancer, kun under `copybot/research/desk/codex/`:
1. `ref_eval.py` med `evaluate(fixture: dict) -> dict` efter spec afsnit 8, og en CLI:
   `python3 ref_eval.py <fixture.json>... --out <dir>` skriver `<fixture_id>.json` som kanonisk JSON.
2. `outputs/<fixture_id>.json` for alle seks fixtures.
3. `test_ref_eval.py` med egne enhedstests af hver regel i afsnit 2-7, skrevet ud fra spec'en.
4. `SPEC_QUESTIONS.md`: tvetydigheder eller huller i spec'en, med dit valg.
5. `REVIEW_NOTES.md`: kort om de risici, du ser for look-ahead, omkostninger, HAC, Holm/BH, ledger, dubletter, huller
   og survivorship i en evaluator som denne.

Tjek, at to kørsler giver byte-identisk output.
