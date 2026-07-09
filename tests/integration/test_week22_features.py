import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from transports.relay.adapter import RelayTransport


class TestWeek22Features(unittest.TestCase):
    def test_relay_as_onion_mode(self):
        # Initialize RelayTransport
        transport = RelayTransport()

        # Mock launch_tor function in tor_manager
        with patch("transports.p2p.tor_manager.launch_tor") as mock_launch:
            mock_launch.return_value = ("testonionrelayaddr.onion", 9999, 5000)

            # Patch env variable
            with patch.dict(os.environ, {"RELAY_AS_ONION": "true"}):
                config = {"PORT": "5000", "SOCKS_PORT": "9050"}
                transport.start(config)

                # Check launch_tor was called with correct port
                mock_launch.assert_called_once_with(peer_port=5000)

                # Check environment variable was populated
                self.assertEqual(
                    os.environ.get("RELAY_ONION_ADDRESS"), "testonionrelayaddr.onion"
                )
                # Check socks proxy configuration
                self.assertEqual(
                    os.environ.get("ALL_PROXY"), "socks5h://127.0.0.1:9999"
                )
