"""
AIOS - AI Native Operating System
Beautiful native GUI with frameless window, custom chrome, and LLM integration.
"""

import sys
import os

# Ensure project root is on Python path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSplitter, QFrame, QGraphicsDropShadowEffect,
    QSizePolicy, QScrollArea, QTextEdit, QLineEdit, QListWidget,
    QListWidgetItem
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, Signal
from PySide6.QtGui import QFont, QPixmap, QColor, QPainter, QLinearGradient, QBrush, QPen

from gui.theme import AISColors, AITheme, AnimationFactory
from gui.window_manager import BeautifulWindow, TitleBar
from gui.terminal import Terminal
from gui.monitor import SystemMonitor
from gui.llm_panel import LLMPanel
from gui.app_launcher import AppLauncher

from kernel.bus import EventBus
from gui.integration import KernelBridge


class ModernButton(QPushButton):
    """Beautiful modern button with gradient and hover effects."""
    
    def __init__(self, text, icon="", primary=True, parent=None):
        super().__init__(text, parent)
        self._primary = primary
        self._hovered = False
        
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)
        self.setFont(QFont("Segoe UI", 10))
        
        bg = AISColors.primary if primary else "transparent"
        bg_hover = AISColors.primary_light if primary else AISColors.surface_light
        txt_color = AISColors.text_on_primary if primary else AISColors.text
        border = "none" if primary else f"1px solid {AISColors.border.name()}"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg.name() if primary else 'transparent'};
                color: {txt_color.name()};
                border: {border};
                border-radius: 8px;
                padding: 8px 20px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {bg_hover.name() if primary else AISColors.surface_light.name()};
                border: {border if not primary else 'none'};
            }}
            QPushButton:pressed {{
                background: {AISColors.primary_dark.name() if primary else AISColors.surface_lighter.name()};
            }}
        """)


class Sidebar(QWidget):
    """Beautiful sidebar with app navigation."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        self.setStyleSheet(f"""
            QWidget {{
                background-color: #0F0F23;
                border-right: 1px solid {AISColors.border.name()};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        
        # AIOS branding
        brand = QLabel("  ⬡  AIOS")
        brand.setFont(QFont("Segoe UI", 14, QFont.Bold))
        brand.setStyleSheet(f"color: {AISColors.primary_light.name()}; padding: 12px 8px; background: transparent;")
        layout.addWidget(brand)
        
        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {AISColors.border.name()}; max-height: 1px;")
        layout.addWidget(sep)
        
        # Nav items
        self._add_nav_item(layout, "⬡  Terminal", True)
        self._add_nav_item(layout, "◉  LLM Chat", False)
        self._add_nav_item(layout, "◈  Monitor", False)
        self._add_nav_item(layout, "▤  Apps", False)
        
        layout.addStretch()
        
        # Status indicator
        status = QLabel("●  System Ready")
        status.setFont(QFont("Segoe UI", 9))
        status.setStyleSheet(f"color: {AISColors.success.name()}; padding: 8px; background: transparent;")
        layout.addWidget(status)
    
    def _add_nav_item(self, layout, text, active=False):
        btn = QPushButton(text)
        btn.setFont(QFont("Segoe UI", 10))
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(36)
        
        if active:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {AISColors.primary.name()}20;
                    color: {AISColors.primary_light.name()};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 12px;
                    text-align: left;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {AISColors.primary.name()}30;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {AISColors.text_muted.name()};
                    border: none;
                    border-radius: 6px;
                    padding: 8px 12px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background: {AISColors.surface_light.name()};
                    color: {AISColors.text.name()};
                }}
            """)
        
        layout.addWidget(btn)


class AIShell(QWidget):
    """The main AIOS shell — frameless, beautiful, AI-native."""
    
    def __init__(self):
        super().__init__()
        
        # Frameless (handles both X11 and Wayland)
        flags = Qt.FramelessWindowHint | Qt.Window
        self.setWindowFlags(flags)
        self.setMinimumSize(900, 600)
        self.setAttribute(Qt.WA_StyledBackground)
        
        # Event bus
        self.bus = EventBus()
        self.kernel_bridge = None
        
        # Maximize state
        self._maximized = False
        self._saved_geometry = None
        
        # Explicit background (required for Wayland)
        self.setStyleSheet(f"background-color: {AISColors.background.name()};")
        
        self._setup_ui()
        
        # Lazy-load kernel
        QTimer.singleShot(200, self._init_kernel)
    
    def _setup_ui(self):
        """Build the entire UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Title bar
        self.title_bar = TitleBar("AIOS - AI Native OS", self)
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.maximize_clicked.connect(self._toggle_maximize)
        self.title_bar.close_clicked.connect(self.close)
        main_layout.addWidget(self.title_bar)
        
        # Content body with sidebar
        body = QWidget()
        body.setStyleSheet(f"background: {AISColors.background.name()};")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = Sidebar()
        body_layout.addWidget(self.sidebar)
        
        # Main content area
        content = QWidget()
        content.setStyleSheet(f"background: {AISColors.background.name()};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(8)
        
        # Header
        header = QLabel("AIOS Terminal")
        header.setFont(QFont("Segoe UI", 18, QFont.Bold))
        header.setStyleSheet(f"color: {AISColors.text.name()}; background: transparent;")
        content_layout.addWidget(header)
        
        # Terminal area
        self.terminal = Terminal(self.bus)
        self.terminal.setMinimumHeight(200)
        content_layout.addWidget(self.terminal, 2)
        
        # Quick action bar
        actions = QHBoxLayout()
        actions.setSpacing(8)
        
        self.llm_btn = ModernButton("💬  LLM Chat", primary=True)
        actions.addWidget(self.llm_btn)
        
        self.monitor_btn = ModernButton("📊  Monitor", primary=False)
        actions.addWidget(self.monitor_btn)
        
        self.apps_btn = ModernButton("📦  Apps", primary=False)
        actions.addWidget(self.apps_btn)
        
        actions.addStretch()
        content_layout.addLayout(actions)
        
        body_layout.addWidget(content, 1)
        main_layout.addWidget(body, 1)
        
        # Connect signals
        self.llm_btn.clicked.connect(self._open_llm_panel)
        self.monitor_btn.clicked.connect(self._open_monitor)
        self.apps_btn.clicked.connect(self._open_app_launcher)
    
    def _init_kernel(self):
        """Initialize kernel bridge lazily."""
        try:
            self.kernel_bridge = KernelBridge(self.bus)
            print("Kernel bridge initialized")
        except Exception as e:
            print(f"Kernel bridge init error: {e}")
    
    def _open_llm_panel(self):
        window = BeautifulWindow("AIOS - LLM Chat", 150, 150, 600, 400)
        panel = LLMPanel(self.bus)
        window.set_content_widget(panel)
        window.show()
    
    def _open_monitor(self):
        window = BeautifulWindow("AIOS - System Monitor", 200, 200, 500, 400)
        monitor = SystemMonitor(self.bus)
        window.set_content_widget(monitor)
        window.show()
    
    def _open_app_launcher(self):
        window = BeautifulWindow("AIOS - App Launcher", 250, 250, 600, 450)
        launcher = AppLauncher(self.bus)
        window.set_content_widget(launcher)
        window.show()
    
    def _toggle_maximize(self):
        if self._maximized:
            if self._saved_geometry:
                self.setGeometry(self._saved_geometry)
            self._maximized = False
        else:
            self._saved_geometry = self.geometry()
            screen = self.screen()
            if screen:
                self.setGeometry(screen.availableGeometry())
            self._maximized = True
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(AISColors.background))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 14, 14)


def run_desktop_mode(app):
    """Run AIOS in full desktop mode (replaces KDE Plasma shell)."""
    print("⬡ AIOS Desktop Mode - Full Desktop Environment")
    from gui.desktop_shell import DesktopShell
    from kernel.bus import EventBus

    bus = EventBus()

    try:
        from gui.integration import KernelBridge
        bridge = KernelBridge(bus)
        print("[AIOS] Kernel bridge initialized")
    except Exception as e:
        print(f"[AIOS] Kernel bridge init error: {e}")

    shell = DesktopShell(bus=bus)
    shell.start()

    return app, shell


def main():
    app = QApplication(sys.argv)

    # Check for desktop mode flag
    if "--desktop" in sys.argv or os.environ.get("AIOS_DESKTOP") == "1":
        app, shell = run_desktop_mode(app)
    else:
        # Standard standalone window mode
        AITheme.apply(app)
        shell = AIShell()
        shell.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
