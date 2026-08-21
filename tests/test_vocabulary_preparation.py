import unittest
from unittest.mock import Mock, patch

from scripts.update_podcast import (
    analyze,
    decide_study_words,
    filter_topic_duplicates,
    prepare_vocabulary,
    remove_advertising,
    validate_notes,
)


def make_study_set(level, vocabulary_count=10, phrase_count=5):
    study_set = {
        "vocabulary": [
            {
                "word": f"word-{index}",
                "kkPhonetic": "/word/",
                "partOfSpeech": "noun",
                "level": level,
                "meaningZh": "繁體中文解釋",
                "example": f"This sentence contains word-{index}.",
            }
            for index in range(vocabulary_count)
        ],
    }
    if phrase_count:
        study_set["phrases"] = [
            {
                "phrase": f"phrase-{index}",
                "highlight": f"phrase-{index}",
                "meaningZh": "繁體中文解釋",
                "example": f"This sentence contains phrase-{index}.",
            }
            for index in range(phrase_count)
        ]
    return study_set


def make_valid_notes(topic_count=3, topic_phrase_count=0):
    study_sets = {
        "practical": make_study_set("A2"),
        "advanced": make_study_set("C1"),
        "topic": make_study_set("B2", topic_count, topic_phrase_count),
    }
    for index, item in enumerate(study_sets["topic"]["vocabulary"]):
        item["word"] = f"topic-{index}"
        item["example"] = f"This sentence contains topic-{index}."
    for study_set in study_sets.values():
        for item in study_set["vocabulary"]:
            item["highlight"] = item["word"]
        for item in study_set.get("phrases", []):
            item["highlight"] = item["phrase"]
    return {"studySets": study_sets}


class AnalyzeTests(unittest.TestCase):
    def test_uses_separate_requests_for_summary_and_each_difficulty(self):
        client = Mock()
        client.generate_json.side_effect = [
            {
                "summaryZh": "繁體中文摘要",
                "summaryEn": "English summary",
            },
            make_study_set("A2"),
            make_study_set("C1"),
            make_study_set("B2", vocabulary_count=7, phrase_count=0),
        ]

        notes = analyze(
            client,
            {"title": "Episode", "description": "Description"},
            "Transcript text.",
        )

        self.assertEqual(client.generate_json.call_count, 4)
        self.assertEqual(set(notes["studySets"]), {"practical", "advanced", "topic"})
        prompts = [call.kwargs["prompt"] for call in client.generate_json.call_args_list]
        self.assertIn("Taiwan Traditional Chinese only", prompts[0])
        self.assertIn("本集 BBC 節目《What in the World》探討", prompts[0])
        self.assertIn("practical English study set", prompts[1])
        self.assertIn("advanced English study set", prompts[2])
        self.assertIn("topic-focused English study set", prompts[3])
        self.assertIn("do not pad it with generic", prompts[3])
        self.assertIn("Do not return phrases", prompts[3])
        for prompt in prompts:
            self.assertIn("Traditional Chinese", prompt)

        for call in client.generate_json.call_args_list[1:3]:
            properties = call.kwargs["schema"]["properties"]
            self.assertEqual(properties["vocabulary"]["minItems"], 10)
            self.assertEqual(properties["vocabulary"]["maxItems"], 10)
            self.assertEqual(properties["phrases"]["minItems"], 5)
            self.assertEqual(properties["phrases"]["maxItems"], 5)
        topic_properties = client.generate_json.call_args_list[3].kwargs["schema"]["properties"]
        self.assertEqual(topic_properties["vocabulary"]["minItems"], 3)
        self.assertEqual(topic_properties["vocabulary"]["maxItems"], 15)
        self.assertNotIn("phrases", topic_properties)
        self.assertIn("Use this priority order", prompts[3])
        self.assertIn("useful place names", prompts[3])
        self.assertIn("Excluded practical and advanced words", prompts[3])


class AdvertisingRemovalTests(unittest.TestCase):
    def test_removes_only_exact_segments_returned_by_the_model(self):
        client = Mock()
        client.generate_json.return_value = {
            "segments": ["Buy our unrelated product today.", "A rewritten passage."],
        }
        transcript = (
            "Welcome to the programme. Buy our unrelated product today. "
            "Orangutans depend on healthy forests."
        )

        result = remove_advertising(
            client,
            {"title": "Orangutans", "description": "Risks facing orangutans"},
            transcript,
        )

        self.assertEqual(result, "Welcome to the programme. Orangutans depend on healthy forests.")
        prompt = client.generate_json.call_args.kwargs["prompt"]
        self.assertIn("EXACT, contiguous verbatim substring", prompt)
        self.assertIn("When uncertain, keep it", prompt)


class MainTests(unittest.TestCase):
    @patch("scripts.update_podcast.fetch")
    @patch("scripts.update_podcast.parse_feed")
    def test_rejects_an_episode_offset_outside_the_feed(self, parse_feed, fetch):
        from scripts.update_podcast import main

        fetch.return_value = b"feed"
        parse_feed.return_value = [{"id": "first"}]
        with patch("sys.argv", ["update_podcast.py", "--episode-offset", "2"]):
            with self.assertRaisesRegex(ValueError, "outside the RSS feed"):
                main()

    @patch("scripts.update_podcast.load_index")
    @patch("scripts.update_podcast.fetch")
    @patch("scripts.update_podcast.parse_feed")
    def test_stops_when_latest_episode_is_already_known(self, parse_feed, fetch, load_index):
        from scripts.update_podcast import main

        fetch.return_value = b"feed"
        parse_feed.return_value = [
            {"id": "latest", "title": "Latest episode"},
            {"id": "older", "title": "Older unprocessed episode"},
        ]
        load_index.return_value = [{"id": "latest"}]

        with (
            patch("sys.argv", ["update_podcast.py"]),
            patch("scripts.update_podcast.find_spotify_episode_url") as spotify_lookup,
            patch("scripts.update_podcast.GeminiClient") as gemini_client,
        ):
            result = main()

        self.assertEqual(result, 0)
        spotify_lookup.assert_not_called()
        gemini_client.assert_not_called()


class VocabularyPreparationTests(unittest.TestCase):
    def test_accepts_topic_sets_at_both_size_limits(self):
        for topic_count in (3, 15):
            with self.subTest(topic_count=topic_count):
                validate_notes(make_valid_notes(topic_count=topic_count))

    def test_rejects_topic_sets_outside_size_limits(self):
        for topic_count in (2, 16):
            with self.subTest(topic_count=topic_count):
                with self.assertRaisesRegex(ValueError, "topic study set"):
                    validate_notes(make_valid_notes(topic_count=topic_count))

    def test_rejects_phrases_in_topic_set(self):
        with self.assertRaisesRegex(ValueError, "topic study set"):
            validate_notes(make_valid_notes(topic_phrase_count=1))

    def test_requires_fixed_counts_for_practical_and_advanced_sets(self):
        for study_level in ("practical", "advanced"):
            with self.subTest(study_level=study_level):
                notes = make_valid_notes()
                notes["studySets"][study_level]["vocabulary"].pop()
                with self.assertRaisesRegex(ValueError, f"{study_level} study set"):
                    validate_notes(notes)

    def test_filters_topic_words_already_used_in_other_sets(self):
        notes = make_valid_notes()
        practical_word = notes["studySets"]["practical"]["vocabulary"][0]["word"]
        notes["studySets"]["topic"]["vocabulary"][0]["word"] = practical_word.upper()

        result = filter_topic_duplicates(notes)

        topic_words = [item["word"] for item in result["studySets"]["topic"]["vocabulary"]]
        self.assertNotIn(practical_word.upper(), topic_words)
        self.assertEqual(len(topic_words), 2)

    def test_rejects_a_highlight_missing_from_its_example(self):
        notes = {"studySets": {
            level: make_study_set(config_level)
            for level, config_level in (("basic", "A2"), ("intermediate", "B1"), ("advanced", "C1"))
        }}
        for study_set in notes["studySets"].values():
            for item in study_set["vocabulary"]:
                item["highlight"] = item["word"]
        notes["studySets"]["advanced"]["vocabulary"][0]["highlight"] = "missing"

        with self.assertRaisesRegex(ValueError, "absent from its example"):
            validate_notes(notes)

    def test_decides_one_word_without_changing_other_fields(self):
        client = Mock()
        client.generate_json.return_value = {"items": [{
            "id": 0, "word": "evaporate", "kkPhonetic": "/ɪˈvæpəˌret/",
        }]}
        item = {
            "word": "evaporating",
            "partOfSpeech": "verb",
            "meaningZh": "蒸發",
            "example": "The water is evaporating quickly.",
        }

        item["kkPhonetic"] = "/ɪˈvæpəˌretɪŋ/"
        result = decide_study_words(client, [item])[0]

        self.assertEqual(result, {
            "word": "evaporate",
            "kkPhonetic": "/ɪˈvæpəˌret/",
        })
        prompt = client.generate_json.call_args.kwargs["prompt"]
        self.assertIn("Original word: evaporating", prompt)
        self.assertNotIn("batteries", prompt)
        self.assertEqual(item["example"], "The water is evaporating quickly.")

    def test_batches_words_and_locks_highlights_before_updating_display_words(self):
        client = Mock()
        client.generate_json.return_value = {"items": [
            {"id": 0, "word": "evaporate", "kkPhonetic": "/evaporate/"},
            {"id": 1, "word": "battery", "kkPhonetic": "/battery/"},
        ]}
        notes = {"vocabulary": [
            {
                "word": "evaporating",
                "kkPhonetic": "/evaporating/",
                "partOfSpeech": "verb",
                "meaningZh": "蒸發",
                "example": "The water is evaporating quickly.",
            },
            {
                "word": "batteries",
                "kkPhonetic": "/batteries/",
                "partOfSpeech": "noun",
                "meaningZh": "電池",
                "example": "The batteries ran out.",
            },
        ]}

        result = prepare_vocabulary(client, notes)

        self.assertEqual(client.generate_json.call_count, 1)
        schema = client.generate_json.call_args.kwargs["schema"]
        self.assertEqual(schema["properties"]["items"]["minItems"], 2)
        self.assertEqual(schema["properties"]["items"]["maxItems"], 2)

        self.assertEqual(result["vocabulary"][0]["word"], "evaporate")
        self.assertEqual(result["vocabulary"][0]["highlight"], "evaporating")
        self.assertEqual(result["vocabulary"][0]["kkPhonetic"], "/evaporate/")
        self.assertEqual(result["vocabulary"][1]["word"], "battery")
        self.assertEqual(result["vocabulary"][1]["highlight"], "batteries")
        self.assertEqual(result["vocabulary"][1]["kkPhonetic"], "/battery/")
        self.assertEqual(result["vocabulary"][0]["example"], "The water is evaporating quickly.")


if __name__ == "__main__":
    unittest.main()
