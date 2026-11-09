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

## Tillæg 21:54 lokal: endnu en test læste filen, og den parsede indholdet

Under kortlægningen for ordre 73 blev en test mere fundet.

| Felt | Indhold |
|---|---|
| Test | `tests/test_research_n6_n4.py`, `Refusal.test_pair_file` |
| Adgangstype | **`open` + `json.load`: filen blev parset, ikke kun hashet.** Testen sammenlignede felter (antal par, at BTC og USDT ikke var med, multiplikatoren for ét navngivet par) |
| Kendt siden | oprettet i `7012c2b` (2026-11-02 10:20 lokal). `B_N4_QUARANTINE_AUDIT.md` omtaler den som tilladt efter ændring 40 punkt 2 |
| Kørsler | alle fulde suites siden 2026-11-02, også 2026-11-09 17:45–17:57 |
| Overspringningen fra kl. 18:15 | dækkede kun hash-testen, så denne test var stadig aktiv. Der har ikke været en fuld kørsel i tiden mellem overspringningen og ordre 73's isolation |
| Anvendt til forskning | Ingen dokumentation for det via testen. Testens kildekode nævner dog ét par og dets multiplikator, og den tekst ligger stadig i git-historikken |

Den første afgørelse kunne altså ikke bygge på det fulde billede. Direktørens vurdering af N4's uafhængighed bør tage højde
for parsingen.

**Git:** git selv kan læse filens bytes, fx ved `checkout`, `cherry-pick` eller når `git status` genberegner en fil med
ændret tidsstempel. Det er ikke målt og kan ikke udelukkes.

**Isolation (ordre 73 P2/P3):** begge tests er erstattet. Vagten afviser stien ud fra tekststrengen, før noget åbnes, og
en fuld kørsel afgør, om flere tests forsøger. En første målrettet kørsel viste vagten i funktion: den stoppede
`test_pair_file`, før filen blev åbnet (1 blokeret forsøg), og det er dokumentationen for, at vagten virker på den rigtige
sti.

## Tillæg 22:25 lokal: status efter direktørordre 74

**Status: `HOLDOUT_ACCESS_CONTAMINATED`.** Det dokumenterer adgangsbruddet og er ikke en påstand om, at nogen bevidst har
tilpasset en strategi til dataene. Originalfil, historik og protokol bevares uændret. Registeret `QUARANTINE.json` er pinnet og ændres
ikke; status står her.

**Adgang:** hashing (`test_files_exist_unchanged`) og JSON-parsing (`test_pair_file`).

**Felter testen undersøgte:** `overlap` (lig antal par), `pairs` (nøglerne: to navngivne symboler var ikke med), og `multiplier` for ét
navngivet par. Den eksakte test står i commit `7012c2b` og gentages ikke her.

**Kendt adgangshistorik:** testene siden 2026-11-02 (`7012c2b` og `8fac269`). Selve listen blev bygget 2026-11-02, se `B_N4_QUARANTINE_AUDIT.md`.

**Ukendt:** antal kørsler i alt, kørsler uden for dev, git's egne læsninger og øvrige åbninger før isolationen.

**Betydning:** N4 må ikke bruges som uberørt, uafhængigt bevis for en ny strategi. Enhver senere brug kræver en særskilt
protokolbeslutning og tydelig oplysning om kontamineringen. Det gælder også en N4-lås, som tidligst var mulig 14/11. Ingen flere
filåbninger, heller ikke til hashing.

**Testindgange (ordre 74 P0):** `python3 -m unittest tests.x` og `scripts/suite_parallel.sh` via `tests/__init__.py`; `unittest discover -s tests`
(`scripts/suite.sh`) via `tests/test_000_quarantine_guard.py`; den beskyttede loader via `protected`. Prøvet på en syntetisk checkout. Direkte kørsel
af én testfil (`python3 tests/test_x.py`) er ikke en understøttet indgang og er ikke dækket af vagten.
