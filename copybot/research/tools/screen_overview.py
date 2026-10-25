"""Overview of the registered explore0 screenings (m21c, m21f, m21h, m21i, m21j), read from their committed result
files only: nothing is recomputed, no threshold is changed, no variant is rerun.

  python3 research/tools/screen_overview.py            markdown table to stdout
  python3 research/tools/screen_overview.py --json     the same rows as JSON
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ("MOVESCREEN_m21c", "DISCOVERY_m21f", "FUNDING_m21h", "SPOTPERP_m21i", "NEWINFO_m21j")
P_SCREEN, P_WEAK, MIN_POWERED = 0.005, 0.05, 60


def rows():
    out = []
    for name in FILES:
        path = os.path.join(HERE, "studies", f"{name}.json")
        with open(path) as f:
            d = json.load(f)
        for r in d["results"]:
            h = r.get("halves") or {}
            h20, h21 = (h.get("2020") or [None, None]), (h.get("2021") or [None, None])
            pl = r.get("placebo") or {}
            hurdle = r.get("cost_hurdle", 0.0046)
            mean, p, se = r.get("mean"), r.get("p"), r.get("se")
            failed = [k for k, v in (r.get("checks") or {}).items() if not v]
            why = []
            if p is not None and p > P_WEAK:
                why.append("ingen påviselig effekt (p > 0,05)")
            elif p is not None and p > P_SCREEN:
                why.append("svagt signal (0,005 < p ≤ 0,05)")
            if h20[1] is not None and h21[1] is not None and h20[1] * h21[1] < 0:
                why.append("fortegnsskift 2020/2021 (ustabilt)")
            if mean is not None and abs(mean) < hurdle:
                why.append("effekt under omkostningskravet")
            if (r.get("n_clusters") or 0) < MIN_POWERED:
                why.append(f"lille stikprøve (< {MIN_POWERED} klynger)")
            out.append({"file": name, "key": r["key"], "window": r.get("window"), "n_events": r.get("n_events"),
                        "n_clusters": r.get("n_clusters"), "mean_bp": None if mean is None else mean * 1e4,
                        "se_bp": None if se is None else se * 1e4, "t": None if not se else mean / se, "p": p,
                        "half_2020": h20, "half_2021": h21, "placebo_p": pl.get("p"),
                        "placebo_clusters": pl.get("n_clusters"), "cost_hurdle_bp": hurdle * 1e4,
                        "verdict": r.get("verdict"), "failed_checks": failed, "classification": why,
                        "excluded": r.get("excluded"), "events_sha256": r.get("events_sha256"),
                        "code_commit": d.get("code_commit")})
    return out


def fmt(x, nd=1):
    return "–" if x is None else f"{x:.{nd}f}"


def markdown(rs):
    lines = ["| # | Nøgle | Klynger (hændelser) | Gns. bp (se) | t | p | 2020 / 2021 bp | Placebo p | Krav bp | "
             "Dom | Fejlede krav | Klassifikation |", "|" + "---|" * 12]
    for i, r in enumerate(rs, 1):
        h = f"{fmt(r['half_2020'][1] and r['half_2020'][1] * 1e4)} / {fmt(r['half_2021'][1] and r['half_2021'][1] * 1e4)}"
        lines.append(f"| {i} | `{r['key']}` | {r['n_clusters']} ({r['n_events']}) | {fmt(r['mean_bp'])} "
                     f"({fmt(r['se_bp'])}) | {fmt(r['t'], 2)} | {fmt(r['p'], 3)} | {h} | {fmt(r['placebo_p'], 3)} | "
                     f"{fmt(r['cost_hurdle_bp'], 0)} | {r['verdict']} | {'; '.join(r['failed_checks'])} | "
                     f"{'; '.join(r['classification'])} |")
    return "\n".join(lines)


if __name__ == "__main__":
    rs = rows()
    print(json.dumps(rs, indent=1, ensure_ascii=False) if "--json" in sys.argv else markdown(rs))
