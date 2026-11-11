# Nedbrudstriage: otte urene stop 10-20 → 11-10 (direktørordre 84)

Skrevet 2026-11-11 kl. 17:41 lokal (CET = UTC+1; før 10-25 CEST = UTC+2). Kun læsning, uden sudo og uden netværkskald.
Intet er stoppet, genstartet eller konfigureret. Bygger videre på `research/desk/INCIDENT_2026-11-09.md` og
`research/LINUX_DRIFT.md` (Mission 25, 2026-10-28).

Kilder: `journalctl --list-boots`, `-b -N` og `-k`, `last -x`, vagtens "no watcher tick from … to …" og "host booted at"
(`data/lab/watch.log`, tick hvert 30. s), mtime på de sidste filer, der nåede disken, smartd's attributlog
(`/var/lib/smartmontools/attrlog.*.csv`, kan læses af alle, hver 30. min siden 10-22 17:02), `sensors`, UDisks2, `free`
og `MAX/MIN/COUNT` i `lab.db`. Værten er en HP Compaq 8200 Elite USDT (ultraslim med ekstern strømforsyning) med
i5-2400S, BIOS J01 v02.33, Samsung SSD 830 på 64 GB og 15,9 GB RAM uden ECC. Kernel 6.12.113 har kørt siden 10-18.

## 1. Tabel pr. stop

"Frys" er sidste vagt-tick + højst 30 s. "Boot" er kernens starttid (UTC). "Nede" er tiden fra sidste tick til boot.

| # | Lokal (dag) | Frys UTC | Oppetid før | Sidste linje i journalen | Boot UTC | Nede | Watchdog | Menneske ved boot | Aktivitet før |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 10-20 23:25 (tir) | 21:25:08 | 29,5 t | 23:24:44 xfconfd start | 21:47:05 | 22 min | nej (fra 10-22) | ja (login 23:47) | Firefox, Claude-app, lane_review-filer (én på 0 byte) |
| 2 | 10-21 13:05 (ons) | 11:04:50 | 13,3 t | 12:47:30 xfconfd start | 11:19:33 | 15 min | nej | ja (13:20) | Firefox, Claude-app, Claude CLI |
| 3 | 10-23 15:08 (fre) | 13:07:56 | 49,8 t | 15:07:08 timedated (252 rtkit-linjer = lyd) | 13:09:32 | 1,6 min | ja | ja (15:11) | headless Firefox-benchmark og brugerens Firefox |
| 4 | 10-26 12:51 (man) | 11:50:38 | 70,7 t | 12:39:47 smartd | 12:23:25 | 33 min | ja, men ingen reset | ja (power key 12:25) | Claude-app (GPU-cache skrevet 12:47) |
| 5 | 10-28 03:28 (ons) | 02:27:41 | 38,0 t | 03:26:03 smartd | 02:29:51 | 2,2 min | ja | **nej** (login 13:49) | Firefox, Claude CLI (MCP-log 03:26:45) |
| 6 | 10-30 18:20 (fre) | 17:19:57 | 62,8 t | 18:17:01 cron | 17:21:36 | 1,7 min | ja | **nej** (login 11-01) | Chrome og Firefox; NTP-timeouts 18:11 |
| 7 | 11-09 17:24 (man) | 16:23:26 (sidste fil 16:23:36) | 239 t | 17:21:39 dashboard | 16:27:06 | 3,7 min | ja | ja (login 17:32) | fuld testsuite med normal prioritet, Chrome, Firefox, Claude CLI |
| 8 | 11-10 23:03 (tir) | 22:02:45 (sidste fil 22:02:58) | 29,6 t | 23:02:52 collector exit | 22:04:15 | 77 s | ja | **nej** (login 11-11 14:10) | Chrome (Canva), laben, collector i genstartsløkke; ingen Claude-session |

Watchdoggen (`RuntimeWatchdogSec=60`, iTCO_wdt) blev slået til 2026-10-22 17:02 med `daemon-reexec` og har været
aktiv i hver boot siden. SSD'ens tællere for tænd (attr 12) og usikker slukning (attr 235) steg med 1 ved stop 3–6 og 8,
men med **3** ved stop 7. Der var kun én Linux-boot.

## 2. Dokumenteret (målt)

- **Intet spor i nogen af de otte stop:** ingen nedlukning og ingen linjer om MCE/EDAC, OOM, I/O, ATA, EXT4, hung
  task, soft/hard lockup, termisk throttling, GPU-hang eller panic. Kernen logger i hele boot'en næsten kun
  `perf: interrupt took too long`, USB-tastatur/-mus og to gange `i915 Atomic update failure` timer før stop 1 og 4,
  ikke ved stoppene. `xfdesktop` segfaultede timer før stop 5 og 7. `/sys/fs/pstore` kræver root.
- **Den sidste linje i journalen betyder intet.** Journalen er tynd (14–310 linjer i timen før hvert stop). De sidste
  linjer er af seks forskellige slags, og fem af dem ligger 1,6–17 min før frysningen. Vagt-tick og filernes mtime er
  derfor bedre ure.
- **Tidspunkt på døgnet:** 03:28, 12:51, 13:05, 15:08, 17:24, 18:20, 23:03 og 23:25 lokal. Der er ingen klynge, og
  stoppene falder ikke sammen med cron (:17), K3-timer eller timeskift.
- **Oppetid før stop:** 13–239 t med median ca. 44 t. Der er ingen fast tæller. I snit kommer et stop hver 2,8 dag;
  den længste rolige periode var 10-30 → 11-09.
- **Watchdog-mønster:** når watchdoggen var aktiv og intet menneske greb ind (stop 5, 6 og 8), var værten nede i
  77–130 s fra sidste tegn på liv til kernestart. Det svarer til watchdoggens 60 s plus firmware. Stop 3 passer også
  (66–96 s), selvom noten fra 10-23 siger, at brugeren slukkede. Watchdoggen nulstiller kun, når systemd (PID 1) holder
  op med at pinge. **Altså stod hele systemet stille, ikke kun skrivebordet eller en app.**
- **Stop 4 (10-26) bryder mønstret:** 33 min uden automatisk reset, selvom watchdoggen var aktiv. SSD-tælleren steg kun
  med 1.
- **SSD-varme er afkræftet:** den rå temperatur (attr 190) var 22–30 °C ved stoppene. Siden 10-22 har den ligget mellem
  15 og 33 °C (snit 24,8). Tallene 69–78 i smartd-linjerne er normaliserede (100 − °C). UDisks2 viser 300,15 K = 27 °C
  nu. SMART er rent: attr 5 og 187 er 0, og attr 199 er uændret 1.
- **Nu:** CPU-pakken er 51 °C (høj 80, kritisk 86), load 1,0, 13 GiB RAM ledig, swap ubrugt. CPU-temperatur, RAM og
  load bliver ikke logget over tid, så værdierne ved stoppene er ukendte.

## 3. Hypoteser (ikke dokumenteret)

| Hypotese | For | Imod | Evidens |
|---|---|---|---|
| H1 Hård låsning i hardware (strøm, RAM, bundkort på en 13 år gammel Sandy Bridge-maskine) | watchdog-reset viser total stilstand; intet logspor; tilfældig tid, oppetid og belastning; ingen ECC/EDAC, så RAM-fejl er usynlige | intet direkte bevis | **MIDDEL** |
| H1a Ekstern strømforsyning eller stikkontakt | 3 tænd for én boot 11-09 (POST fejlede eller blev tændt/slukket igen); 10-26 havde 33 min uden reset (strømsvigt?) | kan også være en hånd på tænd-knappen | SVAG-MIDDEL |
| H1b RAM | klassisk årsag til tilfældige låsninger uden spor | ikke testet | SVAG-MIDDEL |
| H1c CPU-varme eller køling (ultraslimt kabinet) | | 51 °C nu, ingen throttling-linjer; historik mangler | SVAG |
| H2 SSD hænger eller er overophedet | 0-byte-filer efter stop 1 og 7 | 22–30 °C; SMART rent; et rent I/O-hæng stopper sjældent PID 1's ping inden for 60 s | **IMOD** (afkræftet som varme) |
| H3 GPU/i915 under browserbelastning | en GPU-tung browser var åben ved alle 8 stop; xfconfd var sidste linje 2 gange | browseren er næsten altid åben (høj basisrate); ingen GPU HANG-linje | SVAG |
| H4 Softwarebelastning (testsuite, collector-genstartsløkke, dashboard-timer) | tung kørsel ved stop 3 og 7 | stop 8 uden tungt job; stop 1–6 før genstartsløkken; ingen OOM | SVAG / imod |
| H5 Kernefejl (6.12.113 + Sandy Bridge, fx C-states) | samme kerne ved alle stop | intet spor; kan ikke testes uden konfigurationsændring | LAV |
| H6 Strømsvigt i nettet | passer kun på stop 4 | ved 5 af 6 stop med watchdog var der strøm (automatisk reset) | SVAG (kun stop 4) |

**Samlet:** tavse låsninger af hele maskinen, der sandsynligvis skyldes hardware. Watchdoggen gør dem korte (ca.
1,5–4 min), men forhindrer dem ikke. Ejeren skal teste årsagen fysisk.

## 4. Datahuller efter stop 8 (11-10 ca. 22:03 UTC)

Kun `MIN/MAX/COUNT` i `lab.db` (mode=ro, query_only). Ingen rækker eller udfald er læst, og intet er ændret.

| Tabel | Sidste før | Første efter | Hul | Vurdering |
|---|---|---|---|---|
| `events` | 22:02:28 | 22:06:14 | 226 s | laben nede ca. 3,3 min (frys ca. 22:03, supervisor 22:06:38 ifølge vagten) |
| `sim_equity` | 22:01:24 | 23:01:23 | 1 t | normal timerytme; 14 af 14 konti hver time 19–01 UTC; **ingen time tabt** |
| `sim_orders` / `sim_fills` | 21:54:11 | 22:06:15 | 724 s | timen 22 UTC har 3 (ellers 5–12). Det meste er normal kadence; tabt handelstid ca. 3 min |
| `sim_funding` | 20:00:16 | 00:00:29 | 4 t | afregning kun kl. 20 og 00 UTC (samme som 11-08 og 11-09); **ingen afregning tabt** |

Vagten var nede fra 22:02:45 til 22:04:30 og dashboardet fra 22:04:30 til 22:05:56. pm_lp har ingen polls kl. 18–21
UTC, fordi collectoren var i genstartsløkke før stoppet (DNS, se INCIDENT). Stoppet kostede altså ingen pm_lp-polls.

## 5. pm_lp-collectoren nu (kun læst)

- Efter boot døde starten kl. 23:04:35 lokal (`exit 1`, 2,1 GB hukommelsestop, formentlig tilbagerulning af den varme
  journal). Fra 23:07 til 23:22 fejlede den 11 gange mere. **Fra 23:23:07 lokal (22:23 UTC) kørte den:**
  `collector.log` viser "panel dag 24: 200 nye" og "dag 25: 192 beholdt, 8 nye" kl. 01:00. Vagten meldte "collector
  virker igen" 22:24:31 UTC.
- Polls pr. time (`SELECT t/3600, COUNT(*), SUM(ok=0) FROM polls`): kl. 22 UTC 1.600 (4 fejl), derefter 2.200–2.400
  pr. time med 0 fejl til og med kl. 15 UTC 11-11, og kl. 16 UTC 1.400. **Den lavede altså vellykkede netværkskald i
  ca. 18 t.** `/etc/resolv.conf` blev skrevet af DHCP ved boot 23:04:34 (192.168.1.3 og 94.140.15.15). Hvorfor
  navneopslag virker igen, er ikke undersøgt (ingen netværkskald, filteret er forælderens).
- **2026-11-11 17:35:07 lokal blev tjenesten stoppet og slået fra** af `systemctl` (PID 15265, efterfulgt af
  `daemon-reload`). Det var ikke denne session, som kun brugte `show`. Nu er den `inactive (dead)`,
  `UnitFileState=disabled`, NRestarts=0. Vagten meldte "collector NEDE" 16:35:20 UTC. **Der foretages ingen
  netværkskald nu.** Hvem der stoppede den, bør direktøren afklare.

## 6. Anbefalede ejerhandlinger (kræver ingen ændring fra Claude)

Alle handlinger kræver nedetid. Direktøren og ejeren vælger tidspunktet, fordi reglen "ingen genstart 10-31 → 11-27"
stadig står.

1. **Hukommelsestest:** memtest86+ fra USB natten over, mindst 2 gennemløb (pakken er ikke installeret; `/boot` har
   ingen memtest). Finder testen fejl: test ét modul ad gangen, og tag modulerne ud og sæt dem i igen.
2. **Strøm:** kontrollér den eksterne strømforsyning (ledning, stik, varme, lyde), og prøv en anden stikkontakt uden
   stikdåse. En reserveforsyning eller en lille UPS er bedst. Sæt BIOS "After Power Loss" (F10 → Advanced →
   Power-On Options) til tændt; den mangler stadig ifølge LINUX_DRIFT.
3. **Køling:** blæs støv ud af køler og blæser, se at blæseren drejer, og sørg for fri luft om kabinettet (USDT ligger
   ikke i en lukket skuffe).
4. **BIOS:** se efter fejl- eller termiske hændelser i F10-menuen, og læs eventuelle POST-fejlbeeps eller -koder ved
   næste stop. Det kan forklare de 3 tænd 11-09.
5. **Spørgsmål til ejeren:** frøs maskinen også under Windows før 10-18? Var der strømsvigt i huset 10-26 ca. 12:50?
6. **Kræver særskilt ja, ikke nu:** løbende logning af temperatur, RAM og load til fil, `netconsole` eller syslog til en
   anden maskine, `kernel.softlockup_panic`/`hardlockup_panic` og ramoops/pstore. Det kan fange det næste stops sidste
   sekunder.

**Rettelse (17:43 lokal, koordinator):** collectoren blev stoppet og slået fra 17:35:07 lokal af Claude (koordinatoren) på ejerens udtrykkelige beslutning ("Stop collectoren"); se `PM_LP_COLLECTOR_STOP_2026-11-11.md`. Agenten bag denne note kendte ikke til det.
