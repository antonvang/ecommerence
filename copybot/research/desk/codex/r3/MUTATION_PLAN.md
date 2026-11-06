# Mutation lab — direktørordre 52 P0

## Afgrænsning og låse

Arbejdsbranch oprettes fra `1314bdfd2b6566f29fc6dd4cd8bdf3fbaf6ef55c`.
Den aktive evaluator, lab-kode, tests, specifikationer og eksisterende
forventede outputs ændres ikke. Kun filer under `codex/r3/` leveres.
Ingen markedsdata; kun lokal syntetisk evaluering og Git-netværk til overførsel.

Den frosne evaluator har SHA-256
`dbac993c37c61d5917e34ae4d16b78640c748782e1e00712bbd6065f80074fec`.
Før Claude-kode/tests blev åbnet, blev egen `r3/ref_eval.py` opgraderet
alene fra specifikationerne og syv egne tests kørt grønne. Kildens hashes
står i REFERENCE_PROVENANCE.json. De første 76 nye forventninger (6 R1,
47 R2, 23 R3) er låst i EXPECTED_INITIAL_SHA256.json. De skrives aldrig om
af mutationsharnessen. Ældre `codex/outputs/` og `r2/expected/` bevares.

## Baseline før mutation

Den uændrede Claude-evaluator skal bestå alle 25 tests fra de tre bestilte
testfiler efter importsubstitution. Dens output sammenlignes felt for felt
med den uafhængige reference. Tolerance er præcis
`abs(a-b) <= 1e-9*max(1,abs(a),abs(b))`; status, struktur, bool, fejl og
hashes sammenlignes eksakt. Ingen tolerance udvides.

75/76 initiale fixtures matcher. R3_13_numeric_ledger har samme NUMERIC_ERROR,
kode og fravær af delresultater, men en forskellig fejlsti: reference `""`,
Claude `"OverflowError"`. Specifikationen angiver `path: ...` uden en konkret
sti for fangede aritmetikundtagelser. Referencen og forventningen bevares;
afvigelsen rapporteres i BASELINE_COMPARISON.json. En kandidat får ikke en
mutationsdetektion alene ved at videreføre denne allerede kendte afvigelse.
Alle rå baseline-afvigelser bliver stående i resultaterne.

## Mutationer og alvor

`make_mutants.py` verificerer den frosne SHA-256 og fremstiller 45 isolerede
kopier med én fejlidé pr. fil i `mutants/`. Hver substitutionsplacering skal
findes præcis én gang, og filen skal kunne kompileres. Kopierne bruger den
oprindelige uændrede dependency `hypo_engine`; fejl i Holm-kaldet indføres
med lokale mutant-hjælpere, uden at ændre dependency eller aktiv evaluator.

Grupper: look-ahead/tid/gitter, medlemskab, position/omkostning/funding,
numerik/MISSING, rapportering, Holm/BH/fingeraftryk, ledger/replay/hash,
lock/protokol og restart/skrivning. Klassifikationen fastlægges i
mutant_manifest.json før første kørsel. SIKKERHEDSKRITISK bruges, når
fejlidéen kan medføre look-ahead, falsk TESTED/Holm-afvisning, forkert
alphaopkrævning eller accept af ugyldigt/låst-ændret input. Andre fejl er ØVRIG.

M43 og M44 er på forhånd identificeret som ækvivalente: en logisk omskrivning
af ekstremgrænsen for endelige tal og `T>29` i stedet for `T>=30` for heltals-T.
Begrundelserne gemmes pr. mutant. De indgår ikke i score-nævneren. Et fund
mod en påstået ækvivalent stopper kørslen og falsificerer klassifikationen.

Mindst fem mutanter skal have et konkret stille vidne: ændret output med
CLI-exit 0, samme fixture-status OK og samme status for alle hypoteser.
Vidner findes automatisk i harnessen, ikke ud fra et manuelt mærkat alene.
Alle mutanter skal desuden producere et normalt OK-output på den fælles
sanity-fixture R3_01; syntaksfejl og altid-crash er ikke gyldige mutanter.

## Detektion uden trivielle facitter

Hver testkørsel får en ny temp-kopi af de tre testfiler og kandidatfilen.
Begge importnavne `claude_eval_v11` og `claude_eval_v111` peger på kandidaten,
og factory-testens evaluatorimport rammer samme kandidat. De oprindelige
tools og lab-kode skrives ikke. Factory-testene bruger engangs-SSH-nøgler i
temp-mapper; der sendes ingen beskeder eller netværksrequests.

Den oprindelige lock kopieres uændret til temp-mappen. Derfor vil
`test_frozen_checksum` selvfølgelig fejle for alle byteændrede mutanter.
Dette er en reel integritetsdetektor og rapporteres særskilt. Den tæller
ikke som en adfærdsmæssig detektion: ellers ville enhver mutant og enhver
ækvivalent automatisk være fanget. Ingen test fjernes eller ændres.

Et semantisk fund er mindst én anden fejlet Claude-test eller en ny
fixture-afvigelse fra reference ud over den uændrede tolerance. Resultatet
angiver tests/fixtures/begge/ingen, testnavne, afvigende felter, checksum-fund,
baseline-arv og eventuelt stille vidne. Exitfejl og ukorrekt kanonisk JSON
registreres særskilt. Dermed kan det både ses, at produktionslåsen opdager
filændringen, og om kontrolsystemets adfærdstest også opdager fejlen.

## To faser

1. Initial: uændrede 25 Claude-tests og 76 allerede frosne fixtures.
   MUTATION_RESULTS_INITIAL.json gemmes før supplerende testarbejde.
2. Supplering: alle ikke-ækvivalente overlevende beskrives åbent. Nye
   fixtures/tests tilføjes separat; eksisterende fixtures og forventninger
   må ikke ændres. Der køres igen, og resultater før/efter bevares.

Målet vurderes på semantiske fund: 100 % af sikkerhedskritiske og mindst
90 % af øvrige ikke-ækvivalente. En kritisk overlever må ikke skjules med
checksum-fundet eller den kendte baseline-afvigelse.

## Reproduktion

Fra repoets rod:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 copybot/research/desk/codex/r3/make_mutants.py
PYTHONDONTWRITEBYTECODE=1 python3 copybot/research/desk/codex/r3/run_mutants.py --phase initial
# Efter dokumenteret supplering:
PYTHONDONTWRITEBYTECODE=1 python3 copybot/research/desk/codex/r3/run_mutants.py --phase augmented
```

`--phase both` genafspiller de to faser med de samme faseopdelte inputs.
Harnessen verificerer reference-, forventnings- og aktiv evaluator-hashes
før kørsel. Der må ikke skrives til den aktive kode som led i reproduktion.
