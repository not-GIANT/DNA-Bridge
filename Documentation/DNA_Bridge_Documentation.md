# DNA Bridge — Project Documentation

> *Last updated: 2026-06-15*

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [File Reference](#3-file-reference)
4. [Security Model](#4-security-model)
5. [Bug Fixes Applied This Session](#5-bug-fixes-applied-this-session)
6. [Features Implemented](#6-features-implemented)
7. [Pending Features — Backlog](#7-pending-features--backlog)

---

## 1. Overview

**DNA Bridge** is a cross-device clipboard synchronisation tool for Windows. It lets two or more computers share their clipboards in real time over the internet — text, rich text, images, and files — secured with end-to-end encryption.

### How it works (30-second summary)

1. One device runs the **Server** (acts as a relay + management UI).
2. The server generates a **6-character pairing code** (e.g. `898FE9`).
3. Both devices open the **Client** app, enter the same code, and connect.
4. From that point, anything copied on one device is instantly available to paste on all others in the same session.
5. The relay server only ever sees **encrypted blobs** — it never has access to plaintext clipboard content.

### Tech stack

| Layer | Technology |
|---|---|
| Client UI | Python · PyQt6 · qasync |
| Client networking | `websockets` · asyncio |
| Encryption | `cryptography` (Fernet + PBKDF2HMAC/SHA-256) |
| Relay server | Python · FastAPI · uvicorn |
| LAN Discovery | `zeroconf` (mDNS / Bonjour) |
| Tunnel (optional) | Cloudflare Tunnel (`cloudflared.exe`) |
| Packaging | PyInstaller |

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      RELAY SERVER                           │
│   FastAPI  (/ws/{code})  ·  ConnectionManager               │
│   Broadcasts encrypted blobs to all peers in a session      │
│   GUI: server/gui.py  (PyQt6 management window)             │
│   mDNS: server/mdns.py  (_dnabridge._tcp.local.)            │
└──────────────────────────┬──────────────────────────────────┘
                           │  wss://  (WebSocket, TLS)
            ┌──────────────┴──────────────┐
            │                             │
  ┌─────────▼─────────┐       ┌───────────▼───────────┐
  │   CLIENT A        │       │   CLIENT B            │
  │   client/app.py   │       │   client/app.py       │
  │   client/core.py  │       │   client/core.py      │
  │   client/ui.py    │       │   client/ui.py        │
  │   client/         │       │   client/             │
  │     discovery.py  │       │     discovery.py      │
  └───────────────────┘       └───────────────────────┘
            ↑                             ↑
            └─────── mDNS (LAN) ──────────┘
              auto-discovers server IP/port
```

### Data flow for a clipboard sync

```
Clipboard change detected (ClipboardManager)
  → debounced 300ms (QTimer)
  → _process_clipboard_change()
       ├─ Files?  → zip + base64 encode → {"type":"files", ...}
       ├─ Image?  → PNG bytes + base64  → {"type":"image", ...}
       ├─ HTML?   → html + plain text   → {"type":"html",  ...}
       └─ Text?   → plain string        → {"type":"sync",  ...}
  → Fernet encrypt (key derived from pairing code via PBKDF2)
  → JSON wrap {"type":"sync", "payload": "<ciphertext>"}
  → WebSocket send to relay server
  → Relay broadcasts to all other peers
  → Peer decrypts → writes to local clipboard
```

### Chunked transfer (large payloads)

Payloads > 1 MB are automatically split into numbered chunks and reassembled on the receiver. A background eviction timer discards incomplete assemblies after 60 seconds to prevent unbounded memory growth.

---

## 3. File Reference

| File | Role |
|---|---|
| [`server/main.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/server/main.py) | FastAPI relay server. Manages `ConnectionManager` (session → set of WebSockets), broadcasts messages, enforces 10 MB message size cap, handles ping/pong heartbeat. |
| [`server/gui.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/server/gui.py) | PyQt6 server management window. Runs uvicorn + cloudflared in threads, shows active sessions via a polling `QTimer`, displays system logs. |
| [`client/app.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/app.py) | Entry point for the client. Wires up `ClientMainWindow` (UI) with `WebSocketClient` (core) via Qt signals. Manages `config.json` for persisting server URL and pairing code. |
| [`client/core.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py) | Heart of the client. Contains `ClipboardManager` (detects clipboard changes, debounces, classifies type) and `WebSocketClient` (connects, encrypts/decrypts, sends, receives, reassembles chunks, writes back to clipboard). |
| [`client/ui.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/ui.py) | PyQt6 client window. Shows connection controls, history list with per-type cards (thumbnails, badges), system tray icon, about dialog. |
| [`client/encryption.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/encryption.py) | Thin wrapper around `cryptography.fernet`. Derives a 32-byte key from the pairing code using PBKDF2HMAC (SHA-256, 100 000 iterations). |
| [`shared/utils.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/shared/utils.py) | `get_app_dir()` — resolves bundle vs. dev path. `get_config_dir()` — returns `%APPDATA%\DNABridge` on Windows, `~/.dnabridge` elsewhere, creating it if absent. |
| [`shared/logger.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/shared/logger.py) | Sets up a named `logging.Logger` with a consistent timestamp format, used by both client and server. |
| [`tests/test_sync.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/tests) | End-to-end sync test: spins up the relay, connects two WebSocket clients, sends a message, asserts it is received. Run with `python -m tests.test_sync`. |
| [`dna-bridge.spec`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/dna-bridge.spec) | PyInstaller spec for bundling the client into a single-folder Windows EXE. |

---

## 4. Security Model

| Property | Detail |
|---|---|
| Algorithm | AES-128-CBC + HMAC-SHA256 via **Fernet** |
| Key derivation | **PBKDF2HMAC** · SHA-256 · 100 000 iterations |
| Key material | 6-character pairing code (alphanumeric) |
| Salt | `b'dna-bridge-salt-v1'` *(static — see §7.1 for known weakness)* |
| Relay visibility | Relay only ever receives opaque ciphertext; it cannot read clipboard content |
| Transport | WebSocket over TLS (`wss://`) via Cloudflare Tunnel |

> [!WARNING]
> The hardcoded salt means that an attacker who intercepts enough ciphertext could precompute a lookup table for all ~2.17 × 10⁹ possible 6-character codes. See **§7 — 1.1 Dynamic Salt / PAKE** for the planned fix.

---

## 5. Bug Fixes Applied This Session

### 5.1 Clipboard Debounce Race Condition
**File:** [`client/core.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py)

**Problem:** `ClipboardManager` connected directly to `QClipboard.dataChanged`, which fires multiple times per copy event on Windows (once per MIME type registered). This caused duplicate transmissions and occasional Qt threading crashes.

**Fix:** Replaced the direct signal connection with a persistent `QTimer` set to **300 ms single-shot** mode. Each `dataChanged` signal restarts the timer; the actual processing only runs when the timer fires and the clipboard has been stable for the full debounce window.

---

### 5.2 Unbounded Chunk Reassembly Buffer (Memory Leak)
**File:** [`client/core.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py)

**Problem:** If a chunked transfer was interrupted (network drop, sender crash), the partially assembled chunks stayed in `self.pending_chunks` forever, leaking memory proportional to the number of failed transfers.

**Fix:** Each chunk entry is now stamped with `time.monotonic()` on first arrival. A cleanup pass runs on every new chunk receipt, evicting any assembly that has not completed within **60 seconds**.

---

### 5.3 Config Storage in PyInstaller Temp Directory
**File:** [`shared/utils.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/shared/utils.py) · [`client/app.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/app.py)

**Problem:** When packaged by PyInstaller, `sys._MEIPASS` points to a temporary extraction directory that is wiped on every launch. `config.json` was being written there, causing the app to forget the server URL and pairing code on every restart.

**Fix:** Added `get_config_dir()` to `shared/utils.py`. On Windows it returns `%APPDATA%\DNABridge\` (created automatically if absent). On other platforms it falls back to `~/.dnabridge/`. All config reads and writes in `client/app.py` now route through this function.

---

### 5.4 Connection Failure on IPv6 / New Cloudflare Tunnels
**File:** [`client/core.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py)

**Problem:** A `check_dns()` pre-flight step was resolving the tunnel hostname before attempting the WebSocket connection. New Cloudflare tunnels propagate DNS over IPv6 before IPv4, causing the check to fail and block the connection entirely.

**Fix:** Removed `check_dns()` entirely. The WebSocket library's own connection loop (with exponential back-off retry) handles transient DNS propagation delays gracefully without a separate pre-check.

---

### 5.5 Active Sessions Not Displayed in Server UI
**File:** [`server/gui.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/server/gui.py)

**Problem:** The "Sessions" tab in the server window was empty even when clients were connected.

**Fix:** Replaced the broken static display with a `QListWidget` populated by a `QTimer` polling `manager.active_connections` every **2 seconds**. Each session card shows the pairing code and live device count.

---

### 5.6 History Card Size Glitch (Oversized / Gap)
**File:** [`client/ui.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/ui.py)

**Problem:** `add_history_item` called `card.sizeHint()` before the card widget was attached to the list and rendered. Qt returns a garbage value (`-1 × -1`) at this point; adding the thumbnail height on top produced a massively oversized item slot, creating a large blank gap between the header row and the thumbnail.

**Fix:** Replaced `card.sizeHint()` with a deterministic explicit calculation:
```
height = top_margin(10) + bottom_margin(10) + header_row(28) + spacing(6) + body_height + buffer(4)
```
Where `body_height` = thumbnail pixel height for image cards, or `28` for text/HTML cards.

---

### 5.7 Excel / Office Clipboard Priority Conflict (Text Syncing as Image)
**File:** [`client/core.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py)

**Problem:** Applications in the Microsoft Office suite (Excel, Word, PowerPoint) put a graphical rendering (as a bitmap/metafile) onto the clipboard alongside their main text/HTML content. Because the clipboard manager checked `mime_data.hasImage()` first, copying cells in Excel or paragraphs in Word got matched as an image, converted to a large PNG in the background, and synced as an image instead of text/HTML.

**Fix:** Updated the `hasImage()` check in `_process_clipboard_change` to identify native Office formats (like `XML Spreadsheet`, `Biff12`, `Csv`, `Rich Text Format`) in `mime_data.formats()`. If these formats are present *and* there is actual, non-URL text/HTML content in the clipboard, the manager skips processing the event as an image. This lets the data fall through to the HTML/Text sync path where it is correctly synced as rich or plain text. Real image copies (e.g., from browsers or screenshots) still correctly sync as images.

---

## 6. Features Implemented

> Sections 6.1 and 6.2 were implemented on 2026-06-12.
> Sections 6.3 and 6.4 were implemented on 2026-06-15.

### 6.1 Rich Text / HTML Clipboard Support ✅
**Files:** [`client/core.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py)

Formatting (bold, italics, hyperlinks, colours, tables) is now preserved when copying between devices.

**Sending:** `_process_clipboard_change` checks `mime_data.hasHtml()` before the plain-text fallback. If HTML is present, both representations are packaged together:
```json
{ "type": "html", "content": "plain text fallback", "html": "<b>Hello</b> <i>world</i>" }
```

**Receiving:** A new `elif msg_type == "html":` branch in `update_clipboard` constructs a `QMimeData` with both `setHtml()` and `setText()`, then writes it to the clipboard. Pasting into Word, Outlook, or any rich-text-aware application restores full formatting.

**Priority order** (highest wins):
1. Files (copied from Explorer)
2. Image (raw bitmap / screenshot)
3. **HTML / Rich Text** ← new
4. Plain Text (fallback)

---

### 6.2 Graphical History Preview ✅
**Files:** [`client/ui.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/ui.py)

History cards now show visual previews instead of generic labels.

#### Per-type badges

| Type | Badge | Colour |
|---|---|---|
| Raw image / screenshot | **IMAGE** | Cyan `#0891b2` |
| Rich text / HTML | **RICH TEXT** | Violet `#7c3aed` |
| File transfer | **FILES** | Amber `#d97706` |

#### Image thumbnails — `image` type
The base64 PNG content is decoded into a `QPixmap` scaled to **180 × 100 px max** (aspect-ratio preserved, smooth transform) and rendered in a `QLabel` inside the card, alongside the file size (e.g. `PNG · 420.3 KB`).

#### Image thumbnails — `files` type (images from Explorer)
When the filenames list contains image extensions (`.png .jpg .jpeg .gif .bmp .webp .tiff .ico`), the zip archive embedded in `content` is decoded **in-memory** using `zipfile` + `base64`, the first matching member is extracted as raw bytes, and a thumbnail is rendered identically to the `image` path. Gracefully falls back to a plain filename list if extraction fails.

```
files payload (zip base64)
  → base64.b64decode()
  → zipfile.ZipFile(BytesIO(...))
  → zf.read(first_image_member)
  → QImage.loadFromData()
  → QPixmap.scaled(180, 100, KeepAspectRatio, SmoothTransform)
  → QLabel thumbnail in history card
```

---

### 6.3 Client Launch Hardening ✅
**Files:** [`client/app.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/app.py)

**Problem:** Silent crashes (exit code 1, no visible error) when the app failed to start.

**Fix:**
- `QApplication` is now the very first Qt object created in `main()`, before any code that can throw, ensuring a valid Qt context exists for error dialogs.
- The entire initialization sequence and event loop are wrapped in `try/except Exception`.
- On any unhandled exception:
  1. Full traceback is written to `%APPDATA%\DNABridge\crash.log` (appended, timestamped).
  2. A `QMessageBox.critical()` dialog is shown so the user sees exactly what went wrong instead of a silent exit.
- A `_write_crash_log()` helper is provided for use by other modules if needed.

---

### 6.4 LAN Auto-Discovery via mDNS ✅
**Files:**
- [`server/mdns.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/server/mdns.py) *(new)*
- [`server/main.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/server/main.py)
- [`client/discovery.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/discovery.py) *(new)*
- [`client/ui.py`](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/ui.py)

#### Server — `MDNSAdvertiser` (`server/mdns.py`)

Registers a Bonjour / mDNS service on the local network:

| Field | Value |
|---|---|
| Service type | `_dnabridge._tcp.local.` |
| Instance name | `DNA Bridge @ {hostname}` |
| Port | server's bound HTTP port (reads `DNA_BRIDGE_PORT` env var) |
| TXT record | `version=1`, `path=/ws`, `hostname={hostname}` |

- Resolves **all non-loopback IPv4 addresses** for this machine (uses both DNS lookup and outbound-socket trick as fallback).
- Registration runs in a **daemon thread** — never blocks the FastAPI startup sequence.
- **Thread-safe**: uses a lock to handle `start()`/`stop()` races.
- Integrated into `server/main.py` via FastAPI's `asynccontextmanager` lifespan: service is registered on boot and **cleanly unregistered** on shutdown.
- Gracefully degrades: if `zeroconf` is not installed, logs a warning and continues without mDNS.

#### Client — `MDNSDiscovery` (`client/discovery.py`)

QObject subclass that browses for `_dnabridge._tcp.local.` services:

- Uses `zeroconf.ServiceBrowser` internally (zeroconf manages its own daemon threads).
- Emits **PyQt6 signals** (`server_found`, `server_lost`) so UI updates happen safely on the main thread via Qt's cross-thread signal queuing.
- `DiscoveredServer` dataclass carries `name`, `host`, `port`, `hostname`, and computed `display_name` / `ws_url` properties.
- `start()` / `stop()` are idempotent and thread-safe.
- Gracefully degrades when `zeroconf` is missing.

#### Client UI — `DiscoveryDialog` + **Discover** button (`client/ui.py`)

- A **Discover** button (dark style, 68px wide) is placed inline with the Server input field.
- Clicking it opens `DiscoveryDialog` — a styled modal with:
  - Live-updating list of discovered servers: `🖥  DNA Bridge @ DESKTOP-ABC  —  192.168.1.10:8000`
  - **● Scanning...** → **● N server(s) found** status indicator that turns green when a server is discovered.
  - **Connect to Selected** button (enabled once an item is highlighted); double-click also works.
  - **Refresh** button: stops, clears, and restarts the scan.
  - After **4 seconds**, if exactly one server was found, it is auto-highlighted for quick keyboard confirmation.
  - On close, `MDNSDiscovery` is properly stopped to release Zeroconf resources.
- Selecting a server fills the **Server** field with `host:port` (e.g. `192.168.1.10:8000`) and closes the dialog. The user still enters the pairing code manually — discovery only handles the URL.

#### Workflow

```
Server starts
  → MDNSAdvertiser.start()  [daemon thread]
  → registers _dnabridge._tcp.local. on LAN

Client opens Discovery dialog
  → MDNSDiscovery.start()
  → ServiceBrowser scans LAN
  → server_found emitted  → list populated
  → user double-clicks / clicks Connect
  → ip_input.setText("192.168.1.10:8000")
  → user enters pairing code → Connect & Sync
```

### 7.1 🔐 Dynamic Salt / PAKE Key Exchange
**Priority: High (Security)**

**Problem:** The current PBKDF2 salt is hardcoded (`b'dna-bridge-salt-v1'`). An attacker with enough ciphertext can precompute hashes for all ~2.17 × 10⁹ possible 6-character codes offline.

**Proposed fix (Option A — Dynamic Salt):**
- Server generates a cryptographically secure random salt at pairing code generation time and returns it alongside the code via `GET /generate-code`.
- Clients fetch the salt before key derivation. This eliminates precomputed lookup tables entirely.

**Proposed fix (Option B — PAKE):**
- Implement **SPAKE2** (Password-Authenticated Key Exchange). Neither party ever transmits the raw code; instead, both sides prove knowledge of it and derive a strong shared session key. Immune to passive eavesdropping even on a compromised relay.

---

### 7.2 🌐 LAN Auto-Discovery (mDNS / UDP) ✅ IMPLEMENTED
See **Section 6.4** above.

---

### 7.3 👤 Device Identity / Named Sessions
**Priority: Medium (UX)**

Show human-readable device names instead of anonymous counts.

**Implementation sketch:**
- Client sends `{"type": "hello", "name": socket.gethostname()}` immediately after WebSocket connection.
- Server `ConnectionManager` maps `WebSocket → device_name`.
- Server UI shows: `NETETQ (Office Desktop, MacBook Pro)` instead of `NETETQ (2 devices)`.
- Client history cards show: `Received from Office Desktop` instead of `RECEIVED`.

---

### 7.4 🖱️ Force-Disconnect Sessions (Server Admin Control)
**Priority: Low (Server UX)**

Allow the server operator to manually kick a session.

**Implementation sketch:**
- Add a **"Kick"** button next to each session card in the server's Sessions list.
- Clicking it calls `manager.disconnect()` on all WebSockets matching that pairing code, then removes the session entry.

---

### 7.5 🚀 Auto-Start & Start Minimised
**Priority: Low (UX / Convenience)**

**Auto-start on Windows login:**
- Add/remove a registry key under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` pointing to the EXE.
- Exposed as a checkbox in client/server Preferences.

**Start minimised to tray:**
- Hide `QMainWindow` on startup and skip the `show()` call; rely solely on the system tray icon until the user opens the window manually.

---

## Appendix — Running the Project

```bash
# Install dependencies
pip install -r requirements.txt

# Run the relay server (with GUI)
python server/main.py

# Run the client
python client/app.py

# Run end-to-end sync test
python -m tests.test_sync

# Build Windows EXE
pip install -r requirements-dev.txt
pyinstaller dna-bridge.spec
# → dist/DNA-Bridge/
```

> [!NOTE]
> Config is stored at `%APPDATA%\DNABridge\config.json` on Windows. Delete this file to reset the saved server URL and pairing code.
