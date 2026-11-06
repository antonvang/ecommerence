# MUTATION_REVIEW: Claudes egen verifikation af Codex-runde 3 (direktørordre 52 P0)

Status: **P0 GO (syntetisk)**. Ingen sikkerhedskritisk mutant overlevede i nogen fase. Målet på ≥ 90 % for de øvrige blev
først nået efter supplering (73 % → 100 %). Det står åbent her og er ikke skjult.

## 1. Proveniens

- Codex' branch `codex/mutation-r3` har commit `2177763`, og dens forælder er `1314bdf` (frossen v1.1.1). 170 filer
  ændres, alle under `research/desk/codex/r3/` (verificeret med `git diff --name-only`). Branchen er merget.
- Den aktive evaluator `crosscheck/claude_eval_v111.py` har stadig sha256 `dbac993c37c6…`, som er lig med
  `EVALUATOR_V1_1_1.lock` (både før og efter merge og kørsel). Ingen mutant blev anvendt på den aktive evaluator eller
  på lab'en.

## 2. Egen genkørsel (stoler ikke kun på Codex' tal)

- Codex' `run_mutants.py --phase both` havde stien `/workspace/work` hårdkodet fra Codex' miljø.
- Jeg kørte en midlertidig kopi, hvor kun den sti var udskiftet med en scratchpad-mappe. Kopien er slettet bagefter, og
  repo-filen er uændret.
- Resultatet er **identisk** med Codex' `MUTATION_RESULTS.json` på alle felter, og detected_by er ens for alle 45
  mutanter:

| Fase | Sikkerhedskritiske | Øvrige ikke-ækvivalente | Overlevende |
|---|---|---|---|
| Første fase | 28/28 = 100 % | 11/15 = 73,3 % | M23, M27, M41, M45 |
| Efter supplering (3 målrettede fixtures + 1 test med skriveafbrydelse) | 28/28 = 100 % | 15/15 = 100 % | ingen |

Ækvivalente mutanter (holdt uden for nævnerne) er M43 og M44, og jeg har selv kontrolleret dem:
- M43 bytter `abs(r) > 0.5` ud med `r > 0.5 or r < -0.5`. Det er ens for endelige r, og NaN/inf er afvist tidligere.
- M44 bytter `T >= 30` ud med `T > 29`. Det er ens, fordi T er et heltal.

Triviel detektion via sha256 (45/45) er holdt adskilt fra adfærdsdetektion. Codex dokumenterer 28 "stille vidner":
mutanter med exit 0, status OK og uændrede statusfelter, men forkerte tal. Eksempler er M09 (funding-fortegn), M10
(omkostning på position), M11 (bps-enhed), M13 (omkostningstotal), M17 (tæller for manglende funding) og M35
(ledger-hash).

## 3. Vurdering af de fire første overlevende

| Mutant | Fejl | Codex' klasse | Min vurdering |
|---|---|---|---|
| M23 | Dubletter tælles med i Holm-nævneren | ØVRIG | Enig, men den ligger på grænsen. Et større m gør Holm **mere** konservativ, så det giver tabt styrke, ikke falske afvisninger. Den ville dog skjule et ægte fund og er nu fanget. |
| M27 | BH bruger alpha i stedet for q_fdr | ØVRIG | Enig. BH er kun diagnostisk. |
| M41 | Ikke-atomisk skrivning af den endelige fil | ØVRIG | Enig, men den ligger på grænsen. Et nedbrud midt i skrivningen kan efterlade en delvis fil. Den er ikke gyldig JSON og giver derfor ikke et falsk resultat. Den er nu fanget af en test med skriveafbrydelse. |
| M45 | Afkast på præcis 0,5 tælles som ekstreme | ØVRIG | Enig. Det rammer kun en rapporteringstæller. |

## 4. Konsekvens

- Testsuiten og fixtures fanger nu alle 43 ikke-ækvivalente realistiske fejl, herunder 28 sikkerhedskritiske. De nye
  fixtures og tests ligger i `codex/r3/` og bliver en del af regressionen.
- Ingen tolerance eller forventet output er ændret. Codex' første rapport er bevaret med hash-forankring
  (`SUPPLEMENT_PLAN.json`, `MUTATION_RESULTS_INITIAL.json`).
- Begrænsninger: mutanterne er Codex' valg, og mutation testing måler kun de fejl, man tænker på. Alt er syntetisk.
  Harnessen er afhængig af Codex' miljøsti, hvilket er en mindre portabilitetsfejl, som bør rettes i v1.1.2-harnessen.
