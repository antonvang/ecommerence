# Milepælsrapporter: tør kørsel og kørselsprocedure (direktørordre 60, spor A og C; skrevet 2026-11-09 kl. 12:59 lokal, 11:59 UTC)

Formålet er, at de tre rigtige rapporter kører rent første gang. Intet er evalueret før sin skæring.

| Spor | Rapport | Tidligste kørsel (UTC) | Tør kørsel | NOT_DUE nu | Fastlåste input | Dom |
|---|---|---|---|---|---|---|
| A (P0) | STRAKS 7 d, `straks_report.py` | **2026-11-12 17:11:51** | exit 0 | exit 2, lab.db ikke åbnet | alle matcher | KLAR |
| C (P1) | HFC-1 14 d, `hfc1_report3d.py --cohort 2026-11-04 --horizon 14d` | **2026-11-19 00:35:00** | exit 0 | exit 2, lab.db ikke åbnet | alle matcher | KLAR |
| C (P1) | PAR-BOG, `parbog_report.py` | **2026-11-19 20:51:09** | exit 0 | exit 2, lab.db ikke åbnet | alle matcher | KLAR |

- Ingen hash-afvigelse. Intet er fastlåst på ny.
- Én rettelse: skrivningen i STRAKS og PAR-BOG er nu sikker mod nedbrud (afsnit 5). Den ændrer intet tal.
- Ingen ændring i `lab/`, pins (`GATE_MATRIX.json`, `NOV14_READINESS.md`), produktion, processer eller netværk.
- Ingen commit. `python3 -m lab` er ikke kørt. Den rigtige lab.db er ikke åbnet.

## 0. Fælles metode

**Tør kørsel:** hvert værktøj har `--dry-run`. Det bygger en syntetisk database i en midlertidig mappe og bruger et
simuleret ur efter fristen. Outputtet kom i scratch, aldrig i den kanoniske mappe.

**NOT_DUE-vagten** er bevist på tre måder:
- Det rigtige CLI uden `--dry-run` er kørt nu (11:53 UTC). Alle tre gav exit 2 `NOT_DUE`.
- De samme tre kørsler gik gennem en Python-audit-hook (`sys.addaudithook`). Den logger hver `open()` af en
  lab.db-sti, hver `sqlite3.connect` og hvert socket-kald. Resultat: ingen af dem. Kontrol: samme hook på en tør kørsel
  logger to `sqlite3.connect` (den syntetiske db). Hooken virker altså.
- Koden: `run()` tjekker uret, før `connect_ro()` kaldes. STRAKS linje 489, PAR-BOG linje 219, HFC-1 linje 348.
  Der findes ikke noget `--now`, og uret er `time.time()`.

**Kanoniske mapper før og efter:** `research/data/straks_report/` og `research/data/parbog_report/` findes ikke.
`research/data/hfc1_report3d/` har kun de fire 3 d-filer fra 11-08 og 11-09. Ingen ny fil under `research/data/`.

**Tests:**
- `python3 -m unittest tests.test_research_milestone_reports tests.test_research_hfc1_readiness`: 69 OK. Før
  rettelsen var det 67; de 2 nye tests står i afsnit 5.
- `tests.test_research_gates tests.test_lab_safety`: 12 OK.

## 1. STRAKS 7 d (spor A, P0), 2026-11-12

### 1.1 Tør kørsel

`python3 research/tools/straks_report.py --dry-run --out <scratch>`: exit 0, `REPORTED`.
- Filerne er `DRYRUN_straks_7d_2026-11-12.json` og `.md`.
- `result_sha256` er `1efe6823b685…`, både før og efter rettelsen. Den er deterministisk.
- JSON-filen har de forventede nøgler: `accounts` (FØLG og MOD), `cutoff_utc` 2026-11-12 17:01:51, `signal_window_start_utc`
  17:01:11 (payload-t), `flag_41b_move_ids`, `research_status` INCONCLUSIVE, `dry_run` true og `db_uri` med `?mode=ro`.
- Hver konto har `with_41b` og `without_41b`, signaler (set, handlet, sprunget, afvist og uafklaret), handler, timing
  og klasser. `decomposition_failures` er 0.
- Markdown-filen har de faste sætninger, tabellen med og uden 41b, tabellen pr. klasse og en timinglinje.

### 1.2 NOT_DUE-vagt

Den rigtige kørsel `python3 research/tools/straks_report.py` gav exit 2:
`{"status": "NOT_DUE", "detail": "data cutoff 2026-11-12 17:01:51 UTC; earliest run 2026-11-12 17:11:51 UTC"}`.
lab.db blev ikke åbnet, og ingen fil blev skrevet.

### 1.3 Fastlåste input (kontrolleret 2026-11-09 11:54 UTC)

| Input | Fastlåst værdi | Kilde | Nu | OK |
|---|---|---|---|---|
| Konti | FØLG `LANE_35f39bb233` (`straks\|cont`), MOD `LANE_a751c1f595` (`straks\|rev`), kilde `straks` | NOV14 afsnit 7; `lane.ledger_id` (test `Straks.test_times`) | i værktøjet, og testen består | ja |
| Start | `lane.started` ts 2026-11-05 17:01:51 UTC | NOV14 afsnit 7, G22 | `START_TS`; tjekkes mod db ved kørsel (exit 3 ved afvigelse) | ja |
| Skæring | start + 7 × 24 t = 2026-11-12 17:01:51; kørsel ≥ +10 min | AMB-24, G22 | `CUTOFF`, `SETTLE_S` 600 | ja |
| 41b-signaler | 58416, 58417, 58591 | rettelse 41b; `net_report.FLAG_41B` | ens i begge filer | ja |
| `PROTOCOL_V3.md` hele filen | `0a09b3e954d9…` (`ec91280`) | NOV14-pin | `0a09b3e954d9…` | ja |
| Ændring 41 (linje 4309-4339) | låst tekst | PROTOCOL_V3 | sha256 `0d42923a85af0ccf…`; uændret siden `60f9825` | ja |
| Ændring 41a (linje 4341-4362) | låst tekst | PROTOCOL_V3 | `a60098fb8f4c820b…`; uændret siden `14a6fc5` | ja |
| Rettelse 41b (linje 4445-4453) | låst tekst | PROTOCOL_V3 | `9d858db4796eac8e…`; uændret siden `ebb51d2` | ja |
| `lab/straks.py` | `7a110f1fa20f…` (`814ef8b`) | NOV14-pin `STRAKS_CODE` | dev og produktion `7a110f1fa20f…` | ja |
| GATE_MATRIX-linjer | 4336 (41 p. 7), 4358 (41a p. 4) | G22 | linjerne er "7. **Rapport:**" og "4. **Opgørelse" | ja |
| Værktøjet | — | ikke fastlåst | `d1eec5c346d7…` før rettelsen, `9e8356e2ff2a…` efter | — |

### 1.4 Kørselsprocedure 2026-11-12

Kør fra dev-worktree `/home/anton/copybot-dev/copybot`. Værktøjet findes ikke i produktions-checkoutet. Databasen er
produktionens lab.db (standard `--db`). Den åbnes kun med `?mode=ro` og `query_only`.

**Forudsætninger. Alle skal holde, ellers stop:**

```
date -u                                    # FØRST. Skal være >= 2026-11-12 17:11:51 UTC
cd /home/anton/copybot-dev/copybot
git status --short research/tools/straks_report.py research/PROTOCOL_V3.md lab/straks.py   # tomt
sha256sum research/tools/straks_report.py  # 9e8356e2ff2a… (rettelsen committed) eller d1eec5c346d7… (uden)
sha256sum lab/straks.py /home/anton/ecommerence/copybot/lab/straks.py     # begge 7a110f1fa20f…
grep -n "^## Ændring 41 (\|^### Ændring 41a (\|^### Rettelse 41b (" research/PROTOCOL_V3.md   # 4309, 4341, 4445
sed -n 4309,4339p research/PROTOCOL_V3.md | sha256sum     # 0d42923a85af0ccf…
sed -n 4341,4362p research/PROTOCOL_V3.md | sha256sum     # a60098fb8f4c820b…
sed -n 4445,4453p research/PROTOCOL_V3.md | sha256sum     # 9d858db4796eac8e…
python3 -m unittest tests.test_research_milestone_reports  # OK
ls research/data/straks_report/ 2>/dev/null                # må ikke allerede have straks_7d_2026-11-12.*
```

- Er hele `PROTOCOL_V3.md` ændret siden `0a09b3e9…`, er det kun i orden, hvis de tre linjenumre og de tre sektionshashes
  stadig passer. Det er tilfældet, hvis der kun er tilføjet tekst efter 43a. Passer de ikke: stop, og kør ikke.
- Tjek, at ingen af filerne er 0 bytes efter et nedbrud (`git status`).

**Kørsel, én gang:**

```
python3 research/tools/straks_report.py
echo "exit=$?"
```

**Kontrol af outputtet** (`research/data/straks_report/straks_7d_2026-11-12.json` og `.md`):
- exit 0 og `REPORTED`. Begge filer findes.
- `dry_run` er false. `db_uri` er `file:/home/anton/ecommerence/copybot/data/lab/lab.db?mode=ro`.
- `cutoff_utc` er 2026-11-12 17:01:51 UTC, og `start_utc` er 2026-11-05 17:01:51 UTC.
- For begge konti er `lane_started_utc` 2026-11-05 17:01:51 UTC.
- `signal_window_start_utc` er cirka 17:01:11. `signals_between_payload_t_and_event_ts` er et tal; noter det.
- `account_at_last_mark.marked_at_utc` ligger i timen før skæringen. Er den ældre, er kontoen STALE. Noter
  `hours_without_mark` og `fills_after_last_mark_before_cutoff`.
- `with_41b.trades.decomposition_failures` er 0 for begge konti. Er den over 0: rapportér det, og ret intet.
- `with_41b.timing.entry_before_signal_not_flagged_41b` er `[]`. Ellers er der en ny timingafvigelse, som skal
  rapporteres.
- `retired_before_cutoff` er null. Ellers står stoppet i rapporten; noter det.
- `research_status` er INCONCLUSIVE, og md-filen har de faste sætninger.

**Andre udfald:**
- **exit 2:** for tidligt. Vent. Uret må ikke ændres.
- **exit 3:**
  - `START_MISMATCH`: stop og rapportér. Kontoens start er ikke den fastlåste.
  - `NO_DB`: tjek stien.
  - `EXISTS`: slet intet. Sammenlign `result_sha256`, og spørg.
  - `WORDING`: stop.
  - Kun en `.md` eller en tom `.json` efter et nedbrud: slet intet selv. Spørg først, og kør så igen.

**Commit:** `research/data/straks_report/straks_7d_2026-11-12.json` og `.md`. Skriv `result_sha256`, værktøjets sha256 og
`date -u` i commit-teksten. Ingen pin-ændring i samme commit uden en direktørordre.

### 1.5 DNS-afhængighed

- STRAKS handler kun perps. Bøgerne kommer fra `fapi.binance.com/fapi/v1/depth` (`paper_runner.fetch_book`; ingen
  `.SPOT`-sti i `lab/straks.py`).
- Signalerne kommer fra `fapi` klines (`lab/moves.py`). Det gør `opportunity.outcome` også.
- Timemærkningen af STRAKS gik normalt under DNS-blokeringen (commit `7dc00a9`, 59-C: STRAKS-FØLG, STRAKS-MOD og
  PAR-BOG FRESH). Det er ikke tjekket i lab.db nu.
- Selve rapporten bruger intet netværk.
- **STRAKS behøver ikke `data-api.binance.vision`.** Gik fapi-data tabt i perioden, ses det i `hours_without_mark`
  og som "uafklaret" signaler. Det bliver ikke skjult.

## 2. HFC-1 14 d for kohorte 2026-11-04 (spor C, P1), 2026-11-19

### 2.1 Tør kørsel

`python3 research/tools/hfc1_report3d.py --dry-run --horizon 14d --out <scratch>`: exit 0, `REPORTED`.
- Filen er `DRYRUN_hfc1_14d_2026-11-04.json` og `.md`, med `result_sha256` `22a9a4893ee5…`.
- Vinduet er [2026-11-05 00:00, 2026-11-19 00:00), og `due_utc` er 2026-11-19 00:35:00.
- Der er 336 af 336 snapshots, og det sidste er 2026-11-18 23:02.
- Grupperne hedder `bestod_F1-F6_14d_N*`, og offdb-forslaget er `HFC1_OUTCOME_14D_2026-11-04` med `written` false.

Ekstra kontrol i scratch (`hfc14_realcohort.py`):
- Den **committede** kohortefil 11-04 og den rigtige `PINNED` blev brugt sammen med en **syntetisk** census. Der var
  ingen lab.db og intet netværk.
- Ved 00:00:00 og 00:34:59 kom NOT_DUE, og intet blev skrevet. Ved 00:35:00 kom REPORTED.
- Fundne tal: C0 120, C0+ 72, F1 intet spotpar 117, F1 multiplikator 1.
- `bestod_F1-F6_14d_N1000` = 1 og `N5000` = 0. Det passer med protokollens ex ante-tal "0 / 1 (XVG)".
- `cohort_file_pinned_in_protocol` er true. En ny kørsel gav samme hash (idempotent).

### 2.2 NOT_DUE-vagt og hvordan 14 d beregnes

Den rigtige kørsel `python3 research/tools/hfc1_report3d.py --cohort 2026-11-04 --horizon 14d` gav exit 2:
`{"2026-11-04": {"due_utc": "2026-11-19 00:35:00 UTC", "status": "NOT_DUE"}}`. lab.db blev ikke åbnet.

Sådan beregnes 14 d (`window()`, linje 80-85):
- start = 11-04 00:00 + 1 døgn = 2026-11-05 00:00;
- slut = start + 14 × 86.400 s = 2026-11-19 00:00;
- frist = slut + 35 min = 2026-11-19 00:35:00.

Det er samme vindue som `hfc1_daily.outcomes` (`t1 = end + 42 // 3 døgn`). Det er senere end NOV14 linje 500 (00:00)
og dermed fail-closed. `run()` sammenligner kun de ønskede kohorters frist med uret og åbner databasen bagefter.
Testene R04 (14 d NOT_DUE den 11-08) og R02c (databasen åbnes ikke) dækker det.

### 2.3 Fastlåste input (kontrolleret 2026-11-09 11:54 UTC)

| Input | Fastlåst værdi | Kilde | Nu | OK |
|---|---|---|---|---|
| Kohortefil `research/data/hfc1/2026-11-04.json` | præfiks `a5f831c40c19` | protokollen; `PINNED` | `a5f831c40c19eb1e65d0…`; git-ren; 120 rækker = `c0`; har `covered_14d_1000/5000` | ja |
| Regeldelen: de første 3.178 bytes af `HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md` | `cd1b6fc66000544f…` (`48a0a63`) | NOV14-pin `HFC1_PROTOCOL` | `cd1b6fc66000544f…`; filen i `48a0a63` er præcis 3.178 bytes med samme hash | ja |
| Vindue og frist | [11-05 00:00, 11-19 00:00), kørsel ≥ 00:35 | protokol "Udfald"; NOV14 linje 293/500 | `window()` | ja |
| Størrelser | 1.000 og 5.000 USDT pr. ben | protokol F4 | `SIZES` | ja |
| `research/data/hfc1/2026-11-05.json` (bruges ikke ved `--cohort 2026-11-04`) | `b43afaf295c4` | `PINNED` | `b43afaf295c4…` | ja |
| Værktøjet | `e72e9f436055…` (tjekket ved 3 d-kørslen 11-09, commit `c09681a`) | — | `e72e9f436055…`; ikke ændret her | ja |

### 2.4 Kørselsprocedure 2026-11-19 (HFC-1 14 d)

**Forudsætninger:**

```
date -u                                    # FØRST. Skal være >= 2026-11-19 00:35:00 UTC
cd /home/anton/copybot-dev/copybot
git status --short research/data/hfc1 research/tools/hfc1_report3d.py research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md
sha256sum research/data/hfc1/2026-11-04.json      # a5f831c40c19eb1e…
sha256sum research/tools/hfc1_report3d.py         # e72e9f436055…
head -c 3178 research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md | sha256sum   # cd1b6fc66000544f…
python3 -m unittest tests.test_research_hfc1_readiness tests.test_research_milestone_reports   # OK
ls research/data/hfc1_report3d/                    # må ikke allerede have hfc1_14d_2026-11-04.*
```

**Kørsel, én gang, med eksplicit kohorte og horisont:**

```
python3 research/tools/hfc1_report3d.py --cohort 2026-11-04 --horizon 14d
echo "exit=$?"
```

Kør den ikke uden `--cohort`. Ellers kommer 11-05 med som NOT_DUE (dens frist er 11-20 00:35). Kør heller ikke 11-04
og 11-05 sammen.

**Kontrol af outputtet** (`research/data/hfc1_report3d/hfc1_14d_2026-11-04.json` og `.md`):
- exit 0. `cohorts` er `{"2026-11-04": "REPORTED"}`, og begge filer findes.
- `census_snapshots_expected` er 336. Noter `census_snapshots_in_window`, `census_hours_missing` og `last_snapshot_utc`
  (forventet 2026-11-18 23:0x UTC).
- Medlemmer med færre end 252 observationer er "manglende". Det er protokollens 25 %-regel.
- C0 120, C0+ 72, F1 intet spotpar 117, F1 multiplikator 1 og `bestod_F1-F5_N1000` 2. Ex ante er
  `bestod_F1-F6_14d_N1000` 1 og `N5000` 0.
- `cohort_file_pinned_in_protocol` er true. `research_status` er INCONCLUSIVE. `offdb_proposal.entry.id` er
  `HFC1_OUTCOME_14D_2026-11-04`, `already_present` false og `written` false.
- exit 2, exit 3 og `NO_COHORT_FILE`: som i HFC1_REPORT_READINESS afsnit 4.

**Commit:** de to rapportfiler. Tilføj derefter `offdb_proposal.entry` i hånden til
`research/data/factory/offdb_studies.json`. Efter B2-rettelsen giver en ny kørsel ikke EXISTS, men der er ingen grund
til at køre igen.

### 2.5 DNS-afhængighed

- HFC-1 14 d bruger kun census/1-snapshots. `lab/census.py` henter `fapi.binance.com/fapi/v1/premiumIndex` og
  `/fapi/v1/ticker/24hr`.
- Census var komplet under blokeringen. 3 d-rapporten for 11-05 havde 72 af 72 snapshots, 0 timer uden snapshot og
  sidste snapshot 2026-11-08 23:00:54 UTC. Det er kun dækningstal, ikke udfald.
- Omkostningen kommer fra kohortefilen, som blev dannet 11-05. Den er allerede gemt.
- **HFC-1 14 d behøver ikke `data-api.binance.vision`.** DNS-blokeringen påvirker kun dannelsen af nye kohorter
  (11-06 til 11-08 blev ikke dannet). Den påvirker ikke 11-04's udfald.

## 3. PAR-BOG diagnostisk (spor C, P1), 2026-11-19

### 3.1 Tør kørsel

`python3 research/tools/parbog_report.py --dry-run --out <scratch>`: exit 0, `REPORTED`.
- Filen er `DRYRUN_parbog_2026-11-19.json` og `.md`, med `result_sha256` `06cb407b0408…` både før og efter rettelsen.
- Der er 4 handler, hvoraf 3 er lukket. Udgangsårsagerne er normal, stop, tid og "åben ved skæring".
- `integrity_problems` er `[]`, `tid_exit_before_72h` er `[]` og `decomposition_failures` er 0.
- `not_sent_not_recorded_in_db` er null (UNKNOWN).
- Markdown-filen har en tabel pr. par og årsag samt linjer om afvisninger og integritet.

### 3.2 NOT_DUE-vagt

Den rigtige kørsel `python3 research/tools/parbog_report.py` gav exit 2:
`{"status": "NOT_DUE", "detail": "data cutoff 2026-11-19 20:41:09 UTC; earliest run 2026-11-19 20:51:09 UTC"}`.
lab.db blev ikke åbnet, og ingen fil blev skrevet.

### 3.3 Fastlåste input (kontrolleret 2026-11-09 11:54 UTC)

| Input | Fastlåst værdi | Kilde | Nu | OK |
|---|---|---|---|---|
| Konto | PAR-BOG `LANE_68b8b6feb9`, nøgle `pairs\|v1`, kilde `pairs` | NOV14 afsnit 8; `lane.ledger_id(pairs.KEY)` (test) | i værktøjet, og testen består | ja |
| Par | BZ/CL, ETH/BTC, QQQ/SPY, XAG/XAU | 43 punkt 1; `lab/pairs.PAIRS` (test) | ens | ja |
| Start | `lane.started` ts 2026-11-05 20:41:09 UTC | NOV14 afsnit 8, G23 | `START_TS`; tjekkes mod db ved kørsel | ja |
| Skæring | start + 14 × 24 t = 2026-11-19 20:41:09; kørsel ≥ +10 min | AMB-25, G23 | `CUTOFF`, `SETTLE_S` 600 | ja |
| Ændring 43 (linje 4423-4443) | låst tekst | PROTOCOL_V3 | sha256 `4842d5e7b0835428…`; uændret siden `77868fd` | ja |
| Ændring 43a (linje 4455-4466) | låst tekst | PROTOCOL_V3 | `ee72e5da9563cd31…`; hele filen er lig `ec91280`, hvor 43a blev indført | ja |
| GATE_MATRIX-linje 4442 (43 p. 7) | — | G23 | linjen er "7. **Opgørelse:**" | ja |
| `lab/pairs.py` | `5c9b60a4314a…` (`b1ef7a6`) | NOV14-pin `PAIRS_CODE` | dev og produktion `5c9b60a4314a…` | ja |
| Værktøjet `parbog_report.py` | — | ikke fastlåst | `8460017cac9f…` (uændret); bruger `straks_report.write_outputs` | — |

### 3.4 Kørselsprocedure 2026-11-19 (PAR-BOG)

**Forudsætninger:**

```
date -u                                    # FØRST. Skal være >= 2026-11-19 20:51:09 UTC
cd /home/anton/copybot-dev/copybot
git status --short research/tools/parbog_report.py research/tools/straks_report.py research/PROTOCOL_V3.md lab/pairs.py
sha256sum research/tools/parbog_report.py  # 8460017cac9f…
sha256sum research/tools/straks_report.py  # 9e8356e2ff2a… (rettelsen committed) eller d1eec5c346d7…
sha256sum lab/pairs.py /home/anton/ecommerence/copybot/lab/pairs.py       # begge 5c9b60a4314a…
grep -n "^## Ændring 43 (\|^### Ændring 43a (" research/PROTOCOL_V3.md    # 4423, 4455
sed -n 4423,4443p research/PROTOCOL_V3.md | sha256sum     # 4842d5e7b0835428…
sed -n 4455,4466p research/PROTOCOL_V3.md | sha256sum     # ee72e5da9563cd31…
python3 -m unittest tests.test_research_milestone_reports  # OK
ls research/data/parbog_report/ 2>/dev/null                # må ikke allerede have parbog_2026-11-19.*
```

**Kørsel, én gang:**

```
python3 research/tools/parbog_report.py
echo "exit=$?"
```

**Kontrol af outputtet** (`research/data/parbog_report/parbog_2026-11-19.json` og `.md`):
- exit 0. Begge filer findes. `dry_run` er false, og `db_uri` er produktionens med `?mode=ro`.
- `start_utc` er 2026-11-05 20:41:09 UTC, og `cutoff_utc` er 2026-11-19 20:41:09 UTC.
- `per_pair` har præcis de fire par.
- `integrity_problems` og `tid_exit_before_72h` er `[]`. Er de ikke tomme: rapportér dem, og ret intet.
- `total.decomposition_failures` er 0.
- `account_at_last_mark.marked_at_utc` ligger i timen før skæringen.
- Noter `funding_rows_not_assigned_to_a_trade` og `refused_in_db`.
- Værdierne i `not_sent_not_recorded_in_db` er null (UNKNOWN, aldrig 0).
- `research_status` er INCONCLUSIVE.
- exit 2 og exit 3 håndteres som for STRAKS (1.4).

**Commit:** `research/data/parbog_report/parbog_2026-11-19.json` og `.md`, med `result_sha256`, værktøjets hash og
`date -u` i commit-teksten.

### 3.5 DNS-afhængighed

- Begge ben er USD-M-perps (43 punkt 1). Bøgerne kommer fra `fapi/v1/depth` og timebarerne fra `fapi/v1/klines`
  (43 punkt 3).
- `lab/pairs.py` har ingen `.SPOT`-sti. Mærkningen var FRESH under blokeringen (59-C).
- **PAR-BOG behøver ikke `data-api.binance.vision`.**

**Samlet om DNS:** ingen af de tre rapporter behøver `data-api.binance.vision`. Blokeringen ramte spotbenene i de 9
bane- og carry90-konti og dannelsen af HFC-1-kohorter. Ingen af dem indgår i de tre rapporter.

## 4. Planlægning på dagene

- 2026-11-12: STRAKS kl. ≥ 17:11:51 UTC.
- 2026-11-19: HFC-1 14 d kl. ≥ 00:35:00 UTC og PAR-BOG kl. ≥ 20:51:09 UTC. De er uafhængige.
- Der er ingen deploy, så K1-K3-vinduerne gælder ikke. Kørslerne læser kun.

## 5. Rettelse: skrivning sikker mod nedbrud i STRAKS og PAR-BOG

**Fund:** `straks_report.write_outputs` bruges også af `parbog_report.py`. Den skrev `.json` og derefter `.md`, uden
atomisk omdøbning og uden fsync. Det er samme fejl som HFC-1's B3, som blev rettet 11-06, men kun i
`hfc1_report3d.py`.

Går maskinen ned mellem de to skrivninger, ser næste kørsel samme `result_sha256` i `.json`. Den returnerer exit 0,
og `.md` mangler stadig. Værten har haft flere urene stop, og efter et nedbrud er der set friske filer på 0 bytes.
Milepælskørslen er én gang, så det er en reel fejl.

**Rettelse** (kun i `research/tools/straks_report.py`, samme logik som den accepterede B3-rettelse i HFC-1):
- Hver fil skrives til `<fil>.tmp`, får `flush` og `fsync` og flyttes på plads med `os.replace`.
- `.md` skrives først, så en `.md` alene bliver afvist (EXISTS), aldrig troet.
- Findes `.json` med samme resultat, men ingen `.md`, skrives `.md`, og kørslen lykkes.
- En tom `.json` eller et andet resultat giver stadig EXISTS (exit 3), og filen bevares.

Der er ingen ændring i formler, skæringer, regler, tekst eller `result_sha256`. De tørre kørsler gav samme hash før og
efter: STRAKS `1efe6823b685…`, PAR-BOG `06cb407b0408…`.

**Regressionstests** (`tests/test_research_milestone_reports.py`, klasse `CrashSafeWrites`, kun syntetiske data):
- `test_rerun_after_crash_between_json_and_md_completes_the_md` gælder STRAKS og PAR-BOG. Den fejlede før rettelsen
  ("False is not true : straks") og består nu.
- `test_lone_md_or_empty_json_is_refused_and_kept` gælder begge: EXISTS, filen bevares, og ingen `.tmp` bliver tilbage.

Værktøjets sha256 er `d1eec5c346d7…` før og `9e8356e2ff2a…` efter. Afvises rettelsen, skal begge filer rulles tilbage
(`git checkout`), og procedurens hash er så `d1eec5c346d7…`.

## 6. Bemærkninger, ikke rettet (ingen af dem stopper en kørsel)

- **O1:** HFC-1's faste linje "3 dage siger intet om langsigtet profit." står også i 14 d-rapporten (`FIXED_LINES`
  afhænger ikke af horisonten). Sætningen er sand, men passer ikke til en 14 d-rapport. Linjen kan gøres afhængig af
  horisonten, så 3 d-teksten forbliver byte-identisk. Det er ikke gjort, fordi det ikke er en kørselsfejl og ændrer
  rapportens faste tekst. Det er direktørens valg.
- **O2:** `offdb_studies.json` har `HFC1_OUTCOME_3D_2026-11-04`, men ikke `HFC1_OUTCOME_3D_2026-11-05`, selv om
  11-05-rapporten blev committed 11-09 (`c09681a`). Det er uden for spor A og C. Noteret.
- **O3:** `--dry-run` lægger sin syntetiske db i `/tmp/<værktøj>_dry_*` og sletter den ikke. Det er harmløst.
- **O4:** `MILESTONE_REPORT_TOOLS.md` nævner "34 tests". Nu er der 36 i den fil. Den er ikke opdateret her.

## 7. Hvad der ikke er gjort

- Den rigtige lab.db er ikke åbnet, og ingen rapport er kørt efter sin frist. Ingen NOT_DUE er omgået.
- Der er ingen ændring i `lab/`, pins, produktion, processer eller netværk. Intet er committed.
- `research/data/N4_KIMCHI_PAIRS_2026-11-02.json` og karantænemappen er ikke læst.
