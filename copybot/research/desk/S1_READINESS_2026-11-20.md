# S1_READINESS_2026-11-20: S1-evalueringen 20/11 (direktørordre 61, readiness)

**Status:** READY, men det forventede udfald er **INSUFFICIENT_OBSERVATION**. Der er ingen blokering for kørslen. Der
er én uafklaret tolkning (punkt 7). Ingen lås, ingen S2.
**Skrevet:** 2026-11-09 ca. 12:20 UTC (tjekket med `date -u`). lab.db er ikke åbnet, `python3 -m lab` er ikke kørt,
der er ikke lavet nogen netværkskald, og S1's filer er kun læst.

## 1. Hvad 20/11 afgør

- Ordre 49 P3 (INBOX linje 459-461) beder om en S1-evaluering. Den sammenligner fabrikkens ALLOW/BLOCK med lab'ens
  beslutning for hver ny overgang efter baselinen (179). Rapporten skal dække beslutninger, årsagskoder, uforklarede
  forskelle, falske blokeringer, legacy-kompatibilitet, ressourcer, fejl, integritet og testdækning og ende med en
  anbefaling. "Nul fejl er ikke automatisk GO uden relevante hændelser."
- Kriteriet for at gå videre (FACTORY_MIGRATION_P1 linje 55): 14 dage i S1 uden uforklarede BLOCK, uden fejl i gaten og
  uden forskelle uden for en dokumenteret klasse. Kriteriet for tilbagerulning: den første uforklarede BLOCK af en
  eksisterende proces, enhver fejl i gaten eller enhver påvirkning af papirhandlen (FACTORY_INTEGRATION_P3 §5).
- **Evalueringen afgør ikke S2.** S2 kræver en ny, eksplicit ejerbeslutning (D10, G26_S2_S3). Claude aktiverer aldrig
  S2. Også et positivt S1-udfald giver kun en anbefaling.

## 2. Gates ("S1-vurdering kun ved opfyldte gates")

| Gate | Krav | Status 09/11 |
|---|---|---|
| `G24_S1_EVAL` (date) | `date -u` ≥ **2026-11-20T09:55:07Z** (14 fulde døgn fra den faktiske start 2026-11-06 09:55:07 UTC). Ingen `required_flags` | NOT_DUE |
| `G29_LABDB_RO` | lab.db åbnes kun som `mode=ro` + `query_only` (det gør `factory_s1.open_ro`) | opfyldt (kode) |
| `G05_OWN_FORWARD_OBS` | egne overgange læses kun til drift og kvalitet | opfyldt |
| `G26_S2_S3`, `G12_PMLP`, `G27_NO_REAL_MONEY` | ingen S2/S3, pm_lp urørt, ingen rigtige penge | lukket (skal forblive lukket) |

Evalueringen kræver ingen ejergodkendelse (godkendt af direktøren i ordre 48/49) og ingen vært. Pins og kæde skal
være intakte (punkt 5). Er en pin brudt, stoppes der og rapporteres. Der evalueres ikke.

## 3. Udfaldsklasser (kun fra protokollen)

| Klasse | Hvornår | Kilde |
|---|---|---|
| NOT_DUE | før 2026-11-20 09:55:07 UTC | G24 |
| **INSUFFICIENT_OBSERVATION** | 0 (eller "få") nye overgange. Aldrig PASS. Gatens reaktion på nye hændelser er ikke observeret | svar på ordre 49 P0 (INBOX 427), summary.md |
| Kriterium brudt → tilbagerulning anbefales | ≥ 1 `UNEXPLAINED`, kædebrud, fejl i gaten eller påvirkning af papirhandlen | MIGRATION_P1 linje 55-57 |
| Kriterium opfyldt (kun anbefaling) | nok nye overgange, 0 uforklarede, 0 gatefejl, alle BLOCK i dokumenterede klasser | MIGRATION_P1 linje 55 |

- En BLOCK i en dokumenteret klasse (fx `no-charge`, `hash-at-access`) er en forklaret forskel. Den er ikke et brud.
- "Falske blokeringer" kræver, at hver BLOCK gennemgås manuelt. Ved 0 nye overgange er der ingen at gennemgå.

## 4. MONITORING_GAP

| Fra (UTC) | Til (UTC) | Timer | Registreret |
|---|---|---|---|
| 2026-11-07 00:19 | 2026-11-07 19:31 | 19,2 | MISSION27_4 linje 352, direktørtillæg 59 ("S1-hullet registreret") |
| 2026-11-09 07:09 | 2026-11-09 10:08 | 2,99 | **nyt**: kun i summary.md, endnu ikke nævnt i INBOX eller readiness |

Behandling efter svaret på ordre 49 P0 (INBOX 424-428):

- Enhver periode på over 2 timer uden kørsel er et MONITORING_GAP (`GAP_S` = 2 t). Hullerne rapporteres.
- Ved genstart læses alle nye overgange siden det senest behandlede id. Intet går tabt. Dry-run B viser det: en overgang
  i et hul på 20 timer blev registreret ved den første kørsel efter hullet.
- Hændelsesdækning og tidsdækning rapporteres hver for sig. Hullerne forlænger ikke perioden og ugyldiggør den ikke.
  Observationstiden ændres ikke.
- Begrænsning: fabrikken beregner beslutningen ud fra databasens tilstand på kørselstidspunktet (fx om der findes
  `trials` til `no-charge`). En sen kørsel kan derfor se senere evidens. Det har ingen betydning ved 0 nye overgange.
  Hvis der kommer overgange i et hul, skal rapporten nævne det.

## 5. Forudsætninger, verificeret 2026-11-09 ca. 12:15 UTC

| Fil | sha256 nu | Pin / commit | OK |
|---|---|---|---|
| `research/tools/factory_s1.py` | `e18278f4827dd2d0288bba2c39243d99e6aa29114f57930fc2fc5e8a0cb20f5d` | S1_TOOL i NOV14_READINESS, `003a8a2` | ja |
| `research/studies/FACTORY_S1_P0_2026-11-06.md` | `0bd0f5db7ffb8e082fd7b08615100bbb165ed1b68dd2c37ee8f181e676a08af1` | S1_P0, `7a395e3` | ja |
| `research/tools/factory_shadow.py` (beslutningslogik) | `363e102fd2b3278d352735cc77752c554bc0d80ce86124d21cc329c8d2c591ac` | `70856c5` (2026-11-06 08:13 UTC, før start) | ja, ingen ændring siden start |
| `research/tools/factory.py` | `3d07716e87776a1eec5cb8585628f165bf78e7058951a858016d18e43b47426c` | `70856c5` | ja |
| `research/tools/hypo_engine.py` | `9f8446a3e68f15c21b148ad1d388d03d53ed92141e2934b76fc0662eb5219d9a` | `70856c5` | ja |
| `research/desk/GATE_MATRIX.json` | `19b87e9af0cf3c979060ecd825282296a53747b806aeb0ab85bcce0b7e51da99` | `efca77d` | uændret af denne opgave |

- `003a8a2` (runs.jsonl og dækning) blev committet 2026-11-06 10:23 UTC, 28 minutter efter start. Beslutningerne blev
  ikke ændret. Direktøren accepterede det (INBOX 435).
- **Kæde:** 179 poster (alle BASELINE), `verify_chain` er OK, og hovedet `e1da0cd60c49…` er lig med `state.chain_head`.
  Der er ingen `errors.jsonl` og ingen `STOP`.
- **Dækning (beregnet med `factory_s1.coverage` fra egne filer):** 63 gennemførte kørsler af 75 timeslots, 0 fejlede,
  længste hul 19,20 t, 2 MONITORING_GAP, **0 nye overgange**. Ved 20/11 09:55 er der 337 forventede timeslots.
- Øjebliksbillede af S1's filer (de ændres hver time): decisions.jsonl `4ba8c5ce…`, runs.jsonl `f1d560e2…`,
  state.json `fd16c794…`, summary.md `5d7f4975…`.
- **Tests:** `python3 -m unittest tests.test_research_factory_s1 tests.test_research_factory_shadow
  tests.test_research_gate_status` → 32 tests OK. Ingen test er ændret. pytest findes ikke på værten.

## 6. Procedure 20/11 (der findes intet evalueringsværktøj)

`factory_s1.py` kører kun S1 og skriver summary.md. Det evaluerer ikke. Proceduren nedenfor følger G24
`actions_at_opening` ("one S1 run, then the evaluation report") og rapportskabelonen i NOV14_READINESS §9.

1. `date -u` ≥ 2026-11-20 09:55:07 UTC. Ellers stop (NOT_DUE).
2. Kontrollér sha256 for de seks filer i punkt 5. Kontrollér, at der ikke findes en `research/data/factory_s1/STOP`.
3. Kør S1 én gang fra dev-worktreet:
   `python3 research/tools/factory_s1.py --db ~/ecommerence/copybot/data/lab/lab.db` → exit 0.
   **NB:** standardværdien for `--db` peger på worktreets egen, forældede `data/lab/lab.db` (fra 26/10). Angiv altid
   `--db`.
4. Læs kun S1's egne filer: `verify_chain(decisions.jsonl)` skal være lig med `state.chain_head`. Beregn
   `coverage(runs, started_ts, now)`. Tæl OBSERVATION-poster, `unexplained`, BLOCK pr. årsag og `errors.jsonl`.
   Kontrollér, at `last_transition_id` er lig med det højeste id i kæden.
5. Gennemgå hver BLOCK manuelt for falske blokeringer. Det gælder kun, hvis der er nogen.
6. Skriv rapporten efter skabelonen: kørsler forventet/gennemført, længste hul, MONITORING_GAP-perioder, nye overgange,
   ALLOW/BLOCK pr. årsag, uforklarede, falske blokeringer, legacy-kompatibilitet, ressourcer, fejl, kædeintegritet,
   tests, klasse (punkt 3) og anbefaling. Commit den. S2 nævnes kun som ejerens beslutning (D10).

**Synthetic dry-run (09/11, kun scratch):** Kørt på midlertidige databaser fra `tests.test_research_factory_shadow.
synthetic_lab` med `factory_s1.run(now=…)` for hver time i 14 døgn fra den rigtige start. lab.db er ikke brugt.

| Scenarie | Før cutoff | Klasse | Nøgletal |
|---|---|---|---|
| A: 0 nye, hul på 20 t | NOT_DUE | INSUFFICIENT_OBSERVATION | 317/337 kørsler, 1 hul |
| B: 3 forklarede nye, én i hullet | NOT_DUE | tælling, 0 uforklarede (se punkt 7) | ALLOW:propose 1, ALLOW:no-op 1, BLOCK:no-charge 1 |
| C: 1 uforklaret + 1 fejlkørsel | NOT_DUE | kriterium brudt | BLOCK:UNEXPLAINED 1, errors 1 |
| D: selve CLI'en med `--db`/`--dir` | – | INSUFFICIENT_OBSERVATION | exit 0 |

## 7. DNS, blokeringer og uafklarede punkter

- **DNS: ingen afhængighed.** S1 bruger ingen vært, kun den lokale lab.db (read-only). DNS-filtret
  (data.binance.vision, data-api.binance.vision, Polymarket) har ingen betydning for S1.
- **Blokeringer: ingen.** Kørslen 20/11 kræver kun, at timetjekket eller én manuel kørsel sker efter 09:55:07 UTC.
- **Forventet udfald:** INSUFFICIENT_OBSERVATION. Der har været 0 nye overgange på 3,1 døgn, så pipelinen laver ingen
  forskningsovergange lige nu.
- **Uafklaret 1 (direktøren bør afgøre det før 20/11):** "få nye overgange" er ikke kvantificeret nogen steder. Ved 0
  er klassen entydig. Ved 1-k overgange uden uforklarede rapporteres kun tallene, og direktøren afgør. Der opfindes ingen
  tærskel.
- **Uafklaret 2:** decisions.jsonl gemmer ikke overgangens lab-tid, kun `run_ts`. Evalueringskørslen kan derfor tage
  overgange med, der kom mellem 09:55:07 og kørslen. Kør så tæt på 09:55:07 som muligt, og angiv kørselstiden som
  periodens slut.
- **Risiko:** S1 kører kun, når assistentens timetjek kører. Hullet 09/11 07:09-10:08 viser, at det stadig sker.
