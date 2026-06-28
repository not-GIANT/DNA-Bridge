"""
client/discovery.py — LAN Auto-Discovery via mDNS for DNA Bridge.

Browses the local network for DNA Bridge relay servers advertising the
_dnabridge._tcp.local. service type and exposes them as Qt signals so the
UI can react immediately without polling.

Thread safety: Zeroconf callbacks arrive from the zeroconf library's internal
daemon thread. All signal emissions are safe because PyQt6 signals are
thread-safe by design (they queue the call across thread boundaries when
the connection is of type Qt.QueuedConnection, which is the default for
cross-thread signal-slot connections).
"""

import logging
import socket
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger("Client")

# ---------------------------------------------------------------------------
# Lazy import — graceful degradation when zeroconf is not installed
# ---------------------------------------------------------------------------
try:
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf, ServiceStateChange
    from zeroconf._utils.ipaddress import cached_ip_addresses
    _ZEROCONF_AVAILABLE = True
except ImportError:
    _ZEROCONF_AVAILABLE = False

SERVICE_TYPE = "_dnabridge._tcp.local."


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredServer:
    """Holds information about a single discovered DNA Bridge server."""
    name: str          # Human-readable instance name, e.g. "DNA Bridge @ DESKTOP-ABC"
    host: str          # Resolved IPv4 address string
    port: int          # TCP port (typically 8000)
    hostname: str = "" # Server hostname from TXT record (optional)

    @property
    def display_name(self) -> str:
        label = self.name.replace("._dnabridge._tcp.local.", "")
        return f"{label}  —  {self.host}:{self.port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self.host}:{self.port}"


# ---------------------------------------------------------------------------
# Qt-aware discovery engine
# ---------------------------------------------------------------------------

class MDNSDiscovery(QObject):
    """
    Discovers DNA Bridge servers on the local network via mDNS / Bonjour.

    Signals
    -------
    server_found(DiscoveredServer)
        Emitted when a new server appears on the network.
    server_lost(str)
        Emitted when a previously found server disappears. The argument is
        the server's ``name`` field.
    """

    server_found = pyqtSignal(object)   # emits DiscoveredServer
    server_lost  = pyqtSignal(str)      # emits server name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._zeroconf: Optional["Zeroconf"] = None
        self._browser: Optional["ServiceBrowser"] = None
        self._lock = threading.Lock()
        self._servers: Dict[str, DiscoveredServer] = {}
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start browsing for servers. Non-blocking."""
        if not _ZEROCONF_AVAILABLE:
            logger.warning(
                "mDNS discovery disabled: 'zeroconf' package not found. "
                "Install it with:  pip install zeroconf"
            )
            return

        with self._lock:
            if self._running:
                return
            self._running = True

        # Start the browser in the calling thread's context — the zeroconf
        # library manages its own internal daemon threads.
        try:
            zc = Zeroconf()
            browser = ServiceBrowser(zc, SERVICE_TYPE, handlers=[self._on_service_state_change])
            with self._lock:
                self._zeroconf = zc
                self._browser = browser
            logger.info("mDNS: Discovery started — scanning for DNA Bridge servers on LAN...")
        except Exception as e:
            logger.error(f"mDNS: Failed to start discovery: {e}")
            self._running = False

    def stop(self):
        """Stop browsing and release all Zeroconf resources."""
        with self._lock:
            zc = self._zeroconf
            self._zeroconf = None
            self._browser = None
            self._running = False
            self._servers.clear()

        if zc:
            try:
                zc.close()
            except Exception:
                pass
            logger.debug("mDNS: Discovery stopped")

    @property
    def discovered_servers(self) -> list[DiscoveredServer]:
        """Thread-safe snapshot of currently visible servers."""
        with self._lock:
            return list(self._servers.values())

    # ------------------------------------------------------------------
    # Internal — called from zeroconf's daemon thread
    # ------------------------------------------------------------------

    def _on_service_state_change(self, zeroconf: "Zeroconf", service_type: str,
                                  name: str, state_change: "ServiceStateChange"):
        """Dispatch handler for all mDNS service events."""
        if state_change is ServiceStateChange.Added or state_change is ServiceStateChange.Updated:
            self._handle_added(zeroconf, service_type, name)
        elif state_change is ServiceStateChange.Removed:
            self._handle_removed(name)

    def _handle_added(self, zeroconf: "Zeroconf", service_type: str, name: str):
        """Resolve the service details and emit server_found."""
        try:
            info = zeroconf.get_service_info(service_type, name, timeout=3000)
            if not info:
                logger.debug(f"mDNS: Could not resolve service info for {name!r}")
                return

            # Resolve IP address — prefer the first IPv4 address
            host = ""
            for addr_bytes in info.addresses:
                try:
                    resolved = socket.inet_ntoa(addr_bytes)
                    if not resolved.startswith("127."):
                        host = resolved
                        break
                except Exception:
                    continue

            if not host and info.addresses:
                try:
                    host = socket.inet_ntoa(info.addresses[0])
                except Exception:
                    pass

            if not host:
                logger.debug(f"mDNS: No usable address for {name!r}")
                return

            port = info.port
            props = info.decoded_properties if hasattr(info, "decoded_properties") else {}
            # Fallback for older zeroconf versions
            if not props and hasattr(info, "properties"):
                try:
                    props = {
                        k.decode() if isinstance(k, bytes) else k:
                        v.decode() if isinstance(v, bytes) else v
                        for k, v in info.properties.items()
                    }
                except Exception:
                    props = {}

            hostname = props.get("hostname", "")

            server = DiscoveredServer(name=name, host=host, port=port, hostname=hostname)

            with self._lock:
                self._servers[name] = server

            logger.info(f"mDNS: Discovered server — {server.display_name!r}")
            self.server_found.emit(server)

        except Exception as e:
            logger.debug(f"mDNS: Error resolving {name!r}: {e}")

    def _handle_removed(self, name: str):
        """Remove the server entry and emit server_lost."""
        with self._lock:
            removed = self._servers.pop(name, None)

        if removed:
            logger.info(f"mDNS: Server disappeared — {removed.display_name!r}")
            self.server_lost.emit(name)
