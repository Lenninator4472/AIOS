"""
Tests for AIOS Beautiful GUI - Window Management
TDD: RED → GREEN → SURFACE
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# We need QApplication to exist for widget tests
# This must be done before importing any Qt modules
@pytest.fixture(scope="session")
def qapp():
    """Create QApplication once for all tests."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


class TestThemeSystem:
    """Test the beautiful dark theme system."""
    
    def test_colors_exist(self):
        """Theme colors should be defined."""
        from gui.theme import AISColors
        assert AISColors.background is not None
        assert AISColors.surface is not None
        assert AISColors.primary is not None
        assert AISColors.accent is not None
        assert AISColors.text is not None
    
    def test_gradients(self):
        """Gradient functions should return brushes."""
        from gui.theme import AISColors
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QBrush
        rect = QRect(0, 0, 100, 100)
        brush = AISColors.header_gradient(rect)
        assert isinstance(brush, QBrush)
    
    def test_theme_apply(self, qapp):
        """Theme should apply without errors."""
        from gui.theme import AITheme
        # Should not raise
        AITheme.apply(qapp)
    
    def test_animation_factory(self):
        """Animation factory should create valid animations."""
        from gui.theme import AnimationFactory
        from PySide6.QtWidgets import QWidget, QGraphicsOpacityEffect
        widget = QWidget()
        anim = AnimationFactory.fade_in(widget, 100)
        assert anim is not None
        assert anim.duration() == 100


class TestWindowManager:
    """Test the beautiful window manager."""
    
    def test_window_manager_create(self, qapp):
        """WindowManager should create beautiful windows."""
        from gui.window_manager import WindowManager, BeautifulWindow
        wm = WindowManager()
        assert wm.count() == 0
        
        window = wm.create_window("Test", 100, 100, 400, 300)
        assert isinstance(window, BeautifulWindow)
        assert wm.count() == 1
    
    def test_window_title(self, qapp):
        """Window should have correct title."""
        from gui.window_manager import BeautifulWindow
        window = BeautifulWindow("My Window", 100, 100, 400, 300)
        assert window.title_bar.title == "My Window"
    
    def test_window_frameless(self, qapp):
        """Window should be frameless."""
        from gui.window_manager import BeautifulWindow
        from PySide6.QtCore import Qt
        window = BeautifulWindow("Test", 100, 100, 400, 300)
        flags = window.windowFlags()
        assert flags & Qt.FramelessWindowHint
    
    def test_title_bar_buttons(self, qapp):
        """Title bar should have min/max/close buttons."""
        from gui.window_manager import BeautifulWindow
        window = BeautifulWindow("Test", 100, 100, 400, 300)
        tb = window.title_bar
        assert tb.min_btn is not None
        assert tb.max_btn is not None
        assert tb.close_btn is not None
    
    def test_window_add_widget(self, qapp):
        """Window should accept content widgets."""
        from gui.window_manager import BeautifulWindow
        from PySide6.QtWidgets import QLabel
        window = BeautifulWindow("Test", 100, 100, 400, 300)
        label = QLabel("Hello")
        window.add_widget(label)
        # Content layout should have the label
        assert window.content_layout.count() >= 1


class TestMainShell:
    """Test the main AIOS shell."""
    
    def test_main_shell_imports(self):
        """Main shell should import cleanly."""
        # Just verify all the imports work
        from gui.theme import AISColors, AITheme
        from gui.window_manager import BeautifulWindow, TitleBar, WindowManager
        # Success if we get here
        assert True
    
    def test_title_bar_signals(self, qapp):
        """Title bar should emit signals on button clicks."""
        from gui.window_manager import TitleBar
        tb = TitleBar("Test")
        
        # Connect spies
        minimize_called = False
        maximize_called = False
        close_called = False
        
        def on_min():
            nonlocal minimize_called
            minimize_called = True
        
        def on_max():
            nonlocal maximize_called
            maximize_called = True
        
        def on_close():
            nonlocal close_called
            close_called = True
        
        tb.minimize_clicked.connect(on_min)
        tb.maximize_clicked.connect(on_max)
        tb.close_clicked.connect(on_close)
        
        # Click buttons
        tb.min_btn.clicked.emit()
        tb.max_btn.clicked.emit()
        tb.close_btn.clicked.emit()
        
        assert minimize_called, "Minimize signal not emitted"
        assert maximize_called, "Maximize signal not emitted"
        assert close_called, "Close signal not emitted"


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])
