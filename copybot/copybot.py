"""CopyBot - kopier memecoin-wallets på Solana. KUN PAPER TRADING: ingen rigtige penge, ingen private nøgler.

  python copybot.py backtest [--days 14] [--no-sweep]   hurtigt svar på historiske data
  python copybot.py paper                               følg live med falske penge + dashboard
  python copybot.py dashboard [--db data/backtest.db]   vis dashboard for en kørsel
  python copybot.py report [--db data/paper.db]         tal i konsollen
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

DEFAULTS = {
    "rpc_url": "https://api.mainnet-beta.solana.com",
    "rpc_requests_per_second": 3,
    "start_balance_usd": 50,
    "position_pct": 20,
    "max_open_positions": 4,
    "min_trade_usd": 1,
    "shadow_trade_usd": 10,
    "fire_after_losses": 3,
    "next_trader": "best_shadow",
    "warmup_hours": 48,
    "rank_window_days": 7,
    "min_shadow_trades": 5,
    "min_median_hold_minutes": 5,
    "require_positive_shadow": True,
    "min_leader_buy_usd": 50,
    "min_liquidity_usd": 20000,
    "max_price_impact_pct": 3,
    "stop_loss_pct": 40,
    "max_hold_hours": 24,
    "rug_liquidity_usd": 1000,
    "fallback_reserve_usd": 5000,
    "snapshot_seconds": 300,
    "fees": {"dex_pct": 0.5, "bot_pct": 1.0, "mev_slippage_pct": 0.5, "network_fee_sol": 0.0015},
    "backtest": {"days": 14, "max_tx_per_wallet": 600, "copy_delay_seconds": 10},
    "paper": {"poll_seconds": 10, "check_seconds": 20, "max_tx_per_poll": 400, "rpc_url": "", "rpc_requests_per_second": 0},
    "dashboard_port": 8765,
}
B58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path):
    if not os.path.exists(path):
        return copy.deepcopy(DEFAULTS)
    with open(path, encoding="utf-8-sig") as f:
        return merge(DEFAULTS, json.load(f))


def load_wallets(path):
    out, seen = [], set()
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            addr = parts[0]
            if not B58.match(addr):
                print(f"  Springer over ugyldig adresse i wallets.txt: {addr}")
                continue
            if addr in seen:
                continue
            seen.add(addr)
            label = re.sub(r"[^\w.-]", "", parts[1].lstrip("@")) if len(parts) > 1 else ""
            out.append({"addr": addr, "label": label or f"{addr[:4]}..{addr[-4:]}"})
    return out


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # gamle Windows-konsoller kan ikke vise fx "→"
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="CopyBot (paper trading)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backtest")
    b.add_argument("--days", type=int)
    b.add_argument("--no-sweep", action="store_true")
    sub.add_parser("paper")
    d = sub.add_parser("dashboard")
    d.add_argument("--db", default=os.path.join(HERE, "data", "backtest.db"))
    r = sub.add_parser("report")
    r.add_argument("--db", default=os.path.join(HERE, "data", "paper.db"))
    a = ap.parse_args()

    cfg = load_config(os.path.join(HERE, "config.json"))
    root = os.path.join(HERE, "data")
    os.makedirs(root, exist_ok=True)

    if a.cmd in ("backtest", "paper"):
        wallets = load_wallets(os.path.join(HERE, "wallets.txt"))
        if not wallets:
            raise SystemExit("wallets.txt er tom. Indsæt de wallets, du vil kopiere (se LAES MIG.txt), og prøv igen.")
        print(f"CopyBot · {len(wallets)} wallets · RPC: {cfg['rpc_url'].split('?')[0]}")
        if a.cmd == "backtest":
            from backtest import run_backtest
            run_backtest(cfg, wallets, root, days=a.days, sweep=not a.no_sweep)
        else:
            from paper import run_paper
            run_paper(cfg, wallets, root)
    elif a.cmd == "dashboard":
        if not os.path.exists(a.db):
            raise SystemExit(f"Findes ikke: {a.db}. Kør en backtest eller paper trading først.")
        from server import serve
        import webbrowser
        url = f"http://localhost:{cfg['dashboard_port']}"
        print(f"Dashboard: {url}  (luk vinduet for at stoppe)")
        webbrowser.open(url)
        serve(a.db, cfg["dashboard_port"], block=True)
    elif a.cmd == "report":
        if not os.path.exists(a.db):
            raise SystemExit(f"Findes ikke: {a.db}")
        from report import print_report
        from store import Store
        s = Store(a.db)
        print_report(s, f"RAPPORT  {os.path.basename(a.db)}  ({s.get('mode', '?')})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStoppet.")
