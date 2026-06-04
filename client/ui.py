import asyncio
from qasync import asyncSlot
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QSystemTrayIcon, QMenu, 
                             QApplication, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QAction

class PairingDialog(QDialog):
    paired = pyqtSignal(str, str) # Emits (pairing_code, server_ip)

    def __init__(self, server_ip: str = "localhost"):
        super().__init__()
        self.server_ip = server_ip
        self.setWindowTitle("DNA Bridge - Pair Device")
        self.setFixedSize(320, 270)
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                font-size: 14px;
                color: #e0e0e0;
                margin-bottom: 5px;
            }
            QLineEdit {
                background-color: #3b3b3b;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
                color: white;
                font-size: 16px;
                margin-bottom: 15px;
            }
            QPushButton {
                background-color: #0078d4;
                border: none;
                border-radius: 5px;
                padding: 10px;
                color: white;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
            QPushButton#secondary {
                background-color: #444;
            }
            QPushButton#secondary:hover {
                background-color: #555;
            }
        """)

        layout = QVBoxLayout()
        
        ip_label = QLabel("Server IP Address:")
        self.ip_input = QLineEdit()
        self.ip_input.setText(self.server_ip)
        self.ip_input.setPlaceholderText("e.g. localhost or 192.168.1.5")
        self.ip_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        code_label = QLabel("Enter Pairing Code:")
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("e.g. AB12CD")
        self.code_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn_layout = QHBoxLayout()
        self.pair_btn = QPushButton("Connect")
        self.pair_btn.clicked.connect(self.on_pair)
        
        self.gen_btn = QPushButton("Generate New")
        self.gen_btn.setObjectName("secondary")
        self.gen_btn.clicked.connect(self.on_generate)
        
        btn_layout.addWidget(self.gen_btn)
        btn_layout.addWidget(self.pair_btn)
        
        layout.addWidget(ip_label)
        layout.addWidget(self.ip_input)
        layout.addWidget(code_label)
        layout.addWidget(self.code_input)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def on_pair(self):
        code = self.code_input.text().strip().upper()
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "Invalid IP", "Please enter a Server IP Address.")
            return
        if len(code) == 6:
            self.paired.emit(code, ip)
            self.accept()
        else:
            QMessageBox.warning(self, "Invalid Code", "Please enter a 6-character pairing code.")

    @asyncSlot()
    async def on_generate(self):
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("Generating...")
        
        ip = self.ip_input.text().strip()
        if not ip:
            ip = "localhost"
            
        # Clean protocol if entered, and format host
        clean_ip = ip
        for proto in ["http://", "https://", "ws://", "wss://"]:
            if clean_ip.startswith(proto):
                clean_ip = clean_ip[len(proto):]
                
        if ":" not in clean_ip:
            host_with_port = f"{clean_ip}:8000"
        else:
            host_with_port = clean_ip
            
        http_url = f"http://{host_with_port}"
        
        loop = asyncio.get_running_loop()
        code = await loop.run_in_executor(None, self._fetch_code, http_url)
        
        if code:
            self.code_input.setText(code)
        else:
            # Fallback to local generation if server is offline or fails
            import random, string
            fallback_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.code_input.setText(fallback_code)
            
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("Generate New")

    def _fetch_code(self, http_url: str) -> str:
        import urllib.request
        import json
        try:
            req = urllib.request.Request(
                f"{http_url}/generate-code",
                headers={'User-Agent': 'DNA-Bridge-Client'}
            )
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.status == 200:
                    data = json.loads(response.read().decode())
                    return data.get("code")
        except Exception as e:
            print(f"Error fetching pairing code: {e}")
        return None

class SystemTrayApp(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("DNA Bridge - Not Connected")
        
        # We'll use a simple colored circle as an icon if no icon file is found
        self.setIcon(self.create_default_icon("gray"))
        
        self.menu = QMenu()
        self.status_action = QAction("Disconnected", self)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        
        self.menu.addSeparator()
        
        self.pair_action = QAction("Pair Device...", self)
        self.menu.addAction(self.pair_action)
        
        self.quit_action = QAction("Quit", self)
        self.menu.addAction(self.quit_action)
        
        self.setContextMenu(self.menu)

    def set_connected(self, connected: bool, code: str = ""):
        if connected:
            self.setIcon(self.create_default_icon("green"))
            self.setToolTip(f"DNA Bridge - Connected ({code})")
            self.status_action.setText(f"Connected: {code}")
        else:
            self.setIcon(self.create_default_icon("gray"))
            self.setToolTip("DNA Bridge - Disconnected")
            self.status_action.setText("Disconnected")

    def create_default_icon(self, color: str):
        from PyQt6.QtGui import QPainter, QColor, QPixmap
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if color == "green":
            painter.setBrush(QColor("#4CAF50"))
        elif color == "red":
            painter.setBrush(QColor("#F44336"))
        else:
            painter.setBrush(QColor("#9E9E9E"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, 8, 48, 48)
        painter.end()
        return QIcon(pixmap)
