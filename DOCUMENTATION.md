# DNA Bridge - Comprehensive Technical Documentation

DNA Bridge is a lightweight, high-performance Windows clipboard synchronization suite designed to securely sync text clipboard contents between multiple computers. It is built using Python, FastAPI (Server), and PyQt6 (Client), featuring end-to-end encryption (E2EE) and system tray operations.

---

## 1. System Architecture & Component Interactions

DNA Bridge utilizes a star topology where multiple client nodes pair via a transient 6-character code, communicating through a stateless WebSocket relay server.

```mermaid
graph TD
    subgraph Machine A (Client)
        A_Clip[System Clipboard] <-->|Monitor / Write| A_Mgr[Clipboard Manager]
        A_Mgr <-->|Signal| A_App[DNABridgeApp]
        A_App <-->|Encrypt / Decrypt| A_Enc[Encryption Manager]
        A_App <-->|Async WSS| A_WS[WebSocket Client]
    end

    subgraph Relay Server
        S_WS[WebSocket Endpoint /ws/code] <-->|Group Broadcast| S_Mgr[Connection Manager]
        S_API[/generate-code API]
    end

    subgraph Machine B (Client)
        B_WS[WebSocket Client] <-->|Async WSS| B_App[DNABridgeApp]
        B_App <-->|Encrypt / Decrypt| B_Enc[Encryption Manager]
        B_Mgr[Clipboard Manager] <-->|Signal| B_App
        B_Mgr <-->|Monitor / Write| B_Clip[System Clipboard]
    end

    A_WS <-->|Secure Channel| S_WS
    B_WS <-->|Secure Channel| S_WS
```

### 1.1 Communication Sequence
1. **Pairing**: Clients launch and prompt the user for the Server IP and a 6-character Pairing Code.
2. **Key Derivation**: The client derives a 256-bit AES key from the pairing code using PBKDF2HMAC (for E2EE).
3. **Clipboard Change (Sender)**:
   - User copies text on Machine A.
   - [ClipboardManager](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py#L11) detects the change after a 50ms lock-release deferral.
   - The plain text is encrypted into a Fernet token.
   - The token is transmitted via WebSocket connection to `/ws/{pairing_code}`.
4. **Relay Routing**:
   - The Relay Server receives the ciphertext.
   - [ConnectionManager](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/server/main.py#L13) broadcasts the ciphertext to all active connections matching the pairing code, excluding the sender.
5. **Clipboard Change (Receiver)**:
   - Machine B receives the ciphertext.
   - It decrypts it locally using the derived key.
   - [ClipboardManager](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py#L11) updates the local system clipboard while temporarily ignoring incoming OS change notifications to prevent loops.

---

## 2. Client Application Details

The client application integrates native Windows system tray support and non-blocking event loops.

- **Entrypoint**: [client/app.py](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/app.py)
- **UI Windows**: [client/ui.py](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/ui.py)
- **Core Logistics**: [client/core.py](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py)
- **E2EE Cryptography**: [client/encryption.py](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/encryption.py)

### 2.1 Configuration and Server IP Input
Users can configure the server target directly in the GUI:
- **Server IP Field**: [PairingDialog](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/ui.py#L9) features a "Server IP Address" field.
- **Persistence**: Settings are written to and loaded from `client/config.json`. The application auto-loads the previously configured IP on startup.
- **Protocol Resolution**: The input field accepts raw IPs (e.g. `192.168.1.10`), hostnames (`localhost`), or full addresses. The app automatically cleans protocols and appends the default port `:8000` if no port is specified.

### 2.2 Clipboard Conflict Resolution
To prevent `qt.qpa.mime: Retrying to obtain clipboard` errors and infinite loops:
- **Lock-Release Deferral**: When the system clipboard fires a change event, [ClipboardManager](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/client/core.py#L11) waits **50ms** before reading the clipboard. This allows the copying application to release its handle, preventing lock contention.
- **Local Write Protection**: When writing incoming text to the clipboard, the manager sets `self.is_updating_locally = True`. Clipboard read operations are bypassed for 150ms to swallow self-generated clipboard change events safely.
- **Line Ending Normalization**: The plain text is normalized to LF (`\n`) line endings prior to comparison to eliminate loops caused by Windows-specific `\r\n` conversions.

---

## 3. Server Application Details

The server acts as a message router and session controller.

- **Entrypoint / API**: [server/main.py](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/server/main.py)
- **Control Panel GUI**: [server/gui.py](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/server/gui.py)

### 3.1 Server GUI Control Panel
- **Non-Blocking Execution**: The FastAPI/uvicorn server is launched in a background `ServerThread` (inheriting from `threading.Thread`) so that the main PyQt6 GUI event loop remains fully responsive.
- **Auto-Detection**: Displays local network IP interfaces (e.g. `192.168.x.x`) to simplify pairing configurations.
- **System Tray Operation**:
  - Clicking **Start Server** starts the uvicorn process and immediately minimizes/hides the main window to the system tray.
  - Clicking the window close button (`X`) hides the window to the system tray if the server is active, preventing accidental shutdowns.
  - Right-clicking the tray icon shows options to restore the window (`Show Window`), control the service (`Stop Server` / `Start Server`), and safely shut down uvicorn and terminate the process (`Exit`).

---

## 4. End-to-End Encryption (E2EE)

DNA Bridge uses a **Zero-Knowledge** architecture:

- **Key Derivation**: The 6-character alphanumeric pairing code is converted to a 256-bit AES key using PBKDF2HMAC with SHA-256 and a static salt `b'dna-bridge-salt-v1'` over 100,000 iterations.
- **AES-256 CBC**: Data is encrypted and decrypted on the client side using Fernet (symmetric cryptography built on AES-256).
- **Relay Privacy**: The relay server only sees base64-encoded Fernet tokens. Because it does not possess the pairing code or salt, it is impossible for the relay server (or an eavesdropper) to decrypt clipboard contents.

---

## 5. Deployment Options (Over the Internet)

Since DNA Bridge uses WebSockets, the server can be deployed over the internet to sync clipboards globally.

### 5.1 Temporary Exposure (Ngrok)
For testing across networks without hosting setups:
1. Start the Server GUI locally and click **Start Server**.
2. Run Ngrok to forward port 8000:
   ```bash
   ngrok http 8000
   ```
3. Copy the generated forwarding domain (e.g. `xxxx.ngrok-free.app`).
4. Enter `xxxx.ngrok-free.app` as the **Server IP Address** in both clients.

### 5.2 VPS Deployment (AWS, DigitalOcean, Render, Fly.io)
For permanent 24/7 synchronization:
1. Spin up a cloud Linux container or VM.
2. Install dependencies: `pip install uvicorn fastapi websockets cryptography`.
3. Launch the server headlessly:
   ```bash
   uvicorn server.main:app --host 0.0.0.0 --port 8000
   ```
4. Configure clients to point to the server's public IP address or DNS domain on port 8000.

### 5.3 VPN Mesh Network (Tailscale)
If you do not want to expose any ports publicly:
1. Install **Tailscale** on the server machine and client machines.
2. Pair them to your Tailscale network.
3. Start the server and copy its Tailscale IP (e.g., `100.x.y.z`).
4. Point all client applications to this IP: `100.x.y.z:8000`.

---

## 6. Build Instructions for Windows

To package the client or server into standalone `.exe` binaries:

### 6.1 Requirements
Install development requirements:
```bash
pip install -r requirements-dev.txt
```

### 6.2 Bundling the Client
The project includes a pyinstaller spec file ([dna-bridge.spec](file:///d:/CODE%20RED/CODES/Scripts/DNA%20Bridge/DNA%20Bridge/dna-bridge.spec)):
```bash
pyinstaller dna-bridge.spec
```
The bundled executable will be generated under `dist/DNA-Bridge/DNA-Bridge.exe`.
