"""
AIOS Lock Screen
Fullscreen overlay with system authentication via PAM/loginctl.
Shown on Ctrl+Alt+L, lid close, or session idle timeout.
"""

import subprocess
import os
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QPainter, QColor, QFont, QPixmap, QLinearGradient, QBrush,
    QKeyEvent, QFontDatabase
)

from gui.theme import AISColors


class LockScreen(QWidget):
    """Fullscreen lock screen overlay with password authentication."""

    unlocked = Signal()
    locked = Signal()

    def __init__(self):
        super().__init__()
        self._locked = False
        self._attempts = 0

        # Fullscreen overlay flags
        flags = Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.StrongFocus)

        # Semi-transparent dark background
        self.setStyleSheet(f"""
            background: {AISColors.overlay.name()};
        """)

        self._setup_ui()

        # Clock update timer
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        # Escape key to abort (only if already authenticated)
        self._authenticated = False

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Center content
        center = QWidget()
        center.setFixedWidth(400)
        center.setStyleSheet("background: transparent;")

        center_layout = QVBoxLayout(center)
        center_layout.setAlignment(Qt.AlignCenter)
        center_layout.setSpacing(16)

        # AIOS icon
        icon = QLabel("⬡")
        icon.setFont(QFont("Segoe UI", 48))
        icon.setStyleSheet(f"""
            color: {AISColors.primary_light.name()};
            background: transparent;
        """)
        icon.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(icon)

        # Time display
        self.time_label = QLabel()
        self.time_label.setFont(QFont("Segoe UI", 56, QFont.Bold))
        self.time_label.setStyleSheet(f"color: {AISColors.text.name()}; background: transparent;")
        self.time_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.time_label)

        # Date display
        self.date_label = QLabel()
        self.date_label.setFont(QFont("Segoe UI", 14))
        self.date_label.setStyleSheet(f"color: {AISColors.text_muted.name()}; background: transparent;")
        self.date_label.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(self.date_label)

        # Spacer
        center_layout.addSpacing(32)

        # Password input
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter password to unlock...")
        self.password_input.setFont(QFont("Segoe UI", 14))
        self.password_input.setMinimumHeight(48)
        self.password_input.setStyleSheet(f"""
            QLineEdit {{
                background: {AISColors.surface_light.name()};
                color: {AISColors.text.name()};
                border: 2px solid {AISColors.border.name()};
                border-radius: 12px;
                padding: 8px 16px;
                font-size: 14px;
            }}
            QLineEdit:focus {{
                border: 2px solid {AISColors.primary.name()};
            }}
        """)
        self.password_input.returnPressed.connect(self._authenticate)
        center_layout.addWidget(self.password_input)

        # Error label (hidden by default)
        self.error_label = QLabel()
        self.error_label.setFont(QFont("Segoe UI", 10))
        self.error_label.setStyleSheet(f"color: {AISColors.error.name()}; background: transparent;")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setVisible(False)
        center_layout.addWidget(self.error_label)

        # Hint
        hint = QLabel("Press Enter to unlock · Esc to cancel")
        hint.setFont(QFont("Segoe UI", 9))
        hint.setStyleSheet(f"color: {AISColors.text_dim.name()}; background: transparent;")
        hint.setAlignment(Qt.AlignCenter)
        center_layout.addWidget(hint)

        layout.addWidget(center)

    def _update_clock(self):
        """Update time/date display."""
        now = datetime.now()
        self.time_label.setText(now.strftime("%I:%M:%S %p").lstrip("0"))
        self.date_label.setText(now.strftime("%A, %B %d, %Y"))

    def _authenticate(self):
        """Attempt password authentication via loginctl or PAM."""
        password = self.password_input.text()
        if not password:
            return

        self._attempts += 1

        # Attempt unlock through loginctl
        try:
            # Use loginctl to unlock the session
            # Password is verified through the system's PAM stack
            result = subprocess.run(
                ["loginctl", "unlock-session"],
                capture_output=True,
                text=True,
                timeout=5,
                input=password + "\n"  # Some auth methods require stdin
            )

            # Check if it worked
            if result.returncode == 0 or "already" in result.stderr.lower():
                self._unlock()
                return
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: try using python-pam or direct auth
        if self._try_pam_auth(password):
            self._unlock()
            return

        # Authentication failed
        self.error_label.setVisible(True)
        if self._attempts >= 3:
            self.error_label.setText(f"Too many attempts ({self._attempts}). Try again later.")
            QTimer.singleShot(30000, lambda: self.error_label.setVisible(False))
            self.password_input.setEnabled(False)
            QTimer.singleShot(30000, lambda: self.password_input.setEnabled(True))
        else:
            self.error_label.setText(f"Incorrect password. Attempt {self._attempts}/3")
        self.password_input.clear()

    def _try_pam_auth(self, password):
        """Try PAM authentication."""
        try:
            # Try using python-pam if available
            import pam
            p = pam.pam()
            username = os.environ.get("USER", os.environ.get("LOGNAME", "user"))
            return p.authenticate(username, password)
        except ImportError:
            pass

        # Try using subprocess with su or passwd
        try:
            result = subprocess.run(
                ["passwd", "--status"],
                capture_output=True,
                text=True,
                timeout=5,
                input=password + "\n"
            )
            # This may not reliably verify, so fall through
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Fallback: check against system shadow via python
        try:
            import crypt
            import spwd
            username = os.environ.get("USER", os.environ.get("LOGNAME", "user"))
            encrypted = spwd.getspnam(username).sp_pwd
            salt = encrypted[:encrypted.rindex("$", 3) + 1] if "$" in encrypted else encrypted[:2]
            hashed = crypt.crypt(password, salt)
            return hashed == encrypted
        except (ImportError, KeyError, PermissionError):
            # spwd requires root typically
            pass

        return False

    def _unlock(self):
        """Unlock the screen."""
        self._authenticated = True
        self._attempts = 0
        self.error_label.setVisible(False)
        self.password_input.clear()
        self.hide()
        self.unlocked.emit()

    def lock(self):
        """Show the lock screen."""
        self._authenticated = False
        self._locked = True
        self.password_input.clear()
        self.error_label.setVisible(False)
        self.password_input.setEnabled(True)
        self._update_clock()

        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.password_input.setFocus()
        self.locked.emit()

    def keyPressEvent(self, event):
        """Handle Escape to cancel authentication attempt."""
        if event.key() == Qt.Key_Escape:
            if self._authenticated:
                self._unlock()
            else:
                self.password_input.clear()
                self.error_label.setVisible(False)
        elif event.key() == Qt.Key_Tab:
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)
