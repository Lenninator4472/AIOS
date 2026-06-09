from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QLineEdit, QPushButton
from PySide6.QtCore import Qt, Signal, QObject

class LLMSignals(QObject):
    output_received = Signal(str)
    input_submitted = Signal(str)

class LLMPanel(QWidget):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.signals = LLMSignals()
        
        # UI
        self.layout = QVBoxLayout()
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask the LLM...")
        self.submit_btn = QPushButton("Send")
        
        self.layout.addWidget(self.output)
        self.layout.addWidget(self.input)
        self.layout.addWidget(self.submit_btn)
        self.setLayout(self.layout)
        
        # Event handlers
        self.submit_btn.clicked.connect(self.submit_prompt)
        self.input.returnPressed.connect(self.submit_prompt)
        
        # Event bus subscriptions
        self.bus.subscribe("llm.output", self.display_output)
    
    def submit_prompt(self):
        prompt = self.input.text()
        if prompt.strip():
            self.signals.input_submitted.emit(prompt)
            self.bus.emit("llm.input", {"prompt": prompt})
            self.input.clear()
    
    def display_output(self, event_type, data):
        self.output.append(f"AI: {data['output']}")
