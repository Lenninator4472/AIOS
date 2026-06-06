"""Tests for kernel/cron.py — Cron Service."""

import os
import tempfile
import time
from datetime import datetime

from kernel.bus import EventBus
from kernel.cron import (
    CronService,
    parse_cron_expression,
    cron_matches,
    next_run,
    _parse_cron_field,
)


class TestCronExpressionParser:
    """Cron expression parsing utilities."""

    def test_parse_star(self):
        result = parse_cron_expression("* * * * *")
        assert result is not None
        assert result["minute"] == set(range(0, 60))
        assert result["hour"] == set(range(0, 24))
        assert result["day"] == set(range(1, 32))
        assert result["month"] == set(range(1, 13))
        assert result["weekday"] == set(range(0, 7))

    def test_parse_single_number(self):
        result = parse_cron_expression("30 * * * *")
        assert result is not None
        assert result["minute"] == {30}

    def test_parse_comma_separated(self):
        result = parse_cron_expression("0 9,18 * * *")
        assert result is not None
        assert result["hour"] == {9, 18}

    def test_parse_step(self):
        result = parse_cron_expression("*/15 * * * *")
        assert result is not None
        assert 0 in result["minute"]
        assert 15 in result["minute"]
        assert 30 in result["minute"]
        assert 45 in result["minute"]

    def test_invalid_expression_returns_none(self):
        assert parse_cron_expression("") is None
        assert parse_cron_expression("* * *") is None
        assert parse_cron_expression("* * * * * *") is None

    def test_cron_matches(self):
        parsed = parse_cron_expression("30 14 * * *")
        assert parsed is not None

        # Create a datetime that should match
        dt = datetime(2026, 6, 6, 14, 30)
        assert cron_matches(parsed, dt) is True

        # Create a datetime that should not match
        dt2 = datetime(2026, 6, 6, 15, 30)
        assert cron_matches(parsed, dt2) is False

    def test_next_run(self):
        parsed = parse_cron_expression("0 9 * * *")
        assert parsed is not None

        after = datetime(2026, 6, 6, 8, 0)
        nxt = next_run(parsed, after)
        assert nxt is not None
        assert nxt.hour == 9
        assert nxt.minute == 0

    def test_parse_cron_field_star(self):
        result = _parse_cron_field("*", 0, 59)
        assert result == set(range(0, 60))

    def test_parse_cron_field_step(self):
        result = _parse_cron_field("*/10", 0, 59)
        assert 0 in result
        assert 10 in result
        assert 20 in result
        assert 50 in result
        assert 55 not in result


class TestCronService:
    """CronService: schedule, unschedule, list, persistence."""

    def test_constructor_sets_name(self):
        bus = EventBus()
        cron = CronService(bus)
        assert cron.name == "cron"

    def test_schedule_returns_job_id_string(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            job_id = cron.schedule("* * * * *", "echo hello")
            assert isinstance(job_id, str)
            assert len(job_id) > 0
        finally:
            os.unlink(db_path)

    def test_list_jobs_returns_scheduled_jobs(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            cron.schedule("0 9 * * *", "echo morning")
            cron.schedule("0 18 * * *", "echo evening")
            jobs = cron.list_jobs()
            assert len(jobs) == 2
            commands = [j["command"] for j in jobs]
            assert "echo morning" in commands
            assert "echo evening" in commands
        finally:
            os.unlink(db_path)

    def test_unschedule_removes_job(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            job_id = cron.schedule("0 9 * * *", "echo test")
            assert len(cron.list_jobs()) == 1
            result = cron.unschedule(job_id)
            assert result is True
            assert len(cron.list_jobs()) == 0
        finally:
            os.unlink(db_path)

    def test_unschedule_nonexistent_returns_false(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            result = cron.unschedule("nonexistent-id")
            assert result is False
        finally:
            os.unlink(db_path)

    def test_persists_jobs_across_restarts(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron1 = CronService(bus, db_path=db_path)
            cron1.schedule("30 14 * * *", "echo persist")
            cron1.schedule("0 9 * * *", "echo another")
            del cron1

            # Create a new instance with the same DB
            cron2 = CronService(bus, db_path=db_path)
            jobs = cron2.list_jobs()
            assert len(jobs) == 2
        finally:
            os.unlink(db_path)

    def test_get_next_runs_returns_correct_count(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            cron.schedule("0 9 * * *", "echo morning")
            cron.schedule("0 18 * * *", "echo evening")
            runs = cron.get_next_runs(count=3)
            assert len(runs) <= 3
            for jid, cmd, ts in runs:
                assert isinstance(jid, str)
                assert isinstance(cmd, str)
                assert isinstance(ts, str)
        finally:
            os.unlink(db_path)

    def test_emits_cron_job_trigger_on_match(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            cron.start()

            received = []
            def handler(et, data):
                received.append(data)

            bus.subscribe("cron.job.trigger", handler)

            # Directly trigger the tick logic with a matching expression
            now = datetime.utcnow()
            expression = f"{now.minute} {now.hour} {now.day} {now.month} *"
            cron.schedule(expression, "echo now")

            # Run tick
            cron._tick()
            time.sleep(0.1)

            triggered = [e for e in received if e.get("command") == "echo now"]
            assert len(triggered) >= 1
            cron.stop()
        finally:
            os.unlink(db_path)

    def test_list_jobs_returns_created_at(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            cron.schedule("0 12 * * *", "echo lunch")
            jobs = cron.list_jobs()
            assert "created_at" in jobs[0]
            assert jobs[0]["created_at"] is not None
        finally:
            os.unlink(db_path)

    def test_invalid_expression_raises_value_error(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            import pytest
            with pytest.raises(ValueError):
                cron.schedule("invalid", "echo fail")
        finally:
            os.unlink(db_path)

    def test_health_check(self):
        bus = EventBus()
        _, db_path = tempfile.mkstemp(suffix=".db")
        os.close(_)
        try:
            cron = CronService(bus, db_path=db_path)
            hc = cron.health_check()
            assert hc["name"] == "cron"
        finally:
            os.unlink(db_path)
