import os
import sys
import unittest

# Ensure project root directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ["FLASK_SECRET_KEY"] = "test-secret-key"

from transports.relay import server


class TestIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.app.config["TESTING"] = True
        server.app.config["WTF_CSRF_ENABLED"] = False
        cls.client = server.app.test_client()

    def test_anonymous_socket_queue_flow(self):
        # Test direct socket connection without login
        socket_client = server.socketio.test_client(
            server.app, flask_test_client=self.client
        )
        self.assertTrue(socket_client.is_connected())

        # Create queue
        socket_client.emit("create_queue")
        received = socket_client.get_received()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["name"], "queue_created")
        queue_id = received[0]["args"][0]["queue_id"]

        # Push to queue
        socket_client.emit(
            "push_queue", {"queue_id": queue_id, "payload": "test_payload"}
        )
        received = socket_client.get_received()
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["name"], "queue_payload")
        self.assertEqual(received[0]["args"][0]["payload"], "test_payload")

        socket_client.disconnect()

    def test_offline_queue_store_and_forward(self):
        """10.C.1: Messages pushed to an offline queue are buffered and delivered on reconnect."""
        # Creator creates their queue, then disconnects (simulates going offline)
        creator = server.socketio.test_client(server.app, flask_test_client=self.client)
        creator.emit("create_queue")
        recv = creator.get_received()
        creator_queue_id = recv[0]["args"][0]["queue_id"]
        creator.disconnect()

        # Sender creates their own queue, then registers creator's queue as peer target
        sender = server.socketio.test_client(server.app, flask_test_client=self.client)
        sender.emit("create_queue")
        recv = sender.get_received()
        sender_queue_id = recv[0]["args"][0]["queue_id"]

        sender.emit(
            "register_peer",
            {"my_queue": sender_queue_id, "peer_queue": creator_queue_id},
        )
        sender.get_received()

        # Push to creator's (offline) queue — expect recipient_offline_queued
        sender.emit(
            "push_queue", {"queue_id": creator_queue_id, "payload": "offline_message"}
        )
        recv = sender.get_received()
        error_events = [e for e in recv if e["name"] == "push_queue_error"]
        self.assertTrue(
            len(error_events) > 0, f"Expected push_queue_error, got: {recv}"
        )
        self.assertEqual(
            error_events[0]["args"][0]["error"], "recipient_offline_queued"
        )
        sender.disconnect()

        # Creator reconnects and uses rejoin_queue to reclaim their queue_id
        creator2 = server.socketio.test_client(
            server.app, flask_test_client=self.client
        )
        creator2.emit("rejoin_queue", {"queue_id": creator_queue_id})
        recv = creator2.get_received()

        names = [e["name"] for e in recv]
        self.assertIn("queue_rejoined", names)
        payloads = [
            e["args"][0].get("payload") for e in recv if e["name"] == "queue_payload"
        ]
        self.assertIn(
            "offline_message",
            payloads,
            f"Expected offline_message in payloads, got events: {recv}",
        )
        creator2.disconnect()


if __name__ == "__main__":
    unittest.main()
