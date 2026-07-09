import os
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

from transports.p2p import database as database

database.DB_FILE = "test_disappearing_messages.db"
from transports.p2p import server as server


class TestDisappearingMessages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = "test_disappearing_messages.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config["TESTING"] = True
        server.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = server.app.test_client()
        database.init_db()
        database.register_local_user("testuser", "password")

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = "test_disappearing_messages.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def setUp(self):
        # Clear database messages and contacts before each test
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM messages")
        c.execute("DELETE FROM contacts")
        conn.commit()
        conn.close()

        # Log in the client
        self.client.post(
            "/login", json={"username": "testuser", "password": "password"}
        )

    @patch("transports.p2p.server.send_onion_post")
    def test_disappearing_messages_flow(self, mock_send_onion):
        mock_send_onion.return_value = {"status": "delivered"}

        # 1. Add contact
        contact_onion = "friendabcdefghijkl.onion"
        database.add_contact(contact_onion, "friend", "accepted")

        # 2. Set disappearing message TTL (5 seconds = 5000 ms)
        res = self.client.post(
            "/api/messages/set_ttl",
            json={"onion_address": contact_onion, "ttl_ms": 5000},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

        # Verify contact's TTL in DB
        contact = database.get_contact(contact_onion)
        self.assertEqual(contact["disappearing_ttl"], 5000)

        # 3. Send message — expires_at should be computed automatically
        send_data = {
            "onion_address": contact_onion,
            "iv": "dGVzdF9pdg==",
            "ciphertext": "dGVzdF9jaXBoZXJ0ZXh0",
            "seq": 1,
        }
        res = self.client.post("/api/messages/send", json=send_data)
        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json["success"])
        self.assertIsNotNone(res_json["expires_at"])

        # Verify message exists in DB with expires_at
        messages = database.get_messages(contact_onion)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["expires_at"], res_json["expires_at"])

        # 4. Assert local expiry: artificially set expires_at to 1 second ago and run sweeper
        conn = database.get_connection()
        c = conn.cursor()
        past_time = int(time.time() * 1000) - 5000
        c.execute("UPDATE messages SET expires_at = ?", (past_time,))
        conn.commit()
        conn.close()

        # Verify expired message is fetched and deleted
        expired = database.get_expired_messages()
        self.assertEqual(len(expired), 1)

        deleted = database.delete_expired_messages()
        self.assertEqual(deleted, 1)

        messages = database.get_messages(contact_onion)
        self.assertEqual(len(messages), 0)

    @patch("transports.p2p.server.send_onion_post")
    def test_message_deletion_propagation(self, mock_send_onion):
        mock_send_onion.return_value = {"status": "deleted"}

        contact_onion = "friendabcdefghijkl.onion"
        database.add_contact(contact_onion, "friend", "accepted")

        # Save a message locally
        timestamp = int(time.time() * 1000)
        database.save_message(
            contact_onion, "me", '{"iv":"iv","ciphertext":"ct","seq":1}', timestamp
        )

        # Verify it exists
        messages = database.get_messages(contact_onion)
        self.assertEqual(len(messages), 1)

        # Delete message via API — should trigger propagation
        res = self.client.post(
            "/api/messages/delete",
            json={"onion_address": contact_onion, "timestamp": timestamp},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

        # Wait a brief moment for executor to submit task
        time.sleep(0.1)

        # Check propagation request was made
        mock_send_onion.assert_called_once()
        args, kwargs = mock_send_onion.call_args
        self.assertEqual(args[0], contact_onion)
        self.assertEqual(args[1], "/p2p/delete")
        self.assertEqual(args[2]["timestamp"], timestamp)

        # Check message is deleted locally
        messages = database.get_messages(contact_onion)
        self.assertEqual(len(messages), 0)

    def test_p2p_delete_route(self):
        # Test incoming deletion request from accepted peer
        contact_onion = "friendabcdefghijkl.onion"
        database.add_contact(contact_onion, "friend", "accepted")

        timestamp = int(time.time() * 1000)
        database.save_message(
            contact_onion,
            contact_onion,
            '{"iv":"iv","ciphertext":"ct","seq":1}',
            timestamp,
        )

        # Verify it exists
        messages = database.get_messages(contact_onion)
        self.assertEqual(len(messages), 1)

        # Trigger /p2p/delete
        res = self.client.post(
            "/p2p/delete", json={"sender": contact_onion, "timestamp": timestamp}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["status"], "deleted")

        # Check message was deleted locally
        messages = database.get_messages(contact_onion)
        self.assertEqual(len(messages), 0)


if __name__ == "__main__":
    unittest.main()
