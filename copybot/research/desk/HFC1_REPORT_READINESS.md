# HFC-1 3 d-rapport: teknisk parathed til 2026-11-08 ≥ 00:35 UTC (direktørordre 53 P3; skrevet 2026-11-06 kl. 16:25 lokal, 15:25 UTC)

> Opdatering 2026-11-06: patchen i afsnit 3 er anvendt på research/tools/hfc1_report3d.py; B1–B4 er rettet, de 5 expectedFailure-markeringer er fjernet, og testene består som almindelige regressionstests. Kørselsproceduren i afsnit 4 gælder fortsat (B2b-forsigtigheden er ikke længere nødvendig, men skader ikke).

**Dom: TECHNICALLY_READY**, på betingelser. Kørselsproceduren i afsnit 4 skal følges, især `--cohort 2026-11-04`
eksplicit. Patchen i afsnit 3 anbefales anvendt før 11-08 00:35 UTC.

Fire fund (B1-B4) er beskrevet nedenfor. Hvert har en fejlende test med `unittest.expectedFailure` og en foreslået
patch. Ingen af dem ændrer et tal i rapporten. Det gælder dækning, manglende, frafald, realiseret funding,
break-even, netto og dækningsgrad. B2-B4 undgås med proceduren. B1 er en forkert statusmærkning i JSON-filen. Markdown-
rapporten bruger ikke det felt.

**Grundlag:**
- Værktøjet: `research/tools/hfc1_report3d.py`, sha256 `33e9b90807e6deedb62eeb445809bf1cd0706b35d2bb78d7e531a55ac991e1e9`
  (commit `65e4329`). Det er **ikke ændret**.
- Nye filer: denne fil og `tests/test_research_hfc1_readiness.py` med 32 tests (27 OK og 5 forventede fejl).
- Kun syntetiske data. Den rigtige lab.db er ikke åbnet, og værktøjet er ikke kørt mod den. Intet netværk, socket er
  erstattet i testene, og pm_lp er ikke rørt.
- De committede kohortefiler i `research/data/hfc1/` er læst. Test R18 kører dem gennem værktøjet med en **syntetisk**
  census. Det kontrollerer filformat og hashes. Det giver intet rigtigt udfald.

Kørt kommando:

```
python3 -m unittest tests.test_research_hfc1_readiness tests.test_research_milestone_reports tests.test_research_gates tests.test_lab_safety
Ran 78 tests … OK (expected failures=5)
```

## 1. Krav → værktøj → test → dom

Test-id'er er metodenavne i `tests/test_research_hfc1_readiness.py` (R…/B…) og `tests/test_research_milestone_reports.py`
(`HFC1.*`).

| # | Krav (kilde, ordret) | Værktøjets adfærd | Test | Dom |
|---|---|---|---|---|
| 1 | Protokol "Udfald" l. 32: "For **alle** i C0 (ikke kun dem der består F1-F6)" | Hver række i kohortefilen bliver et medlem; `c0` skal svare til antal rækker (ellers exit 3) | R05, R18 (120 rigtige rækker), `HFC1.test_all_c0_members_incl_no_spot_pair` | PASS |
| 2 | Ordre 46 P2: "samtlige C0-kandidater (også uden spotpar), manglende data og frafald separat; ingen survivorship bias" | Frafald (`drop`), manglende (`missing`) og omkostning ukendt (`cost_unknown_no_spot_or_book`) tælles hver for sig; realiseret funding regnes også for frafaldne | R05, R07 | PASS |
| 3 | Protokol l. 33-34: "Mangler et medlem i senere snapshots (afnoteret, omdøbt) eller mangler > 25 % af snapshots i vinduet, er udfaldet **manglende** og tælles som 'ikke dækket', aldrig som succes" | Manglende = ingen obs., < 54 af 72 eller fraværende i vinduets sidste snapshot. Med kendt omkostning er `covered_ex_post` False, og netto er n/a. Afnoterede bliver i opgørelsen med grunde | R06 (afnoteret efter 48 t), R12 (54 = ikke manglende, 53 = manglende), R12b (ingen snapshots), R12c (null-funding) | PASS |
| 4 | Protokol l. 35-36: "andel dækket ex post (realiseret funding ≥ omkostning ved N), median dækningsgrad … separat for C0, C0+ og dem der bestod F1-F6" | Grupperne C0, C0+, `bestod_F1-F5_N*` og `bestod_F1-F6_3d_N*`. Både "af kendte" og den strenge nævner. Lighed tæller som dækket (≥) | R05, R08 (lighed), R09 (andele og medianer håndregnet) | PASS |
| 5 | Protokol F4: "N = 1.000 og 5.000 USDT pr. ben"; AMB-23 | Begge størrelser overalt. Allokeret kapital er 2N ved 1x (2.000 / 10.000, MRT-5) | R08, R10 | PASS |
| 6 | Svar på ordre 46: "rapporterne viser fortsat både funding-break-even (mod perp-notional) og netto på samlet allokeret kapital" | `breakeven_apr_perp_notional` = omk. / (N × 3/365); `net_on_allocated` = (realiseret − omk.) / 2N | R08 (håndregnet eksempel, afsnit 2) | PASS |
| 7 | Protokol "Kohorte og filtre": "frafald rapporteres ved hvert trin" | Ét frafaldstrin pr. gruppe: F1 intet spotpar, F1 multiplikator, F2, F3 (tekst før ":"), F3 tom side, F4 pr. N | R05 (alle trin `hfc1_daily.cohort()` kan skrive) | PASS |
| 8 | Ordre 49 P2: "08/11 HFC-1 (dækning, manglende observationer, realiserede omkostninger, netto)" | Omkostningen er kohortens bogaflæsning ind og ud på samme bog plus taker og tillæg. Det står som fast linje i både md og json. En realiseret exit-omkostning er **ikke implementeret** (MRT-3) | R10 | PASS (mærket begrænsning L1) |
| 9 | Svar på ordre 49 P1: "08/11 HFC-1 3 d-udfald (hvis vinduet faktisk er afsluttet)"; "fremtidige observationer rapporteres ikke som gennemførte". Ordre 53 P3: "NOT_DUE indtil vinduet er afsluttet". `GATE_MATRIX.json` G21_HFC1_3D | NOT_DUE (exit 2) før vinduesslut + 35 min. Intet skrives, og databasen åbnes ikke. Gælder ved 23:59:59, 00:00:00, 00:34:00 og 00:34:59; ved 00:35:00 kommer REPORTED. Hver kohorte har sit eget vindue. Uret er maskinens, og `--now` findes ikke | R02, R02b (CLI), R02c (db ikke åbnet), R03 (11-05 først 11-09 00:35), R04 (14 d), `HFC1.test_not_due_before_window_end_writes_nothing` | PASS |
| 10 | Ordre 46 P2: "ingen konklusion om langsigtet profit fra 3 dage". Protokol: "ingen statistisk test, intet afgøres". AMB-21 | Faste sætninger i md og json. Ordkontrollen nægter "profitabel", "lønsom", "anbefal" osv. | R10 | PASS |
| 11 | Ordre 49 P2: "Én versionsstyret forskningsstatus PASS/FAIL/INCONCLUSIVE/NOT DUE pr. undersøgelse" | `research_status` = INCONCLUSIVE (beskrivende); NOT_DUE er exit 2 | R10, R02 | PASS |
| 12 | `FACTORY_REGISTRY.md` l. 66-67: "HFC-1's udfald fra 08/11 tilføjes til den tid" | `offdb_proposal` har præcis de felter, de 22 eksisterende poster har. `written: false`. Filen er uændret (sha256) | R13 | PASS (men se B2) |
| 13 | `MILESTONE_REPORT_TOOLS.md`: "To kørsler på samme data giver samme hash" | `result_sha256` kan genberegnes uafhængigt af JSON-filen. Det er stabilt over kørselstid og out-mappe og med eksplicit `--cohort` | R14, R14b | PASS med `--cohort` · **FAIL B2/B2b** uden |
| 14 | Samme: "En eksisterende rapport med et andet resultat overskrives ikke (exit 3, EXISTS). Samme resultat er idempotent." | Andet resultat, kun en md-fil eller en tom json efter et nedbrud giver EXISTS (exit 3), og filen bevares. Samme resultat lader filerne stå uændrede | R15, `HFC1.test_existing_different_report_not_overwritten` | PASS · **FAIL B3** (manglende md bliver ikke opdaget) |
| 15 | `G29_LABDB_RO` / MILESTONE: "sqlite-URI … ?mode=ro plus PRAGMA query_only=ON" | Én `sqlite3.connect` (connect_ro). Skrivning fejler. Ingen -wal/-shm/-journal på en rollback-db. Med en aktiv WAL-skriver (som i produktion) er hverken db eller -wal ændret | R16, R16b, R16c, R17b, `HFC1.test_read_only_deterministic_offdb_proposal` | PASS (begrænsning L5) |
| 16 | MILESTONE "Integritet": "exit 3 … hvis en kohortefil ikke matcher protokollens sha256-præfiks … eller hvis databasen mangler" | De rigtige filer matcher `a5f831c40c19…` og `b43afaf295c4…`. En syntetisk 11-04-fil afvises via CLI (exit 3) | R02b, R18, `HFC1.test_pinned_cohort_hashes` | PASS · **FAIL B4** (manglende kohortefil giver exit 2 "NOT_DUE") |
| 17 | Ordre 53 P3 (opgaven): protokolfilens låste hash er uændret efter kørslen | Protokol, offdb-liste, kohortefiler og værktøj har samme sha256 før og efter syntetisk kørsel, dry-run og en for tidlig CLI-kørsel. Den kanoniske outputmappe er ikke oprettet. Regeldelen (første 3.178 bytes = filen i `48a0a63`) har sha256 `cd1b6fc6…` | R17 | PASS (se L7) |
| 18 | Ordre 46 P2 / survivorship: forsvundne kandidater bliver med, med status | Afnoterede bliver med som manglende (R06). En COIN-perp, der forlader `coin_perps`, mærkes "perp ikke TRADING" (B1-kontrol). **Tokeniserede aktie-perps mærkes fejlagtigt "perp ikke TRADING"** | R06, `test_B1_control…`, **B1** | PASS · **FAIL B1** (kun mærkning) |
| 19 | MILESTONE: "Kun standardbiblioteket, intet netværk og aldrig pm_lp" | Ingen urllib.request/socket/http.client/pm_lp i koden. Socket er erstattet i alle tests | R17b, `Static.test_sources` | PASS |
| 20 | Protokol "Kendte begrænsninger": 8 t-antagelsen | Fast linje i md og json | R10 | PASS (L2) |
| 21 | NOV14 afsnit 6: vindue [d+1 00:00, d+4 00:00) | Halvåbent vindue. Et snapshot præcis på t0 tæller med, et på t1 tæller ikke. Snapshots efter vinduet (×5-rate) bruges ikke. Timer uden snapshot rapporteres | R11, `HFC1.test_values_both_sizes_and_post_window_snapshots_excluded` | PASS |

## 2. Håndregnet eksempel (R08)

Medlem PASSA har rate f = 2⁻¹⁰ = 0,0009765625 i alle 72 snapshots. Tallet er valgt, så alle beregninger går op uden
afrunding.
- Realiseret APR = f × 1.095 = 1,0693359375, altså 106,9 %.
- Ved N = 1.000 er omkostningen 8,7890625:
  - realiseret funding = f × 9 × 1.000 = 8,7890625, præcis lig omkostningen;
  - dækket ex post = True (≥), dækningsgrad 1,0, netto 0, netto på allokeret 0;
  - break-even-APR = 8,7890625 / (1.000 × 3/365) = 1,0693359375, lig den realiserede APR, som det skal være.
- Ved N = 5.000 er omkostningen 60:
  - realiseret = 43,9453125 og netto = −16,0546875;
  - netto på allokeret = −16,0546875 / 10.000 = −0,16 %;
  - break-even-APR = 60 / (5.000 × 3/365) = 1,46, og dækningsgrad = 0,732.
- Negativ funding (PASSB, −0,0001) bliver betalt og regnes med. Realiseret er −0,9, og netto ved omkostning 20 er −20,9.

C0 ved N = 1.000 har fire medlemmer med kendt omkostning. Ét af dem er dækket (PASSA). Det giver andel 1/4 af de kendte
og 1/11 med den strenge nævner. Dækningsgraderne er −0,045, 0,27 og 1,0 med median 0,27. Den afnoterede har ingen
dækningsgrad. Netto har median −7,3, minimum −20,9 og maksimum 0 (R09).

## 3. Fund (fejlende tests, `expectedFailure`) og foreslået patch

Patchen nedenfor er prøvet i en kopi af træet i scratch, ikke i repoet. Med den passerer alle 66 tests:
`test_research_hfc1_readiness` uden de fem markører plus de eksisterende 34 i `test_research_milestone_reports`. Når
patchen anvendes, **skal** de fem `@unittest.expectedFailure` fjernes. Ellers giver de "unexpected success", og under
Python 3.13 fejler kørslen så.

| Id | Alvor | Fund | Test |
|---|---|---|---|
| **B1** | Middel-lav (mærkning) | `perp_trading_at_end` læses fra census' `coin_perps`. Det sæt indeholder kun COIN-underliggende TRADING-perps (`lab/scanner._perps`: `underlyingType == "COIN"`, `lab/census.py` 28a). De tokeniserede aktie- og ETF-perps er ikke med, fx AMD, BABA, COIN, CRCL, DELL og EWJ, som udgør en stor del af 11-04-kohortens 117 uden spotpar. De bliver aldrig i sættet og får derfor status "observeret; perp ikke TRADING ved vinduets slut", og `perp_not_trading_at_end` tæller dem med. Det er usandt. Tal for dækning, manglende og netto påvirkes ikke, og md-filen viser ikke feltet | `Findings.test_B1_non_coin_perp_not_labelled_not_trading` (kontrol: `test_B1_control_coin_perp_that_leaves_is_flagged`) |
| **B2** | Lav (procesfælde) | `result_sha256` dækker også `offdb_proposal.already_present` og NOT_DUE-statusser for andre kohorter. (a) Proceduren siger: "Posten tilføjes i hånden ved commit af rapporten". Efter det giver en genkørsel et andet hash og dermed exit 3 EXISTS, et integritetsalarm uden dataændring. (b) Ved standardkørsel uden `--cohort` ændres hashet, når kohortefilen for 11-07 lander. Den skrives selv ≥ 00:35 UTC 11-08. Så fejler en genkørsel samme dag med EXISTS | `test_B2_rerun_after_offdb_entry_added_is_not_an_integrity_failure`, `test_B2b_default_invocation_hash_depends_on_not_due_cohort_files` |
| **B3** | Lav (nedbrud) | `write_outputs` skriver json, derefter md, uden atomisk omdøbning eller fsync. Værten har haft 5 urene stop på 9 dage. Hvis maskinen går ned mellem de to skrivninger, ser næste kørsel samme hash, regner det for idempotent og returnerer succes (exit 0) uden md. En tom json efter et nedbrud er korrekt fail-closed (EXISTS, R15) | `test_B3_idempotent_rerun_does_not_leave_the_md_missing` |
| **B4** | Lav (status) | `--cohort 2026-11-04` efter fristen, men uden kohortefil, giver `{"status": "NOT_DUE"}` med exit 2. Kun detaljen siger `NO_COHORT_FILE`. Operatøren kan tro, at der skal ventes. Ifølge docstringens egen inddeling ("3 integrity failure … missing DB") burde det være exit 3 | `test_B4_due_cohort_without_file_is_not_reported_as_not_due` |

Foreslået patch, prøvet som beskrevet ovenfor. Den anvendes fra `/home/anton/copybot-dev/copybot` med `patch -p1`. Git-
roden ligger én mappe højere, så med git hedder det `git apply --directory=copybot`.

```diff
--- a/research/tools/hfc1_report3d.py
+++ b/research/tools/hfc1_report3d.py
@@ -131,12 +131,14 @@
     days, k = H[horizon]
     expect = days * 24                                   # hourly census snapshots (hfc1_daily.outcomes)
     last = snaps[-1] if snaps else None
+    coin = set().union(*(x[2] for x in snaps)) if snaps else set()     # census coin_perps: COIN-underlying only
     out = []
     for r in body["rows"]:
         sym = r["symbol"]
         v = [s[1][sym] for s in snaps if sym in s[1]]
         present_last = bool(last and sym in last[1])
-        trading_last = bool(last and sym in last[2])
+        # None: never in census coin_perps in the window (e.g. a tokenised stock perp); TRADING status unknown
+        trading_last = bool(last and sym in last[2]) if sym in coin else None
         reasons = []
         if not v:
             reasons.append("ingen observationer i vinduet")
@@ -152,8 +154,9 @@
              "missing_75pct_rule_only": len(v) < (1 - MISSING_FRAC) * expect,
              "realised_f8h": None if missing else st.fmean(v),
              "partial_f8h_not_used": st.fmean(v) if (missing and v) else None,
-             "status": ("manglende" if missing else "observeret") + ("" if trading_last or not present_last
-                                                                     else "; perp ikke TRADING ved vinduets slut")}
+             "status": ("manglende" if missing else "observeret") + (
+                 "; perp ikke TRADING ved vinduets slut" if trading_last is False and present_last else
+                 "; perp-status ukendt (ikke i census coin_perps)" if trading_last is None and present_last else "")}
         m["realised_apr"] = None if missing else m["realised_f8h"] * 1095
         for n in SIZES:
             N = float(n)
@@ -197,7 +200,9 @@
                                                                                 for m in ms),
          "dropouts": sum(1 for m in ms if m["drop"]), "observed": sum(not m["missing"] for m in ms),
          "absent_in_last_snapshot": sum(not m["present_in_last_snapshot"] for m in ms),
-         "perp_not_trading_at_end": sum(m["present_in_last_snapshot"] and not m["perp_trading_at_end"] for m in ms),
+         "perp_not_trading_at_end": sum(m["present_in_last_snapshot"] and m["perp_trading_at_end"] is False
+                                        for m in ms),
+         "perp_status_unknown_not_coin_perp": sum(m["perp_trading_at_end"] is None for m in ms),
          "obs_coverage": _q([m["obs_coverage"] for m in ms]), "realised_apr": _q([m["realised_apr"] for m in ms])}
     for n in SIZES:
         d = [m[f"N{n}"] for m in ms]
@@ -348,6 +353,9 @@
         status, reports = build(con, cohort_dir, days, horizon, now, pins)
     finally:
         con.close()
+    if any(s["status"] == "NO_COHORT_FILE" and now >= window(dt.date.fromisoformat(d), horizon)[2]
+           for d, s in status.items()):
+        raise Refused("NO_COHORT_FILE", 3, json.dumps(status, sort_keys=True))    # due but no file: integrity
     if not reports:
         raise Refused("NOT_DUE", 2, json.dumps(status, sort_keys=True))
     cohorts = [r["cohort"] for r in reports]
@@ -357,7 +365,9 @@
               "sizes_usdt_per_leg": [int(n) for n in SIZES], "fixed_lines": list(FIXED_LINES),
               "research_status": "INCONCLUSIVE (beskrivende; ingen test; afgør intet)",
               "offdb_proposal": offdb_proposal(cohorts, horizon, files)}
-    rsha = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
+    hashed = {**result, "cohort_status": {k: v for k, v in status.items() if v["status"] == "REPORTED"},
+              "offdb_proposal": {k: v for k, v in result["offdb_proposal"].items() if k != "already_present"}}
+    rsha = hashlib.sha256(json.dumps(hashed, sort_keys=True).encode()).hexdigest()   # only what the data decide
     rep = {**result, "result_sha256": rsha, "run_utc": utc(now), "db_uri": ro_uri(db), "dry_run": dry_run}
     raw = json.dumps(rep, sort_keys=True, indent=1, ensure_ascii=False).encode()
     text = md(rep)
@@ -374,13 +384,23 @@
                 same = json.loads(f.read()).get("result_sha256") == json.loads(raw)["result_sha256"]
         except (OSError, ValueError):
             same = False
-        if same:
+        if same and os.path.exists(mp):
             return                                       # idempotent: the same result is already on disk
+        if same:                                         # a crash after the .json: complete the pair
+            _atomic(mp, text.encode("utf-8"))
+            return
         raise Refused("EXISTS", 3, f"{jp} exists with a different result; not overwritten")
-    with open(jp, "wb") as f:
-        f.write(raw)
-    with open(mp, "w", encoding="utf-8") as f:
-        f.write(text)
+    _atomic(mp, text.encode("utf-8"))                    # .md first: a lone .md is refused (EXISTS), never trusted
+    _atomic(jp, raw)
+
+
+def _atomic(path, data):
+    tmp = path + ".tmp"
+    with open(tmp, "wb") as f:
+        f.write(data)
+        f.flush()
+        os.fsync(f.fileno())
+    os.replace(tmp, path)
 
 
 # ---- synthetic data (--dry-run and tests only) ---------------------------------------------------------------------
```

Noter til patchen:
- B2 ændrer definitionen af `result_sha256`. Hashet dækker nu kun de rapporterede kohorter og forslaget uden
  `already_present`. Ingen rapport er skrevet endnu, så ingen gemt hash bliver ugyldig.
- R14 accepterer begge definitioner. `MILESTONE_REPORT_TOOLS.md`'s sætning "dækker hele resultatet uden kørselstidspunkt
  og databasesti" bør så suppleres med "… og uden andre kohorters NOT_DUE-status og offdb-tilstand".
- Med B1-patchen viser en tokeniseret aktie-perp `perp_trading_at_end: null` og "perp-status ukendt". En COIN-perp, der
  forlader sættet i vinduet, mærkes stadig.

## 4. Kørselsprocedure 2026-11-08

Kør fra **dev-worktree `/home/anton/copybot-dev/copybot`**. Værktøjet og kohortefilerne 11-04 og 11-05 ligger kun dér.
Produktions-checkoutet `/home/anton/ecommerence/copybot` har hverken værktøjet eller 11-05-filen. Databasen er
produktionens lab.db (standard `--db`), og den åbnes read-only.

**Forudsætninger (alle skal holde, ellers stop):**

```
date -u                                    # FØRST. Skal være >= 2026-11-08 00:35:00 UTC (vinduesslut 00:00:00 + 35 min)
cd /home/anton/copybot-dev/copybot
git status --short research/data/hfc1 research/tools/hfc1_report3d.py research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md
sha256sum research/data/hfc1/2026-11-04.json      # a5f831c40c19eb1e… (protokollens fastlåste præfiks a5f831c40c19)
sha256sum research/tools/hfc1_report3d.py         # 33e9b908… (uændret), eller patchens hash, hvis den er committed
head -c 3178 research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md | sha256sum   # cd1b6fc66000544f…
python3 -m unittest tests.test_research_hfc1_readiness tests.test_research_milestone_reports   # OK
ls research/data/hfc1_report3d/ 2>/dev/null        # må ikke allerede indeholde hfc1_3d_2026-11-04.*
```

- Kohortefilen må ikke være 0 bytes eller ændret. Se `crash-zero-length-files`: tjek `git status`, og gendan kun fra
  git, hvis git viser den ændret.
- Hele protokolfilens hash (`0c2835…` i NOV14_READINESS) ændrer sig med vilje, når kohorte 11-06 og 11-07 tilføjes.
  Brug regeldelens hash i stedet (L7).

**Kørsel (én gang):**

```
python3 research/tools/hfc1_report3d.py --cohort 2026-11-04       # eksplicit kohorte (undgår B2b)
echo "exit=$?"
```

**Udfald:**
- **exit 0, `REPORTED`:** kontrollér outputtet:
  - `research/data/hfc1_report3d/hfc1_3d_2026-11-04.json` **og** `.md` findes begge (B3);
  - `census_snapshots_in_window` (forventet 72), `census_hours_missing` og `last_snapshot_utc` (forventet
    2026-11-07 23:0x UTC);
  - C0 = 120, C0+ = 72, `frafald F1 intet spotpar` = 117, `frafald F1 multiplikator` = 1, `bestod_F1-F5_N1000` = 2;
  - `research_status` er INCONCLUSIVE, og `offdb_proposal.written` er false.
  - Commit rapportfilerne. Tilføj derefter `offdb_proposal.entry` i hånden til
    `research/data/factory/offdb_studies.json`. **Kør ikke værktøjet igen mod samme `--out` bagefter**, så længe B2 ikke
    er patchet: det giver exit 3 EXISTS uden dataændring.
- **exit 2, `NOT_DUE`:** det er for tidligt, eller kohortefilen mangler. Læs `detail`:
  - `NOT_DUE` med `due_utc`: vent til den tid, og kør igen. Ingen omgåelse; der er intet `--now`, og uret må ikke
    ændres. Intet er skrevet.
  - `NO_COHORT_FILE` i detail (B4): **vent ikke**. Kohortefilen mangler. Stop og tjek `research/data/hfc1/`.
- **exit 3:**
  - `COHORT_HASH_MISMATCH`: filen er ændret. Stop, tjek `git diff`, og kør ikke på en ændret fil.
  - `NO_DB`: tjek stien.
  - `EXISTS`: slet intet. Sammenlign det eksisterende `result_sha256`, og spørg før nogen handling.
  - `COHORT_INCOMPLETE`/`WORDING`: stop og rapportér.
- **Kohorte 11-05:** `python3 research/tools/hfc1_report3d.py --cohort 2026-11-05` tidligst **2026-11-09 00:35:00 UTC**.
  Det giver sin egen fil `hfc1_3d_2026-11-05.*`. Kør ikke 11-04 og 11-05 sammen, for det giver en tredje fil med begge
  kohorter i navnet.
- 14 d-horisonten for 11-04 åbner tidligst 2026-11-19 00:35 UTC (`--horizon 14d`).

**Læsning af JSON uden B1-patch:** for medlemmer uden spotpar betyder `perp_trading_at_end: false` og statussuffikset
"perp ikke TRADING ved vinduets slut" kun "ikke i census' COIN-sæt". Tal det ikke som afnotering. Afnotering står som
`missing` / `present_in_last_snapshot: false`.

## 5. Begrænsninger (dokumenteret, ikke skjult)

- **L1 Exit-omkostning:** omkostningen er bogens gennemgang ved kohortedannelsen: én bogaflæsning, ind og ud på samme
  bog, plus taker 0,001 og tillæg 0,0002 pr. side. En realiseret exit-bog er ikke observeret, for der er intet netværk,
  og HFC-1 handler ikke (MRT-3). Omkostningen kan være både større og mindre ved et rigtigt exit. Den står som fast
  linje.
- **L2 8 t-interval:** realiseret funding = middel af lastFundingRate × 9. Perps med 4 t- eller 1 t-interval
  undervurderes. Intervallerne er ikke undersøgt. Tokeniserede aktie-perps kan have andre intervaller (UNKNOWN). Det
  står som fast linje.
- **L3 "Realiseret funding" er protokollens mål:** middel af timeaflæsninger af census' `lastFundingRate`, ikke de
  afregnede fundingbetalinger (ingen fundinghistorik, ingen netværk). Aflæsningen er tidsvægtet og kan halte op til én
  periode efter afregningen.
- **L4 Netto er beskrevet, ikke opnået:** spot-perp-basis, prisbevægelse, margin, rebalancering og gearing indgår ikke.
  Allokeret kapital = 2N ved 1x (MRT-5). "1.000 og 5.000" er pr. ben (protokol F4), dvs. 2.000 / 10.000 allokeret.
- **L5 WAL-sidefiler:** på produktionen holder samleren lab.db åben i WAL. Read-only-åbningen ændrer hverken db eller
  -wal (R16b). Er databasen i WAL uden en åben skriver og uden sidefiler, opretter SQLite 3.46 selv -wal/-shm ved en
  `mode=ro`-åbning. Hovedfilen er uændret (R16c, observeret i scratch). Det gælder også `hfc1_daily.py` og alle andre
  ro-værktøjer. Det løses kun med `immutable=1`, som er usikkert med en aktiv skriver og derfor ikke foreslås.
- **L6 Observationer tælles pr. snapshot, ikke pr. time:** `census.observe` gemmer højst ét snapshot pr. time og tjekker
  registret efter en genstart. To snapshots i samme time ville løfte `n_obs` og vægte middelværdien. Timerne
  rapporteres separat (`census_hours_covered`).
- **L7 Protokolhash:** NOV14_READINESS fastlåser hele filen (`0c2835…`, `368eaec`). Filen får tilføjet et
  kohorteafsnit hver dag, så den hash ændrer sig med vilje. De uændrede regler er de første 3.178 bytes, og de er
  byte-identiske med filen i `48a0a63` (sha256 `cd1b6fc66000544f6e58a5e202f4c3f0c2d10913c3882f3eda6b8d06cdfe53c6`).
  Testen og proceduren bruger den.
- **L8 Fastlåste kohorte-hashes:** værktøjet har kun 11-04 og 11-05. Senere kohorter rapporteres med
  `cohort_file_pinned_in_protocol: false`, indtil `PINNED` udvides.
- **L9 Ikke kørt mod den rigtige lab.db (regel):** kompatibiliteten med census' payload er vist mod skriveformatet i
  `lab/census.py` (floats, null, `coin_perps`), mod `hfc1_daily.snapshots` (samme parsing) og mod de rigtige
  kohortefiler (R18). Første rigtige kørsel er 11-08.
- **L10 md-filen** viser ikke `absent_in_last_snapshot` / `perp_not_trading_at_end`. De står i JSON-filen.
  Manglende medlemmer står med grunde i md-filen.

## 6. Hvad der ikke er gjort

- Værktøjet er ikke ændret. Patchen er et forslag til koordinatoren.
- Der er intet commit.
- Den rigtige lab.db er ikke åbnet, og der er intet netværk og ingen pm_lp.
- Ingen kørsel efter fristen er forsøgt, og ingen NOT_DUE er omgået.
