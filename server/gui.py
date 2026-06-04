import sys
import socket
import threading
import asyncio
import uvicorn
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QSystemTrayIcon, 
                             QMenu, QMessageBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QAction, QColor, QPixmap, QPainter

# Expose the FastAPI app
try:
    from server.main import app as fastapi_app
except ImportError:
    from main import app as fastapi_app

def get_local_ips():
    ips = []
    try:
        hostname = socket.gethostname()
        _, _, ip_list = socket.gethostbyname_ex(hostname)
        for ip in ip_list:
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            ips.append("127.0.0.1")
    return ips

class ServerThread(threading.Thread):
    def __init__(self, app, host="0.0.0.0", port=8000):
        super().__init__()
        self.app = app
        self.host = host
        self.port = port
        self.server = None
        self.loop = None
        self.daemon = True

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        config = uvicorn.Config(
            self.app, 
            host=self.host, 
            port=self.port, 
            log_level="info",
            loop="asyncio"
        )
        self.server = uvicorn.Server(config)
        self.loop.run_until_complete(self.server.serve())

    def stop(self):
        if self.server:
            self.server.should_exit = True
        self.join(timeout=3.0)

class ServerMainWindow(QMainWindow):
    status_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.allow_exit = False
        
        self.setWindowTitle("DNA Bridge - Relay Server")
        self.setFixedSize(380, 260)
        
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Segoe UI', sans-serif;
            }
            QWidget {
                background-color: #1e1e1e;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
            }
            QLabel#status_lbl {
                font-size: 18px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            QLabel#ip_lbl {
                font-size: 12px;
                color: #aaaaaa;
                background-color: #2b2b2b;
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton {
                background-color: #0078d4;
                border: none;
                border-radius: 5px;
                padding: 12px;
                color: white;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
            QPushButton#stop_btn {
                background-color: #d83b01;
            }
            QPushButton#stop_btn:hover {
                background-color: #a80000;
            }
        """)

        # Central Widget Layout
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Status Label
        self.status_lbl = QLabel("Status: Stopped")
        self.status_lbl.setObjectName("status_lbl")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Info Box displaying local IP Addresses
        local_ips = get_local_ips()
        ip_text = "Local Network IP Addresses for Client Pairing:\n" + "\n".join([f" • {ip}" for ip in local_ips])
        self.ip_lbl = QLabel(ip_text)
        self.ip_lbl.setObjectName("ip_lbl")
        self.ip_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # Action button
        self.action_btn = QPushButton("Start Server")
        self.action_btn.clicked.connect(self.toggle_server)
        
        layout.addWidget(self.status_lbl)
        layout.addWidget(self.ip_lbl)
        layout.addWidget(self.action_btn)
        
        self.setCentralWidget(central)

        # System Tray setup
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.create_status_icon("gray"))
        self.tray.setToolTip("DNA Bridge Server - Stopped")
        
        # Tray Menu
        self.tray_menu = QMenu()
        self.show_action = QAction("Show Window", self)
        self.show_action.triggered.connect(self.showNormal)
        self.show_action.triggered.connect(self.activateWindow)
        
        self.toggle_action = QAction("Start Server", self)
        self.toggle_action.triggered.connect(self.toggle_server)
        
        self.exit_action = QAction("Exit", self)
        self.exit_action.triggered.connect(self.exit_application)
        
        self.tray_menu.addAction(self.show_action)
        self.tray_menu.addAction(self.toggle_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.exit_action)
        
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

        # Connect status signals to UI updates
        self.status_changed.connect(self.update_ui_state)

    def toggle_server(self):
        if self.server_thread and self.server_thread.is_alive():
            self.stop_server()
        else:
            self.start_server()

    def start_server(self):
        if not self.server_thread or not self.server_thread.is_alive():
            self.server_thread = ServerThread(fastapi_app)
            self.server_thread.start()
            self.status_changed.emit(True)
            
            # Auto-minimize/hide to tray when starting the server
            self.hide()
            self.tray.showMessage(
                "Relay Server Active",
                "The DNA Bridge server is running in the background.",
                self.create_status_icon("green"),
                3000
            )

    def stop_server(self):
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.stop()
            self.server_thread = None
        self.status_changed.emit(False)

    def update_ui_state(self, is_running: bool):
        if is_running:
            self.status_lbl.setText("Status: Running on port 8000")
            self.status_lbl.setStyleSheet("color: #107c41;") # Soft green
            self.action_btn.setText("Stop Server")
            self.action_btn.setObjectName("stop_btn")
            self.toggle_action.setText("Stop Server")
            self.tray.setIcon(self.create_status_icon("green"))
            self.tray.setToolTip("DNA Bridge Server - Running")
        else:
            self.status_lbl.setText("Status: Stopped")
            self.status_lbl.setStyleSheet("color: #e0e0e0;")
            self.action_btn.setText("Start Server")
            self.action_btn.setObjectName("")
            self.toggle_action.setText("Start Server")
            self.tray.setIcon(self.create_status_icon("gray"))
            self.tray.setToolTip("DNA Bridge Server - Stopped")
        # Apply fresh stylesheets to button
        self.action_btn.setStyleSheet(self.styleSheet())

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def closeEvent(self, event):
        # Override close button to hide to tray if server is running
        if self.server_thread and self.server_thread.is_alive() and not self.allow_exit:
            event.ignore()
            self.hide()
            self.tray.showMessage(
                "Still Running",
                "DNA Bridge Server continues to run in the background. Use the System Tray menu to exit.",
                self.create_status_icon("green"),
                2000
            )
        else:
            self.stop_server()
            event.accept()

    def exit_application(self):
        self.allow_exit = True
        self.stop_server()
        QApplication.quit()

    def create_status_icon(self, color: str):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if color == "green":
            painter.setBrush(QColor("#107c41"))
        elif color == "red":
            painter.setBrush(QColor("#d83b01"))
        else:
            painter.setBrush(QColor("#7a7a7a"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(8, 8, 48, 48)
        painter.end()
        return QIcon(pixmap)

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    
    window = ServerMainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
