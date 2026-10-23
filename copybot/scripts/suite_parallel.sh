#!/bin/bash
# Full test suite split over N isolated git worktrees (research/LINUX_DRIFT.md 2026-10-23). Each worker gets its own
# checkout of HEAD plus a copy of this tree's uncommitted and untracked files, so tests that write under data/ never
# share a directory. Same summary line as scripts/suite.sh. The serial scripts/suite.sh stays the deploy gate until this
# has matched it on repeated runs.
# Usage: scripts/suite_parallel.sh [N=3] [LOGDIR]
cd "$(dirname "$0")/.." || exit 2
N=${1:-3}
LOGDIR=${2:-/tmp/copybot-suite-par}
ROOT=$(git rev-parse --show-toplevel) || exit 2
REL=$(git rev-parse --show-prefix)                       # copybot/
rm -rf "$LOGDIR"; mkdir -p "$LOGDIR"
T0=$(date +%s)
mods=$(ls tests/test_*.py | sort)
# balance by each module's measured seconds from the last run (file size / 2000 until measured), greedy into N bins
WEIGHTS=${COPYBOT_SUITE_WEIGHTS:-$HOME/.cache/copybot-suite-weights}
bins=$(for f in $mods; do w=$(awk -v m="$f" '$2==m {print $1}' "$WEIGHTS" 2>/dev/null); echo "${w:-$(( $(stat -c %s "$f") / 2000 ))} $f"; done | sort -rn | awk -v n="$N" '
  {best=0; for(i=1;i<n;i++) if (w[i] < w[best]) best=i; w[best]+=$1; b[best]=b[best] " " $2}
  END {for(i=0;i<n;i++) print b[i]}')
changed=$(git ls-files -m -o --exclude-standard . )
i=0; pids=()
while read -r group; do
  [ -z "$group" ] && continue
  wt="$LOGDIR/wt$i"
  git worktree add --detach -q "$wt" HEAD || exit 2
  for f in $changed; do mkdir -p "$wt/$REL$(dirname "$f")"; cp -p "$f" "$wt/$REL$f"; done
  ( cd "$wt/$REL" && timeout 2700 nice -n 10 python3 -m unittest --durations 0 $(echo $group | sed 's#tests/\([^ ]*\)\.py#tests.\1#g') \
      > "$LOGDIR/part$i.log" 2>&1; echo $? > "$LOGDIR/rc$i" ) &
  pids+=($!); i=$((i+1))
done <<< "$bins"
wait "${pids[@]}"
T1=$(date +%s)
RC=0; RAN=0; FAILS=""
for j in $(seq 0 $((i-1))); do
  r=$(cat "$LOGDIR/rc$j"); [ "$r" != 0 ] && RC=1
  n=$(grep -aoE "^Ran [0-9]+ tests" "$LOGDIR/part$j.log" | grep -oE "[0-9]+"); RAN=$((RAN + ${n:-0}))
  FAILS="$FAILS$(grep -aE "^(FAIL|ERROR):" "$LOGDIR/part$j.log")"
  LEFT="$LEFT$(ls -d "$LOGDIR/wt$j/${REL}data/ingest" "$LOGDIR/wt$j/${REL}data/lab/hypotheses" 2>/dev/null | tr '\n' ' ')"
done
for j in $(seq 0 $((i-1))); do git worktree remove --force "$LOGDIR/wt$j"; done
# per-module seconds for the next run's balance (from --durations 0: "1.234s    test_x (tests.test_mod.Class.test_x)")
mkdir -p "$(dirname "$WEIGHTS")"
cat "$LOGDIR"/part*.log | sed -nE 's/^ *([0-9.]+)s +[^ ]+ \(tests\.(test_[a-z0-9_]+)\..*/\1 tests\/\2.py/p' \
  | awk '{s[$2]+=$1} END {for (m in s) printf "%d %s\n", s[m]+1, m}' | sort -rn > "$WEIGHTS.new" \
  && [ -s "$WEIGHTS.new" ] && mv "$WEIGHTS.new" "$WEIGHTS"
echo "SUITE-PAR exit=$RC Ran $RAN tests workers=$i result=$([ $RC = 0 ] && echo OK || echo FAILED) seconds=$((T1 - T0)) left_behind=${LEFT:-none} logs=$LOGDIR"
[ -n "$FAILS" ] && echo "$FAILS" | head -20
[ "$RC" = 0 ] && [ -z "$LEFT" ]
