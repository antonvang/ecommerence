# Codex-runde 2 — blind adversariel kontrol

Udgangspunkt: `22240bbe30b5f2ffc93641e01d3254ccf86fb60e`, arbejdsbranch
`codex-crosscheck`. Eksisterende kilder læst i denne runde: kun
`crosscheck/EVALUATOR_SPEC_V1_1.md`, dens henviste v1-specifikation og egne
filer under `codex/`. Ingen Claude-evaluator, generator eller tests blev læst
eller kørt. Netværk blev kun brugt til det bestilte fetch. Sættet påstår ikke
at have fundet en fejl i Claude; det indeholder angreb til en efterfølgende
blind sammenligning. Ingen konklusioner om alpha eller handelsresultater.

`make_r2_fixtures.py` genererer 47 nye, små syntetiske inputs fra konstanter
og seed 5100. Den læser hverken evaluator, eksterne data eller gamle fixtures.
Hver fixture har højst 32 forskellige observationstider og højst fire assets;
de gyldige vinduer har højst 32 gitterbars. Malformed-container-fixturen er
bevidst ugyldig. Filnavne, byteindhold og manifest er deterministiske.

## Reproduktion

Fra repository-roden, med Python 3.12.14 og kun standardbibliotek:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 copybot/research/desk/codex/r2/make_r2_fixtures.py
PYTHONDONTWRITEBYTECODE=1 python3 -I copybot/research/desk/codex/ref_eval.py copybot/research/desk/codex/r2/fixtures/*.json --out copybot/research/desk/codex/r2/expected
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s copybot/research/desk/codex -p test_ref_eval.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s copybot/research/desk/codex/r2 -p test_r2.py -v
```

42 enhedstests og otte R2-tests består. De otte R2-tests omfatter analytiske
orakler, generatorens determinisme, alle otte valideringskoder, størrelsesloft,
uændret input, kanonisk kodning, to separate CLI-kørsler og restart. Der er 34
OK-fixtures og 13 INVALID_INPUT-fixtures. Alle forventede outputs er kanonisk
JSON uden afsluttende newline. `manifest.json` indeholder inputhash og
angrebsklasse; `RESULTS.md` indeholder både inputhash og outputhash.

Den gamle `codex/outputs/` er bevaret som historiske v1-resultater.
V1.1-forventningerne findes kun i `r2/expected/`.

## Restart og afbrudt output

`test_r2.ArtifactTests.test_cli_two_runs_restart_and_expected_bytes` opretter
i en midlertidig mappe en `R2_42_restart.json`, hvis bytes er en afbrudt
JSON-prefix. Den efterlader også en separat fil med simulerede afbrudte
temp-bytes. CLI'en køres to gange på alle 47 inputs. Efter hver kørsel skal
alle endelige filer være byte-identiske med `expected/`; output må ikke være
appendet eller indeholde newline. En uvedkommende gammel tempfil må ikke
blive læst som resultat. Testen fjerner sin egen mappe bagefter.

`test_ref_eval.Version11Tests.test_atomic_replace_restart_and_replace_failure`
kontrollerer desuden et simuleret svigt i `os.replace`: den gamle komplette
fil bevares, og den nye midlertidige fil ryddes op. Det er en deterministisk
fejlinjektion, ikke et bevis for holdbarhed ved strømsvigt. Der kræves ikke
genbrug af eventuelle gamle tempfiler. Atomicitet og erstatning opnås med en
ny tempfil i samme mappe, flush/fsync, lukning og `os.replace`.

## Hvad der især kan afsløre fejl

- R2_01: fremtid med kun ét sekund er nok til look-ahead; ret-MISSING har
  forrang og må ikke tælle signal/funding. R2_05–07 og 46 angriber embargo.
- R2_02–04: fulde og delvise vendinger samt gratis nulstilling ved huller og
  MISSING. ANALYTIC.md giver selvstændige omkostningsorakler.
- R2_14: en naiv sum giver 0.75, mens den krævede fsum giver 1. R2_15–16
  ændrer skala uden at ændre den analytiske t-værdi.
- R2_17–20: perfekte korrelationer, lige p-værdier, m=1, Holm-stop og BH's
  største kvalificerende rang. R2_21–23 angriber DUPLICATE-forrang.
- R2_24–27: payloadkonflikter, forskellige ts, genforsøg efter afvisning,
  0 versus 0.0 i hash og nøjagtig family-summering.
- R2_28–39 og 45/47: alle fejlkoder, flere samtidige fejl, låse på råt
  protokol/data og malformed containers. Ingen statistik eller ledger må
  slippe gennem ved INVALID_INPUT.

Nye fortolkningsspørgsmål er i SPEC_QUESTIONS.md i denne mappe. Der er ikke
udvidet på specifikationens sammenligningstolerance.
