#!/usr/bin/env bash
# pm_lp_v1 indsamler paa Linux (observationsstudie: ingen ordrer, ingen konto, kun offentlige API'er).
# research/PM_LP_SPEC.md amendment 3: Linux er eneste vaert; D0 laeses fra databasen; kun én indsamler ad gangen.
#
# Start i baggrunden (fra mappen copybot):
#   setsid nohup ./START_PM_LP.sh >> data/research/pm_lp/collector.log 2>&1 < /dev/null &
# Stop: kill <pid> (se: pgrep -af research.pm_lp). Huller i indsamlingen taeller i D1, som protokollen siger.
set -euo pipefail
cd "$(dirname "$0")"

PY=python3
DB=data/research/pm_lp/pm_lp.db
if [ ! -f "$DB" ]; then
  echo "$DB mangler. Den eksisterende database skal flyttes hertil (PM_LP_SPEC amendment 3); ingen ny start." >&2
  exit 1
fi
"$PY" - "$DB" <<'EOF'
import sqlite3, sys
con = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
ok = con.execute("PRAGMA quick_check").fetchone()[0]
d0 = con.execute("SELECT v FROM meta WHERE k='D0'").fetchone()
if ok != "ok" or d0 is None:
    sys.exit(f"pm_lp.db er ikke i orden (quick_check={ok}, D0={d0}): ingen start")
EOF

echo "$(date -u +%FT%TZ) START_PM_LP.sh paa $(hostname)"
# Hold maskinen vaagen mens indsamleren koerer (som keepawake.ps1 paa Windows); aendrer ingen indstillinger.
if command -v systemd-inhibit >/dev/null && \
   systemd-inhibit --what=sleep:idle --who=pm_lp_v1 --why=probe --mode=block true 2>/dev/null; then
  exec systemd-inhibit --what=sleep:idle --who=pm_lp_v1 --why="pm_lp_v1 indsamling" --mode=block \
    "$PY" -u -m research.pm_lp collect --approved
fi
echo "ADVARSEL: dvale kan ikke blokeres herfra (systemd-inhibit kraever en lokal session). Gaar maskinen i dvale," \
     "stopper indsamlingen, og hullet taeller i D1." >&2
exec "$PY" -u -m research.pm_lp collect --approved
