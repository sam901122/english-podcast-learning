import unittest
from unittest.mock import patch

import httpx
from google import genai

from scripts.update_podcast import GeminiClient, is_quota_exhausted


class GeminiTransportTests(unittest.TestCase):
    def test_sdk_does_not_retry_errors_or_timeouts(self):
        real_client = genai.Client
        for failure in ("503", "timeout", "daily", "minute"):
            with self.subTest(failure=failure):
                requests = []

                def respond(request):
                    requests.append(request)
                    if failure == "timeout":
                        raise httpx.ReadTimeout("test timeout", request=request)
                    if failure in ("daily", "minute"):
                        unit = "day" if failure == "daily" else "minute"
                        return httpx.Response(429, json={"error": {
                            "message": f"Rate limit exceeded (limit: 20 requests per {unit} on Free Tier)",
                            "code": "too_many_requests",
                        }})
                    return httpx.Response(503, json={
                        "error": {"message": "high demand", "code": "service_unavailable"}
                    })

                def create_client(**kwargs):
                    kwargs["http_options"]["client_args"] = {
                        "transport": httpx.MockTransport(respond)
                    }
                    return real_client(**kwargs)

                with patch("google.genai.Client", side_effect=create_client):
                    client = GeminiClient("test-key")
                try:
                    with self.assertRaises(Exception) as raised:
                        client._free_client.interactions.create(model="test", input="test")
                    self.assertEqual(is_quota_exhausted(raised.exception), failure == "daily")
                    self.assertEqual(len(requests), 1, "SDK must send exactly one HTTP request")
                    self.assertEqual(requests[0].extensions["timeout"]["read"], 120)
                finally:
                    client._free_client.close()


if __name__ == "__main__":
    unittest.main()
