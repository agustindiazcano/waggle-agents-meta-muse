"""Minimal health-check server used by the Phase 0 placeholder services.

Each service runs ``python -m waggle.<service>`` and answers ``GET /health``.
Real implementations replace these in later phases.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def make_server(service: str, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            body = json.dumps({"service": service, "status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def run(service: str, default_port: int) -> None:
    port = int(os.environ.get("PORT", default_port))
    server = make_server(service, "0.0.0.0", port)
    server.serve_forever()
