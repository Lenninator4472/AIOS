"""
Desktop icons — replaced by AppStoreWidget.
This module kept for backward compatibility; all new code should use AppStoreWidget.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt


class DesktopIconWidget(QWidget):
    """Legacy stub — DesktopIconWidget is no longer used.
    Use gui.app_store.AppStoreWidget instead."""

    def __init__(self):
        super().__init__()
        self._apps = []

    def _app_at_pos(self, pos):
        return None, 0, 0

    def show_fullscreen(self):
        self.hide()
