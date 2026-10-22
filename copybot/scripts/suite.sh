#!/bin/bash
# Full test suite with a summary line (research/LINUX_DRIFT.md "Værktøj", 2026-10-22): exit code, tests run, failures,
# duration, the 15 slowest tests, and that no test left data/ingest or data/lab/hypotheses behind.
# Usage: scripts/suite.sh [LOG]   (default LOG: /tmp/copybot-suite.log). Runs with nice 10 so the lab keeps priority.
cd "$(dirname "$0")/.." || exit 2
LOG=${1:-/tmp/copybot-suite.log}
T0=$(date +%s)
timeout 2700 nice -n 10 python3 -m unittest discover -s tests --durations 15 > "$LOG" 2>&1
RC=$?
T1=$(date +%s)
RAN=$(grep -aoE "^Ran [0-9]+ tests" "$LOG" | tail -1)
RES=$(grep -aE "^(OK|FAILED)" "$LOG" | tail -1)
LEFT=$(ls -d data/ingest data/lab/hypotheses 2>/dev/null | tr '\n' ' ')
echo "SUITE exit=$RC ${RAN:-Ran ? tests} result=${RES:-none (timeout 2700 s?)} seconds=$((T1 - T0)) left_behind=${LEFT:-none} log=$LOG"
grep -aE "^(FAIL|ERROR):" "$LOG" | head -20
sed -n '/^Slowest test durations/,/^$/p' "$LOG" | head -18
[ "$RC" = 0 ] && [ -z "$LEFT" ]
