import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.update_podcast import analyze, decide_study_word, prepare_vocabulary


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
                "meaningZh": "繁體中文解釋",
                "example": f"This sentence contains phrase-{index}.",
            }
            for index in range(5)
        ],
    }


class AnalyzeTests(unittest.TestCase):
    def test_uses_separate_requests_for_summary_and_each_difficulty(self):
        responses = Mock()
        responses.create.side_effect = [
            SimpleNamespace(output_text=json.dumps({
                "summaryZh": "繁體中文摘要",
                "summaryEn": "English summary",
            })),
            SimpleNamespace(output_text=json.dumps(make_study_set("A2"))),
            SimpleNamespace(output_text=json.dumps(make_study_set("B1"))),
            SimpleNamespace(output_text=json.dumps(make_study_set("C1"))),
        ]
        client = SimpleNamespace(responses=responses)

        notes = analyze(
            client,
            {"title": "Episode", "description": "Description"},
            "Transcript text.",
        )

        self.assertEqual(responses.create.call_count, 4)
        self.assertEqual(set(notes["studySets"]), {"basic", "intermediate", "advanced"})
        prompts = [call.kwargs["input"] for call in responses.create.call_args_list]
        self.assertIn("Taiwan Traditional Chinese only", prompts[0])
        self.assertIn("beginner English study set", prompts[1])
        self.assertIn("intermediate English study set", prompts[2])
        self.assertIn("advanced English study set", prompts[3])
        for prompt in prompts:
            self.assertIn("Traditional Chinese", prompt)

        for call in responses.create.call_args_list[1:]:
            properties = call.kwargs["text"]["format"]["schema"]["properties"]
            self.assertEqual(properties["vocabulary"]["minItems"], 10)
            self.assertEqual(properties["vocabulary"]["maxItems"], 10)
            self.assertEqual(properties["phrases"]["minItems"], 5)
            self.assertEqual(properties["phrases"]["maxItems"], 5)


class VocabularyPreparationTests(unittest.TestCase):
    def test_decides_one_word_without_changing_other_fields(self):
        responses = Mock()
        responses.create.return_value = SimpleNamespace(output_text=json.dumps({
            "shouldChange": True,
            "word": "evaporate",
        }))
        client = SimpleNamespace(responses=responses)
        item = {
            "word": "evaporating",
            "partOfSpeech": "verb",
            "meaningZh": "蒸發",
            "example": "The water is evaporating quickly.",
        }

        result = decide_study_word(client, item)

        self.assertEqual(result, "evaporate")
        prompt = responses.create.call_args.kwargs["input"]
        self.assertIn("Original word: evaporating", prompt)
        self.assertNotIn("batteries", prompt)
        self.assertEqual(item["example"], "The water is evaporating quickly.")

    @patch("scripts.update_podcast.decide_study_word")
    def test_locks_highlights_before_updating_display_words(self, decide_study_word):
        replacements = {"evaporating": "evaporate", "batteries": "battery"}
        decide_study_word.side_effect = lambda _client, item: replacements[item["word"]]
        notes = {"vocabulary": [
            {
                "word": "evaporating",
                "partOfSpeech": "verb",
                "meaningZh": "蒸發",
                "example": "The water is evaporating quickly.",
            },
            {
                "word": "batteries",
                "partOfSpeech": "noun",
                "meaningZh": "電池",
                "example": "The batteries ran out.",
            },
        ]}

        result = prepare_vocabulary(object(), notes)

        self.assertEqual(result["vocabulary"][0]["word"], "evaporate")
        self.assertEqual(result["vocabulary"][0]["highlight"], "evaporating")
        self.assertEqual(result["vocabulary"][1]["word"], "battery")
        self.assertEqual(result["vocabulary"][1]["highlight"], "batteries")
        self.assertEqual(result["vocabulary"][0]["example"], "The water is evaporating quickly.")


if __name__ == "__main__":
    unittest.main()
