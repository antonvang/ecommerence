# Dashboard-timer (event farm)

Opdaterer `~/copybot_farm.html` (dashboard, åbner på PAPIR LIVE) og `~/copybot_farm_feed.html` (mobil-feed) hvert
5. minut, kl. xx:x2:30 og xx:x7:30, altså 2½ minut efter papirbogens skridt. Bogen læses read-only. Den syntetiske
korpus og filter-null caches i `~/.cache/copybot_farm` (genberegnes kun, når koden ændres).

    cp research/ops/farm_dashboard/copybot-farm-dashboard.{service,timer} ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now copybot-farm-dashboard.timer

Stop: `systemctl --user disable --now copybot-farm-dashboard.timer`.
