"""
AIOS App Store
Searchable grid of installed applications.
Replaces scattered desktop icons with an organized store interface.
Opens as a centered overlay from the desktop.
"""

import os
import subprocess
import shlex

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QPushButton, QScrollArea, QGridLayout, QFrame, QApplication,
    QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import (
    QPainter, QColor, QFont, QBrush, QPen, QKeyEvent,
)

from gui.launcher import DesktopApp
from gui.theme import AISColors


class AppCard(QFrame):
    """Single app card in the store grid."""

    clicked = Signal(object)  # DesktopApp

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.setFixedSize(120, 110)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            AppCard {{
                background: {AISColors.surface_light.name()};
                border: 1px solid {AISColors.border.name()};
                border-radius: 8px;
            }}
            AppCard:hover {{
                background: {AISColors.surface_lighter.name()};
                border: 1px solid {AISColors.primary.name()}60;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        # Icon circle with first letter
        icon_label = QLabel(self.app.name[0].upper() if self.app.name else "?")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setFixedSize(48, 48)
        icon_label.setStyleSheet(f"""
            background: {AISColors.primary.name()}40;
            color: {AISColors.primary_light.name()};
            border-radius: 24px;
            font-size: 20px;
            font-weight: bold;
        """)
        layout.addWidget(icon_label, 0, Qt.AlignCenter)

        # App name
        name_label = QLabel(self.app.name[:18])
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(f"color: {AISColors.text.name()}; background: transparent; font-size: 10px;")
        name_label.setWordWrap(True)
        layout.addWidget(name_label, 0, Qt.AlignCenter)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.app)
        super().mousePressEvent(event)


class AppStoreWidget(QWidget):
    """Searchable app store overlay."""

    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._apps = []
        self._filtered = []
        self._load_apps()

        # Not a window — embedded child
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(f"background: {AISColors.overlay.name()};")

        # Main layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignCenter)

        # Store window card
        card = QFrame()
        card.setFixedSize(640, 480)
        card.setStyleSheet(f"""
            QFrame {{
                background: {AISColors.surface.name()};
                border: 1px solid {AISColors.border.name()};
                border-radius: 12px;
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("\U0001f4e6  App Store")
        title.setStyleSheet(f"color: {AISColors.primary_light.name()}; font-size: 16px; font-weight: bold; background: transparent;")
        header_row.addWidget(title)
        header_row.addStretch()

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(28, 28)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {AISColors.text_muted.name()};
                border: none;
                border-radius: 14px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {AISColors.surface_light.name()};
                color: {AISColors.text.name()};
            }}
        """)
        close_btn.clicked.connect(self.dismiss)
        header_row.addWidget(close_btn)
        card_layout.addLayout(header_row)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search apps...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: {AISColors.surface_light.name()};
                color: {AISColors.text.name()};
                border: 1px solid {AISColors.border.name()};
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border: 1px solid {AISColors.primary.name()};
            }}
        """)
        self.search_input.textChanged.connect(self._filter)
        card_layout.addWidget(self.search_input)

        # Scrollable grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {AISColors.surface.name()};
                width: 8px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {AISColors.border.name()};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)

        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(4, 4, 4, 4)
        self.grid_layout.setSpacing(6)
        scroll.setWidget(self.grid_container)

        card_layout.addWidget(scroll, 1)

        # Footer with app count
        self.count_label = QLabel(f"{len(self._apps)} apps installed")
        self.count_label.setStyleSheet(f"color: {AISColors.text_muted.name()}; font-size: 11px; background: transparent;")
        card_layout.addWidget(self.count_label)

        outer.addWidget(card)

        # Populate initially
        self._filter("")

    def _load_apps(self):
        """Load apps from XDG desktop files."""
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

        for p in paths:
            app = DesktopApp(p)
            if app.is_valid():
                self._apps.append(app)

        self._apps.sort(key=lambda a: a.name.lower())

    def _filter(self, text):
        """Filter apps by search text."""
        query = text.lower().strip()
        if query:
            self._filtered = [
                a for a in self._apps
                if query in a.name.lower() or query in a.comment.lower()
            ]
        else:
            self._filtered = list(self._apps)

        self._rebuild_grid()

    def _rebuild_grid(self):
        """Rebuild the grid from filtered apps."""
        # Clear existing
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        cols = 4
        for i, app in enumerate(self._filtered):
            card = AppCard(app)
            card.clicked.connect(self._launch_app)
            self.grid_layout.addWidget(card, i // cols, i % cols)

        # Update count
        self.count_label.setText(
            f"Showing {len(self._filtered)} of {len(self._apps)} apps"
        )

    def _launch_app(self, app):
        """Launch an app from the store."""
        app.launch()
        self.dismiss()

    def dismiss(self):
        """Dismiss the store overlay."""
        self.hide()
        self.dismissed.emit()

    def show_store(self):
        """Show as centered overlay."""
        if self.parent():
            parent_geo = self.parent().rect()
            self.setGeometry(parent_geo)
        self.show()
        self.raise_()
        self.search_input.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.dismiss()
        super().keyPressEvent(event)
