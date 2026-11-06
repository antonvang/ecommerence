# C1 — fremadrettet volatilitets-prognosejournal (direktørordre 51 P1)

**Status: DESIGN + KODE + SYNTETISKE TESTS. Ikke aktiveret.** C1 er infrastruktur, der fryser prognoser, før deres
måldøgn begynder. Den træffer ingen afgørelser. Strømmen står i `research/desk/stream_registry.json` som
`fwd_vol_forecast_register` (PROPOSED_NEEDS_SEPARATE_APPROVAL), og den status er uændret. Der er ikke skrevet en
eneste rigtig prognose. Laboratoriets egne observationer siden 2026-10-27 er kun læst til tællinger af dækning
(direktørens databeslutning, ordre 51). Der er ingen modeltilpasning, intet RV-niveau, intet tab og ingen
DM-statistik på rigtige data.

Filer:

- `research/tools/c1_forecast.py` (kun stdlib, intet netværk), konfiguration `DEFAULT_CONFIG`, sha256
  `8a6fb2c3a719e1727b45eb8355f42b94e27ee7c309c20a24361b8425956349b0`
- `tests/test_research_c1_forecast.py` (33 tests)
- `research/data/c1/coverage.json` og `coverage.md` (census/1, kun tællinger)

```
python3 research/tools/c1_forecast.py selftest
python3 research/tools/c1_forecast.py synthetic --out DIR [--seed N] [--eval-days N]
python3 research/tools/c1_forecast.py coverage [--db PATH] [--out research/data/c1]
python3 research/tools/c1_forecast.py verify JOURNAL
python3 -m unittest tests.test_research_c1_forecast
```

## 1. Formål

F2 (volatilitet og regime) spørger, om HAR-RV forudsiger næste døgns realiserede varians bedre end EWMA. Historiske
data kan besvare det med kalibrering fra 14/11 og et separat godkendt vindue. En fremadrettet måling kræver noget
andet: prognoser, der kan bevises at være lavet før udfaldet. C1 leverer den del. Hver prognose skrives i en
append-only, hash-kædet journal med sin input-identitet og sit oprettelsestidspunkt. Udfaldet ("reveal") kan først
hæftes på efter måldøgnet plus en afregningsfrist, og kun én gang. Evalueringen (QLIKE, Diebold-Mariano) nægter at
regne på andet end frosne og afslørede prognoser.

## 2. Data

Kilde: lab.db `observations`, detector `census/1`, metric `snapshot`. Én række pr. time med en kolonnevis payload
(`columns`, `rows[symbol]`). C1 bruger feltet `markPrice`. Rækkens `ts` (indsamlerens tid) placerer mærket i et
timeslot. `lastPrice` er kun talt med i dækningsrapporten til sammenligning.

Det skal siges ligeud, hvad census er og ikke er:

- **`markPrice` er ikke en handlet pris.** Binance udregner den ud fra et indeks over spotbørser plus en udglattet
  basis. Timeafkast af mark måler derfor mest det underliggende indeks og er glattere end handelspriser. F2 bruger
  1-times kline-lukkepriser fra historiske arkiver. **C1's RV er altså ikke F2's måling**, og den kan ikke erstatte
  F2-data.
- Snapshots tages ikke præcis på timen. Rækken lander 0-503 s efter timeslottet (median 34 s), så et "timeafkast"
  dækker 3600 ± ~500 s. Det er støj, ikke bias, men det står her.
- Det er punktprøver én gang i timen, ikke ægte højfrekvent RV. 23 afkast pr. døgn giver en støjfuld RV-estimator.
  Census' high/low er rullende 24 t og kan ikke bruges til range-estimatorer.
- `lastPrice` (handlet, fra ticker/24hr) findes kun for 801 af 941 symboler og mangler oftere. Den er ikke valgt.
- Afnoteringer kan ikke ses i census (FORWARD_DATA_PLAN fund 2). En afnoteret perp ville stå med uændret eller
  manglende mark. C1 udfylder ingenting, så en manglende mark giver et ufuldstændigt døgn.

Når C1 aktiveres, skal et marks informationstid være max(række-ts, `premium_time_ms`/1000). Forskellen er målt
til −93..+1 s og har ingen betydning ved oprettelse kl. ~23:30.

## 3. Definition af RV

- **Timeslot** h = [h, h+3600) UTC. Mærket for slot h er den første census-række med ts i slottet (samme regel som
  `census_check.py`). Prisen skal være endelig og > 0, ellers mangler slottet. Der udfyldes aldrig.
- **Døgn** D = [D, D+86400), UTC-døgnet (`day_offset_s` = 0). Døgnet er **komplet**, når alle 24 slotmærker
  (00:00..23:00) er der.
- **RV_D = Σ_{k=1..23} ln(P_k / P_{k−1})²**, altså de 23 timeafkast mellem døgnets 24 mærker. Et ufuldstændigt døgn
  har ingen RV. Den bliver ikke interpoleret eller skaleret.
- **Grænseafkastet** (23:00-mærket i D−1 → 00:00-mærket i D) indgår ikke i noget døgn. Det er en bevidst *embargo*.
  Med én prisserie deler to døgn, der ligger kant i kant, ellers et mærke. Så ville inputtets sidste mærke være
  måldøgnets første, og en prognose kunne ikke på én gang være oprettet efter sit input-cutoff og før sit måldøgn.
  Med embargoen er cutoff = 23:00-mærket (~23:00:34), prognosen oprettes ~23:30, og måldøgnet starter 00:00.
  Konsekvensen er 23 og ikke 24 afkast pr. døgn. Begge modeller forudsiger den samme 23-afkasts-RV, så
  sammenligningen er fair. Det er dog en målingsforskel fra F2 (pkt. 7).

## 4. Modeller (som ordren og F2)

- **HAR-RV(1,7,30)**: RV_{t+1} = b0 + b1·RV_t + b7·mean(RV_{t−6..t}) + b30·mean(RV_{t−29..t}) + e, OLS (normal
  ligninger, Gauss-Jordan med pivotering; skaleret med gennemsnittet af målet for numerikkens skyld).
  **Estimationsvindue: 365 regressionsrækker** (måldøgn i [L−364, L] for sidste inputdøgn L), som F2's "OLS på de
  foregående 365 dage (rullende, point-in-time)". En række kræver, at målet og alle 30 lagdøgn er komplette.
  `min_rows` = 365, altså intet hul i vinduet. Det kræver **395 sammenhængende komplette døgn** [L−394, L]. Prognosen
  for L+1 er b·(1, RV_L, mean7_L, mean30_L).
- **EWMA λ = 0,94** på samme RV-serie: s_first = RV_first, s_t = λ·s_{t−1} + (1−λ)·RV_t, prognose for L+1 = s_L.
  Rekursionen løber over det sammenhængende løb af komplette døgn, der ender i L. Et manglende døgn genstarter den
  (`gap_policy` = restart, ingen udfyldning), og løbet afkortes til højst 395 døgn (HAR's inputspænd). **Indkøring:**
  startværdiens vægt λ^(n−1) skal være ≤ 0,05, så n ≥ **50** komplette døgn (0,94^49 = 0,048; 0,94^48 = 0,051).
- En prognose ≤ 0 eller ikke-endelig afvises af journalen. HAR kan i princippet give et negativt tal. F2 siger ikke,
  hvad der så skal ske. C1 afviser og tæller, og afgørelsen hører hjemme i en låst protokol (pkt. 11).

## 5. Journal (JSONL, append-only, hash-kædet)

Hver linje er kanonisk JSON (sorterede nøgler, ingen NaN). `entry_hash` = sha256 af linjen uden `entry_hash`.
`prev_hash` = forrige linjes `entry_hash` (genesis: 64 nuller), og `seq` = linjenummer.

| type | felter |
|---|---|
| genesis (linje 0) | journal_version, config (fuld), config_sha256, created_ts, synthetic, activation_ref |
| forecast | model, model_version, config_sha256, symbol, horizon_days (1), input_first_day, input_last_day, input_cutoff_ts, input_sha256, coverage, created_ts (journalens ur), target_start, target_end, value, earliest_eval_ts = target_end + 3600 s, fit (koefficienter/rækker eller løbslængde/startvægt) |
| reveal | forecast_hash, symbol, model, target_start, target_end, status (ok/void), realized, realized_sha256, realized_coverage, revealed_ts, config_sha256 |

`input_sha256` er sha256 over de præcise mærker i inputspændet, i formatet
`c1-input/1|symbol|felt|first_day|last_day` og derefter én linje `slot,repr(ts),repr(pris)` pr. tilstedeværende
slot. `coverage` er andelen af de krævede timemærker (24 × døgn i spændet), der er til stede.

**Afvisningsregler (fail-closed, hver med test):**

1. `created_ts` er journalens eget ur, når posten tilføjes. Et medsendt `created_ts`, der afviger mere end 60 s,
   afvises (tilbagedatering eller fremdatering). Journalens tid må ikke gå baglæns.
2. `created_ts ≥ target_start` → afvist (oprettet i eller efter målvinduet).
3. `input_cutoff_ts > created_ts` → afvist. `input_cutoff_ts > target_start` → afvist. Inputdøgn, der overlapper
   målet, → afvist.
4. `coverage < min_coverage` (1,0) → afvist.
5. Værdi ikke endelig og > 0, ukendt model/version, målvindue ikke ét justeret døgn → afvist.
6. Samme (model, symbol, target_start) igen → afvist. En prognose udstedes aldrig igen.
7. Kæden verificeres helt ved hver læsning og hver tilføjelse: seq, prev_hash, entry_hash, feltmængde, genesis-config
   og -hash, monoton tid. Desuden kontrolleres alle regler igen, så en fil, der er omskrevet og hashet konsistent,
   stadig afvises, hvis den indeholder en lookahead-post. En ufærdig sidste linje afvises.
   `<journal>.head` (seq + hash) fanger en afkortet hale. Et eksternt anker (fx head-hash i en commit) anbefales,
   fordi head-filen kan omskrives sammen med journalen.
8. Klassen har kun `append_forecast`, `append_reveal` og `entries`. Der er intet redigér, slet eller omskriv, og
   filen åbnes kun i append-tilstand.
9. **Reveal:** kun når uret er ≥ `earliest_eval_ts`, kun én gang pr. prognose og kun for en prognose, der findes.
   `ok` kræver RV > 0 ved fuld dækning af måldøgnet. Ellers bliver det `void` (lukket, aldrig scoret).
10. En journal er syntetisk, medmindre den oprettes med `synthetic=False` **og** en `activation_ref`. Ingen
    CLI-kommando gør det. En syntetisk journal afviser ure før 2033 (den syntetiske epoke), og en rigtig journal
    afviser ure i den syntetiske epoke.

## 6. Evaluering

- **QLIKE(RV, F) = RV/F − ln(RV/F) − 1** (Patton 2011). RV > 0 og F > 0 kræves, ellers afvises parret.
- d_{i,t} = QLIKE(EWMA) − QLIKE(HAR) (F2's fortegn: d > 0 betyder, at HAR er bedre). dbar_t er det ligevægtede
  gennemsnit over symboler, hvor begge modeller er afsløret `ok` samme døgn.
- **DM:** t = mean(dbar) / sqrt(LRV/T), hvor LRV er Newey-West med Bartlett-vægte 1 − k/(L+1), **L = 5 faste lags**
  (F2) og autokovarianser divideret med T. Det er samme konvention som `hypo_engine.hac_t`, og en test viser
  identitet. p ensidet = 1 − Φ(t), H0 E[d] ≤ 0. Mindst 7 scorede døgn.
- `evaluate` afviser, hvis en forfalden prognose (earliest_eval_ts ≤ nu) mangler reveal, hvis en prognose ikke er
  oprettet før sit målvindue, hvis to reveals for samme symbol og døgn er uenige, og ved for få døgn. Void og
  uparrede prognoser tælles og scores aldrig.

**Syntetisk ende-til-ende** (seed 51, 4 symboler, HAR-genererede varianser med regimeskift, standardkonfiguration
med 365-vindue, 60 evalueringsdøgn; tidsstempler i 2033): 480 prognoser, 480 reveals, 0 afvist, DM t = 2,13, p =
0,017. Det viser kun, at kæden virker på data, der er lavet efter HAR's egen struktur. **Det siger intet om
markeder eller om F2.**

## 7. Forhold til F2 (uændret)

F2-udkastet er CONDITIONAL og låst (model, benchmark, univers, QLIKE, primær test). C1 ændrer det ikke og
foregriber det ikke.

- **Ens:** HAR-RV 1/7/30 med OLS på 365 dage, EWMA 0,94 på samme RV-serie, prognose for RV_{t+1} lavet ved døgnets
  slutning, QLIKE, d-fortegn, ensidet DM med Newey-West 5 lags på det tværsnitsvægtede daglige middel-d, og fuld
  dækning som krav.
- **Forskelligt (målingen, ikke modellen):** markPrice-snapshots i stedet for 1h-kline-lukkepriser, 23 i stedet for
  24 afkast pr. døgn (embargo), fremadrettet i stedet for historisk, og C1 kan dække alle census-perps, hvor F2's
  univers er fast på 20 mønter.
- **C1 er ikke en F2-test.** C1-prognoser kan ikke give F2 et PASS. Enhver bekræftende brug (univers, vindue,
  α_F = 0,0125 fra ændring 8's programformue, Holm, styrke) kræver en separat godkendelse og en låst, versioneret
  protokol, før det første afslørede udfald ses. Den kan ikke bruge explore0-kalibreringen som validering.

## 8. Dækning nu (census/1, kun tællinger, genereret 2026-11-06 13:59 UTC)

- Snapshots 2026-10-27 15:00 → 2026-11-06 13:00 UTC: **221 af 239 timeslots (92,5 %)**, 18 mangler, 0 dubletter, 0
  fejlrækker. Hullerne ligger alle 2026-10-30 19:00 → 2026-10-31 22:00 (7 + 3 + 3 + 2 + 2 + 1 slots, de urene
  stop i den periode).
- Hele UTC-døgn siden start: 9 (10-28..11-05). **Komplette døgn: 7** (10-28, 10-29, 11-01..11-05). Ufuldstændige:
  10-30 og 10-31. I dag (11-06) er komplet indtil videre.
- **Nuværende sammenhængende løb: 5 komplette døgn fra 2026-11-01** for alle 941 markPrice-symboler. 6 symboler er
  først set efter start. Intet symbol mangler flere slots end selve snapshot-hullerne. Median 7 komplette døgn,
  min 5.
- BTCUSDT og ETHUSDT: 221/239 slots, 7 komplette døgn, løb 5 døgn fra 11-01.
- Antal komplette døgn med RV, der findes i dag: 7 pr. symbol, heraf 5 sammenhængende.

## 9. Første gyldige prognose (hvis indsamlingen fortsætter uden huller)

| model | krav | inputdøgn | første måldøgn (UTC) | oprettes | første reveal |
|---|---|---|---|---|---|
| HAR-RV(1,7,30), 365 rækker + 30 lags | 395 komplette døgn | 2026-11-01..2027-11-30 | **2027-12-01** | 2027-11-30 efter 23:00-mærket, før 00:00 | 2027-12-02 01:00 |
| EWMA 0,94, indkøring 50 | 50 komplette døgn | 2026-11-01..2026-12-20 | **2026-12-21** | 2026-12-20 efter 23:00-mærket, før 00:00 | 2026-12-22 01:00 |

Ethvert nyt manglende timeslot (fx et urent værtsstop, se reboot-noterne) genstarter løbet. Så bliver datoerne
(hullets døgn + 1) + 395 eller + 50 døgn. Et sammenligneligt par (EWMA og HAR samme døgn) findes først fra
2027-12-01. Ren regning med `p2_power.dm_power` (e ukendt, 20 mønter, ρ_c 0,5, HAC 1,5, α 0,0125): styrke 0,12 ved
e = 0,10 efter 90 evalueringsdøgn og 0,47 efter 365. En fremadrettet F2-lignende test er altså tidligst relevant
omkring 2028, medmindre en godkendt protokol vælger et kortere vindue.

## 10. Hvad aktivering kræver

1. **Separat godkendelse:** en dateret ændring i PROTOCOL_V3, der aktiverer C1 som observationsstrøm, med
   config-sha256 ovenfor (eller en ny version). Den må ikke ændre F2.
2. En planlagt kørsel kl. ~23:30 UTC (ikke 00:05 som i FORWARD_DATA_PLAN: det ville ligge inde i måldøgnet). Den
   skal læse census/1 read-only og kun fremad, udstede én prognose pr. model og symbol for det kommende døgn, og
   efter 01:00 UTC hæfte reveals for døgnet før. Den må aldrig skrive tilbagedaterede eller "frosne" prognoser for
   dage, der allerede er begyndt, og aldrig efterregne historikken siden 10-27.
3. En adapter fra census-rækker til (ts, pris) med informationstid max(række-ts, premium_time) og en journalsti
   uden for lab-koden (fx `research/data/c1/journal.jsonl`). Head-hashen skal ankres eksternt (dagligt i en commit).
   Det sker uden ændring i lab/, uden deploy og uden berøring af pm_lp, indsamlere eller systemd-enheder.
4. Lager ~941 × 2 × (~760 B prognose + ~620 B reveal, målt på den syntetiske journal) pr. døgn ≈ 18 MB/uge.
   Det er mere end registrets 4,6 MB, fordi hver post bærer input-hash, fit-info og kædefelter. CPU: sekunder pr. døgn. 0 netværkskald.

## 11. Afvigelser fra registret og begrænsninger

- Registret og FORWARD_DATA_PLAN beskrev C1 som "HAR (1 d/7 d), ≥ 7 dages historik, kl. 00:05". Ordre 51 og F2
  siger HAR-RV(1,7,30) med et 365-vindue, og 00:05 ville bryde reglen om oprettelse før målvinduet. Registret er
  ikke ændret (opgaven tillod kun nye filer). Det bør rettes ved aktivering.
- Med F2's 365-vindue kommer den første HAR-prognose først 13 måneder efter et hulfrit løb. Et kortere vindue ville
  være en anden variant og kræver godkendelse. C1 vælger ikke.
- Negative HAR-prognoser afvises (tælles). Hvordan de skal behandles i en test (afvisning, gulv, log-HAR), er en
  protokolbeslutning.
- Fuld dækning som krav betyder, at ét tabt timeslot sletter et døgn og genstarter EWMA-løbet og HAR-vinduet. Det er
  konservativt, og ved 5 urene værtsstop på 9 døgn (reboot-noterne) er det den største praktiske risiko.
- Journalens ur er værtens ur. Et forkert systemur kan ikke opdages indefra. Et eksternt tidsanker (commit-tid)
  begrænser det.
- Hash-kæden beviser rækkefølge og uændrethed efter skrivning, ikke at prognosen blev skrevet på det angivne
  tidspunkt. Det kræver ekstern ankring af head-hashen, mindst dagligt.

## 12. Testresultater (2026-11-06)

- `python3 -m unittest tests.test_research_c1_forecast`: 33 tests OK. De dækker tilbagedateret prognose,
  oprettelse i eller efter målvinduet, cutoff efter oprettelse eller målstart, lav dækning, genudstedelse og dårlige
  værdier, manipulation (redigeret værdi, omhashet post, slettet, ombyttet, afkortet hale, ufærdig linje, konsistent
  omskrevet lookahead-kæde), dobbelt og for tidlig reveal, void-reveal, evaluering uden reveal, ikke-før-målvinduet,
  uenige reveals, for få døgn, QLIKE- og EWMA-håndeksempler, indkøringsregel, RV-definition, eksakt OLS,
  HAR-koefficienter genfundet (15.000 syntetiske døgn, hældninger ±0,05), HAC = hypo_engine, syntetisk
  ende-til-ende med DM (socket patchet, skriver kun i temp-mappe, deterministisk), ingen netværksimport og
  dækningslæser på en syntetisk db (read-only, læser aldrig 2024-rækker, ingen priser i output).
- `python3 -m unittest tests.test_research_gates tests.test_lab_safety`: 12 tests OK.
