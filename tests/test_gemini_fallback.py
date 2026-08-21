import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.update_podcast import GeminiClient, should_fallback_to_paid


class GeminiFallbackTests(unittest.TestCase):
    def test_recognizes_quota_and_capacity_errors(self):
        for message in (
            "429 Too Many Requests",
            "RESOURCE_EXHAUSTED",
            "503 Service Unavailable",
            "Model has no capacity due to high demand",
        ):
            with self.subTest(message=message):
                self.assertTrue(should_fallback_to_paid(RuntimeError(message)))

    def test_does_not_fallback_for_regular_errors(self):
        self.assertFalse(should_fallback_to_paid(RuntimeError("Invalid JSON schema")))
        self.assertFalse(should_fallback_to_paid(RuntimeError("401 invalid API key")))

    @patch("google.genai.Client")
    def test_generate_json_uses_free_key_first(self, client_class):
        free_client = Mock()
        paid_client = Mock()
        client_class.side_effect = [free_client, paid_client]
        free_client.interactions.create.return_value = SimpleNamespace(output_text='{"ok": true}')

        result = GeminiClient("free", "paid").generate_json(prompt="test", schema={})

        self.assertEqual(result, {"ok": True})
        free_client.interactions.create.assert_called_once()
        paid_client.interactions.create.assert_not_called()

    @patch("google.genai.Client")
    def test_generate_json_falls_back_to_paid_on_429(self, client_class):
        free_client = Mock()
        paid_client = Mock()
        client_class.side_effect = [free_client, paid_client]
        free_client.interactions.create.side_effect = RuntimeError("429 RESOURCE_EXHAUSTED")
        paid_client.interactions.create.return_value = SimpleNamespace(output_text='{"ok": true}')

        result = GeminiClient("free", "paid").generate_json(prompt="test", schema={})

        self.assertEqual(result, {"ok": True})
        free_client.interactions.create.assert_called_once()
        paid_client.interactions.create.assert_called_once()

    @patch("google.genai.Client")
    def test_generate_json_does_not_fallback_on_invalid_request(self, client_class):
        free_client = Mock()
        paid_client = Mock()
        client_class.side_effect = [free_client, paid_client]
        free_client.interactions.create.side_effect = RuntimeError("400 invalid schema")

        with self.assertRaisesRegex(RuntimeError, "invalid schema"):
            GeminiClient("free", "paid").generate_json(prompt="test", schema={})

        paid_client.interactions.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
