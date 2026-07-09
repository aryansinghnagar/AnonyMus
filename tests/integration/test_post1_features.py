import os
import sys
import unittest
import json
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
os.environ['FLASK_SECRET_KEY'] = 'test-secret-key'

from transports.p2p import database as database
database.DB_FILE = 'test_post1_integration.db'
from transports.p2p import server as server
from core.crypto import generate_supporter_badge_signature, DEVELOPER_PUBLIC_KEY_B64

class TestPost1Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = 'test_post1_integration.db'
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
        database.DB_FILE = 'test_post1_integration.db'
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def login(self):
        res = self.client.post('/login', json={'username': 'testuser', 'password': 'password'})
        self.assertEqual(res.status_code, 200)

    def test_channels_broadcast(self):
        self.login()
        # 1. Create a channel
        res = self.client.post('/api/groups/create', json={
            'name': 'Founder Channel',
            'founder_onion': 'founderaddress.onion',
            'is_channel': 1
        })
        self.assertEqual(res.status_code, 200)
        group_id = res.get_json()['group_id']
        
        # 2. Add founder and a member to group
        database.add_group_member(group_id, 'founderaddress.onion', 'Founder', 'founder')
        database.add_group_member(group_id, 'memberaddress.onion', 'Member', 'member')
        
        # 3. Post message as founder -> should succeed
        res = self.client.post('/api/groups/save_message', json={
            'group_id': group_id,
            'sender_onion': 'founderaddress.onion',
            'sender_nickname': 'Founder',
            'message': 'Hello from founder!',
            'timestamp': int(time.time() * 1000)
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        
        # 4. Post message as member -> should fail with 403
        res = self.client.post('/api/groups/save_message', json={
            'group_id': group_id,
            'sender_onion': 'memberaddress.onion',
            'sender_nickname': 'Member',
            'message': 'Hello from member!',
            'timestamp': int(time.time() * 1000)
        })
        self.assertEqual(res.status_code, 403)

    def test_supporter_badges(self):
        self.login()
        onion_address = 'supporteraddress.onion'
        dev_priv_key_b64 = '5ZOf4PhdTNRUN0YDwX/Clf5rgoTuLa1YQz3UtbyrUj4='
        
        # 1. Check initially status is false
        res = self.client.get(f'/api/profile/supporter_badge/status?onion_address={onion_address}')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.get_json()['is_supporter'])
        
        # 2. Verify with invalid signature -> should fail
        res = self.client.post('/api/profile/supporter_badge', json={
            'onion_address': onion_address,
            'signature': 'invalid_signature_string'
        })
        self.assertEqual(res.status_code, 400)
        self.assertIn('error', res.get_json())
        
        # 3. Generate valid signature and verify -> should succeed
        sig = generate_supporter_badge_signature(onion_address, dev_priv_key_b64)
        res = self.client.post('/api/profile/supporter_badge', json={
            'onion_address': onion_address,
            'signature': sig
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        
        # 4. Verify status is now true
        res = self.client.get(f'/api/profile/supporter_badge/status?onion_address={onion_address}')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['is_supporter'])

    def test_abuse_reporting(self):
        self.login()
        res = self.client.post('/api/groups/report_message', json={
            'message_hash': 'testmessagehash123',
            'reporter_onion': 'reporter.onion',
            'reason': 'Spam/Abuse',
            'signature': 'report_sig'
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()['success'])
        
        # Verify in database
        reports = database.get_abuse_reports()
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]['message_hash'], 'testmessagehash123')
