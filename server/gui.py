import sys
import socket
import threading
import asyncio
import uvicorn
import subprocess
import os
import json
import logging
import re
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QSystemTrayIcon, 
                             QMenu, QMessageBox, QPlainTextEdit, QFileDialog,
                             QDialog, QTabWidget, QFrame, QSizePolicy, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QIcon, QAction, QColor, QPixmap, QPainter, QTextCursor

# Add project root to sys.path to allow importing from shared
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from shared.logger import setup_logger, QtLogHandler
    from shared.utils import get_app_dir
except ImportError:
    # Fallback for frozen EXE
    from logger import setup_logger, QtLogHandler
    from utils import get_app_dir

logger = setup_logger("Server")

# Expose the FastAPI app
try:
    from server.main import app as fastapi_app, manager as connection_manager
except ImportError:
    from main import app as fastapi_app, manager as connection_manager

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

class TunnelThread(QObject):
    url_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, port=8000):
        super().__init__()
        self.port = port
        self.process = None
        self._running = False

    def find_cloudflared(self):
        local_path = os.path.join(os.getcwd(), "cloudflared.exe" if sys.platform == "win32" else "cloudflared")
        if os.path.exists(local_path): return local_path
        app_dir = get_app_dir()
        app_path = os.path.join(app_dir, "cloudflared.exe" if sys.platform == "win32" else "cloudflared")
        if os.path.exists(app_path): return app_path
        internal_path = os.path.join(app_dir, "_internal", "cloudflared.exe" if sys.platform == "win32" else "cloudflared")
        if os.path.exists(internal_path): return internal_path
        return shutil.which("cloudflared")

    def start(self):
        self._running = True
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        binary = self.find_cloudflared()
        if not binary:
            self.error_occurred.emit("Cloudflare binary not found.")
            self.finished.emit()
            return

        cmd = [binary, "tunnel", "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate"]
        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            url_pattern = re.compile(r'https://[a-zA-Z0-9-.]+\.trycloudflare\.com')
            while self._running and self.process.poll() is None:
                line = self.process.stdout.readline()
                if not line: break
                clean_line = line.strip()
                if clean_line:
                    if "trycloudflare.com" in clean_line: logger.info(f"[Tunnel] {clean_line}")
                    else: logger.debug(f"[Tunnel] {clean_line}")
                match = url_pattern.search(clean_line)
                if match: self.url_ready.emit(match.group(0).strip())
        except Exception as e: self.error_occurred.emit(str(e))
        finally:
            self.stop()
            self.finished.emit()

    def stop(self):
        self._running = False
        if self.process:
            try:
                if sys.platform == 'win32': subprocess.run(f"taskkill /F /T /PID {self.process.pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else: self.process.terminate()
            except Exception: pass
            self.process = None

class ServerThread(threading.Thread):
    def __init__(self, app, host="0.0.0.0", port=8000):
        super().__init__()
        self.app, self.host, self.port = app, host, port
        self.server, self.loop = None, None
        self.daemon = True

    def run(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            config = uvicorn.Config(self.app, host=self.host, port=self.port, log_level="info", loop="asyncio", ws_max_size=100 * 1024 * 1024, log_config=None)
            self.server = uvicorn.Server(config)
            self.loop.run_until_complete(self.server.serve())
        except Exception as e: logger.error(f"Server error: {e}")

    def stop(self):
        if self.server:
            self.server.should_exit = True
        self.join(timeout=2.0)
        if self.is_alive() and self.loop:
            logger.warning("Server thread did not stop gracefully; forcing loop stop")
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.join(timeout=1.0)



class AboutDialog(QDialog):
    def __init__(self, parent=None, is_server=True):
        super().__init__(parent)
        self.setWindowTitle("About DNA Bridge")
        self.setFixedSize(420, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog { background-color: #0f0f0f; color: #ffffff; font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #e0e0e0; }
            QLabel#title_lbl { font-size: 22px; font-weight: bold; color: #3a86ff; margin-top: 5px; }
            QLabel#section_lbl { font-size: 13px; font-weight: bold; color: #3a86ff; margin-top: 10px; margin-bottom: 3px; }
            QFrame#card { background-color: #1a1a1a; border: 1px solid #2d2d2d; border-radius: 10px; padding: 12px; }
            QPushButton#close_btn { background-color: #3a86ff; border: none; border-radius: 6px; padding: 8px 16px; color: white; font-weight: bold; font-size: 13px; margin-top: 15px; }
            QPushButton#close_btn:hover { background-color: #5595ff; }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 15, 25, 20)
        layout.setSpacing(8)
        title_lbl = QLabel("DNA Bridge Server" if is_server else "DNA Bridge Client")
        title_lbl.setObjectName("title_lbl")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)
        version_lbl = QLabel("Version 3.2")
        version_lbl.setStyleSheet("color: #888; font-size: 11px;")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_lbl)
        card = QFrame(); card.setObjectName("card")
        card_layout = QVBoxLayout(card); card_layout.setSpacing(5)
        dev_title = QLabel("DEVELOPED BY"); dev_title.setObjectName("section_lbl"); dev_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        giant_lbl = QLabel("GIANT"); giant_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: white;"); giant_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline = QLabel("All hail the afternoon supervisor."); tagline.setStyleSheet("font-style: italic; color: #aaa; margin-top: 2px; font-size: 11px;"); tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(dev_title); card_layout.addWidget(giant_lbl); card_layout.addWidget(tagline); card_layout.addSpacing(5)
        feat_title = QLabel("KEY FEATURES"); feat_title.setObjectName("section_lbl"); feat_title.setAlignment(Qt.AlignmentFlag.AlignCenter); card_layout.addWidget(feat_title)
        
        if is_server:
            features = [
                "FastAPI WebSocket Relay: Non-blocking connection router with high-throughput routing.",
                "LAN Discovery via mDNS: Multi-interface zeroconf broadcast of local endpoints.",
                "Automated Cloudflare Tunneling: Integrated NAT-traversal via secure WAN tunnel bridging.",
                "Session Multiplexing: Concurrent channel coordination using cryptographically isolated keys.",
                "Thread-Isolated asyncio Engine: Non-blocking uvicorn runtime running in a dedicated OS thread."
            ]
        else:
            features = [
                "End-to-End Cryptography: PBKDF2-derived AES-256-GCM key matching for zero-knowledge data privacy.",
                "Debounced MIME Event Intercept: Deferred reads preventing OS clipboard locking and race conditions.",
                "Multi-Format Serialization: Seamless base64 packaging and zipping for files, rich HTML, and image sync.",
                "Asynchronous Service Discovery: Background LAN mDNS resolution with automated public tunnel fallback.",
                "Event-Driven PyQt6 Architecture: Responsive Qt interface scheduled cooperatively on a qasync event loop."
            ]
            
        for f in features:
            f_lbl = QLabel(f"• {f}")
            f_lbl.setStyleSheet("color: #ccc; font-size: 11px; margin: 1px;")
            f_lbl.setWordWrap(True)
            card_layout.addWidget(f_lbl)
            
        layout.addWidget(card)
        close_btn = QPushButton("Close"); close_btn.setObjectName("close_btn"); close_btn.clicked.connect(self.accept); layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

class StyledCard(QFrame):
    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(15, 12, 15, 12); self.card_layout.setSpacing(10)
        if title:
            title_lbl = QLabel(title); title_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #3a86ff; margin-bottom: 2px;"); self.card_layout.addWidget(title_lbl)
        self.setStyleSheet("QFrame#card { background-color: #1a1a1a; border: 1px solid #2d2d2d; border-radius: 10px; }")

class ServerMainWindow(QMainWindow):
    status_changed = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.server_thread, self.tunnel_thread = None, None
        self.current_tunnel_url, self.allow_exit = "", False
        
        self.log_handler = QtLogHandler()
        self.log_handler.new_record.connect(self.append_log)
        logger.addHandler(self.log_handler)
        for ln in ["uvicorn", "fastapi", "websockets"]:
            l = logging.getLogger(ln); l.addHandler(self.log_handler); l.setLevel(logging.INFO); l.propagate = False
        
        self.setWindowTitle("DNA Bridge - Relay Server")
        self.setFixedSize(420, 680)
        self.init_ui()
        self.apply_styles()
        self.tabs.setCurrentIndex(0) # Default to Logs (Index 0)

    def init_ui(self):
        central = QWidget(); self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(20, 20, 20, 20); self.main_layout.setSpacing(15)

        # Header
        self.header = QWidget(); hl = QVBoxLayout(self.header)
        hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(2)
        self.status_icon = QLabel("●"); self.status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_icon.setStyleSheet("color: #888; font-size: 20px;")
        self.status_text = QLabel("STOPPED"); self.status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_text.setStyleSheet("font-weight: bold; font-size: 14px; letter-spacing: 1.5px; color: #888;")
        hl.addWidget(self.status_icon); hl.addWidget(self.status_text)

        # Settings Card
        self.settings_card = StyledCard("Relay Configuration")
        ips_row = QHBoxLayout(); ips_lbl = QLabel("Local IPs"); ips_lbl.setFixedWidth(60)
        self.ips_val = QLabel(", ".join(get_local_ips())); self.ips_val.setWordWrap(True); self.ips_val.setStyleSheet("color: #aaa; font-size: 11px;")
        ips_row.addWidget(ips_lbl); ips_row.addWidget(self.ips_val, 1)
        
        tunnel_row = QVBoxLayout(); self.tunnel_lbl = QLabel("Public URL: Not active")
        self.tunnel_lbl.setStyleSheet("color: #888; font-size: 11px;")
        self.copy_btn = QPushButton("Copy URL"); self.copy_btn.setObjectName("mini_btn"); self.copy_btn.setFixedSize(70, 20)
        self.copy_btn.clicked.connect(self.copy_tunnel_url); self.copy_btn.setVisible(False)
        tunnel_row.addWidget(self.tunnel_lbl); tunnel_row.addWidget(self.copy_btn)
        
        action_row = QHBoxLayout()
        self.action_btn = QPushButton("Start Server"); self.action_btn.setObjectName("primary_btn")
        self.action_btn.clicked.connect(self.toggle_server)
        action_row.addWidget(self.action_btn)

        self.settings_card.card_layout.addLayout(ips_row)
        self.settings_card.card_layout.addLayout(tunnel_row)
        self.settings_card.card_layout.addLayout(action_row)

        # Tabs
        self.tabs = QTabWidget()
        
        sessions_widget = QWidget(); sl = QVBoxLayout(sessions_widget)
        sl.setContentsMargins(10, 10, 10, 10)
        
        self.session_list = QListWidget()
        self.session_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
            }
        """)
        self.no_sessions_lbl = QLabel("No active sessions currently.")
        self.no_sessions_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_sessions_lbl.setStyleSheet("color: #666; font-style: italic; font-size: 12px; margin-top: 20px;")
        
        sl.addWidget(self.session_list)
        sl.addWidget(self.no_sessions_lbl)
        
        # Poll connection manager for active sessions
        self.session_timer = QTimer(self)
        self.session_timer.timeout.connect(self.update_active_sessions)
        self.session_timer.start(2000)
        
        log_widget = QWidget(); ll = QVBoxLayout(log_widget); ll.setContentsMargins(8, 10, 8, 8)
        lc = QHBoxLayout(); self.clear_btn = QPushButton("Clear"); self.clear_btn.setObjectName("mini_btn")
        self.clear_btn.clicked.connect(self.clear_logs)
        self.export_btn = QPushButton("Export"); self.export_btn.setObjectName("mini_btn")
        self.export_btn.clicked.connect(self.export_logs)
        self.about_btn = QPushButton("About"); self.about_btn.setObjectName("mini_btn")
        self.about_btn.clicked.connect(self.show_about_dialog)
        lc.addStretch(); lc.addWidget(self.clear_btn); lc.addWidget(self.export_btn); lc.addWidget(self.about_btn)
        self.log_output = QPlainTextEdit(); self.log_output.setReadOnly(True); self.log_output.setMaximumBlockCount(1000)
        ll.addLayout(lc); ll.addWidget(self.log_output)
        
        self.tabs.addTab(log_widget, "System Logs")
        self.tabs.addTab(sessions_widget, "Sessions")

        self.main_layout.addWidget(self.header)
        self.main_layout.addWidget(self.settings_card)
        self.main_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        # Tray
        self.tray = QSystemTrayIcon(self); self.tray.setIcon(self.create_status_icon("#888"))
        tm = QMenu(); self.show_act = QAction("Show Server", self); self.show_act.triggered.connect(self.showNormal)
        self.toggle_act = QAction("Start Server", self); self.toggle_act.triggered.connect(self.toggle_server)
        self.exit_act = QAction("Exit", self); self.exit_act.triggered.connect(self.exit_app)
        tm.addAction(self.show_act); tm.addAction(self.toggle_act); tm.addSeparator(); tm.addAction(self.exit_act)
        self.tray.setContextMenu(tm); self.tray.activated.connect(self.on_tray_activated); self.tray.show()
        self.status_changed.connect(self.update_ui_state)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0f0f0f; }
            QLabel { color: #ffffff; font-size: 12px; }
            QPushButton#primary_btn { background-color: #3a86ff; border: none; border-radius: 6px; padding: 8px; color: white; font-weight: bold; font-size: 12px; }
            QPushButton#primary_btn:hover { background-color: #5595ff; }
            QPushButton#stop_btn { background-color: #d83b01; border: none; border-radius: 6px; padding: 8px; color: white; font-weight: bold; font-size: 12px; }
            QPushButton#stop_btn:hover { background-color: #f04a10; }
            QPushButton#mini_btn { background-color: transparent; border: 1px solid #333; border-radius: 4px; padding: 3px 8px; color: #888; font-size: 10px; }
            QPushButton#mini_btn:hover { background-color: #222; color: white; border: 1px solid #444; }
            QTabWidget::pane { border: 1px solid #2d2d2d; border-radius: 8px; background-color: #161616; top: -1px; }
            QTabBar::tab { background-color: transparent; color: #666; padding: 8px 15px; font-weight: bold; font-size: 11px; }
            QTabBar::tab:selected { color: #3a86ff; border-bottom: 2px solid #3a86ff; }
            QPlainTextEdit { background-color: #0c0c0c; border: none; color: #00ff00; font-family: 'Consolas', monospace; font-size: 11px; }
            QScrollBar:vertical { border: none; background: transparent; width: 6px; }
            QScrollBar::handle:vertical { background: #333; border-radius: 3px; min-height: 20px; }
        """)

    def append_log(self, msg, lvl):
        clr = "#00ff00"
        if lvl >= logging.ERROR: clr = "#ff5555"
        elif lvl >= logging.WARNING: clr = "#ffff55"
        self.log_output.appendHtml(f'<span style="color:{clr};">{msg}</span>')
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)

    def clear_logs(self): self.log_output.clear()

    def update_active_sessions(self):
        try:
            active = connection_manager.get_active_sessions()
        except Exception:
            active = []
            
        self.session_list.clear()
        
        if not active:
            self.no_sessions_lbl.setVisible(True)
            self.session_list.setVisible(False)
            return
            
        self.no_sessions_lbl.setVisible(False)
        self.session_list.setVisible(True)
        
        for code, connections in active:
            num_devices = len(connections)
            if num_devices == 0:
                continue
                
            item = QListWidgetItem()
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: #1a1a1a;
                    border: 1px solid #2d2d2d;
                    border-left: 3px solid #3a86ff;
                    border-radius: 6px;
                    margin: 4px 8px;
                }
            """)
            c_layout = QHBoxLayout(card)
            c_layout.setContentsMargins(15, 10, 15, 10)
            
            code_lbl = QLabel(f"Session: {code}")
            code_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #ffffff;")
            
            devices_lbl = QLabel(f"{num_devices} device(s) connected")
            devices_lbl.setStyleSheet("color: #888; font-size: 11px;")
            
            c_layout.addWidget(code_lbl)
            c_layout.addStretch()
            c_layout.addWidget(devices_lbl)
            
            hint = card.sizeHint()
            hint.setHeight(hint.height() + 8)
            item.setSizeHint(hint)
            
            self.session_list.addItem(item)
            self.session_list.setItemWidget(item, card)

    def export_logs(self):
        fp, _ = QFileDialog.getSaveFileName(self, "Export Logs", os.path.join(get_app_dir(), f"server_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"), "Text Files (*.txt)")
        if fp:
            try:
                with open(fp, 'w') as f: f.write(self.log_output.toPlainText())
                QMessageBox.information(self, "Success", "Logs exported.")
            except Exception as e: QMessageBox.critical(self, "Error", f"Failed: {e}")

    def toggle_server(self):
        if self.server_thread and self.server_thread.is_alive(): self.stop_server()
        else: self.start_server()

    def start_server(self):
        if not self.server_thread or not self.server_thread.is_alive():
            self.server_thread = ServerThread(fastapi_app); self.server_thread.start()
            QTimer.singleShot(1000, self.start_tunnel)
            self.status_changed.emit(True)
            self.hide()
            self.tray.showMessage("Server Active", "DNA Bridge relay is running.", QSystemTrayIcon.MessageIcon.Information, 2000)

    def start_tunnel(self):
        self.tunnel_lbl.setText("Public URL: Connecting...")
        self.tunnel_thread = TunnelThread(); self.tunnel_thread.url_ready.connect(self.on_url_ready)
        self.tunnel_thread.error_occurred.connect(lambda e: self.tunnel_lbl.setText(f"Tunnel Error: {e}"))
        self.tunnel_thread.start()

    def stop_server(self):
        if self.server_thread: self.server_thread.stop(); self.server_thread = None
        if self.tunnel_thread: self.tunnel_thread.stop(); self.tunnel_thread = None
        self.tunnel_lbl.setText("Public URL: Not active"); self.copy_btn.setVisible(False)
        self.status_changed.emit(False)

    def on_url_ready(self, url):
        self.current_tunnel_url = url; self.copy_btn.setVisible(True)
        ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
        self.tunnel_lbl.setText(f"Public URL: {ws_url}")
        logger.info(f"Tunnel ready: {url}")

    def copy_tunnel_url(self):
        if self.current_tunnel_url:
            ws_url = self.current_tunnel_url.replace("https://", "wss://").replace("http://", "ws://")
            QApplication.clipboard().setText(ws_url)
            self.copy_btn.setText("Copied!"); QTimer.singleShot(1500, lambda: self.copy_btn.setText("Copy URL"))

    def update_ui_state(self, run):
        if run:
            self.status_icon.setStyleSheet("color: #4CAF50; font-size: 20px;")
            self.status_text.setText("RUNNING: PORT 8000"); self.status_text.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 14px;")
            self.action_btn.setText("Stop Server"); self.action_btn.setObjectName("stop_btn")
            self.toggle_act.setText("Stop Server"); self.tray.setIcon(self.create_status_icon("#4CAF50"))
        else:
            self.status_icon.setStyleSheet("color: #F44336; font-size: 20px;")
            self.status_text.setText("STOPPED"); self.status_text.setStyleSheet("color: #F44336; font-weight: bold; font-size: 14px;")
            self.action_btn.setText("Start Server"); self.action_btn.setObjectName("primary_btn")
            self.toggle_act.setText("Start Server"); self.tray.setIcon(self.create_status_icon("#888"))
        self.action_btn.style().unpolish(self.action_btn); self.action_btn.style().polish(self.action_btn)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick: self.showNormal(); self.activateWindow()

    def show_about_dialog(self): AboutDialog(self).exec()

    def closeEvent(self, event):
        if self.server_thread and self.server_thread.is_alive() and not self.allow_exit:
            event.ignore(); self.hide()
            self.tray.showMessage("Still Running", "Server is active in tray.", QSystemTrayIcon.MessageIcon.Information, 1500)
        else: self.stop_server(); event.accept()

    def exit_app(self): self.allow_exit = True; self.stop_server(); QApplication.quit()

    def create_status_icon(self, color):
        px = QPixmap(64, 64); px.fill(Qt.GlobalColor.transparent); p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setBrush(QColor(color)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(12, 12, 40, 40); p.end()
        return QIcon(px)

def main():
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    win = ServerMainWindow(); win.show(); sys.exit(app.exec())

if __name__ == "__main__": main()
