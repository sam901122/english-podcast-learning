import unittest

from scripts.find_spotify_episode import find_episode_url, normalize_title


class FindSpotifyEpisodeTests(unittest.TestCase):
    PAGE = """
    <div data-testid="episode-0">
      <img alt="Newest episode">
      <a href="/episode/newest123">Newest episode</a>
    </div>
    <div data-testid="episode-1">
      <img alt="How extreme rain is putting orangutans at risk">
      <a href="/episode/orangutan456">How extreme rain is putting orangutans at risk</a>
    </div>
    """

    def test_finds_a_historical_episode_by_exact_title(self):
        self.assertEqual(
            find_episode_url(self.PAGE, "How extreme rain is putting orangutans at risk"),
            "https://open.spotify.com/episode/orangutan456",
        )

    def test_does_not_return_the_latest_episode_for_a_different_title(self):
        self.assertEqual(find_episode_url(self.PAGE, "Missing episode"), "")

    def test_normalizes_whitespace_case_and_html_entities(self):
        self.assertEqual(normalize_title("  Women &amp; AI  "), "women & ai")


if __name__ == "__main__":
    unittest.main()
