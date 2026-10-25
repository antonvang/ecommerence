# Forslag: fail-closed overvågning af timescanning og værtsgenstart (udkast 2026-10-25 kl. 11:18)

**Status:** forslag. Intet er aktiveret. Vagten (`lab watch`, pid 135362) ændres eller genstartes ikke uden brugerens ja
(hver gang). Autostart er S7-automation og forbliver lukket.

## Hvad der findes i dag (målt i koden)
- `lab/watch.py` kører uden for laben, åbner databaserne read-only og alarmerer, når laben, agenterne, dashboardet
  eller pm_lp-collectoren holder op med at gøre fremskridt. Den registrerer også, når værten har sovet.
  Alarmer går til dens log og `data/lab/watch_status.json`.
- Laben selv (ændring 21z/23): `research.k_preflight` fredag, `scanner.gap` og `system.host_boot`. Alle tre opdages først,
  når laben kører igen.

## Huller
1. **Ingen af dem dømmer timescanningen.** En levende fleet, hvor scanneren hænger, opdages kun af agentens
   heartbeat-regel (STALE efter 3 × 3 600 s), altså for sent for K1/K2.
2. **Efter en genstart af værten kører hverken laben eller vagten.** Der er ingen alarm, før et menneske ser efter.
3. **Ingen kanal ud af maskinen.** Alarmen ligger i en fil. Den eneste aktive "ekstern" læser er Claude-sessionens /loop
   (time-tjek), som kun lever, så længe sessionen gør.

## Forslag (kræver brugerens ja før aktivering)
A. **Ny vagtkomponent `scanner`:**
   - alarm, hvis seneste `abnormal_move/1`-scanning er over 70 min gammel (lørdag–søndag UTC: over 12 min efter HH:02);
   - alarm, hvis en K3-runde nåede S − 31 min uden `selection` eller `missed`.
   **Fail-closed:** kan vagten ikke læse databasen eller tiden, er komponenten `DOWN`, aldrig `OK`.
B. **Genstart af værten:** kun S7-autostart af vagten (ikke af laben) kan alarmere uden et menneske. Det er brugerens
   beslutning; S7 røres ikke.
C. **Ingen automatisk genopretning.** Vagten starter, stopper og genoptager intet. Pauseregler (ændring 18) er uændrede.
   Netværk alene genoptager aldrig handel.

## Testkriterier før aktivering
1. Syntetisk database, hvor scanningen er 71 min gammel: `scanner` = alarm. 69 min: ok. Weekend 12/13 min efter HH:02:
   ok/alarm.
2. Database låst eller ulæselig: `DOWN`, exit 1 i `--once`.
3. K3-runde uden udvælgelse ved S − 30 min: alarm. Med `missed`: ingen ny alarm (allerede registreret).
4. Påmindelser højst hver time (REMIND_S), og ingen skrivning i lab.db (mode=ro).
5. Fuld suite grøn. Genstart af vagten først efter brugerens ja.
