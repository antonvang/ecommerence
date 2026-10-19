"""Static safety audit of every Python file under lab/ (lab/engine/ and lab/families/ included): the lab is paper and
research only. It must never be able to place a real order, sign a request, withdraw funds or read credentials.

The audit parses each file (ast) instead of grepping text, so docstrings, comments, lifecycle states such as
WITHDRAWN and the simulated paper engine (PaperEngine.submit_taker / submit_maker, which fill against a public order
book read with GET) are not false positives. Every rule is also tested against a small source that breaks it, so
the audit itself cannot silently pass everything."""
import ast
import os
import re
import sys
import unittest
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
LAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lab")

# public, read-only data sources the lab reads (plus the local dashboard and citation links)
ALLOWED_HOSTS = {
    "data.binance.vision",            # monthly archives (amendment 8 point 17)
    "fapi.binance.com",               # public USD-M market data (depth, klines, fundingRate): GET only
    "community-api.coinmetrics.io",   # CoinMetrics community API
    "fred.stlouisfed.org",            # FRED rates
    "stablecoins.llama.fi",           # DefiLlama stablecoins
    "www.deribit.com",                # Deribit DVOL index (public)
    "api.hyperliquid.xyz",            # Hyperliquid /info (public, read-only; /exchange is never used)
    "clob.polymarket.com",            # Polymarket public order books
    "gamma-api.polymarket.com",       # Polymarket public market list
    "doi.org", "www.bis.org",         # citations in catalogue evidence
    "127.0.0.1", "localhost",         # the local dashboard
}
FORBIDDEN_IMPORTS = {"hmac", "ccxt", "binance", "web3", "eth_account", "nacl", "ecdsa", "coincurve", "requests",
                     "websocket", "websockets", "aiohttp", "httpx", "paramiko", "smtplib", "ftplib"}
FORBIDDEN_NAMES = re.compile(r"(?i)^(place|create|new|send|post|submit_(real|live))_?orders?$|^cancel_?all_?orders$|"
                             r"^withdraw\w*$|^sign(_?request|_?payload|_?message|transaction)?$|^transfer_?funds$")
FORBIDDEN_TEXT = ("x-mbx-apikey", "/fapi/v1/order", "/fapi/v2/order", "/api/v3/order", "/dapi/v1/order", "/sapi/",
                  "/papi/", "/fapi/v1/leverage", "/fapi/v1/margintype", "withdraw/apply", "api_secret", "apisecret",
                  "secret_key", "private_key", "privatekey", "config.local.json", "hyperliquid.xyz/exchange")
SECRET_ENV = re.compile(r"(?i)(api_?key|secret|private|passphrase|mnemonic|seed_?phrase)")
BODY_SENDERS = {("scanner.py", "http_post")}            # the only function that sends a request body
BODY_TARGETS = {"HL_INFO"}                              # ... and only to Hyperliquid /info
HEAD_SENDERS = {("families/__init__.py", "_head")}      # HEAD only for the F2 COIN-M coverage check
SIMULATED_ENGINE = "paper.py"                           # fills against a book it is given; no network at all


def lab_files():
    out = []
    for root, _, files in os.walk(LAB):
        if "__pycache__" in root:
            continue
        out += [os.path.join(root, f) for f in files if f.endswith(".py")]
    return sorted(out)


def _docstrings(tree):
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body and \
                isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and \
                isinstance(node.body[0].value.value, str):
            ids.add(id(node.body[0].value))
    return ids


def _name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def audit(source, rel):
    """Findings [(rule, line, detail)] for one file's source; rel is its path relative to lab/."""
    tree = ast.parse(source)
    docs, out = _docstrings(tree), []
    parents = {}
    for node in ast.walk(tree):
        for ch in ast.iter_child_nodes(node):
            parents[ch] = node

    def enclosing(node):
        while node in parents:
            node = parents[node]
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return node.name
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in FORBIDDEN_IMPORTS:
                    out.append(("import", node.lineno, a.name))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] in FORBIDDEN_IMPORTS:
            out.append(("import", node.lineno, node.module))
        if rel == SIMULATED_ENGINE and isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(m.split(".")[0] in ("urllib", "socket", "http", "ssl") for m in mods):
                out.append(("engine-network", node.lineno, ",".join(mods)))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and FORBIDDEN_NAMES.search(node.name):
            out.append(("order-function", node.lineno, node.name))
        if isinstance(node, ast.Call):
            n = _name(node.func)
            if n and FORBIDDEN_NAMES.search(n):
                out.append(("order-call", node.lineno, n))
            if n == "Request":
                kw = {k.arg: k.value for k in node.keywords}
                m = kw.get("method")
                if m is not None:
                    v = m.value if isinstance(m, ast.Constant) else None
                    if v not in ("GET", "HEAD"):
                        out.append(("http-method", node.lineno, str(v)))
                    elif v == "HEAD" and (rel, enclosing(node)) not in HEAD_SENDERS:
                        out.append(("http-head", node.lineno, str(enclosing(node))))
                if "data" in kw or len(node.args) >= 2:
                    if (rel, enclosing(node)) not in BODY_SENDERS:
                        out.append(("http-body", node.lineno, str(enclosing(node))))
            if n == "urlopen" and (len(node.args) >= 2 or any(k.arg == "data" for k in node.keywords)):
                if (rel, enclosing(node)) not in BODY_SENDERS:
                    out.append(("http-body", node.lineno, str(enclosing(node))))
            if n == "http_post" and not (node.args and _name(node.args[0]) in BODY_TARGETS):
                out.append(("http-body-target", node.lineno, ast.unparse(node.args[0]) if node.args else "?"))
            if n == "get" and isinstance(node.func, ast.Attribute) and _name(node.func.value) == "environ" and \
                    node.args and isinstance(node.args[0], ast.Constant) and SECRET_ENV.search(str(node.args[0].value)):
                out.append(("secret-env", node.lineno, node.args[0].value))
        if isinstance(node, ast.Subscript) and _name(node.value) == "environ" and \
                isinstance(node.slice, ast.Constant) and SECRET_ENV.search(str(node.slice.value)):
            out.append(("secret-env", node.lineno, node.slice.value))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            low = node.value.lower()
            for t in FORBIDDEN_TEXT:
                if t in low:
                    out.append(("text", node.lineno, t))
            for u in re.findall(r"https?://[^\s\"'{}<>]+", node.value):
                host = urlparse(u).hostname
                if host and host not in ALLOWED_HOSTS:
                    out.append(("host", node.lineno, host))
    return out


class LabHasNoRealTradingCode(unittest.TestCase):
    def test_every_lab_file_is_audited(self):
        files = lab_files()
        rels = {os.path.relpath(f, LAB) for f in files}
        self.assertIn("paper.py", rels)
        self.assertIn(os.path.join("engine", "data.py"), rels)
        self.assertIn(os.path.join("families", "dbasis.py"), rels)
        self.assertGreater(len(files), 30)

    def test_no_order_signing_withdrawal_or_credential_code_anywhere_in_lab(self):
        found = []
        for f in lab_files():
            rel = os.path.relpath(f, LAB).replace(os.sep, "/")
            with open(f, encoding="utf-8") as fh:
                found += [(rel,) + x for x in audit(fh.read(), rel)]
        self.assertEqual(found, [], "\n".join(map(str, found)))

    def test_the_simulated_engine_has_no_network_and_writes_only_sim_tables(self):
        with open(os.path.join(LAB, SIMULATED_ENGINE), encoding="utf-8") as fh:
            src = fh.read()
        tree = ast.parse(src)
        tables = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and _name(n.func) == "append"
                  and isinstance(n.func, ast.Attribute) and _name(n.func.value) == "db"            # db.append(...)
                  and n.args and isinstance(n.args[0], ast.Constant)}
        self.assertTrue(tables)
        self.assertTrue(all(t.startswith("sim_") for t in tables), tables)


class TheAuditCatchesWhatItShould(unittest.TestCase):
    """Each rule against a small source that breaks it (so the audit can never pass vacuously), and the harmless
    look-alikes that must not be flagged."""

    def rules(self, src, rel="x.py"):
        return {r for r, _, _ in audit(src, rel)}

    def test_each_forbidden_pattern_is_caught(self):
        cases = {
            "import": "import hmac\n",
            "order-function": "def place_order(sym, qty):\n    pass\n",
            "order-call": "client.create_order(symbol='BTCUSDT')\n",
            "http-method": "urllib.request.Request(u, method='POST')\n",
            "http-body": "urllib.request.Request(u, data=b'x')\n",
            "http-body-target": "http_post('https://api.hyperliquid.xyz/exchange', {})\n",
            "secret-env": "os.environ.get('BINANCE_API_KEY')\n",
            "text": "H = {'X-MBX-APIKEY': k}\n",
            "host": "U = 'https://api.binance.com/api/v3/account'\n",
        }
        for rule, src in cases.items():
            self.assertIn(rule, self.rules(src), (rule, src))
        self.assertIn("text", self.rules("P = '/fapi/v1/order'\n"))
        self.assertIn("text", self.rules("open('config.local.json')\n"))
        self.assertIn("order-function", self.rules("def withdraw(asset, amount):\n    pass\n"))
        self.assertIn("order-function", self.rules("def sign_request(params):\n    pass\n"))
        self.assertIn("http-head", self.rules("urllib.request.Request(u, method='HEAD')\n", "paper_runner.py"))
        self.assertIn("engine-network", self.rules("import urllib.request\n", SIMULATED_ENGINE))

    def test_harmless_look_alikes_are_not_flagged(self):
        ok = ('"""Never place an order; withdraw nothing; no api_key."""\n'
              'STATES = ("WITHDRAWN", "REJECTED")\n'
              'def submit_taker(self, exp_id, order_id, instrument, side, qty, book):\n'
              '    """Simulated fill against a public book read with GET."""\n'
              '    return {"simulated": True}\n'
              'req = urllib.request.Request("https://fapi.binance.com/fapi/v1/depth?symbol=X", '
              'headers={"User-Agent": "copybot-lab/paper (read-only)"})\n'
              'os.environ.get("COPYBOT_WATCH_NOTIFY")\n')
        self.assertEqual(audit(ok, "x.py"), [])
        self.assertEqual(audit("http_post(HL_INFO, {'type': 'meta'})\n", "scanner.py"), [])


if __name__ == "__main__":
    unittest.main()
