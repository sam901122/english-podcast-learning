import json
import unittest
from unittest.mock import patch

from scripts.update_podcast import find_spotify_episode_url


class SpotifyLookupTests(unittest.TestCase):
    @staticmethod
    def embed_page(title="Test episode", spotify_id="abc123"):
        data = {
            "props": {"pageProps": {"state": {"data": {"entity": {
                "title": title,
                "id": spotify_id,
                "releaseDate": {"isoString": "2026-08-13T13:30:00Z"},
                "relatedEntityUri": "spotify:show:2mPQrJT37b3iXf4zxlnPOD",
            }}}}},
        }
        return (
            '<script id="__NEXT_DATA__" type="application/json">'
            f"{json.dumps(data)}</script>"
        ).encode()

    @patch("scripts.update_podcast.fetch")
    def test_returns_direct_link_for_an_exact_match(self, fetch):
        fetch.return_value = self.embed_page()

        url = find_spotify_episode_url({
            "title": "Test episode",
            "publishedAt": "2026-08-13T13:30:00+00:00",
        })

        self.assertEqual(url, "https://open.spotify.com/episode/abc123")

    @patch("scripts.update_podcast.fetch")
    def test_ignores_a_different_episode(self, fetch):
        fetch.return_value = self.embed_page(title="Different episode")

        url = find_spotify_episode_url({
            "title": "Test episode",
            "publishedAt": "2026-08-13T13:30:00+00:00",
        })

        self.assertEqual(url, "")


if __name__ == "__main__":
    unittest.main()
