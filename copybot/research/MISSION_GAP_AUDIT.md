# Missionsaudit: fra batch-screener til kontinuerlig research- og papirhandelsmotor (2026-10-18)

Formål: at holde det eksisterende Copybot-system op mod brugerens langsigtede mission (9 punkter) og lukke hullerne
trinvis i de eksisterende komponenter. Der bygges intet parallelt system, og ingen gate svækkes.

Metode: fem audit-spor (kode med fil:linje og live-beviser fra `lab.db`/logs, kun læsning) plus en kritiker, der
efterprøvede de vigtigste påstande. Hvert trin er bygget med tests, adversarial review, fuld testsuite på den præcise
commit i en isoleret Linux-worktree, deploy og live-verifikation.

## 1. Status pr. missionspunkt

| # | Missionspunkt | Fandtes før | Lukket 2026-10-18 | Største åbne hul | Næste skridt |
|---|---|---|---|---|---|
| 1 | Løbende research af markeder og ændringer | Scanner hver time (2 detektorer), observationer i hash-kæden | Hvert forslag får en registreret beslutning (`market.event`: INGEN HANDLING/UNDERSØG), 24 t-vedvarenhed, SUPPRESSED som kirkegård, søgningen synlig i feed og globus (ændring 5) | Ingen analyserer observationsstrømmen over tid; listing/delisting og ændringer i belønningspuljer ses ikke | Daglig ikke-afgørende scanner-sammenfatning og en ændringsdetektor uden nye kald (ændring 9) |
| 2 | Mange uafhængige jobs parallelt inden for kapacitet | Jobkø med leases, 2 tunge slots, RAM-adgang | Et stop er ikke en fejl, leases ryddes før workers starter, ødelagt pulje erstattes, flåden overlever databaselåse (ændring 6) | Ingen job-timeout med kill; én data-agent; netværksfejl bruger forsøg | Killable jobproces, data-2 + download-semafor, udskydelige netværksfejl |
| 3 | Generere, teste, afvise og forbedre hypoteser | 28 katalogskabeloner, godkendelse, `register_batch` | — | **Ingen generator: kataloget er opbrugt, 11 af 16 agenter står uden arbejde** | Forhåndsregistrerede hypotesefamilier, kun ikke-prisforudsigelse (ændring 8, besluttet af brugeren; i design) |
| 4 | Stoppe dårlige hypoteser hurtigt og huske hvorfor | Train-gate, placebo, DSR, kirkegård | Ikke-afgørende diagnoser af afsluttede eksperimenter (12 live, hash-kædede), strammere holdout-krav (ændring 5) | Alfa-budget håndhæves ikke; ingen familie-futilitet | Del af ændring 8 |
| 5 | Lovende kandidater fortsætter automatisk gennem gates | Jobkæde, automatisk promovering (ændring 4) | **Holdout-fejl rettet**: holdout åbnes som ét erklæret filsæt, så skabeloner med ekstra kilder (MVRV) kan gennemføre (ændring 7 §8) | Fastlåste tilstande opdages ikke | Detektion i `research_progress` og watcher |
| 6 | Videre til papirhandel, når alle krav er opfyldt | Papirmotor, skyggekonto for MVRV | Pause beholder og bogfører positioner (ændring 4 §7); 10 fremadtest-konti (FWD_) live siden 20:15 UTC; simulerede konti pauses kun på drawdown/data/spread, menneskelig genoptag (ændring 7) | Funding mangler i papir-P&L; ingen genoptag-vej for godkendt PAUSED; paper-1 kører ikke under FAIL_CLOSED/hold | Konformitetsrettelser (trin 1) og papirgennemgang (ændring 11) |
| 7 | Nye markedsændringer udløser hurtig opfølgning | — | Beslutningerne registreres og vises | UNDERSØG kan kun ske for helt nye fingeraftryk; intet følger efter en UNDERSØG | Pr.-instrument-nøgler, dossier-job, fremadtest-skabelon for detektorfund (ændring 9-10) |
| 8 | Opdage tab af edge | Kun circuit breakers | — | Ingen edge-decay-regel | Ændring 11 (papirgennemgang), senest før den første PAPER_TRADING (tidligst 2027) |
| 9 | Agenter laver reelt, verificerbart arbejde | Heartbeats | Agenterne viser arbejde pr. kørsel og hvorfor de står stille; diagnoser og fremadtest giver hash-kædet output | `agent_log` finder ikke scanner/paper-hændelser; output pr. 24 t mangler i UI | Alias-kort og output-felter (trin 1) |

## 2. Deployet og verificeret live 2026-10-18

| Commit | Indhold | Fuld suite på commit |
|---|---|---|
| d36c89d / 70b40d3 | Ændring 5 (tekst / kode): forskningsmotoren | 350 bestået, 1 sprunget over |
| 5f5a0d6 / b352715 | Ændring 6 (tekst / kode): jobkøens robusthed | 350 bestået, 1 sprunget over |
| 8988759 | Papirmotor følger ændring 4 §7; frisk ordrebog; timecache | 357 bestået, 1 sprunget over |
| 4206d49 | Søgning synlig; DNS-cache i flåden; færre opdateringer | 358 bestået, 1 sprunget over |
| fda2cf8 / af6d5ec / 2535fe6 | Ændring 7 (tekst), holdout-filsæt, fremadtest-konti og pauseregler | 371 bestået, 1 sprunget over |

Den sprungne test er reproduktionstesten `test_lab_s2.Acceptance`, som kræver research-cachefiler, der ikke findes på
maskinen. Den står som uafklaret.

Målte tal:
- Papirmotor: 17,7 s → 4,9 s pr. kørsel for skyggekontoen (49 → 17 kald). Med 10 fremadtest-konti: 18,7 s første
  kørsel, derefter cirka 6 s.
- Dashboard: cirka 28 % → 9,4 % af en kerne.
- Flåden overlevede en fremmed databaselås på 45 s og 75 s (før: døde efter 46 s og 61 s).
- Seks stop/start i dag, alle pæne (0,4-1,4 s stop, cirka 5-6 s pause), 0 falske genstarter, S7 fortsatte uden
  nulstilling, pm_lp-snapshots hvert 60.-63. sekund hele dagen.
- Fremadtest første time: 33 papirordrer på 7 konti, 0 fejl; formelle tabeller uændrede; alle 10 forbliver REJECTED.

## 3. Brugerens beslutninger (2026-10-18)

- Fremadtest-konti for de frosne strategier nu (10 konti; MVRV og en dublet udeladt).
- Hypotesegenerering via forhåndsregistrerede familier, kun ikke-prisforudsigelse; brugeren godkender familierne
  selv; registreringer der henter data venter til efter 2026-11-27.
- Skyggekonti følger ændring 3 §2 (drawdown, data, spread) plus menneskelig genoptag.
- Holdout-fejlen rettes som dokumenteret fejlrettelse.
- Antaget, medmindre brugeren siger andet: deploy-frys 2026-10-24 → 11-27 undtagen kritiske rettelser.

## 4. Realistisk tidslinje

- S7 kan tidligst åbne cirka 2026-10-25 06:40 UTC, hvis intet går galt; autostart kræver derefter brugerens ja.
- Fremadtest- og MVRV-vinduet: 2026-11-01 → 2027-04-30; afgørelser tidligst 2027-05-07.
- Ingen ny kandidat kan nå godkendt papirhandel før midten af 2027. Det er en følge af protokollen, ikke af kode.

## 5. Uafklaret

- Linux-gennemløb for tunge jobs (der er endnu aldrig kørt et tungt job på Linux).
- Reproduktionstesten uden cachefiler.
- Effekten af 10 fremadtest-konti på NAS-DNS'en under pm_lp-holdout (målt lav på kopien; følges live).
- Afstemningens køretid i `/api/paper2` vokser med antal ordrer; skal gøres mængdebaseret før vinduets slutning.
