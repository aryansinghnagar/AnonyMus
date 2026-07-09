import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

from transports.p2p import database as database

database.DB_FILE = "test_legacy_migration.db"
from transports.p2p import server as server


class TestLegacyMigration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = "test_legacy_migration.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config["TESTING"] = True
        server.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = server.app.test_client()
        database.init_db()
        database.register_local_user("testuser", "password")

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = "test_legacy_migration.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def setUp(self):
        # Clear database
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM messages")
        c.execute("DELETE FROM contacts")
        c.execute('DELETE FROM config WHERE key LIKE "my_pubkey_for_%"')
        conn.commit()
        conn.close()

        # Log in
        self.client.post(
            "/login", json={"username": "testuser", "password": "password"}
        )

    @patch("transports.p2p.tor_manager.add_onion_service")
    def test_run_legacy_migration_startup_helper(self, mock_add_service):
        mock_add_service.return_value = "pairwisefriend22.onion"

        # Set up a main onion address config
        database.set_config("my_onion_address", "mainserver234567.onion")

        # Add a legacy contact (my_onion_address is NULL or same as main server)
        database.add_contact(
            "friendold2345677.onion",
            "FriendNickname",
            status="accepted",
            my_onion_address="mainserver234567.onion",
        )

        # Verify legacy contact exists in DB
        contact = database.get_contact("friendold2345677.onion")
        self.assertEqual(contact["my_onion_address"], "mainserver234567.onion")

        # Run migration helper
        server.run_legacy_migration()

        # Verify contact's my_onion_address was updated to the new pairwise onion
        contact = database.get_contact("friendold2345677.onion")
        self.assertEqual(contact["my_onion_address"], "pairwisefriend22.onion")
        mock_add_service.assert_called_once()

    def test_migrate_contact_endpoint(self):
        old_onion = "legacyfriend2345.onion"
        new_onion = "pairwisefriend22.onion"

        # Add contact and config pubkey
        database.add_contact(old_onion, "FriendNickname", status="accepted")
        database.set_config(f"my_pubkey_for_{old_onion}", "mockpubkey")

        # Save a message for this contact
        database.save_message(old_onion, "me", "test content", 123456789)

        # Verify they exist
        self.assertIsNotNone(database.get_contact(old_onion))
        self.assertEqual(len(database.get_messages(old_onion)), 1)
        self.assertEqual(
            database.get_config(f"my_pubkey_for_{old_onion}"), "mockpubkey"
        )

        # Call migration endpoint
        res = self.client.post(
            "/api/contacts/migrate",
            json={"old_address": old_onion, "new_address": new_onion},
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

        # Verify old address is gone, new address has the contact and data
        self.assertIsNone(database.get_contact(old_onion))
        contact = database.get_contact(new_onion)
        self.assertIsNotNone(contact)
        self.assertEqual(contact["nickname"], "FriendNickname")

        # Verify messages moved to the new address
        self.assertEqual(len(database.get_messages(old_onion)), 0)
        self.assertEqual(len(database.get_messages(new_onion)), 1)

        # Verify config key moved
        self.assertIsNone(database.get_config(f"my_pubkey_for_{old_onion}"))
        self.assertEqual(
            database.get_config(f"my_pubkey_for_{new_onion}"), "mockpubkey"
        )


if __name__ == "__main__":
    unittest.main()
