"""
AIOS Beautiful Window Manager
Frameless windows with stunning custom title bars, smooth animations, and drag support.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QFrame, QSizeGrip, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, QTimer, QRect, Signal
from PySide6.QtGui import QPainter, QPen, QColor, QLinearGradient, QBrush, QFont, QPixmap, QIcon

from gui.theme import AISColors, AnimationFactory


class TitleBarButton(QPushButton):
    """Beautiful title bar button with hover effects."""
    
    def __init__(self, icon_text, color, hover_color, parent=None):
        super().__init__(parent)
        self.icon_text = icon_text
        self.default_color = color
        self.hover_color = hover_color
        self._is_hovered = False
        
        self.setFixedSize(36, 36)
        self.setCursor(Qt.PointingHandCursor)
        
        # Style
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {color.name()};
                border: none;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {hover_color.name()};
                color: white;
            }}
        """)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Hover background
        if self._is_hovered:
            painter.setBrush(QBrush(self.hover_color))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(self.rect(), 8, 8)
        
        # Icon text
        painter.setPen(QColor(self.default_color) if not self._is_hovered else Qt.white)
        font = QFont("Segoe UI", 12, QFont.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, self.icon_text)
    
    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)


class TitleBar(QWidget):
    """Custom title bar with drag, min/max/close, and beautiful gradient."""
    
    # Signals
    minimize_clicked = Signal()
    maximize_clicked = Signal()
    close_clicked = Signal()
    
    def __init__(self, title="AIOS", parent=None):
        super().__init__(parent)
        self.title = title
        self._start_pos = None
        self._is_maximized = False
        self._is_double_click = False
        
        self.setFixedHeight(44)
        self.setMouseTracking(True)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(4)
        
        # App icon (using unicode symbol)
        icon_label = QLabel("⬡")
        icon_label.setFont(QFont("Segoe UI", 16))
        icon_label.setStyleSheet(f"color: {AISColors.primary_light.name()}; background: transparent;")
        icon_label.setFixedSize(24, 44)
        layout.addWidget(icon_label)
        
        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        self.title_label.setStyleSheet(f"color: {AISColors.title_bar_text.name()}; background: transparent;")
        layout.addWidget(self.title_label)
        
        layout.addStretch()
        
        # Window control buttons
        self.min_btn = TitleBarButton("─", AISColors.warning, QColor("#D97706"))
        self.min_btn.clicked.connect(self.minimize_clicked.emit)
        layout.addWidget(self.min_btn)
        
        self.max_btn = TitleBarButton("□", AISColors.success, QColor("#059669"))
        self.max_btn.clicked.connect(self._on_maximize)
        layout.addWidget(self.max_btn)
        
        self.close_btn = TitleBarButton("✕", AISColors.error, QColor("#DC2626"))
        self.close_btn.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.close_btn)
    
    def _on_maximize(self):
        self._is_maximized = not self._is_maximized
        self.max_btn.icon_text = "❐" if self._is_maximized else "□"
        self.max_btn.update()
        self.maximize_clicked.emit()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_pos = event.globalPos()
            self._is_double_click = event.type() == Qt.MouseButtonDblClick
            if not self._is_double_click:
                self.parent().windowHandle().startSystemMove()
    
    def mouseDoubleClickEvent(self, event):
        self._on_maximize()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw gradient background
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0.0, QColor("#0F0F23"))
        grad.setColorAt(0.5, QColor("#151530"))
        grad.setColorAt(1.0, QColor("#0F0F23"))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())
        
        # Bottom accent line
        line_pen = QPen(AISColors.primary, 1)
        painter.setPen(line_pen)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class BeautifulWindow(QWidget):
    """A beautiful, frameless window with custom chrome and animations."""
    
    def __init__(self, title="AIOS Window", x=100, y=100, width=700, height=500):
        super().__init__()
        
        # Frameless window
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.Window
        )
        self.setGeometry(x, y, width, height)
        self.setAttribute(Qt.WA_StyledBackground)
        
        # Main layout
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)
        
        # Title bar
        self.title_bar = TitleBar(title, self)
        self.title_bar.minimize_clicked.connect(self.showMinimized)
        self.title_bar.maximize_clicked.connect(self._toggle_maximize)
        self.title_bar.close_clicked.connect(self.close)
        self._main_layout.addWidget(self.title_bar)
        
        # Content area (with drop shadow effect)
        self.content = QWidget()
        self.content.setStyleSheet(f"""
            QWidget {{
                background-color: {AISColors.surface.name()};
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }}
        """)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(16, 16, 16, 16)
        self._main_layout.addWidget(self.content, 1)
        
        # Drop shadow
        self._add_shadow()
        
        # Track maximize state
        self._maximized = False
        self._saved_geometry = None
    
    def _add_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)
    
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
    
    def add_widget(self, widget):
        """Add a widget to the content area."""
        self.content_layout.addWidget(widget)
    
    def set_content_widget(self, widget):
        """Set a central content widget."""
        self.content_layout.addWidget(widget)
    
    def paintEvent(self, event):
        """Draw rounded corners for the frameless window."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(AISColors.surface))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 14, 14)


# Re-export with alias
Window = BeautifulWindow


class WindowManager:
    """Manages multiple beautiful AIOS windows."""
    
    def __init__(self):
        self.windows = []
    
    def create_window(self, title="AIOS App", x=200, y=200, width=700, height=500):
        window = BeautifulWindow(title, x, y, width, height)
        self.windows.append(window)
        return window
    
    def close_all(self):
        for window in self.windows:
            window.close()
        self.windows.clear()
    
    def count(self):
        return len(self.windows)
