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
