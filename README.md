<div align="center">

<!-- BANNER -->
<img src="https://raw.githubusercontent.com/not-GIANT/DNA-Bridge/main/assets/banner.svg" alt="DNA Bridge Banner" width="100%"/>

<br/>

<!-- BADGES -->
<a href="https://github.com/not-GIANT/DNA-Bridge/releases/latest">
  <img src="https://img.shields.io/github/v/release/not-GIANT/DNA-Bridge?style=for-the-badge&logo=github&logoColor=white&color=0ea5e9&labelColor=0d1117" alt="Latest Release"/>
</a>
<a href="https://github.com/not-GIANT/DNA-Bridge/blob/main/LICENSE">
  <img src="https://img.shields.io/badge/License-MIT-a78bfa?style=for-the-badge&labelColor=0d1117" alt="License"/>
</a>
<img src="https://img.shields.io/badge/Platform-Windows-38bdf8?style=for-the-badge&logo=windows&logoColor=white&labelColor=0d1117" alt="Platform"/>
<img src="https://img.shields.io/badge/Python-3.10+-22c55e?style=for-the-badge&logo=python&logoColor=white&labelColor=0d1117" alt="Python"/>
<img src="https://img.shields.io/badge/Encryption-AES--128--CBC-f59e0b?style=for-the-badge&logo=letsencrypt&logoColor=white&labelColor=0d1117" alt="Encryption"/>
<img src="https://img.shields.io/badge/WebSockets-Live%20Sync-0ea5e9?style=for-the-badge&labelColor=0d1117" alt="WebSockets"/>

<br/><br/>

> **DNA Bridge** is a lightweight Windows desktop app that instantly syncs your clipboard — text, rich content, images, and files — across multiple computers over the internet or local network, with end-to-end AES-128-CBC + HMAC-SHA256 encryption.

<br/>

<a href="https://github.com/not-GIANT/DNA-Bridge/releases/latest">
  <img src="https://img.shields.io/badge/⬇%20Download%20for%20Windows-0ea5e9?style=for-the-badge&logoColor=white" alt="Download"/>
</a>
&nbsp;
<a href="#-quick-start">
  <img src="https://img.shields.io/badge/📖%20Quick%20Start-1e293b?style=for-the-badge" alt="Quick Start"/>
</a>
&nbsp;
<a href="https://x.com/giant_notop?s=11">
  <img src="https://img.shields.io/badge/𝕏%20Follow-000000?style=for-the-badge&logo=x&logoColor=white" alt="Twitter/X"/>
</a>

</div>

---

## ✨ Features

<!-- FEATURES SVG -->
<img src="https://raw.githubusercontent.com/not-GIANT/DNA-Bridge/main/assets/features.svg" alt="Features" width="100%"/>

<br/>

| Feature | Description |
|---|---|
| ⚡ **Real-Time Sync** | WebSocket-powered clipboard updates across all paired devices instantly |
| 🔐 **End-to-End Encryption** | AES-128-CBC + HMAC-SHA256 — the relay server never sees your data |
| 📋 **Rich Content Support** | Sync plain text, formatted rich text, images, and entire file/folder trees |
| 🔗 **One-Code Pairing** | Connect any two devices with a simple 6-character code — no accounts needed |
| 🌐 **Flexible Networking** | Works over the internet or on a local LAN — you choose |

---

## 📸 Screenshots

<div align="center">
<table>
  <tr>
    <td align="center" width="50%">
      <b>Client Interface</b><br/><br/>
      <img src="https://raw.githubusercontent.com/not-GIANT/DNA-Bridge/main/screenshots/client.png" alt="DNA Bridge Client" width="100%"/>
    </td>
    <td align="center" width="50%">
      <b>Server Dashboard</b><br/><br/>
      <img src="https://raw.githubusercontent.com/not-GIANT/DNA-Bridge/main/screenshots/server.png" alt="DNA Bridge Server" width="100%"/>
    </td>
  </tr>
</table>
</div>

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **Windows 10/11**
- A relay server (self-hosted or remote)

### 1 · Install Dependencies

```bash
pip install -r requirements.txt
```

### 2 · Start the Relay Server

Run this once on any machine reachable by all clients (can be the same PC on a LAN):

```bash
python server/main.py
```

The server will output its address — note it for the next step.

### 3 · Launch the Client

Run on **each** computer you want to sync:

```bash
python client/app.py
```

### 4 · Pair Your Devices

1. Open the client on **Device A** → click **Generate Code** → note the 6-character code
2. Open the client on **Device B** → enter the same code → click **Connect**
3. The tray icon turns **green** ✅ — you're live!

> Copy anything on Device A and it's instantly on Device B's clipboard. That's it.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        DNA Bridge                            │
│                                                             │
│  ┌──────────┐    Encrypted WS     ┌────────────────────┐   │
│  │ Client A │ ─────────────────►  │   Relay Server     │   │
│  │  PyQt6   │ ◄─────────────────  │   FastAPI + WS     │   │
│  └──────────┘    AES-128-CBC      │  (blind to data)   │   │
│                  HMAC-SHA256      └────────────────────┘   │
│  ┌──────────┐                             │                 │
│  │ Client B │ ◄───────────────────────────┘                │
│  │  PyQt6   │         Encrypted WS                         │
│  └──────────┘                                              │
└─────────────────────────────────────────────────────────────┘
```

**Key components:**

- **`client/`** — PyQt6 desktop app with system tray, clipboard monitoring, and encrypted WS transport
- **`server/`** — FastAPI relay that only forwards opaque encrypted blobs
- **`shared/`** — Shared crypto primitives and protocol definitions
- **`tests/`** — Unit and integration tests

---

## 🔐 Security Model

DNA Bridge is designed so that **no one except the paired devices** can read your clipboard data.

| Layer | Mechanism |
|---|---|
| **Confidentiality** | AES-128-CBC with a key derived from your pairing code |
| **Integrity** | HMAC-SHA256 on every message |
| **Relay blindness** | Server forwards only ciphertext — it cannot decrypt or read content |
| **Key exchange** | Pairing code → PBKDF2 key derivation; never transmitted over the wire |

> ⚠️ For maximum security, host your own relay server on trusted infrastructure.

---

## 🛠️ Building a Windows Executable

Bundle the client into a single portable `.exe`:

```bash
# Install build deps
pip install -r requirements-dev.txt

# Build with PyInstaller
pyinstaller dna-bridge.spec

# Output will be in:
#   dist/DNA-Bridge/DNA-Bridge.exe
```

The resulting executable has no external dependencies — distribute it directly.

---

## 📦 Tech Stack

<div align="center">

| Layer | Technology |
|---|---|
| **Client UI** | PyQt6 (PySide6) |
| **Networking** | `websockets`, `qasync` |
| **Encryption** | `cryptography` (AES-128-CBC + HMAC-SHA256) |
| **Server** | FastAPI + Uvicorn |
| **Packaging** | PyInstaller |

</div>

---

## 📁 Project Structure

```
DNA-Bridge/
├── client/           # PyQt6 desktop client
│   └── app.py
├── server/           # FastAPI relay server
│   └── main.py
├── shared/           # Shared crypto & protocol
├── tests/            # Test suite
├── requirements.txt
├── requirements-dev.txt
└── dna-bridge.spec   # PyInstaller spec
```

---

## 🗺️ Roadmap

- [x] Text clipboard sync
- [x] Rich text & image sync
- [x] File & folder sync
- [x] AES-128-CBC + HMAC-SHA256 encryption
- [x] 6-character pairing codes
- [ ] macOS & Linux clients
- [ ] Mobile companion app
- [ ] Self-hosted server installer (Docker)
- [ ] Multi-device rooms (3+ computers)

---

## 🤝 Contributing

Contributions are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

<div align="center">

Made with ❤️ by [not-GIANT](https://github.com/not-GIANT)

<a href="https://x.com/giant_notop?s=11">
  <img src="https://img.shields.io/badge/Follow%20on%20𝕏-000000?style=for-the-badge&logo=x&logoColor=white" alt="X/Twitter"/>
</a>

<br/><br/>

<sub>⭐ Star this repo if DNA Bridge saves you time!</sub>

</div>
