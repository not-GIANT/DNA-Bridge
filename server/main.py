from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List, Set
import random
import string
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DNA Bridge Relay Server")

class ConnectionManager:
    def __init__(self):
        # Maps pairing_code -> Set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, pairing_code: str):
        await websocket.accept()
        if pairing_code not in self.active_connections:
            self.active_connections[pairing_code] = set()
        self.active_connections[pairing_code].add(websocket)
        logger.info(f"Device connected to session: {pairing_code}")

    def disconnect(self, websocket: WebSocket, pairing_code: str):
        if pairing_code in self.active_connections:
            self.active_connections[pairing_code].discard(websocket)
            if not self.active_connections[pairing_code]:
                del self.active_connections[pairing_code]
        logger.info(f"Device disconnected from session: {pairing_code}")

    async def broadcast(self, message: str, pairing_code: str, sender: WebSocket):
        if pairing_code in self.active_connections:
            for connection in self.active_connections[pairing_code]:
                if connection != sender:
                    try:
                        await connection.send_text(message)
                    except Exception as e:
                        logger.error(f"Error broadcasting to device: {e}")

manager = ConnectionManager()

@app.get("/generate-code")
async def generate_code():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return {"code": code}

@app.websocket("/ws/{pairing_code}")
async def websocket_endpoint(websocket: WebSocket, pairing_code: str):
    await manager.connect(websocket, pairing_code)
    try:
        while True:
            data = await websocket.receive_text()
            # The data is expected to be encrypted JSON from the client
            await manager.broadcast(data, pairing_code, sender=websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket, pairing_code)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, pairing_code)
if __name__ == "__main__":
    try:
        from server.gui import main as gui_main
    except ImportError:
        from gui import main as gui_main
    gui_main()
