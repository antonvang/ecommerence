"""Power audit of decided return screens (descriptive, read-only; changes no verdict).

For each screen with a return outcome: SE of the tested mean, the minimum detectable effect at the screen's own
two-sided p <= 0.005 with 80 % power (normal approximation), and the 99.5 % upper bound of |mean|, both against
the screen's cost hurdle. Sources: research.hypothesis_screen events (m17*, per-event y in 'used') and the committed
research/studies/*_m21*.json (se stored). No network, no new data, no holdout.
"""
import glob, json, math, os, sqlite3, statistics, sys
from statistics import NormalDist

Z_A, Z_B = NormalDist().inv_cdf(1 - 0.005 / 2), NormalDist().inv_cdf(0.80)
RETURNS = ("ar_", "far_", "sar_")
COST = 0.0046


def m17(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    last = {}
    for (pl,) in con.execute("SELECT payload FROM events WHERE kind='research.hypothesis_screen' ORDER BY id"):
        p = json.loads(pl)
        last[p["key"]] = p
    out = []
    for k, p in sorted(last.items()):
        if p.get("verdict") not in ("SCREEN_FAIL", "SCREEN_PASS") or not str(p.get("outcome", "")).startswith(RETURNS):
            continue
        ys = [u[3] for u in p.get("used") or []]
        if len(ys) != p.get("n"):                    # 'used' is capped at 400 rows
            se, src = None, f"used {len(ys)} of n {p.get('n')}"
        else:
            se, src = statistics.stdev(ys) / math.sqrt(len(ys)), "event sd/sqrt(n)"
        out.append({"key": k, "verdict": p["verdict"], "n": p["n"], "mean": p.get("mean"), "p": p.get("p"),
                    "se": se, "se_source": src, "hurdle": COST})
    return out


def m21(root):
    out = []
    for f in sorted(glob.glob(os.path.join(root, "*_m21*.json"))):
        for r in json.load(open(f)).get("results") or []:
            if r.get("verdict") not in ("SCREEN_FAIL", "SCREEN_PASS") or r.get("mean") is None:
                continue
            se, src = r.get("se"), "stored se (day clusters)"
            if se is None and r.get("p") not in (None, 0, 1):
                se, src = abs(r["mean"]) / NormalDist().inv_cdf(1 - r["p"] / 2), "derived from p (rough)"
            out.append({"key": r["key"], "verdict": r["verdict"], "n": r.get("n_clusters"), "mean": r["mean"],
                        "p": r.get("p"), "se": se, "se_source": src, "hurdle": r.get("cost_hurdle") or COST})
    return out


def classify(r):
    if r["se"] is None:
        return dict(r, mde=None, upper=None, klasse="ukendt (SE mangler)")
    mde, upper = (Z_A + Z_B) * r["se"], abs(r["mean"]) + Z_A * r["se"]
    k = ("udelukket: en fordel på gulvets størrelse er usandsynlig" if upper < r["hurdle"] else
         "styrke nok, men ikke udelukket" if mde <= r["hurdle"] else "for lav styrke: kunne ikke se en fordel på gulvet")
    return dict(r, mde=mde, upper=upper, klasse=k, n_required=r["n"] * (mde / r["hurdle"]) ** 2)


if __name__ == "__main__":
    db, studies = sys.argv[1], sys.argv[2]
    rows, seen = [classify(r) for r in m17(db) + m21(studies)], {}
    for r in rows:                                   # m17e re-ran some m17 keys on identical events
        sig = (round(r["mean"], 10), r["n"])
        r["duplicate_of"] = seen.get(sig)
        seen.setdefault(sig, r["key"])
    json.dump({"z_alpha": Z_A, "z_power": Z_B, "rows": rows}, sys.stdout, indent=1)
