"""Fetch the latest BBC episode and publish AI-generated learning notes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "site" / "data"
EPISODES_DIR = DATA_DIR / "episodes"
INDEX_FILE = DATA_DIR / "episodes.json"
DEFAULT_FEED_URL = "https://podcasts.files.bbci.co.uk/w13xtvrv.rss"
SPOTIFY_SHOW_ID = "2mPQrJT37b3iXf4zxlnPOD"
SPOTIFY_EMBED_URL = f"https://open.spotify.com/embed/show/{SPOTIFY_SHOW_ID}"
USER_AGENT = "english-podcast-learning-project/1.0"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_GEMINI_WORD_FORM_MODEL = "gemini-3.5-flash-lite"
SUMMARY_ZH_PREFIX = "本集 BBC 節目《What in the World》探討"
STUDY_LEVELS = {
    "basic": {
        "label": "beginner",
        "levels": ["A2", "B1"],
        "guidance": "common, concrete, broadly useful words and everyday phrases",
    },
    "intermediate": {
        "label": "intermediate",
        "levels": ["B1", "B2"],
        "guidance": "moderately challenging words and idiomatic phrases useful in news and conversation",
    },
    "advanced": {
        "label": "advanced",
        "levels": ["C1", "C2"],
        "guidance": "precise, nuanced, less common words and sophisticated phrases",
    },
}


class GeminiClient:
    """Gemini operations used by the podcast pipeline."""

    def __init__(self, api_key: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)

    def generate_json(self, *, prompt: str, schema: dict, model: str | None = None) -> dict:
        for attempt in range(5):
            try:
                response = self._client.interactions.create(
                    model=model or os.getenv("ANALYSIS_MODEL", DEFAULT_GEMINI_MODEL),
                    input=prompt,
                    response_format={
                        "type": "text",
                        "mime_type": "application/json",
                        "schema": schema,
                    },
                )
                if not response.output_text:
                    raise RuntimeError("Gemini returned an empty structured response")
                return json.loads(response.output_text)
            except Exception as error:
                message = str(error)
                permanent_quota_error = any(
                    marker in message.casefold()
                    for marker in ("prepayment credits", "billing", "permission_denied")
                )
                if "429" not in message or permanent_quota_error or attempt == 4:
                    raise
                retry_match = re.search(r"retry in ([0-9.]+)s", message, re.I)
                requested_delay = float(retry_match.group(1)) + 1 if retry_match else 0
                delay = max(2 ** (attempt + 1), requested_delay)
                print(f"Gemini rate limited the request; retrying in {delay}s.")
                time.sleep(delay)

    def transcribe(self, audio_path: Path) -> str:
        uploaded = self._client.files.upload(file=audio_path)
        try:
            response = self._client.interactions.create(
                model=os.getenv("TRANSCRIPTION_MODEL", DEFAULT_GEMINI_MODEL),
                input=[
                    {
                        "type": "text",
                        "text": "BBC World Service news podcast with international names and current "
                        "affairs. Transcribe all spoken English accurately. Return only "
                        "the complete verbatim transcript as plain text. Do not summarize, add headings, "
                        "identify speakers, or use Markdown.",
                    },
                    {"type": "audio", "uri": uploaded.uri, "mime_type": uploaded.mime_type},
                ],
            )
            if not response.output_text:
                raise RuntimeError("Gemini returned an empty transcription")
            return response.output_text.strip()
        finally:
            try:
                self._client.files.delete(name=uploaded.name)
            except Exception as error:
                print(f"Could not delete the temporary Gemini upload: {error}")


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


class SpotifyEmbedDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capturing = False
        self.data = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and dict(attrs).get("id") == "__NEXT_DATA__":
            self._capturing = True

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self.data += data

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capturing:
            self._capturing = False


def find_spotify_episode_url(episode: dict) -> str:
    try:
        parser = SpotifyEmbedDataParser()
        parser.feed((fetch(SPOTIFY_EMBED_URL) or b"").decode("utf-8"))
        entity = json.loads(parser.data)["props"]["pageProps"]["state"]["data"]["entity"]
        title_matches = " ".join(entity["title"].casefold().split()) == " ".join(
            episode["title"].casefold().split()
        )
        spotify_date = entity.get("releaseDate", {}).get("isoString", "")
        date_matches = datetime.fromisoformat(spotify_date.replace("Z", "+00:00")).date() == (
            datetime.fromisoformat(episode["publishedAt"]).date()
        )
        expected_show = entity.get("relatedEntityUri") == f"spotify:show:{SPOTIFY_SHOW_ID}"
        spotify_id = entity.get("id", "")
        if title_matches and date_matches and expected_show and re.fullmatch(r"[A-Za-z0-9]+", spotify_id):
            return f"https://open.spotify.com/episode/{spotify_id}"
        print("Spotify did not return a matching latest episode; continuing without a link.")
    except Exception as error:
        print(f"Spotify lookup failed; continuing without a link: {error}")
    return ""


def load_index() -> list[dict]:
    if not INDEX_FILE.exists():
        return []
    return json.loads(INDEX_FILE.read_text(encoding="utf-8"))


def transcribe(client, audio_path: Path) -> str:
    return client.transcribe(audio_path)


def remove_advertising(client, episode: dict, transcript: str) -> str:
    schema = {
        "name": "advertising_segments",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "segments": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": ["segments"],
        },
    }
    prompt = f"""Identify only advertising, unrelated programme promotions, and promotional calls to action
in this podcast transcript. Return each removable passage as an EXACT, contiguous verbatim substring copied
from the transcript. Never paraphrase, correct, shorten, or include surrounding editorial content. Keep the
BBC programme introduction, presenter dialogue, interviews, news context, credits, and any passage that might
be part of the episode. When uncertain, keep it. Return an empty list when there is no clearly unrelated
promotional passage.

Episode title: {episode['title']}
BBC description: {episode['description']}

Transcript:
{transcript}
"""
    segments = client.generate_json(prompt=prompt, schema=schema["schema"])["segments"]
    cleaned = transcript
    for segment in segments:
        exact_segment = segment.strip()
        if exact_segment and exact_segment in cleaned:
            cleaned = cleaned.replace(exact_segment, "", 1)
        elif exact_segment:
            print("Ignoring an advertising segment that was not copied exactly from the transcript.")
    return re.sub(r"\s+", " ", cleaned).strip()


def summarize(client, episode: dict, transcript: str) -> dict:
    schema = {
        "name": "episode_summaries",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "summaryZh": {"type": "string"},
                "summaryEn": {"type": "string"},
            },
            "required": ["summaryZh", "summaryEn"],
        },
    }
    prompt = f"""Summarize this BBC podcast episode accurately and concisely in two versions.
`summaryZh` MUST use Taiwan Traditional Chinese only. Never use Simplified Chinese characters or Mainland
Chinese wording anywhere in `summaryZh`. `summaryEn` must use clear, natural English.
`summaryZh` MUST begin with this exact text, character for character: {SUMMARY_ZH_PREFIX}
Continue the first sentence directly after that prefix with the episode's main topic. Do not add spaces
inside the title brackets, alter the prefix, or place any text before it.
In `summaryZh`, insert one regular half-width space at every boundary between
Chinese full-width text and half-width Latin letters or numbers (for example: "BBC 記者 Maddie").
Do not add spaces between adjacent Chinese characters. Do not invent facts.

Episode title: {episode['title']}
BBC description: {episode['description']}

Transcript:
{transcript}
"""
    return client.generate_json(prompt=prompt, schema=schema["schema"])


def analyze_study_level(client, transcript: str, study_level: str) -> dict:
    config = STUDY_LEVELS[study_level]
    item_properties = {
        "word": {"type": "string"},
        "kkPhonetic": {"type": "string"},
        "partOfSpeech": {"type": "string"},
        "level": {"type": "string", "enum": config["levels"]},
        "meaningZh": {"type": "string"},
        "example": {"type": "string"},
    }
    phrase_properties = {
        "phrase": {"type": "string"},
        "highlight": {"type": "string"},
        "meaningZh": {"type": "string"},
        "example": {"type": "string"},
    }
    schema = {
        "name": f"{study_level}_study_set",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "vocabulary": {
                    "type": "array",
                    "minItems": 10,
                    "maxItems": 10,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": item_properties,
                        "required": list(item_properties),
                    },
                },
                "phrases": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": phrase_properties,
                        "required": list(phrase_properties),
                    },
                },
            },
            "required": ["vocabulary", "phrases"],
        },
    }
    prompt = f"""Create one {config['label']} English study set from this podcast transcript.
Choose exactly 10 {config['guidance']} as vocabulary, at CEFR {"-".join(config['levels'])}, and exactly
5 useful phrases at a comparable difficulty. Items may overlap with study sets created by other requests.

Every vocabulary `word` must be the exact surface form that appears in its `example`; do not convert it to
a dictionary form yet. For phrases, `phrase` is the reusable learning form and `highlight` is the exact
contiguous surface form that appears in `example` (for example, phrase `take a step back` may highlight
`taking a step back`).
Each `example` must be one complete original sentence from the transcript containing that exact word or
highlight. Do not rewrite examples and do not return multiple sentences or a paragraph.

For every word, provide its American English pronunciation in KK phonetic symbols enclosed in slashes.
Every `meaningZh` MUST use Taiwan Traditional Chinese only. Never use Simplified Chinese characters or
Mainland Chinese wording in any Chinese field. Do not invent facts, wording, words, or phrases.

Transcript:
{transcript}
"""
    return client.generate_json(prompt=prompt, schema=schema["schema"])


def analyze(client, episode: dict, transcript: str) -> dict:
    notes = summarize(client, episode, transcript)
    notes["studySets"] = {
        study_level: analyze_study_level(client, transcript, study_level)
        for study_level in STUDY_LEVELS
    }
    return notes


def decide_study_words(client, items: list[dict]) -> list[dict]:
    if not items:
        return []
    count = len(items)
    schema = {
        "name": "study_word_decisions",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "minItems": count,
                    "maxItems": count,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "integer"},
                            "word": {"type": "string"},
                            "kkPhonetic": {"type": "string"},
                        },
                        "required": ["id", "word", "kkPhonetic"],
                    },
                },
            },
            "required": ["items"],
        },
    }
    input_items = [
        {
            "id": index,
            "word": item["word"],
            "kkPhonetic": item["kkPhonetic"],
            "partOfSpeech": item["partOfSpeech"],
            "meaningZh": item["meaningZh"],
            "example": item["example"],
        }
        for index, item in enumerate(items)
    ]
    prompt = f"""Normalize the display form of exactly {count} English vocabulary items for a learner.

Return exactly one result for every input item. Preserve each integer `id` exactly and return results in
ascending `id` order. Never omit, duplicate, merge, or add an item.

For each item independently:
- Change an ordinary inflected verb to its dictionary base form.
- Change an ordinary plural count noun to singular.
- Keep an established adjective, adverb, noun, proper name, hyphenated term, or fixed lexical form unchanged.
- Keep the original when normalization is uncertain or would make the learning item less natural in context.
- Never correct spelling, rewrite the example, change the meaning, or substitute a synonym.
- If `word` changes, return the American English KK pronunciation of the NEW word, enclosed in slashes.
- If `word` stays unchanged, copy both the original `word` and `kkPhonetic` exactly.

The JSON schema enforces the number of results. Match every result to the correct `id`.
Original word: {items[0]['word'] if count == 1 else '(see the complete item list below)'}
Input items:
{json.dumps(input_items, ensure_ascii=False, indent=2)}
"""
    try:
        payload = client.generate_json(
            prompt=prompt,
            schema=schema["schema"],
            model=os.getenv("WORD_FORM_MODEL", DEFAULT_GEMINI_WORD_FORM_MODEL),
        )
        if "items" in payload:
            decisions = payload["items"]
        elif count == 1:
            decisions = [{"id": 0, "word": payload["word"], "kkPhonetic": payload["kkPhonetic"]}]
        else:
            raise ValueError("Gemini did not return the batch items array")
        by_id = {decision["id"]: decision for decision in decisions}
        if len(decisions) != count or set(by_id) != set(range(count)):
            raise ValueError("Gemini returned missing or duplicate vocabulary IDs")
        normalized = []
        for index in range(count):
            candidate = by_id[index]["word"].strip()
            candidate_phonetic = by_id[index]["kkPhonetic"].strip()
            if not candidate or not candidate_phonetic:
                raise ValueError(f"Gemini returned an empty vocabulary decision for ID {index}")
            normalized.append({"word": candidate, "kkPhonetic": candidate_phonetic})
        return normalized
    except Exception as error:
        print(f"Batch word-form check failed; keeping all original forms: {error}")
        return [
            {"word": item["word"], "kkPhonetic": item["kkPhonetic"]}
            for item in items
        ]


def prepare_vocabulary(client, notes: dict) -> dict:
    study_sets = notes.get("studySets")
    if study_sets:
        vocabulary = [
            item
            for study_level in STUDY_LEVELS
            for item in study_sets[study_level]["vocabulary"]
        ]
    else:
        vocabulary = notes.get("vocabulary", [])
    for item in vocabulary:
        item["highlight"] = item["word"]

    study_words = decide_study_words(client, vocabulary)

    for item, study_word in zip(vocabulary, study_words):
        item.update(study_word)
    return notes


def validate_notes(notes: dict) -> None:
    for study_level in STUDY_LEVELS:
        study_set = notes["studySets"][study_level]
        if len(study_set["vocabulary"]) != 10 or len(study_set["phrases"]) != 5:
            raise ValueError(f"{study_level} study set has an unexpected item count")
        for item in study_set["vocabulary"]:
            if item["highlight"].casefold() not in item["example"].casefold():
                raise ValueError(
                    f"Vocabulary highlight {item['highlight']!r} is absent from its example"
                )
        for item in study_set["phrases"]:
            if item["highlight"].casefold() not in item["example"].casefold():
                raise ValueError(
                    f"Phrase highlight {item['highlight']!r} is absent from its example"
                )


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
    if episode.get("spotifyUrl"):
        public_episode["spotifyUrl"] = episode["spotifyUrl"]
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
    parser.add_argument(
        "--episode-offset",
        type=int,
        help="Process a specific RSS episode by zero-based position",
    )
    args = parser.parse_args()
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    feed_url = os.getenv("PODCAST_FEED_URL", DEFAULT_FEED_URL)
    feed = parse_feed(fetch(feed_url) or b"")
    if not feed:
        raise RuntimeError("The podcast feed did not contain playable episodes")

    index = load_index()
    known = {item["id"] for item in index}
    if args.episode_offset is not None:
        if args.episode_offset < 0 or args.episode_offset >= len(feed):
            raise ValueError(f"Episode offset {args.episode_offset} is outside the RSS feed")
        episode = feed[args.episode_offset]
    else:
        episode = feed[0] if feed[0]["id"] not in known else None
    if episode is None:
        print("No new episode found.")
        return 0
    print(f"New episode: {episode['title']} ({episode['id']})")
    if args.dry_run:
        return 0
    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY is required")

    episode["spotifyUrl"] = find_spotify_episode_url(episode)
    client = GeminiClient(os.environ["GEMINI_API_KEY"])
    with tempfile.TemporaryDirectory(prefix="english-podcast-") as temp_dir:
        audio_path = Path(temp_dir) / "episode.mp3"
        fetch(episode["audioUrl"], audio_path)
        transcript = transcribe(client, audio_path)
        transcript = remove_advertising(client, episode, transcript)
        notes = analyze(client, episode, transcript)
        notes = prepare_vocabulary(client, notes)
        validate_notes(notes)
    save_episode(episode, notes, index)
    print(f"Published learning notes for {episode['id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise
