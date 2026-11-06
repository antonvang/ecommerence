"""Director order 46 P0 + P1: cost and capital realism of the carry books under public Kraken fees. Read-only.

    python3 research/tools/carry_realism.py [--db PATH] [--out DIR]

P0  For a long-spot / short-perp carry, the round trip as a share of the perp notional under Kraken's published
    lowest-tier fees (KRAKEN below; research/studies/DK_RETAIL_P0_2026-11-06.md), in three fill scenarios (taker/taker,
    maker-in/taker-out, taker-in/maker-out; maker fills are a scenario, never assumed), plus an optional slippage
    allowance per side; break-even funding APR at 3, 14, 90 and 180 days; net per 10 000 capital over a funding grid.
    The observed funding of each account (Binance, settled every 8 h, in lab.db) is reported as observed APR on the
    booked notional only - it is not Kraken's funding, and Kraken's hourly settlement is not converted into any other
    expected income. Each active carry account's own fills are re-priced under Kraken fees (fill notional x rate,
    spot legs at spot rates, perp legs at perp rates) next to the fees actually booked.
P1  Capital scenarios for one carry pair and the pair book: spot fully paid on one entity, the short perp on another
    with its own collateral at 1x / 2x / 5x / 10x; the denominator is all allocated capital; the price rise that reaches
    the close-out level (50 % of initial margin, the Danish CFD rule) and the probability of touching it within the
    horizon under a driftless GBM at the stated annual vol (a scenario, not a forecast). Nothing here is verified
    leverage or venue access.

Writes <out>/carry_realism.json and .md and prints the sha256. Descriptive; decides nothing.
"""
import argparse
import hashlib
import json
import math
import os
import sqlite3
from statistics import NormalDist

DB = "/home/anton/ecommerence/copybot/data/lab/lab.db"
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(HERE, "research", "data", "carry_realism")
KRAKEN = {                                   # lowest tier, read 2026-11-06 (kraken.com/pro/fees; support 360048917612)
    "spot": {"maker": 0.0040, "taker": 0.0080},
    "perp": {"maker": 0.0002, "taker": 0.0005},
}
BINANCE_MODEL = {"spot": 0.0010, "perp": 0.0010, "slip": 0.0002}     # what the paper books charge (taker + allowance)
SCENARIOS = {"taker/taker": ("taker", "taker"), "maker/taker": ("maker", "taker"), "taker/maker": ("taker", "maker")}
SLIPS = (0.0, 0.0002, 0.0010)                # per side; Kraken spreads are UNKNOWN, so these are assumptions
HORIZONS = (3, 14, 90, 180)
FUNDING_GRID = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30)
LEVERAGE = (1, 2, 5, 10)
CLOSE_OUT = 0.5                              # close-out at 50 % of initial margin (Finanstilsynet 2019 art. 1(e))
VOL = {"BTC": 0.50, "ETH": 0.65}             # annual vol scenarios (assumptions)
PAIR_VOL = {"BZUSDT": 0.38, "CLUSDT": 0.40, "ETHUSDT": 0.65, "BTCUSDT": 0.50, "QQQUSDT": 0.25, "SPYUSDT": 0.18,
            "XAGUSDT": 0.35, "XAUUSDT": 0.18}  # annual vol scenarios (assumptions, not estimated here)
PAIRS = (("BZUSDT", "CLUSDT"), ("ETHUSDT", "BTCUSDT"), ("QQQUSDT", "SPYUSDT"), ("XAGUSDT", "XAUUSDT"))  # lab.pairs
PAIR_LEVERAGE = (1, 2, 5, 10, 20)
PAIR_LEG, PAIR_HOLD_D = 1_000.0, 3          # amendment 43: 1 000 per leg, out after 72 h at the latest
CAPITAL = 10_000.0
SPOT_SUFFIX = ".SPOT"


def round_trip(scenario, slip=0.0, fees=KRAKEN):
    """Round-trip cost of a long-spot / short-perp pair as a share of the perp notional (equal notionals)."""
    fin, fout = SCENARIOS[scenario]
    return fees["spot"][fin] + fees["spot"][fout] + fees["perp"][fin] + fees["perp"][fout] + 4 * slip


def binance_round_trip():
    m = BINANCE_MODEL
    return 2 * m["spot"] + 2 * m["perp"] + 4 * m["slip"]


def breakeven_apr(rt, days):
    return rt * 365 / days


def net_per_capital(rt, apr, days, capital=CAPITAL, notional=CAPITAL / 2):
    """Funding minus round trip on the perp notional, per unit of the allocated capital (spot + perp collateral)."""
    return (apr * days / 365 - rt) * notional / capital


def close_out_rise(lev):
    """Price rise that takes a short perp's equity to CLOSE_OUT x initial margin (initial margin = notional / lev)."""
    return (1 - CLOSE_OUT) / lev


def touch_prob(rise, vol, days):
    """P(max of a driftless GBM over the horizon reaches +rise) by the reflection principle."""
    if days <= 0:
        return 0.0
    b = math.log(1 + rise)
    return min(1.0, 2 * (1 - NormalDist().cdf(b / (vol * math.sqrt(days / 365)))))


def capital_rows(notional=CAPITAL / 2):
    rows = []
    for lev in LEVERAGE:
        collateral = notional / lev
        total = notional + collateral
        rise = close_out_rise(lev)
        rows.append({"leverage": lev, "spot": notional, "perp_collateral": collateral, "allocated": total,
                     "close_out_rise": rise,
                     "touch": {c: {str(d): touch_prob(rise, v, d) for d in HORIZONS} for c, v in VOL.items()}})
    return rows


def pair_rows():
    """Each leg margined on its own (cross-entity / cross-product netting UNKNOWN): collateral 2 x leg / L; a leg is
    closed out at an adverse move of (1 - CLOSE_OUT) / L; P(at least one leg touches) between max and sum of the legs."""
    rows = []
    for a, b in PAIRS:
        for lev in PAIR_LEVERAGE:
            mv = (1 - CLOSE_OUT) / lev
            pa, pb = touch_prob(mv, PAIR_VOL[a], PAIR_HOLD_D), touch_prob(mv, PAIR_VOL[b], PAIR_HOLD_D)
            rows.append({"pair": f"{a}/{b}", "leverage": lev, "collateral": 2 * PAIR_LEG / lev, "adverse_move": mv,
                         "p_leg_touch_low": max(pa, pb), "p_leg_touch_high": min(1.0, pa + pb)})
    return rows


def accounts(con):
    out = []
    gone = {e for (e,) in con.execute("SELECT exp_id FROM events WHERE kind='lane.retired'")}
    for ts, led, p in con.execute("SELECT ts, exp_id, payload FROM events WHERE kind='lane.started' ORDER BY id"):
        info = json.loads(p)
        fn, src = info.get("function") or "", info.get("source")
        if led in gone or not (src == "carry90" or (src is None and fn.startswith("carry"))):
            continue
        spot_n = perp_n = booked = 0.0
        k = {s: 0.0 for s in ("taker", "maker")}
        for inst, px, q, fee in con.execute("SELECT instrument, px, qty, fee FROM sim_fills WHERE exp_id=?", (led,)):
            n = px * q
            booked += fee
            leg = "spot" if inst.endswith(SPOT_SUFFIX) else "perp"
            spot_n += n if leg == "spot" else 0.0
            perp_n += n if leg == "perp" else 0.0
            for s in k:
                k[s] += n * KRAKEN[leg][s]
        f = con.execute("SELECT COALESCE(SUM(amount), 0), MIN(ts), MAX(ts), COUNT(*) FROM sim_funding WHERE exp_id=?",
                        (led,)).fetchone()
        last = con.execute("SELECT ts, exposure FROM sim_equity WHERE exp_id=? ORDER BY id DESC LIMIT 1",
                           (led,)).fetchone()
        days = ((last[0] if last else ts) - ts) / 86400
        held = (last[1] / 2) if last and last[1] else 0.0          # perp notional ~ half the gross exposure
        out.append({"ledger": led, "name": info.get("name") or fn, "started": ts, "days": days,
                    "spot_notional_traded": spot_n, "perp_notional_traded": perp_n, "fees_booked": booked,
                    "fees_kraken_taker": k["taker"], "fees_kraken_maker": k["maker"], "funding": f[0],
                    "funding_prints": f[3], "perp_notional_now": held,
                    "observed_apr": (f[0] / held * 365 / days) if held and days > 0 else None,
                    "proxy_note": "PAXG spot not transferable (ESMA ART register empty)" if "GULD" in str(
                        info.get("name")) else None})
    return out


def build(con, now):
    rt = {f"{s}|slip={sl}": round_trip(s, sl) for s in SCENARIOS for sl in SLIPS}
    rt["binance_model"] = binance_round_trip()
    return {
        "generated": int(now), "rule": "director order 46 P0+P1 (research/reviews/INBOX.md 2026-11-06)",
        "fees": KRAKEN, "binance_model": BINANCE_MODEL, "round_trip": rt,
        "breakeven_apr": {k: {str(d): breakeven_apr(v, d) for d in HORIZONS} for k, v in rt.items()},
        "net_per_capital_1x": {k: {str(d): {str(a): net_per_capital(v, a, d) for a in FUNDING_GRID} for d in HORIZONS}
                               for k, v in rt.items() if k.endswith("slip=0.0002") or k == "binance_model"},
        "capital": capital_rows(), "pairs_capital": pair_rows(), "accounts": accounts(con) if con else [],
        "unknown": ["Kraken spreads and depth", "Kraken funding levels (only the hourly interval is documented)",
                    "whether Danish retail gets 10x or 2x on Kraken/Coinbase/OKX perps", "cross-entity margin netting",
                    "maker fill probability"],
        "note": "scenarios, not verified access or expected profit; no hedged position is risk-free or capital-neutral"}


def md(rep):
    L = ["# Carry-realisme: Kraken-gebyrer, break-even og kapital (direktørordre 46 P0 + P1)", "",
         "Read-only. Gebyrer: Kraken laveste niveau (spot 0,40/0,80 %, perps 0,02/0,05 %; DK_RETAIL_P0). "
         "Scenarier, ikke verificeret adgang eller forventet profit.", "",
         "## P0: round trip og break-even-funding (andel af perp-notionalen; lige store ben)", "",
         "| Scenarie (ind/ud) | Slip pr. side | Round trip | BE 3 d | BE 14 d | BE 90 d | BE 180 d |", "|---|---|---|---|---|---|---|"]
    for k, v in rep["round_trip"].items():
        sc, sl = (k.split("|slip=") + ["0.0002"])[:2] if "|" in k else ("Binance-model (bøgerne)", "0.0002")
        be = rep["breakeven_apr"][k]
        L.append(f"| {sc} | {float(sl):.2%} | {v:.2%} | {be['3']:.0%} | {be['14']:.1%} | {be['90']:.2%} | {be['180']:.2%} |")
    L += ["", "## Netto pr. kapital ved 1x (spot betalt fuldt, perp-collateral = notional; slip 0,02 %)", "",
          "| Scenarie | Dage | " + " | ".join(f"funding {a:.0%}" for a in FUNDING_GRID) + " |",
          "|---|---|" + "---|" * len(FUNDING_GRID)]
    for k, byd in rep["net_per_capital_1x"].items():
        for d, row in byd.items():
            L.append(f"| {k.split('|')[0]} | {d} | " + " | ".join(f"{row[str(a)]:+.2%}" for a in FUNDING_GRID) + " |")
    L += ["", "## Kontiene genprissat (egne fyld × Kraken-satser; funding er Binance' observerede, 8 t)", "",
          "| Konto | Dage | Spot handlet | Perp handlet | Gebyr bogført | Kraken taker | Kraken maker | Funding | Obs. APR |",
          "|---|---|---|---|---|---|---|---|---|"]
    for a in rep["accounts"]:
        apr = f"{a['observed_apr']:.1%}" if a["observed_apr"] is not None else "–"
        L.append(f"| {a['name']} ({a['ledger'][-6:]}) | {a['days']:.1f} | {a['spot_notional_traded']:,.0f} | "
                 f"{a['perp_notional_traded']:,.0f} | {a['fees_booked']:.2f} | {a['fees_kraken_taker']:.2f} | "
                 f"{a['fees_kraken_maker']:.2f} | {a['funding']:+.2f} | {apr} |")
    L += ["", "Observeret APR = bogført funding / nuværende perp-notional × 365 / dage. Den er få dage gammel, er "
          "Binance' og ikke Kraken's, og er ingen prognose.", "",
          "## P1: kapital og close-out (ét carry-par, 5.000 pr. ben; close-out ved 50 % af initialmarginen)", "",
          "| Gearing perp | Perp-collateral | Samlet allokeret | Stigning til close-out | P(BTC rører) 14 / 90 / 180 d | "
          "P(ETH rører) 14 / 90 / 180 d |", "|---|---|---|---|---|---|"]
    for r in rep["capital"]:
        pb = " / ".join(f"{r['touch']['BTC'][str(d)]:.0%}" for d in (14, 90, 180))
        pe = " / ".join(f"{r['touch']['ETH'][str(d)]:.0%}" for d in (14, 90, 180))
        L.append(f"| {r['leverage']}x | {r['perp_collateral']:,.0f} | {r['allocated']:,.0f} | "
                 f"{r['close_out_rise']:.0%} | {pb} | {pe} |")
    L += ["", f"Vol-scenarier: BTC {VOL['BTC']:.0%}, ETH {VOL['ETH']:.0%} p.a., driftløs GBM, refleksionsprincippet. "
          "Spotbenets gevinst ligger på en anden enhed og dækker ikke perp-marginen uden en overførsel; "
          "en close-out efterlader en ubeskyttet lang spotposition.", "",
          "## P1: parbogen (1.000 pr. ben, hvert ben med egen margin, holdt højst 72 t)", "",
          "| Par | Gearing pr. ben | Collateral i alt | Modgående bevægelse til close-out | P(et ben rører) inden 72 t |",
          "|---|---|---|---|---|"]
    for r in rep["pairs_capital"]:
        L.append(f"| {r['pair']} | {r['leverage']}x | {r['collateral']:,.0f} | {r['adverse_move']:.1%} | "
                 f"{r['p_leg_touch_low']:.0%}-{r['p_leg_touch_high']:.0%} |")
    L += ["", "Hvert ben vurderes alene: parrets afdækning hjælper kun, hvis venue og produkt netter marginen på tværs "
          "(UNKNOWN). Vol-scenarier pr. instrument står i værktøjets PAIR_VOL. CARRY90-GULD bruger PAXG-spot, som ikke kan "
          "overføres til en dansk detailmodel (ESMA's ART-register er tomt); dens række er kun regnskab.", "",
          "**UNKNOWN:** " + "; ".join(rep["unknown"]) + ".", ""]
    return "\n".join(L) + "\n"


def main():
    import datetime as dt
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)
    rep = build(con, dt.datetime.now(dt.timezone.utc).timestamp())
    os.makedirs(a.out, exist_ok=True)
    raw = json.dumps(rep, sort_keys=True, indent=1).encode()
    with open(os.path.join(a.out, "carry_realism.json"), "wb") as f:
        f.write(raw)
    with open(os.path.join(a.out, "carry_realism.md"), "w") as f:
        f.write(md(rep))
    print(f"carry_realism.json sha256 {hashlib.sha256(raw).hexdigest()} accounts {len(rep['accounts'])}")


if __name__ == "__main__":
    main()
