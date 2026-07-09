"""
Tests for the Notification Queue (10.H.3).
Verifies push/poll/clear lifecycle, no cross-contamination between tokens,
and empty-input edge cases.
"""

import os
import sys
import tempfile
import unittest

# Make project root importable
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
)

from transports.p2p import database

# ---------------------------------------------------------------------------
# Test setup: shared in-memory DB (isolated per test class)
# ---------------------------------------------------------------------------

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "schema_p2p.sql")
TEST_ONION_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.onion"
TEST_ONION_B = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.onion"


def _setup_db(tmp_path: str):
    """Create a fresh test DB from schema_p2p.sql."""
    import sqlite3

    db_path = os.path.join(tmp_path, "test_notify.db")
    with open(SCHEMA_PATH) as f:
        schema_sql = f.read()
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    database.DB_FILE = db_path
    return db_path


class TestNotifyQueueDatabase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        _setup_db(self._tmpdir)
        # Seed two contacts
        database.add_contact(TEST_ONION_A, "Alice", status="active")
        database.add_contact(TEST_ONION_B, "Bob", status="active")

    def tearDown(self):
        import shutil

        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # -----------------------------------------------------------------------
    # Token management
    # -----------------------------------------------------------------------

    def test_set_and_get_notify_token(self):
        """set_notify_token / get_notify_token round-trip."""
        database.set_notify_token(TEST_ONION_A, "TOKEN_A")
        self.assertEqual(database.get_notify_token(TEST_ONION_A), "TOKEN_A")

    def test_get_notify_token_unregistered(self):
        """get_notify_token returns None for a contact with no token."""
        self.assertIsNone(database.get_notify_token(TEST_ONION_A))

    def test_overwrite_notify_token(self):
        """Setting a new token overwrites the old one."""
        database.set_notify_token(TEST_ONION_A, "TOKEN_OLD")
        database.set_notify_token(TEST_ONION_A, "TOKEN_NEW")
        self.assertEqual(database.get_notify_token(TEST_ONION_A), "TOKEN_NEW")

    # -----------------------------------------------------------------------
    # Push / poll / clear lifecycle
    # -----------------------------------------------------------------------

    def test_poll_empty(self):
        """Polling with no flags returns empty dict (no pending)."""
        result = database.poll_notify_queue(["TOKEN_A"])
        self.assertEqual(result, set())

    def test_push_then_poll(self):
        """Pushing a flag makes it visible to poll."""
        database.push_notify_queue("TOKEN_A")
        result = database.poll_notify_queue(["TOKEN_A"])
        self.assertIn("TOKEN_A", result)

    def test_push_then_clear_then_poll(self):
        """After clear, the flag is no longer returned by poll."""
        database.push_notify_queue("TOKEN_A")
        database.clear_notify_queue(["TOKEN_A"])
        result = database.poll_notify_queue(["TOKEN_A"])
        self.assertNotIn("TOKEN_A", result)

    def test_multiple_pushes_deduplicated_in_poll(self):
        """Multiple pushes for the same token produce exactly one entry in poll result."""
        database.push_notify_queue("TOKEN_A")
        database.push_notify_queue("TOKEN_A")
        database.push_notify_queue("TOKEN_A")
        result = database.poll_notify_queue(["TOKEN_A"])
        self.assertEqual(result, {"TOKEN_A"})

    def test_no_cross_contamination(self):
        """A flag for token A must not appear in poll results for token B."""
        database.push_notify_queue("TOKEN_A")
        result = database.poll_notify_queue(["TOKEN_B"])
        self.assertNotIn("TOKEN_A", result)
        self.assertNotIn("TOKEN_B", result)

    def test_poll_multiple_tokens(self):
        """Poll correctly separates pending vs. not-pending tokens."""
        database.push_notify_queue("TOKEN_A")
        result = database.poll_notify_queue(["TOKEN_A", "TOKEN_B"])
        self.assertIn("TOKEN_A", result)
        self.assertNotIn("TOKEN_B", result)

    def test_clear_only_targeted_tokens(self):
        """clear_notify_queue only removes the specified tokens' flags."""
        database.push_notify_queue("TOKEN_A")
        database.push_notify_queue("TOKEN_B")
        database.clear_notify_queue(["TOKEN_A"])
        self.assertNotIn("TOKEN_A", database.poll_notify_queue(["TOKEN_A"]))
        self.assertIn("TOKEN_B", database.poll_notify_queue(["TOKEN_B"]))

    # -----------------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------------

    def test_poll_empty_token_list(self):
        """Polling with no tokens returns empty set."""
        self.assertEqual(database.poll_notify_queue([]), set())

    def test_clear_empty_token_list(self):
        """Clearing with no tokens is a no-op (no exception)."""
        database.push_notify_queue("TOKEN_A")
        database.clear_notify_queue([])  # must not raise
        self.assertIn("TOKEN_A", database.poll_notify_queue(["TOKEN_A"]))

    def test_clear_nonexistent_token(self):
        """Clearing a non-existent token is a no-op (no exception)."""
        database.clear_notify_queue(["TOKEN_MISSING"])  # must not raise


if __name__ == "__main__":
    unittest.main()
