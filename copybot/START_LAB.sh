#!/usr/bin/env bash
# Mars Command Center paa Linux - forskningsflaade + dashboard. Kun simuleret handel, ingen rigtige penge.
# Brug:  ./START_LAB.sh        (fra mappen copybot; LAB_PORT vaelger en anden dashboard-port)
# Stopper flaaden uventet, bliver dashboardet koerende og viser "offline", og fejlen skrives her med tidspunkt.
# Intet genstartes automatisk.
set -euo pipefail
cd "$(dirname "$0")"

PY=python3
PORT="${LAB_PORT:-8770}"
now() { date -u +%FT%TZ; }
command -v "$PY" >/dev/null || { echo "Python 3 mangler: sudo apt install python3"; exit 1; }
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python 3.10 eller nyere kraeves"; exit 1; }

if [ ! -f data/lab/lab.db ]; then
  echo "Advarsel: data/lab/lab.db findes ikke. Kopier den fra Windows-pc'en (se research/LINUX_FLYT.md),"
  echo "ellers starter laboratoriet uden sin historik (resultater, godkendelser, MVRV-observation)."
  read -r -p "Start alligevel med en tom database? [j/N] " svar
  [ "${svar:-n}" = "j" ] || exit 1
fi

mkdir -p data/lab
echo "$(now) START_LAB.sh paa $(hostname), port $PORT"
if [ -f data/lab/lab.db ]; then
  echo " Tjekker at laboratoriet kan starte sikkert ..."
  "$PY" -m lab preflight --port "$PORT" || { echo "$(now) Start afbrudt. Se ovenfor (og research/LINUX_FLYT.md)."; exit 1; }
fi
echo
echo " Mars Command Center - forskningsflaade (paper, ingen rigtige penge)"
echo " ==================================================================="
WEB=""
if "$PY" -m lab preflight --dashboard-running --port "$PORT" >/dev/null 2>&1; then
  echo " Dashboardet koerer allerede paa port $PORT: det genbruges."
else
  echo " Starter dashboardet i baggrunden (log: data/lab/web.log) ..."
  "$PY" -m lab web --port "$PORT" >> data/lab/web.log 2>&1 &
  WEB=$!
  sleep 3
  command -v xdg-open >/dev/null && xdg-open "http://127.0.0.1:$PORT" >/dev/null 2>&1 || echo " Aabn http://127.0.0.1:$PORT i browseren."
fi
USER_STOP=0
trap 'USER_STOP=1' INT TERM
echo
echo " Forskningsflaaden koerer nu i DETTE vindue."
echo " - Stop: Ctrl+C her (dashboardet stopper samtidig), eller Pause/Stop i dashboardet."
echo
set +e
"$PY" -m lab fleet
RC=$?
set -e
if [ "$RC" -eq 0 ] || [ "$USER_STOP" -eq 1 ]; then
  echo "$(now) Flaaden er stoppet (exit $RC)."
  [ -n "$WEB" ] && kill "$WEB" 2>/dev/null || true
  exit 0
fi
echo "$(now) FLAADEN STOPPEDE UVENTET (exit $RC). Dashboardet koerer videre og viser 'offline'." >&2
echo "  Se data/lab/logs/supervisor-*.jsonl. Start igen med ./START_LAB.sh, naar aarsagen er kendt." >&2
exit "$RC"
