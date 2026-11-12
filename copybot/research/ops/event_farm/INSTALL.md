# Event farm papirbog: installation (ejerens egen handling)

Ejeren besluttede 2026-11-12 at starte nu (PROTOCOL_V3 ændring 46, tekst 104, D5-underskrevet). Claude installerer
ikke selv vedvarende job. Ejeren kører på HP-USDT:

```
cp /home/anton/copybot-dev/copybot/research/ops/event_farm/copybot-event-farm.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now copybot-event-farm.service
```

**Tjek:** `systemctl --user status copybot-event-farm --no-pager` skal vise `active (running)`, og
`tail -3 ~/event_farm/run.log` skal få en ny linje hvert 5. minut.

**Hvad den gør:** henter hvert 5. minut de lukkede 5m-barer for BTCUSDT og ETHUSDT fra Binance-futures' offentlige
endepunkt (ingen nøgle, ingen konto, ingen ordrer) og papirhandler 96 tests i sin egen fil `~/event_farm`. De første
288 barer (24 timer) er opvarmning uden handler. Den kører i 90 dage. Ca. 0,5 MB pr. døgn og ca. 2 s CPU pr. døgn.

**Stop:** `touch ~/event_farm/STOP` stopper den før næste kald. Eller:

```
systemctl --user disable --now copybot-event-farm.service
rm ~/.config/systemd/user/copybot-event-farm.service
systemctl --user daemon-reload
```
