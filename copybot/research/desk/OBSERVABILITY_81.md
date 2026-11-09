# OBSERVABILITY_81: falske recovered-statusser, terminal close-state, K3/PR1, statusregister og kompatibilitet (direktørordre 81)

Skrevet 2026-11-10 kl. 00:51 lokal (23:51 UTC 11-09). **Dev-only. Ingen patch er anvendt. Ingen deploy, lås, aktivering,
ledger-række eller ændring af collector, DNS eller produktion. `lab/` er uændret.**

Mærker: **[F]** = fakta fra kode, git eller tests. **[V]** = vurdering. Intet netværk; lab.db er ikke åbnet til denne opgave.

Patches: `research/desk/patches/81_observability_recovered.diff`, `81_close_terminal_state_v2.diff`. Ejerens regel og G12 kræver særskilt tilladelse til enhver anvendelse.

## P0. Falsk recovered og auto-resume

`81_observability_recovered.diff` ligger **oven på** `72_external_watch_data_activity.diff` og gentager den ikke. Test: `tests/test_observability_81.py`.

| Fejl [F] | Rettelse (uanvendt) | Test |
|---|---|---|
| 72 tæller en vellykket trade-poll eller status-række som aktivitet. Bøgerne kommer fra en anden vært end trade-polls, så trade-polls alene kan ligne sundt | `ops.required_data_age`: alderen på den **ældste** af de påkrævede kilder (bogsnapshots og vellykkede trade-polls). En kilde uden gyldig række tæller som aldrig. Ulæselig db afgør intet | `test_trade_polls_alone_are_not_enough_although_72_would_accept_them` |
| `external.recovered` kan komme, uden at de påkrævede kilder leverer | `fleet.external_watch` bruger de påkrævede kilder først | `test_fresh_file_and_trade_polls_without_books_are_no_recovery` |
| `mission` viser "running" ud fra filens alder | Ny tekst `external — no valid data` | `test_a_fresh_file_alone_does_not_read_as_running` |
| `coverage.hypotheses` viser RUNNING ud fra filens alder | Data-alder, når den kendes | `test_a_running_claim_needs_data_not_a_fresh_file` |
| `Risk.auto_resume` godtager én probe | `probe` kan være en liste af navngivne kilder. Alle skal virke; en tom liste genoptager aldrig | `test_working_perp_does_not_hide_a_missing_spot_source`, `test_no_declared_source_never_resumes` |
| `lane._data_probe` læser kun perp | `lane._data_probes`: perp og spot-ben | `test_a_carry_account_stays_paused_while_only_perp_data_work` |
| `watch.check_collector` svarer "collection finished" på datoen alene | Finished kræver status-polls frem til slutningen. Ellers "not judged" (`None`), som bevarer den hidtidige tilstand | `test_the_calendar_alone_is_not_finished` |

To tests dokumenterer selve fejlen i den urørte kode: `test_the_real_unpatched_probe_would_have_resumed` og `test_the_real_unpatched_check_reports_finished_on_the_date_alone`.

**Bevidst uændret [F]:** `lab/straks.py` og `lab/pairs.py` er pinnede. De probrer kun en BTCUSDT-bog ved `auto_resume`, altså én kilde. Det kan ikke rettes i patchen. Rækkefølgen er direktørens valg (ordre 59-E).

**Kendt begrænsning [V]:** spot-proben i `lane` kontakter stadig den blokerede vært, så længe kontoen er på pause. Det svarer til dagens mærkning. Det kan fjernes ved at genbruge `PERMANENT_UNAVAILABLE_SUFFIXES` fra close-patchen, men er holdt adskilt.

### Processer, patchen senere ville påvirke [F]

| Fil i patchen | Proces(ser) |
|---|---|
| `lab/ops.py` | `lab fleet`, `lab web`, `lab watch`, **og pm_lp-collectoren** (via `lab.supervisor`, som importerer `lab.ops`) |
| `lab/risk.py` | `lab fleet`, **og pm_lp-collectoren** (via `lab.supervisor`, som importerer `lab.risk`) |
| `lab/fleet.py` | `lab fleet` |
| `lab/mission.py` | `lab fleet`, `lab web` |
| `lab/coverage.py` | `lab web` |
| `lab/lane.py` | `lab fleet` (`paper-1`) |
| `lab/watch.py` | `lab watch` (`copybot-watch.service`) |
| `lab/paper_runner.py` (close v2) | `lab fleet` (`paper-1`), kun lukkende konti |

Collectorens genstart importerer de to markerede filer fra produktionens checkout, så en deploy rører dens genstartsvej (G12, `preflight.collector_restart`). Patchen ændrer ikke collectorens egen kode.

## P1. Close-state v2

`81_close_terminal_state_v2.diff` er selvstændig mod dev-filen. **Den committede 80-patch er uændret.** Test: `tests/test_close_state_81.py`.

| Krav | Sådan | Test |
|---|---|---|
| 7 døgn som foreløbig grænse | `CLOSE_RETRY_MAX_S = 7 * 86400`, kommenteret som dev-teststandard, ikke en stopregel | `test_seven_days_is_the_retry_default` |
| Permanent kilde registreres som terminal uden gentagne netværksforsøg | Benet læses ikke. Tilstanden skrives én gang og er låst | `test_terminal_is_sticky_without_repeated_attempts`, `test_no_book_is_requested_for_either_leg` |
| **Ingen automatisk lukning af perp, når spot er permanent væk** | `blocked_legs`: det permanente ben og dets partner lukkes ikke. `CLOSE_INCOMPLETE_TERMINAL`, `requires_decision: true` | `test_the_perp_leg_is_not_closed_and_the_close_is_incomplete` |
| Terminal er ikke lukket | Felt `closed` er kun sandt ved `CLOSE_SUCCESS` | `test_never_success_while_a_leg_is_open`, `test_both_legs_close_is_the_only_closed_state` |
| Idempotens, genstart, historik | Som 80 | `test_repeats_write_nothing_new`, `test_restart_keeps_the_retry_clock`, `test_earlier_state_events_are_never_changed` |

**Forskel fra 80 [F]:** perp-benet lukkes ikke længere. Funding bogføres videre på et åbent perp-ben, også i terminal tilstand (`test_funding_on_the_open_perp_keeps_booking_without_doubling`), fordi en åben simuleret position stadig betaler eller modtager funding. Ingen bog, ordre eller mærke. Et ben, der allerede er lukket, giver `PARTIAL_CLOSE_TERMINAL` (`test_a_leg_closed_before_the_host_was_declared_gone_is_partial_terminal`).

Mutationstest: at fjerne flerkildeproben, gøre alderen til `min`, gøre finished dato-baseret, fjerne blokeringen og terminal-grenen gav 14 fejl i de to testfiler. Rullet tilbage.

## P2. K3 og PR1

- **K3 har prioritet [direktøren].** K3's relevante gate er det ene kig (ændring 22 F): testen køres én gang pr. retning, første gang ≥ 60 gyldige runder på ≥ 20 UTC-døgn er opfyldt, og resultatet fryses (`research.k3_result`). Frist 2027-03-31; ellers `UNTESTABLE`.
- **PR1 er `DESIGN_ONLY / BLOCKED_DEPENDENCY`.** PR1 læser hverken K3's rækker eller overlappende resultater, før K3's gate er passeret og resultatet er frosset. PR1 måler samme afregningstidspunkt.
- **Ingen `fwd_spec_journal` uden særskilt godkendelse** (status `PROPOSED_NEEDS_SEPARATE_APPROVAL`). Uden den er PR1 ikke kørbar.
- Betingelsen i `PR1_PREREG_DRAFT_80.md` afsnit 12 om rækkefølgen er dermed afgjort. Filen er ikke ændret.
- Ingen lås og ingen data til PR1.

## P3. Statusregister

`research/status/status_register.py` (dev). Test: `tests/test_status_register_81.py`, syntetiske hændelser i midlertidige filer.

| Krav | Sådan |
|---|---|
| Append-only, hashkæde | JSONL med `seq`, `prev_hash`, `hash`. `append` holder lås og fsync. Tilføjer aldrig til en brudt kæde |
| `effective_ts` og `recorded_ts` | Begge kræves; `effective_ts` ≤ `recorded_ts`; `recorded_ts` må ikke gå baglæns |
| Kildehenvisning, forsøgs-ID, status, begrundelse | Felter `source`, `experiment_id`, `status`, `reason`, alle påkrævede. Status fra fast liste |
| Rettelse | Ny linje med `supersedes`; `current()` udledes ved læsning |
| Integritet | `verify` finder ændring, omhash, sletning, ombytning og afskåret linje. En afskåret hale kræver `expected_head` |
| Adskilt | Importerer ikke lab, sqlite eller nogen ledger. Læser kun den fil, den får |
| Ingen produktionsrækker | Ingen standardsti, ingen CLI. Stier inde i dev- eller produktions-checkout afvises. **Ingen registerfil er oprettet** |

## P4. Dev mod produktion `85db922` (read-only)

**Omfang [F]:** `git diff --stat 85db922 HEAD`: 747 filer, 176.037 tilføjelser, 47 sletninger. `85db922` er forfader til HEAD (165 commits). Mappefordeling: `research` 564 filer, `tests` 176, `lab` 7 (371+/33−).

| lab-fil | + / − | Indhold |
|---|---|---|
| `paper_runner.py` | 162 / 15 | 59-D-mark-hændelser (`mark_guarded`, `note_mark_failed`, `note_marked`, `mark_fields`), `funding_fields`, `_funding_guarded`-synlighed |
| `paper.py` | 91 / 7 | Funding-status, `exec_record`, `Book.observed`; `FUNDING_MISSING_MODE` står på `legacy` |
| `lane.py` | 47 / 8 | `mark_guarded`, `daily_observation`; `DAILY_RETURNS_MODE` står på `legacy` |
| `risk.py` | 17 / 0 | `BOOK_AGE_MODE` står på `off` |
| `markprov.py` | 48 / 0 | Ny, ikke koblet ind |
| `reportcheck.py` | 4 / 2 | Læser seneste række efter `id` frem for `ts` |
| `command.py` | 2 / 1 | Nye kinds i `NOT_OUTPUT` |

**Uændret [F]:** `lab/db.py` (ingen skemaændring), `straks.py`, `pairs.py`, `supervisor.py`, `ops.py`, `fleet.py`, `mission.py`, `watch.py`, `coverage.py`.

**Patch-kompatibilitet (`patch --dry-run` på filer fra `85db922`) [F]:**

| Patch | Resultat |
|---|---|
| 72 | Anvendes rent |
| 81 observability | Anvendes; `risk.py` med forskydning −17, `lane.py` −40 |
| 80 og 81 close v2 | **Fejler** hunk 2 i `paper_runner.py` (forudsætter `mark_guarded`) |

**Uforenelige eller afhængige dele [F/V]:**

- Close-patches kræver dev-motoren. Rækkefølge: dev-motor først, derefter close-patch, med hver sit ja.
- Produktionen har ingen `paper.mark_failed`; ved en dev-deploy kommer der én hændelse pr. fejlende konto med det samme.
- `reportcheck`-ændringen kan give andre sammenligninger end historiske rapporter, hvis rækker med ældre `ts` findes [V].
- `research/` og `tests/` kører fra dev-worktree mod produktionens lab.db (read-only). De behøver ikke deploy.

**Migrationsrisici [V]:** ingen databasemigration er nødvendig. Risici: collectorens genstartsimport (`lab.ops`, `lab.risk`), K1/K2/K3-deployvinduer, ordre 78's "ingen deploy før 20/11", pins af `straks.py` og `pairs.py`, og at deploy genstarter flåden. Ingen cherry-pick eller deploy er gjort.

## Uafklaret

1. Om og hvornår de to 81-patches anvendes (ejer, G12, deploy-vindue).
2. Om `straks.py`/`pairs.py`' enkelt-kilde-probe skal ændres.
3. Rækkefølgen af dev-motor og close-patch i produktion.
4. Valget af 7 døgn som endelig grænse.
5. Statusregisterets placering og første række.
6. Spot-probens kontakt med den blokerede vært under pause.
7. Hvad der skal ske med pm_lp-collectorens genstartsløkke (uændret).
