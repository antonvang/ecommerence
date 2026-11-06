# Vedvarende forsknings- og papirhandelskerne

Denne version forbinder forhåndsfastlagte forskningsforsøg, en holdbar jobkø,
uafhængig evaluering, fælles Holm/BH og en separat papirbog. Den kører lokalt
uden netværk. Den aktive evaluator, lab-kode og eksisterende forventede outputs
er uændrede. Ingen børsforbindelse, ekstern ordre eller produktionsservice er
aktiveret som del af dette arbejde.

## Kør hele den syntetiske kæde

Fra repository-roden, med Python-standardbibliotek og `ssh-keygen` til
signaturtests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 copybot/research/desk/codex/operations/research_runner.py demo --out /workspace/work/my-research --workers 3
```

Det opretter et uforanderligt studie med ni foreslåede kandidater: momentum,
reversal og funding-carry med lookbacks 1/3/6. Signalerne dannes af den frosne
opskrift; funding-carry bruger kun allerede afsluttede fundingperioder.
Ingen kandidat udvælges efter sit udfald. Alle data er syntetiske og dateret
2033 for at adskille dem fra observationer.

Filer i den valgte runtime-mappe:

- `study.json`: frosne protokoller, input, kildemetadata og risikogrænser.
- `jobs.sqlite3`: kø, leases, forsøg og transaktionelt gemte resultater.
- `report.json`: komplet batchstatus, fælles inferens og separate papirbøger.

Samme kommando kan køres igen. Identisk input genbruges, og allerede udført
arbejde handles eller opkræves ikke igen. Et ændret studie kan ikke bruge den
gamle kø under samme identitet; opret et eksplicit nyt studie og en ny mappe.
Det er ikke en mekanisme til at nulstille et forsøgsbudget efter et dårligt udfald.

## Hvad der faktisk er håndhævet

- SQLite-transaktioner og unikke leases forhindrer to workers i at færdiggøre
  samme job. Heartbeats holder lange job i live; gamle tokens kan ikke
  overskrive en ny worker. Fejl kan genforsøges inden for et fast budget.
- Hele studiets kandidater og tærskler låses før evaluering. Pooled Holm/BH
  offentliggøres først, når hele det forhåndsfastlagte batch er gennemført.
  Fingeraftryksdubletter tages ud af testmængden.
- Protokollen binder også den konkrete runner-, opskrifts-, kø-, godkendelses-
  og papirimplementering. En ny kodeversion kan ikke skjult genbruge den gamle
  kø eller en gammel protokols godkendelse.
- Begge v1.1.1-evaluatorer skal stemme for hver kandidat. Kode, testgrundlag og
  referenceforventninger kontrolleres af den hærdede mutationsgate.
- Evaluator og papirbog skal dele observationer, signaler, funding og prissti.
  Off-grid, embargo, ikke-medlemmer og manglende gitterrækker afvises i dette
  operative inputformat. Huller udfyldes ikke. Signaler rekonstrueres kausalt
  fra den godkendte opskrift; blot at kopiere et fremtidigt udfald til begge
  inputmodeller passerer ikke.
- Papirbogen køber på ask, sælger på bid, fratrækker fees og bogfører funding
  med positionsfortegn. Den har gross-/asset-caps og et vedvarende drawdownstop.
  Stale eller fremtidige quotes/signaler bruges ikke til fills. Stale
  restpositioner vises, indtil en frisk quote gør en lukning mulig.
- Et risikostop er et færdigbehandlet forskningsudfald, ikke en godkendt
  strategi: `paper_eligible` er false. Eventfejl kan aldrig skjules af
  risikostatus og give COMPLETE. Automatisk promotion er altid false.

Et COMPLETE-resultat betyder, at arbejdsgangen er udført. Det betyder ikke,
at en strategi er egnet til handel eller har dokumenteret et økonomisk resultat.
De ni demo-opskrifter er testprotokoller, ikke påståede dokumenterede edges.

## Fremadrettet papirhandel: den konkrete integrationskontrakt

Der er en testet vej for lokale, fremadrettede exports. En omdøbt syntetisk
fil er ikke nok: både ejerens forhåndsgodkendelse og indsamlerens datakvittering
skal kunne verificeres mod særskilt betroede offentlige nøgler. Der oprettes
ingen rigtig ejer- eller indsamleridentitet af programmet.

1. Fastlæg et datafrit protokolbundle med `mode=forward_paper`, kildeidentitet,
   adapterversion, kandidater, risikogrænser og fremtidige vinduer. Det er
   outputformatet fra `protocol_bundle()`; en færdig studiekladdes bundle kan
   eksporteres med `research_runner.py protocol study.json --out protocol.json`.
2. Ejeren signerer netop bundle-hashen med det eksisterende
   `owner_approval`-format. Registrér den, mens godkendelsen er gyldig og før
   det første vindue starter:

   ```sh
   python3 copybot/research/desk/codex/operations/research_runner.py freeze protocol.json --statement statement.json --signature statement.json.sig --owner-signers owner_allowed_signers --db /workspace/work/authorizations.sqlite3
   ```

   Programmet signerer aldrig for ejeren. Autorisationsregistret er en anden
   database end forskningskøen. En korrekt registreret forhåndsgodkendelse kan
   verificeres efter statementets korte udløbstid; tilbagekaldte trusted keys
   blokerer fortsat. Den lokale tid og filsystemet er trust-grænser; registret
   er ikke en ekstern tidsstempling.
3. Efter det frosne vindue leverer den konkrete adapter observationsdata,
   quotes, terminalmarks og en signeret capture-receipt. Studiets source er:

   ```json
   {"kind":"local_forward_export","source_id":"specific-stream","adapter_version":"v1","receipt":{},"signature":"armored SSH signature"}
   ```

   Receipten skal indeholde præcis `schema_version=1`, source_id,
   adapter_version, protocol_sha256, data_sha256, captured_from og captured_to.
   `data_sha256` er SHA-256 af `canonical(data_bundle(study))`; tidsgrænserne
   skal svare til hele det frosne studie. Kvitteringen signeres i namespace
   `copybot-forward-data` og verificeres for principal `collector`. Den
   signerede kildeidentitet og opskriften kan ikke ændres under samme protokol.
   Kilden skal desuden være EXISTING_ACTIVE i det hashbundne stream-register.
   Foreslåede/blokerede kilder, pm_lp og 2024-holdout afvises også med en
   gyldig signatur; ændringer i registret kræver en ny protokolbinding.
4. Submit og gennemfør den færdige, låste eksport:

   ```sh
   python3 copybot/research/desk/codex/operations/research_runner.py submit forward_study.json --db /workspace/work/forward/jobs.sqlite3
   python3 copybot/research/desk/codex/operations/research_runner.py run --db /workspace/work/forward/jobs.sqlite3 --out /workspace/work/forward/report.json --workers 3 --owner-signers owner_allowed_signers --collector-signers collector_allowed_signers --authorization-db /workspace/work/authorizations.sqlite3
   ```

Manglende godkendelse, kildekvittering eller et ufærdigt vindue holder jobbet i
kø uden at bruge retry-budget. Når forudsætningerne er til stede, genkøres
samme kommando. Ændres selve eksportens bytes, er det et nyt inputsnapshot,
som kræver en ny jobmappe; den oprindelige protokol kan stadig være den samme.

Der er endnu ikke koblet en rigtig indsamler, betroede ejer-/indsamlernøgler
eller et godkendt forward-export på denne installation. De eksisterende
datagates og særskilte stream-godkendelser fra FORWARD_DATA_PLAN.md bevares.
Der hentes ikke markedsdata, bruges historiske forespørgsler eller startes
nye streams i denne ændring.

## Friske helbredskontroller

```sh
PYTHONDONTWRITEBYTECODE=1 python3 copybot/research/desk/codex/operations/research_runner.py doctor --out /workspace/work/research-health --full
PYTHONDONTWRITEBYTECODE=1 python3 -O -m unittest discover -s copybot/research/desk/codex/operations -p 'test_*.py' -v
```

Den hærdede R3-harness bruger eksplicitte gates, der består under Python -O.
Den accepterer kun den ene eksakt fastlagte baseline-afvigelse og afviser nye
afvigelser. Et pinnet manifest låser 238 kontrolfiler; TRUST_BOOTSTRAP.md
forklarer trust-grænsen og hvordan en bevidst versionændring reviewes.
Nye kørselssammenfatninger får run-id og aktuelle kildehashes. Historiske
mutationsrapporter omskrives ikke og bruges ikke som frisk driftsstatus.

## Præcise modelgrænser

Papirmotoren bruger leverede top-of-book-quotes. Den modellerer ikke
ordrebogsdybde, delvise fills, latens eller en børsforbindelse. Evaluatorens
vægt-/afkastmodel og papirbogens cash-/quote-model er bevidst forskellige og
må ikke påstås at være et afkast-krydskontrolpar. `paper_valuation_ts` er den
sidste leverede bar-start-quote; evaluatorens sidste bar bruger den særskilte
terminalmark ved `evaluation_window_end`. Ingen skjult slutlikvidation eller
ekstra handel tilføjes for at få tallene til at ligne hinanden.

Denne kerne gør forsøg hurtige, holdbare og kontrollerbare. Litteraturvurdering,
økonomisk begrundelse, styrke og længere forward-evidens skal stadig indgå i
den konkrete protokols kvalifikation. En demo eller mutationstest erstatter
ikke disse krav og åbner ikke en allerede parkeret eller afsluttet hypotese.
