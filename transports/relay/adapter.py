from core.interfaces import TransportProvider
from typing import Dict, Any

class RelayTransport(TransportProvider):
    def start(self, config: Dict[str, Any]) -> None:
        # Start mDNS if configured
        if config.get("ANONYMUS_MDNS", "false").lower() == "true":
            from transports.relay.server import advertise_mdns
            port = int(config.get("PORT", 5000))
            advertise_mdns(port)

    def stop(self) -> None:
        # Cleanup mdns
        from transports.relay import server
        if getattr(server, 'zeroconf_instance', None):
            try:
                server.zeroconf_instance.close()
                server.zeroconf_instance = None
                print("mDNS advertisement stopped.")
            except Exception as e:
                print(f"Error stopping mDNS: {e}")

    def send(self, recipient: str, ciphertext: str, iv: str, seq: int) -> bool:
        # Relay is zero-knowledge; Python server does not originate/send client payloads.
        return True

    def handoff(self, other: TransportProvider) -> None:
        # Zeroize active relay queue state if any exists
        pass

    def health(self) -> Dict[str, Any]:
        from transports.relay import server
        return {"mdns_active": getattr(server, 'zeroconf_instance', None) is not None}

    def describe(self) -> Dict[str, str]:
        return {"mode": "relay", "version": "1.0", "type": "Centralized Relay"}
