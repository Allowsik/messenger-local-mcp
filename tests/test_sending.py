import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from messenger_mcp.core import App, MatrixError
from messenger_mcp.sending import send_text, send_status, approve


class SendingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "config.json"
        path.write_text(json.dumps({"homeserver": "http://127.0.0.1:9", "user_id": "@owner:test",
            "allowed_rooms": {"!room:test": "Synthetic contact"}, "send_mode": "direct"}), encoding="utf-8")
        self.app = App(path)
        self.client = Mock(token="synthetic-session-token")
        self.client.request.return_value = {"event_id": "$synthetic"}
        self.app.matrix = Mock(return_value=self.client)

    def tearDown(self):
        self.tmp.cleanup()

    def test_same_request_is_sent_once(self):
        first = send_text(self.app, "!room:test", "Hello", "request-test-1")
        second = send_text(self.app, "!room:test", "Hello", "request-test-1")
        self.assertEqual(first["event_id"], second["event_id"])
        self.client.request.assert_called_once()

    def test_reusing_id_for_another_payload_fails(self):
        send_text(self.app, "!room:test", "Hello", "request-test-1")
        with self.assertRaises(ValueError):
            send_text(self.app, "!room:test", "Different", "request-test-1")
        self.client.request.assert_called_once()

    def test_denied_room_never_calls_transport(self):
        with self.assertRaises(ValueError):
            send_text(self.app, "!denied:test", "Hello", "request-test-1")
        self.app.matrix.assert_not_called()

    def test_disabled_send_does_not_read_session(self):
        self.app.config["send_mode"] = "disabled"
        with self.assertRaises(ValueError):
            send_text(self.app, "!room:test", "Hello", "request-test-1")
        self.app.matrix.assert_not_called()

    def test_local_approval_is_enforced(self):
        self.app.config["send_mode"] = "local_approval"
        result = send_text(self.app, "!room:test", "Hello", "request-test-1")
        self.assertEqual(result["status"], "pending_approval")
        self.client.request.assert_not_called()
        approve(self.app, "request-test-1", True)
        self.assertEqual(send_text(self.app, "!room:test", "Hello", "request-test-1")["status"], "accepted")
        self.client.request.assert_called_once()

    def test_uncertain_retry_reuses_matrix_transaction(self):
        self.client.request.side_effect = [MatrixError("offline"), {"event_id": "$synthetic"}]
        self.assertEqual(send_text(self.app, "!room:test", "Hello", "request-test-1")["status"], "uncertain")
        self.assertEqual(send_text(self.app, "!room:test", "Hello", "request-test-1")["status"], "accepted")
        paths = [call.args[1] for call in self.client.request.call_args_list]
        self.assertEqual(paths[0], paths[1])

    def test_uncertain_send_cannot_replay_after_new_login(self):
        self.client.request.side_effect = MatrixError("offline")
        send_text(self.app, "!room:test", "Hello", "request-test-1")
        self.client.token = "another-synthetic-session"
        with self.assertRaises(ValueError):
            send_text(self.app, "!room:test", "Hello", "request-test-1")
        self.client.request.assert_called_once()

    def test_concurrent_clients_share_one_submission(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: send_text(self.app, "!room:test", "Hello", "request-concurrent"), range(2)))
        self.client.request.assert_called_once()

    def test_revoked_chat_hides_outbox(self):
        send_text(self.app, "!room:test", "Hello", "request-test-1")
        self.app.rooms.clear()
        with self.assertRaises(ValueError):
            send_status(self.app, "request-test-1")
