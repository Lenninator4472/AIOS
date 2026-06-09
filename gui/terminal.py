from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLineEdit
from PySide6.QtCore import Qt, Signal, QObject

class TerminalSignals(QObject):
    output_received = Signal(str)
    input_submitted = Signal(str)

class Terminal(QWidget):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.signals = TerminalSignals()
        
        # UI
        self.layout = QVBoxLayout()
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Type command and press Enter...")
        
        self.layout.addWidget(self.output)
        self.layout.addWidget(self.input)
        self.setLayout(self.layout)
        
        # Event handlers
        self.input.returnPressed.connect(self.submit_command)
        
        # Event bus subscriptions
        self.bus.subscribe("terminal.output", self.display_output)
    
    def submit_command(self):
        command = self.input.text()
        if command.strip():
            self.signals.input_submitted.emit(command)
            self.bus.emit("terminal.input", {"command": command})
            self.input.clear()
    
    def display_output(self, event_type, data):
        self.output.append(data["output"])
