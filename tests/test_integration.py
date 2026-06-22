import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ['DATABASE_URL'] = ''
os.environ['FLASK_SECRET_KEY'] = 'test-secret-key'

import database
database.DB_FILE = 'test_users_integration.db'
import server

class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config['TESTING'] = True
        cls.client = server.app.test_client()
        database.init_db()
        database.register_local_user('testuser', 'password')
        
    @classmethod
    def tearDownClass(cls):
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def test_auth_flow_and_socket(self):
        # Test login
        res = self.client.post('/login', json={'username': 'testuser', 'password': 'password'})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        
        # Test socket lifecycle
        socket_client = server.socketio.test_client(server.app, flask_test_client=self.client)
        self.assertTrue(socket_client.is_connected())
        
        # Add contact API check
        contact_data = {
            'onion_address': 'abcdefghijklmnop.onion',
            'nickname': 'testfriend',
            'my_public_key': 'mock_public_key'
        }
        res = self.client.post('/api/contacts/add', json=contact_data)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        
        # Check contact was added to DB
        contact = database.get_contact('abcdefghijklmnop.onion')
        self.assertIsNotNone(contact)
        self.assertEqual(contact['nickname'], 'testfriend')
        
        # Fetch contacts list
        res = self.client.get('/api/contacts')
        self.assertEqual(res.status_code, 200)
        contacts = res.get_json()
        self.assertEqual(len(contacts), 1)
        self.assertEqual(contacts[0]['onion_address'], 'abcdefghijklmnop.onion')
        
        socket_client.disconnect()

if __name__ == '__main__':
    unittest.main()
