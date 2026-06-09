"""
AIOS Desktop Background Window
Fullscreen wallpaper window that sits below all application windows.
Supports solid colors, gradients, and image wallpapers.
"""

import os
import random

from PySide6.QtWidgets import QWidget, QApplication
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QPainter, QLinearGradient, QBrush, QPen, QPixmap, QColor, QFont
)

from gui.theme import AISColors


class DesktopBackground(QWidget):
    """Fullscreen desktop background window behind all applications."""

    # Signal emitted when user right-clicks on desktop
    desktop_context_menu = Signal(object)  # QPoint

    def __init__(self, wallpaper_path=None, parent=None):
        super().__init__(parent)
        self._wallpaper_pixmap = None
        self._wallpaper_path = wallpaper_path
        self._gradient_mode = wallpaper_path is None
        self._gradient_offset = 0.0
        self._anim_timer = None

        # Window flags only when standalone (no parent); embedded = child widget
        if parent is None:
            flags = (
                Qt.FramelessWindowHint |
                Qt.Window |
                Qt.WindowStaysOnBottomHint
            )
            self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_StyledBackground)

        # Set window role hints for KWin to recognize as desktop (standalone only)
        if parent is None:
            self.setProperty("type", "desktop")
            self.setProperty("_KDE_NET_WM_WINDOW_TYPE", "_KDE_NET_WM_WINDOW_TYPE_DESKTOP")
            self.setWindowTitle("AIOS Desktop")
            # Ensure it's truly the bottom layer
            self.lower()

        # Load wallpaper if specified
        if wallpaper_path and os.path.isfile(wallpaper_path):
            self.set_wallpaper(wallpaper_path)

        # Track screen geometry
        self._screen_geometry = None

        # Subtle gradient animation timer (only if no image wallpaper)
        if self._gradient_mode:
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._animate_gradient)
            self._anim_timer.start(50)  # 20fps gradient shift

    def set_wallpaper(self, path):
        """Load and set wallpaper image."""
        if os.path.isfile(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self._wallpaper_pixmap = pixmap
                self._wallpaper_path = path
                self._gradient_mode = False
                if self._anim_timer:
                    self._anim_timer.stop()
                self.update()

    def stop_animation(self):
        """Stop the gradient animation timer."""
        if self._anim_timer and self._anim_timer.isActive():
            self._anim_timer.stop()

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
        """Subtly shift gradient colors for a living wallpaper feel."""
        self._gradient_offset += 0.002
        if self._gradient_offset > 1.0:
            self._gradient_offset = 0.0
        self.update()

    def show_fullscreen(self):
        """Show the desktop background in fullscreen mode."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self.setGeometry(geo)
        # Only set fullscreen state when standalone (parented widgets fill parent)
        if self.parent() is None:
            self.setWindowState(Qt.WindowFullScreen)
        self.show()
        if self.parent() is not None:
            self.lower()

    def paintEvent(self, event):
        """Render the desktop background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()

        if self._wallpaper_pixmap and not self._wallpaper_pixmap.isNull():
            # Draw image wallpaper, scaled to fill
            scaled = self._wallpaper_pixmap.scaled(
                rect.size(),
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
            # Center the image
            x = (rect.width() - scaled.width()) // 2
            y = (rect.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Draw animated gradient wallpaper
            self._draw_gradient(painter, rect)

    def _draw_gradient(self, painter, rect):
        """Draw a beautiful animated gradient wallpaper."""
        # Base colors - deep purple to midnight blue with subtle shift
        offset = self._gradient_offset

        grad = QLinearGradient(0, 0, rect.width(), rect.height())
        grad.setColorAt(0.0, QColor(
            13, 13, 26,  # #0D0D1A
        ))
        grad.setColorAt(0.3 + offset * 0.1, QColor(
            20, 15, 40,  # #140F28
        ))
        grad.setColorAt(0.6 + offset * 0.05, QColor(
            26, 18, 50,  # #1A1232
        ))
        grad.setColorAt(1.0, QColor(
            10, 10, 22,  # #0A0A16
        ))

        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRect(rect)

        # Subtle accent glow in corners
        self._draw_corner_glow(painter, rect, offset)

        # AIOS watermark
        self._draw_watermark(painter, rect)

    def _draw_corner_glow(self, painter, rect, offset):
        """Draw subtle purple/cyan glow in corners for atmosphere."""
        # Top-left glow
        glow = QLinearGradient(0, 0, rect.width() * 0.3, rect.height() * 0.3)
        glow.setColorAt(0.0, QColor(124, 58, 237, 30))  # Purple glow
        glow.setColorAt(1.0, QColor(124, 58, 237, 0))
        painter.setBrush(QBrush(glow))
        painter.drawRect(0, 0, rect.width() // 3, rect.height() // 3)

        # Bottom-right cyan glow
        glow2 = QLinearGradient(
            rect.width(), rect.height(),
            rect.width() * 0.7, rect.height() * 0.7
        )
        glow2.setColorAt(0.0, QColor(6, 182, 212, 25))
        glow2.setColorAt(1.0, QColor(6, 182, 212, 0))
        painter.setBrush(QBrush(glow2))
        painter.drawRect(
            rect.width() * 2 // 3, rect.height() * 2 // 3,
            rect.width() // 3, rect.height() // 3
        )

    def _draw_watermark(self, painter, rect):
        """Draw subtle AIOS watermark at bottom-right."""
        painter.setPen(QColor(124, 58, 237, 40))  # Very subtle purple
        font = QFont("Segoe UI", 11)
        painter.setFont(font)
        painter.drawText(
            rect.width() - 120, rect.height() - 30,
            100, 20,
            Qt.AlignRight | Qt.AlignVCenter,
            "⬡ AIOS"
        )

    def contextMenuEvent(self, event):
        """Emit signal for right-click context menu."""
        self.desktop_context_menu.emit(event.globalPos())
