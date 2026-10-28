# Drift på Linux-pc'en (HP-USDT): log-ud, dvale, genstart og overvågning

Status 2026-10-18. Linux er den eneste vært. Windows bruges kun til at rette kode og pushe.

**Målt** betyder observeret på værten. **Forventet** betyder udledt af koden eller systemets opsætning, men ikke
afprøvet på denne maskine.

## Processer (alle startet i hånden, i baggrunden)

| Del | Start (fra `~/ecommerence/copybot`) | Stop |
|---|---|---|
| pm_lp-indsamler | `setsid nohup ./START_PM_LP.sh >> data/research/pm_lp/collector.log 2>&1 < /dev/null &` | `kill <pid>`. Hullet tæller i dækningen. |
| Laboratoriet: flåde og dashboard | `setsid nohup ./START_LAB.sh >> data/lab/start.log 2>&1 < /dev/null &` | `python3 -m lab stop --reason "..."` |
| Uafhængig vagt | `setsid nohup ./START_WATCH.sh >> data/lab/watch.log 2>&1 < /dev/null &` | `kill <pid>` |

- Alle tre nægter at starte en ekstra kopi (lås i `data/`).
- **Stop af flåden** (`lab stop` og dashboardets stop-knap), som koden gør det fra commit efter d37201f:
  - Flåden holder op med at tage nye jobs. Tunge jobs, der kører i jobprocesser, afbrydes: poolen lukkes
    (`cancel_futures`), og jobprocesserne dræbes. `system.stopped` skrives, før der ventes på tråde, og der ventes
    højst 10 s i alt. Et stop tager derfor sekunder, ikke op til 3 minutter.
  - Et afbrudt job lægges straks tilbage i køen (`job.interrupted`) og får sit forsøg tilbage (PROTOCOL_V3
    ændring 6). Det tæller ikke som fejl: ingen `job.timeout`, `job.retry`, `job.failed` eller `worker.failed`. Det
    gælder også ved nedlukning af pc'en, hvor jobprocessen dør først. Kan det ikke skrives, kører `jobs.recover`
    jobbet igen efter næste start.
  - Under stoppet genstartes ingen workers (ingen falsk `worker.restarted`).
- **Låst database.** Holder en anden proces databasens skrivelås i over 30 s (fx en `sqlite3`-skal), venter flåden
  den ud i stedet for at stoppe. Bagefter skrives `system.db_busy` med varigheden. Før ændring 6 stoppede flåden
  med exit 1.
- **Frossen eller hængt flåde.** `lab stop` venter ikke på den.
  - Flåden regnes kun for hængt, når processen står i tilstand T (frosset), eller når dens heartbeat er over 30 s
    gammelt. Så melder `lab stop` det straks med pid og procestilstand (exit 3).
  - Holder en anden proces databasens skrivelås (aflæst i `/proc/locks`), melder `lab stop` hvilken, og flåden
    røres ikke, heller ikke med `--force` (exit 3).
  - `python3 -m lab stop --force --reason "..."` afslutter en hængt flåde: først SIGTERM og SIGCONT, så den
    lukker pænt ned som ovenfor, og først SIGKILL efter 20 s (også jobprocesser, der er startet i mellemtiden).
    Bagefter skrives `system.stop_forced`. Kan den ikke skrives, siger `lab stop` det og giver exit 4.
  - Flåden genkendes kun som `python3 -m lab [--db ...] fleet|supervise`, startet fra denne mappe og højst 300 s
    før sin `system.running`-hændelse. En genbrugt pid eller en flåde fra en anden kopi af koden røres ikke.
  - Målt 2026-10-18 i en isoleret database: en frossen supervisor meldt på 0 s; `--force` stoppede den pænt på 1 s
    (exit 0). Testet (tests/test_lab_stop.py): SIGTERM midt i et 120 s job giver exit 0 på få sekunder, og jobbet
    køres igen efter genstart.
  - Ved SIGKILL skriver START_LAB.sh "STOPPEDE UVENTET", og dashboardet kører videre.
- Kontrollér en start med `pgrep -af "research.pm_lp|lab (fleet|web|watch)"`. Kontrollér også, at
  `data/lab/watch_status.json` får nyt tidsstempel hvert halve minut.
- Status nu: `python3 -m lab watch --once` (exit 0 = alt kører) og `python3 -m lab health`.

## Dvale

**Målt kl. 14:04 UTC: dvale er blokeret.**
- Du startede blokeringslinjen nedenfor på skrivebordet kl. 14:03:34 UTC (pid 225567, session 2, `setsid nohup`).
- `systemd-inhibit --list` viser `copybot ... sleep:idle ... block`.
- Vagten kontrollerer det hvert halve minut (komponenten `awake`). Den godtager, at dvale-målene er `masked` i
  systemd (gælder også efter genstart), og ellers en blokering i logind. Den melder kun, hvis ingen af dem findes.
- Før det, kl. 12:44 UTC, var der ingen blokering. Der var kun "delay"-inhibitorer, `IdleAction=ignore`, og kernen
  havde talt 0 dvaler siden opstart.
- XFCE er sat eksplicit 2026-10-18 (uden sudo, i brugerens xfconf):
  - Strømstyringen går aldrig i dvale ved inaktivitet (`inactivity-on-ac` og `inactivity-on-battery` = 14 =
    "aldrig").
  - Dvale- og dvaletilstandsknapperne gør intet (`sleep-button-action`, `hibernate-button-action` = 0).
  - Tænd/sluk-knappen spørger stadig (3).
  - Log-ud-dialogen viser ikke længere Dvale og Dvaletilstand (`xfce4-session /shutdown/ShowSuspend`,
    `ShowHibernate` = false).
  - Fortryd: `xfconf-query -c <kanal> -p <egenskab> -r`.
- Varig blokering for hele systemet, også efter genstart og før log-ind: kørt 2026-10-18 med root-godkendelse
  (brugeren `anton` er ikke i `sudo`-gruppen; polkit-dialogen kræver root-adgangskoden). Alle fem står som `masked`:
  `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target`.
  Fortryd med `unmask`.
- Strømsvigt kan ingen indstilling i styresystemet forhindre. BIOS-indstillingen "After Power Loss: Power On" får
  maskinen til at tænde igen bagefter, men intet starter af sig selv før S7.
- XFCE's egen inhibit-grænseflade (som videoafspillere bruger) blev afprøvet. Den laver **ikke** en logind-blokering
  og stopper derfor ikke dvale fra menuen. Den bruges ikke.

**Forventet, ikke afprøvet her:**
- Ved dvale fryser alt, også vagten.
- Der tages ingen snapshots. Hullet tæller imod pm_lp-dækningen og mod D1, hvis det sker i holdout-perioden
  10-31 → 11-13.
- Efter opvågning fortsætter processerne, og vagten melder "maskinen har været i dvale".
  - Den ser det enten på kernens dvaletæller eller på, at `CLOCK_BOOTTIME` er løbet fra `CLOCK_MONOTONIC`.
  - Det sidste dækker også dvale til disk.
- Vil du have det bekræftet, skal der laves en kort, bevidst dvale uden for holdout-perioden. Det er din beslutning.

**Mindste sikre blokering, uden at ændre indstillinger.** Kør denne linje i en terminal på selve skrivebordet. Over
SSH afviser polkit den.

```
setsid nohup systemd-inhibit --what=sleep:idle --who=copybot --why="lab og pm_lp" --mode=block sleep infinity >/dev/null 2>&1 &
```

- Kontrollér med `systemd-inhibit --list` (der skal stå `copybot ... block`) eller med `python3 -m lab watch --once`
  (linjen `awake`).
- Efter genstart er linjen ikke længere nødvendig, fordi dvale-målene er `masked`. Den skader ikke og kan køres som
  ekstra sikring.
- Med `setsid nohup` overlever blokeringen, at terminalvinduet lukkes. Den varer, til processen stoppes, eller
  maskinen genstarter.
- Uden `setsid nohup` ophører den, når vinduet lukkes.

**Mere robust, men en systemændring:** `sudo systemctl mask sleep.target suspend.target hibernate.target
hybrid-sleep.target`. Fortryd med `unmask`. Kræver din godkendelse.

## Log-ud

- **Målt:** `KillUserProcesses=false`, og processerne er startet med `setsid nohup`, så de ignorerer SIGHUP.
  Indsamleren kører i SSH-session 104, som er lukket, og den har kørt videre i over 1 time.
- **Forventet:** log-ud af skrivebordet rammer dem ikke, fordi de ikke kører i skrivebordssessionen.
  - Vagtens skrivebordsnotifikationer kræver dog en aktiv skrivebordssession med notifikationsdæmon.
  - Uden en sådan står alarmer kun i `data/lab/logs/watch-*.jsonl` (med `"notified": false`), i `data/lab/watch.log`
    og i `data/lab/watch_status.json`.
- **Undtagelse:** startes `./START_LAB.sh` i forgrunden i et terminalvindue, stopper laboratoriet, når vinduet lukkes.

## Genstart og strømsvigt

- Alt stopper, og **intet starter af sig selv.** Det er bevidst: autostart er S7-automatisering. Undtagelse, når
  tjenesten er installeret: indsamleren (se "pm_lp: beskyttelse af holdout", punkt C).
- Efter genstart kører du de tre startlinjer ovenfor, i rækkefølgen indsamler, laboratorium, vagt.
- **Indsamleren** genoptager med samme D0 (2026-10-17).
  - Målt ved genstart samme dag: første snapshot 6–14 s efter start.
  - Efter en rigtig genstart af maskinen (eventuelt med valg af nyt panel ved midnat) er tiden ikke målt.
- **Laboratoriet** kører preflight og recovery. Paper-strategier varmer op og afstemmer, før de handler.
- **S7** nulstilles, hvis afstanden mellem to `system.alive`-poster bliver over 2 timer. Supervisoren skriver en post
  hver time, så den sikre pause er 2 timer minus tiden siden seneste post. Det kan være ned til ca. 1 time.
  `python3 -m lab gate` viser tællingen.
- **Varm journal efter `kill -9` eller strømsvigt.** Vagten kan så melde "pm_lp database unreadable". Indsamleren
  ruller journalen tilbage selv, næste gang den starter. Slet aldrig `pm_lp.db-journal` i hånden.
- **Afprøvet efter strømsvigt 2026-10-23** (pc'en frøs ca. 15:05, blev slukket, startede 15:09). Tjekliste, i
  rækkefølge, alle kommandoer fra `~/ecommerence/copybot`:
  1. `systemctl --user show pm-lp-collector -p ActiveState -p NRestarts` → active (linger; kom selv 15:09:52).
  2. `git -C ~/ecommerence status --short` → tom (ellers tomme filer efter nedbrud: gendan, se ovenfor).
  3. `python3 -m lab verify` (hashkæderne) og `python3 -c "import sqlite3; print(sqlite3.connect('data/lab/lab.db').execute('PRAGMA quick_check').fetchone())"` → ok.
  4. `(setsid nohup ./START_LAB.sh >> data/lab/start.log 2>&1 < /dev/null &)` (kodevagt + preflight kører selv).
  5. Vagten: `setsid nohup ./START_WATCH.sh >> data/lab/watch.log 2>&1 < /dev/null &` — kun efter brugerens ja,
     indtil S7-scriptet er installeret. Den melder selv sit hul ("overvågningen var nede … 54 min").
  6. `python3 -m lab deploy-check --commit $(git rev-parse --short HEAD)` → DEPLOY OK.
  Målt: laben nede 15:08–15:16, vagten 15:07–16:02 (ventede på ja), pm_lp mistede 2 min snapshots, S7 talte ikke
  udfaldet (`system.alive` 14:58 og 15:15). Vagtens detektion er afprøvet på en kopi af registret med den rigtige kode:
  tavs supervisor (900 s), agent med puls men uden gennemløb (1200 s), fejlet agent og FAIL_CLOSED blev alle meldt.
- **Strømsvigt 2026-10-26 (Mission 14; skrevet 2026-10-26 kl. 13:46 lokal, før kode). Tidslinje i UTC, målt:**
  | Tid | Hændelse | Kilde |
  |---|---|---|
  | 11:47:34 | sidste lab-hændelse | `events` |
  | 11:50:02 | sidste pm_lp-snapshot | `pm_lp.db` `snaps` |
  | 11:50:38 | sidste vagt-tick | `watch.log` |
  | ca. 11:51 | hård slukning: ingen nedlukning i journalen (den slutter 11:39:47; de sidste minutter nåede ikke disken) | `journalctl -b -2` |
  | 12:23:25 | opstart 1 | `journalctl --list-boots` |
  | 12:25:27 | `Power key pressed short` → logind slukker (ingen skrivebordssession endnu, så xfce's "spørg" gjaldt ikke) | `journalctl -b -1` |
  | 12:25:50 | opstart 2 (den nuværende) | `/proc/stat` btime |
  | 12:26:04 → 12:27:34 | indsamlerens ExecStartPre (venter på navneopslag) timede ud efter 90 s | `journalctl --user` |
  | 12:28:35 / 12:29:38 | systemd startede indsamleren igen (NRestarts=1) / første snapshot | journal / `snaps` |
  | 12:36:28 | laben startet i hånden (ventede K3-vinduet 12:00 ± 35 min ud); `system.host_boot` og `scanner.gap` skrevet selv | `events` |
  | 12:36:55 | første scanning efter start | `scan.finished` |
  | 12:37:29 | vagten startet efter brugerens ja; meldte selv sit hul (46 min) | `watch.log` |
  Huller: pm_lp 39,6 min snapshots; laben 48,9 min; vagten 46,9 min. S7 talte ikke udfaldet (`system.alive` 11:40:45 og
  12:36:28, under 2 t), og S7-gaten er ÅBEN (7,09 af 7 dage). Starter selv: kun indsamleren (systemd, linger). Starter
  ikke selv: laboratoriet og vagten (S7-enhederne er forberedt, ikke installeret). Værten har ingen batteri- eller
  strømforsyningsenhed i `/sys/class/power_supply`: et strømsvigt eller et langt tryk slukker straks.
  K3-runden S = 12:00 UTC blev auditeret `ugyldig` automatisk ved start (data mangler) og tæller ikke.
- **Kontrol efter værtstart: `python3 -m lab watch --once` (Mission 14; skrevet 2026-10-26 kl. 13:46 lokal, før
  kode).** Fundet: linjen `scanner` blev aldrig skrevet af `--once` (exit-koden talte den dog med), og tre kontroller
  kunne melde OK ud fra data fra før genstarten. Rettelser, alle kun skærpelser (ingen grænse løsnes):
  1. `--once` skriver `scanner`-linjen.
  2. Nye linjer kun i `--once`: `host` (opstartstid, kun oplysning) og `watcher`: en vagt-løkke
     (`python3 -m lab watch`, ikke `--once`) kører fra denne mappe, og `watch.heartbeat` er højst 120 s gammel og
     nyere end opstarten. Mangler vagten, er `--once` ikke grøn (exit 1).
  3. Ingen sundhed ud fra gammel status:
     - `lab`: supervisorens puls skal være nyere end opstarten.
     - `collector`: seneste snapshot skal være nyere end opstarten.
     - `scanner`: seneste `scan.finished` skal være nyere end flådens seneste `system.running`. De første 15 min efter
       start er linjen "ikke vurderet"; derefter er manglende scanning siden start en fejl.
     - `paper`: før 1,5 t efter start er linjen "ikke vurderet" (før stod der "marked hourly" ud fra gamle mærker), og
       derefter skal hvert aktivt regnskabs seneste mærke også være nyere end starten.
  Den kørende vagt bruger samme kontroller (punkt 3) fra sin næste start; `host`/`watcher` findes kun i `--once`.
  Intet starter, stopper eller genstarter noget; S7-enhederne, pm_lp og alle pause- og FAIL_CLOSED-regler er uændrede.

## pm_lp: beskyttelse af holdout (godkendt af brugeren 2026-10-19)

Driftsregler, ikke en protokolændring: ingen porte, vinduer, paneler, data eller D0 ændres (PM_LP_SPEC er uændret).

**Grundlag (read-only undersøgelse 2026-10-19, alle tider UTC):**

| Hul | Vært | Varighed | Årsag |
|---|---|---|---|
| 10-18 04:37:50 → 06:39:35 | Windows | 121,8 min | Processen stod stille og fortsatte uden genstart (dvale eller frosset konsol; ikke bevist) |
| 10-18 10:15:10 → 11:20:08 | Windows → Linux | 65,0 min | Windows-pc'en genstartede; indsamleren blev startet på Linux 11:19:54 |
| 10-19 07:39:52 → 10:30:02 | Linux | 170,2 min | Brugeren trykkede på tænd/sluk-knappen 07:40:27 (systemjournalen: `Power key pressed short` → `Powering off`; bekræftet af brugeren); ca. 165 min gik med at vente på start i hånden |

- I alle tre huller var der 0 snapshots og 0 trade-polls. Et netværksudfald havde givet polls med `ok=0`
  (`pm_lp.py` gemmer også fejlede polls); der er 0 fejlede polls ud af 140.400. Dækningsberegningen er korrekt
  (rækker = runder × 200 hver dag).
- D1 er gennemsnittet over hele holdout (10-31 → 11-13), ikke en daglig grænse: alle snapshot-rækker / (markedsdage
  × 1440) (`pm_lp.coverage`). Uden huller er dækningen ca. 97,9 % (en runde pr. ca. 61,3 s). Budgettet til
  nedetid er derfor ca. 1.600 min (ca. 26 timer) i alt over de 14 dage. De tre huller ovenfor ville tilsammen have
  kostet ca. 1,8 procentpoint.

**A. Efter enhver genstart eller stop: indsamleren først og straks.**
- Start indsamleren, før noget andet undersøges, merges, testes eller deployes. Først derefter laboratoriet og
  vagten (rækkefølgen ovenfor).
- Undersøg årsagen bagefter, mens indsamleren kører.

**B. Ingen planlagte ændringer 2026-10-31 → 2026-11-27** (holdout og opfølgning på markedernes afgørelse).
- Ingen planlagt genstart af maskinen og ingen systemopdatering til og med 2026-11-27.
- ~~Ingen deploy af laboratoriet 2026-10-31 → 2026-11-13 (holdout).~~ **Fjernet af brugeren 2026-10-20** ("drop
  regel B ... ikke begrænset af den irriterende regel"): deploy af laboratoriet er tilladt hele perioden. En deploy
  genstarter kun flåde og dashboard; indsamleren er en separat systemd-tjeneste og røres ikke. Brugeren er oplyst
  om, at pm_lp's holdout dermed ikke længere er beskyttet mod laboratoriets genstarter. Punkterne nedenfor om
  maskinen og indsamleren gælder fortsat, fordi de ikke begrænser laboratoriet; vil brugeren også fjerne dem, kræver
  det et udtrykkeligt ord.
- Indsamleren stoppes aldrig med vilje i perioden.
- Kan noget ikke vente (fx en sikkerhedsrettelse), kræver det brugerens udtrykkelige godkendelse, og indsamleren
  bliver ved med at køre.
- Undtaget er de trin, protokollen selv kræver: `dev` og commit af `PM_LP_FROZEN.md` (punkt F). De rører ikke
  indsamleren, og en commit med kun dokumentation kræver ingen genstart.

**C. Autostart af indsamleren alene.**
- **Undtagelse fra S7-reglen, besluttet af brugeren 2026-10-19:** tjenesten for indsamleren må installeres før
  S7-gaten er åben (S7 var CLOSED, 0,18 af 7 dage). Brugeren blev oplyst om, at tidsplanen også uden undtagelsen
  havde givet beskyttelse før holdout, og valgte at installere nu. Undtagelsen gælder kun denne ene tjeneste.
  S7-gaten selv, dens beregning og reglen for al anden automatisering (laboratoriet, vagten, planlagte opgaver)
  er uændrede.
- Laboratoriet og vagten startes fortsat i hånden.
- Unit-fil: `research/systemd/pm-lp-collector.service`. Den venter på navneopslag efter opstart (højst 10 min),
  fordi indsamleren kalder API'et før sin fejltolerante løkke, og den starter igen 60 s efter et nedbrud.
- Installation (brugeren, i en terminal; den kørende indsamler røres ikke):
  ```
  mkdir -p ~/.config/systemd/user
  cp ~/ecommerence/copybot/research/systemd/pm-lp-collector.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable pm-lp-collector.service      # kun enable: ingen start nu
  loginctl enable-linger anton                          # brugertjenester starter ved opstart uden login
  ```
- Test: én bevidst genstart før holdout, helst i development-perioden (til 2026-10-23), aldrig i holdout. Genstart
  lige efter en `system.alive`-post (ca. HH:51 UTC). Bagefter: `systemctl --user status pm-lp-collector`, ny
  linje i `runs`, første snapshot inden for få minutter. Start laboratoriet i hånden inden for ca. 1 time (S7, se
  ovenfor) og derefter vagten.
- **Slå tjenesten fra efter 2026-11-27** (indsamlingen er færdig ved D0+41), før `holdout` køres:
  `systemctl --user disable --now pm-lp-collector`. Ellers starter en senere genstart indsamleren, som skriver en ny
  `runs`-række og dermed ændrer databasen efter resultatet.
- Når tjenesten er slået til, startes og stoppes indsamleren kun med `systemctl --user start|stop pm-lp-collector`,
  aldrig med START_PM_LP.sh i hånden (den anden kopi afvises af `collector.lock` og prøves igen hvert minut).
- Fortryd: `systemctl --user disable --now pm-lp-collector`, `rm ~/.config/systemd/user/pm-lp-collector.service`,
  `systemctl --user daemon-reload`, `loginctl disable-linger anton`. Start derefter i hånden som før.

**D. Ingen genstartsknap på låseskærmen.**
- Udført af brugeren 2026-10-19. Grundlaget var en hypotese om genstarten 10-19, som systemjournalen siden har
  afkræftet (det var tænd/sluk-knappen, trykket af brugeren selv). Ændringen beholdes som ekstra sikring.
- Ændring (brugeren, kræver sudo): fjern `~power` fra greeterens indikatorer. Den gælder fra næste gang
  låseskærmen vises. LightDM må ikke genstartes (det lukker skrivebordssessionen).
  ```
  sudo cp -a /etc/lightdm/lightdm-gtk-greeter.conf /etc/lightdm/lightdm-gtk-greeter.conf.bak-20261019
  echo 'indicators = ~host;~spacer;~clock;~spacer;~session;~language;~a11y' | sudo tee -a /etc/lightdm/lightdm-gtk-greeter.conf
  ```
- Fortryd: `sudo cp -a /etc/lightdm/lightdm-gtk-greeter.conf.bak-20261019 /etc/lightdm/lightdm-gtk-greeter.conf`.
- Tænd/sluk-knappen og genstart fra skrivebordet virker stadig.

**E. Læseadgang til systemjournalen.**
- Så en fremtidig genstart kan bevises (hvem eller hvad udløste den). Gruppen `systemd-journal` giver kun adgang
  til journalen (mindre end `adm`, som også giver alle filer i `/var/log`).
- Ændring (brugeren, kræver sudo): `sudo usermod -aG systemd-journal anton`. Gælder fra næste login.
- Fortryd: `sudo gpasswd -d anton systemd-journal`.

**F. `dev` og `PM_LP_FROZEN.md` (PM_LP_SPEC §9 trin 5) på en kopi, så indsamleren ikke forstyrres.**
- `dev` nægter at køre før valideringen er slut (`day_of(nu) <= D0+13`). Første mulige tid er 2026-10-31 00:00 UTC,
  dvs. holdout dag 1. Kør tidligst 01:00 UTC (02:00 dansk tid; sommertiden slutter 10-25), så de sidste trades fra
  10-30 er hentet. `dev` læser kun rækker før 10-31 00:00 UTC og bruger intet netværk, så resultatet er det samme
  på en kopi som på den levende database.
- Hvorfor en kopi: `dev` læser alle markeder i development og validation og hasher hele databasefilen
  (`export_manifest`). På den levende database ville det konkurrere med indsamleren i holdout, og hashen ville
  beskrive en fil, der ændrer sig hvert minut. En SQLite-backup er konsistent, tager få sekunder (indsamleren
  venter op til 60 s på en lås), og kopien gemmes som det præcise grundlag for resultatet.
- Trin (fra `~/ecommerence/copybot`; intet her rører indsamleren):
  ```
  mkdir -p ~/pm_lp_runs/2026-10-31
  python3 - ~/pm_lp_runs/2026-10-31/pm_lp.db <<'EOF'
  import sqlite3, sys
  s = sqlite3.connect('file:data/research/pm_lp/pm_lp.db?mode=ro', uri=True)
  d = sqlite3.connect(sys.argv[1]); s.backup(d); d.close(); s.close()
  EOF
  sha256sum ~/pm_lp_runs/2026-10-31/pm_lp.db
  git -C ~/ecommerence worktree add --detach ~/pm_lp_devrun "$(git -C ~/ecommerence rev-parse HEAD)"
  mkdir -p ~/pm_lp_devrun/copybot/data/research/pm_lp
  cp ~/pm_lp_runs/2026-10-31/pm_lp.db ~/pm_lp_devrun/copybot/data/research/pm_lp/pm_lp.db
  cd ~/pm_lp_devrun/copybot && python3 -m research.pm_lp dev | tee ~/pm_lp_runs/2026-10-31/dev_output.json
  ```
- Kontrol: `git` i resultatet er produktionens HEAD, `D0` er 20743, og `db_sha256` er lig `sha256sum` af kopien.
- `holdout` læser `data/research/results/pm_lp_v1_dev.json` i produktionsmappen: kopiér den dertil
  (`cp ~/pm_lp_devrun/copybot/data/research/results/pm_lp_v1_dev.json ~/ecommerence/copybot/data/research/results/`).
- `research/PM_LP_FROZEN.md` skrives med linjen `n_req: <tal>` (eller `n_req: none`, når middelværdien er ≤ 0),
  development- og validation-resuméet, `coverage_dev`, `coverage_val`, `db_sha256`, `git` og tidspunktet for
  kopien. Den committes og lægges i produktion (fast-forward og `git pull --ff-only`). `holdout` kræver, at filen er
  committet og uændret i produktionsmappen.
- **Format (audit 2026-10-19, godkendt):** præcis én linje, der begynder med `n_req:`, og efter kolon kun et
  heltal eller `none`. Ingen anden linje må begynde med `n_req:` (`frozen()` tager den sidste og kalder `int()` på
  den). Skriv desuden `dev_json_sha256: <sha256sum af pm_lp_v1_dev.json>` og `db_copy_sha256: <sha256sum af
  kopien>`.
- Commit filen 2026-10-31, før nogen ser på holdout-data. Kør ikke `dev` igen bagefter (den overskriver
  `pm_lp_v1_dev.json` uden advarsel).
- **Ved `holdout` (tidligst 2026-11-28 00:00 UTC; koden afviser før D0+41 er slut):** slå først tjenesten fra
  (punkt C). Kontrollér i hånden, at `sha256sum data/research/results/pm_lp_v1_dev.json` er lig
  `dev_json_sha256`, og at `n_req` i json-filen er lig værdien i `PM_LP_FROZEN.md`. Kør `holdout` én gang (koden
  håndhæver det ikke).
- I `RESULTS_pm_lp_v1.md` beskrives som kendt begrænsning: `n_req` antager uafhængige markedsdage, så G3 er et
  svagere krav, end tallet ser ud; G2 bruger cluster-bootstrap over markeder, men ikke over dage.
- Efter 2026-11-27, i dev og ikke deployet før holdout er evalueret: tests for `dev`- og `holdout`-datovagten, at
  `dev` ikke ser data efter perioden, `frozen()`-parsning og en kontrol af `n_req` mellem filerne.
- Oprydning: `git -C ~/ecommerence worktree remove ~/pm_lp_devrun`. Kopien i `~/pm_lp_runs/2026-10-31/` gemmes.

**G. Autostart af vagten (PROTOCOL_V3 ændring 15 punkt 5, brugerens ja 2026-10-21).**
- **Først når S7-gaten er åben** (7 rene dage, `gate_s7.open` i `/api/kpis`). S7-reglen ovenfor er uændret; ja'et
  2026-10-21 er ikke en undtagelse som C, kun en beslutning om, hvad der sker, når S7 åbner.
- Unit-fil: `research/systemd/lab-watch.service` (kun læsning; genstarter aldrig laboratoriet eller indsamleren;
  starter igen 60 s efter et nedbrud).
- Installation (brugeren, i en terminal, når S7 er åben; linger er allerede slået til for indsamleren):
  ```
  cp ~/ecommerence/copybot/research/systemd/lab-watch.service ~/.config/systemd/user/
  systemctl --user daemon-reload
  systemctl --user enable lab-watch.service             # kun enable: virker fra næste opstart
  ```
- Kører der en vagt startet i hånden, skal den ikke stoppes; tjenesten starter først ved næste opstart. Vil man skifte
  med det samme: `kill <pid>` (se `pgrep -af "lab watch"`) og derefter `systemctl --user start lab-watch`.
- Fortryd: `systemctl --user disable --now lab-watch`, `rm ~/.config/systemd/user/lab-watch.service`,
  `systemctl --user daemon-reload`. Start derefter i hånden som før.

## Overvågning

| Hvem | Ser | Hvordan |
|---|---|---|
| Flådens agent `risk-1` | at indsamleren eller vagten ikke har skrevet i 15 min | `external.stale` og `external.recovered` i den hash-kædede log og i dashboardets feed |
| Flådens supervisor | en agent, der fejler eller er gået i stå | agenten står rød (`failed`); genstart med backoff, højst 5 i timen |
| Dashboardet | flåden nede | viser "offline" efter 30 s og bliver kørende, når flåden går ned |
| **Vagten** (`lab watch`, uafhængig proces) | se listen under tabellen | log `data/lab/logs/watch-*.jsonl`, `data/lab/watch.log`, statusfil `data/lab/watch_status.json` og skrivebordsnotifikation. Én alarm pr. komponent ved fejl, påmindelse hver time, besked når den virker igen |

Vagten ser:
- flåden nede, frosset eller hængt (2 min);
- FAIL_CLOSED eller ressource-hold over 30 min (`lab_state`);
- hver enkelt agent, der fejler eller er hængt (`agent:<navn>`; vurderes ikke, mens flåden er nede);
- dashboardet nede;
- indsamlerproces væk, gamle snapshots (5 min) eller ulæselig database;
- dvale, bagefter;
- om dvale er blokeret i logind (`awake`).

**Grænser:**
- Alt overvågning kører på samme maskine. Strømsvigt, genstart, dvale eller netværksudfald på selve pc'en kan kun en
  anden maskine opdage, mens det sker.
- Er både flåden og vagten nede, opdager ingen af dem noget.
- `risk-1` ser kun en vagt, der har kørt mindst én gang (dens heartbeat-fil findes).
- Vagten ændrer aldrig databasernes indhold. At åbne `lab.db` (WAL) kan dog oprette eller opdatere filerne
  `lab.db-wal` og `lab.db-shm`.

### Indsamlerens genstart afhænger af lab-koden (tilføjet 2026-10-22, før kode)

En gennemgang 2026-10-22 viste: `research/pm_lp.py` (`collect()`) importerer `lab.supervisor`, som importerer
`lab.legacy`, `lifecycle`, `ops`, `db` og `risk`, fra samme checkout som lab-deploys trækker ind i. Den kørende
indsamler påvirkes ikke af et deploy, men brækker et deploy de importer (eller efterlader et nedbrud filerne på 0 bytes,
som 2026-10-21), fejler hver genstart, som systemd laver hvert 60. sekund, og der samles intet ind.

Derfor (ingen ændring af pm_lp-koden, enheden eller indsamleren):
- `lab preflight` (START_LAB.sh) tjekker ved hver start, at ingen af indsamlerens filer (`lab/supervisor.py`,
  `lab/legacy.py`, `lab/lifecycle.py`, `lab/ops.py`, `lab/db.py`, `lab/risk.py`, `research/pm_lp.py`,
  `START_PM_LP.sh`) er tomme, og at `import lab.supervisor, research.pm_lp` lykkes i en ny Python-proces. Fejler det,
  starter labbet ikke, og den, der deployede, ser det med det samme og ruller tilbage, før indsamleren næste gang
  skal genstarte.
- Deploys, der ændrer de filer, undgås fra 10-31 til 11-13.

### Værktøj (tilføjet 2026-10-22, før kode)

Brugeren bad 2026-10-22 om bedre værktøj ("Du gør det der er bedst"). Intet her beslutter
noget, ændrer en gate eller rører indsamleren:
- `python3 -m lab deploy-check [--commit SHA]`: én kommando efter et deploy, kun læsning. Dashboardet kører den
  forventede commit; endpoints `kpis lanes coverage experiments overview` svarer 200; flåde, dashboard, vagt og
  indsamler kører; seneste start skrev PREFLIGHT OK (startloggen læses som bytes); indsamleren kunne genstarte; ingen
  tracked fil er tom; checkout uden lokale ændringer; FAIL_CLOSED fra; alle agenter aktive (venter op til 90 s på en
  frisk flåde). Slutter med `DEPLOY OK` eller `DEPLOY CHECK FAILED`.
- `tests/test_code_hygiene.py` (under 1 s): ingen funktion eller klasse defineret to gange i samme lab-modul, intet
  tomt lab-modul, og alle lab-moduler kan importeres.
- `scripts/suite.sh [LOG]`: hele testsamlingen med `nice`, timeout 2700 s og én opsummeringslinje (exitkode, antal,
  resultat, sekunder, de 15 langsomste tests, efterladte `data/ingest` eller `data/lab/hypotheses`).
- `scripts/suite_parallel.sh [N=3] [LOGDIR]` (tilføjet 2026-10-23 kl. 17:45): samme tests fordelt på N isolerede
  `git worktree`-kopier af HEAD plus arbejdstræets ucommittede og usporede filer, så tests, der skriver under `data/`,
  aldrig deler mappe; fordeling efter hvert moduls målte sekunder fra sidste kørsel (`~/.cache/copybot-suite-weights`).
  Målt: tre kørsler i træk 966 tests OK (1 sprunget over, som den serielle), intet efterladt, 361 s, 375 s og 265 s
  (balanceret: 263/242/246 s pr. del) mod 568–677 s seriel. Bruges som den fulde suite før deploy; `suite.sh` består
  som reference, hvis de to nogensinde giver forskelligt antal tests eller resultat.
- **Obsidian-vault: droppet samme dag (2026-10-22), før deploy.** Brugeren skrev "Jeg kommer ikke til at bruge den";
  ubrugt kode skal ikke køre. Koden fjernes; intet blev skrevet i produktionen.
- `python3 -m lab report-verify [--day YYYY-MM-DD]` (tilføjet 2026-10-22 kl. ca. 22:40, før kode; brugeren bad om, at
  døgnrapporten kan reproduceres uafhængigt, og at afvigelser vises tydeligt). Kun læsning, egen kode (ren SQL, ikke
  `lane.report`): artefaktets SHA-256 er den, `research.lane_report` registrerede; kontiene er præcis dem, der var
  startet før døgnets slut og ikke stoppet før dets start; for hver konto genberegnes værdi (sidste mærkning før
  døgnets slut, ellers startkapitalen fra `lane.started`), netto, funding, gebyrer, største fald og status; kontantsaldoen
  i sidste mærkning genskabes fra startkapital + handlernes pengestrømme − gebyrer + funding; `net_total` er summen.
  Hver kontrol er en linje `[OK ]`/`[NO ]` med begge tal, og kommandoen slutter med `REPORT OK` eller
  `REPORT MISMATCH` (exitkode 1). Uden `--day` kontrolleres den seneste rapport.
- `python3 -m lab hypo-audit` (tilføjet 2026-10-22 kl. ca. 23:10, før kode; brugeren bad om en målbar oversigt over
  hypotesepipelinen, se `research/studies/AUDIT_HYPOTESER_2026-10-22.md`). Kun læsning af registret: antal pr.
  afgørelse; for UNTESTABLE udelukkelserne summeret pr. underårsag og pr. type (hændelser, største n); for SCREEN_FAIL
  de fejlede tjek og hvilke nøgler, hvis placebo-tjek fejlede uden en placebo-værdi; for hver låst måling resultatet
  og screeningens træfrate på uafhængige data. Den ændrer intet og afgør intet.
  **Automatisk efter hver døgnrapport (tilføjet 2026-10-23 kl. 18:55, før kode; brugerens directive om automatiske
  afstemningskontroller):** banens rapportjob kører samme kontroller (`lab/reportcheck.py checks`, kun læsning) lige
  efter rapporten og registrerer `research.lane_report_verified` (dag, OK/afviger, de fejlede kontroller). Dashboardet
  viser "verificeret" eller "AFVIGER" ved seneste døgnrapport, og en afvigelse står i Overblik. En fejl i selve
  kontrollen stopper ikke rapporten; den registreres som ikke verificeret med årsagen.
- Indeks `events_exp ON events(exp_id, kind, id)` (tilføjet 2026-10-23 kl. ca. 14:00, før kode; brugeren bad om at
  fjerne målt spild). Målt: webprocessen brugte 15,5 % af en kerne hele tiden (3008 s CPU på 19316 s), mere end flåden
  (6,1 %), fordi den åbne dashboardfane henter ~13 endpoints hvert 10.-20. sekund. Opslag med `kind=? AND exp_id=?`
  (fx `pipeline.recorded_sha`, 9 ms pr. kald, 51 kald pr. visning) brugte `events_kind` og læste alle ~4.300
  `job.done`-rækker. På en kopi af registret (22.174 hændelser) faldt de dashboardfunktioner, der kaldes ved hver
  opdatering, fra 1,47 s til 0,77 s (`balance` 0,21→0,05 s, `rejected` 0,31→0,02 s, `paper2` 0,36→0,11 s); output var
  identisk med fastfrosset ur (kun disk/RAM-målinger afveg). Indekset bygges på 0,03 s ved næste start; det ændrer
  ingen række, ingen hashkæde og ingen afgørelse.
  **Målt efter deploy (e4791cb, 2026-10-23 ca. 14:20):** endpoints i produktionen `balance` 0,24→0,07 s, `paper2`
  0,43→0,18 s, `rejected` 0,33→0,03 s, `v2/experiments` 0,39→0,11 s. Webprocessens samlede CPU kan ikke sammenlignes
  før/efter: den følger, hvor ofte den åbne fane spørger (ca. 3 nye forbindelser/s mens fanen ses; 24 % målt, med
  ~0,1-0,2 s CPU pr. tråd). Browserens egen fane-proces brugte samtidig >1,5 kerner (top), langt mere end serveren.
- Dashboardets planet tegnes kun, når billedet ændrer sig (tilføjet 2026-10-23 kl. ca. 14:45, før kode; brugeren bad
  om at måle og rette browserens CPU). Målt: Firefox-fanen med dashboardet (indholdsproces 8687) har brugt 17,9 % af
  en kerne i snit i 49 timer, og hovedprocessen 16 %. Årsag: `Planet` tegner kloden pixel for pixel i JavaScript i
  hver animationsramme (~60/s), men billedet flyttes kun én teksturkolonne ad gangen (512 kolonner pr. omdrejning på
  4 min ≈ 2,1 skift/s; i standby 0,3/s). Over 96 % af tegningerne er identiske. Rettelse: en ramme tegnes kun, når
  kolonneforskydningen har ændret sig; layout og vinduesændring tegner som før. Samme billede, samme hastighed.
  Måling før/efter under ens forhold: headless Firefox 1600×1000, dev-webserver på port 8791 mod en kopi af registret,
  20 s opvarmning, 60 s målt CPU for hele Firefox-procestræet. Før: 31,4 %.
  **Rettelse samme dag (ca. 15:20): planet-rettelsen er IKKE indført.** Målt efter: 31,1 % (ingen forskel). Enkelte
  kørsler (hver 1 gang, 20 s opvarmning): tom side 17,9 % (en ny profils egen opstart), planet slået fra 31,4 %, alle
  CSS-animationer fra 21,9 %, kun LED-blinket `.led.live` fra 21,6 %, skelet-animationen fra 31,4 %, blink i 4 trin
  23,7 %, i 2 trin 27,8 % og 29,5 % (samme variant to gange: støj ca. ±4 point). Peger på LED-blinket (ca. −10
  point), men en serie med 60 s opvarmning og 2 gentagelser blev afbrudt, da pc'en frøs ca. 15:05 og blev slukket
  af brugeren (laben nede ca. 15:08–15:16, pm_lp mistede 2 minutter; registret `quick_check` ok). **Ingen afgørelse,
  ingen ændring af dashboardet.** Headless Firefox kørte ved siden af brugerens egen Firefox, da pc'en frøs; årsagen
  er ukendt (intet i journalen), men flere browser-benchmarks kører ikke uden brugerens ja.
  **Afgjort samme dag kl. 16:16–16:32 (brugerens ja 16:12):** ny serie med 60 s opvarmning, 2 gentagelser, én
  headless Firefox ad gangen med `nice 19` og en vagt, der afbrød ved < 2 GB ledig RAM eller load > 6 (udløste ikke;
  ledig RAM ≥ 11,2 GB). CPU for Firefox-procestræet, 60 s: tom side 2,1 / 2,2 %; dashboard som i dag 12,6 / 15,6 %
  (snit 14,1; runde 1 med samtidige tests, load 4); uden LED-blink 4,5 / 5,7 % (snit 5,1); blink i 4 trin 8,2 / 7,9 %.
  Forskellen (ca. 9 point) er tre gange større end spredningen mellem gentagelser. **Ændring:** `.led.live` (forbindelses-
  lampen) lyser fast grønt uden animation; farven og teksten ("live"/"polling"/"offline") viser stadig tilstanden.
  Forventet: dashboardfanen ca. 14 % → ca. 5 % af en kerne i headless Firefox (målt; brugerens egen Firefox er ikke målt).
- **Dashboardets top gøres entydig (tilføjet 2026-10-23 kl. 16:45, før kode; brugeren bad om et "meget bedre, mere
  clean" dashboard).** Skærmbillede af produktionen (1600 px bred) viste: syv pengekort i to rækker, hvor det største
  "TOTAL P&L" kun er MVRV-skyggekontoen (−18,97 $), fremadtest og samlet værdi i en anden række, og banekontiene (−220 $
  for alle 14) først længere nede; ingen samlet dom over, om noget kræver handling; "Startforsøg" og "Senest stoppet"
  fylder med rækker som "intet spotpar". Ændring, kun visning (samme API, ingen ny beregning af tal):
  - **Overblik** øverst: én dom ("Alt kører" eller "N kræver opmærksomhed") og en liste over det, der kræver handling,
    fra de eksisterende felter: FAIL_CLOSED, supervisor, vagt, agenternes `health` (FAILED/STALE/BLOCKED), fejl i
    vinduet, pause/ressourcestop, data ældre end 2 t og godkendelser, der venter. Grøn kun, når listen er tom.
  - **Papirkonti**: én tabel med en række pr. gruppe (baner og scanner, fremadtest, skyggehandel) og I alt: konti,
    startkapital, saldo, netto, gebyrer, funding — fra `/api/balance` som før; alt mærket simuleret og ikke bevis.
  - "Senest stoppet" og "Startforsøg" foldes sammen som standard (et klik åbner dem).
- **Falsk grøn for live-kilder rettet (tilføjet 2026-10-23 kl. 17:03, før kode).** `/api/coverage` viste GDELT som
  `ok`, skønt ingen nyhed er gemt siden 2026-10-22 10:23 UTC (ca. 31 t) og hvert forsøg siden fejlede med HTTP 429
  (backoff efter ændring 17 punkt 9: nu 24 t mellem forsøg). Årsag: kildens alder blev målt fra `MAX(ts)` over alle
  rækker, også fejlrækkerne, så en fejl gjorde kilden "frisk"; og en fejl talte kun som aktuel i 2 t. Ændring, kun
  visning: alderen måles fra seneste datarække; ny tilstand `failing` ("fejler") når seneste fejl er nyere end seneste
  data og der ikke er kommet data i over 2 t; ellers som før (`stale` efter kildens grænse, `errors` ved en fejl inden
  for 2 t, `ok`). En enkelt fejl lige efter frisk data er stadig `errors`, ikke `failing`.
  **GDELT undersøgt samme dag kl. 18:35 (3 manuelle opslag):** første svar 200 med tom krop (`{}`, 15,8 s), de næste
  to — med 8 s mellemrum og andre forespørgsler (`bitcoin`; `... sourcelang:eng`) — HTTP 429 "Please limit requests to
  one every 5 seconds ... switch to our ngrams dataset". GDELT begrænser altså denne adresse, også ved én forespørgsel
  i døgnet; det er ikke en fejl i vores kode og løses ikke af en kortere backoff. Ingen hypotese bruger GDELT
  (ændring 17 læser kun Binances meddelelser), så intet forskningsarbejde er blokeret. Kilden står som `failing` med
  backoff op til 24 t (ændring 17 punkt 9); ingen ændring.
- **Pengekortene tilbage (tilføjet 2026-10-23 kl. 17:20, før kode; brugeren: "dashboard skal beholde de gamle penge
  profit ting").** De syv kort (saldo, total P&L, i dag, aktive strategier; fremadtest-saldo, samlet simuleret værdi,
  samlet simuleret P&L) med tal-animation og glød vises igen under Overblik; kontotabellen pr. gruppe bliver under
  dem. Feltet "Jobs i kø" viser klar og planlagt hver for sig ("0 klar", "3 planlagt · næste 2027-05-07"), fordi
  de tre jobs er fremadtestenes afgørelser i 2027, ikke en fastlåst kø.

### Git-cachen husker ikke en fil, der netop er ændret ("racy"), rettelse (tilføjet 2026-10-24 kl. 14:14, før kode)

Fundet af den fulde suite 2026-10-24 (testen `GitCaches.test_a_working_file_is_hashed_again_after_any_write` fejlede
under belastning): `registry.hash_object` (d66304a) husker `git hash-object` pr. (inode, størrelse, mtime, ctime).
Linux sætter filtider med et groft ur (millisekunder), så en fil, der skrives om inden for samme tik med samme
størrelse, har samme nøgle, og cachen ville give den gamle blob. For familiegodkendelsens bundne filer kunne en netop
ændret fil i princippet se uændret ud. Rettelse (git's egen "racy clean"-regel): en hash huskes kun, når filens mtime og
ctime ligger mindst 2 sekunder før beregningen; ellers regnes den igen ved hvert kald. Ingen binding, tærskel eller
gate ændres; svaret bliver aldrig forkert, kun lidt langsommere for en fil, der lige er skrevet.

### En stoppet kontos "dage" er dens levetid, ikke alderen i dag (tilføjet 2026-10-24 kl. 13:38, før kode)

`command.lane_view` regnede `days` = (nu − start) også for stoppede konti, så de tre `scanner_premium`-konti viste 4,2–4,5
døgn, skønt de levede fra 10-19 23:24 / 10-20 04:18 / 10-20 05:37 til 10-21 01:42 / 10-22 05:13 / 10-21 19:02 (lokal tid).
Ændring, kun visning: `days` = ((stop eller nu) − start) / 86 400. Ingen stopregel bruger feltet.

### Bane-opdelingen adskiller målt bogafstand fra det modellerede slippage-tillæg (tilføjet 2026-10-24 kl. 13:36, før kode)

Målt 2026-10-24 (rå `sim_fills`): `paper.submit_taker` sætter fyldprisen = det gennemgåede bogniveau × (1 ± `extra_slippage`)
(bane- og scannerkonti: 0,02 % pr. ben, ændring 11 punkt 4). `lane.decomposition` (12h punkt 3) kalder Σ |px − mid| · qty
"spread/slippage" og mærker den observeret, men den indeholder tillægget. Ingen dobbelttælling (gebyret står for sig),
men målt og modelleret er blandet: median pr. ben for de store mønter 3,7 bp (perp) og 5,5 bp (spot), heraf 2 bp model;
for de tre `scanner_premium`-konti 19,7 og 33,9 bp. Ændring, kun visning: opdelingen får `book` (Σ afstanden fra midten til
bogniveauet, målt) og `allowance` (Σ tillægget, beregnet af kontoens egen `costs.extra_slippage` fra `lane.started`), som
summerer til den uændrede `spread_slippage`; dashboardet viser tillægget. Ingen pris, intet gebyr, ingen regel og intet
resultat ændres.

### Skrevne klokkeslæt kontrolleres mod commit-tiden; erratum for 2026-10-23 (tilføjet 2026-10-24 kl. 13:24, før kode)

Fejlen: klokkeslæt i daterede noter blev skrevet efter skøn (ud fra planlagte vækninger), ikke aflæst. Fem gange
2026-10-24 lå den skrevne tid efter den commit, der skrev den (rettet: 8231fee, 1190b74, b93e0a6 og to før push);
`scripts/check_note_times.py` (git blame, kun læsning) finder yderligere 8 linjer fra 2026-10-23, 2–17 minutter efter
deres commit. Klassifikation: forfatterfejl i prosa ("fremtidigt tidsstempel"), ikke en fejl i lab-data: ingen
signaler, funding, hændelsesrækkefølge eller P&L bruger disse tekster, og "før kode" afgøres af commit-rækkefølgen,
som er intakt i alle 8 tilfælde. De 8 historiske linjer omskrives ikke (en af dem står i en ændring i PROTOCOL_V3);
de korrekte tider er commit-tiderne:

| Fil | Skrevet | Commit |
|---|---|---|
| LINUX_DRIFT.md, `suite_parallel.sh` | 17:45 | 17:44 |
| LINUX_DRIFT.md, dashboardets top | 16:45 | 16:43 |
| LINUX_DRIFT.md, falsk grøn for live-kilder | 17:03 | 17:00 |
| LINUX_DRIFT.md, pengekortene tilbage | 17:20 | 17:11 |
| LINUX_DRIFT.md, `lab status` senere afgørelse | 21:10 | 21:00 |
| LINUX_DRIFT.md, fremadtest mod køb-og-hold | 18:15 | 17:58 |
| LINUX_DRIFT.md, vagten måler pm_lp-dækningen | 17:55 | 17:46 |
| PROTOCOL_V3.md ændring 11i, "registret til 16:20" | 16:20 | 16:17 |

Ændring: kontrollen bliver en test (`tests/test_note_times.py`), der kører over `research/` for linjer committet fra
2026-10-24; "kl." skal være ≤ commit-tiden, "ca." må runde højst 5 minutter op. Klokkeslæt aflæses med `date` i samme
trin, som noten skrives.

### Dashboardets "Fremadtest (låst)" viser også U1F og M1F (tilføjet 2026-10-24 kl. 12:54, før kode)

Metrikken viste kun H5F og H5X (USD-M-listninger). Ændring, kun visning: `coverage.forward` får en række for M1F
(ændring 17j), talt fra news-watch' titler efter den låste tekst: meddelelser med `usable_from` ≥ 2026-10-25 00:00
UTC, der matcher punkt 2's regel; mønter, der har stået i en tidligere "Extend the Monitoring Tag"-titel (punkt 3a),
og stablecoins/BTC (punkt 3c) tælles ikke. Punkt 3b og 3d (afnotering, spotpris) anvendes først ved målingen, så tallet
er kandidater. Rækken viser mønter (af 20), meddelelser (mindst 6) og tidligste kørsel (den 20. mønts t + 7 døgn +
72 timer). U1F (ændring 17i) får en række uden tal: dens katalog læses først ved målingen. Hver række får sin egen
forklaring. Ingen kurs læses; ingen regel, lås eller alfa ændres.

### Git-opslagene bag familiegodkendelsen caches præcist (tilføjet 2026-10-24 kl. 11:42, før kode)

Målt 2026-10-24 (kopi af registret): `/api/kpis`, som dashboardet henter hvert 15. sekund, bruger 0,20 af 0,29 s på
12 git-underprocesser fra `families.blobs` (ændring 8 punkt 5: de fire bundne filers committede og arbejdskopiens
blobs). Ændring, kun hastighed, samme svar: `registry.blob_at(commit, sti)` huskes, når `commit` er en fuld sha (en
commits indhold kan ikke ændres; kun fundne blobs huskes); `registry.last_commit(sti)` huskes, så længe HEAD peger det
samme sted (nøgle: HEAD-filens indhold og stat for ref-filen og `packed-refs`; enhver commit, checkout eller pull
skifter nøglen); arbejdskopiens blob regnes stadig af `git hash-object` og huskes, så længe filens inode, størrelse,
mtime og ctime er de samme (enhver skrivning ændrer ctime). Godkendelsens binding, tærskler og registrering er
uændrede; ingen gate ændres.

### `/api/overview` og `/api/mission` bruger dashboardets trinvise kædetjek (tilføjet 2026-10-24 kl. 10:55, før kode)

Målt 2026-10-24: `/api/overview` svarer på 5,9 s og `/api/mission` på 6,2 s; profilen (kopi af registret) viser, at
94 % af tiden er `db.verify()`, der hasher alle 184 897 kæderækker igen ved hvert kald og vokser med registret.
`/api/audit` bruger allerede `web.verify_chains` (samme resultat som `db.verify()`, men kun nye rækker hashes; de
triggere, der forbyder UPDATE og DELETE, tjekkes ved hvert kald, og mangler én, gås hele kæden igennem; en baggrundstråd
går alle kæder igennem fra start hvert 10. minut; supervisoren laver stadig den fulde `db.verify()` ved start).
Ændring, efter brugerens "Fix alt" samme dag: `/api/overview` og `/api/mission` bruger den samme trinvise funktion og
den samme cache som `/api/audit`. `lab verify`, preflight, risikotjekket og supervisoren er uændrede (fuld gennemgang).
Ingen tærskel, ingen gate og ingen kæderegel ændres.

### `lab status` viser en senere afgørelse frem for en gammel PASS (tilføjet 2026-10-23 kl. 21:10, før kode)

`python3 -m lab status` viste `E_vol_managed_long_p1  REJECTED  EXPLORATORY  PASS (screen): all validation gates
passed; eligible for a human-approved sealed holdout`. Tilstanden er rigtig (brugerens afgørelse 2026-10-17 15:33,
MISSION6_FLEET_RUN.md), men kolonnen viser det seneste resultats dom, og den er den gamle screen-PASS. Dashboardet viser
allerede den rigtige grund (`last_reason`). Ændring, kun visning i CLI: når et eksperiment er i en sluttilstand
(REJECTED, RETIRED, WITHDRAWN), og resultatets dom begynder med PASS, viser `lab status` i stedet den seneste
overgangs tilstand og grund efterfulgt af "(tidligere: PASS …)". Ingen tilstand, intet resultat og ingen gate ændres.

### Eksterne poster vises ikke som kørende uden livstegn (tilføjet 2026-10-23 kl. 19:05, før kode)

Hypoteseregistret viste `X02_copybot_paper` og `X03_funding_live_v0` som RUNNING. Statussen er den importerede tekst
fra 2026-10-17 ("RUNNING outside the lab (paper.py / funding.py)"); deres datafiler (`data/paper.db`, `data/funding.db`)
findes ikke på denne maskine, så intet viser, at de kører. Ændring, kun visning: en ekstern post med resultatet RUNNING
vises kun som RUNNING, når `ops.external_freshness` (filernes ændringstid, ingen fil åbnes) har set en skrivning inden
for et døgn; ellers `UNVERIFIED` med årsagen. X01 (pm_lp, frisk fil) er uændret RUNNING. Ingen registerpost ændres.
Samme pakke: listen "Strategityper" under Godkendelser (ca. 30 skabeloner fra det lukkede katalog, næsten alle
"Afvist i test") foldes sammen som standard; "Venter på dig" står åben.

### Fremadtest mod køb-og-hold (tilføjet 2026-10-23 kl. 18:15, før kode; brugerens directive: "undersøg, om de nuværende rapporter kan give falsk optimisme")

Målt: `FWD_E_vol_managed_long_p1` står +2,79 % siden 10-18 20:15 UTC, mens lige-vægtet køb-og-hold af de 8 mønter, den
har handlet, gav +3,18 % i samme periode (Binance 1h-åbning ved start mod nu). Dashboardet viser fremadtestenes P&L
(+178–276 USD samlet) i grønt uden nogen sammenligning, så en gevinst, der er ren markedsbevægelse, ligner en fordel.
Ændring, kun visning og registrering (ingen fremadtestregel, ingen afgørelse, intet i papirregnskabet ændres):
- `lab/benchmark.py`: højst én gang i timen, for hver aktiv fremadtestkonto, lige-vægtet køb-og-hold af de mønter, kontoen
  har handlet, fra kontoens første mærkning til nu. Startprisen pr. mønt er 1h-åbningen ved start (hentes én gang og
  gemmes); nutidsprisen kommer fra ét samlet kald (`/fapi/v1/ticker/price`). Gemmes som observationer
  (`benchmark/1`, `fwd_bh_return`), så tallet kan genberegnes.
- `/api/balance` og dashboardets fremadtest-kort viser køb-og-hold i USD og forskellen (P&L − køb-og-hold).
- Ærligt: det er en tilnærmelse (de handlede mønter, ikke nødvendigvis hele universet; ingen funding/gebyr i
  benchmarket). Den afgør intet; fremadtestens egen regel (ændring 7) gælder.
- Udvidet samme dag kl. 18:25 (før kode): skyggekontoen (`SHADOW_`, kortet "Total P&L (paper)") får samme
  sammenligning, så det største tal øverst heller ikke står uden benchmark.

### Vagten måler pm_lp-dækningen (tilføjet 2026-10-23 kl. 17:55, før kode; brugerens ja samme dag: "ja til pm_lp dækning")

Indtil nu opdagede vagten kun et totalt stop (seneste snapshot ældre end 300 s). En delvis forringelse — som natten
til 2026-10-22, hvor timer lå på 32–85 % og døgnet endte på 91,4 % — blev ikke meldt, før døgnrapporten. Ny kontrol
`pm_coverage` i `lab watch`, kun læsning (`mode=ro`, samme forbindelse som kontrollen af indsamleren), højst én
gang i timen: dagens løbende snapshot-dækning = snapshots i dag ÷ (markeder i dagens panel × minutter siden 00:00 UTC),
samme tælling som `research/pm_lp.py coverage` (D1 ≥ 90 %). Under 90 % efter mindst 2 timer af døgnet er en fejl i
vagten (log, skrivebordsbesked, statusfil); gårsdagens færdige døgn vises i detaljen. Indsamleren, dens database og
holdouten røres ikke; intet genstartes.

### Før pm_lp-holdouten: watchdog og strøm (tjekket 2026-10-22)

- **Watchdog: aktiv** (brugeren 2026-10-22 17:02, med sudo). `/etc/systemd/system.conf` har `RuntimeWatchdogSec=60`,
  `/etc/sysctl.d/90-panic.conf` har `kernel.panic = 10`. Kontrol uden sudo: `systemctl show -p RuntimeWatchdogUSec
  -p WatchdogLastPingTimestamp` (1min og et tidspunkt under et minut gammelt) og `cat /proc/sys/kernel/panic` (10).
  Fryser kernen, nulstiller `iTCO_wdt` maskinen efter ca. 1 minut; collectoren og labbet starter igen (vagten ikke).
  Et frossent skrivebord med en levende kerne fanges ikke.
- **Strøm: mangler.** HP Compaq 8200 Elite USDT, BIOS J01 v02.33: ved opstart F10 → Advanced → Power-On Options →
  "After Power Loss" = **On** (eller "Previous State") → F10 gem. Kræver en planlagt genstart, som skal ske før
  2026-10-31 (fra 10-31 til 11-27 må maskinen ikke genstartes). Efter genstarten: `python3 -m lab deploy-check` og
  START_WATCH.sh for vagten.
- **Disk:** SMART PASSED 2026-10-22 (0 omallokerede sektorer, 76 % slid tilbage, 31 °C); `smartd` overvåger den.

## Ekstern sundhedskontrol og S7

- **Er den nødvendig?**
  - For pm_lp betyder et uopdaget nedbrud i holdout-perioden (10-31 → 11-13) direkte tab af dækning. Mindst 90 %
    kræves.
  - En kontrol fra en anden maskine er derfor værdifuld i den periode, men den er ikke nødvendig for at studiet er
    gyldigt.
- **Er den tilladt?**
  - S7 omfatter planlagt automatisering (`ENGINE_PROPOSAL.md` §10, `lab/README.md`). Den er derfor ikke installeret.
  - Den stående regel er: ingen planlagte opgaver eller permanent automatisering, før S7-gaten er åben (7 rene dage)
    og du har godkendt det.
  - Det gælder også en tjeneste, timer eller autostart for vagten.
  - Vagten er tilladt nu, fordi den startes i hånden, kun læser og aldrig genstarter noget.
- **Når S7 er åben og du har godkendt det**, er den understøttede kontrol: `ssh anton@192.168.1.108 'cd
  ~/ecommerence/copybot && python3 -m lab watch --once'`. Exit-koden 0 betyder, at alt kører.
- **Genstart 2026-10-23 viste hullet (tilføjet samme dag kl. 15:23, før kode).** Pc'en frøs ca. 15:05 og blev
  slukket. Efter opstarten 15:09 kørte kun pm_lp-indsamleren (systemd, linger). Laboratoriet og vagten kom ikke op:
  der findes ingen autostart for dem, med vilje (reglen ovenfor). Laboratoriet blev startet i hånden 15:16; vagten
  venter på brugerens ja. S7 talte ikke udfaldet (huller under 2 t tolereres): 4,11 af 7 dage.
  **Forberedt, ikke installeret:** `lab/automation/s7_install_linux.sh` med to systemd-brugerenheder
  (`copybot-lab.service`, `copybot-watch.service`), Linux-udgaven af `s7_install_task.ps1`. Scriptet afviser og
  installerer intet, medmindre `python3 -m lab gate --require` slutter med 0 (S7 åben). Det slår enhederne til ved
  næste opstart (`enable`, ikke `--now`), så det aldrig starter en ekstra flåde ved siden af en kørende.
  - `copybot-lab.service` kører `START_LAB.sh` ved opstart (efter linger, før login) og genstarter **ikke** efter et
    nedbrud (`Restart=no`): som i dag skal et menneske se årsagen (START_LAB.sh: "Intet genstartes automatisk").
    START_LAB.sh's kodevagt og preflight gælder uændret; `lab.lock` forhindrer to flåder.
  - `copybot-watch.service` kører `START_WATCH.sh` og genstartes efter 60 s, hvis den dør (den læser kun og
    genstarter aldrig noget; `watch.lock` forhindrer to vagter).
  - Ventetid på navneopslag før start som i pm-lp-collector.service (højst 10 min).
  - **Rettelse (Mission 14; skrevet 2026-10-26 kl. 13:55 lokal, før kode).** Målt ved opstarten 2026-10-26: systemd
    afbryder `ExecStartPre` efter `TimeoutStartSec` (standard 90 s, `TimeoutStartUSec=1min 30s`), så "højst 10 min"
    var i praksis 90 s. Indsamleren klarede det, fordi `Restart=on-failure` startede den igen 60 s senere
    (NRestarts=1). `copybot-lab.service` har `Restart=no`: med langsomt netværk ved opstart ville laboratoriet aldrig
    være startet. Den forberedte (ikke installerede) `copybot-lab.service` får `TimeoutStartSec=15min` (120 × 5 s
    venten plus navneopslagenes egne timeouts); intet andet ændres, og intet installeres eller startes.
    `copybot-watch.service` har ingen `ExecStartPre` og ændres ikke. Indsamlerens installerede tjeneste røres ikke
    (pm_lp-reglen); den samme linje dér er brugerens beslutning og virker først ved næste start
    (`daemon-reload`, ingen genstart).
  - Fortryd: `systemctl --user disable copybot-lab copybot-watch` og slet de to filer.
  - Installation kræver begge dele: S7 åben og brugerens ja (brugeren kører scriptet selv).
- **Installeret af brugeren 2026-10-26 kl. 14:04:19 lokal; audit (Mission 15; skrevet 2026-10-26 kl. 14:14 lokal,
  før kode).** Målt: journalen viser `daemon-reload` og `enable` fra brugerens egen `systemctl` 14:04:19–14:04:20 (ikke
  Claude). `~/.config/systemd/user/copybot-{lab,watch}.service` er byte for byte lig `lab/automation/` i 111c037 (med
  `TimeoutStartSec=15min`); begge `enabled`, `inactive`. pm-lp-collector uændret (pid 1495, NRestarts=1, filen fra
  10-19). Prøvekørsel af scriptet mod en tom mappe med en falsk `systemctl`: gaten OPEN, to filer kopieret, kun
  `daemon-reload` og `enable copybot-lab copybot-watch`; anden kørsel afviser med exit 3 og ændrer intet.
  `systemd-analyze --user verify` uden fejl.
  - **Hvad scriptet gør:** opretter de to unit-filer og to symlinks i `default.target.wants/`, kører `daemon-reload`
    (genindlæser alle brugerenheder; genstarter ingen) og `enable` uden `--now`. Starter intet nu. Rører ikke
    pm-lp-collector, data, databaser, FAIL_CLOSED eller pauser. `lab gate --require` åbner `lab.db` med den almindelige
    forbindelse (`CREATE ... IF NOT EXISTS`, ingen rækker skrives).
  - **Ved opstart:** begge starter parallelt med indsamleren (ingen `After=` mellem dem; de er uafhængige). Laben venter
    højst 10 min på DNS og kører derefter `START_LAB.sh` uændret: kodevagt, preflight (`PREFLIGHT OK` krævet),
    `lab.lock`. FAIL_CLOSED og pauser ligger i databasen og gælder som ved start i hånden. Ingen nøgler eller tokens
    (paper, offentlige API'er).
  - **Dobbelte processer:** `lab.lock`, `watch.lock` og preflight afviser en ekstra flåde/vagt. Laben (`Restart=no`)
    forbliver da `failed`. Vagten (`Restart=on-failure`, `StartLimitIntervalSec=0`) prøver igen hvert 60 s, så længe
    en anden vagt holder låsen (én loglinje i minuttet), og overtager, når den anden dør. Sker kun, hvis nogen starter
    `copybot-watch` med hånden, mens en håndstartet vagt kører. Installér aldrig også `research/systemd/lab-watch.service`
    (punkt G): det ville være to tjenester om samme lås; `copybot-watch.service` erstatter den.
  - **Forskelle fra start i hånden:** (1) Stopper flåden uventet, afslutter `START_LAB.sh` med fejl, og systemd stopper
    hele enhedens cgroup, også dashboardet (i hånden blev dashboardet stående og viste "offline"). Vagten melder begge.
    (2) Uden skærm åbner `xdg-open` tekstbrowseren `lynx`, som afslutter straks på /dev/null; målt: exit 0, kun
    terminalkoder i `start.log`. (3) Ved nedlukning får alle processer i enheden SIGTERM (jobs afbrydes som ved
    nedlukning i dag, ændring 6).
  - **Deploy efter installationen:** `lab stop` afslutter `START_LAB.sh` med 0, enheden bliver `inactive`, og en start
    med `setsid nohup ./START_LAB.sh` kører uden for systemd til næste opstart. Det virker; næste opstart bruger
    tjenesten igen. Den håndstartede vagt (pid 2845) kører til næste opstart.
  - **Rollback:** `systemctl --user disable copybot-lab copybot-watch`, `rm ~/.config/systemd/user/copybot-{lab,watch}.service`,
    `systemctl --user daemon-reload`. Stopper ingen kørende proces.
  - **Ikke bevist:** at enhederne faktisk starter ved en rigtig opstart. Det kræver en genstart (brugerens beslutning;
    tidligst efter en `system.alive`-post og uden for K3-vinduer, og senest 2026-10-30, før pm_lp-perioden).
    Forventet efter opstart: `systemctl --user is-active copybot-lab copybot-watch` = active, `python3 -m lab watch
    --once` exit 0 med `host` booted få min siden og `watcher` = tjenestens MainPID, `deploy-check` DEPLOY OK.
- **`deploy-check`: ingen falsk grøn vagt (Mission 15; skrevet 2026-10-26 kl. 14:14 lokal, før kode).** I dag tæller
  rækken `watcher running` enhver proces med `python3 -m lab watch` i kommandolinjen, også en `--once`-kontrol og en
  hængt vagt. Rettelse: `--once`-processer tælles ikke, og en ny række `watcher heartbeat fresh` kræver, at
  `data/lab/watch.heartbeat` er højst 120 s gammel og nyere end opstarten (samme grænse som `watch --once`). Kun
  skærpelse; intet startes eller stoppes.
- **Testplan: S7-testgenstart (Mission 16; skrevet 2026-10-26 kl. 14:28 lokal). Udføres KUN efter brugerens ja.**
  - **Tidspunkt:** tirsdag 2026-10-27 kl. 12:40 UTC (13:40 dansk tid). Reserve: onsdag 10-28 eller torsdag 10-29 samme
    klokkeslæt; aldrig fredag efter 12:00 UTC, i weekenden eller fra 10-31. Begrundelse: K3-vinduerne ligger om hver lige
    time ± 35 min (00/04/08/12/16/20 UTC rigtige, 02/06/10/14/18/22 UTC placebo), så 12:35–13:25 UTC er frit. Kl. 12:40
    er efter K3's 12:00-vindue og 12:02-scanningen, og selv den værste ventetid på netværket (15 min) er overstået før
    papirmærkerne kl. 13:00, scanningen kl. 13:02 og næste K3-vindue kl. 13:25. Ingen daglige jobs (00:00, 00:30), ingen
    weekend-timer (K1/K2) og ikke FOMC-aftenen 10-28.
  - **Forventet hul (målt ved opstarten 2026-10-26):** kerne + userspace 19 s; netværket globalt 108 s efter kernen
    (kablet forbindelse); indsamlerens DNS-ventetid afbrydes efter 90 s og startes igen efter 60 s (første snapshot
    ca. 3,5 min efter kernen); BIOS og nedlukning ca. 1 min. Derfor: vagt ca. 2 min, lab ca. 3–4 min, pm_lp ca. 5 min
    (ca. 5 snapshot-runder af 1.440 den dag, før holdout; D1 måles først fra 10-31). K3, K1/K2, papirmærker, daglige
    jobs, R3 og sim_exec: intet tab forventet. Et afbrudt job lægges tilbage i køen (ændring 6).
  - **Før (fra `~/ecommerence/copybot`, T−10 min):** `date -u`; `python3 -m lab watch --once` (exit 0);
    `python3 -m lab deploy-check` (DEPLOY OK); `systemctl --user is-enabled copybot-lab copybot-watch pm-lp-collector`
    (enabled ×3); `sha256sum ~/.config/systemd/user/copybot-{lab,watch}.service` (begynder e3efa4906df6432b og
    0629c087f0e00575 = 111c037/6b02c19); `python3 -m lab jobs --status running` (running 0); `python3 -m lab gate`
    (OPEN); `python3 -m lab health` (FAIL_CLOSED: no). Noter K3 `valid_rounds` fra `/api/research` og de aktive pauser
    (2026-10-26: kun den pensionerede `LANE_4c87acd9ce`, spread_anomaly 10-19).
  - **Genstart (brugeren, i en terminal på skrivebordet):** `python3 -m lab stop --reason "S7-testgenstart"` og derefter
    `systemctl reboot`. Log ikke ind de første 5 min (så beviser opstarten, at enhederne starter før login), og tryk
    ikke på tænd/sluk-knappen ved login-skærmen (logind slukker).
  - **Efter (T+5 min; laben har højst 15 min til DNS + preflight, derefter er det en fejl):**
    1. `systemctl --user is-active copybot-lab copybot-watch pm-lp-collector` → active ×3;
       `systemctl --user show copybot-lab copybot-watch -p MainPID -p ActiveEnterTimestamp` → start før login.
    2. `python3 -m lab watch --once` → exit 0; `host` booted få min siden; `watcher` pid = copybot-watch's MainPID;
       `lab` puls; `scanner` OK (flåden scanner ved start); `collector` snapshot nyere end opstarten; `paper` "not judged
       yet" de første 1,5 t (forventet).
    3. `python3 -m lab deploy-check` → DEPLOY OK (inkl. `watcher heartbeat fresh`).
    4. Hændelser: `system.host_boot`, `system.startup` med `fail_closed: false`, `scanner.gap` (forventet 0 timer).
    5. pm_lp: `systemctl --user show pm-lp-collector -p MainPID -p NRestarts`, ny `runs`-række med HEAD, hul i `snaps`.
    6. K3: `valid_rounds` uændret; lå genstarten i et vindue, skal den runde stå `ugyldig` i auditten (aldrig udfyldt).
    7. `python3 -m lab health` → FAIL_CLOSED: no; samme aktive pauser som før (ingen ryddet, ingen ny).
    8. `journalctl -b -1 | grep "System is rebooting"` (ren nedlukning) og `journalctl --user -b -u copybot-lab -u
       copybot-watch` (ingen fejl).
  - **Rollback:** laben ikke active efter 17 min → læs `journalctl --user -b -u copybot-lab` og `data/lab/start.log`,
    start i hånden med `(setsid nohup ./START_LAB.sh >> data/lab/start.log 2>&1 < /dev/null &)`; vil man helt tilbage:
    `systemctl --user disable copybot-lab copybot-watch`, `rm ~/.config/systemd/user/copybot-{lab,watch}.service`,
    `systemctl --user daemon-reload`, og start laben og vagten i hånden som før. Vagten genstarter i ring → `systemctl
    --user disable --now copybot-watch`, start i hånden. Indsamleren ikke active → `systemctl --user start
    pm-lp-collector` (punkt C; aldrig START_PM_LP.sh i hånden).
  - **Kan ikke bevises af kommandoer:** at maskinen faktisk genstarter (brugeren), skrivebordsnotifikationen,
    dashboardet i browseren (F12; værten har ingen JS-motor). Claude-sessionen dør med værten og fortsættes med
    `claude --continue` efter login.
  - **Udfald 2026-10-27 (skrevet kl. 14:14 lokal): testen blev aflyst, ingen genstart.** Preflight kl. 12:25 UTC var
    grøn (enheder enabled med de rigtige sha256, pm_lp aktiv, 0 job, FAIL_CLOSED nej, netværk 200 på under 1 s). Laben
    blev stoppet kl. 12:38 UTC, men værten blev ikke genstartet (`uptime -s` uændret 2026-10-26 12:25:50 UTC). Ved fristen
    kl. 13:10 UTC blev laben startet i hånden efter rollback-planen (13:11 UTC, DEPLOY OK) før K3-placebovinduet kl.
    13:25 UTC. Hul for fleet/web: 33 min; vagt og pm_lp kørte hele tiden. S7-enhederne er stadig enabled og ubevist;
    reserven er onsdag 10-28 eller torsdag 10-29 kl. 12:40 UTC, kun efter brugerens nye ja.
- **Agenternes sundhed bygger på udført arbejde, ikke på puls (tilføjet 2026-10-23 kl. 15:34, før kode; brugeren bad
  om, at en kørende proces eller en frisk puls aldrig fremstår som sund uden nyligt arbejde).** I dag dømmer både
  dashboardet (`status`) og vagten (`agent:<navn>`) kun ud fra pulsen og `ok`-flaget: en periodisk agent, hvis gennemløb
  udebliver eller fejler, men som stadig sender puls, vises som sund. Nyt felt `health` pr. agent i `/api/agents`, med
  grund (`health_reason`) og forventet interval:
  - `STALE`: pulsen er gammel, eller en periodisk agents seneste vellykkede gennemløb er ældre end 3 intervaller (mindst
    10 min) — grænsen følger agentens eget interval (premium-watch 60 s, news-watch 600 s, scanner 3600 s …).
  - `FAILED`: status fejlet, eller seneste fejl er nyere end seneste succes.
  - `BLOCKED`: status blokeret, eller en jobagent har kørbare jobs, men intet job er lykkedes i 30 min.
  - `HEALTHY`: periodisk agent med vellykket gennemløb inden for grænsen; jobagent, der kører et job eller har arbejde.
  - `IDLE`: jobagent uden kørbare jobs af sine typer (venter legitimt).
  - `UNKNOWN`: periodisk agent uden registreret succes.
  Vagten får samme dom for periodiske agenter: intet vellykket gennemløb inden for grænsen er en fejl, også med frisk
  puls. Dashboardets agentliste viser `health` og grunden. Ingen gate, ingen beslutning og ingen genstart ændres.
- `python3 -m lab research-memory [--json FIL]` (tilføjet 2026-10-23 kl. 15:47, før kode; brugeren bad om en
  læringsløkke: for hver afgjort hypotese hypotese og låst protokol, data og dataversion, resultat og usikkerhed,
  omkostninger og baselines, afvisningsgrund, og hvilken ny evidens der kan retfærdiggøre en gentest). Kun læsning af
  registret; samler, hvad der allerede er registreret: låste målinger (`research.measurement`: lås-sha256, alfa, n,
  middel og p pr. fase, antal datafiler og en samlet sha256 over deres sha256'er), katalog- og familieeksperimenter
  (`results`: protokolversion, dom, fejlede gates, Sharpe/DSR, omkostningsmodel) og screeningen (17: dom og årsag).
  Gentestbetingelsen er en fast regel pr. slags, aldrig et nyt kriterium: låst måling → kun en ny dateret ændring med et
  fremadvindue efter låsen (2022–2023 er brugt, 2024 er holdout, 2025+ er reserveret); katalogskabelon → kataloget er
  lukket (ændring 8), kun som familie; screening FAIL → explore0 er brugt; UNTESTABLE → ≥ 15 hændelser med data.
  Fanget ved bygningen: H5 (16c) står som PASS på validation3 (n 26), mens min statusrapport sagde "0 af 4"; det tal
  gjaldt kun ændring 17's screening. Den ændrer intet og afgør intet; ingen holdout læses.
  Rettet samme dag kl. 18:40 (før kode): en screenings-PASS, som en låst måling siden har afgjort (4 nøgler), henviser
  nu til målingens afgørelse i stedet for reglen "en LÅS-17-lås, så afgør målingen".

- **2026-10-24 kl. 17:44 (før kode): forskningshukommelsen tager også de committede screeninger med (ændring 21c og 21f).**
  `python3 -m lab research-memory` læste kun registret, men m21c og m21f er registreret som committede filer
  (`research/studies/MOVESCREEN_m21c.json`, `DISCOVERY_m21f.json`). Uden dem kunne en ny idé blive afprøvet igen under
  et nyt navn. Nu læses `research/studies/*_m21*.json`: hver nøgle med dom, n hændelser, n klynger, gennemsnit, p,
  omkostningskrav, fejlede tjek, sha256 af hændelserne og filen. Gentestreglen er den samme faste regel pr. dom som
  ændring 17's screening. Kun læsning; den ændrer og afgør intet.

- **2026-10-24 kl. 22:23 (før kode): dashboardet får en markedsscanner som hovedvisning (`/api/markets`).**
  - **Kilde:** kun registret (skrivebeskyttet), ingen nye datakilder og ingen beregning, der kan afvige fra
    detektoren. Pr. marked på ændring 21's liste vises den seneste scanning fra `abnormal_move`'s egne observationer:
    - kurs og afkast 1 t og 24 t med z;
    - volumenforhold mod 720 t-medianen;
    - præmie (mark − indeks);
    - bogens rundtur for 5 000 USD og spread;
    - weekend- og helligdagstid (`off_hours`);
    - dataalder;
    - flag med tærskel og regel fra målelogen.
  - **Sparkline:** de seneste 48 markedstimers lukkekurser, én pr. `open_s`, med den tidligste scanning af timen.
  - **Undersøgelse:** den seneste analysepost (`opportunity.move`) med triage, forklaringer, næste skridt og
    nyheder.
  - **Status:** "frisk" (scanning ≤ 75 min gammel), "forældet" (ældre) og "fejl" (fejl eller for kort historik i
    seneste scanning).
  - **Ingen påstand om realtid:** visningen siger "opdateres hver time kl. HH:02 UTC". Et flag vises som en
    observation, aldrig som en handelsmulighed.
  - **Filtre og sortering** i browseren (alle, krypto, TradFi, kun flaggede; |z|, volumen, præmie, bogomkostning,
    dataalder). Ingen tal er hardcodede: tomme og forældede data vises som sådan.
  - Ingen tærskel, scanneradfærd eller beregning ændres.

- **2026-10-24 kl. 22:27 (før kode): omkostningsopdeling for alle papirkonti, med kontoens egen kapital.**
  - `lane.decomposition` regnede netto mod konstanten `CAPITAL` (10 000). Alle 25 konti har i dag kapital 10 000, så
    intet tal er forkert. En konto med anden kapital ville dog få forkert opdeling; nu bruges kapitalen fra kontoens
    `paper.started`.
  - Opdelingen (funding, gebyrer, spread/slippage med målt bog og modelleret tillæg, pris/basis, den uafhængige
    kontrol fra 21t) beregnes også for fremadtests og shadow-konti i `/api/paper2` og vises i papirpanelet. Tallene
    er de samme fills og funding, som ledgeren bruger; ingen ny formel for netto.
  - **Fund kl. 22:27 (21t-kontrollen på en kopi af registret):** 4 ikke-bane-konti (SHADOW_E_mvrv_value_p3,
    FWD_E_vol_managed_long_p1, FWD_E_xs_betting_against_beta_p2, FWD_E_xs_max_lottery_p2) har en afvigelse på
    ~±10 USD og hver 1 fill efter seneste mark. Opdelingen tog netto fra den seneste mark, men gebyrer, spread og
    funding fra **alle** fills og afregninger. Komponenterne passede altså ikke til netto, når et fill lå efter marken.
    **Rettelse:** fills og funding skæres ved markens tid (ts ≤ mark). Senere fills tælles i `fills_after_mark`, og
    den næste mark tager dem med. Ingen ledger, kasse eller equity ændres; kun den viste opdeling.

- **2026-10-24 kl. 22:28 (før kode): forskningspipeline og kapacitet i dashboardet (`/api/research`).**
  - **Kilder, kun læsning:** research-memory (låste målinger, katalog- og familieeksperimenter, ændring 17's
    screeninger og de committede m21-studier) og de fremadrettede tests' tællere (`coverage.forward`).
  - **Visning:** trin (opdaget → undersøgt → hypotese → protokol → screening → validering → papir/skygge →
    overvågning) med antal pr. trin. Hver hypotese har sin dom med den eksisterende status: PASS, SCREEN_FAIL, REJECTED,
    UNTESTABLE, DROPPED, OBSERVATION osv., aldrig slået sammen. Desuden n, klynger, effekt, p, omkostningskrav, årsag og
    den faste gentestregel.
  - **Kapacitet:** status pr. papirkonto er `UNTESTABLE_CAPACITY` med grunden fra
    `research/drafts/SYSTEMKORT_OG_RISICI_2026-10-24.md`. Ingen kurve eller break-even vises, før en dateret ændring
    og brugerens ja foreligger.
  - Ingen status ændres, og intet genåbnes.

- **2026-10-24 kl. 23:11 (før kode): "war room" i dashboardet (master mission 3).** Kun visning og læsning; ingen
  gate, omkostningsregel, tærskel eller status ændres.
  - **Audit før kode (skrivebeskyttet):**
    - 41 `agent.error` fra paper-1 (FileNotFoundError) ligger alle 2026-10-18 kl. 09:40–10:22 UTC og er ikke
      gentaget.
    - premium-watch havde 10 netværksfejl 10-22.
    - De 20 `worker.heartbeat_stale` det seneste døgn er "from previous run", én pr. opstart (dagens deploys).
    - Ingen aktiv fejl.
    - P&L-identiteter på alle 25 konti: realiseret + urealiseret = total, opdelingens netto = total, afstemning OK.
      0 brud.
  - **Hændelser (`/api/events`, nyt):** én liste over de seneste 72 timer fra eksisterende registreringer:
    - `opportunity.move`: hvad, bevægelsestime, hvornår Copybot vidste det (scan-ts), berørte markeder (andre
      overvågede markeder med |z_1h| ≥ 2 i samme scan), flag og værdier, nyheder og makro i vinduet, triagens
      alternative forklaringer og dom, og næste skridt fra triagen;
    - `risk.pause` (datapauser);
    - on-chain-revisioner (`flow_revision`);
    - kapacitetsfejl (tomme bøger).
    Nyheder vises som tidsmæssigt sammenfald, aldrig som årsag. Mangler en kilde, står det. "Aktuel" = højst 6 timer
    siden Copybot kendte til hændelsen.
  - **Scanner:**
    - seneste forudsagte funding pr. marked fra `pricing_constraint/2` (`predicted_funding`), med alder;
    - en datakvalitetsmærkning (frisk scan, bog uden fejl, ingen `history_short`/`error` i seneste scan);
    - forskningsstatus fra seneste undersøgelse (triagens dom eller "ingen flag").
    Sortering efter signal kan ikke placere en række med dårlig datakvalitet over en med god: dårlig kvalitet sorteres
    sidst i signal-sorteringen.
  - **Monitorhistorik (21w):** M1, M2, M4 og M5 rekonstrueres as-of slutningen af hvert af de seneste 14 afsluttede
    UTC-døgn fra de append-only tabeller, med ts ≤ as-of i hver forespørgsel. M3 bygger på `lane.decomposition`, som
    ikke er as-of, og vises kun for nu. Det står i visningen. Samme regler og tærskler som 21w.
  - **Økonomi og kapacitet:** egne paneler fra `/api/paper2` og `/api/research`.
    - Samlet sum kun for P&L og omkostninger, ikke for equity.
    - Hvert tal mærket: bogført simuleret, nutidig likviditetsmåling eller utilstrækkelige data.
    - Kapaciteten deles i likvide og tynde bøger. Tomme og censurerede bøger vises som sådan.
  - **Animation:** kun en kort markering af et nyt flag eller en ny hændelse og glidende talskift. Slås fra ved
    `prefers-reduced-motion`. Data ældre end markedsscannerens grænse vises dæmpet med "forældet".

## 2026-10-25 kl. 10:33 — natten efter 85db130: netværk, afregnet funding og weekenddækning (målt, read-only)
- **Netværk:** data_fetch-pauser i 9 episoder 2026-10-18..25. 7 af dem ligger kl. 00:00–04:31 UTC (natlige udfald på
  værten eller linjen; årsag ukendt). Minutserien viser, at de fleste varede under 2,5 min. Natten til 10-22 havde
  huller på op til 31 min. 03:30-udfaldet i nat: pauser på 3 konti, ophævet automatisk 04:23 UTC efter ændring 18.
  Selve udfaldet gav intet hul over 150 s i minutserien. Ingen ændring af pausereglen (21z E); det kræver brugerens ja.
- **Afregnet funding (21y B), audit af alle 31 rækker:**
  - hver (marked, afregningstid) gemt præcis én gang;
  - alle tider på 4- eller 8-timersgitteret;
  - hentet 144–154 s efter afregningen;
  - `value` = `rate`;
  - alle ≥ START.
  Hver afregning, som scannerens egen forudsagte `next_funding_ts` pegede på, findes. Ingen mangler og ingen ekstra.
  Råvarer afregner hver 4. time; BTC, ETH, SPY, QQQ og USDBRL hver 8. time. Alle 27 TradFi-afregninger var præcis 0.
  Forudsagt (seneste scan før) og afregnet BTC/ETH ligger inden for ca. 0,002 % af hinanden. Det siger intet om en
  fordel og bruges ikke som evidens.
- **Weekenddækning (21z):** ingen crontab og ingen systemd-timere hos brugeren. Laben har ingen autostart (S7, røres
  ikke). En genstart af værten i en weekend kan derfor koste hele weekenden. Den risiko kan kun brugeren fjerne.

## 2026-10-25 kl. 13:01 — vagten får komponenten `scanner` (brugerens ja 2026-10-25 ca. kl. 12:50, før kode)
Brugeren valgte "Vagt: scanner-alarm" (byg, test og genstart vagten én gang). Gennemføres efter
`research/drafts/OVERVAAGNING_UDKAST_2026-10-25.md` punkt A og testkriterierne der. Kun læsning (mode=ro); vagten
starter, stopper og genoptager intet. Laben, pm_lp-collectoren, pauseregler og FAIL_CLOSED røres ikke.
- **Bedømmes kun, når laben kører**, og fleeten har kørt i mindst 5 min. Ellers dømmer komponenten `lab` allerede.
- **Nede**, når:
  - seneste `abnormal_move/1`-scanning er over 70 min gammel;
  - det er lørdag–søndag UTC, klokken er ≥ HH:12, og timens scanning mangler (K1/K2, 21y);
  - en K3-runde (ændring 22) er nået S − 30 min til S + 35 min uden `selection` eller `missed`.
- **Fail-closed:** kan databasen ikke læses, er komponenten nede, aldrig ok.
- **Alarmering:** via vagtens eksisterende kanal (log, statusfil og skrivebordsnotifikation), påmindelse højst hver time.

- **2026-10-28 kl. 17:05 lokal (Mission 25, kun læsning): værten er gået ned uden nedlukning 5 gange på 9 døgn.**
  `journalctl --list-boots`: opstarterne, der sluttede 2026-10-20 23:24, 10-21 12:47, 10-23 15:07, 10-26 12:39 og
  10-28 03:26 (lokal), har ingen `systemd-shutdown`-linje (10-19's to stop var rene). Ingen MCE-, I/O-, ATA-, EXT4- eller
  OOM-linjer før nogen af dem. De tre sidste sluttede med smartd-linjen "Airflow_Temperature_Cel changed from 71 to 72",
  "76 to 74" (10-23 14:02, sidste aflæsning) og "69 to 70". Disken er en Samsung SSD 830 (`/sys/block/sda/device/model`,
  ikke-roterende); attribut 190 er dens egen temperatur, i dette døgn op til 76 °C. CPU'en er 49–54 °C (coretemp; høj
  80 °C). 10-28-stoppet kom tilbage efter 4 min uden et menneske (03:26 → 03:30). **Ikke bevist:** at varmen er
  årsagen; mønstret (stop uden spor ved 69–76 °C) passer på en SSD, der hænger ved overophedning. K3-runden
  2026-10-26 12:00 UTC er ugyldig af netop det stop (udgangsmålinger mangler; tælles, erstattes ikke).
  **Ejerhandling:** bedre køling/luftgennemstrømning til SSD'en (støv, blæser, plads omkring kabinettet) før
  pm_lp-fristen 10-31 → 11-27, hvor der ikke må genstartes; et stop i den periode koster pm_lp-dækning.
