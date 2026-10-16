"""Wallet-track records uden fremtidig information: en launch ser kun udfald, der var kendt før dens beslutningstid."""
from __future__ import annotations

OUTCOME_KNOWN_AFTER = 3600   # en tidligere launch tæller først, når grad_ts + 1 time er passeret
EARLY = 60                   # "early buyer" = købte i de første 60 sek
MIN_LAUNCHES = 3


def early_buys(launch):
    """{wallet: SOL købt} i de første EARLY sek (samme grænse som træk: blocktid < grad_ts + EARLY)."""
    cut = launch.g["grad_ts"] + EARLY
    out = {}
    for e in launch.events:
        if e["side"] == "buy" and e["ts"] < cut:
            out[e["trader"]] = out.get(e["trader"], 0.0) + e["sol"]
    return out


def wallet_features(targets, history, outcome, decision=60):
    """For hver target-launch: træk ud fra early buyers' resultater i TIDLIGERE history-launches.

    outcome(launch) -> netto-afkast eller None. Returnerer {mint: dict}. Gennemløb i tidsorden, så hver target kun
    ser history-launches med grad_ts + OUTCOME_KNOWN_AFTER <= target.grad_ts + decision.
    """
    hist = sorted(history, key=lambda x: x.g["grad_ts"])
    hist_info = [(x.g["grad_ts"] + OUTCOME_KNOWN_AFTER, early_buys(x), outcome(x)) for x in hist]
    stats = {}  # wallet -> [n, sum]
    out, j = {}, 0
    for t in sorted(targets, key=lambda x: x.g["grad_ts"]):
        now = t.g["grad_ts"] + decision
        while j < len(hist_info) and hist_info[j][0] <= now:
            _, buyers, oc = hist_info[j]
            if oc is not None:
                for w in buyers:
                    st = stats.setdefault(w, [0, 0.0])
                    st[0] += 1
                    st[1] += oc
            j += 1
        eb = early_buys(t)
        total = sum(eb.values())
        known = {w: stats[w][1] / stats[w][0] for w in eb if w in stats and stats[w][0] >= MIN_LAUNCHES}
        ksol = sum(eb[w] for w in known)
        out[t.g["mint"]] = {
            "early_buyers": len(eb),
            "known_buyers": len(known),
            "smart_count": sum(1 for s in known.values() if s > 0),
            "smart_wscore": (sum(eb[w] * s for w, s in known.items()) / ksol) if ksol else None,
            "bad_share": (sum(eb[w] for w, s in known.items() if s < -0.3) / total) if total else 0.0,
            "history_used": j,
        }
    return out
