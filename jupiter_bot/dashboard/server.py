"""Local, read-only monitoring dashboard: one page plus JSON endpoints.

    python3 -m jupiter_bot.dashboard --journal ~/.local/share/jupiter-bot/observations.db [--port 8787]

Binds to 127.0.0.1 only. GET only; every other method gets 405. No endpoint
writes anything: the journal is opened read-only per request and every other
file is only read if it exists. Requests whose Host header is not this
loopback address are refused (blocks DNS-rebinding from a web page).
"""
from __future__ import annotations

import argparse
import json
import socketserver
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import data

HOST = "127.0.0.1"
DEFAULT_PORT = 8787
STATIC = Path(__file__).resolve().parent / "static"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Content-Security-Policy": ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
                                "form-action 'none'; frame-ancestors 'none'"),
}


def _json(status, payload):
    body = json.dumps(payload, allow_nan=False, default=str, ensure_ascii=False).encode("utf-8")
    return status, {"Content-Type": "application/json; charset=utf-8"}, body


def _error(status, message):
    return _json(status, {"error": message})


def _page():
    body = (STATIC / "index.html").read_bytes()
    return HTTPStatus.OK, {"Content-Type": "text/html; charset=utf-8"}, body


def _hours(query):
    try:
        return float(query.get("hours", ["24"])[0])
    except ValueError:
        return 24.0


API = {
    "/api/overview": lambda paths, query, now: data.overview(paths, now),
    "/api/market": lambda paths, query, now: data.market(paths, _hours(query), now),
    "/api/research": lambda paths, query, now: data.research(paths, now),
    "/api/paper": lambda paths, query, now: data.paper(paths, now),
    "/api/execution": lambda paths, query, now: data.execution(paths, now),
}


def allowed_host(host_header, port):
    if host_header is None:
        return True  # HTTP/1.0 clients such as curl -0; the socket is loopback-only anyway
    return host_header.strip().lower() in {"%s:%d" % (h, port) for h in (HOST, "localhost")} | \
        ({HOST, "localhost"} if port == 80 else set())


def route(method, target, paths, now=None, host=None, port=DEFAULT_PORT):
    """(status, headers, body) for one request. Pure apart from reading files."""
    if method != "GET":
        status, headers, body = _error(HTTPStatus.METHOD_NOT_ALLOWED, "Kun GET er tilladt")
        headers["Allow"] = "GET"
        return status, headers, body
    if not allowed_host(host, port):
        return _error(HTTPStatus.FORBIDDEN, "Ukendt Host-header")
    parts = urlsplit(target)
    if parts.path in ("/", "/index.html"):
        return _page()
    handler = API.get(parts.path)
    if handler is None:
        return _error(HTTPStatus.NOT_FOUND, "Ukendt sti")
    try:
        return _json(HTTPStatus.OK, handler(paths, parse_qs(parts.query), time.time() if now is None else now))
    except Exception as exc:  # one bad file must not take the page down
        return _error(HTTPStatus.INTERNAL_SERVER_ERROR, "%s: %s" % (type(exc).__name__, exc))


class Handler(BaseHTTPRequestHandler):
    server_version = "jupiter-dashboard"
    sys_version = ""
    paths = None  # set by make_server

    def do_GET(self):
        self._send(*route("GET", self.path, self.paths, host=self.headers.get("Host"),
                          port=self.server.server_address[1]))

    def _not_allowed(self):
        self._send(*route(self.command, self.path, self.paths))

    def __getattr__(self, name):
        # BaseHTTPRequestHandler answers unknown methods with 501; we answer every non-GET with 405.
        if name.startswith("do_"):
            return self._not_allowed
        raise AttributeError(name)

    def _send(self, status, headers, body):
        self.send_response(status)
        for key, value in dict(SECURITY_HEADERS, **headers).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format, *args):
        if not str(args[1] if len(args) > 1 else "").startswith("2"):
            sys.stderr.write("%s %s\n" % (self.log_date_time_string(), format % args))


class LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind would resolve a host name (getfqdn); loopback needs none.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def make_server(paths, port=DEFAULT_PORT):
    handler = type("BoundHandler", (Handler,), {"paths": paths})
    return LoopbackServer((HOST, port), handler)


def main(argv=None):
    from ..__main__ import allowed_path

    parser = argparse.ArgumentParser(prog="python3 -m jupiter_bot.dashboard",
                                     description="Read-only dashboard on http://127.0.0.1:PORT/")
    parser.add_argument("--journal", help="observation journal (default: DATA_DIR/observations.db)")
    parser.add_argument("--data-dir", help="default ~/.local/share/jupiter-bot")
    parser.add_argument("--mandate", help="default ~/.config/jupiter-bot/mandate.json")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    paths = data.Paths.defaults(
        journal=allowed_path(args.journal) if args.journal else None,
        data_dir=allowed_path(args.data_dir) if args.data_dir else None,
        mandate=allowed_path(args.mandate) if args.mandate else None)
    paths = data.Paths(journal=allowed_path(paths.journal), data_dir=allowed_path(paths.data_dir),
                       mandate=allowed_path(paths.mandate), repo=paths.repo)
    server = make_server(paths, args.port)
    print("jupiter_bot dashboard: http://%s:%d/  (journal %s, read-only)" % (HOST, server.server_port, paths.journal),
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
