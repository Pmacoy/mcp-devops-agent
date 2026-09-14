"""A minimal service standing in for "the app" in this demo.

It exists so list_services has more than one thing to say, and so the
demo stack looks like a small real system (a web tier + a background
worker + a queue) rather than a single container. It does not
participate in the incident scenario -- api stays healthy throughout;
worker is the one that breaks.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

START_TIME = datetime.now(timezone.utc)


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        import json

        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if self.path == "/health":
            self._json(200, {"status": "ok"})
            return
        if self.path == "/":
            uptime = (datetime.now(timezone.utc) - START_TIME).total_seconds()
            self._json(
                200,
                {
                    "service": "api",
                    "uptime_seconds": round(uptime, 1),
                    "redis_url": os.environ.get("REDIS_URL", ""),
                },
            )
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: object) -> None:  # quiet the default access log
        pass


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
