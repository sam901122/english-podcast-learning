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

from opencc import OpenCC

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "site" / "data"
EPISODES_DIR = DATA_DIR / "episodes"
INDEX_FILE = DATA_DIR / "episodes.json"
DEFAULT_FEED_URL = "https://podcasts.files.bbci.co.uk/w13xtvrv.rss"
USER_AGENT = "english-podcast-learning-project/1.0"
VOCABULARY_COUNT = 20
PHRASE_COUNT = 10
STUDY_LEVELS = ("basic", "intermediate", "advanced")
CEFR_ORDER = {"A2": 0, "B1": 1, "B2": 2, "C1": 3, "C2": 4}
CEFR_BY_STUDY_LEVEL = {
    "basic": {"A2", "B1"},
    "intermediate": {"B1", "B2"},
    "advanced": {"C1", "C2"},
}


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
                "title": text_of(item.find("title"), "Untitled episode"),
                "description": first_child_text(item, ("description", "summary")),
                "publishedAt": published,
                "bbcUrl": text_of(item.find("link")),
                "audioUrl": audio_url,
            }
        )
    return episodes


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        with destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)


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


def validate_and_sort_notes(notes: dict) -> dict:
    seen_terms = {"vocabulary": set(), "phrases": set()}
    study_sets = notes.get("studySets", {})
    for study_level in STUDY_LEVELS:
        study_set = study_sets.get(study_level, {})
        if not study_set:
            raise ValueError(f"Missing study set: {study_level}")

        collections = (
            ("vocabulary", "word", VOCABULARY_COUNT),
            ("phrases", "phrase", None),
        )
        for collection_name, term_key, expected_count in collections:
            items = study_set.get(collection_name, [])
            if expected_count is not None and len(items) != expected_count:
                raise ValueError(
                    f"Expected {expected_count} {study_level} {collection_name}, received {len(items)}"
                )
            if collection_name == "phrases" and len(items) > PHRASE_COUNT:
                raise ValueError(
                    f"Expected at most {PHRASE_COUNT} {study_level} phrases, received {len(items)}"
                )

            for item in items:
                term = item[term_key].strip()
                normalized_term = term.casefold()
                if not term or normalized_term in seen_terms[collection_name]:
                    raise ValueError(f"Duplicate or empty {term_key}: {term!r}")
                seen_terms[collection_name].add(normalized_term)

                if item["level"] not in CEFR_BY_STUDY_LEVEL[study_level]:
                    raise ValueError(
                        f"Unexpected CEFR level {item['level']!r} in {study_level} for {term!r}"
                    )

                example = item["example"]
                example_parts = item.get("exampleParts", [])
                if not example.strip() or len(example) > 500 or "\n" in example or "\r" in example:
                    raise ValueError(f"Invalid single-sentence example for {term!r}")
                if not example_parts or "".join(part["text"] for part in example_parts) != example:
                    raise ValueError(f"exampleParts do not reconstruct the example for {term!r}")
                highlighted_parts = [
                    part for part in example_parts if part["highlight"] and part["text"].strip()
                ]
                if len(highlighted_parts) != 1:
                    raise ValueError(f"Expected exactly one LLM-selected highlight for {term!r}")

            items.sort(key=lambda item: CEFR_ORDER[item["level"]])
    return notes


def normalize_traditional_chinese(value, converter: OpenCC | None = None):
    converter = converter or OpenCC("s2tw")
    if isinstance(value, str):
        return converter.convert(value)
    if isinstance(value, list):
        return [normalize_traditional_chinese(item, converter) for item in value]
    if isinstance(value, dict):
        return {key: normalize_traditional_chinese(item, converter) for key, item in value.items()}
    return value


def learning_item_schema(kind: str, allowed_levels: list[str]) -> dict:
    term_properties = {
        "level": {"type": "string", "enum": allowed_levels},
        "meaningZh": {"type": "string"},
        "example": {"type": "string"},
        "exampleParts": {
            "type": "array",
            "minItems": 1,
            "maxItems": 7,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "text": {"type": "string"},
                    "highlight": {"type": "boolean"},
                },
                "required": ["text", "highlight"],
            },
        },
    }
    if kind == "vocabulary":
        term_properties = {
            "word": {"type": "string"},
            "kkPhonetic": {"type": "string"},
            "partOfSpeech": {"type": "string"},
            **term_properties,
        }
        required = [
            "word", "kkPhonetic", "partOfSpeech", "level", "meaningZh", "example",
            "exampleParts",
        ]
    else:
        term_properties = {"phrase": {"type": "string"}, **term_properties}
        required = ["phrase", "level", "meaningZh", "example", "exampleParts"]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": term_properties,
        "required": required,
    }


def study_set_schema(study_level: str) -> dict:
    allowed_levels = sorted(CEFR_BY_STUDY_LEVEL[study_level], key=CEFR_ORDER.get)
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "vocabulary": {
                "type": "array",
                "minItems": VOCABULARY_COUNT,
                "maxItems": VOCABULARY_COUNT,
                "items": learning_item_schema("vocabulary", allowed_levels),
            },
            "phrases": {
                "type": "array",
                "minItems": 0,
                "maxItems": PHRASE_COUNT,
                "items": learning_item_schema("phrases", allowed_levels),
            },
        },
        "required": ["vocabulary", "phrases"],
    }


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
                "studySets": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {level: study_set_schema(level) for level in STUDY_LEVELS},
                    "required": list(STUDY_LEVELS),
                },
            },
            "required": ["summaryZh", "summaryEn", "studySets"],
        },
    }
    prompt = f"""You create concise study notes for Taiwanese English learners.
Summarize this episode in Taiwan Traditional Chinese and simple English. Build three distinct study sets
from the transcript, with exactly {VOCABULARY_COUNT} vocabulary words and up to {PHRASE_COUNT} phrases in
each set:
- `basic`: A2-B1 items
- `intermediate`: B1-B2 items
- `advanced`: C1-C2 items

Do not repeat a vocabulary learning form or canonical phrase across study sets. Choose genuinely useful
items and assign an accurate CEFR `level` within the allowed range for its study set. Include fewer than
{PHRASE_COUNT} phrases, including zero, when the transcript does not contain enough genuinely useful phrases;
never pad the list with weak, generic, or invented phrases. The web page will show the advanced set by default.

For vocabulary, set `word` to the form a learner should study. Convert ordinary inflected verbs to the
dictionary base form (for example, `evaporating` becomes `evaporate`) and ordinary plural nouns to singular.
Keep a participial form such as `dehydrated`, `stranded`, or `sequestered` when it functions as an
established adjective in that sentence and is genuinely more useful to learn as an adjective. Do not
mechanically convert every participial adjective into a verb. Make `partOfSpeech`, meaning, KK pronunciation,
and CEFR `level` describe the learning form in `word`.

For phrases, set `phrase` to the reusable canonical form a learner should study, normally using a base verb
(for example, `taking a step back` in the transcript becomes `take a step back`). For every word and phrase,
`example` must be exactly one complete original sentence from the podcast transcript without rewriting it.
Never return a paragraph, multiple sentences, speaker labels, or surrounding context.

The LLM must decide the exact highlight span. Split the complete `example` into ordered `exampleParts` whose
`text` values concatenate to exactly the original `example`, character for character. Mark only the one exact
surface form of the learning word or phrase with `highlight: true` (for example, only `evaporating` or only
`taking a step back`). Mark every other character with `highlight: false`. Do not include punctuation,
surrounding words, repeated unrelated matches, or extra whitespace in the highlighted part. Do not derive the
highlight with morphology or string rules; select the intended span from the sentence semantically.

For every word, provide its American English pronunciation in KK phonetic symbols, enclosed in slashes.
Give phrases a Taiwan Traditional Chinese meaning only; do not provide an English definition. Every Chinese
character in `summaryZh` and `meaningZh` must use Taiwan Traditional Chinese. Never output Simplified Chinese
characters or Mainland Chinese wording. Do not invent facts or wording.
In the Taiwan Traditional Chinese summary, insert one regular half-width space at every boundary between
Chinese full-width text and half-width Latin letters or numbers (for example: "BBC 記者 Maddie").
Apply this typography rule consistently. Internal rule keyword: 盤古之白; do not include the keyword
in the generated notes.

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
    notes = normalize_traditional_chinese(json.loads(response.output_text))
    return validate_and_sort_notes(notes)


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
        "studySets": notes["studySets"],
    }
    detail_file = EPISODES_DIR / f"{episode['id']}.json"
    detail_file.write_text(json.dumps(public_episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index[:] = [item for item in index if item.get("id") != episode["id"]]
    index_entry = {key: public_episode[key] for key in ("id", "title", "publishedAt", "bbcUrl", "summaryZh")}
    index.insert(0, index_entry)
    index.sort(key=lambda value: value.get("publishedAt", ""), reverse=True)
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Only inspect the feed")
    args = parser.parse_args()
    feed_url = os.getenv("PODCAST_FEED_URL", DEFAULT_FEED_URL)
    feed = parse_feed(fetch_bytes(feed_url))
    if not feed:
        raise RuntimeError("The podcast feed did not contain playable episodes")

    index = load_index()
    known = {item["id"] for item in index}
    force_latest = os.getenv("FORCE_REPROCESS_LATEST", "").lower() in {"1", "true", "yes"}
    episode = feed[0] if force_latest else next((item for item in feed if item["id"] not in known), None)
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
        download_file(episode["audioUrl"], audio_path)
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
