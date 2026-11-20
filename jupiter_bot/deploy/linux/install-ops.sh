#!/usr/bin/env bash
# Install two systemd *user* timers next to the collector (install-collector.sh first):
#   jupiter-health  every 15 min: desktop alert + journald error if a source is stale
#   jupiter-backup  daily 03:30:  consistent copy of the journal, newest 7 kept
# Both only read the journal. Backups land in $JUPITER_DATA_DIR/backups, which is
# on the same disk: it protects against corruption and deletion, not disk loss.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DATA_DIR="${JUPITER_DATA_DIR:-$HOME/.local/share/jupiter-bot}"
JOURNAL="$DATA_DIR/observations.db"
UNIT_DIR="${JUPITER_UNIT_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
PYTHON="${PYTHON:-$(command -v python3 || true)}"

die() { echo "STOP: $*" >&2; exit 1; }
[[ -n "$PYTHON" ]] || die "python3 not found"
[[ -f "$JOURNAL" ]] || die "no journal at $JOURNAL; run install-collector.sh first"
case "$REPO$DATA_DIR" in
  *$'\n'*|*'"'*|*'\'*|*'%'*) die "paths with newlines, quotes, backslashes or % are not supported" ;;
esac

echo "==> Check: one health run and one backup now"
(cd "$REPO" && "$PYTHON" -m jupiter_bot.ops health --journal "$JOURNAL") || echo "   (a source is stale right now; the alarm works)"
(cd "$REPO" && "$PYTHON" -m jupiter_bot.ops backup --journal "$JOURNAL") || die "backup failed"

mkdir -p "$UNIT_DIR"
for job in health backup; do
  cat > "$UNIT_DIR/jupiter-$job.service" <<EOF
# Installed by jupiter_bot/deploy/linux/install-ops.sh. Reads the journal only.
[Unit]
Description=jupiter_bot collector $job (read-only)
Documentation=file://$REPO/jupiter_bot/deploy/linux/README.md

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart="$PYTHON" -m jupiter_bot.ops $job --journal "$JOURNAL"
TimeoutStartSec=300
Nice=10
NoNewPrivileges=yes
EOF
done
cat > "$UNIT_DIR/jupiter-health.timer" <<'EOF'
# Installed by jupiter_bot/deploy/linux/install-ops.sh.
[Unit]
Description=Check every 15 min that the jupiter_bot collector still gets data

[Timer]
OnCalendar=*:02/15:30
Persistent=false

[Install]
WantedBy=timers.target
EOF
cat > "$UNIT_DIR/jupiter-backup.timer" <<'EOF'
# Installed by jupiter_bot/deploy/linux/install-ops.sh.
[Unit]
Description=Daily backup of the jupiter_bot journal

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now jupiter-health.timer jupiter-backup.timer
systemctl --user list-timers 'jupiter-*' --no-pager || true
