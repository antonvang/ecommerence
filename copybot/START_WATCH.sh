#!/usr/bin/env bash
# Uafhaengig overvaagning af laboratoriet og pm_lp-indsamleren (lab/watch.py). Kun laesning; genstarter aldrig noget.
# Start i baggrunden (fra mappen copybot), uafhaengigt af START_LAB.sh og START_PM_LP.sh:
#   setsid nohup ./START_WATCH.sh >> data/lab/watch.log 2>&1 < /dev/null &
# Status nu:  python3 -m lab watch --once     (exit 0 = alt koerer)
# Stop:       kill <pid>  (se: pgrep -af "lab watch"). Laboratoriet melder det efter 15 min (external.stale W_watch).
# S7: startes i haanden. Autostart/timer/service er S7-automatisering og venter til S7-gaten er aaben.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUNBUFFERED=1
export RES_OPTIONS="${RES_OPTIONS:-timeout:1 attempts:2}"
echo "$(date -u +%FT%TZ) START_WATCH.sh paa $(hostname)"
exec python3 -m lab watch --port "${LAB_PORT:-8770}"
