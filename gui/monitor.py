from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import Qt, QTimer
import psutil

class SystemMonitor(QWidget):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.layout = QVBoxLayout()
        
        # CPU
        self.cpu_label = QLabel("CPU Usage: 0%")
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100)
        self.layout.addWidget(self.cpu_label)
        self.layout.addWidget(self.cpu_progress)
        
        # Memory
        self.mem_label = QLabel("Memory Usage: 0%")
        self.mem_progress = QProgressBar()
        self.mem_progress.setRange(0, 100)
        self.layout.addWidget(self.mem_label)
        self.layout.addWidget(self.mem_progress)
        
        # Disk
        self.disk_label = QLabel("Disk Usage: 0%")
        self.disk_progress = QProgressBar()
        self.disk_progress.setRange(0, 100)
        self.layout.addWidget(self.disk_label)
        self.layout.addWidget(self.disk_progress)
        
        self.setLayout(self.layout)
        
        # Update timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_metrics)
        self.timer.start(1000)  # Update every second
    
    def update_metrics(self):
        # CPU
        cpu_percent = psutil.cpu_percent()
        self.cpu_label.setText(f"CPU Usage: {cpu_percent}%")
        self.cpu_progress.setValue(int(cpu_percent))
        
        # Memory
        mem = psutil.virtual_memory()
        mem_percent = mem.percent
        self.mem_label.setText(f"Memory Usage: {mem_percent}%")
        self.mem_progress.setValue(int(mem_percent))
        
        # Disk
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        self.disk_label.setText(f"Disk Usage: {disk_percent}%")
        self.disk_progress.setValue(int(disk_percent))
        
        # Emit event
        self.bus.emit("system.monitor.tick", {
            "cpu": cpu_percent,
            "memory": mem_percent,
            "disk": disk_percent
        })
