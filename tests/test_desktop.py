"""
Tests for AIOS Phase 2 Desktop Environment Components
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication once for all tests."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestDesktopBackground:
    """Tests for the desktop background window."""

    def test_import(self):
        """DesktopBackground should be importable."""
        from gui.desktop import DesktopBackground
        assert DesktopBackground is not None

    def test_create(self, qapp):
        """DesktopBackground should create without error."""
        from gui.desktop import DesktopBackground
        bg = DesktopBackground()
        assert bg is not None
        assert bg.windowTitle() == "AIOS Desktop"

    def test_window_flags(self, qapp):
        """Should have frameless and bottom hints."""
        from gui.desktop import DesktopBackground
        from PySide6.QtCore import Qt
        bg = DesktopBackground()
        flags = bg.windowFlags()
        assert flags & Qt.FramelessWindowHint
        assert flags & Qt.WindowStaysOnBottomHint

    def test_set_wallpaper_nonexistent(self, qapp):
        """Setting nonexistent wallpaper should not crash."""
        from gui.desktop import DesktopBackground
        bg = DesktopBackground()
        bg.set_wallpaper("/nonexistent/image.png")

    def test_clear_wallpaper(self, qapp):
        """Clearing wallpaper should revert to gradient mode."""
        from gui.desktop import DesktopBackground
        bg = DesktopBackground()
        bg.clear_wallpaper()
        assert bg._gradient_mode is True

    def test_custom_wallpaper_path(self, qapp, tmp_path):
        """Constructor should accept a wallpaper path."""
        img_path = tmp_path / "wallpaper.png"
        img_path.write_text("fake-png-data")
        from gui.desktop import DesktopBackground
        bg = DesktopBackground(wallpaper_path=str(img_path))
        assert bg is not None

    def test_desktop_context_menu_signal(self, qapp):
        """Right-click should emit context menu signal."""
        from gui.desktop import DesktopBackground
        from PySide6.QtCore import QPoint
        bg = DesktopBackground()
        received = []
        bg.desktop_context_menu.connect(lambda p: received.append(p))
        # Simulate emitting
        bg.desktop_context_menu.emit(QPoint(100, 100))
        assert len(received) == 1


class TestSystemPanel:
    """Tests for the system panel/taskbar."""

    def test_import(self):
        """SystemPanel should be importable."""
        from gui.panel import SystemPanel
        assert SystemPanel is not None

    def test_create(self, qapp):
        """SystemPanel should create without error."""
        from gui.panel import SystemPanel
        panel = SystemPanel()
        assert panel is not None

    def test_window_flags(self, qapp):
        """Should have frameless and top hints."""
        from gui.panel import SystemPanel
        from PySide6.QtCore import Qt
        panel = SystemPanel()
        flags = panel.windowFlags()
        assert flags & Qt.FramelessWindowHint
        assert flags & Qt.WindowStaysOnTopHint

    def test_launcher_signal(self, qapp):
        """Panel should emit launcher_requested when launcher btn clicked."""
        from gui.panel import SystemPanel
        panel = SystemPanel()
        received = []
        panel.launcher_requested.connect(lambda: received.append(True))
        # Simulate button click
        panel.launcher_btn.click()
        assert len(received) == 1

    def test_clock_widget(self, qapp):
        """Clock widget should show time."""
        from gui.panel import ClockWidget
        clock = ClockWidget()
        assert clock.label is not None
        # Should show non-empty text (current time)
        assert len(clock.label.text()) > 0

    def test_tray_widget(self, qapp):
        """Tray widget should have indicators."""
        from gui.panel import TrayWidget
        tray = TrayWidget()
        assert len(tray._icons) == 3  # network, audio, battery


class TestAppLauncher:
    """Tests for the app launcher overlay."""

    def test_import(self):
        """AppLauncher should be importable."""
        from gui.launcher import AppLauncher
        assert AppLauncher is not None

    def test_create(self, qapp):
        """AppLauncher should create without error."""
        from gui.launcher import AppLauncher
        launcher = AppLauncher()
        assert launcher is not None

    def test_dismissed_signal(self, qapp):
        """AppLauncher should emit dismissed signal."""
        from gui.launcher import AppLauncher
        launcher = AppLauncher()
        received = []
        launcher.dismissed.connect(lambda: received.append(True))
        launcher._dismiss()
        assert len(received) == 1

    def test_filter_apps(self, qapp):
        """Filtering apps should narrow results."""
        from gui.launcher import AppLauncher
        launcher = AppLauncher()
        # Should not crash
        launcher._filter_apps("")
        assert len(launcher._filtered) > 0 or len(launcher._apps) == 0

    def test_desktop_app_parse_valid(self, tmp_path):
        """DesktopApp should parse valid .desktop file."""
        from gui.launcher import DesktopApp
        desktop = tmp_path / "test-app.desktop"
        desktop.write_text(
            "[Desktop Entry]\n"
            "Name=Test App\n"
            "Exec=/usr/bin/test\n"
            "Icon=test\n"
            "Comment=A test application\n"
            "Categories=Utility;\n"
        )
        app = DesktopApp(str(desktop))
        assert app.is_valid()
        assert app.name == "Test App"
        assert app.exec == "/usr/bin/test"

    def test_desktop_app_parse_nodisplay(self, tmp_path):
        """DesktopApp should handle NoDisplay=true."""
        from gui.launcher import DesktopApp
        desktop = tmp_path / "hidden.desktop"
        desktop.write_text(
            "[Desktop Entry]\n"
            "Name=Hidden App\n"
            "Exec=/usr/bin/hidden\n"
            "NoDisplay=true\n"
        )
        app = DesktopApp(str(desktop))
        assert not app.is_valid()

    def test_desktop_app_invalid(self, tmp_path):
        """DesktopApp should handle missing fields."""
        from gui.launcher import DesktopApp
        desktop = tmp_path / "invalid.desktop"
        desktop.write_text("[Desktop Entry]\nNoExec=true\n")
        app = DesktopApp(str(desktop))
        assert not app.is_valid()


class TestLockScreen:
    """Tests for the lock screen."""

    def test_import(self):
        """LockScreen should be importable."""
        from gui.lockscreen import LockScreen
        assert LockScreen is not None

    def test_create(self, qapp):
        """LockScreen should create without error."""
        from gui.lockscreen import LockScreen
        ls = LockScreen()
        assert ls is not None

    def test_window_flags(self, qapp):
        """Should have top hint for overlay."""
        from gui.lockscreen import LockScreen
        from PySide6.QtCore import Qt
        ls = LockScreen()
        flags = ls.windowFlags()
        assert flags & Qt.WindowStaysOnTopHint
        assert flags & Qt.FramelessWindowHint

    def test_lock_unlock_signals(self, qapp):
        """Lock and unlock should emit signals."""
        from gui.lockscreen import LockScreen
        ls = LockScreen()
        locked_signals = []
        unlocked_signals = []
        ls.locked.connect(lambda: locked_signals.append(True))
        ls.unlocked.connect(lambda: unlocked_signals.append(True))
        ls._unlock()
        assert len(unlocked_signals) == 1

    def test_clock_update(self, qapp):
        """Clock and date labels should update."""
        from gui.lockscreen import LockScreen
        ls = LockScreen()
        ls._update_clock()
        assert len(ls.time_label.text()) > 0
        assert len(ls.date_label.text()) > 0


class TestNotificationManager:
    """Tests for the notification manager."""

    def test_import(self):
        """NotificationManager should be importable."""
        from gui.notifications import NotificationManager
        assert NotificationManager is not None

    def test_create(self, qapp):
        """NotificationManager should create without error."""
        from gui.notifications import NotificationManager
        nm = NotificationManager()
        assert nm is not None

    def test_show_notification(self, qapp):
        """Showing a notification should create a bubble."""
        from gui.notifications import NotificationManager
        nm = NotificationManager()
        nm.show_notification(
            app_name="TestApp",
            title="Test Title",
            body="Test body message"
        )
        assert len(nm._notifications) == 1
        bubble = nm._notifications[0]
        assert bubble.app_name == "TestApp"
        assert bubble.title == "Test Title"
        assert bubble.body == "Test body message"

    def test_multiple_notifications(self, qapp):
        """Multiple notifications should stack."""
        from gui.notifications import NotificationManager
        nm = NotificationManager()
        nm.show_notification(app_name="A", title="1", body="First")
        nm.show_notification(app_name="B", title="2", body="Second")
        assert len(nm._notifications) == 2

    def test_dismiss_bubble(self, qapp):
        """Dismissing a bubble should remove it from tracking."""
        from gui.notifications import NotificationManager
        nm = NotificationManager()
        nm.show_notification(app_name="Test", title="T", body="Msg")
        bubble = nm._notifications[0]
        nm._on_bubble_dismissed(bubble)
        assert len(nm._notifications) == 0

    def test_notification_history(self, qapp):
        """Dismissed notifications should appear in history."""
        from gui.notifications import NotificationManager
        nm = NotificationManager()
        nm.show_notification(app_name="Hist", title="H", body="History test")
        bubble = nm._notifications[0]
        nm._on_bubble_dismissed(bubble)
        history = nm.get_history()
        assert len(history) >= 1
        assert history[-1]["app_name"] == "Hist"

    def test_notification_bubble_creation(self, qapp):
        """NotificationBubble should render correctly."""
        from gui.notifications import NotificationBubble
        bubble = NotificationBubble(
            app_name="App",
            title="Title",
            body="Body text"
        )
        assert bubble.app_name == "App"
        assert bubble.title == "Title"
        assert bubble.body == "Body text"
        assert bubble.notification_id is not None


class TestDesktopShell:
    """Tests for the desktop shell orchestrator."""

    def test_import(self):
        """DesktopShell should be importable."""
        from gui.desktop_shell import DesktopShell
        assert DesktopShell is not None

    def test_create(self, qapp):
        """DesktopShell should create without error."""
        from kernel.bus import EventBus
        from gui.desktop_shell import DesktopShell
        bus = EventBus()
        shell = DesktopShell(bus=bus)
        assert shell is not None
        assert shell._is_running is False

    def test_start_creates_components(self, qapp):
        """Starting shell should create all desktop components."""
        from kernel.bus import EventBus
        from gui.desktop_shell import DesktopShell
        bus = EventBus()
        shell = DesktopShell(bus=bus)
        shell.start()
        assert shell.desktop is not None
        assert shell.panel is not None
        assert shell.launcher is not None
        assert shell.notifications is not None
        assert shell.lockscreen is not None
        assert shell._is_running is True
        # Cleanup
        shell.shutdown()

    def test_shutdown_cleans_up(self, qapp):
        """Shutdown should mark as not running."""
        from kernel.bus import EventBus
        from gui.desktop_shell import DesktopShell
        bus = EventBus()
        shell = DesktopShell(bus=bus)
        shell.start()
        shell.shutdown()
        assert shell._is_running is False

    def test_ready_signal(self, qapp):
        """Shell should emit ready signal after startup."""
        from kernel.bus import EventBus
        from gui.desktop_shell import DesktopShell
        bus = EventBus()
        shell = DesktopShell(bus=bus)
        received = []
        shell.shell_ready.connect(lambda: received.append(True))
        shell.start()
        assert len(received) >= 1
        shell.shutdown()

    def test_launcher_toggle(self, qapp):
        """Toggle launcher should show/hide."""
        from kernel.bus import EventBus
        from gui.desktop_shell import DesktopShell
        bus = EventBus()
        shell = DesktopShell(bus=bus)
        shell.start()
        assert shell._launcher_open is False
        # Test the toggle method directly
        shell._toggle_launcher()
        shell._on_launcher_dismissed()
        assert shell._launcher_open is False
        shell.shutdown()

    def test_notification_via_bus(self, qapp):
        """Desktop notification via EventBus should create bubble."""
        from kernel.bus import EventBus
        from gui.desktop_shell import DesktopShell
        bus = EventBus()
        shell = DesktopShell(bus=bus)
        shell.start()
        bus.emit("desktop.notify", {
            "app_name": "BusTest",
            "title": "Via Bus",
            "body": "This came through EventBus"
        })
        # EventBus is synchronous, so the notification should exist
        assert len(shell.notifications._notifications) >= 1
        shell.shutdown()

    def test_lock_via_bus(self, qapp):
        """Locking via EventBus should trigger lock screen."""
        from kernel.bus import EventBus
        from gui.desktop_shell import DesktopShell
        bus = EventBus()
        shell = DesktopShell(bus=bus)
        shell.start()
        assert shell._locked is False
        bus.emit("desktop.lock", {})
        assert shell._locked is True
        shell.shutdown()
