# Uafhængig referencekontrol — direktørordre 50 P3

Dette er det historiske resultat fra runde 1. `ref_eval.py` og egne tests
er siden opgraderet til v1.1 i direktørordre 51 P0; se `r2/README.md`,
`r2/ANALYTIC.md`, `r2/SPEC_QUESTIONS.md` og `r2/RESULTS.md` for runde 2.
De seks oprindelige v1-outputfiler nedenfor er bevaret uændret.

Kontrollen vedrører udelukkende syntetiske fixtures og implementering af
EVALUATOR_SPEC v1. Der drages ingen konklusioner om alpha eller handelsresultater.

## Proveniens og uafhængighed

- Kildebranch: `claude/why-cant-we-do-this-wh3ohb`.
- Lokal arbejdsbranch: `codex-crosscheck`.
- Udgangspunkt: `d0806105ee2e8e1ddbfd0fc13a720323f07cf621`.
- Læste eksisterende filer: `crosscheck/CODEX_REVIEW_TASK.md`,
  `crosscheck/EVALUATOR_SPEC.md` og de seks JSON-fixtures. Katalog- og
  Git-metadata blev undersøgt for at finde repo, branch og eventuelle AGENTS.md;
  ingen AGENTS.md blev fundet.
- Ingen anden repository-kode blev læst, importeret eller kørt. Ingen kode læst
  fra `research/tools/`, `lab/`, `tests/` eller `crosscheck/*.py`, heller ikke
  `make_fixtures.py`. Egne tests bruger håndskrevne data og ingen fixtures som
  forventningsfacit. Ingen sammenligning med en anden evaluators output.
- Branchhentning krævede det udtrykkeligt bestilte Git-fetch. En read-only
  GitHub-branchopslagning bekræftede branchens eksistens, mens standard-shellens
  proxyforbindelse fejlede. Fetch lykkedes derefter med shellens netværksadgang.
  Evaluator, fixturelæsning og tests bruger kun Python 3-standardbibliotek og
  lokale filer; de foretager ingen netværkskald og bruger ingen markedsdata.
- Alle repository-ændringer er under `research/desk/codex/`. Specifikation og
  fixtures er uændrede.

## Fixture-SHA-256

| Fil | SHA-256 |
| --- | --- |
| F1_clean.json | `3c5debad5d902c038406448f485f8b1fc0641ad70b68eea23b58faf7003b3aa2` |
| F2_lookahead.json | `59edbbaf10392566e9767e42d84a9c279e8abd9d657146db031ae14be2fccf43` |
| F3_gaps_nan.json | `88f2d58d109dbf7fc9759c85a2227466252f7401591dae4a83a495aa2cce909e` |
| F4_survivorship.json | `d16e361e1d230e86479a0bb47ee4e5fbf99b3c372dff7b724f96322f232bac73` |
| F5_extreme_dupes_offgrid.json | `3c4c0ad8c9760ac640eea820852b7a85060be9a49e3d58527853d75b9e135461` |
| F6_short.json | `058c04fbdb0dbb31e19c0ccb306f8bf04f4c6fff88b51a037167493073f2595d` |

## Kontroller og reproduktion

Fra repoets rod:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s copybot/research/desk/codex -p test_ref_eval.py -v
python3 -I copybot/research/desk/codex/ref_eval.py copybot/research/desk/synthetic_fixtures/*.json --out copybot/research/desk/codex/outputs
```

Kørselsmiljø: Python 3.12.14, Clang 22.1.3. Python-versionen er relevant for
`sum`- og flydende tal-konventionerne beskrevet i SPEC_QUESTIONS.md.

32 egne tests er grønne. Testene dækker afsnit 2–7 samt outputskema, kanonisk
UTF-8, CLI, flere inputfiler, uændret input og gentagne kørsler. HAC kontrolleres
blandt andet analytisk med en alternerende serie: T=30, L=3, S=1/30, se=1/30.
Ledgerens første to hashpræimages er skrevet eksplicit i testen. Holm/BH testes
med konstruerede p-værdier, herunder et tilfælde, hvor Holm stopper straks og
BH afviser alle, samt grænselighed, dubletter og utilstrækkelige hypoteser.

Alle seks fixtures er kørt i to separate isolerede Python-processer med hver
sin outputmappe. De seks par er byte-identiske. Hver fil er også kontrolleret
mod præcis kanonisk JSON-kodning uden afsluttende newline og uden ikke-endelige
værdier. Midlertidige outputs fra anden kørsel blev fjernet efter kontrollen.

| Outputfil | Bytes | SHA-256 |
| --- | ---: | --- |
| F1_clean.json | 1763 | `5548df86cbc2751bb78a424d5a221a654a6d60dd54ace89edd54a4765be70562` |
| F2_lookahead.json | 1772 | `19eb445467735cf24325e592cb5543f84b1ec632dd44f287fdea05812cf71b0e` |
| F3_gaps_nan.json | 1792 | `033ea202b27d32d5678a1032be235c69ad570215829711a40c277da8d9b0671b` |
| F4_survivorship.json | 1775 | `59d2cc5bcf4cc6dc5ea9304db787f1f1295671680b34b09159978195ffc1098c` |
| F5_extreme_dupes_offgrid.json | 2407 | `b3d4d583bc9438b31d0d45a081f4e9092addc32b76905b508e8db0318731f761` |
| F6_short.json | 1642 | `7c699981e49f1bed9bad8c665a06d913629e29604a40f0e748274814b83a0c32` |

## Risici i denne type evaluator

- **Look-ahead:** `avail_ts <= ts` er tilladt; fremtidige endelige signaler
  skal give nulposition og kan stadig koste en lukning. Signalets angivne
  tilgængelighed efterprøves ikke mod nogen ekstern kilde. Et ugyldigt signal
  tælles som signal-missing før availability kontrolleres.
- **Omkostninger og funding:** turnover er pr. asset i vægte og inkluderer
  indgang, vending og skift til nul. Et hul/MISSING nulstiller gratis efter
  specifikationen. Den konvention kan afvige fra et system med vedvarende
  positioner. Funding med fortegn fratrækkes også ved korte positioner;
  manglende funding erstattes af nul og optælles. Totalerne er summer over
  asset-bars, mens porteføljeafkast er gennemsnit pr. bar.
- **HAC:** Newey-West bruger divisor T ved alle lags, Bartlett-vægte og
  normal-approksimation med ensidet erfc-hale. Tidsafstande over huller
  komprimeres i serien efter afsnit 4. Kort serie eller S <= 0 må ikke komme i
  testmængden. Næsten nul varians og store tal kan give numerisk følsomhed;
  der foretages ingen egen regularisering. Ekstremer beholdes og kan dominere
  gennemsnit og HAC.
- **Holm/BH og hypotesedubletter:** kun status TESTED indgår i m; ingen
  opdeling pr. family. Holm stopper ved første ikke-afvisning; BH søger
  største kvalificerende rang og er kun diagnostisk. Fingeraftrykket udelader
  cost og funding, så en dublet kan have anden statistik, men stadig være
  udelukket. Identiske idéer under andre signalnavne opdages ikke.
- **Ledger:** kun accepterede nøgler er idempotente; genbrug af en accepteret
  nøgle skjuler også et ændret payload. Afviste nøgler kan prøves igen. Bool,
  float og nul skal afvises som variants. Request-rækkefølge, taltyper og UTF-8
  påvirker hash; sekvensen er ikke sorteret efter ts. Hashkæden alene giver
  ingen ekstern forankring, holdbar lagring eller beskyttelse mod omskrivning
  af hele kæden. Denne evaluator genafspiller requests i hukommelsen.
- **Rækkedubletter:** første række i filen vinder, også hvis dens afkast er
  ugyldigt; senere bedre data bruges ikke. Off-grid-rækker filtreres først.
  Tællernes overlap kræver den eksplicitte konvention i SPEC_QUESTIONS.md.
- **Huller:** rå gittertid uden rækker er gap; rækker uden gyldige medlemmer
  er empty. Nulposition med gyldigt afkast er stadig en porteføljeobservation.
  Assets med ugyldigt afkast udelades fra nævneren; der indsættes ikke nulafkast.
- **Survivorship:** medlemsskab afgøres på hver observation med inklusiv
  listed_from og eksklusiv delisted_at. Historikken før afnotering beholdes,
  og nye assets optages først ved listed_from. Korrektheden afhænger af det
  leverede univers; fremtidige metadata kan ikke opdages af evaluatoren.

Skemavalidering, numerisk overflow og andre konventionshuller er afgrænset i
SPEC_QUESTIONS.md. Denne kontrol er ikke en sammenligning med anden kode.
