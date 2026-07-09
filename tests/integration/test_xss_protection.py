import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-for-xss-protection-test"

from transports.p2p import database as database

database.DB_FILE = "test_users_xss.db"
from transports.p2p import server as server


class TestXSSProtection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = "test_users_xss.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config["TESTING"] = True
        server.app.config["WTF_CSRF_ENABLED"] = False
        server.limiter.enabled = False
        cls.client = server.app.test_client()
        database.init_db()
        database.register_local_user("testuser", "password")

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = "test_users_xss.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def test_xss_input_rejection(self):
        # Authenticate first
        res = self.client.post(
            "/login", json={"username": "testuser", "password": "password"}
        )
        self.assertEqual(res.status_code, 200, res.data)

        # Test add contact with malicious XSS nickname
        contact_data = {
            "onion_address": "abcdefghijklmnop.onion",
            "nickname": "<script>alert(1)</script>",
            "my_public_key": "mock_public_key",
        }
        res = self.client.post("/api/contacts/add", json=contact_data)
        # Should return 400 Bad Request due to validation failure
        self.assertEqual(res.status_code, 400)
        self.assertIn("Nickname contains invalid characters", res.get_json()["error"])

        # Verify contact was NOT added to DB
        contact = database.get_contact("abcdefghijklmnop.onion")
        self.assertIsNone(contact)


if __name__ == "__main__":
    unittest.main()
