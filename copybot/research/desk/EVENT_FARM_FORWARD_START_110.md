# Event farm fremadrettet papirbog: start (PROTOCOL_V3 ændring 46)

**Beslutning:** ejeren skrev 2026-11-12 ca. 22:46 lokal: "Start nu. Lige meget med den frsye regel og forsæt med hvad vi gør efter autonomt". Det tilsidesætter direktørbeslutning 109 (vent til efter 20/11) for denne papirbog.

**Kontrol før start:** `python3 -m research.tools.event_farm_run check` viste alle 9 G31-flag OK, gyldighed OK og `decide` G31+G15 OPEN. Suiten gav 2647 OK (5 forventede fejl, 1 skippet, 0 blokeret). tests_green-fingeraftryk `c5ebb62b…`.

**Aktivering:** 2026-11-12 22:09:59 UTC. Aktiveringsslot 1794521400 = 22:10:00 UTC. Udsagn `caea20b2…`, nonce `dbbedd7014936390`.

**Første kald:** 22:15:20 UTC.
- BTCUSDT og ETHUSDT: HTTP 200, 2 rækker hver, 1 lukket bar leveret og 1 dannende bar droppet.
- startTime = aktiveringsslottet, så ingen backfill.
- Bogen: 2 nye barer, 2 behandlet, ingen halt.

**Drift:** systemd `--user`-enheden `research/ops/event_farm/copybot-event-farm.service` installeres af ejeren (`INSTALL.md`). Indtil da står bogen stille. Når den startes, henter den de manglende barer fra den sidst lagrede bar med `limit=499`, så det er ikke backfill før slottet.

Opvarmning er de første 288 barer (24 t). Rapporter ved dag 14, 28 og 90, beskrivende og mærket PAPIR / SIMULERING.
