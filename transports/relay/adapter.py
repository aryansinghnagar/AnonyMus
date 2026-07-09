from typing import Any

from core.interfaces import TransportProvider


class RelayTransport(TransportProvider):
    def start(self, config: dict[str, Any]) -> None:
        import os

        # Start mDNS if configured
        if config.get("ANONYMUS_MDNS", "false").lower() == "true":
            from transports.relay.server import advertise_mdns

            port = int(config.get("PORT", 5000))
            advertise_mdns(port)

        # Configure Tor SOCKS5 proxy for FFI onion routing (2-Hop Private Message Routing)
        socks_port = config.get("SOCKS_PORT", 9050)

        relay_as_onion = (
            os.environ.get("RELAY_AS_ONION", "false").lower() == "true"
            or config.get("RELAY_AS_ONION", "false").lower() == "true"
        )
        if relay_as_onion:
            print("[Onion Relay] Starting Tor Hidden Service for Relay Server...")
            from transports.p2p.tor_manager import launch_tor

            port = int(config.get("PORT", 5000))
            onion_address, socks_port, peer_port = launch_tor(peer_port=port)
            os.environ["RELAY_ONION_ADDRESS"] = onion_address
            print(
                f"[Onion Relay] Relay running as onion service at: http://{onion_address}"
            )

        os.environ["ALL_PROXY"] = f"socks5h://127.0.0.1:{socks_port}"
        print(
            f"2-Hop Private Message Routing configured via Tor SOCKS5 proxy on port {socks_port}"
        )

    def stop(self) -> None:
        # Cleanup mdns
        from transports.relay import server

        if getattr(server, "zeroconf_instance", None):
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

    def health(self) -> dict[str, Any]:
        from transports.relay import server

        return {"mdns_active": getattr(server, "zeroconf_instance", None) is not None}

    def describe(self) -> dict[str, str]:
        return {"mode": "relay", "version": "1.0", "type": "Centralized Relay"}
