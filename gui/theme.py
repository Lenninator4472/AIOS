"""
AIOS Beautiful Theme System
Dark theme with stunning color palette, gradients, and smooth animations.
"""

from PySide6.QtGui import QPalette, QColor, QLinearGradient, QBrush, QFont
from PySide6.QtCore import Qt, QEasingCurve, QPropertyAnimation, QPoint, QSize


class AISColors:
    """Stunning dark theme color palette — Dracula-inspired with AIOS flair."""
    # Core
    background = QColor("#0D0D1A")       # Deep midnight blue-black
    surface = QColor("#1A1B2E")           # Dark surface
    surface_light = QColor("#242538")     # Lighter surface for cards
    surface_lighter = QColor("#2D2E42")   # Hover states
    
    # Primary / Accent
    primary = QColor("#7C3AED")           # Vibrant purple
    primary_light = QColor("#A78BFA")     # Light purple
    primary_dark = QColor("#5B21B6")      # Deep purple
    accent = QColor("#06B6D4")            # Cyan accent
    accent_light = QColor("#22D3EE")      # Light cyan
    accent_glow = QColor("#0891B2")       # Glow effect
    
    # Functional
    success = QColor("#10B981")           # Green
    warning = QColor("#F59E0B")           # Amber
    error = QColor("#EF4444")             # Red
    info = QColor("#3B82F6")              # Blue
    
    # Text
    text = QColor("#E2E8F0")              # Primary text
    text_muted = QColor("#94A3B8")        # Secondary text
    text_dim = QColor("#64748B")          # Disabled text
    text_on_primary = QColor("#FFFFFF")   # Text on primary bg
    
    # Borders
    border = QColor("#2D2E42")            # Subtle borders
    border_focus = QColor("#7C3AED")      # Focused border
    border_accent = QColor("#06B6D4")     # Accent border
    
    # Special
    title_bar_bg = QColor("#0F0F23")      # Title bar background
    title_bar_text = QColor("#E2E8F0")    # Title bar text
    glow = QColor(124, 58, 237, 40)       # Purple glow ( translucent)
    overlay = QColor(13, 13, 26, 180)     # Modal overlay
    
    # Gradients
    @staticmethod
    def header_gradient(rect):
        """Stunning gradient for title bars and headers"""
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor("#7C3AED"))
        grad.setColorAt(0.5, QColor("#06B6D4"))
        grad.setColorAt(1.0, QColor("#7C3AED"))
        return QBrush(grad)
    
    @staticmethod
    def accent_gradient(rect):
        """Soft accent gradient for buttons and highlights"""
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor("#7C3AED"))
        grad.setColorAt(1.0, QColor("#5B21B6"))
        return QBrush(grad)
    
    @staticmethod
    def glow_gradient(rect):
        """Subtle glow gradient for hover effects"""
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor(124, 58, 237, 60))
        grad.setColorAt(0.5, QColor(6, 182, 212, 30))
        grad.setColorAt(1.0, QColor(124, 58, 237, 60))
        return QBrush(grad)


class AITheme:
    """Applies the beautiful dark theme to the entire application."""
    
    FONT_FAMILY = "Segoe UI, SF Pro Display, -apple-system, sans-serif"
    
    @staticmethod
    def apply(app):
        """Apply the global dark theme palette and stylesheet."""
        palette = QPalette()
        
        # Fill all palette roles
        palette.setColor(QPalette.Window, AISColors.background)
        palette.setColor(QPalette.WindowText, AISColors.text)
        palette.setColor(QPalette.Base, AISColors.surface)
        palette.setColor(QPalette.AlternateBase, AISColors.surface_light)
        palette.setColor(QPalette.ToolTipBase, AISColors.surface_light)
        palette.setColor(QPalette.ToolTipText, AISColors.text)
        palette.setColor(QPalette.Text, AISColors.text)
        palette.setColor(QPalette.Button, AISColors.surface_light)
        palette.setColor(QPalette.ButtonText, AISColors.text)
        palette.setColor(QPalette.BrightText, AISColors.text_on_primary)
        palette.setColor(QPalette.Link, AISColors.primary_light)
        palette.setColor(QPalette.Highlight, AISColors.primary)
        palette.setColor(QPalette.HighlightedText, AISColors.text_on_primary)
        
        # Disabled states
        palette.setColor(QPalette.Disabled, QPalette.WindowText, AISColors.text_dim)
        palette.setColor(QPalette.Disabled, QPalette.Text, AISColors.text_dim)
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, AISColors.text_dim)
        
        app.setPalette(palette)
        
        # Set font
        font = QFont(AITheme.FONT_FAMILY)
        font.setPointSize(10)
        app.setFont(font)
        
        # Global stylesheet
        app.setStyleSheet("""
            /* Global */
            QWidget {
                background-color: #0D0D1A;
                color: #E2E8F0;
                font-family: "Segoe UI", "SF Pro Display", -apple-system, sans-serif;
                border: none;
            }
            
            /* Tooltips */
            QToolTip {
                background-color: #242538;
                color: #E2E8F0;
                border: 1px solid #2D2E42;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }
            
            /* Scrollbars */
            QScrollBar:vertical {
                background: #1A1B2E;
                width: 8px;
                border-radius: 4px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #2D2E42;
                min-height: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #7C3AED;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar:horizontal {
                background: #1A1B2E;
                height: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #2D2E42;
                min-width: 30px;
                border-radius: 4px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #7C3AED;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0;
            }
            
            /* Menu */
            QMenu {
                background-color: #1A1B2E;
                border: 1px solid #2D2E42;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 32px 8px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #7C3AED;
                color: #FFFFFF;
            }
            QMenu::separator {
                height: 1px;
                background: #2D2E42;
                margin: 4px 8px;
            }
        """)


class AnimationFactory:
    """Create beautiful, smooth animations for UI elements."""
    
    @staticmethod
    def fade_in(widget, duration=300, start_value=0.0, end_value=1.0):
        """Fade in animation with easing."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(duration)
        anim.setStartValue(start_value)
        anim.setEndValue(end_value)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        return anim
    
    @staticmethod
    def slide_in(widget, direction="left", duration=250):
        """Slide in animation from any direction."""
        anim = QPropertyAnimation(widget, b"pos")
        anim.setDuration(duration)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        return anim
    
    @staticmethod
    def pulse_animation(target, property_name=b"opacity", duration=1000):
        """Pulse/glow animation loop."""
        anim = QPropertyAnimation(target, property_name)
        anim.setDuration(duration)
        anim.setStartValue(0.6)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.InOutSine)
        anim.setLoopCount(-1)  # infinite
        return anim
