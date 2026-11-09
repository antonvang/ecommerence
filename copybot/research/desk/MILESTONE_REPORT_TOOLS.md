# Milepælsrapporter: HFC-1 08/11, STRAKS 12/11, PAR-BOG 19/11 (skrevet 2026-11-06 kl. 16:09 lokal, 15:09 UTC)

Lukker de tre værktøjshuller i `research/desk/NOV14_READINESS.md` afsnit 6-8 (AMB-21..25), som direktørordre 46 P2,
49 P2 og 52 P1 kræver. Tre nye read-only scripts og én testfil. Ingen eksisterende fil er ændret. Ingen af dem er kørt
mod lab.db for at få resultater. Før fristen svarer de NOT_DUE (exit 2) og åbner slet ikke databasen. Det er
kontrolleret 15:05 UTC: alle tre gav exit 2.

| Værktøj | Undersøgelse | Dataskæring (UTC) | Tidligste kørsel (UTC) | Output |
|---|---|---|---|---|
| `research/tools/hfc1_report3d.py` | HFC-1 3 d, kohorte 11-04 (11-05 åbner dagen efter) | vindue [2026-11-05 00:00, 2026-11-08 00:00) | **2026-11-08 00:35:00** (11-05: 11-09 00:35) | `research/data/hfc1_report3d/hfc1_3d_<kohorter>.{json,md}` |
| `research/tools/straks_report.py` | STRAKS-FØLG `LANE_35f39bb233`, STRAKS-MOD `LANE_a751c1f595` | **2026-11-12 17:01:51** (lane.started + 7 × 24 t) | 2026-11-12 17:11:51 | `research/data/straks_report/straks_7d_2026-11-12.{json,md}` |
| `research/tools/parbog_report.py` | PAR-BOG `LANE_68b8b6feb9` | **2026-11-19 20:41:09** (lane.started + 14 × 24 t) | 2026-11-19 20:51:09 | `research/data/parbog_report/parbog_2026-11-19.{json,md}` |

## Fælles regler (alle tre)

- **Kun læsning af databasen:** sqlite-URI `file:/home/anton/ecommerence/copybot/data/lab/lab.db?mode=ro` plus `PRAGMA
  query_only=ON`. `--db` findes kun til tests. Værktøjerne skriver aldrig til lab.db, og testene viser, at
  skriveforsøg fejler. Der er ingen SQL-skrivning uden for de syntetiske byggere; en statisk test håndhæver det.
- **Kun standardbiblioteket, intet netværk og aldrig pm_lp.** Ingen `urllib.request`, `socket` eller `http.client`.
  Testene erstatter socket. Ingen import af `lab/`, ingen nyhedstabel og ingen karantænefil.
- **Fail-closed tid:** før tidligste kørsel kommer status `NOT_DUE` med exit 2, og intet bliver skrevet. Uret er
  maskinens eget (`time.time()`); der findes ingen `--now`, så fristen kan ikke omgås. Rækker med `ts ≥ skæring`
  ignoreres (halvåbent vindue). Ti minutters margin (STRAKS/PAR) og 35 minutter (HFC-1) sikrer, at det gennemløb,
  der startede før skæringen, er færdigt med at skrive.
- **`--dry-run`** bygger en lille syntetisk database i en midlertidig mappe og kører på et simuleret ur efter
  fristen. Den rører aldrig lab.db. Filerne får præfikset `DRYRUN_` og `"dry_run": true`.
- **Deterministisk:** `result_sha256` dækker hele resultatet uden kørselstidspunkt og databasesti. To kørsler på
  samme data giver samme hash (testet). En eksisterende rapport med et andet resultat overskrives ikke (exit 3,
  `EXISTS`). Samme resultat er idempotent.
- **Integritet:** exit 3, hvis kontoens `lane.started` ikke er den fastlåste (ts, kilde, nøgle), hvis en kohortefil
  ikke matcher protokollens sha256-præfiks (`a5f831c40c19…` for 11-04, `b43afaf295c4…` for 11-05), eller hvis
  databasen mangler.
- **Ordvalg:** alle rapporter har de faste sætninger "beskrivende/diagnostisk; afgør intet; aldrig bevis". En
  selvkontrol nægter at skrive en markdown-tekst med ord som "profitabel", "lønsom", "anbefal" eller "bevist". Hver
  rapport har `research_status` = `INCONCLUSIVE (… ingen test; afgør intet)`. Det er ordre 49 P2's status pr.
  undersøgelse, og det er ikke PASS.

## 1. `hfc1_report3d.py` — HFC-1-udfald (protokol `research/studies/HFC1_HIGH_FUNDING_FEASIBILITY_2026-11-04.md`)

**Kilder:**
- Protokollen: "Kohorte og filtre", "Udfald" (linje 30-36), "Leverancer" og "Kendte begrænsninger".
- Ordre 46 P2: alle C0-kandidater, også uden spotpar; manglende data og frafald separat; ingen survivorship; ingen
  profitkonklusion.
- Ordre 46-svaret: både funding-break-even mod perp-notional og netto på samlet allokeret kapital.
- Ordre 49 P2 og 49 P1-svaret: "hvis vinduet faktisk er afsluttet"; fremtidige observationer rapporteres ikke som
  gennemførte.
- `GATE_MATRIX.json` G21.

**Vindue:**
- Kohorte d bruger census/1-snapshots med ts i [d+1 00:00, d+1+H 00:00) og H = 3 d. `--horizon 14d` følger samme
  regler; for kohorte 11-04 er tidligste kørsel 2026-11-19 00:35.
- Værktøjet beregner hver kohortes vinduesslut. Kun kohorter med `nu ≥ slut + 35 min` beregnes.
- Andre kohorter står som `NOT_DUE` uden tal. Er ingen forfalden, kommer exit 2.

**Pr. medlem:** alle rækker i kohortefilen indgår, også `F1 intet spotpar` og `F1 multiplikator`.
- Antal observationer af 72 og dækningsgrad.
- Med i vinduets sidste snapshot, og om perpen er TRADING ved slut. Survivorship: forsvundne mønter bliver med, med
  status.
- Manglende: ingen observationer, > 25 % huller eller fraværende i sidste snapshot. Grundene står på hver række.
- Realiseret funding = middel × 9 × N, både for N = 1.000 og N = 5.000.
- Omkostning fra kohortefilen og ex ante-dækning.
- Ex post-dækning: realiseret ≥ omkostning. Et manglende udfald med kendt omkostning er `False`, aldrig succes.
- Dækningsgrad, break-even-APR mod perp-notional = omkostning / (N × 3/365), netto = realiseret − omkostning, og
  netto på allokeret kapital = netto / (2N).

**Grupper:**
- C0 og C0+.
- `bestod_F1-F5_N<N>`: ikke frafaldet og bog/kapacitet ok ved N.
- `bestod_F1-F6_3d_N<N>`: også dækket ex ante.
- Ét frafaldstrin pr. gruppe: `frafald F1 intet spotpar`, `frafald F1 multiplikator`, F2/F3 og `frafald F4 N5000`.

**Opgørelse pr. gruppe og N:**
- Antal medlemmer, manglende (både den strenge og den rene 75 %-læsning), frafald og observeret.
- Omkostning kendt / ukendt. Ukendt er `n/a`, ikke "manglende".
- Dækket ex post både med kendte som nævner og med den strenge nævner (alle medlemmer, hvor ukendt aldrig er succes).
- Ex ante → ex post.
- Median, min og maks for dækningsgrad, break-even-APR, netto og netto på allokeret kapital.

**Plus:** census-snapshots i vinduet (forventet 72), timer uden snapshot, kohortefilens sha256 og
4 t-fundingbegrænsningen.

**offdb-listen:**
- `FACTORY_REGISTRY.md` linje 66 siger: "HFC-1's udfald fra 08/11 tilføjes til den tid". Ordre 49 nævner ikke
  offdb-listen; kravet står kun der.
- Værktøjet laver en **foreslået** post (`offdb_proposal`) med præcis de felter, de eksisterende poster i
  `research/data/factory/offdb_studies.json` har: id `HFC1_OUTCOME_3D_<kohorter>`, slægt
  `delta_neutral_funding_carry`, attempts 0, alpha 0,0, evidence og filer.
- Det angiver, om id'et allerede findes, og har `"written": false`. Filen skrives aldrig af værktøjet (testet med
  sha256). Posten tilføjes i hånden ved commit af rapporten.

**Kørsel 2026-11-08:**

```
date -u                                   # skal være ≥ 2026-11-08 00:35:00 UTC
python3 research/tools/hfc1_report3d.py   # alle gemte kohorter; 11-04 REPORTED, 11-05 NOT_DUE
python3 research/tools/hfc1_report3d.py --cohort 2026-11-05   # 2026-11-09 ≥ 00:35 UTC
```

## 2. `straks_report.py` — STRAKS 7 d (PROTOCOL_V3 ændring 41 linje 4309-4339, 41a linje 4341-4362, 41b linje 4445-4453)

**Kilder:**
- 41 punkt 7: antal handler, netto, opdelingen funding/gebyrer/bog/tillæg/prisbevægelse, FØLG mod MOD, pr.
  markedsklasse.
- 41a punkt 4: samme signaler, inkl. sprungne og afviste; pr. konto og klasse; største eksponering; markedets
  bevægelse adskilt fra det simulerede resultat.
- 41b punkt 2: med og uden `41b_timing`.
- Ordre 49 P2: efter omkostninger, timingafvigelser.
- `GATE_MATRIX.json` G22.

**Tider:**
- Start = `lane.started`-eventets ts 2026-11-05 17:01:51 UTC. Den er fastlåst i værktøjet og tjekkes for begge konti.
- Skæring = start + 7 × 24 t = **2026-11-12 17:01:51 UTC** (AMB-24, fail-closed).
- Signalerne afgrænses fra payloadens `t` (17:01:11), som `lab/straks.py` selv gør. Antallet af signaler i de 40 s
  mellem de to rapporteres (`signals_between_payload_t_and_event_ts`).

**Pr. konto, i to varianter (med og uden de tre 41b-signaler 58416, 58417 og 58591):**
- **Signaler:**
  - set: `opportunity.move` i [t, skæring);
  - handlet;
  - sprunget pr. årsag (`straks.skipped`, fx "åben position på markedet", "for gammel", "ingen retning");
  - afvist (`paper.refused`/`paper.signal_while_paused` eller ordre uden fyld);
  - uafklaret ("signal < 2 t før skæringen" eller "ingen ordre, ingen straks.skipped").
- **Handler:**
  - rundture og åbne ved skæringen;
  - brutto = prisbevægelse ved mid;
  - netto for lukkede handler = brutto − gebyrer − bog − tillæg + funding. Funding er afregnet mens positionen var
    åben. Hver handel krydstjekkes mod fyldprisernes P&L (`decomposition_failures`);
  - for åbne positioner: betalte omkostninger og funding.
- **Konto ved seneste timemærkning før skæringen** (samme konvention som `lane.decomposition`):
  - netto og netto på kapitalen;
  - funding, gebyrer, bog, tillæg og prisbevægelse;
  - største eksponering og største fald;
  - antal mærkninger, timer uden mærkning, og fyld efter mærkningen men før skæringen.
  - Netto uden 41b = kontonetto − de mærkede handlers netto.
- **Timing:**
  - indgang − signal (median, min, maks);
  - indgange før signalet, og dem af dem der *ikke* er blandt 41b-id'erne (en ny afvigelse ville stå her);
  - indgange senere end 2 t;
  - hold − 24 t, og udgange før 24 t.
- **Pr. klasse:**
  - lab'ets eget felt `class` (crypto/commodity/equity_etf/fx);
  - skabelonens krypto/metaller/energi/aktieindeks/FX.
- **Markedets 24 t-bevægelse efter signalet:** `opportunity.outcome.ret_24h_after`, med fortegn i kontoens retning.
  Den vises for alle signaler og for de handlede, adskilt fra det simulerede resultat.
- Stop før skæringen (`lane.retired`) vises.

**Kørsel 2026-11-12:**

```
date -u                                   # skal være ≥ 2026-11-12 17:11:51 UTC
python3 research/tools/straks_report.py
```

## 3. `parbog_report.py` — PAR-BOG diagnostisk (PROTOCOL_V3 ændring 43 linje 4423-4443, 43a linje 4455-4466)

**Kilder:**
- 43 punkt 7: pr. par antal handler, brutto, netto, gebyrer, bog, tillæg, funding og udgangsårsag
  (normal/stop/tid).
- 43a: fulde fyld; "ikke sendt: bog for tynd"; BLOCKED.
- ChatGPT 11-05: QQQ/SPY med nettoeksponering.
- `GATE_MATRIX.json` G23.

**Tider:** start 2026-11-05 20:41:09 UTC (fastlåst og tjekket). Skæring = start + 14 × 24 t = **2026-11-19
20:41:09 UTC** (AMB-25).

**Indhold:**
- **Handler:** indgange (`…|in|<par>|<time>|<ben>`) parres med næste udgang (`…|out|…`) for samme par.
- **Udgangsårsag:** læses af udgangsordrernes `signal_ref` `pairs.<normal|stop|tid>@<time>:z=<z>`, som `lab/pairs.py`
  skriver. En position, der er åben ved skæringen, får "åben ved skæring"; dens udgang efter skæringen ignoreres.
- **Opdelt samlet og pr. par efter årsag:**
  - handler, lukkede og åbne;
  - brutto og netto (lukkede);
  - gebyrer, bog, tillæg og funding på begge ben;
  - holdetid, z ved ind og ud;
  - nettonotional ved indgang;
  - delvist fyldte ben (43a).
- **Afvisninger i lab.db** pr. årsag.
- **Integritetsfund:** udgang uden indgang, ny indgang før udgang, ukendt ordre-id, par uden for 43 punkt 1, og
  'tid' før 72 t.
- **Kontoen ved seneste mærkning før skæringen**, som i STRAKS.

**Kørsel 2026-11-19:**

```
date -u                                   # skal være ≥ 2026-11-19 20:51:09 UTC
python3 research/tools/parbog_report.py
```

## Tvetydigheder og hvordan værktøjerne håndterer dem (fail-closed)

| Nr. | Hvad | Håndtering |
|---|---|---|
| AMB-21 | HFC-1 "evalueres først efter 14/11" mod milepælen 08/11 | Kun beskrivende opgørelse 08/11; fast sætning om, at der ingen evaluering, konklusion eller ny regel er før notatet efter 11-28; status INCONCLUSIVE |
| AMB-22 | Medlemmer uden spotpar har ingen omkostning | Realiseret funding (en ren perp-størrelse) beregnes for alle. Dækning og netto er `n/a` for frafald, aldrig "manglende". Manglende er kun dataudfald. Den strenge nævner (ukendt = ikke dækket) vises ved siden af nævneren "af kendte" |
| AMB-23 | N 1.000 og 5.000; C0, C0+, beståede | Begge størrelser og alle grupper, plus ét frafaldstrin pr. gruppe |
| AMB-24 | STRAKS "2026-11-12 (7 dage)" | 7 × 24 t fra lane.started 17:01:51; nægter før 17:11:51 |
| AMB-25 | PAR "2026-11-19 (diagnostisk)" | 14 × 24 t fra lane.started 20:41:09; nægter før 20:51:09 |
| MRT-1 | HFC "Mangler et medlem i senere snapshots" | Læses som fraværende i vinduets sidste snapshot, foruden > 25 %-reglen. Begge læsninger tælles (`missing`, `missing_75pct_rule_only`) |
| MRT-2 | "dem der bestod F1-F6" — F6 afhænger af horisont og størrelse | Både F1-F5 (bog og kapacitet ved N) og F1-F6 (dækket ex ante ved H og N). For 11-04 ved 3 d er F1-F6 tom (0 dækket ex ante), og den vises tom |
| MRT-3 | Ordre 49 P2 "realiserede omkostninger" | Der er ingen exit-bog, fordi HFC-1 ikke handler og værktøjet ikke bruger netværk. Omkostningen er kohortens bogaflæsning ind og ud på samme bog plus taker og tillæg, mærket som sådan. **Ikke implementeret: en realiseret exit-omkostning.** |
| MRT-4 | offdb "count then" (registret, HFC-1-posten) | Posten foreslås med attempts 0 og alpha 0, fordi protokollen kører "ingen statistisk test". Skal udfaldet tælle som forsøg, retter direktøren eller Claude forslaget i hånden. Værktøjet skriver aldrig listen |
| MRT-5 | Allokeret kapital | 2N ved 1x: spot N plus perp-collateral N (CARRY_REALISM præcisering 2). Gearing og margin regnes ikke |
| MRT-6 | lane.started-eventets ts mod payloadens t (40 s for STRAKS, 39 s for PAR) | Skæringen bruger eventets ts (NOV14 og GATE_MATRIX). Signalvinduet bruger t som lab'et. Antal i mellemrummet rapporteres |
| MRT-7 | Urealiseret P&L pr. position ved skæringen | Lab'et gemmer kun mærkning pr. konto (`sim_equity`), ikke pr. instrument. Åbne positioner viser betalte omkostninger og funding. Deres prisbevægelse findes kun i kontonettoen. Netto pr. klasse og pr. par dækker lukkede handler. **Ikke implementeret: urealiseret pr. position.** |
| MRT-8 | Ikke-sendte ordrer (STRAKS: ugyldig eller ikke hentet bog; PAR: "bog for tynd", BLOCKED, minimumsnotional) | `lab/straks.py` og `lab/pairs.py` gemmer dem kun i gennemløbets svar, ikke i lab.db. De rapporteres som UNKNOWN (`null`), aldrig som 0. STRAKS-signaler uden spor vises som "uafklaret". **Ikke implementeret: tælling af "ikke sendt: bog for tynd"** (kræver en lab-ændring, som ikke er i opgaven) |
| MRT-9 | Markedsklasse er ikke defineret i 41 | Lab'ets `class` og skabelonens fem klasser vises begge. Kobber tælles som metal; ukendt instrument tælles som "ukendt" |
| MRT-10 | Markedets bevægelse efter signalet | Kun `opportunity.outcome` med ts < skæring og `to_s` < skæring tæller. Fortegnet er kontoens retning. Den holdes adskilt fra resultatet |
| MRT-11 | Uden 41b på kontoniveau | Kontonetto − de mærkede handlers netto, men kun hvis alle tre var lukket ved seneste mærkning. Ellers UNKNOWN |
| MRT-12 | Udgangsårsag ulige på de to ben, eller ukendt | Vises som "uens: …" eller "ukendt (…)", aldrig som en af de tre |

## Tests (`tests/test_research_milestone_reports.py`, 36 tests, kun syntetiske databaser, socket patched)

- **HFC-1:**
  - vindue og frist (11-08 00:35);
  - NOT_DUE før vinduesslut uden output, også via CLI;
  - 11-04 REPORTED og 11-05 NOT_DUE i samme kørsel; 14 d NOT_DUE;
  - alle fem C0-medlemmer inkl. to uden spotpar og en multiplikator;
  - snapshots efter vinduet indgår ikke;
  - begge størrelser og regnestykkerne;
  - manglende og frafald hver for sig; manglende med omkostning er aldrig dækket;
  - snapshot-parsing svarer til `hfc1_daily.snapshots`;
  - fastlåste kohorte-hashes (også de rigtige filer);
  - read-only (sha256 uændret, ingen -wal/-shm/-journal, skriveforsøg fejler), deterministisk, offdb-listen uændret;
  - ingen overskrivning; dry-run.
- **STRAKS:**
  - tider og ledger-id'er (`lane.ledger_id`);
  - NOT_DUE;
  - skæringen udelukker fyld og signaler efter den;
  - FØLG ±60 brutto, og delene summerer;
  - med og uden 41b; en ny tidsafvigelse uden for 41b bliver fanget;
  - sprungne årsager og klasser; markedets bevægelse med kontoens fortegn;
  - forkert start giver exit 3;
  - `direction` er lig `lab.straks.direction`;
  - read-only og deterministisk;
  - **ende-til-ende med den rigtige lab-motor:** kontonetto og dele er lig `lane.decomposition`.
- **PAR:**
  - tider, ledger-id og parlisten er lig `lab/pairs.py`;
  - NOT_DUE;
  - opdeling på normal/stop/tid/åben;
  - skæringen;
  - delvist ben;
  - udgang uden indgang;
  - `signal_ref`-formatet;
  - read-only og deterministisk;
  - **ende-til-ende med `lab/pairs.py`:** en "normal"-udgang findes, og netto er lig `lane.decomposition`.
- **Fælles:**
  - NOT_DUE åbner ikke databasen;
  - en statisk scanning (ingen netværksmoduler, pm_lp, lab-import eller SQL-skrivning uden for de syntetiske byggere);
  - URI-formen er `file:/home/anton/…/lab.db?mode=ro`.

Kørt 2026-11-06 (UTC):
- `python3 -m unittest tests.test_research_milestone_reports`: 34 OK.
- `tests.test_research_gates tests.test_lab_safety`: OK.
- Alle `tests/test_research_*` plus `test_lab_safety`: 345 OK.
