# HOLDOUT_TEST_ACCESS_AUDIT: testsuitens adgang til 2024-holdout-filer (direktørordre 59-F P2, 2026-11-09)

Append-only. Ingen historiske auditposter er omskrevet. Alt herunder er undersøgt read-only: fillister, filtider,
kode og tællinger. **Ingen 2024-fil er åbnet eller læst under denne undersøgelse.**

## 1. Hvad skete der

| Punkt | Fund | Grundlag |
|---|---|---|
| Test | `tests/test_lab_research_engine.py::HoldoutGate::test_too_few_symbols_fail_the_holdout`, i suiten siden `70b40d3` (2026-10-18) | `git log -S` |
| Kaldsti | `pipeline.step_holdout` → `_declare_holdout` (ikke mocket) → `data.files_for(sym, "holdout")` → `data._fetch` → `urlopen(data.binance.vision …2024-MM.zip)` (4 forsøg) | kodelæsning (59-E) |
| Med cache | ingen download, ingen prisparsing; `Gateway.access` **læser råbytes** fra holdout-filerne for at beregne sha256 og skriver `datasets` og `holdout.opened` i **testens midlertidige DB** | kodelæsning (59-E) |
| Uden cache | testen forsøger at **downloade** 2024-filerne | observeret 2026-11-09 04:17–04:30 UTC i den isolerede worktree (blokeret af DNS; intet hentet) |

**Nyt fund (denne audit):** dev-worktree'ens cache `copybot/data/lab/market/` indeholder **192 filer, alle fra 2024**:

| Fakta | Værdi |
|---|---|
| Symboler | 8: ADA, AVAX, BNB, DOGE, DOT, LINK, LTC, XRP (USDT) |
| Filer pr. symbol | 12 måneders 1h-klines + 12 måneders fundingRate |
| Filtider | alle 2026-10-19, kl. 10:19:27–10:21:20 lokal (på under 2 min) |
| Andre filer i cachen | ingen (0 filer fra andre år) |

Mønstret, kun holdout-sættet hentet samlet på én gang, passer med, at **testen selv downloadede 2024-filerne** ved den
første fulde suite i dev-worktree'en 2026-10-19. Det var dagen for flytningen til Linux-PC'en (`LINUX_FLYT.md`).
Tidspunktet ligger mellem commits `4c32ff6` (10:08) og `5f1de9a` (10:24) samme dag. Hvilken præcis kørsel det var, er
ikke dokumenteret (UNVERIFIED).

## 2. Hvad er dokumenteret

- **2026-10-19:** 192 rå 2024-holdout-filer blev hentet over netværket til dev-worktree'ens cache, efter alt at dømme
  af testsuiten.
- **Siden da:** hver fuld suite i dev-worktree'en har læst råbytes fra holdout-filerne via `Gateway.access`
  (sha256-hashing). Alene i denne session findes 60 suite-logfiler i scratchpad. Antallet af tidligere kørsler er ukendt.
- **Adgangen var begrænset til råbyte-hashing:** ingen prisparsing, ingen afkast, ingen strategiresultat (efter
  kodelæsningen i 59-E).
- `datasets` og `holdout.opened` blev kun skrevet i testens midlertidige databaser.
- **Produktionen er ikke berørt:**
  - produktionens `lab.db` har 0 `holdout.opened` og 0 `datasets`-rækker for 2024;
  - produktionens cache har 0 filer fra 2024;
  - dev-worktree'ens `lab.db` har 0 hændelser.
- **2026-11-09:** den isolerede 59-D-worktree forsøgte at downloade. DNS blokerede det, og intet blev hentet.

## 3. Hvad er stadig ukendt

- Præcis hvilken kørsel 2026-10-19 der hentede filerne, og om den skete via denne test eller en anden sti. Kun denne
  test er påvist at kunne gøre det.
- Antallet af suite-kørsler i dev-worktree'en før denne session.
- Om andre tests eller værktøjer har læst cachen. Hjælperens netværkshegnede kørsel 59-E fandt 0 netværks- og
  downloadforsøg i 1288 tests, men dækkede ikke filadgang og ikke subprocesser. 59-F P0/P1 udvider kontrollen.
- Om produktionens testsuite nogensinde har kørt den test med netværk. Produktionens cache har ingen 2024-filer, så
  intet tyder på det.

## 4. Tidligere holdout-erklæringer

- Erklæringer som "Slut-testen for 2024 er ikke åbnet" (`PROTOCOL_V3.md` l. 140) og "The sealed 2024 holdout was not
  opened" (`MISSION6_FLEET_RUN.md` l. 99) samt sessionens "2024-holdout er ikke rørt"/"ingen 2024-holdout" handler
  om **forskningsanalysen**: ingen protokol har åbnet holdout i lab.db, og ingen resultater er beregnet på 2024.
  **Det er fortsat korrekt.**
- De er dog **ufuldstændige**: rå 2024-filer er hentet og hashet af testsuiten i dev-miljøet. Rettelsen tilføjes her
  og i `MISSION27_4` punkt 27 (append-only). De oprindelige tekster ændres ikke.
- Konsekvens for evidensen:
  - ingen kendt, fordi ingen priser eller afkast fra 2024 er beregnet eller set;
  - holdout-sættets "usethed" er dermed intakt på resultatniveau, men **ikke på filniveau**.
  - Fremtidige holdout-erklæringer skal skelne mellem "analyse ikke åbnet" og "filer ikke tilgået".

## 5. Forslag (afventer direktøren; intet udført)

1. Karantæne af de 192 cachede 2024-filer i dev-worktree'en. Forslaget er at flytte dem ud af `data/lab/market` til en
   registreret karantænemappe med en post i `research/data/QUARANTINE.json`, så ingen test eller noget værktøj kan nå
   dem. De slettes ikke uden ja.
2. Testisolationen (`tests/offline_market.py`) merges til dev-grenen først efter 59-F's verifikation.
3. Indtil da køres den fulde suite fortsat uden `tests/test_lab_research_engine.py`.
