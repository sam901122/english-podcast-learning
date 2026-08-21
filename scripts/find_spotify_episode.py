"""Find a historical Spotify episode URL without changing the daily pipeline."""

from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EPISODES_DIR = ROOT / "site" / "data" / "episodes"
DEFAULT_SHOW_ID = "2mPQrJT37b3iXf4zxlnPOD"
USER_AGENT = "english-podcast-learning-project/1.0"
EPISODE_BLOCK = re.compile(
    r'data-testid="episode-\d+"(?P<body>.*?)(?=data-testid="episode-\d+"|$)',
    re.DOTALL,
)
EPISODE_LINK = re.compile(r'href="(?:https://open\.spotify\.com)?/episode/(?P<id>[A-Za-z0-9]+)"')
ALT_TEXT = re.compile(r'alt="(?P<title>[^"]+)"')


def normalize_title(value: str) -> str:
    return " ".join(html.unescape(value).casefold().split())


def find_episode_url(page: str, title: str) -> str:
    expected_title = normalize_title(title)
    for match in EPISODE_BLOCK.finditer(page):
        block = match.group("body")
        titles = {normalize_title(value) for value in ALT_TEXT.findall(block)}
        link = EPISODE_LINK.search(block)
        if expected_title in titles and link:
            return f"https://open.spotify.com/episode/{link.group('id')}"
    return ""


def fetch_show_page(show_id: str) -> str:
    request = urllib.request.Request(
        f"https://open.spotify.com/show/{show_id}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read().decode("utf-8")


def load_episode_title(episode_id: str) -> str:
    episode_file = EPISODES_DIR / f"{episode_id}.json"
    if not episode_file.exists():
        raise FileNotFoundError(f"Unknown local episode ID: {episode_id}")
    return json.loads(episode_file.read_text(encoding="utf-8"))["title"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--episode-id", help="Local episode ID from site/data/episodes")
    target.add_argument("--title", help="Exact Spotify episode title")
    parser.add_argument("--show-id", default=DEFAULT_SHOW_ID, help="Spotify show ID")
    args = parser.parse_args()

    title = load_episode_title(args.episode_id) if args.episode_id else args.title
    url = find_episode_url(fetch_show_page(args.show_id), title)
    if not url:
        raise RuntimeError(f"Spotify episode not found: {title}")
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
