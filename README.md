# DNA Bridge

DNA Bridge is a lightweight Windows application that allows users to instantly copy and paste text between multiple computers over the internet.

## Features
- **Real-Time Sync**: Instant clipboard updates via WebSockets.
- **End-to-End Encryption**: All clipboard data is encrypted (AES-256) on the client side.
- **System Tray Operation**: Runs quietly in the background.
- **Easy Pairing**: Simple 6-character codes to link devices.

## Tech Stack
- **Client**: Python, PyQt6, `websockets`, `cryptography`, `qasync`.
- **Server**: Python, FastAPI, WebSockets.

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Start the relay server:
   ```bash
   python server/main.py
   ```

3. Run the client on two or more computers:
   ```bash
   python client/app.py
   ```

## Usage
1. Open the client on both devices.
2. Generate a pairing code on one device or enter a matching code on both.
3. Once connected (tray icon turns green), any text you copy on one device will be instantly available to paste on the other.

## Building for Windows
To bundle the client into a single EXE:
1. Install development dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```
2. Run PyInstaller:
   ```bash
   pyinstaller dna-bridge.spec
   ```
3. The executable will be in the `dist/DNA-Bridge` folder.

## Security
DNA Bridge uses E2EE. The relay server only sees encrypted blobs and does not have access to your clipboard content. The encryption key is derived from your unique pairing code.
