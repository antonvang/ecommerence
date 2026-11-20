#!/usr/bin/env bash
# Install the read-only jupiter_bot dashboard as a long-running systemd *user* service:
#   jupiter-dashboard  http://127.0.0.1:8787/ (loopback only), restarts on failure
# It only reads: the journal (read-only), backups, health-state, research/ and
# ~/.config/jupiter-bot/mandate.json. GET only; no endpoint writes anything.
#
#   ./install-dashboard.sh            install and start
#   ./install-dashboard.sh --dry-run  checks + write the unit, no systemctl
#
# Overrides: JUPITER_DATA_DIR (default ~/.local/share/jupiter-bot), PYTHON,
# JUPITER_UNIT_DIR (default ~/.config/systemd/user), JUPITER_DASHBOARD_PORT (default 8787).
set -euo pipefail

DRY_RUN=0
case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  "") ;;
  *) echo "usage: $0 [--dry-run]" >&2; exit 64 ;;
esac

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DATA_DIR="${JUPITER_DATA_DIR:-$HOME/.local/share/jupiter-bot}"
JOURNAL="$DATA_DIR/observations.db"
UNIT_DIR="${JUPITER_UNIT_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
PYTHON="${PYTHON:-$(command -v python3 || true)}"
PORT="${JUPITER_DASHBOARD_PORT:-8787}"

die() { echo "STOP: $*" >&2; exit 1; }
[[ -n "$PYTHON" ]] || die "python3 not found"
[[ -f "$REPO/jupiter_bot/dashboard/server.py" ]] || die "not a jupiter_bot checkout with the dashboard: $REPO"
[[ -f "$JOURNAL" ]] || die "no journal at $JOURNAL; run install-collector.sh first"
[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1024 && PORT <= 65535 )) || die "JUPITER_DASHBOARD_PORT must be 1024-65535"
if [[ $DRY_RUN -eq 0 && $EUID -eq 0 ]]; then
  die "run as your normal user, not root (this installs a per-user service)"
fi
case "$REPO$DATA_DIR" in
  *$'\n'*|*'"'*|*'\'*|*'%'*) die "paths with newlines, quotes, backslashes or % are not supported" ;;
esac

echo "==> Check: dashboard tests (offline)"
(cd "$REPO" && "$PYTHON" -m unittest jupiter_bot.tests.test_dashboard) || die "dashboard tests failed"

mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/jupiter-dashboard.service" <<EOF
# Installed by jupiter_bot/deploy/linux/install-dashboard.sh. Reads only; listens on 127.0.0.1.
[Unit]
Description=jupiter_bot dashboard on http://127.0.0.1:$PORT/ (read-only)
Documentation=file://$REPO/jupiter_bot/deploy/linux/README.md

[Service]
Type=simple
WorkingDirectory=$REPO
ExecStart="$PYTHON" -m jupiter_bot.dashboard --journal "$JOURNAL" --data-dir "$DATA_DIR" --port $PORT
Restart=on-failure
RestartSec=10
Nice=10
NoNewPrivileges=yes

[Install]
WantedBy=default.target
EOF
echo "wrote $UNIT_DIR/jupiter-dashboard.service"

if [[ $DRY_RUN -eq 1 ]]; then
  echo "Dry run: not starting. Start by hand: systemctl --user daemon-reload && systemctl --user enable --now jupiter-dashboard.service"
  exit 0
fi
systemctl --user daemon-reload
systemctl --user enable --now jupiter-dashboard.service
systemctl --user --no-pager status jupiter-dashboard.service | head -n 5 || true
echo "Open http://127.0.0.1:$PORT/"
