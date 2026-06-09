"""
AIOS App Launcher
Fullscreen overlay with application search and launch.
Reads .desktop files from standard XDG directories.
"""

import os
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QFrame, QScrollArea,
    QGridLayout, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QPainter, QColor, QFont, QIcon, QPixmap, QKeyEvent,
    QLinearGradient, QBrush
)

from gui.theme import AISColors


class DesktopApp:
    """Represents a parsed .desktop file entry."""

    def __init__(self, path):
        self.path = path
        self.name = ""
        self.exec = ""
        self.icon = ""
        self.comment = ""
        self.categories = ""
        self.no_display = False
        self.terminal = False
        self._parse()

    def _parse(self):
        """Parse a .desktop file."""
        try:
            with open(self.path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("Name="):
                        self.name = line[5:]
                    elif line.startswith("Exec="):
                        self.exec = line[5:]
                    elif line.startswith("Icon="):
                        self.icon = line[5:]
                    elif line.startswith("Comment="):
                        self.comment = line[5:]
                    elif line.startswith("Categories="):
                        self.categories = line[11:]
                    elif line.startswith("NoDisplay="):
                        self.no_display = line[10:].strip().lower() == "true"
                    elif line.startswith("Terminal="):
                        self.terminal = line[9:].strip().lower() == "true"
        except (OSError, UnicodeDecodeError):
            pass

    def is_valid(self):
        """Check if this is a valid, visible app."""
        return bool(self.name) and bool(self.exec) and not self.no_display

    def launch(self):
        """Launch the application."""
        import shlex
        cmd = self.exec
        # Handle .desktop Exec field placeholders
        cmd = cmd.replace("%u", "").replace("%U", "")
        cmd = cmd.replace("%f", "").replace("%F", "")
        cmd = cmd.replace("%i", "").replace("%c", self.name)
        cmd = cmd.replace("%k", self.path)
        parts = shlex.split(cmd)
        if parts:
            try:
                subprocess.Popen(parts)
            except FileNotFoundError:
                pass


class AppLauncher(QWidget):
    """Fullscreen app launcher overlay shown on Super key press."""

    dismissed = Signal()

    def __init__(self):
        super().__init__()
        self._apps = []
        self._filtered = []
        self._selected_index = 0

        # Fullscreen overlay flags
        flags = Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.setStyleSheet(f"""
            background: {AISColors.overlay.name()};
        """)

        # Load apps
        self._load_apps()

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        # Center container
        container = QWidget()
        container.setFixedWidth(640)
        container.setStyleSheet(f"""
            background: {AISColors.surface.name()};
            border-radius: 16px;
            border: 1px solid {AISColors.border.name()};
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(24, 24, 24, 24)
        container_layout.setSpacing(16)

        # Header
        header = QLabel("⬡  App Launcher")
        header.setFont(QFont("Segoe UI", 16, QFont.Bold))
        header.setStyleSheet(f"color: {AISColors.primary_light.name()}; background: transparent;")
        container_layout.addWidget(header)

        # Search bar
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search applications...")
        self.search.setFont(QFont("Segoe UI", 14))
        self.search.setMinimumHeight(44)
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: {AISColors.surface_light.name()};
                color: {AISColors.text.name()};
                border: 2px solid {AISColors.border.name()};
                border-radius: 10px;
                padding: 8px 16px;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 2px solid {AISColors.primary.name()};
            }}
        """)
        self.search.textChanged.connect(self._filter_apps)
        self.search.returnPressed.connect(self._launch_selected)
        container_layout.addWidget(self.search)

        # App list
        self.list_widget = QListWidget()
        self.list_widget.setFont(QFont("Segoe UI", 12))
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                border-radius: 8px;
                color: {AISColors.text.name()};
            }}
            QListWidget::item:selected {{
                background: {AISColors.primary.name()}30;
                color: {AISColors.primary_light.name()};
            }}
            QListWidget::item:hover {{
                background: {AISColors.surface_light.name()};
            }}
        """)

        # Populate apps
        self._populate_list()

        # Keyboard navigation
        self.list_widget.itemActivated.connect(self._on_item_activated)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)

        container_layout.addWidget(self.list_widget, 1)

        # Footer hint
        footer = QLabel("↑↓ Navigate · Enter Launch · Esc Close")
        footer.setFont(QFont("Segoe UI", 9))
        footer.setStyleSheet(f"color: {AISColors.text_muted.name()}; background: transparent;")
        footer.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(footer)

        layout.addWidget(container)

    def _load_apps(self):
        """Scan XDG data directories for .desktop files."""
        paths = set()
        data_dirs = os.environ.get(
            "XDG_DATA_DIRS",
            "/usr/share:/usr/local/share"
        ).split(":")
        data_dirs.append(os.path.expanduser("~/.local/share/applications"))

        for d in data_dirs:
            apps_dir = os.path.join(d, "applications")
            if os.path.isdir(apps_dir):
                for f in os.listdir(apps_dir):
                    if f.endswith(".desktop"):
                        paths.add(os.path.join(apps_dir, f))

        self._apps = []
        for p in paths:
            app = DesktopApp(p)
            if app.is_valid():
                self._apps.append(app)

        # Sort by name
        self._apps.sort(key=lambda a: a.name.lower())
        self._filtered = list(self._apps)

    def _populate_list(self, apps=None):
        """Populate the list widget with apps."""
        self.list_widget.clear()
        apps = apps if apps is not None else self._filtered
        for app in apps:
            item = QListWidgetItem()
            icon_char = "⬡"
            if "browser" in app.categories.lower() or "web" in app.categories.lower():
                icon_char = "🌐"
            elif "game" in app.categories.lower():
                icon_char = "🎮"
            elif "development" in app.categories.lower() or "ide" in app.categories.lower():
                icon_char = "💻"
            elif "office" in app.categories.lower():
                icon_char = "📄"
            elif "media" in app.categories.lower() or "audio" in app.categories.lower() or "video" in app.categories.lower():
                icon_char = "🎵"
            elif "system" in app.categories.lower() or "utility" in app.categories.lower():
                icon_char = "⚙"
            elif "graphics" in app.categories.lower():
                icon_char = "🎨"
            elif "network" in app.categories.lower() or "chat" in app.categories.lower() or "communication" in app.categories.lower():
                icon_char = "💬"
            display = f"{icon_char}  {app.name}"
            if app.comment:
                display += f"\n  {app.comment}"
            item.setText(display)
            item.setData(Qt.UserRole, app)
            self.list_widget.addItem(item)

    def _filter_apps(self, text):
        """Filter apps by search text."""
        text = text.lower().strip()
        if not text:
            self._filtered = list(self._apps)
        else:
            self._filtered = [
                app for app in self._apps
                if text in app.name.lower()
                or text in app.categories.lower()
                or (app.comment and text in app.comment.lower())
            ]
        self._populate_list(self._filtered)

        # Auto-select first
        if self._filtered and self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _launch_selected(self):
        """Launch the currently selected app."""
        item = self.list_widget.currentItem()
        if item:
            app = item.data(Qt.UserRole)
            if app:
                app.launch()
                self._dismiss()

    def _on_item_activated(self, item):
        """Handle double-click / Enter on item."""
        app = item.data(Qt.UserRole)
        if app:
            app.launch()
            self._dismiss()

    def _on_row_changed(self, row):
        """Track selection for keyboard navigation."""
        self._selected_index = row

    def _dismiss(self):
        """Hide the launcher."""
        self.hide()
        self.dismissed.emit()

    def show_launcher(self):
        """Show the launcher with focus on search bar."""
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        self.search.clear()
        self._filter_apps("")
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def keyPressEvent(self, event):
        """Handle Escape to dismiss."""
        if event.key() == Qt.Key_Escape:
            self._dismiss()
        elif event.key() == Qt.Key_Down:
            # Move selection down
            row = self.list_widget.currentRow()
            if row < self.list_widget.count() - 1:
                self.list_widget.setCurrentRow(row + 1)
        elif event.key() == Qt.Key_Up:
            row = self.list_widget.currentRow()
            if row > 0:
                self.list_widget.setCurrentRow(row - 1)
        else:
            super().keyPressEvent(event)
