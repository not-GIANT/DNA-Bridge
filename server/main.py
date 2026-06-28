from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import random
import string
import json
import logging
import os
import sys

# Add project root to sys.path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from shared.logger import setup_logger
except ImportError:
    from logger import setup_logger

try:
    from server.mdns import MDNSAdvertiser
except ImportError:
    from mdns import MDNSAdvertiser

logger = setup_logger("Server")

# ---------------------------------------------------------------------------
# mDNS advertiser — shared instance, lifetime managed by FastAPI lifespan
# ---------------------------------------------------------------------------
_mdns_advertiser: MDNSAdvertiser | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """FastAPI lifespan handler: start mDNS on boot, stop it on shutdown."""
    global _mdns_advertiser

    # Determine the port the server is running on from env (uvicorn sets this
    # via --port; default to 8000).
    port = int(os.environ.get("DNA_BRIDGE_PORT", 8000))

    _mdns_advertiser = MDNSAdvertiser(port=port)
    _mdns_advertiser.start()

    yield  # Application is running

    # Clean shutdown
    if _mdns_advertiser:
        _mdns_advertiser.stop()
        _mdns_advertiser = None


app = FastAPI(title="DNA Bridge Relay Server", lifespan=lifespan)


import threading

class ConnectionManager:
    def __init__(self):
        # Maps pairing_code -> Set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.lock = threading.Lock()

    async def connect(self, websocket: WebSocket, pairing_code: str):
        await websocket.accept()
        with self.lock:
            if pairing_code not in self.active_connections:
                self.active_connections[pairing_code] = set()
            self.active_connections[pairing_code].add(websocket)
        logger.info(f"New connection to session: {pairing_code} (Active: {len(self.active_connections[pairing_code])})")

    def disconnect(self, websocket: WebSocket, pairing_code: str):
        with self.lock:
            if pairing_code in self.active_connections:
                self.active_connections[pairing_code].discard(websocket)
                if not self.active_connections[pairing_code]:
                    del self.active_connections[pairing_code]
                    logger.debug(f"Session {pairing_code} closed (no active devices)")
                else:
                    logger.info(f"Device disconnected from {pairing_code} (Remaining: {len(self.active_connections[pairing_code])})")

    async def broadcast(self, message: str, pairing_code: str, sender: WebSocket):
        with self.lock:
            connections = list(self.active_connections.get(pairing_code, []))
            
        if connections:
            count = 0
            dead_connections = []
            for connection in connections:
                if connection != sender:
                    try:
                        await connection.send_text(message)
                        count += 1
                    except Exception as e:
                        logger.error(f"Error broadcasting to device in {pairing_code}: {e}")
                        dead_connections.append(connection)
            
            if dead_connections:
                for dead in dead_connections:
                    self.disconnect(dead, pairing_code)
                
            if count > 0:
                logger.debug(f"Broadcasted encrypted payload to {count} devices in session {pairing_code}")

    def get_active_sessions(self) -> list:
        with self.lock:
            return [(code, list(conns)) for code, conns in self.active_connections.items()]

manager = ConnectionManager()

# Maximum allowed WebSocket message size (10MB) to allow for 5MB payload + E2EE/JSON overhead
MAX_MESSAGE_SIZE = 10 * 1024 * 1024

@app.get("/generate-code")
async def generate_code():
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    logger.info(f"Generated new pairing code: {code}")
    return {"code": code}

@app.websocket("/ws/{pairing_code}")
async def websocket_endpoint(websocket: WebSocket, pairing_code: str):
    await manager.connect(websocket, pairing_code)
    try:
        while True:
            data = await websocket.receive_text()
            
            # Enforcement of maximum message size
            if len(data) > MAX_MESSAGE_SIZE:
                logger.warning(f"Rejected oversized message from {pairing_code} ({len(data)/1024/1024:.2f} MB)")
                continue

            try:
                # Expecting JSON protocol: {"type": "sync|chunk|ping", ...}
                message = json.loads(data)
                msg_type = message.get("type")
                
                if msg_type == "ping":
                    # Echo back a pong for heartbeat/latency checks
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "time": message.get("time")
                    }))
                else:
                    # Broadcast sync and chunk messages to all other peers
                    await manager.broadcast(data, pairing_code, sender=websocket)
            except json.JSONDecodeError:
                # Fallback for legacy clients sending raw strings (not recommended)
                await manager.broadcast(data, pairing_code, sender=websocket)
            except Exception as e:
                logger.error(f"Error processing message from {pairing_code}: {e}")
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, pairing_code)
    except Exception as e:
        logger.error(f"WebSocket session error ({pairing_code}): {e}")
        manager.disconnect(websocket, pairing_code)

if __name__ == "__main__":
    try:
        from server.gui import main as gui_main
    except ImportError:
        from gui import main as gui_main
    gui_main()
