"""
server/mdns.py — mDNS service advertisement for DNA Bridge.

Registers the relay server on the local network as:
    _dnabridge._tcp.local.

Other devices on the same LAN can discover this automatically without the
user needing to know the server's IP address.

Thread safety: all Zeroconf operations run in the daemon thread that the
zeroconf library manages internally; this module only calls into that
thread via the stable public API.
"""

import logging
import socket
import threading
from typing import Optional

logger = logging.getLogger("Server")

# ---------------------------------------------------------------------------
# Lazy import — zeroconf is an optional dependency for the server.
# If it is not installed the server will still start normally; mDNS
# advertisement is silently skipped and a warning is logged.
# ---------------------------------------------------------------------------
try:
    from zeroconf import Zeroconf, ServiceInfo
    _ZEROCONF_AVAILABLE = True
except ImportError:
    _ZEROCONF_AVAILABLE = False


# Service type agreed upon by both server and client
SERVICE_TYPE = "_dnabridge._tcp.local."


def _get_local_ips() -> list[bytes]:
    """Return all non-loopback IPv4 addresses for this machine as packed bytes."""
    ips: list[bytes] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            addr = info[4][0]
            if not addr.startswith("127."):
                packed = socket.inet_aton(addr)
                if packed not in ips:
                    ips.append(packed)
    except Exception:
        pass

    # Always try the primary outbound interface as a fallback
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
        packed = socket.inet_aton(primary)
        if packed not in ips and not primary.startswith("127."):
            ips.append(packed)
    except Exception:
        pass

    return ips


class MDNSAdvertiser:
    """
    Advertises the DNA Bridge relay server via mDNS / Bonjour.

    Usage::

        advertiser = MDNSAdvertiser(port=8000)
        advertiser.start()   # non-blocking
        ...
        advertiser.stop()    # clean unregister
    """

    def __init__(self, port: int = 8000):
        self.port = port
        self._zeroconf: Optional["Zeroconf"] = None
        self._service_info: Optional["ServiceInfo"] = None
        self._lock = threading.Lock()
        self._started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Register the mDNS service. Safe to call multiple times."""
        if not _ZEROCONF_AVAILABLE:
            logger.warning(
                "mDNS advertisement disabled: 'zeroconf' package not found. "
                "Install it with:  pip install zeroconf"
            )
            return

        with self._lock:
            if self._started:
                return
            self._started = True

        # Run registration in a daemon thread so it never blocks the FastAPI
        # startup sequence.
        t = threading.Thread(target=self._register, daemon=True, name="mdns-advertiser")
        t.start()

    def stop(self):
        """Unregister the mDNS service and release resources."""
        with self._lock:
            zc = self._zeroconf
            info = self._service_info
            self._zeroconf = None
            self._service_info = None
            self._started = False

        if zc is None:
            return

        try:
            if info:
                zc.unregister_service(info)
                logger.info("mDNS: Service unregistered")
        except Exception as e:
            logger.debug(f"mDNS: Error during service unregister: {e}")
        finally:
            try:
                zc.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_service_info(self) -> Optional["ServiceInfo"]:
        """Build the Zeroconf ServiceInfo descriptor."""
        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = "dna-bridge-server"

        # Instance name must be unique on the network; use hostname to ensure that.
        instance_name = f"DNA Bridge @ {hostname}"
        # Fully-qualified service name required by zeroconf
        service_name = f"{instance_name}.{SERVICE_TYPE}"

        addresses = _get_local_ips()
        if not addresses:
            logger.warning("mDNS: No non-loopback addresses found; using 127.0.0.1")
            addresses = [socket.inet_aton("127.0.0.1")]

        properties = {
            "version": "1",
            "path": "/ws",
            "hostname": hostname,
        }

        logger.debug(
            f"mDNS: Building ServiceInfo — name={service_name!r}, "
            f"port={self.port}, addresses={[socket.inet_ntoa(a) for a in addresses]}"
        )

        return ServiceInfo(
            type_=SERVICE_TYPE,
            name=service_name,
            addresses=addresses,
            port=self.port,
            properties=properties,
            server=f"{hostname}.local.",
        )

    def _register(self):
        """Background thread: create Zeroconf instance and register service."""
        try:
            info = self._build_service_info()
            if info is None:
                return

            zc = Zeroconf()
            zc.register_service(info)

            with self._lock:
                # Check if stop() was called while we were registering
                if not self._started:
                    # Already stopped — clean up immediately
                    try:
                        zc.unregister_service(info)
                    except Exception:
                        pass
                    zc.close()
                    return
                self._zeroconf = zc
                self._service_info = info

            ip_strs = [socket.inet_ntoa(a) for a in info.addresses]
            logger.info(
                f"mDNS: Advertising '{info.name}' on port {self.port} "
                f"at {ip_strs}"
            )

        except Exception as e:
            logger.error(f"mDNS: Failed to register service: {e}")
            self._started = False
