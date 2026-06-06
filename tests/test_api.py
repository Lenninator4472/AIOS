"""Tests for kernel/api.py — HTTP REST API Service."""

import json
import os
import time
import urllib.request
import urllib.error

from kernel.bus import EventBus
from kernel.api import RestAPI
from kernel.vfs import VirtualFileSystem


class _MockScheduler:
    """Minimal scheduler mock for API tests."""

    def schedule(self, command):
        return "mock-task-id"


class _MockOrchestrator:
    """Minimal orchestrator mock for API tests."""

    def __init__(self):
        self.agents = {"test-agent": _MockAgent()}

    def get(self, name):
        return self.agents.get(name)

    def delegate(self, name, task):
        return {"result": f"handled by {name}: {task}"}


class _MockAgent:
    def process(self, task):
        return {"user_response": f"processed: {task}"}


class _MockFacts:
    def count(self):
        return 42


def _base_url():
    port = os.environ.get("FIRAI_API_PORT", "8765")
    return f"http://localhost:{port}"


def _get(path):
    return urllib.request.urlopen(f"{_base_url()}{path}", timeout=5)


def _post(path, body):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{_base_url()}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(req, timeout=5)


class TestRestAPI:
    """RestAPI: lifecycle, routes, edge cases."""

    def test_has_correct_name(self):
        bus = EventBus()
        api = RestAPI(bus)
        assert api.name == "api"

    def test_is_a_service_subclass(self):
        bus = EventBus()
        api = RestAPI(bus)
        assert hasattr(api, "start")
        assert hasattr(api, "stop")
        assert hasattr(api, "health_check")

    def test_start_opens_port(self):
        bus = EventBus()
        api = RestAPI(bus)
        os.environ["FIRAI_API_PORT"] = "18766"
        try:
            api.start()
            time.sleep(0.2)
            resp = urllib.request.urlopen("http://localhost:18766/health", timeout=5)
            assert resp.status == 200
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_get_health_returns_200_with_json_body(self):
        bus = EventBus()
        api = RestAPI(bus)
        os.environ["FIRAI_API_PORT"] = "18767"
        try:
            api.start()
            time.sleep(0.2)
            resp = _get("/health")
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["status"] == "ok"
            assert "uptime" in data
            assert data["version"] == "0.1.0"
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_get_vfs_nonexistent_returns_404(self):
        bus = EventBus()
        vfs = VirtualFileSystem()
        vfs.mount("/test", reader=lambda: "content")
        api = RestAPI(bus, vfs=vfs)
        os.environ["FIRAI_API_PORT"] = "18768"
        try:
            api.start()
            time.sleep(0.2)
            try:
                _get("/vfs/nonexistent")
                assert False, "Expected 404"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_get_vfs_existing_returns_200(self):
        bus = EventBus()
        vfs = VirtualFileSystem()
        vfs.mount("/test", reader=lambda: "hello world")
        api = RestAPI(bus, vfs=vfs)
        os.environ["FIRAI_API_PORT"] = "18769"
        try:
            api.start()
            time.sleep(0.2)
            resp = _get("/vfs/test")
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["path"] == "/test"
            assert "hello world" in data["content"]
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_post_tasks_without_scheduler_returns_503(self):
        bus = EventBus()
        api = RestAPI(bus)  # No scheduler
        os.environ["FIRAI_API_PORT"] = "18770"
        try:
            api.start()
            time.sleep(0.2)
            try:
                _post("/tasks", {"command": "echo hello"})
                assert False, "Expected 503"
            except urllib.error.HTTPError as e:
                assert e.code == 503
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_post_tasks_with_scheduler_returns_task_id(self):
        bus = EventBus()
        api = RestAPI(bus, scheduler=_MockScheduler())
        os.environ["FIRAI_API_PORT"] = "18771"
        try:
            api.start()
            time.sleep(0.2)
            resp = _post("/tasks", {"command": "echo hello"})
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert "task_id" in data
            assert data["task_id"] == "mock-task-id"
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_post_agent_unknown_returns_404(self):
        bus = EventBus()
        api = RestAPI(bus, orchestrator=_MockOrchestrator())
        os.environ["FIRAI_API_PORT"] = "18772"
        try:
            api.start()
            time.sleep(0.2)
            try:
                _post("/agent/nonexistent", {"task": "do something"})
                assert False, "Expected 404"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_post_agent_known_returns_200(self):
        bus = EventBus()
        api = RestAPI(bus, orchestrator=_MockOrchestrator())
        os.environ["FIRAI_API_PORT"] = "18773"
        try:
            api.start()
            time.sleep(0.2)
            resp = _post("/agent/test-agent", {"task": "do something"})
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["agent"] == "test-agent"
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_get_facts_returns_count(self):
        bus = EventBus()
        api = RestAPI(bus, facts=_MockFacts())
        os.environ["FIRAI_API_PORT"] = "18774"
        try:
            api.start()
            time.sleep(0.2)
            resp = _get("/facts")
            assert resp.status == 200
            data = json.loads(resp.read().decode())
            assert data["count"] == 42
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_server_stops_cleanly(self):
        bus = EventBus()
        api = RestAPI(bus)
        api.start()
        api.stop()
        assert api.is_running is False
        # Double stop should be idempotent
        api.stop()
        assert api.is_running is False

    def test_multiple_requests_work(self):
        bus = EventBus()
        vfs = VirtualFileSystem()
        vfs.mount("/greeting", reader=lambda: "hi")
        api = RestAPI(bus, vfs=vfs)
        os.environ["FIRAI_API_PORT"] = "18775"
        try:
            api.start()
            time.sleep(0.2)
            # First request
            resp1 = _get("/health")
            assert resp1.status == 200
            # Second request
            resp2 = _get("/vfs/greeting")
            assert resp2.status == 200
            data2 = json.loads(resp2.read().decode())
            assert "hi" in data2["content"]
            # Third request
            try:
                _get("/vfs/ghost")
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_unknown_route_returns_404(self):
        bus = EventBus()
        api = RestAPI(bus)
        os.environ["FIRAI_API_PORT"] = "18776"
        try:
            api.start()
            time.sleep(0.2)
            try:
                _get("/some/unknown/route")
                assert False, "Expected 404"
            except urllib.error.HTTPError as e:
                assert e.code == 404
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]

    def test_post_tasks_without_command_returns_400(self):
        bus = EventBus()
        api = RestAPI(bus, scheduler=_MockScheduler())
        os.environ["FIRAI_API_PORT"] = "18777"
        try:
            api.start()
            time.sleep(0.2)
            try:
                _post("/tasks", {})
                assert False, "Expected 400"
            except urllib.error.HTTPError as e:
                assert e.code == 400
        finally:
            api.stop()
            del os.environ["FIRAI_API_PORT"]
