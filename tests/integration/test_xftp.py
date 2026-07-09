import os
import sys
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

from transports.p2p import database as database, server as server


class TestXFTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.DB_FILE = "test_xftp_integration.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)
        server.app.config["TESTING"] = True
        server.app.config["WTF_CSRF_ENABLED"] = False
        server.app.config["RATELIMIT_ENABLED"] = False
        server.limiter.enabled = False
        cls.client = server.app.test_client()
        database.init_db()
        database.register_local_user("xftpuser", "password")

    @classmethod
    def tearDownClass(cls):
        database.DB_FILE = "test_xftp_integration.db"
        if os.path.exists(database.DB_FILE):
            os.remove(database.DB_FILE)

    def setUp(self):
        # Clear the server's in-memory chunk store before each test
        with server.file_chunks_lock:
            server.file_chunks.clear()

    def test_upload_and_download_flow_relay(self):
        # Login first to authenticate local session
        res = self.client.post(
            "/login", json={"username": "xftpuser", "password": "password"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])

        # Upload a chunk
        chunk_id = "test-chunk-123"
        chunk_data = b"Hello, this is a decrypted file chunk."

        upload_res = self.client.post(
            f"/api/file/upload/{chunk_id}",
            data=chunk_data,
            content_type="application/octet-stream",
        )
        self.assertEqual(upload_res.status_code, 200)
        self.assertTrue(upload_res.get_json()["success"])

        # Verify it exists in server memory
        with server.file_chunks_lock:
            self.assertIn(chunk_id, server.file_chunks)
            self.assertEqual(server.file_chunks[chunk_id]["data"], chunk_data)

        # Download the chunk
        download_res = self.client.get(f"/api/file/download/{chunk_id}")
        self.assertEqual(download_res.status_code, 200)
        self.assertEqual(download_res.data, chunk_data)

        # Verify it is deleted on download (single-download constraint)
        with server.file_chunks_lock:
            self.assertNotIn(chunk_id, server.file_chunks)

    def test_upload_chunk_size_limit(self):
        # Login first
        self.client.post(
            "/login", json={"username": "xftpuser", "password": "password"}
        )

        # Limit is ~16KB (16500 bytes). Let's try to upload 20KB chunk.
        large_data = b"A" * 20000
        chunk_id = "too-large-chunk"

        res = self.client.post(
            f"/api/file/upload/{chunk_id}",
            data=large_data,
            content_type="application/octet-stream",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("exceeds maximum limit", res.get_json()["error"])

    def test_unauthorized_access(self):
        # Logout / clear session by re-instantiating test client
        self.client = server.app.test_client()

        # Try uploading
        res_upload = self.client.post(
            "/api/file/upload/unauth-chunk",
            data=b"data",
            content_type="application/octet-stream",
        )
        self.assertEqual(res_upload.status_code, 401)

        # Try downloading
        res_download = self.client.get("/api/file/download/unauth-chunk")
        self.assertEqual(res_download.status_code, 401)

    def test_public_p2p_endpoints(self):
        # P2P public endpoints (/p2p/*) do not require authenticated session cookie
        self.client = server.app.test_client()

        chunk_id = "public-chunk"
        chunk_data = b"public-data"

        upload_res = self.client.post(
            f"/p2p/file/upload/{chunk_id}",
            data=chunk_data,
            content_type="application/octet-stream",
        )
        self.assertEqual(upload_res.status_code, 200)
        self.assertTrue(upload_res.get_json()["success"])

        download_res = self.client.get(f"/p2p/file/download/{chunk_id}")
        self.assertEqual(download_res.status_code, 200)
        self.assertEqual(download_res.data, chunk_data)

    def test_chunk_expiration_sweeper(self):
        # Upload an expired chunk by mocking the time
        chunk_id = "expired-chunk"
        with server.file_chunks_lock:
            server.file_chunks[chunk_id] = {
                "data": b"expired-data",
                "expires_at": time.time() - 100,  # expired 100s ago
            }

        # Login
        self.client.post(
            "/login", json={"username": "xftpuser", "password": "password"}
        )

        # Try downloading expired chunk
        res = self.client.get(f"/api/file/download/{chunk_id}")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
