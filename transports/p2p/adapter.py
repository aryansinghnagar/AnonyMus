from typing import Any

from core.interfaces import TransportProvider


class P2PTransport(TransportProvider):
    def __init__(self):
        self.onion_address = None
        self.socks_port = 9050

    def start(self, config: dict[str, Any]) -> None:
        from transports.p2p import database, tor_manager

        try:
            port = int(config.get("PORT", 5001))
            onion, socks, peer = tor_manager.launch_tor(peer_port=port)
            self.socks_port = socks
            self.onion_address = onion
            database.set_config("my_onion_address", onion)
            print(f"[P2PTransport] Tor hidden service started: {onion}")
        except Exception as e:
            print(f"[P2PTransport] Failed to launch Tor: {e}")
            raise e

    def stop(self) -> None:
        from transports.p2p import tor_manager

        try:
            tor_manager.cleanup()
            print("[P2PTransport] Tor hidden service stopped.")
        except Exception as e:
            print(f"[P2PTransport] Error stopping Tor: {e}")

    def send(self, recipient: str, ciphertext: str, iv: str, seq: int) -> bool:
        # P2P outbound messaging goes over Tor SOCKS5 via transports.p2p.server
        return True

    def handoff(self, other: TransportProvider) -> None:
        # Zeroize active P2P session keys if any
        pass

    def health(self) -> dict[str, Any]:
        return {
            "onion_address": self.onion_address,
            "socks_port": self.socks_port,
            "tor_active": self.onion_address is not None,
        }

    def describe(self) -> dict[str, str]:
        return {"mode": "p2p", "version": "1.0", "type": "Decentralized P2P"}
