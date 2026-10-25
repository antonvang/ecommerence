"""Dashboard market events (research/LINUX_DRIFT.md 2026-10-24 23:11): one list of the last 72 hours from records that
already exist - investigated moves, data pauses, on-chain revisions and empty books. Read-only; nothing is inferred
beyond what the records say. News near a move is a coincidence in time, never a cause.
"""
from __future__ import annotations

import json
import time

LOOKBACK_S, CURRENT_S, CO_MOVE_Z = 72 * 3600, 6 * 3600, 2.0
CAUSE_NOTE = "tidsmæssigt sammenfald, ikke årsag"


def _p(raw):
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


def _move(r, now):
    p = _p(r["payload"])
    tri = p.get("triage") or {}
    others = p.get("others") or {}
    co = sorted(s for s, o in others.items() if o.get("z_1h") is not None and abs(o["z_1h"]) >= CO_MOVE_Z)
    news, macro = p.get("news") or [], (p.get("macro") or {}).get("releases") or []
    known = p.get("scan_ts") or r["ts"]
    return {"kind": "move", "id": r["id"], "title": f"{p.get('label') or p.get('instrument')}: "
                                                  f"{', '.join(p.get('flags') or []) or 'flag'}",
            "instrument": p.get("instrument"), "class": p.get("class"),
            "occurred_ts": p.get("move_hour_s"), "occurred_end_ts": (p["move_hour_s"] + 3600) if p.get("move_hour_s") else None,
            "known_ts": known, "current": now - known <= CURRENT_S,
            "markets": [p.get("instrument")] + co, "co_moving": co,
            "evidence": {"z_1h": p.get("z_1h"), "z_24h": p.get("z_24h"), "ret_1h": p.get("ret_1h"),
                         "ret_24h": p.get("ret_24h"), "volume_ratio": p.get("volume_ratio"),
                         "sigma_1h": p.get("sigma_1h"), "tails_720h": p.get("tails_720h"),
                         "book_round_trip": (p.get("book") or {}).get("round_trip")},
            "news": [{"title": n.get("title"), "source": n.get("source"), "published_ts": n.get("published_ts"),
                      "url": n.get("url")} for n in news[:5]],
            "news_note": CAUSE_NOTE if news else "ingen nyhed i kilderne inden for ±3 timer",
            "macro": macro[:5], "macro_note": None if macro else "ingen planlagt makroudgivelse i kalenderen",
            "explanations": tri.get("explanations") or [], "verdict": tri.get("verdict"), "reason": tri.get("reason"),
            "next": tri.get("next") or p.get("next"), "rule": tri.get("rule") or p.get("rule")}


def view(db, now=None):
    now = now or time.time()
    since = now - LOOKBACK_S
    out = [_move(r, now) for r in db.q("SELECT id, ts, payload FROM events WHERE kind='opportunity.move' AND ts>=? "
                                        "ORDER BY id", since)]
    for r in db.q("SELECT id, ts, exp_id, payload FROM events WHERE kind='risk.pause' AND ts>=? ORDER BY id", since):
        p = _p(r["payload"])
        out.append({"kind": "data_pause", "id": r["id"], "title": f"Pause: {p.get('rule')}", "instrument": None,
                    "occurred_ts": r["ts"], "known_ts": r["ts"], "current": now - r["ts"] <= CURRENT_S,
                    "markets": [], "ledger": r["exp_id"], "evidence": {"detail": p.get("detail")},
                    "next": "løftes selv efter ~1 time med fungerende data (ændring 18)" if p.get("rule") == "data_fetch"
                    else "kræver et menneske", "explanations": [], "news": []})
    for r in db.q("SELECT id, ts, instrument, value, payload FROM observations WHERE detector='onchain/1' AND "
                  "metric='flow_revision' AND ts>=? ORDER BY id", since):
        p = _p(r["payload"])
        out.append({"kind": "onchain_revision", "id": r["id"], "title": f"On-chain revideret: {r['instrument']}",
                    "instrument": r["instrument"], "occurred_ts": r["ts"], "known_ts": r["ts"],
                    "current": now - r["ts"] <= CURRENT_S, "markets": [],
                    "evidence": {"date": p.get("date"), "first": p.get("first"), "revised": r["value"]},
                    "next": "første værdi bruges (point-in-time); revisionen logges kun (21q/21r)",
                    "explanations": [], "news": []})
    for r in db.q("SELECT id, ts, instrument, payload FROM observations WHERE detector='capacity/1' AND metric='error' "
                  "AND ts>=? ORDER BY id", since):
        out.append({"kind": "book_missing", "id": r["id"], "title": f"Ingen bog: {r['instrument']}",
                    "instrument": r["instrument"], "occurred_ts": r["ts"], "known_ts": r["ts"],
                    "current": now - r["ts"] <= 24 * 3600, "markets": [r["instrument"]],
                    "evidence": {"error": _p(r["payload"]).get("error")},
                    "next": "ingen kurve for denne bog; kontrollér markedets status (21v)", "explanations": [],
                    "news": []})
    for r in db.q("SELECT id, ts, payload FROM events WHERE kind='research.k_preflight' AND ts>=? ORDER BY id", since):
        p = _p(r["payload"])                                                     # amendment 21z D point 2
        out.append({"kind": "k_preflight", "id": r["id"], "title": f"K1/K2-weekend {p.get('weekend')}: {p.get('status')}",
                    "instrument": None, "occurred_ts": r["ts"], "known_ts": r["ts"],
                    "current": now - r["ts"] <= 48 * 3600, "markets": [],
                    "evidence": {"reasons": p.get("reasons"), "markets": p.get("markets")},
                    "next": "ingen handling" if p.get("status") == "KLAR" else
                    "ret årsagen før lørdag 00:00 UTC; protokollen ændres ikke (21z D)", "explanations": [], "news": []})
    out.sort(key=lambda e: (e["known_ts"] or 0, e["id"]), reverse=True)
    counts = {}
    for e in out:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    news_n = db.one("SELECT COUNT(*) FROM observations WHERE detector='news/1' AND metric='news_item' AND ts>=?",
                    since)[0]
    return {"events": out, "counts": counts, "news_items_72h": news_n, "now": now, "lookback_h": LOOKBACK_S // 3600,
            "notes": [f"nyheder ved en bevægelse er {CAUSE_NOTE}", "aktuel = højst 6 timer siden Copybot vidste det",
                      "kun hændelser, der allerede er registreret; intet udledes her"]}
