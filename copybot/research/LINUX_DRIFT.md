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
- Kontrollér en start med `pgrep -af "research.pm_lp|lab (fleet|web|watch)"`. Kontrollér også, at
  `data/lab/watch_status.json` får nyt tidsstempel hvert halve minut.
- Status nu: `python3 -m lab watch --once` (exit 0 = alt kører) og `python3 -m lab health`.

## Dvale

**Målt kl. 14:04 UTC: dvale er blokeret.**
- Du startede blokeringslinjen nedenfor på skrivebordet kl. 14:03:34 UTC (pid 225567, session 2, `setsid nohup`).
- `systemd-inhibit --list` viser `copybot ... sleep:idle ... block`.
- Vagten kontrollerer det hvert halve minut (komponenten `awake`, læser logind) og melder, hvis blokeringen
  forsvinder, fx efter en genstart.
- Før det, kl. 12:44 UTC, var der ingen blokering. Der var kun "delay"-inhibitorer, `IdleAction=ignore`, og kernen
  havde talt 0 dvaler siden opstart.
- XFCE står på standard bortset fra tænd/sluk-knappen ("spørg"). Standard for "dvale ved inaktivitet" er ikke
  aflæst; med blokeringen er det ligegyldigt.
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
- Skal køres igen efter hver genstart af maskinen og efter log-ud af skrivebordet. Vagten minder om det.
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

- Alt stopper, og **intet starter af sig selv.** Det er bevidst: autostart er S7-automatisering.
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
