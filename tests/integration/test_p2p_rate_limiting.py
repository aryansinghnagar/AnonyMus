import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-for-rate-limiting-test"

from transports.p2p import server as server


class TestP2PRateLimiting(unittest.TestCase):
    def setUp(self):
        server.app.config["TESTING"] = True
        self.ctx = server.app.test_request_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()

    def test_p2p_rate_limit_key_derivation(self):
        # 1. Test when request JSON contains a sender onion address
        with server.app.test_request_context(
            path="/p2p/message",
            method="POST",
            json={"sender": "alice.onion", "iv": "123", "ciphertext": "abc", "seq": 1},
        ):
            key = server.get_p2p_rate_limit_key()
            self.assertEqual(key, "alice.onion")

        # 2. Test when request JSON contains an onion_address
        with server.app.test_request_context(
            path="/p2p/handshake",
            method="POST",
            json={"onion_address": "bob.onion", "public_key": "pub"},
        ):
            key = server.get_p2p_rate_limit_key()
            self.assertEqual(key, "bob.onion")

        # 3. Test fallback to IP address when no JSON is present
        with server.app.test_request_context(path="/p2p/handshake", method="POST"):
            key = server.get_p2p_rate_limit_key()
            self.assertIn(key, ("127.0.0.1", "::1", "localhost"))


if __name__ == "__main__":
    unittest.main()
