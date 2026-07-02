import asyncio
import os
import sys
import logging
from datetime import datetime
from qasync import asyncSlot
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QSystemTrayIcon, QMenu, 
                             QApplication, QMessageBox, QPlainTextEdit, QFileDialog,
                             QDialog, QTabWidget, QListWidget, QListWidgetItem,
                             QFrame, QSizePolicy, QComboBox, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QByteArray, QTimer
from PyQt6.QtGui import QIcon, QAction, QTextCursor, QPixmap, QPainter, QColor, QFont, QLinearGradient, QImage

class AboutDialog(QDialog):
    def __init__(self, parent=None, is_server=False):
        super().__init__(parent)
        self.setWindowTitle("About DNA Bridge")
        self.setFixedSize(420, 560)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #0f0f0f;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel {
                color: #e0e0e0;
            }
            QLabel#title_lbl {
                font-size: 22px;
                font-weight: bold;
                color: #3a86ff;
                margin-top: 5px;
            }
            QLabel#section_lbl {
                font-size: 13px;
                font-weight: bold;
                color: #3a86ff;
                margin-top: 10px;
                margin-bottom: 3px;
            }
            QFrame#card {
                background-color: #1a1a1a;
                border: 1px solid #2d2d2d;
                border-radius: 10px;
                padding: 12px;
            }
            QPushButton#close_btn {
                background-color: #3a86ff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                color: white;
                font-weight: bold;
                font-size: 13px;
                margin-top: 15px;
            }
            QPushButton#close_btn:hover {
                background-color: #5595ff;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 15, 25, 20)
        layout.setSpacing(8)
        
        # Header
        title_val = "DNA Bridge Server" if is_server else "DNA Bridge Client"
        title_lbl = QLabel(title_val)
        title_lbl.setObjectName("title_lbl")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)
        
        version_lbl = QLabel("Version 4.0")
        version_lbl.setStyleSheet("color: #888; font-size: 11px;")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version_lbl)
        
        # Content Card
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(5)
        
        dev_title = QLabel("DEVELOPED BY")
        dev_title.setObjectName("section_lbl")
        dev_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        giant_lbl = QLabel("GIANT")
        giant_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        giant_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        tagline = QLabel("Built by a human on planet Earth.")
        tagline.setStyleSheet("font-style: italic; color: #aaa; margin-top: 2px; font-size: 11px;")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        card_layout.addWidget(dev_title)
        card_layout.addWidget(giant_lbl)
        card_layout.addWidget(tagline)
        card_layout.addSpacing(5)
        
        features_title = QLabel("KEY FEATURES")
        features_title.setObjectName("section_lbl")
        features_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(features_title)
        
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
        
        close_btn = QPushButton("Close")
        close_btn.setObjectName("close_btn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

class StyledCard(QFrame):
    def __init__(self, title=None, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(15, 12, 15, 12)
        self.card_layout.setSpacing(10)
        
        if title:
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #3a86ff; margin-bottom: 2px;")
            self.card_layout.addWidget(title_lbl)
            
        self.setStyleSheet("""
            QFrame#card {
                background-color: #1a1a1a;
                border: 1px solid #2d2d2d;
                border-radius: 10px;
            }
        """)


class DiscoveryDialog(QDialog):
    """
    Modal dialog that scans the local network for DNA Bridge servers via mDNS
    and lets the user select one to auto-populate the Server field.
    """
    server_selected = pyqtSignal(str)  # emits the ws-compatible host string

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Discover Servers on LAN")
        self.setFixedSize(420, 380)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setModal(True)

        self._discovery = None
        self._server_map = {}   # display_name -> DiscoveredServer
        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._try_auto_select)

        self._init_ui()
        self._apply_styles()
        self._start_discovery()

    # ------------------------------------------------------------------
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        # Title row
        title_row = QHBoxLayout()
        title_lbl = QLabel("LAN Server Discovery")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #3a86ff;")
        self._scan_lbl = QLabel("● Scanning...")
        self._scan_lbl.setStyleSheet("font-size: 10px; color: #FFC107;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        title_row.addWidget(self._scan_lbl)
        layout.addLayout(title_row)

        hint = QLabel("DNA Bridge servers on your local network appear here automatically.")
        hint.setStyleSheet("color: #666; font-size: 10px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Server list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.itemDoubleClicked.connect(self._on_select)
        layout.addWidget(self._list, 1)

        # Empty-state label (overlaid via a wrapper)
        self._empty_lbl = QLabel("No servers found yet...\n\nMake sure the DNA Bridge Server\nis running on the same network.")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #444; font-size: 11px; margin: 20px;")
        layout.addWidget(self._empty_lbl)
        self._empty_lbl.setVisible(True)

        # Buttons
        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("secondary_btn")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._restart_discovery)

        self._select_btn = QPushButton("Connect to Selected")
        self._select_btn.setObjectName("primary_btn")
        self._select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._select_btn.setEnabled(False)
        self._select_btn.clicked.connect(self._on_select)

        btn_row.addWidget(self._refresh_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._select_btn)
        layout.addLayout(btn_row)

        self._list.itemSelectionChanged.connect(
            lambda: self._select_btn.setEnabled(len(self._list.selectedItems()) > 0)
        )

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #0f0f0f;
                color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel { color: #e0e0e0; font-size: 12px; }
            QListWidget {
                background-color: #141414;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
                color: #ddd;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-bottom: 1px solid #222;
                border-radius: 0px;
            }
            QListWidget::item:selected {
                background-color: #1e3a5f;
                color: #3a86ff;
                border-left: 3px solid #3a86ff;
            }
            QListWidget::item:hover:!selected {
                background-color: #1a1a1a;
            }
            QPushButton#primary_btn {
                background-color: #3a86ff;
                border: none; border-radius: 6px;
                padding: 8px 16px; color: white;
                font-weight: bold; font-size: 12px;
            }
            QPushButton#primary_btn:hover { background-color: #5595ff; }
            QPushButton#primary_btn:disabled {
                background-color: #1e1e1e; color: #444;
            }
            QPushButton#secondary_btn {
                background-color: #252525;
                border: 1px solid #333; border-radius: 6px;
                padding: 8px 16px; color: #aaa;
                font-weight: bold; font-size: 12px;
            }
            QPushButton#secondary_btn:hover { background-color: #333; color: white; }
        """)

    # ------------------------------------------------------------------
    def _start_discovery(self):
        """Import MDNSDiscovery lazily and start browsing."""
        try:
            try:
                from client.discovery import MDNSDiscovery
            except ImportError:
                from discovery import MDNSDiscovery

            self._discovery = MDNSDiscovery(self)
            self._discovery.server_found.connect(self._on_server_found)
            self._discovery.server_lost.connect(self._on_server_lost)
            self._discovery.start()
            # Auto-select after 4 seconds if exactly one server is found
            self._auto_timer.start(4000)
        except Exception as e:
            self._scan_lbl.setText(f"⚠ Discovery unavailable: {e}")
            self._scan_lbl.setStyleSheet("font-size: 10px; color: #ff5555;")

    def _restart_discovery(self):
        """Stop current scan, clear list, restart."""
        if self._discovery:
            self._discovery.stop()
            self._discovery = None
        self._list.clear()
        self._server_map.clear()
        self._select_btn.setEnabled(False)
        self._empty_lbl.setVisible(True)
        self._scan_lbl.setText("● Scanning...")
        self._scan_lbl.setStyleSheet("font-size: 10px; color: #FFC107;")
        self._auto_timer.stop()
        self._start_discovery()

    # ------------------------------------------------------------------
    # mDNS signal handlers
    def _on_server_found(self, server):
        display = server.display_name
        if display in self._server_map:
            return  # already listed
        self._server_map[display] = server

        item = QListWidgetItem()
        item.setText(f"🖥  {display}")
        item.setData(Qt.ItemDataRole.UserRole, display)
        self._list.addItem(item)

        self._empty_lbl.setVisible(False)
        self._scan_lbl.setText(f"● {self._list.count()} server(s) found")
        self._scan_lbl.setStyleSheet("font-size: 10px; color: #4CAF50;")

    def _on_server_lost(self, name: str):
        # Remove from map and list by matching the name field in stored servers
        to_remove = [k for k, v in self._server_map.items() if v.name == name]
        for key in to_remove:
            del self._server_map[key]
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.ItemDataRole.UserRole) == key:
                    self._list.takeItem(i)
                    break

        count = self._list.count()
        self._empty_lbl.setVisible(count == 0)
        if count == 0:
            self._scan_lbl.setText("● Scanning...")
            self._scan_lbl.setStyleSheet("font-size: 10px; color: #FFC107;")
        else:
            self._scan_lbl.setText(f"● {count} server(s) found")

    def _try_auto_select(self):
        """After 4 seconds, auto-select if exactly one server was found."""
        if self._list.count() == 1:
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------
    def _on_select(self):
        items = self._list.selectedItems()
        if not items:
            return
        display = items[0].data(Qt.ItemDataRole.UserRole)
        server = self._server_map.get(display)
        if server:
            # Emit the raw host:port so app.py can format_ws_url on it
            self.server_selected.emit(f"{server.host}:{server.port}")
        self.accept()

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self._auto_timer.stop()
        if self._discovery:
            self._discovery.stop()
            self._discovery = None
        super().closeEvent(event)

class ClientMainWindow(QMainWindow):
    paired = pyqtSignal(str, str)
    recopy_requested = pyqtSignal(str)
    notification_mode_changed = pyqtSignal(str)
    plain_text_only_changed = pyqtSignal(bool)
    
    def __init__(self, server_ip: str = "localhost", notification_mode: str = "normal", plain_text_only: bool = False):
        super().__init__()
        self.server_ip = server_ip
        self.notification_mode = notification_mode
        self.plain_text_only = plain_text_only
        self.setWindowTitle("DNA Bridge Client v4.0")
        self.setFixedSize(420, 680)
        icon_path = self._resolve_icon_path("client.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.init_ui()
        self.apply_styles()
        
        # Always default to System Logs tab on startup (Index 0 now)
        self.tabs.setCurrentIndex(0)

    def _resolve_icon_path(self, filename: str) -> str:
        """Return the path to an icon file, handling both source and PyInstaller builds."""
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, filename)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(project_root, filename)

    def init_ui(self):
        central = QWidget()
        self.main_layout = QVBoxLayout(central)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        # 1. Header Section
        self.header_widget = QWidget()
        header_layout = QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)
        
        self.status_icon = QLabel("●")
        self.status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_icon.setStyleSheet("color: #888; font-size: 20px;")
        
        self.status_text = QLabel("DISCONNECTED")
        self.status_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_text.setStyleSheet("font-weight: bold; font-size: 14px; letter-spacing: 1.5px; color: #888;")
        
        header_layout.addWidget(self.status_icon)
        header_layout.addWidget(self.status_text)
        
        # 2. Connection Card
        self.conn_card = StyledCard("Connection Settings")
        
        ip_row = QHBoxLayout()
        ip_lbl = QLabel("Server")
        ip_lbl.setFixedWidth(50)
        self.ip_input = QLineEdit()
        self.ip_input.setText(self.server_ip)
        self.ip_input.setPlaceholderText("localhost or URL")
        self.discover_btn = QPushButton("Discover")
        self.discover_btn.setObjectName("secondary_btn")
        self.discover_btn.setFixedWidth(68)
        self.discover_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.discover_btn.setToolTip("Scan the local network for DNA Bridge servers")
        self.discover_btn.clicked.connect(self._open_discovery_dialog)
        ip_row.addWidget(ip_lbl)
        ip_row.addWidget(self.ip_input, 1)
        ip_row.addWidget(self.discover_btn)
        
        code_row = QHBoxLayout()
        code_lbl = QLabel("Pairing")
        code_lbl.setFixedWidth(50)
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("6-char code")
        self.code_input.setMaxLength(6)
        code_row.addWidget(code_lbl)
        code_row.addWidget(self.code_input, 1)
        
        action_row = QHBoxLayout()
        self.gen_btn = QPushButton("Generate")
        self.gen_btn.setObjectName("secondary_btn")
        self.gen_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gen_btn.clicked.connect(self.on_generate)
        
        self.connect_btn = QPushButton("Connect && Sync")
        self.connect_btn.setObjectName("primary_btn")
        self.connect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.connect_btn.clicked.connect(self.on_pair)
        
        action_row.addWidget(self.gen_btn)
        action_row.addWidget(self.connect_btn, 1)
        
        self.conn_card.card_layout.addLayout(ip_row)
        self.conn_card.card_layout.addLayout(code_row)
        self.conn_card.card_layout.addLayout(action_row)

        # 3. Settings Card
        self.settings_card = StyledCard("Preferences")
        
        notify_row = QHBoxLayout()
        notify_lbl = QLabel("Alerts")
        notify_lbl.setFixedWidth(50)
        self.notify_combo = QComboBox()
        self.notify_combo.addItems(["Always", "Muted", "Large (>5MB)"])
        
        if self.notification_mode == "quiet":
            self.notify_combo.setCurrentIndex(1)
        elif self.notification_mode == "large_only":
            self.notify_combo.setCurrentIndex(2)
            
        self.notify_combo.currentIndexChanged.connect(self._on_notify_mode_changed)
        notify_row.addWidget(notify_lbl)
        notify_row.addWidget(self.notify_combo, 1)
        
        # Plain Text Only checkbox
        self.plain_text_only_chk = QCheckBox("Plain Text Only  (strips HTML & hyperlinks on sync)")
        self.plain_text_only_chk.setChecked(self.plain_text_only)
        self.plain_text_only_chk.setToolTip(
            "When enabled, all clipboard content is synced as plain text only.\n"
            "This prevents applications like Excel from converting pasted\n"
            "content into hyperlinks when rich text or HTML formatting is present."
        )
        self.plain_text_only_chk.clicked.connect(self._on_plain_text_only_clicked)
        
        self.settings_card.card_layout.addLayout(notify_row)
        self.settings_card.card_layout.addWidget(self.plain_text_only_chk)


        # 4. View Tabs
        self.tabs = QTabWidget()
        
        # History View
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)
        history_layout.setContentsMargins(5, 5, 5, 5)
        self.history_list = QListWidget()
        history_layout.addWidget(self.history_list)
        
        # Logs View
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(8, 10, 8, 8)
        
        log_controls = QHBoxLayout()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("mini_btn")
        self.clear_btn.clicked.connect(self.clear_logs)
        
        self.export_btn = QPushButton("Export")
        self.export_btn.setObjectName("mini_btn")
        self.export_btn.clicked.connect(self.export_logs)
        
        self.about_btn = QPushButton("About")
        self.about_btn.setObjectName("mini_btn")
        self.about_btn.clicked.connect(self.show_about_dialog)
        
        log_controls.addStretch()
        log_controls.addWidget(self.clear_btn)
        log_controls.addWidget(self.export_btn)
        log_controls.addWidget(self.about_btn)
        
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(500)
        
        log_layout.addLayout(log_controls)
        log_layout.addWidget(self.log_output)
        
        self.tabs.addTab(log_widget, "System Logs")
        self.tabs.addTab(history_widget, "History")

        # Assembly
        self.main_layout.addWidget(self.header_widget)
        self.main_layout.addWidget(self.conn_card)
        self.main_layout.addWidget(self.settings_card)
        self.main_layout.addWidget(self.tabs, 1)

        self.setCentralWidget(central)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0f0f0f;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
            }
            QLineEdit {
                background-color: #252525;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 6px 10px;
                color: white;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #3a86ff;
            }
            QComboBox {
                background-color: #252525;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 5px 10px;
                color: white;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                width: 25px;
            }
            QPushButton#primary_btn {
                background-color: #3a86ff;
                border: none;
                border-radius: 6px;
                padding: 8px;
                color: white;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#primary_btn:hover {
                background-color: #5595ff;
            }
            QPushButton#secondary_btn {
                background-color: #252525;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 8px;
                color: #aaa;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#secondary_btn:hover {
                background-color: #333;
                color: white;
            }
            QPushButton#mini_btn {
                background-color: transparent;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 3px 8px;
                color: #888;
                font-size: 10px;
            }
            QPushButton#mini_btn:hover {
                background-color: #222;
                color: white;
                border: 1px solid #444;
            }
            QTabWidget::pane {
                border: 1px solid #2d2d2d;
                border-radius: 8px;
                background-color: #161616;
                top: -1px;
            }
            QTabBar::tab {
                background-color: transparent;
                color: #666;
                padding: 8px 15px;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                color: #3a86ff;
                border-bottom: 2px solid #3a86ff;
            }
            QPlainTextEdit {
                background-color: #0c0c0c;
                border: none;
                color: #00ff00;
                font-family: 'Consolas', monospace;
                font-size: 10px;
            }
            QListWidget {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #333;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #444;
            }
            QCheckBox {
                color: #aaa;
                font-size: 11px;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid #444;
                background: #1e1e1e;
            }
            QCheckBox::indicator:checked {
                background: #3a86ff;
                border: 1px solid #3a86ff;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #3a86ff;
            }
        """)

    def set_connection_status(self, state: str, code: str = ""):
        if state == "connected":
            self.status_icon.setStyleSheet("color: #4CAF50; font-size: 20px;")
            self.status_text.setText(f"PAIRED: {code}")
            self.status_text.setStyleSheet("font-weight: bold; font-size: 14px; letter-spacing: 1.5px; color: #4CAF50;")
            self.connect_btn.setText("Connected")
            self.connect_btn.setEnabled(False)
        elif state == "connecting":
            self.status_icon.setStyleSheet("color: #FFC107; font-size: 20px;")
            self.status_text.setText("CONNECTING...")
            self.status_text.setStyleSheet("font-weight: bold; font-size: 14px; letter-spacing: 1.5px; color: #FFC107;")
            self.connect_btn.setText("Cancel")
            self.connect_btn.setEnabled(True)
        else:
            self.status_icon.setStyleSheet("color: #F44336; font-size: 20px;")
            self.status_text.setText("DISCONNECTED")
            self.status_text.setStyleSheet("font-weight: bold; font-size: 14px; letter-spacing: 1.5px; color: #F44336;")
            self.connect_btn.setText("Connect & Sync")
            self.connect_btn.setEnabled(True)

    def add_history_item(self, text: str, direction: str = "sent"):
        import json
        timestamp = datetime.now().strftime("%H:%M:%S")
        direction_color = '#3a86ff' if direction == 'received' else '#4CAF50'
        direction_label = "RECEIVED" if direction == "received" else "SENT"

        # --- Parse payload type ---
        payload_type = "text"   # default
        preview_text = ""
        img_pixmap = None
        html_content = ""
        filenames = []

        try:
            data = json.loads(text)
            if isinstance(data, dict) and "type" in data:
                payload_type = data["type"]
                content = data.get("content", "")

                if payload_type == "image":
                    # Decode base64 PNG into a QPixmap thumbnail
                    try:
                        ba = QByteArray.fromBase64(content.encode("utf-8"))
                        image = QImage()
                        image.loadFromData(ba, "PNG")
                        if not image.isNull():
                            img_pixmap = QPixmap.fromImage(image).scaled(
                                180, 100,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation
                            )
                        size_kb = len(ba) / 1024
                        preview_text = f"PNG · {size_kb:.1f} KB"
                    except Exception:
                        preview_text = "[Image Data]"

                elif payload_type == "html":
                    html_content = data.get("html", "")
                    preview_text = content.replace('\n', ' ').replace('\r', '').strip()
                    if len(preview_text) > 120:
                        preview_text = preview_text[:117] + "..."

                elif payload_type == "files":
                    import base64, zipfile, io as _io
                    filenames = data.get("filenames", [])
                    _img_exts = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.tiff', '.ico'}
                    _image_members = [f for f in filenames
                                      if os.path.splitext(f.lower())[1] in _img_exts]

                    if _image_members and content:
                        # Try to extract and render the first image from the zip
                        try:
                            zip_bytes = base64.b64decode(content.encode('utf-8'))
                            with zipfile.ZipFile(_io.BytesIO(zip_bytes), 'r') as zf:
                                # Find the matching member inside the archive
                                members = zf.namelist()
                                target = next(
                                    (m for m in members
                                     if os.path.splitext(m.lower())[1] in _img_exts),
                                    None
                                )
                                if target:
                                    img_data = zf.read(target)
                                    image = QImage()
                                    image.loadFromData(img_data)
                                    if not image.isNull():
                                        img_pixmap = QPixmap.fromImage(image).scaled(
                                            180, 100,
                                            Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation
                                        )
                                        size_kb = len(img_data) / 1024
                                        fname = os.path.basename(target)
                                        preview_text = f"{fname}  ·  {size_kb:.1f} KB"
                        except Exception:
                            pass  # Fall through to plain filename list below

                    if not preview_text:
                        preview_text = ", ".join(filenames) if filenames else "[Files]"
                        if len(preview_text) > 120:
                            preview_text = preview_text[:117] + "..."

                else:
                    preview_text = content.replace('\n', ' ').replace('\r', '').strip()
                    if len(preview_text) > 120:
                        preview_text = preview_text[:117] + "..."
        except Exception:
            # Raw plain text
            preview_text = text.replace('\n', ' ').replace('\r', '').strip()
            if len(preview_text) > 120:
                preview_text = preview_text[:117] + "..."

        if not preview_text and payload_type == "text":
            preview_text = "(Empty Content)"

        # --- Build card ---
        item = QListWidgetItem()
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1a1a1a;
                border: 1px solid #2d2d2d;
                border-left: 3px solid {direction_color};
                border-radius: 6px;
                margin: 5px 12px;
            }}
        """)

        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(15, 10, 15, 10)
        c_layout.setSpacing(6)

        # Header row
        header = QHBoxLayout()
        h_lbl = QLabel(direction_label)
        h_lbl.setStyleSheet("font-weight: bold; font-size: 9px; color: #888;")
        time_lbl = QLabel(timestamp)
        time_lbl.setStyleSheet("color: #555; font-size: 9px;")

        # Type badge for html
        if payload_type == "html":
            badge = QLabel("RICH TEXT")
            badge.setStyleSheet("""
                background-color: #7c3aed;
                color: white;
                font-size: 8px;
                font-weight: bold;
                padding: 1px 5px;
                border-radius: 3px;
            """)
        elif payload_type == "files":
            badge = QLabel("FILES")
            badge.setStyleSheet("""
                background-color: #d97706;
                color: white;
                font-size: 8px;
                font-weight: bold;
                padding: 1px 5px;
                border-radius: 3px;
            """)
        elif payload_type == "image":
            badge = QLabel("IMAGE")
            badge.setStyleSheet("""
                background-color: #0891b2;
                color: white;
                font-size: 8px;
                font-weight: bold;
                padding: 1px 5px;
                border-radius: 3px;
            """)
        else:
            badge = None

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedSize(45, 20)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #333;
                border-radius: 3px;
                color: #aaa;
                font-size: 9px;
            }
            QPushButton:hover { background-color: #3a86ff; color: white; }
        """)
        copy_btn.clicked.connect(lambda: self.recopy_requested.emit(text))

        header.addWidget(h_lbl)
        header.addWidget(time_lbl)
        if badge:
            header.addSpacing(4)
            header.addWidget(badge)
        header.addStretch()
        header.addWidget(copy_btn)
        c_layout.addLayout(header)

        # Body content
        if img_pixmap:
            # Thumbnail + size info side by side
            body = QHBoxLayout()
            body.setSpacing(10)

            thumb_lbl = QLabel()
            thumb_lbl.setPixmap(img_pixmap)
            thumb_lbl.setFixedSize(img_pixmap.width(), img_pixmap.height())
            thumb_lbl.setStyleSheet("border: 1px solid #333; border-radius: 4px;")

            info_lbl = QLabel(preview_text)
            info_lbl.setStyleSheet("color: #888; font-size: 10px;")
            info_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            body.addWidget(thumb_lbl)
            body.addWidget(info_lbl)
            body.addStretch()
            c_layout.addLayout(body)
        else:
            p_lbl = QLabel(preview_text)
            p_lbl.setStyleSheet("color: #ddd; font-size: 11px;")
            p_lbl.setWordWrap(True)
            p_lbl.setMinimumHeight(15)
            c_layout.addWidget(p_lbl)

        # Explicit height — card.sizeHint() is unreliable before the widget is shown.
        # Layout margins: top=10, bottom=10 → 20px vertical padding
        # Header row: 28px,  spacing: 6px,  body: thumbnail height or ~28px for text
        _body_h = img_pixmap.height() if img_pixmap else 28
        _card_h = 20 + 28 + 6 + _body_h + 4   # margins + header + spacing + body + buffer
        item.setSizeHint(QSize(0, _card_h))

        self.history_list.insertItem(0, item)
        self.history_list.setItemWidget(item, card)

        if self.history_list.count() > 15:
            self.history_list.takeItem(self.history_list.count() - 1)

    def append_log(self, message, level):
        color = "#00ff00"
        if level >= logging.ERROR: color = "#ff5555"
        elif level >= logging.WARNING: color = "#ffff55"
        elif level <= logging.DEBUG: color = "#5555ff"
            
        self.log_output.appendHtml(f'<span style="color:{color};">{message}</span>')
        self.log_output.moveCursor(QTextCursor.MoveOperation.End)

    def clear_logs(self): self.log_output.clear()

    def export_logs(self):
        try: from shared.utils import get_app_dir
        except ImportError: from utils import get_app_dir
            
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Logs", os.path.join(get_app_dir(), f"dna_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"), "Text Files (*.txt)"
        )
        if file_path:
            try:
                with open(file_path, 'w') as f: f.write(self.log_output.toPlainText())
                QMessageBox.information(self, "Export Successful", f"Logs saved to {file_path}")
            except Exception as e: QMessageBox.critical(self, "Export Failed", f"Could not save logs: {e}")

    def _open_discovery_dialog(self):
        """Open the LAN discovery dialog; populate Server field on selection."""
        dlg = DiscoveryDialog(self)
        dlg.server_selected.connect(self.ip_input.setText)
        dlg.exec()

    def on_pair(self):
        code = self.code_input.text().strip().upper()
        ip = self.ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "Invalid IP", "Please enter a Server IP Address.")
            return
        if len(code) == 6:
            self.paired.emit(code, ip)
        else:
            QMessageBox.warning(self, "Invalid Code", "Please enter a 6-character pairing code.")

    @asyncSlot()
    async def on_generate(self):
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("...")
        ip = self.ip_input.text().strip() or "localhost"
        
        clean_ip = ip
        for proto in ["http://", "https://", "ws://", "wss://"]:
            if clean_ip.startswith(proto): clean_ip = clean_ip[len(proto):]
                
        is_domain = any(c.isalpha() for c in clean_ip.replace("localhost", ""))
        host_with_port = clean_ip if ":" in clean_ip else (clean_ip if is_domain else f"{clean_ip}:8000")
        http_url = f"https://{host_with_port}" if (is_domain and not clean_ip.startswith("127.")) else f"http://{host_with_port}"
        
        loop = asyncio.get_running_loop()
        code = await loop.run_in_executor(None, self._fetch_code, http_url)
        
        self.code_input.setText(code or "".join(os.urandom(3).hex().upper()))
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("Generate")

    def _fetch_code(self, http_url: str) -> str:
        import urllib.request, json
        try:
            req = urllib.request.Request(f"{http_url}/generate-code", headers={'User-Agent': 'DNA-Bridge-Client', 'Bypass-Tunnel-Reminder': 'true'})
            with urllib.request.urlopen(req, timeout=3.0) as res:
                if res.status == 200: return json.loads(res.read().decode()).get("code")
        except Exception: pass
        return None

    def _on_notify_mode_changed(self, index):
        mode = ["normal", "quiet", "large_only"][index]
        self.notification_mode = mode
        self.notification_mode_changed.emit(mode)

    def _on_plain_text_only_clicked(self, checked: bool):
        self.plain_text_only = checked
        self.plain_text_only_changed.emit(checked)

    def show_about_dialog(self):
        AboutDialog(self, is_server=False).exec()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

class SystemTrayApp(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("DNA Bridge")
        self.setIcon(self.create_status_icon("#888"))
        
        self.menu = QMenu()
        self.status_action = QAction("Disconnected", self)
        self.status_action.setEnabled(False)
        self.menu.addAction(self.status_action)
        self.menu.addSeparator()
        self.show_action = QAction("Open DNA Bridge", self)
        self.menu.addAction(self.show_action)
        self.quit_action = QAction("Quit", self)
        self.menu.addAction(self.quit_action)
        self.setContextMenu(self.menu)

    def set_status(self, state: str, code: str = "", latency: int = -1):
        color = "#888"
        text = "Disconnected"
        if state == "connected":
            color = "#4CAF50"
            text = f"Paired: {code}"
            if latency >= 0: text += f" ({latency}ms)"
        elif state == "connecting":
            color = "#FFC107"
            text = "Connecting..."
            
        self.setIcon(self.create_status_icon(color))
        self.status_action.setText(text)
        self.setToolTip(f"DNA Bridge - {text}")

    def create_status_icon(self, color_hex: str):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(12, 12, 40, 40)
        painter.end()
        return QIcon(pixmap)
