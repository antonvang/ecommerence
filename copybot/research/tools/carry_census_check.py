"""MISSION27_3 point 9: descriptive forward-census carry check (decides nothing). Needs fundinginfo.json (fapi/v1/fundingInfo) in the cwd."""
import json, sqlite3, statistics as st, collections


def main():
    db = sqlite3.connect("file:/home/anton/ecommerence/copybot/data/lab/lab.db?mode=ro", uri=True)
    iv = {x["symbol"]: int(x["fundingIntervalHours"]) for x in json.load(open("fundinginfo.json"))}
    B1, B2, VOL = 0.32, 0.108, 20e6
    hours = {}
    for ts, pl in db.execute("SELECT ts,payload FROM observations WHERE detector='census/1' AND metric='snapshot' ORDER BY id"):
        p = json.loads(pl); t = (p.get("premium_fetched_at") or ts) // 3600 * 3600
        cols = p["columns"]; rows = {}
        for s, r in p["rows"].items():
            d = dict(zip(cols, r))
            try: f = float(d["lastFundingRate"]); v = float(d["quoteVolume"])
            except (TypeError, ValueError, KeyError): continue
            rows[s] = (f * 24 / iv.get(s, 8) * 365, v)
        hours[t] = rows
    ts = sorted(h for h in hours if sum(v >= VOL for _, v in hours[h].values()) > 0); print("zero-liquid hours", len(hours) - len(ts)); print("hours", len(ts), ts[0], ts[-1])
    liq = lambda h: {s: a for s, (a, v) in hours[h].items() if v >= VOL}
    n1, n2, nl = [], [], []
    for h in ts:
        L = liq(h); nl.append(len(L)); n1.append(sum(a > B1 for a in L.values())); n2.append(sum(a > B2 for a in L.values()))
    print("liquid per hour median", st.median(nl), "above B1 median/max", st.median(n1), max(n1), "above B2 median/max", st.median(n2), max(n2))
    print("share above B1 median %.3f" % st.median([a / b for a, b in zip(n1, nl)]), "B2 %.3f" % st.median([a / b for a, b in zip(n2, nl)]))
    # persistence
    pers = collections.defaultdict(list); realised = []
    for i, h in enumerate(ts):
        for s, a in liq(h).items():
            if a <= B1: continue
            for k in (24, 48, 72, 120):
                h2 = h + k * 3600
                if h2 in hours and s in hours[h2]: pers[k].append(hours[h2][s][0] > B1)
            fut = [hours[h + j * 3600][s][0] for j in range(1, 73) if h + j * 3600 in hours and s in hours[h + j * 3600]]
            if len(fut) >= 60: realised.append(st.fmean(fut))
    for k in sorted(pers): print("persist", k, "h: n", len(pers[k]), "share still > B1 %.3f" % (sum(pers[k]) / len(pers[k])))
    if realised:
        realised.sort(); print("realised next 72h APR: n", len(realised), "median %.3f mean %.3f p25 %.3f p75 %.3f" % (st.median(realised), st.fmean(realised), realised[len(realised)//4], realised[3*len(realised)//4]), "share > B1 %.3f" % (sum(r > B1 for r in realised)/len(realised)))
    # distinct symbols ever above B1 (liquid), and their duration
    ever = collections.Counter(s for h in ts for s, a in liq(h).items() if a > B1)
    print("distinct liquid symbols ever > B1", len(ever), ever.most_common(12))
    # negative side for info
    neg = [sum(a < -B1 for a in liq(h).values()) for h in ts]; print("liquid below -B1 median/max", st.median(neg), max(neg))
    eu = json.load(open("/home/anton/copybot-dev/copybot/research/data/eu_venue_markets.json"))["venues"]
    eucoins = set(c for vv in eu.values() for c in vv["coins"])
    base = lambda s: s[:-4].removeprefix("1000000").removeprefix("1000")
    ok = {s for s in ever if base(s) in eucoins}
    print("ever>B1 with EU spot", len(ok), "of", len(ever), sorted(ok, key=lambda s: -ever[s])[:15])
    # restrict realised/persistence to EU-spot symbols
    r2 = []; p72 = []
    for h in ts:
        for s, a in liq(h).items():
            if a <= B1 or s not in ok: continue
            fut = [hours[h + j * 3600][s][0] for j in range(1, 73) if h + j * 3600 in hours and s in hours[h + j * 3600]]
            if len(fut) >= 60: r2.append(st.fmean(fut))
            h2 = h + 72 * 3600
            if h2 in hours and s in hours[h2]: p72.append(hours[h2][s][0] > B1)
    r2.sort()
    print("EU-spot: hours-x-symbols >B1 per hour median", st.median([sum(1 for s,a in liq(h).items() if a>B1 and s in ok) for h in ts]))
    if r2: print("EU-spot realised 72h APR n", len(r2), "median %.3f mean %.3f share>B1 %.3f" % (st.median(r2), st.fmean(r2), sum(x>B1 for x in r2)/len(r2)), "persist72 %.3f n %d" % (sum(p72)/len(p72), len(p72)))


if __name__ == "__main__":
    main()
