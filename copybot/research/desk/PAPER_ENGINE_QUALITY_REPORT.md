# Papirmotorens kvalitet: revision (direktørordre 66, spor B)

Dato: 2026-11-09 (UTC). Gren `claude/66b-engine-audit` fra `cee7fca`, kun lokalt: ikke pushet, ikke deployet.
Omfang: `lab/paper.py`, `lab/paper_runner.py`, `lab/lane.py`, `lab/risk.py`, `lab/carry90.py`, `lab/reportcheck.py`,
`research/tools/net_report.py`. `lab/straks.py` og `lab/pairs.py` er kun læst; deres sha256 er uændret
(`7a110f1f…`, `5c9b60a4…`). Ingen protokol og ingen pin i `GATE_MATRIX.json` eller `NOV14_READINESS.md` er ændret.

Metode: kodelæsning, syntetiske tests i `tests/test_lab_engine_audit_66b.py` (midlertidige databaser, mocket
markedsdata, intet netværk) og skrivebeskyttede forespørgsler mod produktionens `lab.db` (`mode=ro`,
`PRAGMA query_only=ON`, kørt i `unshare -rn`). Kun optællinger, ingen rå rækker. Forespørgslerne er kørt ca. 14:20 UTC.

Statusord: **CONFIRMED** = fejlende syntetisk test (eventuelt også spor i den rigtige database). **SUSPECTED** =
set i koden, uden test. **CLEARED** = kontrolleret og fundet korrekt. Et `expectedFailure` dokumenterer en bekræftet fejl,
der ikke er rettet (STOP), og slår over i "unexpected success" den dag, den bliver rettet.

## Fund efter prioritet

| # | Fund | Alvor | Status (test) | Den rigtige DB | Rettelse |
|---|---|---|---|---|---|
| 1 | Bøgerne lane/carry90 kunne ikke mærkes i 34,7 t, og intet blev registreret (59-D-hændelsen) | uopdaget fejl: høj | CONFIRMED, rettet i dev af 59-D (`test_cleared_59d_lane_mark_failure_is_recorded`) | 9 aktive konti (6 lane, 3 carry90) uden mærke fra 06/11 20:00 til 08/11 06:42 UTC; 0 `paper.mark_failed` (59-D er ikke i produktion) | 59-D (`6304503`), ikke deployet |
| 2 | Mærkningen i `close_ledger` slugte fejl: en stoppet konto med et ben åbent kunne fryse sin værdi, uden at det blev registreret | uopdaget fejl: middel | CONFIRMED (`test_confirmed_fixed_closing_ledger_mark_failure_is_recorded`) | ingen direkte spor (lukkede konti blev flade straks) | **rettet**: `mark_guarded` + `note_marked` (kun registrering) |
| 3 | En manglende UTC-dag slås sammen til ét "dagligt" afkast i z-reglen (stop af typen 'edge' og 'promising', amendment 11) | forkert rapporteret resultat: lav-middel | CONFIRMED (`test_confirmed_stop_a_missing_utc_day_is_merged_into_one_daily_return`, xfail) | 9 aktive konti mangler 2026-11-07 (følge af fund 1) | **STOP**: ændrer en aktiv stopregel |
| 4 | Mærkefejl i STRAKS og PAR-BOG er tavse (samme mønster som før 59-D) | uopdaget fejl: middel | CONFIRMED (`test_confirmed_stop_straks_mark_failure_is_silent`, xfail; `pairs.py` er identisk) | 0 uforklarede huller i STRAKS-/PAR-mærker | **STOP**: filerne er frosne til 20/11 |
| 5 | `fetch_book` stempler bogen med passets `now`. Ordre, fyld og `book_ts` får derfor passets starttid, og 60-s-vagten (`data_max_age_s`) kan aldrig slå til | forkert tidsstempel; vagten virker ikke: lav-middel | CONFIRMED (`test_confirmed_stop_book_and_fill_times_are_the_pass_clock_not_the_read_time`, xfail) | 3908/3908 `sim_exec` med `book_age_s` = 0; ordrehændelsen (vægur) ligger 1–168 s efter ordretiden (p50 8, p99 52); 35 over 60 s; 1 krydsede en hel time, uden effekt på funding | **STOP**: en reel aldersvagt ville give nye pauser i aktive bøger |
| 6 | Funding går i stå i det stille, hvis 1 t-baren ved en afregning mangler, mens senere barer findes (`break`). Instrumentet bogfører intet, før baren falder ud af vinduet (1000 t Binance, 48 t HL) | forkert resultat: lav (latent) | CONFIRMED (`test_confirmed_stop_a_missing_middle_bar_stalls_funding_silently`, xfail) | 0 ud af 559 krydstjekkede afregninger mangler; 0 `paper.funding_gap` | **STOP**: prisreglen i amendment 9 afsnit 2 |
| 7 | `net_report.py` beholder den gamle basis ved et fortegnsskift: realiseret pris, antal lukkede og retning pr. instrument bliver forkerte | forkert rapporteret resultat: lav | CONFIRMED (`test_confirmed_stop_net_report_keeps_the_old_basis_through_a_flip`, xfail) | 2 fortegnsskift i alt, begge i FWD-konti, som net_report ikke medtager: 0 berørte tal i dag | **STOP**: filen er pinnet (`NET_REPORT e8cac57c`) |
| 8 | `reportcheck` tog "seneste" mærke og pausestatus efter `ts`, mens rapporten og `Risk.paused` bruger `id`: falsk REPORT MISMATCH | falsk alarm: lav | CONFIRMED (`test_confirmed_fixed_reportcheck_reads_latest_by_id_like_the_report`) | 0 rækker i `sim_equity`/`risk_events` med omvendt ts-rækkefølge; 17/17 verificerede rapporter ok | **rettet**: `ORDER BY id DESC` |
| 9 | `on_trade` kunne fylde en hvilende maker-ordre på et print, der var ældre end ordren (look-back) | forkert resultat: lav (koden kaldes ikke) | CONFIRMED (`test_confirmed_fixed_a_maker_order_cannot_fill_on_an_older_print`) | 0 maker-ordrer, 0 maker-fyld | **rettet**: print før ordren springes over |
| 10 | Mærkepriser pr. instrument gemmes ikke (`sim_equity` har kun equity/cash/exposure); urealiseret P&L for bøger med to ben kan ikke genberegnes fra databasen alene | proveniens: lav | SUSPECTED (skemaet) | – | anbefaling, ingen ændring |
| 11 | Dagsgrænsen: `net_report` læser `ts <= cutoff`, lane-rapporten og `reportcheck` læser `ts < dagens slut` | uoverensstemmelse: lav (latent) | SUSPECTED | 0 rækker præcis kl. 00:00:00 UTC | ingen (net_report er pinnet) |
| 12 | Funding-hentning i pause- og lukkevejen (`_funding_guarded`) står kun i passets returværdi; den indhenter sig selv ved næste pas | uopdaget forsinkelse: lav | SUSPECTED | 98 funding-rækker bogført > 2 t efter afregningen (maks. 6,4 t; 4 afregningstimer, 45 under nedetid); 0 mangler | ingen |

## Kontrolleret og fundet korrekt (CLEARED)

- **Hash-kæder** i `sim_orders` (5900), `sim_fills` (6424), `sim_cancels` (0), `sim_exec` (3908), `sim_equity` (8536),
  `sim_funding` (4568) og `risk_events` (5980): 0 brudte led. UNIQUE-indekserne findes; 0 dubletter af fill_id, order_id
  og funding-nøgle. Samtidige skrivere og en tabt kapløbskontrol på samme ordre-id giver ét fyld og intakte kæder
  (`test_cleared_a_lost_check_race_on_one_order_id_books_one_fill`, `test_cleared_interleaved_writers_keep_every_hash_chain`).
- **Gebyrer og glidning**: 0 negative gebyrer; 0 fyld hvor gebyret ≠ sats × px × qty; 0 taker-fyld med bogniveau på den
  forkerte side af mid. Alle 6424 fyld er taker.
- **Funding**: 0 rækker hvor beløbet ≠ −qty × pris × sats; 0 på en flad position; 0 hvor qty ≠ position før afregningen;
  0 før T_F; 0 bogført før afregningen. Krydstjek mod den uafhængigt indsamlede `funding_settled/1`: 559 holdte
  afregninger, 0 mangler, 0 med en anden sats. Test: `test_cleared_sign_flat_and_replay`.
- **Positioner og equity**: motoren nulstiller basis ved fortegnsskift og deler gebyret
  (`test_cleared_engine_flip_resets_basis_and_splits_the_fee`). Alle 8536 mærker: kontanter = genafspillet kapital +
  fyld − gebyrer + funding (0 afvigelser); toppen falder aldrig (0); drawdown = (top − equity)/top (0 afvigelser).
  `reconcile` er ok for alle 38 bøger. 0 støvpositioner.
- **Idempotens**: en ny kørsel i samme time laver ingen ekstra ordrer, fyld, mærker eller funding
  (`test_cleared_a_rerun_in_the_same_hour_duplicates_nothing`). 5 timer med to mærker: alle er det endelige mærke for en
  flad konto ved stop (det er designet sådan).
- **Look-ahead**: signaler bruger kun lukkede 1 t-barer (`close_time < now`). Funding bruger åbningen af baren, der starter
  ved afregningen. 0 fyld, hvor ordre-ts ≠ fyld-ts; 0 hvor `book_ts` ≠ fyld-ts.
- **Rapporter**: 17/17 `research.lane_report_verified` er ok. 0 par af PAUSE/CLEAR med omvendt ts-rækkefølge.

## `except Exception` i `lab/` (116 steder efter rettelsen; 117 før)

- **I papirvejen, tavse** (fejlen står kun i passets returværdi, intet i databasen): `straks.py:153` og `pairs.py:162`
  (mærke, fund 4); `paper_runner.py:256` (funding, fund 12); `paper_runner.py:602`, `lane.py:1182`,
  `straks.py:117/142` og `pairs.py:98/127` (ordre ikke sendt; næste pas prøver igen); `lane.py:557` (en læsefejl
  registreres som 11b "would hold nothing now"). `paper_runner.py:288` var tavs og er nu rettet (fund 2).
- **I papirvejen, registreret eller sikker**: `paper_runner.py:273/418/449/563/568`, `lane.py:479/912/1049/1147/1482`,
  `risk.py:250` og `paper.py:462` registreres som hændelse, pause, PROBE eller sim_exec-fejlrække.
  `lane.py:376/549/936/943` og `paper.py:468` er dokumenterede fallbacks eller ren diagnostik.
- **Uden for papirvejen**: mest registreret (observationer/hændelser/log) eller konservativt
  (`lifecycle`/`preflight`/`registry` svarer "ikke rent/ukendt"). Kandidater til tavs maskering, som bør ses efter
  (ikke ændret her): `web.py:221` (kædeverifikationen beholder i det stille sin gamle tilstand),
  `scanner.py:111/198`, `hypogen.py:588/595` ("ingen git: intet er låst"), `watch.py:265/380/717`.

## Rettelser på grenen (kun registrering eller rækkefølge; ingen eksisterende ledger-række ændres)

- `lab/paper_runner.py` `close_ledger`: mærkningen går gennem 59-D's `mark_guarded`, og det endelige mærke for en flad konto
  kalder `note_marked`. Ordrer, fyld, kontanter og mærker er de samme som før.
- `lab/reportcheck.py`: "seneste" mærke og PAUSE/CLEAR vælges efter `id` som i motoren. 0 rækker i den rigtige DB
  rammes, så tidligere udfald er uændrede.
- `lab/paper.py` `on_trade`: et print ældre end ordren fylder den ikke. Der findes ingen kalder i dag.

## STOP: til direktøren

1. Fund 3: z-reglen og en manglende dag (aktive lane-konti). Skal hullet udelades, eller skal et flerdagsafkast
   normaliseres? Det er en regelændring.
2. Fund 4: STRAKS og PAR-BOG får mærkeregistrering som 59-D, når filerne ikke længere er frosne (efter 20/11).
3. Fund 5: aldersvagten og tidsstemplerne. En vægur-tid på bogen giver nye pauser og andre ts i aktive bøger.
4. Fund 6: hvordan funding prises, når en bar mangler (amendment 9 afsnit 2).
5. Fund 7: en ny pin af `net_report.py` med basis nulstillet ved fortegnsskift (i dag 0 berørte tal).
6. Fund 10: gem mærkepriserne (nyt felt eller ny tabel). Det ændrer skemaet og hører derfor til en senere ordre.
