import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-for-db-key-test"

from transports.p2p import database as database

database.DB_FILE = "test_users_db_key.db"
from transports.p2p import server as server


class TestP2PDBKeyCookie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = "test_users_db_key.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config["TESTING"] = True
        server.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = server.app.test_client()
        database.init_db()
        database.register_local_user("testuser", "password")

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = "test_users_db_key.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def test_no_db_key_in_cookie(self):
        res = self.client.post(
            "/login", json={"username": "testuser", "password": "password"}
        )
        self.assertEqual(res.status_code, 200)

        # Verify response contains the cookie
        cookies = res.headers.getlist("Set-Cookie")
        self.assertTrue(any("session=" in cookie for cookie in cookies))

        # Decode session cookie using Flask's SecureCookieSessionInterface serializer
        from flask.sessions import SecureCookieSessionInterface

        serializer = SecureCookieSessionInterface().get_signing_serializer(server.app)

        # Extract session cookie value
        cookie_val = None
        for cookie in cookies:
            if "session=" in cookie:
                cookie_val = cookie.split("session=")[1].split(";")[0]
                break

        self.assertIsNotNone(cookie_val)

        # Decode the session data
        session_data = serializer.loads(cookie_val)

        # Verify db_key is NOT in session cookie data
        self.assertNotIn("db_key", session_data)

        # Verify db_key_id IS in session cookie data
        self.assertIn("db_key_id", session_data)
        self.assertEqual(session_data["username"], "testuser")


if __name__ == "__main__":
    unittest.main()
