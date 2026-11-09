# Ordre 59-D/59-E: synlige fejl i timemærkningen (paper.mark_failed)

Skrevet 2026-11-09 kl. 05:17 dansk tid (04:17 UTC). Skåret ned efter ordre 59-E (option A) samme dag.
Kun simulering. Ingen rigtige penge, ingen nøgler.

**Intet er deployet.** Ændringen ligger kun på den lokale gren `claude/59d-mark-failed` i en isoleret worktree.
Produktionen (`~/ecommerence/copybot`), `~/copybot-dev`, kørende processer, systemd, DNS og netværket er ikke rørt.
Intet er pushet.

## Fejlen

- Hver time mærker papirkontiene deres positioner til bogens midtpris (`paper_runner._mark_hourly`).
- Spotbenet læser bogen fra `https://data-api.binance.vision`. Et lokalt DNS-filter blokerer den vært.
- Når mærkningen fejlede, skete der intet synligt. `lane.run_one` svarede stadig `"status": "ok"`. Der blev ikke
  skrevet nogen hændelse. Det samme gjaldt `paper_runner.mark_only` (pausestien). `straks.run_one`, `pairs.run_one`
  og `paper_runner.close_ledger` har samme tavse mønster, men er uden for denne rettelse (se nedenfor).
- Følgen i produktionen: egenkapitalen for 9 konti har stået stille siden 2026-11-08 06:40:31 UTC. Funding bogføres
  stadig.

## Hvad er rettet

Kun det, de 9 lane-/carry-konti har brug for (59-E). Ét fælles sted i `lab/paper_runner.py`: `mark_guarded(...)`.
Kun tre filer er ændret: `lab/lane.py`, `lab/paper_runner.py` og `lab/command.py`.

| Sted | Før | Nu |
|---|---|---|
| `lane.run_one` (carry, scanner, HL, carry90: konti med spotben) | fejl slugt, ingen hændelse | `paper.mark_failed` |
| `paper_runner.mark_only` (pause; pausede lane-konti går denne vej) | fejl slugt, ingen hændelse | `paper.mark_failed` |
| `paper_runner.run_one` (E_-strategier) | uændret adfærd | kun `paper.mark_recovered` (én linje) |
| `paper_runner.close_ledger` | tavst mønster | uændret (ikke nødvendigt for de 9) |
| `straks.run_one`, `pairs.run_one` | tavst mønster | uændret, FROSSET |

- Linjen i `paper_runner.run_one` er nødvendig, fordi `mark_only` også bruges af E_-konti: uden den ville en E_-konto,
  der genoptages efter en registreret fejl, aldrig få `paper.mark_recovered`, og en senere fejl af samme klasse ville
  blive tiet ihjel af dedupe.
- `straks.py` og `pairs.py` er FROSSET til efter deres milepæle (STRAKS 12/11, parbog 19/11). De er byte-identiske
  med 85db922 (sha256 `7a110f1f…a542` og `5c9b60a4…1219`). De mærker normalt, fordi de kun har perp-ben
  (`fapi.binance.com`), ikke spotværten.
- `close_ledger` er udeladt: en konto, der lukkes, mens en fejl står åben, får ingen `paper.mark_recovered`. Det er
  accepteret.

Ingen pause, ingen gate, ingen FAIL_CLOSED. Ordrer, fyld, kontanter og mærker er uændrede. Det er bevist i en test
og i en sammenligning med den gamle kode (se "Test").

## Status: før og nu

Feltet `status` er uændret for alle forbrugere. Tre nye felter er lagt til i svarene fra `lane.run_one` (normal
sti) og `paper_runner.mark_only`.

| Felt | Betydning |
|---|---|
| `status` | uændret: `"ok"` og `"paused"` også når mærkningen fejler |
| `marked` | uændret: `True`, `False` eller teksten `"no mark prices: ..."` (lane) |
| `reason` | uændret i `mark_only` ved fejl |
| `run_completed` | nyt: `True`, passet kørte til ende |
| `mark_succeeded` | nyt: `True`, hvis passet skrev et mærke |
| `mark_failed` | nyt: `True`, hvis et mærkeforsøg fejlede |

- Begge mærkefelter `False` betyder: intet mærke var forfaldent (kontoen var allerede mærket i denne time).
- Tidlige svar (`fail_closed`, pause ved datafejl, `blocked`, `unsupported`) og svar fra straks, pairs,
  `close_ledger` og E_-`run_one` har ikke de nye felter. Mangler feltet, gælder den gamle betydning.

## Hændelsen `paper.mark_failed`

Aktør `agent:paper-1`. `exp_id` = kontoen. Payload:

| Nøgle | Indhold |
|---|---|
| `ledger` | kontoen (samme som `exp_id`) |
| `t` | passets tid, UTC sekunder |
| `marked` | altid `false` |
| `error_type` | `type(e).__name__`, fx `URLError`, `IndexError` |
| `error_class` | grov klasse: `dns`, `timeout`, `http`, `connection`, `no_price` eller `other` |
| `error` | sikker tekst: `repr(e)`, URL'er skåret til `skema://vært`, query-strenge fjernet, nøgle-/token-lignende værdier og lange uigennemsigtige strenge erstattet med `[redacted]`, højst 200 tegn |
| `last_mark_ts` | seneste gode mærke: `SELECT MAX(ts) FROM sim_equity WHERE exp_id=?` (eller `null`) |
| `mark_age_s` | `t - last_mark_ts` |
| `failing_since` | første fejl i denne fejlperiode |
| `previous_class` | klassen før skiftet, ellers `null` |
| `events_in_episode` | nummer på hændelsen i fejlperioden (1, 2, ...) |
| `simulated` | altid `true` |
| `rule` | henvisning til denne fil |

Klassen findes kun ud fra undtagelsesobjektet. Der er intet netværkskald og intet navneopslag.
- `dns`: `socket.gaierror` eller resolverens tekst ("Name or service not known" m.fl.), også bag `URLError`.
- `connection`: `ConnectionRefusedError` og andre forbindelsesfejl. Et DNS-filter, der svarer `0.0.0.0`, ser sådan ud.
- `timeout`, `http`: som navnet siger.
- `no_price`: bogen mangler et niveau eller felt (`IndexError`, `KeyError`, `ValueError`, `TypeError`).

## Hændelsen `paper.mark_recovered`

Skrives, når et mærke faktisk er skrevet efter en registreret fejl. Payload:

| Nøgle | Indhold |
|---|---|
| `ledger`, `t`, `simulated` | som ovenfor |
| `marked` | altid `true` |
| `first_mark_ts` | det første gode mærke efter fejlen |
| `failing_since` | første registrerede fejl |
| `failure_duration_s` | `first_mark_ts - failing_since` |
| `last_mark_before_ts` | seneste gode mærke før fejlen |
| `mark_gap_s` | `first_mark_ts - last_mark_before_ts` (hele hullet i egenkapitalen) |
| `error_class` | den sidste klasse i fejlperioden |
| `events_in_episode` | antal `paper.mark_failed` i fejlperioden |

## Regler mod støj og for genopretning

1. Tilstanden læses af kontoens seneste `paper.mark_failed`/`paper.mark_recovered`. Ingen hukommelse i processen.
   Den overlever derfor en genstart.
2. En fejl skrives, når kontoen går fra god til fejl. Den skrives også, når fejlklassen skifter under fejlen.
3. Samme vedvarende fejl skrives ikke igen. Heller ikke hver time.
4. `paper.mark_recovered` skrives én gang, ved det første mærke, der faktisk står i `sim_equity`.
5. Genopretning udledes aldrig af et DNS-opslag eller en anden test. Et pass uden forfaldent mærke er ingen genopretning.
6. Kontrol og skrivning sker i én transaktion (`BEGIN IMMEDIATE`).
7. Første fejl efter deploy giver én hændelse pr. frossen konto med `last_mark_ts` = 2026-11-08 06:40:31 UTC.

## Forbrugere og kompatibilitet

Fundet med grep i `copybot/lab` og `copybot/research`.

- `lab/fleet.py` `paper_pass`: melder agenten degraderet kun ved `status` `blocked` eller `error`. Uændret. En
  mærkefejl giver stadig ingen degradering. Resultatet logges via `_summary` (JSON, opsummeret). Nye felter er ufarlige.
- `paper_runner.run` samler svarene. Ingen kode læser `marked` eller de nye felter. Kun tests læser `marked`.
- `lab/command.py` `NOT_OUTPUT`: `paper.mark_failed` og `paper.mark_recovered` er tilføjet. Ellers ville de tælle som
  "output" for agenten paper-1 på dashboardet. Fejltællerne (`errors_window`, `errors_total`) tæller kun job- og
  agentfejl. De er uændrede.
- `lab/web.py` `/api/audit` og SSE-strømmen viser alle hændelser. De nye vises der uden ændring.
- `lab/mission.py` viser seneste hændelse pr. E_-eksperiment. En pauset E_-strategi kan nu vise `paper.mark_failed`.
  Det er meningen.
- `lab/command.py` eksperimentfilter `since` bruger `MAX(ts)` af alle hændelser. En mærkefejl tæller som aktivitet.
- `lab/watch.py` måler selv mærkealder (`PAPER_MARK_MAX_S` = 2,5 t) fra `sim_equity`. Uændret og uafhængig.
- `lab/reportcheck.py`, `lab/coverage.py`, `lab/eventreport.py`, `lab/events.py`: læser andre hændelser. Uændret.
- `lab/dashboard.html`: viser ingen `paper.*`-hændelser. Ikke ændret (ingen JS-motor på værten til at prøve det).
- `copybot/research`: ingen kode læser `paper.*`-hændelser eller disse svar.
- Ingen allowlist af hændelsestyper findes i laben (`db.event` tager enhver type). Intet skulle registreres.
- Sikkerhedstesten (`tests/test_lab_safety.py`) er grøn. `import socket` og `urllib.error` er kun til klassificering;
  intet nyt netværkskald.
- pm_lp-indsamleren importerer `lab.supervisor`, `legacy`, `lifecycle`, `ops`, `registry`, `risk`, `db` og
  `research.pm_lp`. Ingen af dem er ændret.

## Test

- `tests/test_lab_mark_failed.py`, 17 tests, midlertidige databaser, mocket `get`, netværk og DNS spærret.
  Dækker: godt mærke uden hændelse; første fejl (DNS) giver én hændelse; afvist forbindelse; manglende spotpris;
  samme fejl gentaget giver stadig én hændelse; ny klasse giver hændelse nr. 2; genopretning giver
  `paper.mark_recovered`; pass uden forfaldent mærke er ingen genopretning; sikker fejltekst; pausestien
  (`mark_only`, også kaldt direkte); E_-stiens direkte mærke afslutter en fejlperiode; ingen ændring i positioner,
  fyld, kontanter, `sim_*`- og `risk_events`-rækker med hashes; ingen PAUSE, ingen FAIL_CLOSED, ingen
  `paper.error`, hashkæder intakte; `NOT_OUTPUT`; straks.py og pairs.py har de låste sha256.
- Byte-sammenligning mod den gamle kode (85db922): 14 timer på en carry-konto, først normal sti (god, DNS, DNS,
  ingen pris, afvist, god, DNS, god), så pausesti (DNS, DNS, ingen pris, god, afvist, god). Alle `sim_*`- og
  `risk_events`-rækker og svarene (uden de tre nye felter) er byte-identiske.
- Hele suiten (2026-11-09 05:35–05:47 UTC) med en lille loader: alle 114 `tests/test*.py`-moduler UNDTAGEN
  `tests/test_lab_research_engine.py` (59-E P2), netværket spærret (kun loopback) og `data._fetch` uden cache
  afvist: 1288 tests OK, 1 skipped, 0 blokerede netværks- eller downloadforsøg.

## Holdout-test uden netværk (59-E P2)

- `test_lab_research_engine.HoldoutGate.test_too_few_symbols_fail_the_holdout` mockede `_market`, `_quality`,
  `_positions`, `_evaluate` og `_benchmark`, men ikke `_declare_holdout`. Stien var: `pipeline.step_holdout` →
  `_declare_holdout` → `data.files_for(sym, "holdout")` → `data._fetch` → `urllib.request.urlopen` (data.binance.vision,
  2024-filer). Uden cache prøvede den at hente. Kun DNS stoppede den.
- Med cache (som i dev-worktree'en) henter den ikke, men `Gateway.access` læser filernes bytes for at beregne sha256
  og skriver `datasets`- og `holdout.opened`-rækker i testens midlertidige database. Priserne parses ikke.
- Rettelse kun i testkode: `tests/offline_market.py`. `data.CACHE` peger på en tom midlertidig mappe, `data._fetch` og
  `urlopen` fejler lukket med `OfflineFixtureMissing("BLOCKED: no offline fixture: <url>")`, og `files_for` giver
  syntetiske stand-in-filer. Testen rører ikke længere 2024-data. Ingen ændring i `lab/`.
- `tests/test_offline_market_guard.py` prøver vagten alene, uden rigtig 2024-fil og uden netværk.
- 59-F: `data._fetch` i fixturen giver kun filer fra testens egen midlertidige cache. En anden cache (også en
  lokkefil `BNBUSDT-1h-2024-01.zip`) bruges aldrig. `offline_market.file_guard()` lader `open`, `io.open` og `os.open`
  fejle med `ProtectedFileAccess` på en beskyttet sti: en rigtig markedscache (`*/data/lab/market/*`), en 2024-zip
  eller en lab-/forskningsdatabase uden for den midlertidige mappe. HoldoutGate bruger vagten og tjekker, at den
  erklærede holdout-mængde kun består af syntetiske filer, og at udfaldet er uændret (for få symboler → REJECTED).
- 59-F (2026-11-09 06:13–06:25 UTC): hele suiten, også `test_lab_research_engine.py`, er kørt i et
  netværksnavnerum uden rod (`unshare -rn`, kun loopback, også for underprocesser) med netværks-, download- og
  filvagt i Python. 1308 tests: 1306 OK, 1 skipped, 1 fejl. 0 netværks- og 0 downloadforsøg. Filvagten slog til
  251 gange. Ingen af dem var holdout-testen:
  - `test_lab_coverage` (10 tests, 250 gange): `families.absent` → `hypogen._absent` læser checkoutets
    `data/lab/market/absent_404.json` (en liste over manglende filer, ikke priser). Testene består alligevel.
  - `test_lab_mission.test_mission_endpoints` (1 gang): `/api/results` læser checkoutets
    `data/research/results/*.json`. Den ene fejl kom fra vagtens ekstra regel for `data/research`. Med den regel
    kun talt består testen (12/12).
  - Disse to læser en rigtig checkouts data, når de køres i produktion eller dev. Ikke rettet her (uden for 59-F).

## DEPLOY-plan (senere, kun efter et udtrykkeligt ja)

Tidspunkt:
- Ikke i K3: ±35 min om 00/04/08/12/16/20 UTC. Ikke i K1/K2: HH:00–HH:12 UTC lørdag og søndag.
- Heller ikke HH:00–HH:12 på hverdage (timemærker og scanning kl. HH:02).
- Godt vindue: en hverdag 12:40–15:20 UTC, fx 13:20 UTC. Ingen genstart af pc'en før 2026-11-27.

Før (fra `~/ecommerence/copybot`):
1. `date -u`. Tjek at vinduet er frit.
2. `git -C ~/ecommerence status --short` → tom. `git -C ~/ecommerence log -1 --oneline` → 85db922 (eller nyere;
   så rebases grenen først, og suiten køres igen).
3. `python3 -m lab deploy-check` → DEPLOY OK. `python3 -m lab health` → FAIL_CLOSED: no.
4. `systemctl --user show pm-lp-collector -p ActiveState -p MainPID -p NRestarts`. Noter værdierne.

Deploy:
5. `git -C ~/ecommerence merge --ff-only claude/59d-mark-failed` (grenen bygger direkte på 85db922).
   Tjek bagefter: `sha256sum lab/straks.py lab/pairs.py` → de låste værdier (frosne filer).
6. `sync`. Ingen tomme filer: `find lab research tests -name '*.py' -size 0` → intet output (efter et nedbrud kan
   nyhentede filer stå med 0 byte).
7. Indsamlerens genstart må ikke kunne gå i stykker: `python3 -c "import lab.supervisor, research.pm_lp"` → ingen
   fejl. (Ingen af dens filer er ændret, men tjekket er billigt.)
8. `python3 -m lab stop --reason "59-D deploy"`, derefter `(setsid nohup ./START_LAB.sh >> data/lab/start.log 2>&1 < /dev/null &)`.
   Kodevagt og preflight (`PREFLIGHT OK`, tjekker også indsamlerens filer) kører selv.
9. Vent ca. 2 min. Ét dashboard-kald med lang timeout (ikke korte curl-løkker).

Efter:
10. `python3 -m lab deploy-check --commit $(git rev-parse --short HEAD)` → DEPLOY OK.
11. `systemctl --user show pm-lp-collector -p ActiveState -p MainPID -p NRestarts` → samme MainPID, samme NRestarts.
12. Efter næste time (HH:00 + få min): én `paper.mark_failed` pr. frossen konto (forventet 9), klasse `connection`
    eller `dns`, `last_mark_ts` = 1794120031 (2026-11-08 06:40:31 UTC). Timen efter: ingen nye (dedupe).
13. `python3 -m lab health` → FAIL_CLOSED: no, samme pauser som før. Ingen ny `paper.error`.

## ROLLBACK-plan

1. Samme tidsregler som ovenfor.
2. `git -C ~/ecommerence revert --no-edit 85db922..claude/59d-mark-failed` (nye commits; historikken bevares).
3. Samme tjek som trin 6–11: ingen tomme filer, `import lab.supervisor, research.pm_lp`,
   `lab stop` + `START_LAB.sh` (preflight), `deploy-check` → DEPLOY OK, indsamlerens MainPID og NRestarts uændret.
4. Allerede skrevne `paper.mark_*`-hændelser bliver stående (tabellen er kun-tilføj). Ingen kode læser dem efter en
   revert. De skader ikke.

## Hvad dette ikke løser

- Mærkerne står stadig stille, så længe værten blokeres. Rettelsen gør det kun synligt.
- At fjerne blokeringen (DNS-filteret eller en anden spotkilde) er et særskilt valg for ejeren.
