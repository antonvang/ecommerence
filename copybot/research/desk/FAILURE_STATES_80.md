# FAILURE_STATES_80: lukketilstande, kontakt til blokerede værter og append-only statusser (direktørordre 80)

Skrevet 2026-11-10 kl. 00:23 lokal (23:23 UTC 11-09). **Kun design og kortlægning. Ingen deploy, ingen ny collector, ingen
aktivering, ingen ændring af DNS, netværksregler, collectors, ledgerstatus eller eksisterende filer.**

Mærker: **[F]** = fakta fra kode, `ps`/`systemctl` (read-only) eller lab.db-aggregater. **[V]** = vurdering. lab.db er kun
læst med `COUNT(*)`, `MIN(ts)`, `MAX(ts)` (`mode=ro`, `query_only`). `pm_lp.db` er ikke læst. Intet netværk.

## P0. Fejlhåndtering for permanent utilgængelige ben (uanvendt patch)

Patch: `research/desk/patches/80_close_terminal_state.diff`. **Ikke anvendt.** `lab/paper_runner.py` er uændret. Testet på
midlertidige kopier i `tests/test_partial_close_80.py` (17 tests; en mutation af den terminale gren og terminal-reglen gav 8
fejl og er rullet tilbage).

Patchen har kun ét mål: `close_ledger`. Den rører ikke stopregler, `run_one`, mærkning af aktive konti eller collectors.

| Tilstand (`paper.close_state`, `close_state` i svaret) | Betydning | Forsøges igen? |
|---|---|---|
| `CLOSE_SUCCESS` | Ingen åbne ben og et mærke på eller efter sidste fyld. Eneste "lukket" | — |
| `PARTIAL_CLOSE_RETRYING` | Mindst ét ben lukket eller reduceret, mindst ét åbent, og de åbne kan stadig lukkes | Ja |
| `PARTIAL_CLOSE_TERMINAL` | Som ovenfor, men ingen åbne ben kan lukkes (permanent vært eller tiden brugt) | Nej |
| `CLOSE_INCOMPLETE_RETRYING` | Intet ben lukket, de åbne kan stadig lukkes | Ja |
| `CLOSE_INCOMPLETE_TERMINAL` | Intet ben lukket, kan ikke fuldføres | Nej |

"Kun ét ben lukket" står eksplicit i `unpaired_open_legs` og `closed_legs`, både under retry og terminalt.

| Krav | Sådan opfyldes det | Test |
|---|---|---|
| Ingen falsk `CLOSE_SUCCESS` | Afgøres ét sted (`close_state_of`, ren funktion). Kræver flad konto og mærke efter sidste fyld | `test_success_only_when_flat_and_marked_after_the_last_fill` og `test_never_success_while_a_leg_is_open` |
| Ingen skjult uendelig closing | Terminal, hvis alle åbne ben er permanent utilgængelige, eller efter `CLOSE_RETRY_MAX_S` = 7 d [V]. Status i svaret og i hændelsen. `retry_deadline_ts` gemmes | `test_retrying_is_bounded_and_ends_terminal` |
| Ingen opdigtede priser | Et permanent utilgængeligt ben læses, prises, mærkes og lukkes ikke. Ingen række skrives for det | `test_the_blocked_host_is_never_contacted_and_nothing_is_invented` |
| Alle simulerede hændelser bevares | Patchen sletter og ændrer intet; hændelser er append-only | `test_state_events_are_append_only` |
| Ingen dobbeltbogføring | Ordre-id'er uændrede. Ny hændelse kun ved ændret tilstand | `test_repeated_attempts_write_no_new_rows_or_state_events` |
| Genstart bevarer status | Tilstand og `first_ts` læses af databasen | `test_restart_keeps_the_terminal_state`, `test_restart_keeps_the_retry_clock` |
| Ingen automatisk genoptagelse | Terminal er låst: ingen bog, funding eller mærke, også hvis værten svarer | `test_terminal_is_sticky_silent_and_books_nothing_more` |

**Bemærkninger [F]:**

- Patchen er lavet mod dev-filen. Produktionens `lab/paper_runner.py` er en anden (branch `claude/why-cant-we-do-this-wh3ohb`, `85db922`, 2026-11-05) og har hverken `mark_guarded` eller `note_mark_failed`. Patchen kan ikke anvendes direkte dér.
- Produktionens `close_ledger` lukker også ben for ben, så risikoen fra ordre 78 gælder der.
- Dev og produktion svarer begge `status: "closing"` uden lukketilstand i dag.

**Beslutninger, der kræver særskilt godkendelse [V]:**

- Reglen om 7 d er et forslag og gælder også FWD- og SHADOW-konti.
- Perp-benet lukkes stadig, selv om spot-benet er permanent væk: det er den nuværende adfærd og ikke en ny regel. Alternativet (ingen ben lukkes) ændrer lukkeadfærden. Patchen tager ikke stilling.
- En ophævelse af en terminal tilstand er ikke med. Den kræver en ny dateret beslutning og et nyt forsøg, aldrig genoptagelse.

## P3. Processer, der stadig forsøger at kontakte de fem værter (read-only)

Set kl. 23:20 UTC 11-09: `lab watch`, `lab web`, `lab fleet` kører, `copybot-lab.service` og `copybot-watch.service` er
`active/running`. `pm-lp-collector.service` er `activating/auto-restart`, `Result=exit-code`, `NRestarts=292` [F].

**Rettelse til `NETWORK_REPLAN_76.md` afsnit 1b og 6 punkt 6:** `copybot-lab.service` er installeret og aktiv, ikke kun forberedt.

| Proces og kilde | Blokeret vært | Fejladfærd | Risiko for falsk "recovered" | Risiko for manglende/misvisende observationer | Senere ændring kræver |
|---|---|---|---|---|---|
| `pm-lp-collector.service`: `research.pm_lp collect` | clob, gamma (+ Polymarket-data-vært, ikke på listen) | `ExecStartPre` kører `getent hosts clob.polymarket.com` (`::` godkendes). Kaldet før løkken fejler, procesen dør, `Restart=on-failure` efter 60 s. `http` prøver 5 gange | **Bekræftet mønster [F]:** hver start skriver en `runs`-række. `fleet.external_watch` og `mission` bruger filens alder, så skrivningen giver `external.recovered`. Hændelser for `X01_pm_lp_v1`: 7 stale og 7 recovered, seneste recovered 2026-11-09 16:29:14 UTC, midt i hullet i `PM_LP_D1_STATUS_72.md` | `mission` kan vise "running (external process)". `lab/watch.py` læser derimod rigtige snapshots og er ærlig under holdout, men svarer "collection finished" efter D0+41, uanset data | `G12_PMLP`, ejerens tilladelse (`72_*`-patches), `G11_RESTART_1128`; ingen planlagt stop til og med 27/11 |
| `lab fleet`, `paper-1`, 60 s: `lane.run_one` → `_mark_hourly` → `fetch_book(.SPOT)` | data-api | [F] Forsøges hver gang, indtil et mærke findes. Mindst ét fejlende kald pr. konto og pas (9 konti). Passet svarer alligevel `ok`. Produktionen sluger fejlen: `paper.mark_failed` har 0 rækker i lab.db | Svarer værten, skrives et mærke uden særmarkering, og `net_report` siger FRESH. Det er en ægte pris, men strider mod "ingen automatisk genoptagelse" (ordre 76) | `sim_equity` står stille uden hændelse. Funding kører videre (ordre 78 B) | Motorændring: dateret ændring, grøn suite, deploy tidligst efter 20/11 |
| `paper-1`: `close_ledger` ved stop | data-api | Ben for ben (ordre 78), gentages for evigt | Ingen statusfelt; `status: "closing"` | Partial close uden status | Patch 80, særskilt ja |
| `paper-1`: `lane.spot_pairs` (timevis) | data-api | Sidste liste beholdes; `None` efter genstart | Lav | Filter 19 springer intet over efter genstart | Som ovenfor |
| `paper-1`: `lane.manage` → `_probe`, scanner, HL | data-api | Mønter uden bog droppes, `lane.skipped` | Lav | `lane.skipped` med netværksårsag kan ligne manglende likviditet [V] | Særskilt beslutning om at stoppe nystarter |
| `paper-1`: `Risk.auto_resume` for pausede konti (ændring 18) | ingen selv; `_data_probe` er kun perp | [F] En `data_fetch`-pause kan hæve sig, fordi perp virker | **Ja for spot-konti:** "data virker" gælder kun perp-benet | Pause slutter, spot stadig væk | Motorændring, særskilt ja |
| `discovery-scanner`, 3.600 s: `venue_subsidy`, `pricing_constraint` | clob, gamma | Fejlrække pr. kørsel: 94 og 99 rækker, seneste 2026-11-09 23:02:00 UTC. Sidste data 11-06 20:02:00 | Lav: `coverage` viser `failing` | Serien har hul uden en permanent statustekst | Dateret ændring af detektorlisten |
| `news_pass` → `capacity.run`, hver 23. t | data-api | Fejlrække pr. instrument: 54, seneste 11-09 06:39:58. Perp fortsætter | Lav | Efter 11-06 kun perp-rækker; spot+perp-kurver må ikke sammenlignes over skellet | Dateret ændring (21v) |
| `data-1`, `ingest.enqueue`, `explore.enqueue`, `hypogen.enqueue` | data.binance.vision | Job prøver filer via `_fetch`/`guarded_get`. Omfang ikke målt (jobs-tabellen er uden for rammen) | Lav | En netværksfejl er ikke det samme som husket 404; `UNTESTABLE` kan misforstås [V] | Dateret ændring; G02, G10 |
| `copybot-lab.service` (`ExecStartPre`) | DNS-opslag af data.binance.vision | `::` godkendes; NXDOMAIN giver stop efter 10 min | Ventetjekket siger ikke, at værten virker | Risiko ved næste boot, hvis svaret ændres [V] | Ejerens beslutning om enheden; `G11` |
| Fleet- og collector-proces: `install_dns_cache` (`DNS_TTL` 300 s) | alle | Gemmer vellykkede opslag i 5 min. Fejl gemmes ikke | Lav | Et svar inden for en kort åbning kan bruges i op til 5 min [V] | Dateret ændring |
| Manuelle værktøjer: `hfc1_daily`, `pilot`, `carry_basis`, `fetch_recent_funding`, `v1_books`, `dns_diag`, `gate_status --check-dns` | data-api, clob m.fl. | Kører ikke nu efter `ps` | — | `hfc1_daily cohort` må ikke køres som erstatning | Ikke brug; ingen ændring |

**Sammenfatning [V]:** ingen af processerne omgår beslutningen, men flere gentager kald uden status. De reelle falske statusser er `external.recovered`, `auto_resume` for spot-konti og `collection finished` efter 11-27.

**Hvad ikke er målt:** antal kald pr. minut (kun afledt af kode), jobkøens indhold og om Polymarket-data-værten svarer.

## P4. Append-only plan for statusser

Formål: statusserne skal kunne ses uden at røre noget eksisterende. **Planen ændrer ingen ledgerstatus og indfører ingen automatik.**

**Principper:**

1. Historiske poster (`sim_*`, `events`, `results`, `transitions`, `lane.*`, kohortefiler, rapporter) ændres aldrig, og deres oprindelige tidsstempler bevares.
2. En status er en ny række i et særskilt, hash-kædet register. Der er ingen UPDATE og ingen DELETE. En rettelse er en ny række med `supersedes`.
3. `effective_ts` er tiden for den underliggende observation; `recorded_ts` er tiden for registreringen. De blandes aldrig.
4. Registret er read-side: motor, stopregler, `closing_ledgers`, gates og dashboards ændrer ikke adfærd af det. Rapporter læser det kun som et ekstra felt.
5. Ingen automatisk ændring af eksisterende ledgerstatus. Værktøjer må kun foreslå rækker (`dry-run`). Hver første række for et emne kræver en dateret direktør- eller ejerbeslutning.

**Foreslået rækkeformat (ingen fil oprettet):** `seq`, `prev_hash`, `hash`, `subject` (konto, kohorte, forsøg), `subject_type`, `status`, `effective_ts`, `recorded_ts`, `evidence` (tabel, id-interval eller sha256), `reason`, `decided_by`, `rule`, `supersedes`.

| Status | Emne | Krævet evidens | Må aldrig betyde |
|---|---|---|---|
| `DATA_SOURCE_UNAVAILABLE` | Konto, kohorte, forsøg | Ordre 76, vært, sidste verificerede observation og tid | At forsøget er forkastet; at posterne er ugyldige |
| `PARTIAL_CLOSE` | Konto | Lukkefyld (`sim_orders` med `\|close\|`), åbne ben; `classify_close` eller `paper.close_state` | Lukket; aktuel P&L |
| `CLOSE_INCOMPLETE` | Konto | Ingen lukkefyld eller flad uden mærke; samme kilder | Lukket; stoppet handelsrisiko |
| `EQUITY_NOT_COMPUTABLE` | Konto | Åbent ben uden friskt mærke (2 t); sidste verificerede mærke | At equity er nul eller sidste mærke |
| `HOLDOUT_NOT_EVALUATED` | Forsøg | Beslutning og grund | Statistisk forkastet eller valideret |

**Forhold til eksisterende mærker:** `FRESH`, `STALE`, `MISSING_MARK` og `research_status` bliver som de er. Statusserne lægges ved siden af, de erstatter dem ikke. `pm_lp_v1` får parret `TERMINATED_DATA_QUALITY_FAILURE / HOLDOUT_NOT_EVALUATED` (`PM_LP_TERMINATION_80.md`). `partial_close.py` (ordre 78) leverer tilstande, men skriver intet.

**Rækkefølge (hvert trin eget ja):** (1) registerets format og en test af hash-kæde og `supersedes`; (2) en `dry-run`-rapport, der kun foreslår rækker; (3) direktøren afgør første rækker; (4) visning i `net_report` og dashboard som et ekstra felt.

**Tilbagerulning:** en ny række, der ophæver, eller at registret ikke læses. Ingen sletning.

## Uafklaret

1. Er 7 d rimelig retry-grænse, og skal den gælde FWD/SHADOW?
2. Skal perp-benet lukkes, når spot-benet er permanent væk?
3. Hvornår og hvordan collectoren og scanner-detektorerne stoppes eller ændres (G12 og særskilte godkendelser).
4. Hvor registret skal ligge, og hvem der skriver første række.
5. Jobkøens faktiske kald mod data.binance.vision; Polymarket-data-værten.
6. Patch 80 forudsætter dev-motoren; rækkefølgen af deploy er ikke besluttet.
