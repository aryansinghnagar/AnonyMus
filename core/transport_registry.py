import os
from typing import Dict
from core.interfaces import TransportProvider

class TransportRegistry:
    def __init__(self):
        self._transports: Dict[str, TransportProvider] = {}
        self._active_mode = os.environ.get("ANONYMUS_MODE", "relay").lower()

    def register(self, name: str, transport: TransportProvider):
        self._transports[name] = transport

    def get_active_mode(self) -> str:
        return self._active_mode

    def get_active_transport(self) -> TransportProvider:
        return self._transports[self._active_mode]

    def switch_mode(self, new_mode: str, new_config: dict) -> bool:
        new_mode = new_mode.lower()
        if new_mode not in self._transports:
            return False
        if new_mode == self._active_mode:
            return True

        current = self._transports[self._active_mode]
        target = self._transports[new_mode]

        # 1. Handoff session state
        current.handoff(target)
        # 2. Stop current transport
        current.stop()
        # 3. Start target transport
        target.start(new_config)

        self._active_mode = new_mode
        # Set environment variable so child processes/subprocesses inherit the configuration
        os.environ["ANONYMUS_MODE"] = new_mode
        return True

registry = TransportRegistry()
