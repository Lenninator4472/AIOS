from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QPushButton, QLabel, QListWidget
from PySide6.QtCore import Qt, QProcess
import subprocess

class AppLauncher(QWidget):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.layout = QVBoxLayout()
        
        # App list
        self.app_list = QListWidget()
        self.app_list.addItems(["Chrome", "VS Code", "Terminal", "Calculator"])
        self.app_list.itemDoubleClicked.connect(self.launch_app)
        
        # Custom command
        self.custom_cmd = QLineEdit()
        self.custom_cmd.setPlaceholderText("Enter custom command...")
        self.custom_btn = QPushButton("Run")
        self.custom_btn.clicked.connect(self.run_custom_command)
        
        self.layout.addWidget(QLabel("Installed Apps:"))
        self.layout.addWidget(self.app_list)
        self.layout.addWidget(self.custom_cmd)
        self.layout.addWidget(self.custom_btn)
        self.setLayout(self.layout)
    
    def launch_app(self, item):
        app = item.text().lower()
        try:
            if app == "chrome":
                subprocess.Popen(["flatpak", "run", "com.google.Chrome"])
            elif app == "vs code":
                subprocess.Popen(["flatpak", "run", "com.visualstudio.code"])
            elif app == "terminal":
                subprocess.Popen(["gnome-terminal"])
            elif app == "calculator":
                subprocess.Popen(["gnome-calculator"])
            self.bus.emit("app.launched", {"app": app})
        except Exception as e:
            self.bus.emit("app.error", {"error": str(e)})
    
    def run_custom_command(self):
        cmd = self.custom_cmd.text()
        try:
            subprocess.Popen(cmd, shell=True)
            self.bus.emit("app.launched", {"app": cmd})
        except Exception as e:
            self.bus.emit("app.error", {"error": str(e)})
