"""Tests for kernel/vfs.py — Virtual Filesystem."""
import pytest
from kernel.vfs import VirtualFileSystem, VFSError


@pytest.fixture
def vfs():
    fs = VirtualFileSystem()
    fs.mount("/memory", reader=lambda: "3 facts stored")
    fs.mount("/tasks", reader=lambda: "2 tasks running", is_dir=True)
    fs.mount("/tasks/active", reader=lambda: "task_abc: running")
    fs.mount("/system/uptime", reader=lambda: "0d 0h 12m")
    fs.mount("/system/hostname", reader=lambda: "ai-dos")
    return fs


class TestVirtualFileSystem:
    """VirtualFileSystem — mount, read, listdir, exists."""

    def test_read_file(self, vfs):
        content = vfs.read("/memory")
        assert "3 facts stored" in content

    def test_read_nested_file(self, vfs):
        content = vfs.read("/tasks/active")
        assert "task_abc" in content

    def test_read_deeply_nested(self, vfs):
        content = vfs.read("/system/uptime")
        assert "0d" in content
        content = vfs.read("/system/hostname")
        assert "ai-dos" in content

    def test_list_root(self, vfs):
        items = vfs.listdir("/")
        names = [n for n, _ in items]
        assert "memory" in names
        assert "tasks" in names
        assert "system" in names

    def test_list_dir(self, vfs):
        items = vfs.listdir("/tasks")
        names = [n for n, _ in items]
        assert "active" in names

    def test_exists(self, vfs):
        assert vfs.exists("/memory") is True
        assert vfs.exists("/nonexistent") is False

    def test_read_nonexistent_raises(self, vfs):
        with pytest.raises(VFSError):
            vfs.read("/ghost")

    def test_listdir_nonexistent_raises(self, vfs):
        with pytest.raises(VFSError):
            vfs.listdir("/ghost")

    def test_mount_over_existing_updates(self, vfs):
        vfs.mount("/memory", reader=lambda: "updated content")
        assert "updated" in vfs.read("/memory")

    def test_dir_format(self, vfs):
        content = vfs.read("/")
        assert "[dir]" in content
        assert "memory" in content

    def test_reader_exception_handled(self, vfs):
        def broken():
            raise RuntimeError("kaboom")
        vfs.mount("/broken", reader=broken)
        content = vfs.read("/broken")
        assert "error" in content

    def test_normalize_double_slash(self, vfs):
        assert vfs.exists("//memory") is True

    def test_trailing_slash(self, vfs):
        assert vfs.exists("/memory/") is True
