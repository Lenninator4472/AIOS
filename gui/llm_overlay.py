from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QApplication
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from gui.llm_panel import LLMPanel
from gui.theme import AISColors


class LLMOverlay(QWidget):
    """Semi-transparent fullscreen overlay with embedded LLM chat panel."""

    dismissed = Signal()

    def __init__(self, bus, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(f"background: {AISColors.overlay.name()};")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        card = QWidget()
        card.setFixedSize(700, 500)
        card.setStyleSheet(f"""
            background: {AISColors.surface.name()};
            border-radius: 12px;
            border: 1px solid {AISColors.border.name()};
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        header = QLabel("  \u25cb  LLM Chat")
        header.setFont(QFont("Segoe UI", 14, QFont.Bold))
        header.setStyleSheet(
            f"color: {AISColors.primary_light.name()};"
            f"padding: 12px 16px;"
            f"background: transparent;"
        )
        card_layout.addWidget(header)

        self.llm_panel = LLMPanel(bus)
        card_layout.addWidget(self.llm_panel)

        layout.addWidget(card)

    def show_overlay(self):
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        self.llm_panel.input.setFocus()

    def hide_overlay(self):
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide_overlay()
            self.dismissed.emit()
        super().keyPressEvent(event)
