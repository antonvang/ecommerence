# Sikkerhedsafvigelse: hashing af N4-parlisten (direktørordre 73 P1, append-only)

Skrevet 18:18 lokal, 2026-11-09. Tilføj kun nye afsnit; ret ikke i det, der står.

| Felt | Indhold |
|---|---|
| Test | `tests/test_research_gates.py`, `Quarantine.test_files_exist_unchanged` |
| Fil | `research/data/N4_KIMCHI_PAIRS_2026-11-02.json` |
| Adgangstype | byte-læsning med `open(..., "rb")` og SHA-256; sammenligning med registerets hash; indholdet printes ikke |
| Første kendte adgang via testen | testen kom ind i commit `8fac269` (2026-11-02 23:41 lokal, ændring 40) |
| Dokumenterede kørsler 2026-11-09 | fuld guarded suite 17:45–17:57 og det målrettede modulkald ca. 18:05 |
| Øvrige kørsler | alle fulde suites i dev siden 2026-11-02. Antallet er ikke talt op, og produktionens kørsler er ikke undersøgt |
| Anvendt til forskning | Ingen dokumentation for det via denne test. Testen bruger kun hashen |
| Agenter 2026-11-09 | begge rapporterer 0 åbninger i deres worktrees (filen var holdt ude) |

**Usikkerheder:** dette er ingen påstand om, at filen aldrig er åbnet på anden måde. `B_N4_QUARANTINE_AUDIT.md` beskriver
tidligere brug før karantænen. Testvagtens fil-guard dækker ikke stien, så "file-guard 0" i rapporterne siger intet om
denne fil.

**Status:** testen springes over i den lokale testvagt (direktøren: GO). Testen i repoet er uændret, så et almindeligt
`unittest`-kald hasher stadig filen, indtil P2 er udført. Filen er ikke rørt under denne registrering.
