"""Director addendum 59 B: reproducible reconciliation of the daily lane report (lab `lane.report`, artifact
data/lab/artifacts/_lane/<day>.json) against the net report (research/data/net_report/net_<day+1>.json).

Read-only: the artifact and the net-report JSON are read as files; lab.db is opened with mode=ro and query_only, and only
sim_equity is read. Nothing is written except the optional --out markdown. Per account it shows both nets, the
difference and the two equity marks each total used (lane report: last mark with ts < day end; net report: the latest
mark at its run time), and checks that each net equals the equity at its own mark minus capital.
"""
import argparse
import json
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROD = os.path.expanduser("~/ecommerence/copybot")
DAY = 86400
TOL = 0.005


def day_start(day):
    return int(time.mktime(time.strptime(day, "%Y-%m-%d"))) - time.timezone


def hm(ts):
    return time.strftime("%m-%d %H:%M:%S", time.gmtime(ts)) if ts is not None else "–"


def ro(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def reconcile(lane, net, con, day):
    end = day_start(day) + DAY
    lr = {r["ledger"]: r for r in lane["accounts"]}
    nr = {a["ledger"]: a for a in net["accounts"]}
    rows = []
    for led in sorted(set(lr) | set(nr)):
        a, b = lr.get(led), nr.get(led)
        cap = float(b["capital"]) if b else 10000.0
        before = con.execute("SELECT ts, equity FROM sim_equity WHERE exp_id=? AND ts<? ORDER BY id DESC LIMIT 1",
                             (led, end)).fetchone()
        at = con.execute("SELECT ts, equity FROM sim_equity WHERE exp_id=? AND ts<=? ORDER BY id DESC LIMIT 1",
                         (led, b["marked_at"])).fetchone() if b and b.get("marked_at") is not None else None
        r = {"ledger": led, "source": (b or a or {}).get("source"),
             "lane_net": a["net"] if a else None, "net_net": b["net"] if b else None,
             "lane_mark": before[0] if before else None, "net_mark": b.get("marked_at") if b else None,
             "lane_ok": bool(a and before and abs(before[1] - cap - a["net"]) <= TOL),
             "net_ok": bool(b and at and abs(at[1] - cap - b["net"]) <= TOL)}
        r["diff"] = (r["net_net"] or 0.0) - (r["lane_net"] or 0.0)
        r["cause"] = ("SAME_MARK" if abs(r["diff"]) <= TOL and r["lane_mark"] == r["net_mark"] else
                      "TIMING_MARK" if r["lane_ok"] and r["net_ok"] and r["lane_mark"] != r["net_mark"] else
                      "UNEXPLAINED")
        r["stale_h"] = (end - r["lane_mark"]) / 3600 if r["lane_mark"] else None
        rows.append(r)
    lt = sum(r["lane_net"] or 0.0 for r in rows)
    nt = sum(r["net_net"] or 0.0 for r in rows)
    explained = sum(r["diff"] for r in rows if r["cause"] in ("SAME_MARK", "TIMING_MARK"))
    status = ("RECONCILED" if all(r["cause"] != "UNEXPLAINED" for r in rows) and abs((nt - lt) - explained) <= TOL
              else "ACCOUNTING_UNRECONCILED")
    return {"day": day, "day_end_utc": hm(end), "lane_total": lt, "net_total": nt, "difference": nt - lt,
            "explained_by_timing": explained, "status": status, "accounts": rows,
            "lane_accounts": len(lr), "net_accounts": len(nr)}


def markdown(res, lane_path, net_path):
    out = [f"# Afstemning lane-rapport {res['day']} mod netrapport (direktørtillæg 59 B)", "",
           f"- Lane-rapport: `{lane_path}` (sidste mærkning med ts < {res['day_end_utc']} UTC).",
           f"- Netrapport: `{net_path}` (seneste mærkning ved kørslen).",
           f"- Konti: {res['lane_accounts']} / {res['net_accounts']}.",
           f"- Totaler: lane {res['lane_total']:.2f}, netrapport {res['net_total']:.2f}, forskel "
           f"{res['difference']:.2f}; forklaret af mærketidspunkt {res['explained_by_timing']:.2f}.",
           f"- **Status: {res['status']}**", "",
           "| Konto | Kilde | Lane netto | Lane-mærke (UTC) | Net netto | Net-mærke (UTC) | Forskel | Årsag | Mærke før dagsslut (t) |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in res["accounts"]:
        out.append(f"| {r['ledger'][-6:]} | {r['source']} | {r['lane_net']:.2f} | {hm(r['lane_mark'])} | "
                   f"{r['net_net']:.2f} | {hm(r['net_mark'])} | {r['diff']:+.2f} | {r['cause']} | "
                   f"{r['stale_h']:.1f} |")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--lane", help="lane report artifact (default: production artifacts/_lane/<day>.json)")
    ap.add_argument("--net", help="net report JSON (default: research/data/net_report/net_<day+1>.json)")
    ap.add_argument("--db", default=os.path.join(PROD, "data", "lab", "lab.db"))
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    nxt = time.strftime("%Y-%m-%d", time.gmtime(day_start(a.day) + DAY))
    lane_path = a.lane or os.path.join(PROD, "data", "lab", "artifacts", "_lane", f"{a.day}.json")
    net_path = a.net or os.path.join(HERE, "research", "data", "net_report", f"net_{nxt}.json")
    with open(lane_path, encoding="utf-8") as f:
        lane = json.load(f)
    with open(net_path, encoding="utf-8") as f:
        net = json.load(f)
    con = ro(a.db)
    try:
        res = reconcile(lane, net, con, a.day)
    finally:
        con.close()
    md = markdown(res, lane_path, net_path)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(md)
    print(md)
    return 0 if res["status"] == "RECONCILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
