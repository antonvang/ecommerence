# Dashboard-timer: installation (ejerens egen handling)

Claude må ikke selv installere vedvarende baggrundsjob på maskinen. Ejeren aktiverer timeren med disse kommandoer:

```
mkdir -p ~/.config/systemd/user
cp /home/anton/copybot-dev/copybot/research/ops/dashboard_timer/copybot-dashboard.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now copybot-dashboard.timer
```

**Tjek:** `systemctl --user list-timers copybot-dashboard.timer` viser næste kørsel. Åbn
`file:///home/anton/copybot_dashboard.html` i Chrome. Siden genindlæser sig selv hvert 5. minut.

**Slå fra (rollback):**

```
systemctl --user disable --now copybot-dashboard.timer
rm ~/.config/systemd/user/copybot-dashboard.service ~/.config/systemd/user/copybot-dashboard.timer
systemctl --user daemon-reload
```

Timeren rører ikke pm_lp, papirbots eller andre units. Den læser `lab.db` read-only, har intet netværk og skriver kun
`~/copybot_dashboard.html`.
