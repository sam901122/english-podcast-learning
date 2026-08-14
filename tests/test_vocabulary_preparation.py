import unittest
from unittest.mock import Mock, patch

from scripts.update_podcast import (
    analyze,
    decide_study_words,
    prepare_vocabulary,
    remove_advertising,
    validate_notes,
)


def make_study_set(level):
    return {
        "vocabulary": [
            {
                "word": f"word-{index}",
                "kkPhonetic": "/word/",
                "partOfSpeech": "noun",
                "level": level,
                "meaningZh": "繁體中文解釋",
                "example": f"This sentence contains word-{index}.",
            }
            for index in range(10)
        ],
        "phrases": [
            {
                "phrase": f"phrase-{index}",
                "highlight": f"phrase-{index}",
                "meaningZh": "繁體中文解釋",
                "example": f"This sentence contains phrase-{index}.",
            }
            for index in range(5)
        ],
    }


class AnalyzeTests(unittest.TestCase):
    def test_uses_separate_requests_for_summary_and_each_difficulty(self):
        client = Mock()
        client.generate_json.side_effect = [
            {
                "summaryZh": "繁體中文摘要",
                "summaryEn": "English summary",
            },
            make_study_set("A2"),
            make_study_set("B1"),
            make_study_set("C1"),
        ]

        notes = analyze(
            client,
            {"title": "Episode", "description": "Description"},
            "Transcript text.",
        )

        self.assertEqual(client.generate_json.call_count, 4)
        self.assertEqual(set(notes["studySets"]), {"basic", "intermediate", "advanced"})
        prompts = [call.kwargs["prompt"] for call in client.generate_json.call_args_list]
        self.assertIn("Taiwan Traditional Chinese only", prompts[0])
        self.assertIn("本集 BBC 節目《What in the World》探討", prompts[0])
        self.assertIn("beginner English study set", prompts[1])
        self.assertIn("intermediate English study set", prompts[2])
        self.assertIn("advanced English study set", prompts[3])
        for prompt in prompts:
            self.assertIn("Traditional Chinese", prompt)

        for call in client.generate_json.call_args_list[1:]:
            properties = call.kwargs["schema"]["properties"]
            self.assertEqual(properties["vocabulary"]["minItems"], 10)
            self.assertEqual(properties["vocabulary"]["maxItems"], 10)
            self.assertEqual(properties["phrases"]["minItems"], 5)
            self.assertEqual(properties["phrases"]["maxItems"], 5)


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

        with patch("sys.argv", ["update_podcast.py"]):
            result = main()

        self.assertEqual(result, 0)


class VocabularyPreparationTests(unittest.TestCase):
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
