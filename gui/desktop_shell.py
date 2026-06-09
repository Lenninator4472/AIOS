"""
AIOS Desktop Shell
Single unified desktop window containing background, panel, overlays, and app store.
All desktop components live as children of one root window.
"""

import os
import sys
import subprocess

from PySide6.QtWidgets import QApplication, QWidget, QMenu, QFileDialog, QLabel
from PySide6.QtCore import Qt, QTimer, Signal, QRect
from PySide6.QtGui import (
    QKeySequence, QShortcut, QPainter, QLinearGradient, QBrush, QPixmap,
    QColor, QFont, QPen,
)

from gui.desktop import DesktopBackground
from gui.panel import SystemPanel
from gui.launcher import AppLauncher
from gui.notifications import NotificationManager
from gui.lockscreen import LockScreen
from gui.terminal_overlay import TerminalOverlay
from gui.llm_overlay import LLMOverlay
from gui.app_store import AppStoreWidget
from gui.theme import AISColors
from kernel.bus import EventBus


class DesktopShell(QWidget):
    """Single unified desktop window. All components are child widgets."""

    shell_ready = Signal()
    shell_exit_requested = Signal()

    def __init__(self, bus=None, wallpaper_path=None):
        super().__init__()
        self.bus = bus or EventBus()

        # Unified window: frameless, fullscreen
        flags = Qt.FramelessWindowHint | Qt.Window
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setWindowTitle("AIOS Desktop")

        # Wallpaper state
        self._wallpaper_pixmap = None
        self._wallpaper_path = wallpaper_path
        self._gradient_mode = wallpaper_path is None
        self._gradient_offset = 0.0

        # Desktop components (lazy-created child widgets)
        self.desktop = None        # DesktopBackground (embedded child)
        self.panel = None          # SystemPanel (embedded child)
        self.launcher = None       # AppLauncher
        self.notifications = None  # NotificationManager
        self.lockscreen = None     # LockScreen
        self.terminal_overlay = None  # TerminalOverlay
        self.llm_overlay = None       # LLMOverlay
        self.app_store = None         # AppStoreWidget

        # State
        self._is_running = False
        self._launcher_open = False
        self._locked = False
        self._shortcuts = []
        self._anim_timer = None
        self._kwin_interface = None

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Initialize and show all desktop components."""
        if self._is_running:
            return

        print("[AIOS DesktopShell] Starting desktop environment...")

        # Fill screen
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        self.setWindowState(Qt.WindowFullScreen)
        self.show()
        self.lower()

        # 1. Desktop background (embedded child — paints via our paintEvent)
        self.desktop = DesktopBackground(
            wallpaper_path=self._wallpaper_path,
            parent=self,
        )
        self.desktop.desktop_context_menu.connect(self._on_desktop_context_menu)
        self.desktop.setGeometry(self.rect())
        self.desktop.show()
        print("[AIOS DesktopShell] Desktop background created")

        # 2. System panel (embedded child)
        self.panel = SystemPanel(parent=self)
        self.panel.launcher_requested.connect(self._toggle_launcher)
        self.panel.llm_requested.connect(self._toggle_llm)
        self.panel.show_at_bottom()
        print("[AIOS DesktopShell] System panel created")

        # 3. Browser icon on desktop
        self.browser_icon = QLabel(self)
        self.browser_icon.setFixedSize(72, 80)
        self.browser_icon.setCursor(Qt.PointingHandCursor)
        self.browser_icon.setAlignment(Qt.AlignCenter)
        self.browser_icon.setStyleSheet(f"""
            QLabel {{
                background: {AISColors.primary.name()}30;
                color: {AISColors.primary_light.name()};
                border: 1px solid {AISColors.primary.name()}40;
                border-radius: 8px;
                font-size: 10px;
                padding: 4px;
            }}
            QLabel:hover {{
                background: {AISColors.primary.name()}50;
                border: 1px solid {AISColors.primary.name()}80;
            }}
        """)
        # Try all known browser executables
        browser_exe = self._find_browser()
        browser_name = os.path.basename(browser_exe).capitalize() if browser_exe else "Browser"
        self.browser_icon.setText(f"\U0001f310\n{browser_name}")
        self.browser_icon.move(40, 100)
        self.browser_icon.show()
        # Click to launch
        self.browser_icon.mousePressEvent = lambda ev: (
            subprocess.Popen([browser_exe]) if browser_exe else None
        )

        # 4. App launcher (hidden by default)
        self.launcher = AppLauncher()
        self.launcher.dismissed.connect(self._on_launcher_dismissed)
        print("[AIOS DesktopShell] App launcher ready")

        # 5. Notification manager
        self.notifications = NotificationManager()
        print("[AIOS DesktopShell] Notification manager ready")

        # 6. Lock screen
        self.lockscreen = LockScreen()
        self.lockscreen.unlocked.connect(self._on_unlocked)
        print("[AIOS DesktopShell] Lock screen ready")

        # 7. Terminal overlay
        self.terminal_overlay = TerminalOverlay(bus=self.bus)
        print("[AIOS DesktopShell] Terminal overlay ready")

        # 8. LLM chat overlay
        self.llm_overlay = LLMOverlay(bus=self.bus)
        print("[AIOS DesktopShell] LLM chat overlay ready")

        # 9. App store
        self.app_store = AppStoreWidget(parent=self)
        self.app_store.dismissed.connect(self._close_app_store)
        print("[AIOS DesktopShell] App store ready")

        # 10. Register keyboard shortcuts
        self._register_shortcuts()

        # 11. Gradient animation timer
        if self._gradient_mode:
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._animate_gradient)
            self._anim_timer.start(50)

        # 12. KWin DBus integration (deferred)
        QTimer.singleShot(2000, self._init_kwin_integration)

        # 13. Subscribe to EventBus
        self._subscribe_bus()

        self._is_running = True
        self.shell_ready.emit()
        print("[AIOS DesktopShell] Desktop environment ready")

    def _find_browser(self):
        """Find the first available browser on the system."""
        candidates = [
            "firefox", "google-chrome", "chromium", "brave-browser",
            "vivaldi", "opera", "microsoft-edge", "epiphany",
        ]
        for exe in candidates:
            path = subprocess.run(
                ["which", exe], capture_output=True, text=True
            ).stdout.strip()
            if path:
                return path
        return None

    def shutdown(self):
        """Clean shutdown of all desktop components."""
        print("[AIOS DesktopShell] Shutting down...")
        self._is_running = False

        if self._anim_timer and self._anim_timer.isActive():
            self._anim_timer.stop()
        if self.desktop:
            self.desktop.stop_animation()
        if self.panel:
            self.panel.clock.stop()
            self.panel.monitor.stop()
        if self.notifications:
            for bubble in list(self.notifications._notifications):
                bubble._dismiss()

        # Close all windows
        for w in [self.lockscreen, self.launcher, self.notifications,
                  self.terminal_overlay, self.llm_overlay,
                  self.app_store, self.panel, self.desktop]:
            if w:
                w.close()

        self.close()

    # ── Wallpaper ──────────────────────────────────────────────────────

    def set_wallpaper(self, path):
        """Load and set wallpaper image."""
        if os.path.isfile(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self._wallpaper_pixmap = pixmap
                self._wallpaper_path = path
                self._gradient_mode = False
                if self._anim_timer and self._anim_timer.isActive():
                    self._anim_timer.stop()
                self.update()

    def clear_wallpaper(self):
        """Revert to gradient wallpaper."""
        self._wallpaper_pixmap = None
        self._wallpaper_path = None
        self._gradient_mode = True
        if not self._anim_timer:
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._animate_gradient)
            self._anim_timer.start(50)
        self.update()

    def _animate_gradient(self):
        self._gradient_offset += 0.002
        if self._gradient_offset > 1.0:
            self._gradient_offset = 0.0
        self.update()

    def paintEvent(self, event):
        """Draw wallpaper or gradient background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()

        if self._wallpaper_pixmap and not self._wallpaper_pixmap.isNull():
            scaled = self._wallpaper_pixmap.scaled(
                rect.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            self._draw_gradient(painter, rect)

    def _draw_gradient(self, painter, rect):
        """Draw animated gradient wallpaper."""
        offset = self._gradient_offset
        grad = QLinearGradient(0, 0, rect.width(), rect.height())
        grad.setColorAt(0.0, QColor(13, 13, 26))
        grad.setColorAt(0.3 + offset * 0.1, QColor(20, 15, 40))
        grad.setColorAt(0.6 + offset * 0.05, QColor(26, 18, 50))
        grad.setColorAt(1.0, QColor(10, 10, 22))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRect(rect)

        # Corner glow
        glow = QLinearGradient(0, 0, rect.width() * 0.3, rect.height() * 0.3)
        glow.setColorAt(0.0, QColor(124, 58, 237, 30))
        glow.setColorAt(1.0, QColor(124, 58, 237, 0))
        painter.setBrush(QBrush(glow))
        painter.drawRect(0, 0, rect.width() // 3, rect.height() // 3)

        glow2 = QLinearGradient(
            rect.width(), rect.height(),
            rect.width() * 0.7, rect.height() * 0.7,
        )
        glow2.setColorAt(0.0, QColor(6, 182, 212, 25))
        glow2.setColorAt(1.0, QColor(6, 182, 212, 0))
        painter.setBrush(QBrush(glow2))
        painter.drawRect(
            rect.width() * 2 // 3, rect.height() * 2 // 3,
            rect.width() // 3, rect.height() // 3,
        )

        # Watermark
        painter.setPen(QColor(124, 58, 237, 40))
        font = QFont("Segoe UI", 11)
        painter.setFont(font)
        painter.drawText(
            rect.width() - 120, rect.height() - 30,
            100, 20,
            Qt.AlignRight | Qt.AlignVCenter,
            "\u2b21 AIOS",
        )

    def _context_menu_style(self):
        return f"""
            QMenu {{
                background: {AISColors.surface.name()};
                border: 1px solid {AISColors.border.name()};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 8px 24px;
                border-radius: 4px;
                color: {AISColors.text.name()};
            }}
            QMenu::item:selected {{
                background: {AISColors.primary.name()}30;
                color: {AISColors.primary_light.name()};
            }}
            QMenu::separator {{
                height: 1px;
                background: {AISColors.border.name()};
                margin: 4px 8px;
            }}
        """

    # ── Context Menu ───────────────────────────────────────────────────

    def _on_desktop_context_menu(self, pos):
        """Handle right-click on desktop — show context menu."""
        menu = QMenu()
        menu.setStyleSheet(self._context_menu_style())

        term_action = menu.addAction("\U0001f5a5  Open Terminal")
        term_action.triggered.connect(self._toggle_terminal)

        llm_action = menu.addAction("\U0001f4ac  LLM Chat")
        llm_action.triggered.connect(self._toggle_llm)

        store_action = menu.addAction("\U0001f4e6  App Store")
        store_action.triggered.connect(self._open_app_store)

        menu.addSeparator()

        wallpaper_action = menu.addAction("\U0001f5bc  Change Wallpaper...")
        wallpaper_action.triggered.connect(self._show_wallpaper_dialog)

        menu.addSeparator()

        lock_action = menu.addAction("\U0001f512  Lock Screen")
        lock_action.triggered.connect(self._lock_screen)

        menu.addSeparator()

        power_action = menu.addAction("\u23f0  Power Off")
        power_action.triggered.connect(self.request_shutdown)

        restart_action = menu.addAction("\U0001f504  Restart")
        restart_action.triggered.connect(self.request_restart)

        logout_action = menu.addAction("\U0001f6aa  Log Out")
        logout_action.triggered.connect(self.request_logout)

        menu.exec(pos)

    # ── Overlay Toggles ────────────────────────────────────────────────

    def _toggle_terminal(self):
        if self.terminal_overlay and self.terminal_overlay.isVisible():
            self.terminal_overlay.hide_overlay()
        elif self.terminal_overlay:
            self.terminal_overlay.show_overlay()
            self.terminal_overlay.raise_()

    def _toggle_llm(self):
        if self.llm_overlay and self.llm_overlay.isVisible():
            self.llm_overlay.hide_overlay()
        elif self.llm_overlay:
            self.llm_overlay.show_overlay()
            self.llm_overlay.raise_()

    def _open_app_store(self):
        if self.app_store:
            self.app_store.show_store()
            self.app_store.raise_()

    def _close_app_store(self):
        pass  # already hidden by AppStoreWidget.dismiss()

    def _toggle_launcher(self):
        if self._launcher_open:
            self.launcher.hide()
            self._launcher_open = False
        else:
            self.launcher.show_launcher()
            self._launcher_open = True

    def _on_launcher_dismissed(self):
        self._launcher_open = False

    def _lock_screen(self):
        if not self._locked:
            self.lockscreen.lock()
            self.lockscreen.raise_()
            self._locked = True

    def _unlock_screen(self):
        self._locked = False

    def _on_unlocked(self):
        self._locked = False

    # ── Keyboard Shortcuts ─────────────────────────────────────────────

    def _register_shortcuts(self):
        shortcuts = []

        sup_shortcut = QShortcut(QKeySequence(Qt.Key_Super_L), self)
        sup_shortcut.activated.connect(self._toggle_launcher)
        shortcuts.append(sup_shortcut)

        sup_space = QShortcut(QKeySequence("Meta+Space"), self)
        sup_space.activated.connect(self._toggle_launcher)
        shortcuts.append(sup_space)

        lock_shortcut = QShortcut(QKeySequence("Ctrl+Alt+L"), self)
        lock_shortcut.activated.connect(self._lock_screen)
        shortcuts.append(lock_shortcut)

        term_shortcut = QShortcut(QKeySequence("Meta+T"), self)
        term_shortcut.activated.connect(self._toggle_terminal)
        shortcuts.append(term_shortcut)

        llm_shortcut = QShortcut(QKeySequence("Meta+L"), self)
        llm_shortcut.activated.connect(self._toggle_llm)
        shortcuts.append(llm_shortcut)

        store_shortcut = QShortcut(QKeySequence("Meta+A"), self)
        store_shortcut.activated.connect(self._open_app_store)
        shortcuts.append(store_shortcut)

        show_desktop = QShortcut(QKeySequence("Meta+D"), self)
        show_desktop.activated.connect(self._show_desktop)
        shortcuts.append(show_desktop)

        self._shortcuts = shortcuts

    # ── Bus Subscription ───────────────────────────────────────────────

    def _subscribe_bus(self):
        self.bus.subscribe("desktop.wallpaper.set", self._on_set_wallpaper)
        self.bus.subscribe("desktop.lock", lambda ev, dt: self._lock_screen())
        self.bus.subscribe("desktop.unlock", lambda ev, dt: self._unlock_screen())
        self.bus.subscribe("desktop.notify", self._on_notify_event)
        self.bus.subscribe("desktop.launch", self._on_launch_event)
        self.bus.subscribe("system.shutdown", lambda ev, dt: self.request_shutdown())
        self.bus.subscribe("system.restart", lambda ev, dt: self.request_restart())
        self.bus.subscribe("system.logout", lambda ev, dt: self.request_logout())

    # ── Event Handlers ─────────────────────────────────────────────────

    def _on_set_wallpaper(self, event_type, data):
        if not data:
            return
        path = data.get("path", "")
        if path:
            self.set_wallpaper(path)

    def _on_notify_event(self, event_type, data):
        if self.notifications:
            self.notifications.show_notification(
                app_name=data.get("app_name", "AIOS"),
                title=data.get("title", ""),
                body=data.get("body", ""),
                urgency=data.get("urgency", "normal"),
            )

    def _on_launch_event(self, event_type, data):
        command = data.get("command", "")
        if command:
            try:
                subprocess.Popen(command, shell=True)
            except Exception as e:
                print(f"[AIOS DesktopShell] Launch error: {e}")

    def _show_wallpaper_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            None, "Select Wallpaper", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.svg)",
        )
        if path:
            self.bus.emit("desktop.wallpaper.set", {"path": path})

    def _show_desktop(self):
        if self._kwin_interface:
            try:
                self._kwin_interface.showDesktop()
            except Exception:
                pass
        else:
            try:
                subprocess.run(["wmctrl", "-k", "on"], capture_output=True)
            except FileNotFoundError:
                pass

    def request_shutdown(self):
        try:
            subprocess.run(["loginctl", "poweroff"], capture_output=True)
        except FileNotFoundError:
            subprocess.run(["systemctl", "poweroff", "-i"], capture_output=True)

    def request_restart(self):
        try:
            subprocess.run(["loginctl", "reboot"], capture_output=True)
        except FileNotFoundError:
            subprocess.run(["systemctl", "reboot", "-i"], capture_output=True)

    def request_logout(self):
        self.shell_exit_requested.emit()
        QApplication.quit()

    def _init_kwin_integration(self):
        try:
            import dbus
            bus = dbus.SessionBus()
            kwin = bus.get_object("org.kde.KWin", "/KWin")
            self._kwin_interface = dbus.Interface(kwin, "org.kde.KWin")
            print("[AIOS DesktopShell] KWin DBus integration active")
        except Exception as e:
            print(f"[AIOS DesktopShell] KWin DBus not available: {e}")
            self._kwin_interface = None

    def _restack_desktop(self):
        if self.desktop:
            self.desktop.lower()

    def contextMenuEvent(self, event):
        self._on_desktop_context_menu(event.globalPos())


def run_desktop_shell(bus=None):
    """Main entry point for the AIOS desktop shell."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    from gui.theme import AITheme
    AITheme.apply(app)

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, project_root)

    shell = DesktopShell(bus=bus)
    shell.start()

    return app, shell
