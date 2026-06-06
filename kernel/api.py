"""
AI-DOS Kernel: HTTP REST API Service
A tiny REST API server using only stdlib ``http.server``.
"""

import json
import os
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from kernel.bus import EventBus
from kernel.service import Service


_API_VERSION = "0.1.0"


def _json_response(handler, code: int, body: dict):
    """Write a JSON response with the given status code."""
    payload = json.dumps(body).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class _RequestHandler(BaseHTTPRequestHandler):
    """Internal request handler that delegates to the parent RestAPI."""

    # Suppress default logging to stderr
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        self.server._api._handle_request("GET", self.path, self, body=None)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {}
        self.server._api._handle_request("POST", self.path, self, body=parsed)


class RestAPI(Service):
    """
    Lightweight REST API server built on ``http.server.HTTPServer``.

    Default port is 8765; override via the ``FIRAI_API_PORT`` environment variable.

    Constructor receives optional references to kernel components for
    delegation.  Any of them may be ``None`` (degraded behaviour).

    Routes::

        GET  /health          → {"status": "ok", "uptime": "...", "version": "0.1.0"}
        GET  /vfs/*           → reads from the provided VFS instance
        POST /tasks           → schedules a command via the provided scheduler
        POST /agent/<name>    → delegates a task to the provided orchestrator
        GET  /facts           → returns fact count from the provided FactMemory
    """

    def __init__(self, bus: EventBus, vfs=None, scheduler=None,
                 orchestrator=None, facts=None):
        super().__init__("api", bus)
        self._vfs = vfs
        self._scheduler = scheduler
        self._orchestrator = orchestrator
        self._facts = facts
        self._start_time = datetime.now()
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _on_start(self):
        port = int(os.environ.get("FIRAI_API_PORT", "8765"))
        self._httpd = HTTPServer(("0.0.0.0", port), _RequestHandler)
        self._httpd._api = self  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def _on_stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    # ------------------------------------------------------------------
    # Route dispatcher
    # ------------------------------------------------------------------

    def _handle_request(self, method: str, path: str, handler, body: dict | None):
        parsed = urlparse(path)
        route = parsed.path

        self._bus.emit("api.request", {
            "method": method,
            "path": route,
            "timestamp": datetime.now().isoformat(),
        })

        try:
            if method == "GET" and route == "/health":
                self._handle_health(handler)
            elif method == "GET" and route.startswith("/vfs/"):
                self._handle_vfs_read(route, handler)
            elif method == "POST" and route == "/tasks":
                self._handle_create_task(body, handler)
            elif method == "POST" and route.startswith("/agent/"):
                self._handle_agent(route, body, handler)
            elif method == "GET" and route == "/facts":
                self._handle_facts(handler)
            else:
                _json_response(handler, 404, {"error": "Not found"})
        except Exception as e:
            _json_response(handler, 500, {"error": str(e)})

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    def _handle_health(self, handler):
        uptime = str(datetime.now() - self._start_time).split(".")[0]
        _json_response(handler, 200, {
            "status": "ok",
            "uptime": uptime,
            "version": _API_VERSION,
        })

    def _handle_vfs_read(self, route: str, handler):
        if self._vfs is None:
            _json_response(handler, 503, {"error": "VFS not available"})
            return
        vfs_path = "/" + route[len("/vfs/"):]
        vfs_path = vfs_path.rstrip("/") or "/"
        try:
            content = self._vfs.read(vfs_path)
            _json_response(handler, 200, {"path": vfs_path, "content": content})
        except Exception:
            _json_response(handler, 404, {"error": f"Path not found: {vfs_path}"})

    def _handle_create_task(self, body: dict | None, handler):
        if self._scheduler is None:
            _json_response(handler, 503, {"error": "Scheduler not available"})
            return
        command = (body or {}).get("command", "")
        if not command:
            _json_response(handler, 400, {"error": "Missing 'command' in body"})
            return
        task_id = self._scheduler.schedule(command)
        _json_response(handler, 200, {"task_id": task_id})

    def _handle_agent(self, route: str, body: dict | None, handler):
        if self._orchestrator is None:
            _json_response(handler, 503, {"error": "Orchestrator not available"})
            return
        agent_name = route[len("/agent/"):]
        if not agent_name:
            _json_response(handler, 400, {"error": "Missing agent name"})
            return
        task = (body or {}).get("task", "")
        if not task:
            _json_response(handler, 400, {"error": "Missing 'task' in body"})
            return

        agent = self._orchestrator.get(agent_name)
        if agent is None:
            _json_response(handler, 404, {"error": f"Unknown agent: {agent_name}"})
            return

        result = self._orchestrator.delegate(agent_name, task)
        _json_response(handler, 200, {"agent": agent_name, "result": result})

    def _handle_facts(self, handler):
        if self._facts is None:
            _json_response(handler, 503, {"error": "FactMemory not available"})
            return
        _json_response(handler, 200, {"count": self._facts.count()})
