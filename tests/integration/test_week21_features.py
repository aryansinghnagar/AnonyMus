import os
import sys
import unittest
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ['FLASK_SECRET_KEY'] = 'test-secret-key'

from transports.p2p import database as database
database.DB_FILE = 'test_week21_integration.db'
from transports.p2p import server as server

class TestWeek21Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = 'test_week21_integration.db'
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
        database.DB_FILE = 'test_week21_integration.db'
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def login(self):
        res = self.client.post('/login', json={'username': 'testuser', 'password': 'password'})
        self.assertEqual(res.status_code, 200)

    def test_profiles_lifecycle(self):
        self.login()
        
        # 1. Verify active profile initially is 'default'
        res = self.client.get('/api/profiles/active')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['profile_id'], 'default')

        # 2. Create Profile 1 (Public Work Profile)
        res = self.client.post('/api/profiles/create', json={
            'display_name': 'Work Profile',
            'hidden': 0
        })
        self.assertEqual(res.status_code, 200)
        work_id = res.get_json()['profile_id']
        self.assertIsNotNone(work_id)

        # 3. Create Profile 2 (Hidden Decoy Profile)
        res = self.client.post('/api/profiles/create', json={
            'display_name': 'Secret Profile',
            'hidden': 1,
            'passphrase': 'supersecretpass'
        })
        self.assertEqual(res.status_code, 200)
        secret_id = res.get_json()['profile_id']
        self.assertIsNotNone(secret_id)

        # 4. Fetch profiles: should show 'Default' and 'Work', but NOT 'Secret'
        res = self.client.get('/api/profiles')
        self.assertEqual(res.status_code, 200)
        profiles = res.get_json()
        profile_ids = [p['profile_id'] for p in profiles]
        self.assertIn('default', profile_ids)
        self.assertIn(work_id, profile_ids)
        self.assertNotIn(secret_id, profile_ids)

        # 5. Switch to Work Profile
        res = self.client.post('/api/profiles/switch', json={'profile_id': work_id})
        self.assertEqual(res.status_code, 200)
        
        res = self.client.get('/api/profiles/active')
        self.assertEqual(res.get_json()['profile_id'], work_id)

        # Add a contact to Work Profile
        res = self.client.post('/api/contacts/add', json={
            'onion_address': 'workcontactonionaddress.onion',
            'nickname': 'Work Colleague',
            'my_public_key': 'PublicKeyBase64String'
        })
        self.assertEqual(res.status_code, 200)

        # 6. Switch back to Default Profile
        res = self.client.post('/api/profiles/switch', json={'profile_id': 'default'})
        self.assertEqual(res.status_code, 200)
        
        # Verify Work Profile contact is not listed under default profile
        res = self.client.get('/api/contacts')
        contacts = res.get_json()
        self.assertFalse(any(c['onion_address'] == 'workcontactonionaddress.onion' for c in contacts))

        # 7. Switch back to Work Profile and verify contact is listed
        self.client.post('/api/profiles/switch', json={'profile_id': work_id})
        res = self.client.get('/api/contacts')
        contacts = res.get_json()
        self.assertTrue(any(c['onion_address'] == 'workcontactonionaddress.onion' for c in contacts))

        # 8. Attempt to unlock hidden profile with incorrect password
        res = self.client.post('/api/profiles/unlock', json={'passphrase': 'wrongpassword'})
        self.assertEqual(res.status_code, 401)

        # 9. Unlock hidden profile with correct password
        res = self.client.post('/api/profiles/unlock', json={'passphrase': 'supersecretpass'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['profile']['profile_id'], secret_id)

        # Verify active profile is now 'Secret Profile'
        res = self.client.get('/api/profiles/active')
        self.assertEqual(res.get_json()['profile_id'], secret_id)

    def test_message_batching(self):
        self.login()
        # Create accepted contact to send to
        onion = 'recipientpeerforbatching.onion'
        database.add_contact(onion, 'Recipient', status='accepted')
        
        # 1. Send message batch
        events = [
            {'iv': 'iv1', 'ciphertext': 'ciphertext1', 'seq': 1},
            {'iv': 'iv2', 'ciphertext': 'ciphertext2', 'seq': 2}
        ]
        res = self.client.post('/api/messages/send_batch', json={
            'onion_address': onion,
            'events': events
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])

        # Verify messages saved locally
        msgs = database.get_messages(onion)
        self.assertEqual(len(msgs), 2)
        self.assertIn('ciphertext1', msgs[0]['message'])
        self.assertIn('ciphertext2', msgs[1]['message'])
        
        # 2. Receive batch simulating remote peer sending to us
        sender_onion = 'senderpeerforbatching.onion'
        database.add_contact(sender_onion, 'Sender', status='accepted')
        
        res = self.client.post('/p2p/message/batch', json={
            'sender': sender_onion,
            'timestamp': int(time.time() * 1000),
            'events': [
                {'iv': 'iv3', 'ciphertext': 'ciphertext3', 'seq': 1},
                {'iv': 'iv4', 'ciphertext': 'ciphertext4', 'seq': 2}
            ]
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()['status'], 'delivered')

        # Verify received messages saved locally
        received_msgs = database.get_messages(sender_onion)
        self.assertEqual(len(received_msgs), 2)
        self.assertIn('ciphertext3', received_msgs[0]['message'])
        self.assertIn('ciphertext4', received_msgs[1]['message'])
