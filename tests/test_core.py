import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from messenger_mcp.core import App, Matrix


class AccessAndIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "config.json"
        path.write_text(json.dumps({"homeserver": "http://127.0.0.1:18008", "user_id": "@owner:test", "allowed_rooms": {"!ok:test": "Selected"}}))
        self.app = App(path)

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, eid, body, timestamp=1, sender="@a:test"):
        return {"event_id": eid, "type": "m.room.message", "sender": sender, "origin_server_ts": timestamp, "content": {"body": body, "msgtype": "m.text"}}

    def refresh_with(self, events):
        client = Mock()
        client.messages.return_value = {"chunk": events}
        self.app.matrix = Mock(return_value=client)
        return self.app.refresh("!ok:test")

    def test_denied_room_never_contacts_matrix(self):
        self.app.matrix = Mock()
        for operation in (lambda: self.app.refresh("!denied:test"), lambda: self.app.read("!denied:test")):
            with self.assertRaises(ValueError):
                operation()
        self.app.matrix.assert_not_called()

    def test_dedup_edits_and_redactions(self):
        original = self.event("$1", "old")
        self.refresh_with([original, original])
        edit = self.event("$edit", "* new", 2)
        edit["content"].update({"m.new_content": {"body": "new"}, "m.relates_to": {"rel_type": "m.replace", "event_id": "$1"}})
        self.refresh_with([edit, original])
        self.assertEqual([m["body"] for m in self.app.read("!ok:test")["messages"]], ["new"])
        self.refresh_with([original])
        self.assertEqual(self.app.read("!ok:test")["messages"][0]["body"], "new")
        self.refresh_with([{"type": "m.room.redaction", "content": {"redacts": "$1"}}])
        self.refresh_with([original])
        self.assertEqual(self.app.read("!ok:test")["messages"], [])

    def test_another_sender_cannot_edit_original(self):
        original = self.event("$1", "original")
        edit = self.event("$2", "spoof", 2, "@other:test")
        edit["content"].update({"m.new_content": {"body": "spoof"}, "m.relates_to": {"rel_type": "m.replace", "event_id": "$1"}})
        self.refresh_with([edit, original])
        self.assertEqual(self.app.read("!ok:test")["messages"][0]["body"], "original")

    def test_encrypted_room_fails_without_caching_partial_text(self):
        with self.assertRaises(ValueError):
            self.refresh_with([self.event("$1", "text"), {"type": "m.room.encrypted"}])
        self.assertEqual(self.app.read("!ok:test")["messages"], [])

    def test_search_is_literal_and_confined_to_room(self):
        self.refresh_with([self.event("$1", "50%_ Łódź"), self.event("$2", "other", 2)])
        self.assertEqual(len(self.app.read("!ok:test", query="%_")["messages"]), 1)
        self.assertEqual(len(self.app.read("!ok:test", query="' OR 1=1 --")["messages"]), 0)

    def test_no_plaintext_remote_http(self):
        with self.assertRaises(ValueError):
            Matrix("http://example.com")

    def test_unicode_casefold_search(self):
        self.refresh_with([self.event("$1", "ŁÓDŹ i żółć")])
        self.assertEqual(len(self.app.read("!ok:test", query="łódź")["messages"]), 1)

    def test_cursor_handles_equal_timestamps(self):
        self.refresh_with([self.event("$a", "one"), self.event("$b", "two"), self.event("$c", "three")])
        first = self.app.read("!ok:test", limit=2)
        second = self.app.read("!ok:test", limit=2, cursor=first["next_cursor"])
        ids = [m["event"] for m in first["messages"] + second["messages"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {"$a", "$b", "$c"})

    def test_alias_resolution_is_exact_and_ambiguous_names_fail(self):
        self.assertEqual(self.app.resolve_room("SELECTED"), "!ok:test")
        self.app.rooms["!other:test"] = "Selected"
        with self.assertRaises(ValueError):
            self.app.resolve_room("selected")

    def test_bad_cursor_fails(self):
        with self.assertRaises(ValueError):
            self.app.read("!ok:test", cursor="not-valid")


if __name__ == "__main__":
    unittest.main()
