import json
import asyncio
import websockets
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtGui import QClipboard
try:
    from client.encryption import EncryptionManager
except ImportError:
    from encryption import EncryptionManager

class ClipboardManager(QObject):
    text_changed = pyqtSignal(str)

    def __init__(self, clipboard: QClipboard):
        super().__init__()
        self.clipboard = clipboard
        self.last_text = self.normalize_text(self.clipboard.text())
        self.clipboard.dataChanged.connect(self.on_data_changed)
        
        # Flag to prevent self-collision and loop when updating the clipboard from the server
        self.is_updating_locally = False

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        # Normalize Windows line endings to standard LF
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def on_data_changed(self):
        if self.is_updating_locally:
            return
            
        # Defer clipboard reading by 50ms to allow the source app to release its clipboard lock.
        # This prevents "qt.qpa.mime: Retrying to obtain clipboard" warnings and read failures.
        QTimer.singleShot(50, self._process_clipboard_change)

    def _process_clipboard_change(self):
        # Double check in case we started updating locally during the 50ms window
        if self.is_updating_locally:
            return
            
        text = self.clipboard.text()
        normalized = self.normalize_text(text)
        if not normalized:
            return

        if normalized != self.last_text:
            self.last_text = normalized
            self.text_changed.emit(text)

    def update_clipboard(self, text: str):
        normalized = self.normalize_text(text)
        if normalized == self.last_text:
            return
            
        self.is_updating_locally = True
        self.last_text = normalized
        self.clipboard.setText(text)
        
        # Reset the flag after 150ms to ensure the OS event has passed
        QTimer.singleShot(150, self._reset_local_update_flag)

    def _reset_local_update_flag(self):
        self.is_updating_locally = False

class WebSocketClient(QObject):
    message_received = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, pairing_code: str, server_url: str):
        super().__init__()
        self.pairing_code = pairing_code
        self.server_url = server_url
        self.encryption = EncryptionManager(pairing_code)
        self.websocket = None
        self.is_running = False

    async def connect(self):
        uri = f"{self.server_url}/ws/{self.pairing_code}"
        self.is_running = True
        retry_delay = 1
        while self.is_running:
            try:
                self.websocket = None
                async with websockets.connect(uri) as websocket:
                    self.websocket = websocket
                    retry_delay = 1 # Reset backoff on successful connection
                    self.connected.emit()
                    while self.is_running:
                        message = await websocket.recv()
                        decrypted = self.encryption.decrypt(message)
                        if decrypted:
                            self.message_received.emit(decrypted)
            except asyncio.CancelledError:
                self.is_running = False
                self.websocket = None
                self.disconnected.emit()
                break
            except Exception as e:
                self.websocket = None
                self.disconnected.emit()
                print(f"WebSocket Connection Error: {e}")
                try:
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)
                except asyncio.CancelledError:
                    self.is_running = False
                    break

    async def send_text(self, text: str):
        # Version-safe check for connection openness
        is_open = False
        if self.websocket:
            if hasattr(self.websocket, 'open'):
                is_open = self.websocket.open
            elif hasattr(self.websocket, 'state'):
                from websockets.protocol import State
                is_open = self.websocket.state is State.OPEN
            else:
                is_open = True

        if is_open:
            encrypted = self.encryption.encrypt(text)
            try:
                await self.websocket.send(encrypted)
            except Exception as e:
                print(f"Error sending message: {e}")
                self.websocket = None
        else:
            print("WebSocket is not connected. Message not sent.")

    def stop(self):
        self.is_running = False
