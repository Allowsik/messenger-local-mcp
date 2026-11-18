import unittest
from unittest.mock import Mock, patch
from messenger_mcp.cli import BotReplies


def batch(cursor, bodies):
    return {"next_batch": cursor, "rooms": {"join": {"!room:test": {"timeline": {"events": [
        {"content": {"body": body}} for body in bodies]}}}}}


class LoginRepliesTests(unittest.TestCase):
    def test_old_password_prompt_is_discarded(self):
        client = Mock()
        client.request.side_effect = [batch("old", ["Please enter your Password"]), batch("boundary", []), batch("next", ["New response"])]
        replies = BotReplies(client, "!room:test", "@bot:test")
        self.assertEqual(replies.poll(0), ["New response"])
        self.assertEqual(client.request.call_args.kwargs["query"]["since"], "boundary")

    def test_welcome_does_not_end_wait_before_actual_prompt(self):
        client = Mock()
        client.request.side_effect = [batch("cached", []), batch("0", []), batch("1", ["Hello, I'm a Facebook Messenger bridge bot."]),
            batch("2", []), batch("3", ["Please enter your Username or email address"]), batch("4", [])]
        replies = BotReplies(client, "!room:test", "@bot:test")
        with patch("builtins.print"):
            self.assertTrue(replies.wait())
        self.assertEqual(replies.cursor, "4")

    def test_cached_initial_sync_backlog_is_discarded(self):
        client = Mock()
        client.request.side_effect = [batch("cached", []), batch("old", ["Old command reply"]),
                                     batch("boundary", []), batch("new", ["Current response"])]
        replies = BotReplies(client, "!room:test", "@bot:test")
        self.assertEqual(replies.poll(0), ["Current response"])


if __name__ == "__main__":
    unittest.main()
