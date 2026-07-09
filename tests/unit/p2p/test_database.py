import os
import sys
import time
import unittest

# Ensure project root directory is in path
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from transports.p2p import database

database.DB_FILE = "test_users.db"


class TestDatabaseAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = "test_users.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = "test_users.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def test_1_register_user(self):
        res = database.register_local_user("Alice", "password123")
        self.assertTrue(res.get("success"))

        # Test duplicate (since already initialized, should say already initialized)
        res = database.register_local_user("bob", "different")
        self.assertEqual(res.get("error"), "Local database is already initialized.")

    def test_2_login_user(self):
        res = database.login_local_user("alice", "password123")
        self.assertTrue(res.get("success"))

        res = database.login_local_user("ALICE", "wrongpassword")
        self.assertEqual(res.get("error"), "Wrong credentials.")

    def test_3_login_oracle_timing(self):
        # Time a known user with wrong password
        t0 = time.time()
        database.login_local_user("alice", "wrongpassword")
        t1 = time.time()
        time_known = t1 - t0

        # Time an unknown user
        t2 = time.time()
        database.login_local_user("unknown_user", "password")
        t3 = time.time()
        time_unknown = t3 - t2

        # They should both be taking bcrypt time, typically >0.01s
        self.assertGreater(time_known, 0.01)
        self.assertGreater(time_unknown, 0.01)

        # The difference should be relatively small
        ratio = max(time_known, time_unknown) / min(time_known, time_unknown)
        self.assertLess(ratio, 5.0, "Timing difference too large, possible oracle leak")

    def test_4_login_lockout(self):
        # Reset any active lockout or attempts
        database.set_config("failed_login_attempts", "0")
        database.set_config("lockout_until", "")

        # 4 failed attempts should not trigger lockout
        for _ in range(4):
            res = database.login_local_user("alice", "wrongpassword")
            self.assertEqual(res.get("error"), "Wrong credentials.")

        # 5th failed attempt should trigger lockout
        res = database.login_local_user("alice", "wrongpassword")
        self.assertEqual(res.get("error"), "Wrong credentials.")
        self.assertEqual(database.get_config("failed_login_attempts"), "5")
        self.assertIsNotNone(database.get_config("lockout_until"))

        # Subsequent attempts should return locked message
        res = database.login_local_user("alice", "wrongpassword")
        self.assertIn("Account is locked", res.get("error"))

        # Resetting/logging in successfully resets attempts
        database.set_config("failed_login_attempts", "0")
        database.set_config("lockout_until", "")
        res = database.login_local_user("alice", "password123")
        self.assertTrue(res.get("success"))
        self.assertEqual(database.get_config("failed_login_attempts"), "0")


if __name__ == "__main__":
    unittest.main()
