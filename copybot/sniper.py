"""Paper-sniper: "køber" pump.fun-coins i det øjeblik, de graduerer til PumpSwap. KUN FALSKE PENGE.

Prisen læses direkte fra poolens to vaults (x*y=k), så den er den rigtige pris i det sekund, botten ser
graduation. Vores faktiske forsinkelse er dermed med i tallene. Tre faste regler testes side om side.
Historisk data sagde nej til dem alle (se README); det her er den ærlige test på fremtidige data.
"""
from __future__ import annotations

import os
import threading
import time

from solana_rpc import RPC
from store import Store
from swaps import WSOL, _keys

MIGRATION = "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg"  # pump.fun's migrations-konto
RULES = {
    "60s": {"hold": 60},
    "5min": {"hold": 300},
    "tp50_sl30": {"hold": 4 * 3600, "tp": 0.5, "sl": 0.3},
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS snipes (id INTEGER PRIMARY KEY AUTOINCREMENT, rule TEXT, mint TEXT, pool TEXT,
  sol_vault TEXT, tok_vault TEXT, grad_ts INTEGER, seen_ts INTEGER, opened_ts INTEGER, closed_ts INTEGER,
  entry_px REAL, exit_px REAL, tokens REAL, cost_usd REAL, proceeds_usd REAL, pnl_usd REAL, reason TEXT);
"""


def parse_migration(tx):
    """Find coin, pool og de to vaults i en Migrate-transaktion. None hvis det ikke er en rigtig graduation."""
    if not tx or (tx.get("meta") or {}).get("err") is not None:
        return None
    meta = tx["meta"]
    if "Migrate" not in " ".join(meta.get("logMessages") or []):
        return None
    keys, _ = _keys(tx)
    post = meta.get("postTokenBalances") or []
    mints = {b["mint"] for b in post if b["mint"] != WSOL}
    if len(mints) != 1:
        return None
    mint = mints.pop()
    own_t = {b.get("owner") for b in post if b["mint"] == mint}
    own_s = {b.get("owner") for b in post if b["mint"] == WSOL}
    pools = (own_t & own_s) - {MIGRATION, None}
    if len(pools) != 1:
        return None
    pool = pools.pop()
    sol_b = next(b for b in post if b["mint"] == WSOL and b.get("owner") == pool)
    tok_b = next(b for b in post if b["mint"] == mint and b.get("owner") == pool)
    sol = int(sol_b["uiTokenAmount"]["amount"]) / 10 ** int(sol_b["uiTokenAmount"]["decimals"])
    if sol < 50:  # en rigtig graduation lægger ~67-85 SOL i poolen
        return None
    return {"mint": mint, "pool": pool, "sol_vault": keys[sol_b["accountIndex"]], "tok_vault": keys[tok_b["accountIndex"]],
            "grad_ts": tx.get("blockTime")}


def buy(size, price, pool_usd, fee, tip):
    """Antal tokens for `size` USD inkl. gebyr, tip og pris-påvirkning (x*y=k)."""
    return max(size - tip, 0.0) * (1 - fee) / (price * (1 + size / pool_usd))


def sell(tokens, price, pool_usd, fee, tip):
    v = tokens * price
    return max(v * pool_usd / (pool_usd + v) * (1 - fee) - tip, 0.0)


class Sniper:
    def __init__(self, cfg, root, log=print):
        sc = cfg["sniper"]
        self.size = float(sc["size_usd"])
        self.fee = sc["fee_pct"] / 100.0
        self.tip_sol = sc["tip_sol"]
        self.poll = sc["poll_seconds"]
        p = cfg["paper"]
        self.rpc = RPC(p.get("rpc_url") or cfg["rpc_url"], sc["rpc_requests_per_second"], log=lambda *a: None,
                       fallback=sc.get("fallback_rpcs") or ())
        self.s = Store(os.path.join(root, "sniper.db"))
        self.s.db.executescript(SCHEMA)
        self.log = log
        self.sol_usd = None
        self.cursor = None
        self.to_open = {}  # mint -> (graduation, første forsøg): pool-konti er ikke altid synlige med det samme
        self.pending = {}  # signatur -> (første gang set, sidste forsøg); nye transaktioner kan ikke altid hentes med det samme

    def _sol_usd(self, market):
        try:
            self.sol_usd = market.sol_usd()
        except Exception:
            pass
        return self.sol_usd

    def _reserves(self, rows):
        """{vault: beholdning} for alle vaults i rows. Mangler en konto, er poolen tømt.

        Højst 8 konti pr. kald: PublicNode svarer 403 på getMultipleAccounts med 16 eller flere.
        """
        keys = sorted({r["sol_vault"] for r in rows} | {r["tok_vault"] for r in rows})
        out = {}
        for k in range(0, len(keys), 8):
            chunk = keys[k:k + 8]
            res = self.rpc.call("getMultipleAccounts", [chunk, {"encoding": "jsonParsed", "commitment": "processed"}])
            for addr, acc in zip(chunk, (res or {}).get("value") or []):
                try:
                    out[addr] = float(acc["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"] or 0)
                except (TypeError, KeyError):
                    out[addr] = 0.0
        return out

    def _price(self, res, sol_vault, tok_vault):
        sol, tok = res.get(sol_vault, 0.0), res.get(tok_vault, 0.0)
        if sol <= 0 or tok <= 0:
            return None, 0.0
        return sol / tok * self.sol_usd, sol * self.sol_usd

    def detect(self):
        """Nye graduations siden sidst (ældste først)."""
        sigs = self.rpc.signatures(MIGRATION, until=self.cursor, limit=100) if self.cursor else self.rpc.signatures(MIGRATION, limit=1)
        if self.cursor is None:
            self.cursor = sigs[0]["signature"] if sigs else None
            return []  # start fra nu: ingen gamle graduations
        if sigs:
            self.cursor = sigs[0]["signature"]
        now = time.time()
        for sg in reversed(sigs):
            if sg.get("err") is None:
                self.pending.setdefault(sg["signature"], [now, 0.0])
        out = []
        for sig, (first, last) in list(self.pending.items()):
            if now - last < 2:
                continue  # prøv højst hvert 2. sekund, så den gratis RPC ikke blokerer os
            self.pending[sig][1] = now
            tx = self.rpc.transaction(sig)
            if tx is None and now - first < 30:
                continue  # endnu ikke tilgængelig hos RPC'en: prøv igen senere
            del self.pending[sig]
            g = parse_migration(tx)
            if g:
                out.append(g)
        return out

    def open(self, g):
        """True når købet er registreret (eller allerede var det); False hvis poolens pris ikke kan læses endnu."""
        if self.s.one("SELECT 1 FROM snipes WHERE mint=? LIMIT 1", g["mint"]):
            return True  # pump.fun laver nogle gange flere Migrate-transaktioner pr. coin: køb kun én gang
        now = int(time.time())
        res = self._reserves([{"sol_vault": g["sol_vault"], "tok_vault": g["tok_vault"]}])
        px, pool_usd = self._price(res, g["sol_vault"], g["tok_vault"])
        if not px:
            return False  # de nye pool-konti er ikke synlige hos RPC'en endnu
        tip = self.tip_sol * self.sol_usd
        for rule in RULES:
            tokens = buy(self.size, px, pool_usd, self.fee, tip)
            self.s.x("INSERT INTO snipes(rule,mint,pool,sol_vault,tok_vault,grad_ts,seen_ts,opened_ts,entry_px,tokens,cost_usd) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?)", rule, g["mint"], g["pool"], g["sol_vault"], g["tok_vault"],
                     g["grad_ts"], now, now, px, tokens, self.size)
        self.log(f"[SNIPE] {g['mint'][:6]} · set {now - (g['grad_ts'] or now)} sek efter graduation · pris ${px:.8f}")
        return True

    def check(self):
        rows = self.s.q("SELECT * FROM snipes WHERE closed_ts IS NULL")
        if not rows:
            return
        res = self._reserves(rows)
        now = int(time.time())
        tip = self.tip_sol * self.sol_usd
        for r in rows:
            rule = RULES[r["rule"]]
            px, pool_usd = self._price(res, r["sol_vault"], r["tok_vault"])
            reason = None
            if px is None:
                reason, px, pool_usd = "rug", 0.0, 1.0
            elif rule.get("tp") and px >= r["entry_px"] * (1 + rule["tp"]):
                reason = "tp"
            elif rule.get("sl") and px <= r["entry_px"] * (1 - rule["sl"]):
                reason = "sl"
            elif now - r["opened_ts"] >= rule["hold"]:
                reason = "tid"
            if not reason:  # åben: gem nuværende salgsværdi, så balancen på dashboardet følger med live
                self.s.x("UPDATE snipes SET exit_px=?, proceeds_usd=? WHERE id=?", px,
                         sell(r["tokens"], px, pool_usd, self.fee, tip), r["id"])
            if reason:
                got = sell(r["tokens"], px, pool_usd, self.fee, tip) if px else 0.0
                self.s.x("UPDATE snipes SET closed_ts=?, exit_px=?, proceeds_usd=?, pnl_usd=?, reason=? WHERE id=?",
                         now, px, got, got - r["cost_usd"], reason, r["id"])

    def _detect_and_open(self):
        now = time.time()
        for g in self.detect():
            self.to_open.setdefault(g["mint"], (g, now))
        for mint, (g, first) in list(self.to_open.items()):
            if self.open(g):
                del self.to_open[mint]
            elif now - first > 20:
                del self.to_open[mint]  # opgiv, men tæl det, så tabte graduations aldrig er usynlige
                self.s.set("sniper_dropped", (self.s.get("sniper_dropped") or 0) + 1)

    def _check_every_2s(self):
        if time.time() - self._last_check >= 2:
            self._last_check = time.time()
            self.check()

    def run(self, market, stop=None):
        self.log(f"Sniper (paper) kører · ${self.size:.0f} pr. regel · regler: {', '.join(RULES)}")
        self._last_check = 0.0
        while not (stop and stop.is_set()):
            t0 = time.time()
            if self._sol_usd(market):
                # hver del for sig: en fejl ved at finde nye graduations må ikke stoppe salget af åbne positioner
                for step in (self._detect_and_open, self._check_every_2s):
                    try:
                        step()
                    except Exception as e:
                        self.s.set("sniper_error", [int(time.time()), f"{step.__name__}: {type(e).__name__}: {str(e)[:160]}"])
            self.s.set("sniper_heartbeat", int(time.time()))
            time.sleep(max(0.0, self.poll - (time.time() - t0)))


def start_in_background(cfg, root, market, log=print):
    sn = Sniper(cfg, root, log=log)
    t = threading.Thread(target=sn.run, args=(market,), daemon=True)
    t.start()
    return sn
