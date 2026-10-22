"""Obsidian vault (research/LINUX_DRIFT.md, 2026-10-22): a read-only, linked Markdown view of the lab for the user.

The agent vault-1 rewrites `data/vault/Lab/` once an hour from the registry and the committed protocol: one note per
hypothesis (screen, lock, measurement; negative results included), per protocol amendment, per paper ledger, per
experiment and per daily lane report, plus an index. Only `Lab/` is written; anything else in the vault (the user's
own notes) is never read or touched. A note is display only: decisions live in the registry and the protocol.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone

from lab.db import HERE

ROOT = os.path.join(HERE, "data", "vault")
SUB = "Lab"
PROTOCOL = os.path.join(HERE, "research", "PROTOCOL_V3.md")
EVERY = 3600
HEAD = re.compile(r"^## (Ændring|Rettelse|Præcisering)([^\n]*)$", re.M)
AMEND = re.compile(r"^## Ændring ([0-9][0-9a-z]*(?: og [0-9][0-9a-z]*)?) \((\d{4}-\d{2}-\d{2})\)")
LABEL = "> Genereret af labbet (vault-1). Kun visning: afgørelser står i registret og i protokollen. Simuleret, aldrig bevis."


def _ts(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if t else "–"


def _safe(name):
    return re.sub(r'[\\/:*?"<>|#^\[\]]', "_", name).strip()[:120]


def _num(x, nd=4):
    return "–" if x is None else f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def _pct(x):
    return "–" if x is None else f"{x * 100:+.2f} %"


def amendments(text):
    """[(id, date, title, body)] of the protocol's '## Ændring <id> (<date>): <title>' sections, in file order."""
    out, heads = [], list(HEAD.finditer(text))
    for i, h in enumerate(heads):
        m = AMEND.match(h.group(0))
        if not m:
            continue
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        title = h.group(0).split("):", 1)[1].strip() if "):" in h.group(0) else ""
        out.append((m.group(1), m.group(2), title, text[h.start():end].strip()))
    return out


def _amend_link(rule):
    m = re.search(r"amendment (\S+)", rule or "")
    return f"[[Ændring {m.group(1)}]]" if m else "–"


def notes(db, now=None, protocol_text=None):
    """{relative path: markdown} for every generated note (pure: reads the registry and the protocol text only)."""
    from lab import command, hypogen, measure, registry
    now = now or time.time()
    out = {}
    if protocol_text is None:
        with open(PROTOCOL, encoding="utf-8") as f:
            protocol_text = f.read()
    am = amendments(protocol_text)
    for aid, date, title, body in am:
        out[f"Ændringer/Ændring {aid}.md"] = (f"---\ntype: ændring\ndato: {date}\n---\n# Ændring {aid} ({date})\n\n"
                                              f"{LABEL}\n\n**{title}**\n\nKilde: `research/PROTOCOL_V3.md`\n\n"
                                              + body.split("\n", 1)[1].strip() + "\n")
    # hypotheses: candidates, screens and locked measurements
    res = hypogen.results(db)
    meas = {}
    for r in db.q("SELECT ts, payload FROM events WHERE kind=? ORDER BY id", measure.EVENT):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        if p.get("hypothesis"):
            meas[p["hypothesis"]] = p | {"ts": r["ts"]}
    cands = hypogen.candidates(db, now)
    locks = {k for k, *_ in hypogen.cached_locks(db, now)}
    rows = []
    for c in cands:
        k, s = c["key"], res.get(c["key"]) or {}
        m = meas.get(k)
        status = m["verdict"] if m else ("LÅST" if k in locks else c["status"])
        rows.append((k, c["type"], c["outcome"], status, s.get("n"), s.get("mean"), s.get("p")))
        lines = [f"---\ntype: hypotese\nstatus: {status}\nbegivenhed: {c['type']}\nudfald: {c['outcome']}\n---",
                 f"# {k}\n", LABEL + "\n",
                 f"- **Regel:** {_amend_link(c.get('rule') or s.get('rule') or hypogen.RULE)}",
                 f"- **Begivenhedstype:** [[Type {c['type']}]] · **udfald:** `{c['outcome']}`",
                 f"- **Status:** {status} · **begivenheder i explore0:** {c['events']} · **prioritet:** {c['priority']}"]
        if s:
            lines += ["", "## Screening (explore0, aldrig bevis)",
                      f"- Afgørelse: **{s.get('verdict')}** — {s.get('reason')}",
                      f"- n {s.get('n')} · gennemsnit {_pct(s.get('mean'))} · median {_pct(s.get('median'))} · "
                      f"p {_num(s.get('p'))}",
                      f"- Placebo (t − 30 d): {json.dumps(s.get('placebo'), ensure_ascii=False)}" if s.get("placebo")
                      else "- Placebo: –",
                      f"- Screenet {_ts(s.get('ts'))} (hændelse {s.get('event_id')})"]
        if k in locks:
            lines += ["", "## Lås", "Låst i protokollen med `LÅS-17` før måling."]
        if m:
            lines += ["", "## Måling (train3 → validation3)", f"- Afgørelse: **{m['verdict']}** — {m.get('reason')}",
                      f"- alpha {m.get('alpha')} · retning {m.get('direction')}"]
            for ph, v in (m.get("phases") or {}).items():
                lines.append(f"- {ph}: n {v.get('n')} · gennemsnit {_pct(v.get('mean'))} · p {_num(v.get('p'))}")
        out[f"Hypoteser/{_safe(k.replace('|', ' '))}.md"] = "\n".join(lines) + "\n"
    types = sorted({r[1] for r in rows})
    for t in types:
        mine = [r for r in rows if r[1] == t]
        out[f"Hypoteser/Type {t}.md"] = (f"# Type {t}\n\n{LABEL}\n\n| Hypotese | Status | n | Gennemsnit | p |\n|---|---|---|---|---|\n"
                                         + "".join(f"| [[{_safe(k.replace('|', ' '))}]] | {st} | {_num(n)} | {_pct(mu)} | "
                                                   f"{_num(p)} |\n" for k, _, _, st, n, mu, p in mine))
    # paper ledgers (lane, scanner, HL, forward, shadow)
    lv = command.lane_view(db, now)
    accts = {a["ledger"]: a for a in lv["active"] + lv["recent"]}
    pv = command.paper_view(db, reconcile=False, edges=False, now=now)["strategies"]
    for s in pv:
        led = s["exp_id"]
        a = accts.get(led) or {}
        kind = ("HL-konto" if a.get("hl") else "scannerkonto" if a.get("scanner") else "banekonto" if s.get("lane")
                else "fremadtest" if s.get("forward") else "skyggekonto" if s.get("shadow") else "papirkonto")
        lines = [f"---\ntype: konto\nart: {kind}\naktiv: {str(bool(s.get('active'))).lower()}\n---", f"# {led}\n",
                 LABEL + "\n", f"- **Art:** {kind} · **navn:** {s.get('name') or a.get('name') or '–'}",
                 f"- **Aktiv:** {'ja' if s.get('active') else 'nej'} · **pause:** "
                 f"{(s.get('pause') or {}).get('rule') or 'nej'}",
                 f"- **Værdi:** {_num(s.get('equity'), 2)} $ · **netto:** {_num(s.get('total_pnl'), 2)} $ · "
                 f"**gebyrer:** {_num(s.get('fees'), 2)} $ · **funding:** {_num(s.get('funding'), 2)} $",
                 f"- **Største fald:** {_pct(s.get('max_drawdown'))} · **ordrer:** {s.get('orders')} · "
                 f"**handler lukket:** {s.get('closed_trades')}"]
        if a:
            lines += [f"- **Funktion:** `{a.get('function')}` {json.dumps(a.get('params'), ensure_ascii=False)}",
                      f"- **Mønter:** {', '.join(a.get('coins') or [])} · **holdt:** {', '.join(a.get('held') or [])}",
                      f"- **Startet:** {_ts(a.get('started'))} · **stoppet:** {_ts(a.get('stopped'))} "
                      f"{a.get('stop_detail') or ''}"]
        out[f"Konti/{_safe(led)}.md"] = "\n".join(lines) + "\n"
    # experiments
    for x in registry.status(db):
        out[f"Eksperimenter/{_safe(x['exp_id'])}.md"] = (
            f"---\ntype: eksperiment\ntilstand: {x['state']}\n---\n# {x['exp_id']}\n\n{LABEL}\n\n"
            f"- **Tilstand:** {x['state']} · **mekanisme:** {x.get('mechanism') or '–'} · **version:** {x.get('version')}\n"
            f"- **Afgørelse:** {x.get('verdict') or '–'}\n")
    # daily lane reports
    reps = []
    for r in db.q("SELECT ts, payload FROM events WHERE kind='research.lane_report' ORDER BY id"):
        p = json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"]
        if p.get("day"):
            reps.append(p)
            out[f"Rapporter/Bane {p['day']}.md"] = (
                f"---\ntype: døgnrapport\ndag: {p['day']}\n---\n# Banekonti {p['day']}\n\n{LABEL}\n\n"
                f"- **Konti:** {p.get('accounts')} · **netto i alt:** {_num(p.get('net_total'), 2)} $\n"
                f"- **Opfyldte pilotkriterier:** {', '.join(p.get('met') or []) or 'ingen'}\n"
                f"- **Artefakt:** `{p.get('artifact_sha256')}`\n")
    # index
    by = {}
    for r in rows:
        by[r[3]] = by.get(r[3], 0) + 1
    idx = [f"# Copybot-lab\n\n{LABEL}\n", f"Opdateret {_ts(now)}.\n", "## Hypotesepipeline (ændring 17)",
           " · ".join(f"{k}: {v}" for k, v in sorted(by.items())) + "\n", "Typer: " + ", ".join(f"[[Type {t}]]" for t in types)
           + "\n", "## Konti", "| Konto | Aktiv | Netto $ |\n|---|---|---|"]
    idx += [f"| [[{_safe(s['exp_id'])}]] | {'ja' if s.get('active') else 'nej'} | {_num(s.get('total_pnl'), 2)} |"
            for s in pv]
    idx += ["", "## Døgnrapporter"] + [f"- [[Bane {p['day']}]] · netto {_num(p.get('net_total'), 2)} $"
                                        for p in reps[-14:][::-1]]
    idx += ["", "## Protokolændringer (nyeste først)"] + [f"- [[Ændring {aid}]] ({date}) {title}"
                                                        for aid, date, title, _ in am[::-1]]
    out["Copybot.md"] = "\n".join(idx) + "\n"
    return out


def write(db, root=None, now=None, protocol_text=None):
    """Rewrite `<root>/Lab/` from notes(): changed files only (atomic rename), generated files no longer produced are
    removed; nothing outside Lab/ is touched. Returns counts."""
    base = os.path.join(root or ROOT, SUB)
    want = notes(db, now, protocol_text)
    wrote = 0
    for rel, text in want.items():
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, encoding="utf-8") as f:
                if f.read() == text:
                    continue
        except FileNotFoundError:
            pass
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        wrote += 1
    removed = 0
    for d, _, files in os.walk(base):
        for name in files:
            rel = os.path.relpath(os.path.join(d, name), base)
            if name.endswith(".md") and rel not in want:
                os.remove(os.path.join(d, name))
                removed += 1
    return {"notes": len(want), "written": wrote, "removed": removed, "dir": os.path.relpath(base, HERE)}


def maybe_write(db, now=None, root=None, every=EVERY):
    """Called by strategy-1 each pass: writes the vault at most once per `every` seconds (judged by the index note's
    mtime, so a restart does not rewrite it) and only for the lab's own registry (tests use temporary ones). Never
    raises: a vault error must not stop strategy-1's other work."""
    now = now or time.time()
    if root is None and os.path.abspath(db.path) != os.path.join(HERE, "data", "lab", "lab.db"):
        return None
    idx = os.path.join(root or ROOT, SUB, "Copybot.md")
    try:
        if os.path.exists(idx) and now - os.path.getmtime(idx) < every:
            return None
        res = write(db, root, now)
        os.utime(idx, (now, now))                           # the index marks the last write, changed or not
        return res
    except Exception as e:                                  # noqa: BLE001 - reported in strategy-1's result
        return {"error": repr(e)[:300]}
