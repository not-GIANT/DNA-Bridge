import json
import asyncio
import websockets
import logging
import socket
import uuid
import time
import base64
import hashlib
import zipfile
import io
import os
import shutil
import sys
from typing import Dict, List
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QBuffer, QByteArray, QIODevice, QUrl, QMimeData
from PyQt6.QtGui import QClipboard, QImage

logger = logging.getLogger("Client")

# Maximum size for a single sync (5MB).
# This prevents accidental memory exhaustion when copying large folders or images.
MAX_SYNC_SIZE = 5 * 1024 * 1024 

try:
    from websockets.protocol import State as WS_State        # websockets < 11
except ImportError:
    try:
        from websockets.connection import State as WS_State  # websockets ≥ 11
    except ImportError:
        WS_State = None

def get_total_size(paths: List[str]) -> int:
    """Calculates the total size of all files and folders in the list."""
    total = 0
    for path in paths:
        try:
            if os.path.isfile(path):
                total += os.path.getsize(path)
            elif os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        total += os.path.getsize(os.path.join(root, file))
        except Exception as e:
            logger.debug(f"Error getting size for {path}: {e}")
    return total

def create_zip_archive(paths: List[str]) -> str:
    logger.debug(f"Creating zip archive for paths: {paths}")
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for path in paths:
            if os.path.isfile(path):
                logger.debug(f"Zipping file: {path}")
                zip_file.write(path, os.path.basename(path))
            elif os.path.isdir(path):
                logger.debug(f"Zipping directory: {path}")
                for root, dirs, files in os.walk(path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        rel_path = os.path.relpath(file_path, os.path.dirname(path))
                        zip_file.write(file_path, rel_path)
    zip_bytes = zip_buffer.getvalue()
    logger.debug(f"Zip created. Raw size: {len(zip_bytes)} bytes")
    return base64.b64encode(zip_bytes).decode("utf-8")

def extract_zip_archive(zip_base64: str, target_dir: str) -> List[str]:
    try:
        zip_bytes = base64.b64decode(zip_base64.encode("utf-8"))
        zip_buffer = io.BytesIO(zip_bytes)
        logger.debug(f"Decoding zip archive ({len(zip_bytes)} bytes)...")
    except Exception as e:
        logger.error(f"Failed to decode zip base64: {e}")
        return []
    
    extracted_paths = []
    try:
        with zipfile.ZipFile(zip_buffer, "r") as zip_file:
            members = zip_file.infolist()
            logger.debug(f"Zip contains {len(members)} items")
            
            norm_target_dir = os.path.normcase(os.path.abspath(target_dir))
            
            for member in members:
                filename = os.path.basename(member.filename)
                if not filename and member.is_dir():
                    continue
                    
                target_path = os.path.abspath(os.path.join(target_dir, member.filename))
                norm_target_path = os.path.normcase(target_path)
                
                # Prevent directory traversal attacks
                if not norm_target_path.startswith(norm_target_dir):
                    logger.warning(f"Blocked suspicious file path in zip: {member.filename}")
                    continue
                    
                try:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zip_file.open(member) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    extracted_paths.append(target_path)
                    logger.debug(f"Extracted: {member.filename}")
                except Exception as e:
                    logger.error(f"Failed to extract {member.filename}: {e}")
    except zipfile.BadZipFile:
        logger.error("Failed to extract: Incoming data is not a valid ZIP archive")
    except Exception as e:
        logger.error(f"Zip extraction error: {e}")
        
    return extracted_paths
            
try:
    from client.encryption import EncryptionManager
except ImportError:
    from encryption import EncryptionManager

class ClipboardManager(QObject):
    text_changed = pyqtSignal(str)

    def __init__(self, clipboard: QClipboard):
        super().__init__()
        self.clipboard = clipboard
        self.clipboard.dataChanged.connect(self.on_data_changed)
        
        # Flag to prevent self-collision and loop when updating the clipboard from the server
        self.is_updating_locally = False
        
        # When True, strip HTML/rich-text metadata and sync only plain text
        # This prevents Excel and other apps from auto-converting pasted content into hyperlinks
        self.plain_text_only = False
        
        # Hash of the last sent/received payload to prevent loop duplicates across all data types
        self.last_payload_hash = ""
        
        # Initialize last payload hash from current clipboard content if possible
        try:
            mime = self.clipboard.mimeData()
            if mime.hasText():
                text = self.normalize_text(self.clipboard.text())
                if text:
                    self.last_payload_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        except Exception:
            pass
        
        # Use a persistent timer to avoid race conditions with multiple rapid local updates
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._reset_local_update_flag)

        # Debounce timer to avoid multiple rapid clipboard reads/spawns
        self.debounce_timer = QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self._process_clipboard_change)

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
        self.debounce_timer.stop()
        self.debounce_timer.start(50)

    def _process_clipboard_change(self):
        # Double check in case we started updating locally during the 50ms window
        if self.is_updating_locally:
            return
            
        mime_data = self.clipboard.mimeData()
        
        # 1. Check if the clipboard contains file/directory URLs (documents)
        if mime_data.hasUrls():
            urls = mime_data.urls()
            paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            if paths:
                logger.debug(f"Detected {len(paths)} local file(s) on clipboard")
                asyncio.create_task(self._process_files_async(paths))
                return
                
        # 2. Check if the clipboard contains an Image
        if mime_data.hasImage():
            # Check if this is an office/document copy that has both text and image, 
            # where we want to prioritize the text/HTML representation instead of the image.
            is_office_doc = False
            for fmt in mime_data.formats():
                fmt_lower = fmt.lower()
                if "csv" in fmt_lower or "spreadsheet" in fmt_lower or "biff" in fmt_lower or "rich text" in fmt_lower:
                    is_office_doc = True
                    break

            has_text_content = False
            if mime_data.hasText() or mime_data.hasHtml():
                text_val = mime_data.text() if mime_data.hasText() else ""
                if text_val and text_val.strip():
                    # If it's just a URL (typical of copied images in browsers), keep image priority.
                    # Otherwise, prioritize the text/HTML representation.
                    text_strip = text_val.strip()
                    is_url = text_strip.startswith(("http://", "https://", "file://", "data:"))
                    if not is_url:
                        has_text_content = True

            if not (is_office_doc and has_text_content):
                image = self.clipboard.image()
                if isinstance(image, QImage) and not image.isNull():
                    logger.debug("Detected image data on clipboard")
                    asyncio.create_task(self._process_image_async(image))
                    return
                
        # 3. Check if clipboard contains rich text / HTML
        if mime_data.hasHtml() and not self.plain_text_only:
            html = mime_data.html()
            text = mime_data.text()
            normalized = self.normalize_text(text)
            if html and normalized:
                payload = json.dumps({
                    "type": "html",
                    "content": normalized,
                    "html": html
                })
                payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                if payload_hash != self.last_payload_hash:
                    self.last_payload_hash = payload_hash
                    logger.debug(f"Detected rich text change on clipboard ({len(html)} chars HTML)")
                    self.text_changed.emit(payload)
                    return

        # 4. Check if the clipboard contains plain text
        text = self.clipboard.text()
        normalized = self.normalize_text(text)
        if not normalized:
            return
            
        payload_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if payload_hash != self.last_payload_hash:
            self.last_payload_hash = payload_hash
            logger.debug(f"Detected text change on clipboard ({len(normalized)} chars)")
            # Plain text is emitted as raw legacy string for perfect backward compatibility
            self.text_changed.emit(normalized)

    async def _process_files_async(self, paths: List[str]):
        try:
            # Check size before zipping to avoid wasted CPU/Memory
            loop = asyncio.get_running_loop()
            total_size = await loop.run_in_executor(None, get_total_size, paths)
            
            if total_size > MAX_SYNC_SIZE:
                logger.warning(f"File sync aborted: Total size ({total_size/1024/1024:.1f} MB) exceeds 5MB limit.")
                return

            logger.info(f"Zipping {len(paths)} local file(s)/folder(s) in background...")
            zip_base64 = await loop.run_in_executor(None, create_zip_archive, paths)
            
            # Construct structured JSON payload
            filenames = [os.path.basename(p) for p in paths]
            payload = json.dumps({
                "type": "files",
                "content": zip_base64,
                "filenames": filenames
            })
            
            payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if payload_hash != self.last_payload_hash:
                self.last_payload_hash = payload_hash
                logger.info(f"Local files zipped and encrypted (Size: {len(payload)/1024:.2f} KB). Syncing...")
                self.text_changed.emit(payload)
        except Exception as e:
            logger.error(f"Error compressing files: {e}")

    async def _process_image_async(self, image: QImage):
        try:
            logger.info("Converting local image to PNG base64 in background...")
            # Save QImage to byte buffer
            ba = QByteArray()
            buffer = QBuffer(ba)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            image.save(buffer, "PNG")
            img_bytes = ba.data()
            
            if len(img_bytes) > MAX_SYNC_SIZE:
                logger.warning(f"Image sync aborted: Size ({len(img_bytes)/1024/1024:.1f} MB) exceeds 5MB limit.")
                return

            loop = asyncio.get_running_loop()
            img_base64 = await loop.run_in_executor(None, lambda: base64.b64encode(img_bytes).decode("utf-8"))
            
            # Construct structured JSON payload
            payload = json.dumps({
                "type": "image",
                "content": img_base64
            })
            
            payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if payload_hash != self.last_payload_hash:
                self.last_payload_hash = payload_hash
                logger.info(f"Local image converted to PNG (Size: {len(payload)/1024:.2f} KB). Syncing...")
                self.text_changed.emit(payload)
        except Exception as e:
            logger.error(f"Error processing image: {e}")

    def update_clipboard(self, payload: str):
        # Prevent loop processing if incoming payload matches our last payload
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if payload_hash == self.last_payload_hash:
            return
            
        # Parse payload format
        try:
            data = json.loads(payload)
            if isinstance(data, dict) and "type" in data:
                msg_type = data.get("type")
                content = data.get("content", "")
                
                if msg_type == "image":
                    ba = QByteArray.fromBase64(content.encode("utf-8"))
                    image = QImage()
                    image.loadFromData(ba, "PNG")
                    if not image.isNull():
                        logger.info("Writing incoming image to clipboard...")
                        self.is_updating_locally = True
                        self.last_payload_hash = payload_hash
                        self.clipboard.setImage(image)
                        self.update_timer.start(150)
                    else:
                        logger.error("Failed to load QImage from incoming data")

                elif msg_type == "html":
                    if self.plain_text_only:
                        # Strip all HTML/rich text — write only plain text to clipboard
                        logger.info("Plain Text Only mode: stripping HTML from incoming rich text")
                        if content:
                            self.is_updating_locally = True
                            self.last_payload_hash = payload_hash
                            self.clipboard.setText(content)
                            self.update_timer.start(150)
                    else:
                        logger.info("Writing incoming rich text to clipboard...")
                        html = data.get("html", "")
                        mime = QMimeData()
                        if html:
                            mime.setHtml(html)
                        if content:
                            mime.setText(content)
                        self.is_updating_locally = True
                        self.last_payload_hash = payload_hash
                        self.clipboard.setMimeData(mime)
                        self.update_timer.start(150)
                    
                elif msg_type == "files":
                    # Extraction is CPU/IO intensive, offload it to background task
                    logger.info("Extracting incoming files in background...")
                    self.is_updating_locally = True
                    self.last_payload_hash = payload_hash
                    asyncio.create_task(self._extract_files_async(content))
                    # Note: We do NOT start self.update_timer here; it is started inside the async task
                    # after the extraction completes and the local clipboard write is done.
                    
                else:
                    # Fallback text
                    if content:
                        self.is_updating_locally = True
                        self.last_payload_hash = payload_hash
                        self.clipboard.setText(content)
                        self.update_timer.start(150)
            else:
                self.is_updating_locally = True
                self.last_payload_hash = payload_hash
                self.clipboard.setText(payload)
                self.update_timer.start(150)
        except Exception:
            # Not JSON, treat as raw plaintext (legacy client support)
            self.is_updating_locally = True
            self.last_payload_hash = payload_hash
            self.clipboard.setText(payload)
            self.update_timer.start(150)

    async def _extract_files_async(self, zip_base64: str):
        try:
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads", "DNA-Bridge")
            os.makedirs(downloads_dir, exist_ok=True)
            
            loop = asyncio.get_running_loop()
            extracted_paths = await loop.run_in_executor(None, extract_zip_archive, zip_base64, downloads_dir)
            
            if extracted_paths:
                logger.info(f"Extracted {len(extracted_paths)} files to {downloads_dir}. Updating clipboard URLs...")
                urls = [QUrl.fromLocalFile(p) for p in extracted_paths]
                mime = QMimeData()
                mime.setUrls(urls)
                
                # Write to local clipboard without triggering outgoing loop
                self.is_updating_locally = True
                self.clipboard.setMimeData(mime)
                self.update_timer.start(150)
            else:
                logger.warning("No files were extracted from archive")
                self.is_updating_locally = False
        except Exception as e:
            logger.error(f"Error extracting incoming files: {e}")
            self.is_updating_locally = False

    def _reset_local_update_flag(self):
        self.is_updating_locally = False

class WebSocketClient(QObject):
    message_received = pyqtSignal(str)
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    latency_updated = pyqtSignal(int) # latency in ms

    def __init__(self, pairing_code: str, server_url: str):
        super().__init__()
        self.pairing_code = pairing_code
        self.server_url = server_url
        self.encryption = EncryptionManager(pairing_code)
        self.websocket = None
        self.is_running = False
        self.is_connected = False
        
        # Chunk reassembly buffer: { chunk_id: {index: data} }
        self.chunk_buffer: Dict[str, Dict[int, str]] = {}
        # Timestamps for each chunk buffer to prevent memory leaks: { chunk_id: timestamp }
        self.chunk_timestamps: Dict[str, float] = {}
        self.heartbeat_task = None


    async def connect(self):
        # Ensure clean URI
        clean_url = self.server_url.strip()
        if clean_url.endswith("/"):
            clean_url = clean_url[:-1]
        
        uri = f"{clean_url}/ws/{self.pairing_code.strip()}"
        
        # Extract hostname for DNS pre-check
        hostname = uri.split("://")[-1].split(":")[0].split("/")[0]
        
        self.is_running = True
        retry_delay = 1
        ssl_verify = True
        
        # Headers to bypass tunnel landing pages (Cloudflare/Localtunnel) and identify the client
        headers = {
            "bypass-tunnel-reminder": "true",
            "User-Agent": "DNA-Bridge-Client/1.0"
        }

        while self.is_running:
            try:
                self.websocket = None
                
                # Setup fresh connection arguments for each attempt
                connect_kwargs = {
                    "additional_headers": headers,
                    "max_size": 10 * 1024 * 1024, # 10MB
                    "ping_timeout": 60,
                    "ping_interval": 20,
                    "open_timeout": 30, # Increased from default 10s to handle tunnel latency
                }

                import ssl
                import sys
                if uri.startswith("wss://"):
                    if ssl_verify:
                        ssl_context = ssl.create_default_context()
                        
                        # Try to load certifi certificates
                        try:
                            import certifi
                            ssl_context.load_verify_locations(cafile=certifi.where())
                        except Exception as e:
                            logger.debug(f"Failed to load certifi: {e}")
                            
                        # If on Windows, also load system certificates from CA and ROOT stores.
                        # This ensures that corporate proxies or updated system CAs are trusted.
                        if sys.platform == "win32":
                            for store in ["CA", "ROOT"]:
                                try:
                                    for cert, encoding, trust in ssl.enum_certificates(store):
                                        if encoding == "x509_asn":
                                            ssl_context.load_verify_locations(cadata=cert)
                                except Exception as e:
                                    logger.debug(f"Failed to load Windows system certs from {store}: {e}")
                    else:
                        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                        ssl_context.check_hostname = False
                        ssl_context.verify_mode = ssl.CERT_NONE
                        
                    connect_kwargs["ssl"] = ssl_context

                logger.info(f"Connecting to {uri}...")
                
                try:
                    async with websockets.connect(uri, **connect_kwargs) as websocket:
                        self.websocket = websocket
                        retry_delay = 1
                        self.is_connected = True
                        self.connected.emit()
                        
                        # Start heartbeat task (cancel previous if exists)
                        if self.heartbeat_task:
                            self.heartbeat_task.cancel()
                        self.heartbeat_task = asyncio.create_task(self._heartbeat())
                        
                        while self.is_running:
                            raw_message = await websocket.recv()
                            try:
                                message = json.loads(raw_message)
                                msg_type = message.get("type")
                                
                                if msg_type == "sync":
                                    payload = message.get("payload")
                                    loop = asyncio.get_running_loop()
                                    decrypted = await loop.run_in_executor(None, self.encryption.decrypt, payload)
                                    if decrypted:
                                        self.message_received.emit(decrypted)
                                
                                elif msg_type == "chunk":
                                    chunk_id = message.get("id")
                                    index = message.get("index")
                                    total = message.get("total")
                                    data = message.get("data")
                                    
                                    if chunk_id not in self.chunk_buffer:
                                        self.chunk_buffer[chunk_id] = {}
                                        self.chunk_timestamps[chunk_id] = time.time()
                                    
                                    self.chunk_buffer[chunk_id][index] = data
                                    
                                    if len(self.chunk_buffer[chunk_id]) == total:
                                        # All chunks received, reassemble in a background thread to prevent UI freezing
                                        logger.info(f"Reassembling {total} chunks for payload {chunk_id}")
                                        
                                        loop = asyncio.get_running_loop()
                                        chunks_dict = self.chunk_buffer[chunk_id]
                                        del self.chunk_buffer[chunk_id]
                                        if chunk_id in self.chunk_timestamps:
                                            del self.chunk_timestamps[chunk_id]
                                        
                                        def reassemble_and_decrypt(chunks, total_count):
                                            full = "".join(chunks[i] for i in range(total_count))
                                            return self.encryption.decrypt(full)
                                            
                                        decrypted = await loop.run_in_executor(None, reassemble_and_decrypt, chunks_dict, total)
                                        if decrypted:
                                            self.message_received.emit(decrypted)
                                
                                elif msg_type == "pong":
                                    latency = int((time.time() - message.get("time")) * 1000)
                                    self.latency_updated.emit(latency)
                                    
                            except json.JSONDecodeError:
                                # Fallback for legacy raw strings
                                loop = asyncio.get_running_loop()
                                decrypted = await loop.run_in_executor(None, self.encryption.decrypt, raw_message)
                                if decrypted:
                                    self.message_received.emit(decrypted)
                            except Exception as e:
                                logger.error(f"Error processing incoming message: {e}")
                except TypeError as e:
                    if "additional_headers" in str(e):
                        # Fallback for older websockets versions
                        connect_kwargs["extra_headers"] = connect_kwargs.pop("additional_headers")
                        logger.debug("Retrying with extra_headers for legacy websockets compatibility")
                        continue
                    raise e

            except asyncio.CancelledError:
                self.is_running = False
                self.websocket = None
                self.chunk_buffer = {}
                self.chunk_timestamps = {}
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                    self.heartbeat_task = None
                if self.is_connected:
                    self.is_connected = False
                    self.disconnected.emit()
                break
            except Exception as e:
                self.websocket = None
                self.chunk_buffer = {}
                self.chunk_timestamps = {}
                if self.heartbeat_task:
                    self.heartbeat_task.cancel()
                    self.heartbeat_task = None
                if self.is_connected:
                    self.is_connected = False
                    self.disconnected.emit()
                
                error_msg = str(e)
                # Check for SSL verification error and perform fallback
                if "CERTIFICATE_VERIFY_FAILED" in error_msg or "certificate verify failed" in error_msg:
                    logger.warning("SSL Certificate Verification failed. Falling back to connection with SSL verification disabled (E2EE remains active)...")
                    ssl_verify = False
                    continue

                # More descriptive error logging
                if "timed out" in error_msg.lower():
                    logger.error(f"Handshake Timeout: The server at {self.server_url} is too slow or unreachable.")
                else:
                    logger.error(f"WebSocket Connection Error: {e}")
                
                try:
                    logger.info(f"Retrying connection in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 30)
                except asyncio.CancelledError:
                    self.is_running = False
                    break

    async def _heartbeat(self):
        """Sends periodic pings to the server to measure latency and keep connection alive."""
        while self.is_connected:
            try:
                # Evict chunks older than 30 seconds to prevent resource leak
                now = time.time()
                stale_ids = [cid for cid, t in list(self.chunk_timestamps.items()) if now - t > 30.0]
                for cid in stale_ids:
                    logger.warning(f"Evicting stale incomplete chunk buffer for payload {cid}")
                    if cid in self.chunk_buffer:
                        del self.chunk_buffer[cid]
                    if cid in self.chunk_timestamps:
                        del self.chunk_timestamps[cid]

                if self.websocket:
                    await self.websocket.send(json.dumps({
                        "type": "ping",
                        "time": time.time()
                    }))
                await asyncio.sleep(15) # Ping every 15 seconds
            except Exception:
                break

    async def send_text(self, text: str):
        is_open = False
        ws = self.websocket
        if ws:
            if WS_State is not None and hasattr(ws, 'state'):
                is_open = ws.state is WS_State.OPEN
            elif hasattr(ws, 'open'):
                is_open = ws.open
            else:
                is_open = True

        if not is_open:
            logger.warning("WebSocket is not connected. Sync aborted.")
            return

        # Offload CPU-bound encryption to a background thread to keep the GUI responsive
        loop = asyncio.get_running_loop()
        encrypted = await loop.run_in_executor(None, self.encryption.encrypt, text)
        if not encrypted:
            return

        try:
            # If payload is larger than 1MB, use chunking
            CHUNK_SIZE = 512 * 1024 # 512KB
            if len(encrypted) > 1024 * 1024:
                chunk_id = str(uuid.uuid4())
                total_chunks = (len(encrypted) + CHUNK_SIZE - 1) // CHUNK_SIZE
                logger.info(f"Sending large payload in {total_chunks} chunks (ID: {chunk_id})")
                
                for i in range(total_chunks):
                    start = i * CHUNK_SIZE
                    end = start + CHUNK_SIZE
                    chunk_data = encrypted[start:end]
                    
                    await self.websocket.send(json.dumps({
                        "type": "chunk",
                        "id": chunk_id,
                        "index": i,
                        "total": total_chunks,
                        "data": chunk_data
                    }))
            else:
                # Normal sync message
                await self.websocket.send(json.dumps({
                    "type": "sync",
                    "payload": encrypted
                }))
            logger.debug("Clipboard data sent successfully")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            self.websocket = None

    def stop(self):
        self.is_running = False
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            self.heartbeat_task = None
        self.chunk_buffer = {}
        self.chunk_timestamps = {}
