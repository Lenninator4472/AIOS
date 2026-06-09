import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from main import AIShell

# Preload kernel and event bus
app = QApplication(sys.argv)
window = AIShell()

# Show window after 100ms (non-blocking)
QTimer.singleShot(100, window.show)

# Start event loop
sys.exit(app.exec())
