"""
AIOS Desktop Panel
Bottom taskbar with clock, system tray, app launcher, and workspace indicators.
Stays above maximized windows using Type DOCK hints.
"""

import subprocess
import os
import psutil
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QFrame, QSystemTrayIcon,
    QMenu, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal, QRect
from PySide6.QtGui import (
    QPainter, QLinearGradient, QBrush, QPen, QColor, QFont, QPixmap, QIcon
)

from gui.theme import AISColors


class ClockWidget(QWidget):
    """Digital clock widget for the panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)

        self.label = QLabel(self)
        self.label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.label.setStyleSheet(f"""
            color: {AISColors.text.name()};
            background: transparent;
            padding: 0 12px;
        """)
        self.label.setAlignment(Qt.AlignCenter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

        # Update clock every second
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_time)
        self._timer.start(1000)
        self._update_time()

    def stop(self):
        """Stop the clock timer."""
        if self._timer and self._timer.isActive():
            self._timer.stop()

    def _update_time(self):
        now = datetime.now()
        self.label.setText(now.strftime("%I:%M %p").lstrip("0") + f"\n{now.strftime('%b %d')}")
        self.setFixedWidth(self.label.sizeHint().width() + 24)


class TrayWidget(QWidget):
    """System tray area - hosts StatusNotifierItems from running apps."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self._icons = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)
        layout.addStretch()

        # Placeholder tray icons for common services
        self._add_tray_indicator("network", "Network")
        self._add_tray_indicator("audio", "Audio")
        self._add_tray_indicator("battery", "Battery")

    def _add_tray_indicator(self, name, tooltip):
        btn = QPushButton(self)
        btn.setFixedSize(24, 24)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #94A3B8;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(124, 58, 237, 0.2);
                color: #A78BFA;
            }
        """)
        symbols = {"network": "🌐", "audio": "🔊", "battery": "🔋"}
        btn.setText(symbols.get(name, "●"))
        self.layout().addWidget(btn)
        self._icons.append(btn)

    def add_icon_widget(self, widget):
        """Add a custom widget as a tray icon."""
        widget.setParent(self)
        self.layout().addWidget(widget)


class MonitorWidget(QWidget):
    """Compact CPU / memory / disk readouts for the system panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)

        self.cpu_label = QLabel(self)
        self.mem_label = QLabel(self)
        self.dsk_label = QLabel(self)

        base = f"color: {AISColors.text_muted.name()}; background: transparent; font-size: 10px; padding: 0 3px;"
        for lbl in (self.cpu_label, self.mem_label, self.dsk_label):
            lbl.setStyleSheet(base)
            lbl.setFont(QFont("Segoe UI", 10))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(2)
        layout.addWidget(self.cpu_label)
        layout.addWidget(self.mem_label)
        layout.addWidget(self.dsk_label)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(2000)
        self._update()

    def stop(self):
        if self._timer and self._timer.isActive():
            self._timer.stop()

    def _update(self):
        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            dsk = psutil.disk_usage("/").percent
            self.cpu_label.setText(f"\U0001f5a5  {cpu:.0f}%")
            self.mem_label.setText(f"\U0001f4be  {mem:.0f}%")
            self.dsk_label.setText(f"\U0001f4c0  {dsk:.0f}%")
        except Exception:
            pass


class SystemPanel(QWidget):
    """Bottom system panel/taskbar with clock, tray, and app launcher."""

    launcher_requested = Signal()
    llm_requested = Signal()
    clock_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AIOS Panel")

        # Window flags only when standalone (no parent); embedded = child widget
        if parent is None:
            flags = (
                Qt.FramelessWindowHint |
                Qt.Window |
                Qt.WindowStaysOnTopHint
            )
            self.setWindowFlags(flags)
            # Window type hints for KWin
            self.setProperty("type", "dock")
            self.setProperty("_KDE_NET_WM_WINDOW_TYPE", "_KDE_NET_WM_WINDOW_TYPE_DOCK")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)

        self.setFixedHeight(44)

        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        # App launcher button (AIOS logo)
        self.launcher_btn = QPushButton("\u2b21", self)
        self.launcher_btn.setFixedSize(36, 36)
        self.launcher_btn.setCursor(Qt.PointingHandCursor)
        self.launcher_btn.setToolTip("App Launcher (Super)")
        self.launcher_btn.clicked.connect(self.launcher_requested.emit)
        self.launcher_btn.setStyleSheet(f"""
            QPushButton {{
                background: {AISColors.primary.name()};
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {AISColors.primary_light.name()};
            }}
            QPushButton:pressed {{
                background: {AISColors.primary_dark.name()};
            }}
        """)
        layout.addWidget(self.launcher_btn)

        self.llm_btn = QPushButton("\U0001f4ac", self)
        self.llm_btn.setFixedSize(36, 36)
        self.llm_btn.setCursor(Qt.PointingHandCursor)
        self.llm_btn.setToolTip("LLM Chat (Super+L)")
        self.llm_btn.clicked.connect(self.llm_requested.emit)
        self.llm_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {AISColors.text_muted.name()};
                border: 1px solid {AISColors.border.name()};
                border-radius: 8px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: {AISColors.surface_light.name()};
                color: {AISColors.primary_light.name()};
                border: 1px solid {AISColors.primary.name()};
            }}
        """)
        layout.addWidget(self.llm_btn)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color: {AISColors.border.name()};")
        sep.setFixedWidth(1)
        layout.addWidget(sep)

        self.monitor = MonitorWidget(self)
        layout.addWidget(self.monitor)

        layout.addStretch(1)

        # Clock
        self.clock = ClockWidget(self)
        layout.addWidget(self.clock)

        # System tray
        self.tray = TrayWidget(self)
        layout.addWidget(self.tray)

    def show_at_bottom(self):
        """Position the panel at the bottom of the screen and show."""
        if self.parent() is not None:
            # When embedded in parent widget, fill parent's bottom
            parent_geo = self.parent().rect()
            self.setGeometry(
                parent_geo.x(),
                parent_geo.y() + parent_geo.height() - self.height(),
                parent_geo.width(),
                self.height()
            )
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                self.setGeometry(
                    geo.x(),
                    geo.y() + geo.height() - self.height(),
                    geo.width(),
                    self.height()
                )
        self.show()

    def paintEvent(self, event):
        """Draw beautiful gradient panel background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dark gradient background
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor("#151530"))
        grad.setColorAt(1.0, QColor("#0F0F23"))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())

        # Top accent line
        line_pen = QPen(AISColors.primary, 1)
        painter.setPen(line_pen)
        painter.drawLine(0, 0, self.width(), 0)

        # Top highlight
        highlight = QLinearGradient(0, 0, self.width(), 0)
        highlight.setColorAt(0.0, QColor(124, 58, 237, 0))
        highlight.setColorAt(0.3, QColor(124, 58, 237, 30))
        highlight.setColorAt(0.7, QColor(6, 182, 212, 20))
        highlight.setColorAt(1.0, QColor(124, 58, 237, 0))
        painter.setBrush(QBrush(highlight))
        painter.drawRect(0, 0, self.width(), 1)
