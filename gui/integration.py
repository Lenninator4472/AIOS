from kernel.bus import EventBus
from kernel.engine import AIDOSKernel
from PySide6.QtCore import QObject, Signal

class KernelBridge(QObject):
    output_received = Signal(str)
    
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.kernel = AIDOSKernel(model="llama3.2:1b", dry_run=False)
        
        # Monkey-patch kernel to use our bus
        self.kernel.bus = self.bus
        
        # Subscribe to terminal input — wrap to match bus signature handler(et, data)
        self.bus.subscribe("terminal.input", lambda et, data: self.process_command(data))
        # Subscribe to LLM input
        self.bus.subscribe("llm.input", lambda et, data: self.process_llm(data))

    def process_command(self, data):
        command = data["command"]
        try:
            response = self.kernel._dispatch(command)
            self.bus.emit("terminal.output", {"output": response})
        except Exception as e:
            self.bus.emit("terminal.output", {"output": f"Error: {str(e)}"})

    def process_llm(self, data):
        prompt = data["prompt"]
        try:
            response = self.kernel.process_intent(prompt)
            output = response.get("user_response", str(response))
            self.bus.emit("llm.output", {"output": output})
        except Exception as e:
            self.bus.emit("llm.output", {"output": f"Error: {str(e)}"})
