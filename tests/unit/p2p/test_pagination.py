import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from transports.p2p import database as database
database.DB_FILE = 'test_pagination.db'

class TestPagination(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = 'test_pagination.db'
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        database.init_db()
        database.register_local_user('testuser', 'password')
        database.add_contact('peer.onion', 'Peer', status='accepted')
        
        # Insert 10 test messages
        for i in range(10):
            database.save_message('peer.onion', 'peer.onion', f"Message {i}", 1000 + i)

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = 'test_pagination.db'
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def test_get_messages_no_pagination(self):
        msgs = database.get_messages('peer.onion')
        self.assertEqual(len(msgs), 10)
        self.assertEqual(msgs[0]['message'], "Message 0")
        self.assertEqual(msgs[-1]['message'], "Message 9")

    def test_get_messages_limit(self):
        msgs = database.get_messages('peer.onion', limit=5)
        self.assertEqual(len(msgs), 5)
        self.assertEqual(msgs[0]['message'], "Message 0")
        self.assertEqual(msgs[-1]['message'], "Message 4")

    def test_get_messages_offset(self):
        msgs = database.get_messages('peer.onion', limit=3, offset=2)
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0]['message'], "Message 2")
        self.assertEqual(msgs[-1]['message'], "Message 4")

if __name__ == '__main__':
    unittest.main()
