#!/usr/bin/env bash
# Install the jupiter_bot market-data collector as a systemd *user* timer.
#
# What it does: every minute, one `python3 -m jupiter_bot collect` cycle fetches
# public data (Binance SOLUSDC candles, two Jupiter quotes; status feeds hourly)
# into a journal outside the repository. Read-only public data: no keys, no
# wallet, no orders, no root. Run it from a SEPARATE clone, not from a folder
# that runs Copybot.
#
#   ./install-collector.sh            install and start
#   ./install-collector.sh --dry-run  checks + one cycle + write units, no systemctl
#
# Overrides: JUPITER_DATA_DIR (default ~/.local/share/jupiter-bot), PYTHON,
# JUPITER_UNIT_DIR (default ~/.config/systemd/user).
set -euo pipefail

DRY_RUN=0
case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  "") ;;
  *) echo "usage: $0 [--dry-run]" >&2; exit 64 ;;
esac

die() { echo "STOP: $*" >&2; exit 1; }
say() { echo "==> $*"; }

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DATA_DIR="${JUPITER_DATA_DIR:-$HOME/.local/share/jupiter-bot}"
JOURNAL="$DATA_DIR/observations.db"
UNIT_DIR="${JUPITER_UNIT_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
PYTHON="${PYTHON:-$(command -v python3 || true)}"

[[ -n "$PYTHON" ]] || die "python3 not found"
[[ -f "$REPO/jupiter_bot/__main__.py" ]] || die "not a jupiter_bot checkout: $REPO"
if [[ $DRY_RUN -eq 0 && $EUID -eq 0 ]]; then
  die "run as your normal user, not root (this installs a per-user timer)"
fi
case "$REPO$DATA_DIR" in
  *$'\n'*|*'"'*|*'\'*|*'%'*) die "paths with newlines, quotes, backslashes or % are not supported" ;;
esac

say "Python and SQLite"
"$PYTHON" - <<'EOF' || die "Python >= 3.9 with SQLite >= 3.24 is required"
import sqlite3, sys
print("   python", sys.version.split()[0], "sqlite", sqlite3.sqlite_version)
assert sys.version_info >= (3, 9) and sqlite3.sqlite_version_info >= (3, 24)
EOF

say "Not an active Copybot folder"
shopt -s nullglob
copybot_dbs=("$REPO"/copybot/data/*.db "$REPO"/copybot/lab/*.db "$REPO"/copybot/*.db)
shopt -u nullglob
if [[ ${#copybot_dbs[@]} -gt 0 ]]; then
  die "this checkout has Copybot databases (${copybot_dbs[0]}...). Use a separate clone for the collector."
fi
case "$DATA_DIR/" in
  "$REPO"/*) die "keep the journal outside the repository (JUPITER_DATA_DIR=$DATA_DIR)" ;;
esac

say "Tests (offline)"
(cd "$REPO" && "$PYTHON" -m unittest discover -s jupiter_bot/tests >/dev/null 2>&1) \
  || die "tests fail in $REPO; nothing installed. Run: $PYTHON -m unittest discover -s jupiter_bot/tests -v"

say "One collection cycle now -> $JOURNAL"
mkdir -p "$DATA_DIR"
set +e
(cd "$REPO" && "$PYTHON" -m jupiter_bot collect --journal "$JOURNAL")
code=$?
set -e
case $code in
  0) say "cycle OK" ;;
  1) say "cycle partly failed (see the line above); installing anyway, failures are journaled" ;;
  *) die "every source failed (no network?). Nothing installed." ;;
esac

say "systemd user units -> $UNIT_DIR"
mkdir -p "$UNIT_DIR"
cat > "$UNIT_DIR/jupiter-collect.service" <<EOF
# Installed by jupiter_bot/deploy/linux/install-collector.sh. Public data only.
[Unit]
Description=jupiter_bot market-data collector, one cycle (no keys, no trading)
Documentation=file://$REPO/jupiter_bot/deploy/linux/README.md

[Service]
Type=oneshot
WorkingDirectory=$REPO
ExecStart="$PYTHON" -m jupiter_bot collect --journal "$JOURNAL"
TimeoutStartSec=50
Nice=10
NoNewPrivileges=yes
EOF
cat > "$UNIT_DIR/jupiter-collect.timer" <<'EOF'
# Installed by jupiter_bot/deploy/linux/install-collector.sh.
[Unit]
Description=Run the jupiter_bot collector every minute (7 s past, after bars close)

[Timer]
OnCalendar=*-*-* *:*:07
AccuracySec=1s
Persistent=false

[Install]
WantedBy=timers.target
EOF

if [[ $DRY_RUN -eq 1 ]]; then
  say "dry run: units written, systemctl not called"
  exit 0
fi

say "Enable timer"
systemctl --user daemon-reload
systemctl --user enable --now jupiter-collect.timer
systemctl --user list-timers jupiter-collect.timer --no-pager || true

cat <<EOF

Installed. The collector runs every minute while you are logged in.
  Logs:     journalctl --user -u jupiter-collect.service -n 20
  Data:     cd "$REPO" && $PYTHON -m jupiter_bot journal-status --journal "$JOURNAL"
  Stop:     $REPO/jupiter_bot/deploy/linux/uninstall-collector.sh   (keeps the data)
  Update:   git -C "$REPO" pull   (the next cycle uses the new code)
To keep it running when you are logged out (your choice):  loginctl enable-linger "$USER"
EOF
