"""
AIOS Notification Manager
DBus org.freedesktop.Notifications service implementation.
Listens for system notifications and displays them as popup overlays.
"""

import uuid
import subprocess
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal, QRect, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPixmap, QLinearGradient, QBrush, QPen,
    QTextOption, QFontMetrics
)

from gui.theme import AISColors


class NotificationBubble(QWidget):
    """Single notification popup bubble."""

    dismissed = Signal(object)  # self

    def __init__(self, app_name, title, body, icon_data=None, urgency="normal", notification_id=None):
        super().__init__()
        self.app_name = app_name
        self.title = title
        self.body = body
        self.notification_id = notification_id or str(uuid.uuid4())[:8]
        self._timeout_ms = self._get_timeout(urgency)
        self._hovered = False

        # Window flags: always-on-top tooltip-style popup
        flags = Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint | Qt.ToolTip
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFocusPolicy(Qt.NoFocus)

        self.setFixedWidth(360)
        self.setMinimumHeight(80)
        self.setMaximumHeight(200)

        self._setup_ui()

        # Auto-dismiss timer
        if self._timeout_ms > 0:
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._dismiss)
            self._timer.setSingleShot(True)
            self._timer.start(self._timeout_ms)

    def _get_timeout(self, urgency):
        """Get timeout in ms based on urgency level."""
        if urgency == "critical":
            return 10000  # 10s for critical
        elif urgency == "low":
            return 3000   # 3s for low
        return 5000       # 5s normal

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # App name + time header
        header = QHBoxLayout()
        app_label = QLabel(self.app_name or "System")
        app_label.setFont(QFont("Segoe UI", 9, QFont.Bold))
        app_label.setStyleSheet(f"color: {AISColors.primary_light.name()}; background: transparent;")
        header.addWidget(app_label)
        header.addStretch()

        time_label = QLabel(datetime.now().strftime("%I:%M %p").lstrip("0"))
        time_label.setFont(QFont("Segoe UI", 8))
        time_label.setStyleSheet(f"color: {AISColors.text_dim.name()}; background: transparent;")
        header.addWidget(time_label)
        layout.addLayout(header)

        # Title
        if self.title:
            title_label = QLabel(self.title)
            title_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
            title_label.setStyleSheet(f"color: {AISColors.text.name()}; background: transparent;")
            title_label.setWordWrap(True)
            layout.addWidget(title_label)

        # Body
        if self.body:
            body_label = QLabel(self.body)
            body_label.setFont(QFont("Segoe UI", 10))
            body_label.setStyleSheet(f"color: {AISColors.text_muted.name()}; background: transparent;")
            body_label.setWordWrap(True)
            layout.addWidget(body_label)

    def _dismiss(self):
        """Animate dismissal and close."""
        self.dismissed.emit(self)
        self.hide()
        self.deleteLater()

    def enterEvent(self, event):
        self._hovered = True
        # Extend timeout while hovering
        if hasattr(self, '_timer') and self._timer.isActive():
            self._orig_interval = self._timer.interval()
            self._timer.setInterval(3000)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        if hasattr(self, '_timer') and self._timer.isActive() and hasattr(self, '_orig_interval'):
            self._timer.setInterval(self._orig_interval)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Click to dismiss immediately."""
        self._dismiss()

    def paintEvent(self, event):
        """Draw the notification bubble with dark theme styling."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        rect = self.rect()

        # Dark surface with slight transparency
        bg_color = QColor(26, 27, 46, 235)  # AISColors.surface with slight transparency
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(AISColors.border, 1))
        painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), 12, 12)

        # Left accent bar
        accent_grad = QLinearGradient(0, 0, 4, rect.height())
        accent_grad.setColorAt(0.0, AISColors.primary)
        accent_grad.setColorAt(1.0, QColor(6, 182, 212, 200))
        painter.setBrush(QBrush(accent_grad))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(0, 4, 4, rect.height() - 8, 2, 2)


class NotificationManager(QWidget):
    """Manages notification display - listens on DBus and shows bubbles."""

    def __init__(self):
        super().__init__()
        self._notifications = []  # Active notification bubbles
        self._history = []        # Past notifications (max 50)
        self._dbus_service = None

        # Hidden parent widget for notification management
        self.setVisible(False)

        # Global notification position tracking
        self._next_y = 0
        self._screen_geometry = None

        # Schedule DBus connection (deferred to not block startup)
        QTimer.singleShot(1000, self._init_dbus)

    def _init_dbus(self):
        """Initialize DBus notification listener."""
        try:
            import dbus
            import dbus.service
            from dbus.mainloop.glib import DBusGMainLoop
            from gi.repository import GLib

            # Use GLib main loop for DBus (compatible with Qt)
            DBusGMainLoop(set_as_default=True)

            bus = dbus.SessionBus()
            name = dbus.service.BusName(
                "org.freedesktop.Notifications",
                bus=bus
            )
            self._dbus_service = NotificationDBusService(
                bus, "/org/freedesktop/Notifications",
                self._on_notification
            )
            print("[AIOS NotificationManager] DBus service registered")
        except ImportError:
            print("[AIOS NotificationManager] DBus not available - notification listening disabled")
        except Exception as e:
            print(f"[AIOS NotificationManager] DBus init error: {e}")

    def _on_notification(self, app_name, replaces_id, app_icon, title, body, actions, hints, timeout):
        """Called when a notification is received via DBus."""
        urgency = hints.get("urgency", 1) if hints else 1
        urgency_map = {0: "low", 1: "normal", 2: "critical"}
        urgency_str = urgency_map.get(urgency, "normal")

        self.show_notification(
            app_name=app_name or "System",
            title=title,
            body=body,
            urgency=urgency_str,
            notification_id=replaces_id
        )
        # Return a notification ID
        return 0

    def show_notification(self, app_name="System", title="", body="", urgency="normal", notification_id=None):
        """Display a notification bubble."""
        bubble = NotificationBubble(
            app_name=app_name,
            title=title,
            body=body,
            urgency=urgency,
            notification_id=notification_id
        )
        bubble.dismissed.connect(self._on_bubble_dismissed)
        self._notifications.append(bubble)
        self._history.append({
            "app_name": app_name,
            "title": title,
            "body": body,
            "urgency": urgency,
            "timestamp": datetime.now().isoformat(),
            "id": bubble.notification_id
        })
        # Trim history to 50
        if len(self._history) > 50:
            self._history = self._history[-50:]

        self._position_bubble(bubble)
        bubble.show()

    def _position_bubble(self, bubble):
        """Position the notification bubble in the top-right corner."""
        screen = QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        if not geo:
            bubble.setGeometry(100, 100, bubble.width(), bubble.minimumHeight())
            return

        self._screen_geometry = geo

        # Stack notifications from top-right
        spacing = 12
        x = geo.x() + geo.width() - bubble.width() - spacing

        # Find next available Y position
        y = geo.y() + 48  # Leave room for panel at top
        for existing in self._notifications:
            if existing.isVisible() and existing != bubble:
                y = existing.geometry().y() + existing.height() + spacing

        # Check if it would go off screen
        if y + bubble.height() > geo.y() + geo.height() - 60:
            if self._notifications:
                oldest = self._notifications[0]
                if oldest != bubble:
                    oldest._dismiss()

        bubble.setGeometry(x, y, bubble.width(), bubble.minimumHeight())

        # Slide-in animation
        start_x = geo.x() + geo.width()
        anim = QPropertyAnimation(bubble, b"pos", bubble)
        anim.setDuration(200)
        anim.setStartValue(QRect(start_x, y, bubble.width(), bubble.height()).topLeft())
        anim.setEndValue(QRect(x, y, bubble.width(), bubble.height()).topLeft())
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()

    def _on_bubble_dismissed(self, bubble):
        """Remove dismissed bubble from tracking."""
        if bubble in self._notifications:
            self._notifications.remove(bubble)
        # Reposition remaining bubbles
        self._reposition_all()

    def _reposition_all(self):
        """Reposition all visible notification bubbles."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        spacing = 12
        # Get width from any visible bubble; all bubbles have the same fixed width
        bw = 360
        for b in list(self._notifications):
            if b.isVisible():
                bw = b.width()
                break
        x = geo.x() + geo.width() - bw - spacing

        y = geo.y() + 48

        for bubble in list(self._notifications):
            if bubble.isVisible():
                new_rect = QRect(x, y, bubble.width(), bubble.minimumHeight())
                anim = QPropertyAnimation(bubble, b"geometry", bubble)
                anim.setDuration(150)
                anim.setEndValue(new_rect)
                anim.setEasingCurve(QEasingCurve.OutCubic)
                anim.start()
                y += bubble.minimumHeight() + spacing

    def get_history(self):
        """Return notification history list."""
        return list(self._history)


# Lazy DBus import - only define the service class if dbus is available
_dbus_available = False
NotificationDBusService = None

try:
    import dbus
    import dbus.service
    _dbus_available = True

    class _NotificationDBusService(dbus.service.Object):
        """DBus service implementing org.freedesktop.Notifications."""

        def __init__(self, bus, path, callback):
            super().__init__(bus, path)
            self._callback = callback

        @dbus.service.method(
            "org.freedesktop.Notifications",
            in_signature="susssasa{sv}i",
            out_signature="u"
        )
        def Notify(self, app_name, replaces_id, app_icon, title, body, actions, hints, timeout):
            return self._callback(app_name, replaces_id, app_icon, title, body, actions, hints, timeout)

        @dbus.service.method(
            "org.freedesktop.Notifications",
            in_signature="",
            out_signature="as"
        )
        def GetCapabilities(self):
            return ["body", "actions", "urgency", "icon-static"]

        @dbus.service.method(
            "org.freedesktop.Notifications",
            in_signature="",
            out_signature="ssss"
        )
        def GetServerInformation(self):
            return "AIOS Notification Daemon", "AIOS", "1.0", "1.2"

        @dbus.service.method(
            "org.freedesktop.Notifications",
            in_signature="u",
            out_signature=""
        )
        def CloseNotification(self, notification_id):
            pass

    NotificationDBusService = _NotificationDBusService
except ImportError:
    pass
