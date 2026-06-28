"""
DNA Bridge Client — Entry Point
================================
Root cause of the previous launch crash:
  PyQt6 6.7+ raises a C++ Access Violation (0xC0000005) when a QObject subclass
  is instantiated if any PyQt6 widget modules were imported *before* QApplication
  was created. The fix is to create QApplication first, then import all
  Qt-dependent code lazily inside main().
"""

import sys
import os
import traceback

# ---------------------------------------------------------------------------
# Path setup (must happen before any project imports)
# ---------------------------------------------------------------------------
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ---------------------------------------------------------------------------
# Only stdlib / non-Qt imports at module level.
# All Qt and project-specific imports are deferred inside main() so that
# QApplication is guaranteed to exist before any QObject subclass is defined
# or instantiated.
# ---------------------------------------------------------------------------
import asyncio
import logging
import json


# ---------------------------------------------------------------------------
# Crash logging helper (pure stdlib, no Qt dependency)
# ---------------------------------------------------------------------------

def _write_crash_log(tb_text: str, config_dir: str):
    """Write a crash report to %APPDATA%/DNABridge/crash.log."""
    try:
        os.makedirs(config_dir, exist_ok=True)
        crash_path = os.path.join(config_dir, "crash.log")
        from datetime import datetime
        header = f"\n{'='*60}\nCRASH @ {datetime.now().isoformat()}\n{'='*60}\n"
        with open(crash_path, "a", encoding="utf-8") as f:
            f.write(header + tb_text + "\n")
    except Exception:
        pass  # Never let the crash logger itself crash


# ---------------------------------------------------------------------------
# Config helpers (stdlib only — no Qt)
# ---------------------------------------------------------------------------

def _get_config_dir() -> str:
    """Returns persistent, writeable directory for storing user configuration."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            path = os.path.join(appdata, "DNABridge")
            os.makedirs(path, exist_ok=True)
            return path
    path = os.path.join(os.path.expanduser("~"), ".dnabridge")
    os.makedirs(path, exist_ok=True)
    return path


def _load_config(config_file: str, bundled_config_file: str) -> dict:
    for path in [config_file, bundled_config_file]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
    return {}


_config_cache = None

def _get_config(config_file: str, bundled_config_file: str) -> dict:
    global _config_cache
    if _config_cache is None:
        _config_cache = _load_config(config_file, bundled_config_file)
    return _config_cache


def format_ws_url(ip: str) -> str:
    clean_ip = ip
    scheme = "ws"
    if "://" in clean_ip:
        parsed_scheme = clean_ip.split("://")[0]
        if parsed_scheme in ["http", "ws"]:
            scheme = "ws"
        elif parsed_scheme in ["https", "wss"]:
            scheme = "wss"
        clean_ip = clean_ip.split("://")[1]

    if clean_ip.endswith("/"):
        clean_ip = clean_ip[:-1]

    # Extract host only, ignoring path suffix and port
    host_part = clean_ip.split("/")[0].split(":")[0]
    is_domain = any(c.isalpha() for c in host_part.replace("localhost", ""))

    if is_domain:
        if "://" not in ip:
            scheme = "wss"
        return f"{scheme}://{clean_ip}"
    else:
        if ":" not in clean_ip:
            return f"{scheme}://{clean_ip}:8000"
        else:
            return f"{scheme}://{clean_ip}"


def load_server_ip(config_file: str, bundled_config_file: str) -> str:
    config = _get_config(config_file, bundled_config_file)
    ip = config.get("server_ip")
    if ip:
        return ip
    url = config.get("server_url")
    if url:
        parsed = url.replace("ws://", "").replace("wss://", "").replace("http://", "").replace("https://", "")
        if parsed.endswith("/"):
            parsed = parsed[:-1]
        return parsed
    return "localhost"


def save_server_ip(ip: str, config_file: str, bundled_config_file: str):
    config = _get_config(config_file, bundled_config_file)
    config["server_ip"] = ip
    config["server_url"] = format_ws_url(ip)
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")


def load_notification_mode(config_file: str, bundled_config_file: str) -> str:
    config = _get_config(config_file, bundled_config_file)
    return config.get("notification_mode", "normal")


def save_notification_mode(mode: str, config_file: str, bundled_config_file: str):
    config = _get_config(config_file, bundled_config_file)
    config["notification_mode"] = mode
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")


def load_plain_text_only(config_file: str, bundled_config_file: str) -> bool:
    config = _get_config(config_file, bundled_config_file)
    return bool(config.get("plain_text_only", False))


def save_plain_text_only(value: bool, config_file: str, bundled_config_file: str):
    config = _get_config(config_file, bundled_config_file)
    config["plain_text_only"] = value
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")


# ---------------------------------------------------------------------------
# Entry point — ALL Qt imports are deferred into here
# ---------------------------------------------------------------------------

def main():
    # ── Step 1: QApplication MUST be the very first Qt object created ──────
    # Do NOT import any Qt or project UI code above this point!
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMessageBox
    from PyQt6.QtCore import QObject

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # ── Step 2: Now it's safe to import all Qt-dependent code ─────────────
    try:
        from qasync import QEventLoop, asyncSlot
    except ImportError as e:
        QMessageBox.critical(None, "DNA Bridge — Missing Dependency",
                             f"qasync is not installed:\n{e}\n\nRun: pip install qasync")
        sys.exit(1)

    try:
        from client.ui import SystemTrayApp, ClientMainWindow
        from client.core import ClipboardManager, WebSocketClient
    except ImportError:
        try:
            from ui import SystemTrayApp, ClientMainWindow
            from core import ClipboardManager, WebSocketClient
        except ImportError as e:
            QMessageBox.critical(None, "DNA Bridge — Import Error", str(e))
            sys.exit(1)

    try:
        from shared.logger import setup_logger, QtLogHandler
        from shared.utils import get_app_dir, get_config_dir
    except ImportError:
        try:
            from logger import setup_logger, QtLogHandler
            from utils import get_app_dir, get_config_dir
        except ImportError as e:
            QMessageBox.critical(None, "DNA Bridge — Import Error", str(e))
            sys.exit(1)

    # ── Step 3: Config paths ───────────────────────────────────────────────
    config_dir = get_config_dir()
    app_dir = get_app_dir()
    config_file = os.path.join(config_dir, "config.json")
    bundled_config_file = os.path.join(app_dir, "config.json")

    logger = setup_logger("Client")

    # ── Step 4: Define the application controller (safe now) ──────────────
    class DNABridgeApp(QObject):
        def __init__(self):
            super().__init__()
            self.app = app

            # Load config
            self.server_ip = load_server_ip(config_file, bundled_config_file)
            self.notification_mode = load_notification_mode(config_file, bundled_config_file)
            self.plain_text_only = load_plain_text_only(config_file, bundled_config_file)

            # Build UI
            self.main_window = ClientMainWindow(
                server_ip=self.server_ip,
                notification_mode=self.notification_mode,
                plain_text_only=self.plain_text_only
            )

            # Wire logger to UI
            self.log_handler = QtLogHandler()
            self.log_handler.new_record.connect(self.main_window.append_log)
            logger.addHandler(self.log_handler)

            logger.info("DNA Bridge Client starting up")
            logger.debug(f"Loaded server IP: {self.server_ip}")

            # System tray
            self.tray = SystemTrayApp()
            self.tray.show()

            # Clipboard
            self.clipboard_manager = ClipboardManager(app.clipboard())
            self.clipboard_manager.plain_text_only = self.plain_text_only
            self.ws_client = None
            self.ws_task = None

            # Connect signals
            self.main_window.paired.connect(self.start_ws_client)
            self.main_window.recopy_requested.connect(self.on_recopy_requested)
            self.main_window.notification_mode_changed.connect(self.on_notification_mode_changed)
            self.main_window.plain_text_only_changed.connect(self.on_plain_text_only_changed)
            self.tray.show_action.triggered.connect(self.main_window.showNormal)
            self.tray.show_action.triggered.connect(self.main_window.activateWindow)
            self.tray.quit_action.triggered.connect(self.quit)
            self.tray.activated.connect(self.on_tray_activated)
            self.clipboard_manager.text_changed.connect(self.on_clipboard_changed)

            logger.info("Application UI and Clipboard Manager ready")

        @asyncSlot(str, str)
        async def start_ws_client(self, pairing_code: str, server_ip: str):
            logger.info(f"Initiating pairing with code: {pairing_code} at {server_ip}")
            self.server_ip = server_ip
            save_server_ip(server_ip, config_file, bundled_config_file)

            server_url = format_ws_url(server_ip)

            if self.ws_client:
                logger.debug("Stopping existing WebSocket client")
                try:
                    self.ws_client.message_received.disconnect()
                    self.ws_client.connected.disconnect()
                    self.ws_client.disconnected.disconnect()
                    self.ws_client.latency_updated.disconnect()
                except (TypeError, RuntimeError):
                    pass
                self.ws_client.stop()
                if self.ws_task:
                    self.ws_task.cancel()
                    self.ws_task = None

            self.tray.set_status("connecting")
            self.main_window.set_connection_status("connecting")

            self.ws_client = WebSocketClient(pairing_code, server_url)
            self.ws_client.message_received.connect(self.on_message_received)
            self.ws_client.connected.connect(lambda: self._on_ws_connected(pairing_code))
            self.ws_client.disconnected.connect(self._on_ws_disconnected)
            self.ws_client.latency_updated.connect(
                lambda l: self.tray.set_status("connected", pairing_code, l)
            )

            logger.info(f"Connecting to {server_url}...")
            self.ws_task = asyncio.create_task(self.ws_client.connect())

        def _on_ws_connected(self, code):
            logger.info(f"Successfully connected and paired (Code: {code})")
            self.tray.set_status("connected", code)
            self.main_window.set_connection_status("connected", code)
            self.main_window.hide()
            self.tray.showMessage(
                "DNA Bridge Connected",
                f"Paired successfully with code: {code}",
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )

        def _on_ws_disconnected(self):
            logger.warning("Disconnected from relay server")
            self.tray.set_status("disconnected")
            self.main_window.set_connection_status("disconnected")

        def on_tray_activated(self, reason):
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
                self.main_window.showNormal()
                self.main_window.activateWindow()

        def on_recopy_requested(self, text: str):
            logger.info("Recopy requested from history. Updating local clipboard silently...")
            self.clipboard_manager.update_clipboard(text)

        def on_notification_mode_changed(self, mode: str):
            logger.info(f"Notification mode changed to: {mode}")
            self.notification_mode = mode
            save_notification_mode(mode, config_file, bundled_config_file)

        def on_plain_text_only_changed(self, value: bool):
            logger.info(f"Plain Text Only mode {'enabled' if value else 'disabled'}")
            self.plain_text_only = value
            self.clipboard_manager.plain_text_only = value
            save_plain_text_only(value, config_file, bundled_config_file)

        @asyncSlot(str)
        async def on_clipboard_changed(self, text: str):
            if self.ws_client:
                size_kb = len(text.encode("utf-8")) / 1024
                logger.info(f"Local clipboard change detected ({size_kb:.2f} KB). Syncing...")
                await self.ws_client.send_text(text)
                self.main_window.add_history_item(text, direction="sent")

        def on_message_received(self, text: str):
            size_bytes = len(text.encode("utf-8"))
            size_kb = size_bytes / 1024
            logger.info(f"Incoming clipboard update received ({size_kb:.2f} KB). Updating local...")
            self.clipboard_manager.update_clipboard(text)
            self.main_window.add_history_item(text, direction="received")

            show_notify = True
            if self.notification_mode == "quiet":
                show_notify = False
            elif self.notification_mode == "large_only":
                if size_bytes <= 5 * 1024 * 1024:
                    show_notify = False

            if show_notify:
                self.tray.showMessage(
                    "Clipboard Synced",
                    f"Content updated from another device ({size_kb:.1f} KB).",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000
                )

        def quit(self):
            logger.info("Application shutting down")
            if self.ws_client:
                self.ws_client.stop()
                if self.ws_task:
                    self.ws_task.cancel()
            app.quit()

    # ── Step 5: Run the app inside a crash guard ───────────────────────────
    try:
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)

        dna_app = DNABridgeApp()
        dna_app.main_window.show()

        with loop:
            loop.run_forever()

    except Exception:
        tb_text = traceback.format_exc()
        _write_crash_log(tb_text, _get_config_dir())
        try:
            crash_path = os.path.join(_get_config_dir(), "crash.log")
            QMessageBox.critical(
                None,
                "DNA Bridge — Startup Error",
                f"The application encountered a fatal error and could not start.\n\n"
                f"{tb_text}\n\n"
                f"A crash log has been saved to:\n{crash_path}"
            )
        except Exception:
            print("FATAL:", tb_text, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
