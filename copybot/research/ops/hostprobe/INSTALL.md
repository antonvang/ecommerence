# hostprobe: installation (ejerens egen handling)

Godkendt af direktøren (beslutning 91) efter ejerens ja. Claude installerer ikke selv vedvarende job. Ejeren kører:

```
mkdir -p ~/.config/systemd/user ~/hostprobe
cp /home/anton/copybot-dev/copybot/research/ops/hostprobe/copybot-hostprobe.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now copybot-hostprobe.service
```

**Tjek:** `systemctl --user status copybot-hostprobe --no-pager` skal vise `active (running)`, og
`tail -2 ~/hostprobe/$(date -u +%F).jsonl` skal vise linjer, der kommer hvert 10. sekund.

**Hvad den gør:** én linje hvert 10. sekund med load, CPU, RAM, pres (PSI), CPU-temperatur, throttling og disk-kø;
de tungeste processer hvert minut; SSD-temperatur hvert 10. minut. Den skriver kun i `~/hostprobe` (ca. 5 MB pr. døgn)
og læser kun `/proc`, `/sys` og én D-Bus-egenskab. Intet netværk, ingen database, ingen sudo, ingen genstart. Den er
begrænset til 5 % CPU og 64 MB RAM.

**Slå fra (rollback):**

```
systemctl --user disable --now copybot-hostprobe.service
rm ~/.config/systemd/user/copybot-hostprobe.service
systemctl --user daemon-reload
```

Logfilerne i `~/hostprobe` kan slettes bagefter.
