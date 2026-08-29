from __future__ import annotations

import json
import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .store import RunStore


def serve_dashboard(database: str, host: str = "127.0.0.1", port: int = 8765, auth_token: str | None = None) -> None:
    server = create_dashboard_server(database, host, port, auth_token)
    actual_host, actual_port = server.server_address[:2]
    if isinstance(actual_host, bytes):
        actual_host = actual_host.decode()
    print(f"Agent Harness dashboard: http://{actual_host}:{actual_port}")
    server.serve_forever()


def create_dashboard_server(database: str, host: str = "127.0.0.1", port: int = 8765, auth_token: str | None = None) -> ThreadingHTTPServer:
    store = RunStore(database)
    token = auth_token or os.environ.get("AGENT_HARNESS_AUTH_TOKEN")
    app_html = Path(__file__).with_name("web").joinpath("index.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        server_version = "AgentHarness/1.0"

        def do_GET(self) -> None:
            if self.path == "/" or self.path == "/index.html":
                return self._send(app_html, "text/html; charset=utf-8")
            if not self._authorized(token):
                return self._json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            if self.path == "/api/health":
                return self._json({"ok": True, "schema_version": 1})
            if self.path.startswith("/api/runs/"):
                run = store.get_run(self.path.removeprefix("/api/runs/"))
                return self._json(run or {"error": "not_found"}, HTTPStatus.OK if run else HTTPStatus.NOT_FOUND)
            if self.path == "/api/runs":
                return self._json(store.list_runs())
            if self.path.startswith("/api/reviews"):
                status = "pending" if "status=pending" in self.path else None
                return self._json(store.list_reviews(status))
            return self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            if not self._authorized(token):
                return self._json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
            match = re.fullmatch(r"/api/reviews/([a-f0-9]+)", self.path)
            if not match:
                return self._json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            try:
                length = min(int(self.headers.get("Content-Length", "0")), 64_000)
                payload = json.loads(self.rfile.read(length))
                review = store.decide_review(match.group(1), payload["decision"], payload.get("notes", ""), payload.get("reviewer", "human"), int(payload["version"]))
                return self._json(review)
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except RuntimeError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.CONFLICT)

        def _authorized(self, expected: str | None) -> bool:
            return not expected or self.headers.get("Authorization") == f"Bearer {expected}"

        def _json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send(json.dumps(value).encode(), "application/json", status)

        def _send(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            print(f"dashboard {self.address_string()} {format % args}")

    return ThreadingHTTPServer((host, port), Handler)
