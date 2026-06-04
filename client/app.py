import sys
import asyncio
from qasync import QEventLoop, asyncSlot
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject
try:
    from client.ui import SystemTrayApp, PairingDialog
    from client.core import ClipboardManager, WebSocketClient
except ImportError:
    from ui import SystemTrayApp, PairingDialog
    from core import ClipboardManager, WebSocketClient

import os
import json

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_server_ip() -> str:
    default_ip = "localhost"
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                ip = config.get("server_ip")
                if ip:
                    return ip
                # Fallback to parsing legacy server_url
                url = config.get("server_url")
                if url:
                    parsed = url.replace("ws://", "").replace("wss://", "").replace("http://", "").replace("https://", "")
                    if parsed.endswith("/"):
                        parsed = parsed[:-1]
                    return parsed
        except Exception as e:
            print(f"Error reading config: {e}")
    return default_ip

def save_server_ip(ip: str):
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
        except Exception:
            pass
    config["server_ip"] = ip
    # Maintain server_url for backward compatibility
    clean_ip = ip
    for proto in ["http://", "https://", "ws://", "wss://"]:
        if clean_ip.startswith(proto):
            clean_ip = clean_ip[len(proto):]
    if ":" not in clean_ip:
        ws_url = f"ws://{clean_ip}:8000"
    else:
        ws_url = f"ws://{clean_ip}"
    config["server_url"] = ws_url
    
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")

class DNABridgeApp(QObject):
    def __init__(self, app: QApplication):
        super().__init__()
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        
        self.server_ip = load_server_ip()
        
        self.tray = SystemTrayApp()
        self.tray.show()
        
        self.clipboard_manager = ClipboardManager(self.app.clipboard())
        self.ws_client = None
        self.ws_task = None
        
        # Connect UI actions
        self.tray.pair_action.triggered.connect(self.show_pairing_dialog)
        self.tray.quit_action.triggered.connect(self.quit)
        
        # Clipboard signals
        self.clipboard_manager.text_changed.connect(self.on_clipboard_changed)

    def show_pairing_dialog(self):
        self.dialog = PairingDialog(server_ip=self.server_ip)
        self.dialog.paired.connect(self.start_ws_client)
        self.dialog.show()

    @asyncSlot(str, str)
    async def start_ws_client(self, pairing_code: str, server_ip: str):
        self.server_ip = server_ip
        save_server_ip(server_ip)
        
        # Format connection URL
        clean_ip = server_ip
        for proto in ["http://", "https://", "ws://", "wss://"]:
            if clean_ip.startswith(proto):
                clean_ip = clean_ip[len(proto):]
        if ":" not in clean_ip:
            server_url = f"ws://{clean_ip}:8000"
        else:
            server_url = f"ws://{clean_ip}"

        if self.ws_client:
            try:
                self.ws_client.message_received.disconnect()
                self.ws_client.connected.disconnect()
                self.ws_client.disconnected.disconnect()
            except TypeError:
                pass
            self.ws_client.stop()
            if self.ws_task:
                self.ws_task.cancel()
                self.ws_task = None
            
        self.ws_client = WebSocketClient(pairing_code, server_url)
        self.ws_client.message_received.connect(self.on_message_received)
        self.ws_client.connected.connect(lambda: self.tray.set_connected(True, pairing_code))
        self.ws_client.disconnected.connect(lambda: self.tray.set_connected(False))
        
        # Run the WebSocket client connection task
        self.ws_task = asyncio.create_task(self.ws_client.connect())

    @asyncSlot(str)
    async def on_clipboard_changed(self, text: str):
        if self.ws_client:
            await self.ws_client.send_text(text)

    def on_message_received(self, text: str):
        # When a message comes from another device, update the local clipboard
        self.clipboard_manager.update_clipboard(text)
        self.tray.showMessage(
            "Clipboard Synced",
            "Content updated from another device.",
            self.tray.create_default_icon("green"),
            2000
        )

    def quit(self):
        if self.ws_client:
            self.ws_client.stop()
            if self.ws_task:
                self.ws_task.cancel()
        self.app.quit()

def main():
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    dna_app = DNABridgeApp(app)
    
    # Check if we have a saved pairing code (future feature)
    # For now, just show the dialog on first run
    dna_app.show_pairing_dialog()
    
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
