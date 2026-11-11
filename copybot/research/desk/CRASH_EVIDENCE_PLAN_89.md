# Bevisplan for nedbrud (direktørordre 89: design GO, systemændringer blokeret)

Skrevet 2026-11-11 kl. 17:48 lokal. Planen er kun design. Intet er installeret, aktiveret, konfigureret eller
genstartet, og der er hverken brugt sudo eller netværk. Planen bygger på `research/desk/CRASH_TRIAGE_84.md`:
8 tavse stop på 22 døgn, rodårsag **UNKNOWN**. Coordinatoren stoppede pm_lp-collectoren efter ejerens beslutning; det
er kendt.

## 1. Hvad der logges i dag (læst, ikke ændret)

| Kilde | Tilstand | Hvad den fanger ved et stop | Mangler |
|---|---|---|---|
| journald | persistent (`/var/log/journal`, 112 MB); `SyncIntervalSec` er standard (5 min); `ForwardToSyslog=yes`, men rsyslog kører ikke | linjer, der er ældre end ca. 30 s (kernens writeback: `dirty_expire` 30 s, `dirty_writeback` 5 s) | journalen er tynd: ingen løbende temperatur, RAM eller load |
| Hardware-watchdog | `RuntimeWatchdogSec=60` (iTCO_wdt), `RebootWatchdogUSec=10min`, `kernel.panic=10` | nulstiller værten ca. 60 s efter, at PID 1 holder op med at pinge | logger intet; `bootstatus=0` kan ikke bruges som bevis |
| Kernens detektorer | `nmi_watchdog=1`, `watchdog_thresh=10`, `hung_task_timeout=120`; alle `*_panic=0`, `panic_on_oops=0` | skriver hard/soft lockup og hung task til kmsg | uden panic lander teksten aldrig på disken, når maskinen fryser |
| pstore | backend `efi_pstore` er indlæst; `systemd-pstore` er slået til; `/var/lib/systemd/pstore` er tom | gemmer kernens log ved panic eller oops | der var ingen panic ved de 8 stop, så der er intet gemt |
| MCE | `CONFIG_X86_MCE_INTEL=y`; rasdaemon og mcelog er ikke installeret | fatale MCE-banker logges ved næste boot ("Machine check events logged") | ingen fundet i de 9 boots; EDAC er nyttesløs uden ECC-RAM |
| Sensorer | `coretemp` (pakke og 4 kerner), `x86_pkg_temp`, throttle-tællere (alle 0 siden boot), cpufreq, PSI (`/proc/pressure`) | kun nu-værdier | ingen historik; ingen blæser- eller spændingssensorer (`hp-isa pwm1 N/A`); strømforsyningen kan ikke måles i software |
| SSD | smartd skriver `attrlog` hver 30. min (temperatur, tænd-tæller, usikre slukninger) | temperatur og antal tænd før og efter | intervallet er grovt |
| Lab | vagt-tick hver 30. s i `watch.log`, `lab.db`-hændelser | frysningstid ±30 s og boot-tid | ingen værtstilstand |

`dmesg_restrict=1`, så kernens log læses via `journalctl -k` (brugeren er i gruppen `systemd-journal`). `/sys/fs/pstore`
og debugfs kræver root.

## 2. Minimal observationsløsning: `hostprobe` (trin 1, ingen sudo, ingen genstart)

**Formål:** de sidste 10 s før et stop skal stå på disken: CPU, RAM, I/O-kø, temperatur og throttling.

- **Én langlivet proces** i en systemd-brugerenhed (`~/.config/systemd/user/hostprobe.service`). Linger er slået til,
  så den starter selv ved boot. Mønstret følger `copybot-dashboard.service`: `Nice=19`, `NoNewPrivileges=yes`,
  `RestrictAddressFamilies=AF_UNIX`, `MemoryMax=64M`, `Restart=always`.
- **Hver 10. s** skrives én JSON-linje på ca. 600 B med:
  - UTC og monotonisk tid, boot_id;
  - `loadavg`, `procs_running/blocked` (vigtig ved I/O-hæng) og CPU-% fra `/proc/stat`;
  - `MemAvailable`, `Dirty/Writeback`, swap;
  - PSI cpu/memory/io avg10;
  - coretemp (pakke og kerner), throttle-tællere og cpufreq;
  - deltaer for `sda/stat` (I/O i kø, io_ticks).
- **Hvert 60. s:** de 3 tungeste processer efter CPU og RSS, og antal Chrome- og Firefox-processer.
- **Hvert 10. min:** UDisks2 `SmartTemperature`.
- **Holdbarhed:** linjen tilføjes og `fdatasync` kaldes efter hver måling. Højst ca. 10 s går tabt, medmindre SSD'en
  selv hænger (se 2b). Én fil pr. døgn i `~/hostprobe/`, der slettes efter 30 dage.
- **Efter et stop:** et læsescript viser de sidste 30 målinger fra forrige boot (boot_id) ved siden af watch-tick og
  journal.

**2b. USB-pind som andet medie (valgfrit):** ejeren sætter en USB-pind i, og den monteres som bruger via udisks (aktiv
session, ingen sudo). `hostprobe` skriver en kopi dertil. Hænger SSD'en, står de sidste sekunder stadig på pinden. Det
skelner mellem H2 (SSD) og H1 (hele platformen).

### Forventet belastning (målt på værten med en engangsprototype, der kun læser)

| Ressource | Skøn | Grundlag |
|---|---|---|
| CPU | < 0,05 % af én kerne | 0,9 ms pr. læsning af 25 filer; ps-scan 5,5 ms pr. 60 s (192 processer); parsing ca. 1 ms |
| RAM | ca. 11–15 MB RSS | prototypens maxrss 10,5 MB |
| Diskplads | ca. 5 MB pr. døgn, ca. 150 MB efter 30 dage | 8.640 linjer à ca. 600 B |
| Skrivninger | ca. 0,15 GB pr. døgn inklusive ext4-journal for fdatasync (skøn: ca. 16 KB pr. sync) | værten skriver i dag 13,8–15,8 GB pr. døgn (SMART 241, 20 dage; `/sys/block/sda/stat`): **ca. 1 % ekstra** |
| SSD-slid | ubetydeligt | attr 177 steg fra 851 til 879 P/E på 20 dage; tillægget er ca. 1 % |

### Påvirkning af beskyttede processer og datagates

**Ingen.** `hostprobe`:
- læser ikke `lab.db` eller `pm_lp.db`, så der er ingen låse og ingen holdout;
- laver ingen netværkskald (`AF_UNIX` bruges kun til D-Bus);
- skriver uden for begge checkouts, så `git status`, deploy-check og guard-tests ikke påvirkes;
- rører ikke lab, vagt, S7-enheder, collector eller dashboard;
- kræver ingen genstart.

**Aktivering kræver direktørens GO**, fordi det er en ny brugerenhed i `~/.config/systemd/user`. Den kræver ikke sudo.
Den kan stoppes når som helst med `systemctl --user disable --now hostprobe`.

## 3. Hvad kræver ejerens eller sudo-handling

| Trin | Kræver | Genstart? | Gevinst | Risiko |
|---|---|---|---|---|
| A. `sysctl kernel.hardlockup_panic=1` (og fil i `/etc/sysctl.d`) | sudo | nej | en låst CPU giver panic, efi_pstore gemmer kmsg, genstart efter 10 s, og `systemd-pstore` arkiverer. **Kommer der ingen dump efter næste stop, peger det på platform eller strøm (ingen NMI)** | LAV: en hård låsning kommer aldrig tilbage alligevel. efi_pstore skriver EFI-variabler (gammel UEFI med fuld NVRAM er en kendt, sjælden risiko; `systemd-pstore` sletter efter arkivering) |
| B. `softlockup_panic=1` | sudo | nej | fanger softlocks | MIDDEL: soft lockups, der ellers ville gå over, giver flere genstarter. Anbefales ikke nu |
| C. journald `SyncIntervalSec=10s` (drop-in og genstart af journald) | sudo | kun journald | tab ca. 30 s → ca. 10 s | LAV; ringe gevinst, når `hostprobe` findes |
| D. `netconsole` til en anden maskine på LAN | sudo, en modtager (ejerens maskine) og et netværks-ja | nej | den bedste kilde til kernens sidste linjer, også ved disk-hæng | LAN-UDP; kræver direktørens ja (netværk) |
| E. rasdaemon eller mcelog, memtest86+ fra apt | sudo og apt-netværk | nej (memtest kræver boot) | MCE-historik; GRUB-indgang til memtest | installationen er blokeret nu |
| F. ramoops og kerneparametre (`intel_idle.max_cstate=1`) | sudo | **ja** | A/B-test | efter 27/11 |

**Anbefalet rækkefølge, når blokeringen løftes:** først `hostprobe` (trin 1, uden sudo), dernæst A. D kun hvis ejeren
har en anden maskine. B, C og F nu er ikke anbefalet.

## 4. Visuel kontrol af strømforsyningen nu (GO, ingen afbrydelse)

Ejeren må ikke tage stik ud eller flytte kablet under drift. Ejeren kontrollerer:
- **Adapteren:** den eksterne adapter til USDT'en. Er den lun eller meget varm at røre ved? Lugter den, summer eller
  piber den? Er der misfarvning, eller er huset revnet? Lyser LED'en, hvis den har en, roligt?
- **Kablet:** knæk, klemte steder, slidt isolering ved begge ender. Sidder stikkene fast og helt inde, uden at vrikke?
- **Placering:** fri luft om adapteren (ikke under tæppe eller i skuffe), stikdåse eller direkte i væggen, andre store
  forbrugere på samme kreds (varmeapparat, kedel).
- **Mærkat:** model, watt og spænding (19,5 V?). Skriv ned eller tag foto til at bestille en reserve.
- **Strømsvigt:** husker ejeren strømsvigt eller blink i huset 10-26 ca. 12:50, eller ved nogen af de andre stop?

## 5. Vedligeholdelsesplan efter 27/11 (prioriteret)

Basisrate: 8 stop på 22,3 døgn, ca. 0,36 pr. døgn. Stoppene kommer i klynger, så en ændring skal give **mindst 14
døgn uden stop** (P ≈ 0,6 % under en Poisson-model; i praksis højere), før den kaldes en forbedring. **Ét skridt ad
gangen**, så årsagen kan skelnes. Diagnostik, der ikke ændrer noget, må samles i ét vindue.

| Prioritet | Handling | Type | Varighed | Udfald |
|---|---|---|---|---|
| 1 | **memtest86+** fra USB eller GRUB, mindst 2 fulde gennemløb natten over (16 GB) | diagnostik | 4–8 t | Fejl: test ét modul ad gangen og udskift det dårlige. Rent: RAM er mindre sandsynlig, men ikke udelukket |
| 1 | **BIOS (F10):** læs eventuelle hændelses- og POST-fejllogs, tjek blæser og temperaturindstillinger, notér versionen (J01 v02.33, 2019). Sæt "After Power Loss" til tændt | diagnostik og én harmløs indstilling | 15 min | termiske hændelser eller POST-fejl peger på H1a/H1c |
| 2 | **Reserve-strømforsyning** (samme specifikation) i 14–21 døgn | én ændring | ingen nedetid ud over skiftet | ingen stop i 14+ døgn: strømforsyningen er sandsynlig årsag |
| 3 | **Rensning og køling:** blæs støv ud af køler og blæser, tjek at blæseren drejer, giv fri luft. Kun ny kølepasta, hvis CPU-temperaturen under belastning viser > 75 °C i `hostprobe` | én ændring | 30 min | |
| 4 | **Software A/B**, kun hvis 1–3 ikke hjælper: boot den ældre kerne 6.12.107 (findes i `/boot`), derefter `intel_idle.max_cstate=1` | én ændring ad gangen | genstart | |
| 5 | Kraftigere tiltag: ny SSD, RAM-udskiftning trods ren memtest eller anden maskine | | | sidste udvej |

**Før vinduet:** planlæg lab, vagt og S7 efter de normale regler for deploy og nedetid (K1–K3), og registrér nedetiden
i ledgeren. Collectoren er stoppet efter ejerens beslutning og er ikke del af planen.
