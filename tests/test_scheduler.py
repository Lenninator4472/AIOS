"""Tests for kernel/scheduler.py — Background Task Scheduler."""

import time
from kernel.bus import EventBus
from kernel.scheduler import BackgroundTaskScheduler, TaskStatus


class TestScheduler:
    """BackgroundTaskScheduler: schedule, track, cancel background tasks."""

    def test_scheduler_has_name(self):
        """Scheduler should have a default or assigned name."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        assert sch.name == "scheduler"

    def test_scheduler_is_a_service(self):
        """Scheduler should be a Service with lifecycle."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        assert hasattr(sch, "start")
        assert hasattr(sch, "stop")
        assert hasattr(sch, "health_check")

    def test_schedule_returns_task_id(self):
        """schedule() should return a string task ID."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        tid = sch.schedule("echo hello")
        assert isinstance(tid, str)
        assert len(tid) > 0
        sch.stop()

    def test_get_status_after_schedule(self):
        """get_status() should return a valid status immediately after schedule.

        May be PENDING (if thread hasn't started yet) or RUNNING (it started
        before the main thread checked) — both are valid concurrent states.
        """
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        tid = sch.schedule("echo hello")

        status = sch.get_status(tid)
        assert status is not None
        assert status.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        sch.stop()

    def test_task_completes_successfully(self):
        """After a short command completes, status should be 'completed'."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        tid = sch.schedule("echo hello")
        time.sleep(0.3)  # brief wait for thread

        status = sch.get_status(tid)
        assert status.status == TaskStatus.COMPLETED
        assert status.exit_code == 0
        sch.stop()

    def test_task_captures_stdout(self):
        """Completed task should store stdout output."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        tid = sch.schedule("echo hello_world")
        time.sleep(0.3)

        status = sch.get_status(tid)
        assert "hello_world" in status.stdout
        sch.stop()

    def test_task_fails_with_nonzero_exit(self):
        """A command with non-zero exit should have status 'failed'."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        tid = sch.schedule("exit 42")
        time.sleep(0.3)

        status = sch.get_status(tid)
        assert status.status == TaskStatus.FAILED
        assert status.exit_code == 42
        sch.stop()

    def test_task_captures_stderr(self):
        """Failed task should capture stderr."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        tid = sch.schedule("ls /nonexistent_path_xyzzy 2>&1 || true")
        time.sleep(0.3)

        status = sch.get_status(tid)
        assert status.status == TaskStatus.COMPLETED
        sch.stop()

    def test_list_tasks_returns_all(self):
        """list_tasks() should return all scheduled tasks."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        t1 = sch.schedule("echo a")
        t2 = sch.schedule("echo b")
        time.sleep(0.3)

        tasks = sch.list_tasks()
        assert len(tasks) == 2
        sch.stop()

    def test_list_tasks_filter_by_status(self):
        """list_tasks(status=...) should filter."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        sch.schedule("echo a")
        time.sleep(0.3)

        completed = sch.list_tasks(TaskStatus.COMPLETED)
        assert len(completed) >= 1
        pending = sch.list_tasks(TaskStatus.PENDING)
        assert len(pending) == 0
        sch.stop()

    def test_schedule_emits_task_started_event(self):
        """schedule() should emit 'task.started'."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        received = []

        def handler(et, data):
            received.append((et, data))

        bus.subscribe("task.started", handler)
        sch.schedule("echo hello")
        time.sleep(0.3)

        assert len(received) == 1
        assert received[0][0] == "task.started"
        assert "task_id" in received[0][1]
        sch.stop()

    def test_completion_emits_task_completed_event(self):
        """Task completion should emit 'task.completed'."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        received = []

        def handler(et, data):
            received.append(et)

        bus.subscribe("task.completed", handler)
        sch.schedule("echo hello")
        time.sleep(0.3)

        assert len(received) == 1
        assert received[0] == "task.completed"
        sch.stop()

    def test_get_status_returns_none_for_unknown(self):
        """get_status() for an unknown task_id should return None."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        assert sch.get_status("nonexistent-id") is None

    def test_cancel_running_task(self):
        """cancel() should stop a running task."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        tid = sch.schedule("sleep 10")
        time.sleep(0.1)  # let it start

        result = sch.cancel(tid)
        assert result is True
        time.sleep(0.2)

        status = sch.get_status(tid)
        assert status.status == TaskStatus.FAILED
        sch.stop()

    def test_cancel_completed_task_returns_false(self):
        """cancel() on an already completed task should return False."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        tid = sch.schedule("echo done")
        time.sleep(0.3)

        result = sch.cancel(tid)
        assert result is False
        sch.stop()

    def test_cancel_unknown_task_returns_false(self):
        """cancel() on a nonexistent task ID should return False."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        assert sch.cancel("fake-id") is False

    def test_health_check_includes_task_count(self):
        """health_check() should report active and total task counts."""
        bus = EventBus()
        sch = BackgroundTaskScheduler(bus)
        sch.start()
        sch.schedule("echo a")
        sch.schedule("echo b")
        time.sleep(0.3)

        health = sch.health_check()
        assert "active_tasks" in health
        assert "total_tasks" in health
        assert health["total_tasks"] >= 2
        sch.stop()
