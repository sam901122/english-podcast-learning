import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.update_podcast import decide_study_word, prepare_vocabulary


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
