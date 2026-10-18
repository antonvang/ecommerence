#!/usr/bin/env bash
# Mars Command Center paa Linux - forskningsflaade + dashboard. Kun simuleret handel, ingen rigtige penge.
# Brug:  ./START_LAB.sh        (fra mappen copybot)
set -euo pipefail
cd "$(dirname "$0")"

PY=python3
command -v "$PY" >/dev/null || { echo "Python 3 mangler: sudo apt install python3"; exit 1; }
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python 3.10 eller nyere kraeves"; exit 1; }

if [ ! -f data/lab/lab.db ]; then
  echo "Advarsel: data/lab/lab.db findes ikke. Kopier den fra Windows-pc'en (se research/LINUX_FLYT.md),"
  echo "ellers starter laboratoriet uden sin historik (resultater, godkendelser, MVRV-observation)."
  read -r -p "Start alligevel med en tom database? [j/N] " svar
  [ "${svar:-n}" = "j" ] || exit 1
fi

mkdir -p data/lab
echo
echo " Mars Command Center - forskningsflaade (paper, ingen rigtige penge)"
echo " ==================================================================="
echo " Starter dashboardet i baggrunden (log: data/lab/web.log) ..."
"$PY" -m lab web --port 8770 >> data/lab/web.log 2>&1 &
WEB=$!
trap 'kill $WEB 2>/dev/null || true' EXIT
sleep 3
command -v xdg-open >/dev/null && xdg-open http://127.0.0.1:8770 >/dev/null 2>&1 || echo " Aabn http://127.0.0.1:8770 i browseren."
echo
echo " Forskningsflaaden koerer nu i DETTE vindue."
echo " - Stop: Ctrl+C her (dashboardet stopper samtidig), eller Pause/Stop i dashboardet."
echo
"$PY" -m lab fleet
