import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

from transports.p2p import database as database

database.DB_FILE = "test_week25_sync.db"
from transports.p2p import server as server


class TestWeek25DeviceSync(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = "test_week25_sync.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config["TESTING"] = True
        server.app.config["WTF_CSRF_ENABLED"] = False
        server.app.config["RATELIMIT_ENABLED"] = False
        server.limiter.enabled = False
        cls.client = server.app.test_client()
        database.init_db()
        database.register_local_user("syncuser", "syncpassword")

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = "test_week25_sync.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        # Kill pairing broker if running
        if server.active_pairing_broker:
            server.active_pairing_broker.shutdown()
            server.active_pairing_broker.server_close()

    def login(self):
        res = self.client.post(
            "/login", json={"username": "syncuser", "password": "syncpassword"}
        )
        self.assertEqual(res.status_code, 200)

    def test_sync_endpoints_flow(self):
        self.login()

        # 1. Trigger pairing server setup
        res = self.client.post("/api/sync/pair")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIsNotNone(data["ip"])
        self.assertEqual(data["port"], 8999)
        self.assertIsNotNone(data["k"])

        # 2. Push database to pairing server locally
        res_push = self.client.post(
            "/api/sync/push", json={"ip": data["ip"], "port": 8999, "k": data["k"]}
        )
        self.assertEqual(res_push.status_code, 200)
        push_data = res_push.get_json()
        self.assertTrue(push_data["success"])
        self.assertIn("backup successfully fanned out", push_data["message"])

        # Confirm backup database file is generated
        self.assertTrue(os.path.exists("test_week25_sync.db.bak"))
