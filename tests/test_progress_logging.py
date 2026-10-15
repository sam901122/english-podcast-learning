import threading
import unittest
from unittest.mock import Mock, patch

from scripts.update_podcast import GeminiClient, log, run_logged


class ProgressLoggingTests(unittest.TestCase):
    @patch("builtins.print")
    def test_log_flushes_with_timestamp(self, output):
        log("test stage")
        output.assert_called_once()
        self.assertTrue(output.call_args.kwargs["flush"])
        self.assertRegex(output.call_args.args[0], r"^\[.*\+00:00\] test stage$")

    @patch("scripts.update_podcast.log")
    def test_success_reports_elapsed_time_and_returns_result(self, output):
        result = object()
        self.assertIs(run_logged("test stage", lambda: result), result)
        messages = [call.args[0] for call in output.call_args_list]
        self.assertEqual(messages[0], "START test stage")
        self.assertRegex(messages[-1], r"DONE test stage; elapsed=\d+\.\ds")

    @patch("scripts.update_podcast.log")
    def test_failure_preserves_exception_and_reports_stage(self, output):
        error = ValueError("invalid response")
        with self.assertRaises(ValueError) as raised:
            run_logged("summary", Mock(side_effect=error))
        self.assertIs(raised.exception, error)
        self.assertIn("FAILED summary; elapsed=", output.call_args.args[0])
        self.assertIn("ValueError: invalid response", output.call_args.args[0])

    @patch("scripts.update_podcast.HEARTBEAT_INTERVAL_SECONDS", 0.01)
    def test_heartbeat_during_blocking_operation(self):
        heartbeat_seen = threading.Event()
        messages = []

        def capture(message):
            messages.append(message)
            if message.startswith("WAITING"):
                heartbeat_seen.set()

        with patch("scripts.update_podcast.log", side_effect=capture):
            self.assertTrue(run_logged("AI summary", heartbeat_seen.wait, 2))
        self.assertTrue(any("WAITING AI summary; elapsed=" in message for message in messages))
        self.assertTrue(messages[-1].startswith("DONE AI summary"))

    @patch("scripts.update_podcast.time.sleep")
    @patch("scripts.update_podcast.log")
    def test_retry_reports_tier_attempt_and_wait(self, output, sleep):
        client = object.__new__(GeminiClient)
        client._free_client = object()
        client._paid_client = object()
        operation = Mock(side_effect=[RuntimeError("503")] * 3 + ["ok"])
        self.assertEqual(client._with_fallback(operation, "AI summary; model=test"), "ok")
        messages = [call.args[0] for call in output.call_args_list]
        self.assertTrue(any("tier=free; attempt=3/3" in message for message in messages))
        self.assertTrue(any("waiting 30s before paid attempt 1/3" in message for message in messages))
        self.assertTrue(any("DONE AI summary; model=test; tier=paid; attempt=1/3" in message for message in messages))
        self.assertEqual(sleep.call_count, 3)


if __name__ == "__main__":
    unittest.main()
