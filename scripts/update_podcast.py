"""Fetch the latest BBC episode and publish AI-generated learning notes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "site" / "data"
EPISODES_DIR = DATA_DIR / "episodes"
INDEX_FILE = DATA_DIR / "episodes.json"
DEFAULT_FEED_URL = "https://podcasts.files.bbci.co.uk/w13xtvrv.rss"
USER_AGENT = "english-podcast-learning-project/1.0"


def text_of(element: ET.Element | None, default: str = "") -> str:
    return (element.text or default).strip() if element is not None else default


def first_child_text(item: ET.Element, names: tuple[str, ...]) -> str:
    for child in item:
        if child.tag.split("}")[-1] in names and child.text:
            return child.text.strip()
    return ""


def episode_id(guid: str, audio_url: str) -> str:
    source = guid or audio_url
    match = re.search(r"(?:episodes/|/)([a-z0-9]{8})(?:[/?._-]|$)", source, re.I)
    return match.group(1).lower() if match else hashlib.sha256(source.encode()).hexdigest()[:16]


def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    episodes: list[dict] = []
    for item in root.findall("./channel/item"):
        enclosure = item.find("enclosure")
        audio_url = enclosure.get("url", "") if enclosure is not None else ""
        guid = text_of(item.find("guid"))
        if not audio_url:
            continue
        published_raw = text_of(item.find("pubDate"))
        try:
            published = parsedate_to_datetime(published_raw).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            published = published_raw
        episodes.append(
            {
                "id": episode_id(guid, audio_url),
                "guid": guid,
                "title": text_of(item.find("title"), "Untitled episode"),
                "description": first_child_text(item, ("description", "summary")),
                "publishedAt": published,
                "bbcUrl": text_of(item.find("link")),
                "audioUrl": audio_url,
            }
        )
    return episodes


def fetch(url: str, destination: Path | None = None) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        if destination is None:
            return response.read()
        with destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    return None


def load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def transcribe(client, audio_path: Path) -> str:
    with audio_path.open("rb") as audio:
        result = client.audio.transcriptions.create(
            model=os.getenv("TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"),
            file=audio,
            language="en",
            prompt="BBC World Service news podcast with international names and current affairs.",
        )
    return result.text.strip()


def analyze(client, episode: dict, transcript: str) -> dict:
    schema = {
        "name": "learning_notes",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summaryZh": {"type": "string"},
                "summaryEn": {"type": "string"},
                "vocabulary": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "word": {"type": "string"},
                            "partOfSpeech": {"type": "string"},
                            "level": {"type": "string", "enum": ["B1", "B2", "C1", "C2"]},
                            "meaningZh": {"type": "string"},
                            "definitionEn": {"type": "string"},
                            "example": {"type": "string"},
                        },
                        "required": ["word", "partOfSpeech", "level", "meaningZh", "definitionEn", "example"],
                    },
                },
                "phrases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "phrase": {"type": "string"},
                            "meaningZh": {"type": "string"},
                            "definitionEn": {"type": "string"},
                            "example": {"type": "string"},
                        },
                        "required": ["phrase", "meaningZh", "definitionEn", "example"],
                    },
                },
            },
            "required": ["summaryZh", "summaryEn", "vocabulary", "phrases"],
        },
    }
    prompt = f"""You create concise study notes for a Taiwanese English learner at B1-B2 level.
Summarize this episode in Traditional Chinese and simple English. Select 8-12 genuinely useful
B1-C2 words and 4-8 phrases that appear in the transcript. Examples must be short verbatim excerpts
from the supplied transcript. Do not invent facts or words.

Episode title: {episode['title']}
BBC description: {episode['description']}

Transcript:
{transcript}
"""
    response = client.responses.create(
        model=os.getenv("ANALYSIS_MODEL", "gpt-5-mini"),
        input=prompt,
        text={"format": {"type": "json_schema", **schema}},
    )
    return json.loads(response.output_text)


def save_episode(episode: dict, notes: dict, index: list[dict]) -> None:
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    public_episode = {
        "id": episode["id"],
        "title": episode["title"],
        "description": episode["description"],
        "publishedAt": episode["publishedAt"],
        "bbcUrl": episode["bbcUrl"],
        "summaryZh": notes["summaryZh"],
        "summaryEn": notes["summaryEn"],
        "vocabulary": notes["vocabulary"],
        "phrases": notes["phrases"],
    }
    detail_file = EPISODES_DIR / f"{episode['id']}.json"
    detail_file.write_text(json.dumps(public_episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index_entry = {key: public_episode[key] for key in ("id", "title", "publishedAt", "bbcUrl", "summaryZh")}
    index.insert(0, index_entry)
    index.sort(key=lambda value: value.get("publishedAt", ""), reverse=True)
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Only inspect the feed")
    args = parser.parse_args()
    feed_url = os.getenv("PODCAST_FEED_URL", DEFAULT_FEED_URL)
    feed = parse_feed(fetch(feed_url) or b"")
    if not feed:
        raise RuntimeError("The podcast feed did not contain playable episodes")

    index = load_index()
    known = {item["id"] for item in index}
    episode = next((item for item in feed if item["id"] not in known), None)
    if episode is None:
        print("No new episode found.")
        return 0
    print(f"New episode: {episode['title']} ({episode['id']})")
    if args.dry_run:
        return 0
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required")

    from openai import OpenAI

    client = OpenAI()
    with tempfile.TemporaryDirectory(prefix="english-podcast-") as temp_dir:
        audio_path = Path(temp_dir) / "episode.mp3"
        fetch(episode["audioUrl"], audio_path)
        transcript = transcribe(client, audio_path)
        notes = analyze(client, episode, transcript)
    save_episode(episode, notes, index)
    print(f"Published learning notes for {episode['id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
