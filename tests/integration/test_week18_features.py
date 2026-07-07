import os
import sys
import unittest
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ['FLASK_SECRET_KEY'] = 'test-secret-key'

from transports.p2p import database as database
database.DB_FILE = 'test_week18_integration.db'
from transports.p2p import server as server

class TestWeek18Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = 'test_week18_integration.db'
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config['TESTING'] = True
        server.app.config['WTF_CSRF_ENABLED'] = False
        server.app.config['RATELIMIT_ENABLED'] = False
        server.limiter.enabled = False
        cls.client = server.app.test_client()
        database.init_db()
        database.register_local_user('testuser', 'password')
        
    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = 'test_week18_integration.db'
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def login(self):
        res = self.client.post('/login', json={'username': 'testuser', 'password': 'password'})
        self.assertEqual(res.status_code, 200)

    def test_preferred_relay_api(self):
        self.login()
        
        # Test default/empty preferred relay
        res = self.client.get('/api/settings/preferred_relay')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['preferred_file_relay'], '')

        # Save preferred relay
        res = self.client.post('/api/settings/preferred_relay', json={'preferred_file_relay': 'http://my-relay.onion'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        # Read back
        res = self.client.get('/api/settings/preferred_relay')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['preferred_file_relay'], 'http://my-relay.onion')

    def test_send_receipts_toggle(self):
        self.login()
        onion = 'xyzxyzxyzxyzxyzx.onion'
        database.add_contact(onion, 'xyzfriend', status='accepted')

        # Toggle receipts off
        res = self.client.post('/api/contacts/update_receipts', json={'onion_address': onion, 'send_receipts': False})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        # Verify in DB
        contact = database.get_contact(onion)
        self.assertEqual(contact['send_receipts'], 0)

        # Toggle receipts on
        res = self.client.post('/api/contacts/update_receipts', json={'onion_address': onion, 'send_receipts': True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        
        contact = database.get_contact(onion)
        self.assertEqual(contact['send_receipts'], 1)

    def test_message_edits_and_deletes(self):
        self.login()
        onion = 'xyzxyzxyzxyzxyzx.onion'
        database.add_contact(onion, 'xyzfriend', status='accepted')
        timestamp = 1234567890

        # Save a test message
        message_payload = {"iv": "mock_iv", "ciphertext": "mock_ciphertext", "seq": 1}
        database.save_message(onion, 'You', json.dumps(message_payload), timestamp)

        # Retrieve message and verify delivery_state is default ('sent')
        msgs = database.get_messages(onion)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]['delivery_state'], 'sent')

        # Update delivery state to read
        res = self.client.post('/api/messages/receipt', json={'onion_address': onion, 'timestamp': timestamp, 'state': 'read'})
        self.assertEqual(res.status_code, 200)
        
        msgs = database.get_messages(onion)
        self.assertEqual(msgs[0]['delivery_state'], 'read')

        # Edit message
        res = self.client.post('/api/messages/edit', json={'onion_address': onion, 'timestamp': timestamp, 'message': 'New edited message text'})
        self.assertEqual(res.status_code, 200)

        # Verify edit history is saved
        res = self.client.get(f'/api/messages/edits?onion_address={onion}&timestamp={timestamp}')
        self.assertEqual(res.status_code, 200)
        edits = res.get_json()['edits']
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]['old_text'], json.dumps(message_payload))

        # Delete message
        res = self.client.post('/api/messages/delete', json={'onion_address': onion, 'timestamp': timestamp})
        self.assertEqual(res.status_code, 200)

        # Verify message is gone from database
        msgs = database.get_messages(onion)
        self.assertEqual(len(msgs), 0)

if __name__ == '__main__':
    unittest.main()
