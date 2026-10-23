#!/usr/bin/env bash
# S7-automatisering på Linux: FORBEREDT, IKKE AKTIVERET (research/LINUX_DRIFT.md, "Ekstern sundhedskontrol og S7").
# Slår copybot-lab.service og copybot-watch.service til som systemd-brugertjenester, så laboratoriet og vagten starter
# ved næste opstart. Afviser og installerer intet, medmindre S7-gaten er åben (`python3 -m lab gate --require` = 0).
# Køres kun af brugeren, i hånden, fra mappen copybot, når S7 er åben og brugeren har besluttet det:
#   lab/automation/s7_install_linux.sh
# Starter intet nu (enable uden --now): en kørende flåde får aldrig en ekstra ved siden af sig.
# Fortryd: systemctl --user disable copybot-lab copybot-watch; rm ~/.config/systemd/user/copybot-{lab,watch}.service
set -euo pipefail
cd "$(dirname "$0")/../.."
UNITS="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
if ! python3 -m lab --db "${LAB_DB:-data/lab/lab.db}" gate --require; then
  echo "S7-gaten er lukket: automatiseringen blev IKKE installeret."
  exit 2
fi
mkdir -p "$UNITS"
for u in copybot-lab copybot-watch; do
  if [ -e "$UNITS/$u.service" ]; then
    echo "$UNITS/$u.service findes allerede: intet ændret."
    exit 3
  fi
done
for u in copybot-lab copybot-watch; do
  cp "lab/automation/$u.service" "$UNITS/$u.service"
done
"$SYSTEMCTL" --user daemon-reload
"$SYSTEMCTL" --user enable copybot-lab copybot-watch
echo "Installeret: copybot-lab og copybot-watch starter ved næste opstart (intet startet nu)."
