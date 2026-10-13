"""Refresh the dashboard's stores after a new checker run, so what is said on the call is still true.

    python tools/recheck_update.py <new batch dir> <db snapshot dir> <out dir> [versions.json]

For every store already in the database (the snapshot from ArtifactData list with out_dir): rebuild the
Claude-owned fields (fund, aabning, n_vigtige, prio, score, phone, tjekket) from the new result and write an
update only where something changed. A store whose important problems are all gone gets status "rettet"
(only while it has not been called). Unreachable stores keep their old data. Call outcomes (status, log,
kontakt, ordre, note, ...) are never touched otherwise. Writes <out>/<domain>.json and <out>/_batch_N.json
(ArtifactData batch entries pinned with if_version; versions.json maps doc id -> version from a fresh
listing, because the snapshot files hold only the document fields)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from call_sheet import CONCRETE_WARN, SEV  # noqa: E402
from dashboard_seed import SAY_PREFER, heading, phone_parts, priority, say_line, tidy  # noqa: E402

FIELDS = ("fund", "aabning", "n_vigtige", "prio", "score", "tel", "telefon", "email_side", "cvr")


def fresh(r, old):
    """New Claude-owned fields for one store, None when the new result cannot be trusted."""
    if not (r.get("reachable") and r.get("shopify")) or r.get("password"):
        return None
    fails = sorted([c for c in r["checks"] if c["status"] == "fejl"], key=lambda c: SEV[c["severity"]])
    cwarn = sorted([c for c in r["checks"] if c["status"] == "advarsel" and c["id"] in CONCRETE_WARN], key=lambda c: SEV[c["severity"]])
    if not fails and not cwarn:
        return {"rettet": True}
    other = sorted([c for c in r["checks"] if c["status"] == "advarsel" and c not in cwarn], key=lambda c: SEV[c["severity"]])
    ph = phone_parts((r.get("contact") or {}).get("phone")) or (old.get("tel"), old.get("telefon"))
    ct = r.get("contact") or {}
    return {"fund": [{"id": c["id"], "s": c["status"], "t": heading(c),
                      "hvad": tidy(" ".join(map(str, c["evidence"])) if isinstance(c["evidence"], list) else str(c["evidence"])),
                      "hvorfor": c["why"], "ret": c["fix"]} for c in fails + cwarn + other],
            "aabning": say_line(fails, cwarn, SAY_PREFER.get(r["domain"])), "n_vigtige": len(fails) + len(cwarn),
            "prio": priority(r, fails, cwarn), "score": r.get("score"), "tel": ph[0], "telefon": ph[1],
            "email_side": ct.get("email") or old.get("email_side", ""), "cvr": ct.get("cvr") or old.get("cvr", ""),
            "tjekket": r.get("checked_at", ""), "tjek_version": r.get("checker_version", "")}


def main(batch_dir, snap_dir, out_dir, versions=None):
    os.makedirs(out_dir, exist_ok=True)
    vers = json.load(open(versions, encoding="utf-8")) if versions else {}
    writes, report = [], {"uaendret": [], "opdateret": [], "rettet": [], "kunne_ikke_tjekkes": []}
    for name in sorted(os.listdir(snap_dir)):
        snap = json.load(open(os.path.join(snap_dir, name), encoding="utf-8"))
        old, dom = snap.get("data", snap), snap.get("id") or name[:-5]
        ver = vers.get(dom) or snap.get("version")
        try:
            r = json.load(open(os.path.join(batch_dir, dom + ".json"), encoding="utf-8"))
        except (OSError, ValueError):
            r = {}
        new = fresh(r, old) if r else None
        if new is None:
            report["kunne_ikke_tjekkes"].append(dom)
            continue
        if new.get("rettet"):
            if (old.get("status") or "ny") == "ny" and not old.get("log"):
                upd = {"status": "rettet"}
                report["rettet"].append(dom)
            else:
                report["uaendret"].append(dom)
                continue
        else:
            upd = {k: new[k] for k in FIELDS if new[k] != old.get(k)}
            if not upd:
                report["uaendret"].append(dom)
                continue
            upd.update(tjekket=new["tjekket"], tjek_version=new["tjek_version"])
            report["opdateret"].append((dom, sorted(k for k in upd if k not in ("tjekket", "tjek_version"))))
        path = os.path.abspath(os.path.join(out_dir, dom + ".json"))
        json.dump(upd, open(path, "w", encoding="utf-8"), ensure_ascii=False)
        writes.append({"op": "update", "collection": "stores", "doc_id": dom, "if_version": ver, "file_path": path})
    for i in range(0, len(writes), 50):
        json.dump(writes[i:i + 50], open(os.path.join(out_dir, f"_batch_{i // 50 + 1}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(report, open(os.path.join(out_dir, "_report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print({k: len(v) for k, v in report.items()}, "writes:", len(writes))


if __name__ == "__main__":
    main(*sys.argv[1:5])
