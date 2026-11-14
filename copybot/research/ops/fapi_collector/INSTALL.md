# Indsamler af positionering og likvideringer (ændring 49, gate G32)

Kun offentlige data fra Binance (ingen nøgle, ingen ordrer). Gemmer i `~/fapi_collector/positioning.db`.

Installér (ejeren gør det selv):

```
cp /home/anton/copybot-dev/copybot/research/ops/fapi_collector/copybot-fapi-collector.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now copybot-fapi-collector.service
```

Tjek: `systemctl --user status copybot-fapi-collector` og `cat ~/fapi_collector/status.json`.
Stop: `touch ~/fapi_collector/STOP` (eller `systemctl --user disable --now copybot-fapi-collector`).
