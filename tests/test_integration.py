import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ['DATABASE_URL'] = ''
os.environ['FLASK_SECRET_KEY'] = 'test-secret-key'

import server
import database
database.DB_FILE = 'test_users_integration.db'

class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config['TESTING'] = True
        cls.client = server.app.test_client()
        database.init_db()
        database.register_user('testuser', 'password')
        
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
        
        # Create queue
        socket_client.emit('create_queue')
        received = socket_client.get_received()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['name'], 'queue_created')
        queue_id = received[0]['args'][0]['queue_id']
        
        # Push to queue
        socket_client.emit('push_queue', {'queue_id': queue_id, 'payload': 'test_payload'})
        received = socket_client.get_received()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['name'], 'queue_payload')
        self.assertEqual(received[0]['args'][0]['payload'], 'test_payload')
        
        socket_client.disconnect()

if __name__ == '__main__':
    unittest.main()
