#!/usr/bin/env bash
# Stop and remove the jupiter_bot collector timer, the ops timers and the dashboard.
# The journal (data) is kept.
set -euo pipefail
UNIT_DIR="${JUPITER_UNIT_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
systemctl --user disable --now jupiter-collect.timer jupiter-health.timer jupiter-backup.timer jupiter-forward.timer 2>/dev/null || true
systemctl --user disable --now jupiter-dashboard.service 2>/dev/null || true
systemctl --user stop jupiter-collect.service jupiter-health.service jupiter-backup.service jupiter-forward.service 2>/dev/null || true
for unit in jupiter-{collect,health,backup,forward}.{timer,service} jupiter-dashboard.service; do
  if [[ -f "$UNIT_DIR/$unit" ]] && grep -qE "install-(collector|ops|dashboard)\.sh" "$UNIT_DIR/$unit"; then
    rm -- "$UNIT_DIR/$unit"
    echo "removed $UNIT_DIR/$unit"
  fi
done
systemctl --user daemon-reload 2>/dev/null || true
echo "Collector stopped. Data kept in ${JUPITER_DATA_DIR:-$HOME/.local/share/jupiter-bot}."
