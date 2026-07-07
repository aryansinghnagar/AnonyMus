import os
import sys
import unittest
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ['FLASK_SECRET_KEY'] = 'test-secret-key'

from transports.p2p import database as database
database.DB_FILE = 'test_week19_integration.db'
from transports.p2p import server as server

class TestWeek19Groups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = 'test_week19_integration.db'
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
        database.DB_FILE = 'test_week19_integration.db'
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def login(self):
        res = self.client.post('/login', json={'username': 'testuser', 'password': 'password'})
        self.assertEqual(res.status_code, 200)

    def test_group_lifecycle(self):
        self.login()
        founder_onion = 'founderonionaddress.onion'
        
        # 1. Create a group
        res = self.client.post('/api/groups/create', json={
            'name': 'Test Cryptography Group',
            'founder_onion': founder_onion
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        group_id = data.get('group_id')
        self.assertIsNotNone(group_id)

        # 2. Get groups list and verify
        res = self.client.get('/api/groups')
        self.assertEqual(res.status_code, 200)
        groups = res.get_json()
        self.assertTrue(any(g['group_id'] == group_id for g in groups))

        # 3. Add a member
        member_onion = 'memberonionaddress.onion'
        res = self.client.post('/api/groups/add_member', json={
            'group_id': group_id,
            'member_onion': member_onion,
            'nickname': 'Bob',
            'role': 'member'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get('success'))

        # 4. Get group details and verify members
        res = self.client.get(f'/api/groups/{group_id}')
        self.assertEqual(res.status_code, 200)
        details = res.get_json()
        self.assertEqual(details['group']['name'], 'Test Cryptography Group')
        self.assertEqual(len(details['members']), 2) # Founder + Bob
        
        # Verify roles
        roles = {m['member_onion']: m['role'] for m in details['members']}
        self.assertEqual(roles[founder_onion], 'founder')
        self.assertEqual(roles[member_onion], 'member')

        # 5. Save and retrieve group messages
        ts = 1600000000
        res = self.client.post('/api/groups/save_message', json={
            'group_id': group_id,
            'sender_onion': founder_onion,
            'sender_nickname': 'Founder',
            'message': 'Hello decentralized world!',
            'timestamp': ts
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get('success'))

        res = self.client.get(f'/api/groups/{group_id}/messages')
        self.assertEqual(res.status_code, 200)
        messages = res.get_json()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['message'], 'Hello decentralized world!')
        self.assertEqual(messages[0]['sender_nickname'], 'Founder')

        # 6. Generate and use invite token
        res = self.client.post('/api/groups/invite', json={'group_id': group_id})
        self.assertEqual(res.status_code, 200)
        invite_data = res.get_json()
        self.assertTrue(invite_data.get('success'))
        token = invite_data.get('token')
        self.assertIsNotNone(token)

        # Use the invite token
        res = self.client.post('/api/groups/use_invite', json={'token': token})
        self.assertEqual(res.status_code, 200)
        use_data = res.get_json()
        self.assertTrue(use_data.get('success'))
        self.assertEqual(use_data.get('group_id'), group_id)

        # Use invalid/already-used token should fail
        res = self.client.post('/api/groups/use_invite', json={'token': token})
        self.assertEqual(res.status_code, 400)

        # 7. Add vouches and fetch trust graph status
        res = self.client.post('/api/groups/vouch', json={
            'group_id': group_id,
            'vouching_member': founder_onion,
            'vouched_member': member_onion
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get('success'))

        res = self.client.get(f'/api/groups/{group_id}/vouches')
        self.assertEqual(res.status_code, 200)
        vouches = res.get_json()
        self.assertEqual(len(vouches), 1)
        self.assertEqual(vouches[0]['vouching_member'], founder_onion)
        self.assertEqual(vouches[0]['vouched_member'], member_onion)

        # 8. Remove a member
        res = self.client.post('/api/groups/remove_member', json={
            'group_id': group_id,
            'member_onion': member_onion
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get('success'))

        res = self.client.get(f'/api/groups/{group_id}')
        self.assertEqual(res.status_code, 200)
        details = res.get_json()
        self.assertEqual(len(details['members']), 1) # Only Founder remaining
