"""Read-only live check after the amendment 9 deploy: balance blocks, reconciliation, funding, scan research jobs.
Runs in ~/ecommerence/copybot on Linux. Works on a backup-API copy of the live DB; also reads /api/balance."""
import json
import sqlite3
import sys
import time
import urllib.request

sys.path.insert(0, ".")
src = sqlite3.connect("file:data/lab/lab.db?mode=ro", uri=True)
dst = sqlite3.connect("/tmp/a9_copy.db")
src.backup(dst)
dst.close()
from lab import command  # noqa: E402
from lab.db import DB  # noqa: E402

db = DB("/tmp/a9_copy.db")
now = time.time()
b = command.balance(db, now)
print("== formal (headline, unchanged)")
print({k: b.get(k) for k in ("capital", "equity", "pnl", "realized", "unrealized", "fees", "funding", "funding_t0")})
print("== forward (simulated, not approved)")
print(json.dumps(b.get("forward"), default=str)[:900])
print("== combined (simulated)")
print(json.dumps(b.get("combined"), default=str)[:900])
print("== reconciliation")
rec = b.get("reconciliation") or {}
print("ok", rec.get("ok"), "problems", rec.get("problems"))
for k, v in rec.items():
    if k not in ("ok", "problems", "ledgers"):
        print(" ", k, v)
print("== per ledger (from paper_view)")
v = command.paper_view(db, reconcile=True, edges=True, now=now)
for s in v["strategies"]:
    eq = s["equity"][-1]["equity"] if s["equity"] else s["capital"]
    print(f"  {s['exp_id']:<34} fwd={str(s['forward']):<5} cap={s['capital']:>7.0f} eq={eq:>10.2f} "
          f"pnl={eq - s['capital']:>7.2f} real={s['realized'] or 0:>7.2f} unreal={s['unrealized'] or 0:>7.2f} "
          f"fees={s['fees']:>6.2f} fund={s['funding']:>8.4f} pos={s['open_positions']} paused={s['paused']} "
          f"rec={(s['reconciliation'] or {}).get('ok')} edge={json.dumps(s.get('edge'), default=str)[:120]}")

print("== funding")
for r in db.q("SELECT id, datetime(ts,'unixepoch') t, kind, substr(payload,1,200) p FROM events WHERE kind IN "
              "('paper.funding_started','paper.funding_gap') ORDER BY id"):
    print(" ", tuple(r))
n = db.one("SELECT COUNT(*), COALESCE(SUM(amount),0), MIN(settle_ts), MAX(settle_ts) FROM sim_funding")
print("  sim_funding rows", n[0], "sum", round(n[1], 6), "settle range",
      n[2] and time.strftime("%Y-%m-%d %H:%M", time.gmtime(n[2])), n[3] and time.strftime("%Y-%m-%d %H:%M",
                                                                                         time.gmtime(n[3])))
for r in db.q("SELECT exp_id, COUNT(*) c, ROUND(SUM(amount),6) s FROM sim_funding GROUP BY exp_id ORDER BY exp_id"):
    print("   ", tuple(r))

print("== scan research jobs")
for r in db.q("SELECT job_id, status, attempts, datetime(next_run,'unixepoch') nr, lease_owner, substr(error,1,120) e "
              "FROM jobs WHERE kind IN ('scan_digest','scan_dossier') ORDER BY created_ts"):
    print(" ", tuple(r))
for r in db.q("SELECT id, datetime(ts,'unixepoch') t, kind, actor, substr(payload,1,300) p FROM events WHERE kind IN "
              "('research.digest','research.dossier') ORDER BY id DESC LIMIT 6"):
    print(" ", tuple(r))

print("== /api/balance (live web)")
try:
    with urllib.request.urlopen("http://127.0.0.1:8770/api/balance", timeout=10) as r:
        live = json.loads(r.read())
    print({k: live.get(k) for k in ("capital", "equity", "pnl")}, "forward" in live, "combined" in live,
          "reconciliation ok", (live.get("reconciliation") or {}).get("ok"))
except Exception as e:
    print("  web error", repr(e))
