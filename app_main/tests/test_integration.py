import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ['DATABASE_URL'] = ''
os.environ['FLASK_SECRET_KEY'] = 'test-secret-key'

import app_main.server as server
import app_main.database as database
database.DB_FILE = 'test_users_integration.db'

class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config['TESTING'] = True
        cls.client = server.app.test_client()
        database.init_db()
        database.register_user('testuser', 'TestPass123!')
        
    @classmethod
    def tearDownClass(cls):
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def test_auth_flow_and_socket(self):
        # Test login
        res = self.client.post('/login', json={'username': 'testuser', 'password': 'TestPass123!'})
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
        
        # Test push_queue error: unauthorized queue
        socket_client.emit('push_queue', {'queue_id': 'some-other-queue', 'payload': 'test'})
        received = socket_client.get_received()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['name'], 'push_queue_error')
        self.assertEqual(received[0]['args'][0]['error'], 'unauthorized')

        # Test push_queue error: too large payload
        large_payload = 'a' * (100 * 1024 + 1)
        socket_client.emit('push_queue', {'queue_id': queue_id, 'payload': large_payload})
        received = socket_client.get_received()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['name'], 'push_queue_error')
        self.assertEqual(received[0]['args'][0]['error'], 'payload_too_large')

        # Test push_queue error: invalid payload (missing payload or queue_id)
        socket_client.emit('push_queue', {'queue_id': queue_id})
        received = socket_client.get_received()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]['name'], 'push_queue_error')
        self.assertEqual(received[0]['args'][0]['error'], 'invalid_payload')
        
        socket_client.disconnect()

if __name__ == '__main__':
    unittest.main()
