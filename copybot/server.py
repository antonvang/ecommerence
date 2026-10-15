"""Lokal webserver til dashboardet (kun på din egen PC)."""
from __future__ import annotations

import json
import math
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from report import build_state
from store import Store

HERE = os.path.dirname(os.path.abspath(__file__))


def _clean(o):
    if isinstance(o, float) and (math.isinf(o) or math.isnan(o)):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                    self._send(200, "text/html; charset=utf-8", f.read())
            elif path == "/api/state":
                s = Store(db_path)
                try:
                    body = json.dumps(_clean(build_state(s))).encode()
                finally:
                    s.close()
                self._send(200, "application/json", body)
            else:
                self._send(404, "text/plain", b"not found")

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    return Handler


def serve(db_path, port, block=False):
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(db_path))
    if block:
        srv.serve_forever()
    else:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
