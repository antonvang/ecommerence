"""Paper trading: følger wallets live med falske penge. Intet sendes til blockchainen."""
from __future__ import annotations

import os
import time
import webbrowser

from engine import Engine
from market import LiveMarket
from server import serve
from solana_rpc import RPC
from store import Store
from swaps import parse_swaps

PUBLICNODE = "https://solana-rpc.publicnode.com"


def single_instance(root):
    """Lås, så der kun kører én paper-bot ad gangen (fx autostart + START_COPYBOT.bat). Slippes, når processen stopper."""
    f = open(os.path.join(root, "paper.lock"), "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def run_paper(cfg, wallets, root, log=print):
    lock = single_instance(root)
    if lock is None:
        raise SystemExit(f"Paper trading kører allerede. Se http://localhost:{cfg['dashboard_port']}")
    p = cfg["paper"]
    store = Store(os.path.join(root, "paper.db"))
    store.set("mode", "PAPER")
    market = LiveMarket(log=log)
    url, rps = cfg["rpc_url"], cfg["rpc_requests_per_second"]
    if p.get("rpc_url"):
        url, rps = p["rpc_url"], p.get("rpc_requests_per_second") or rps
    elif "api.mainnet-beta.solana.com" in url:
        url, rps = PUBLICNODE, 8  # live kræver kun nye data: PublicNode er gratis og langt hurtigere end Solanas egen
    log(f"Paper RPC: {url.split('?')[0]} ({rps}/sek)")
    rpc = RPC(url, rps, log=log)
    eng = Engine(cfg, store, market, wallets, live=True, quiet=False, log=log)
    eng.start(int(time.time()))

    port = cfg["dashboard_port"]
    serve(store.path, port)
    url = f"http://localhost:{port}"
    log(f"Dashboard: {url}  (lad dette vindue være åbent - luk det for at stoppe)")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    cursors = store.get("cursors", {})
    for w in wallets:
        if w["addr"] not in cursors:
            sigs = rpc.signatures(w["addr"], limit=1)
            cursors[w["addr"]] = sigs[0]["signature"] if sigs else None
    store.set("cursors", cursors)
    log(f"Følger {len(wallets)} wallets. Der sker først noget, når de handler.")

    last_check = 0.0
    while True:
        t0 = time.time()
        for w in wallets:
            a = w["addr"]
            try:
                new = rpc.signatures(a, until=cursors.get(a), limit=1000) if cursors.get(a) else rpc.signatures(a, limit=1)
                if not cursors.get(a):
                    cursors[a] = new[0]["signature"] if new else None
                    continue
                ok = [i for i, s in enumerate(new) if s.get("err") is None]  # fejlede transaktioner hentes aldrig
                if len(ok) > p["max_tx_per_poll"]:
                    log(f"  @{w['label']} lavede {len(ok)} transaktioner siden sidst - tager kun de {p['max_tx_per_poll']} nyeste")
                    new = new[: ok[p["max_tx_per_poll"]]]
                for s in reversed(new):  # ældste først
                    sig = s["signature"]
                    if s.get("err") is None and not store.one("SELECT 1 FROM seen WHERE sig=?", sig):
                        tx = rpc.transaction(sig)
                        if tx is None:
                            break  # ikke klar endnu, prøv igen næste runde
                        store.x("INSERT OR IGNORE INTO seen(sig) VALUES(?)", sig)
                        for sw in parse_swaps(tx, a, market.sol_usd):
                            eng.on_swap(sw)
                    cursors[a] = sig
                store.set("cursors", cursors)
            except Exception as e:
                msg = f"Fejl ved @{w['label']}: {e}"
                log("  " + msg)
                store.set("last_error", [int(time.time()), msg])
        if time.time() - last_check >= p["check_seconds"]:
            try:
                eng.check(int(time.time()))
            except Exception as e:
                log(f"  Fejl ved pristjek: {e}")
            last_check = time.time()
        store.set("heartbeat", int(time.time()))
        time.sleep(max(0.0, p["poll_seconds"] - (time.time() - t0)))
