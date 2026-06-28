# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_all

# Add project root to path for imports during analysis if needed
sys.path.insert(0, os.path.abspath('.'))

def collect_pkg(package):
    datas, binaries, hiddenimports = collect_all(package)
    return datas, binaries, hiddenimports

# Common dependencies
ws_datas, ws_binaries, ws_hidden = collect_pkg('websockets')
crypto_datas, crypto_binaries, crypto_hidden = collect_pkg('cryptography')

ws_extra_hidden = [
    'websockets.client',
    'websockets.server',
    'websockets.legacy',
    'websockets.legacy.client',
    'websockets.legacy.server',
    'websockets.legacy.auth',
    'websockets.legacy.protocol',
    'websockets.legacy.handshake',
    'websockets.legacy.framing',
    'websockets.sync',
    'websockets.sync.client',
    'websockets.sync.server',
    'websockets.sync.connection',
]

# --- Client Analysis ---
client_hidden = ws_hidden + ws_extra_hidden + crypto_hidden + ['qasync', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'certifi']
client_datas = ws_datas + crypto_datas
if os.path.exists('config.json'):
    client_datas.append(('config.json', '.'))

client_binaries = ws_binaries + crypto_binaries
qt_excludes = ['PySide6', 'PyQt5', 'PySide2', 'matplotlib', 'tkinter']

a_client = Analysis(
    ['client/app.py'],
    pathex=[],
    binaries=client_binaries,
    datas=client_datas,
    hiddenimports=client_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# --- Server Analysis ---
server_hidden = ws_hidden + ws_extra_hidden + crypto_hidden + ['qasync', 'fastapi', 'uvicorn', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'certifi']
# FastAPI and Uvicorn often need extra collection
f_d, f_b, f_h = collect_pkg('fastapi')
u_d, u_b, u_h = collect_pkg('uvicorn')
server_datas = ws_datas + crypto_datas + f_d + u_d
server_binaries = ws_binaries + crypto_binaries + f_b + u_b
server_hidden += f_h + u_h

# Include cloudflared.exe if present
if os.path.exists('cloudflared.exe'):
    server_datas.append(('cloudflared.exe', '.'))
elif os.path.exists('cloudflared'):
    server_datas.append(('cloudflared', '.'))

a_server = Analysis(
    ['server/gui.py'],
    pathex=[],
    binaries=server_binaries,
    datas=server_datas,
    hiddenimports=server_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz_client = PYZ(a_client.pure, a_client.zipped_data)
pyz_server = PYZ(a_server.pure, a_server.zipped_data)

exe_client = EXE(
    pyz_client,
    a_client.scripts,
    [],
    exclude_binaries=True,
    name='DNA-Bridge-Client',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='client.png' if os.path.exists('client.png') else None,
)

exe_server = EXE(
    pyz_server,
    a_server.scripts,
    [],
    exclude_binaries=True,
    name='DNA-Bridge-Server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='server.png' if os.path.exists('server.png') else None,
)

coll = COLLECT(
    exe_client,
    a_client.binaries,
    a_client.zipfiles,
    a_client.datas,
    exe_server,
    a_server.binaries,
    a_server.zipfiles,
    a_server.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DNA-Bridge',
)
