from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class TransportProvider(ABC):
    """Contract every AnonyMus transport (relay, p2p) must satisfy."""

    @abstractmethod
    def start(self, config: Dict[str, Any]) -> None:
        """Boot the transport (start server, init Tor, register mDNS, etc.)."""

    @abstractmethod
    def stop(self) -> None:
        """Tear down the transport, zeroize keys, close sockets."""

    @abstractmethod
    def send(self, recipient: str, ciphertext: str, iv: str, seq: int) -> bool:
        """Deliver an encrypted payload to the recipient. Returns True on success."""

    @abstractmethod
    def handoff(self, other: "TransportProvider") -> None:
        """Gracefully transfer session state to another transport (for mode switch)."""

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return transport health metrics (bootstrap %, queue depth, etc.)."""

    @abstractmethod
    def describe(self) -> Dict[str, str]:
        """Return static metadata: mode name, version, capabilities."""
