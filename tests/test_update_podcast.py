import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from scripts.update_podcast import (
    PHRASE_COUNT,
    VOCABULARY_COUNT,
    analyze,
    normalize_traditional_chinese,
    validate_and_sort_notes,
)


LEVELS = {
    "basic": ("B1", "A2"),
    "intermediate": ("B2", "B1"),
    "advanced": ("C2", "C1"),
}


def make_item(kind, study_level, index, level):
    surface = f"{study_level}-{kind}-surface-{index}"
    item = {
        "level": level,
        "meaningZh": "測試",
        "example": f"The podcast says {surface} in this sentence.",
        "exampleParts": [
            {"text": "The podcast says ", "highlight": False},
            {"text": surface, "highlight": True},
            {"text": " in this sentence.", "highlight": False},
        ],
    }
    if kind == "vocabulary":
        item.update({
            "word": f"{study_level}-word-{index}",
            "kkPhonetic": "/test/",
            "partOfSpeech": "noun",
        })
    else:
        item["phrase"] = f"{study_level}-phrase-{index}"
    return item


def make_notes():
    study_sets = {}
    for study_level, levels in LEVELS.items():
        study_sets[study_level] = {
            "vocabulary": [
                make_item("vocabulary", study_level, index, levels[index % 2])
                for index in range(VOCABULARY_COUNT)
            ],
            "phrases": [
                make_item("phrases", study_level, index, levels[index % 2])
                for index in range(PHRASE_COUNT)
            ],
        }
    return {"summaryZh": "摘要", "summaryEn": "Summary", "studySets": study_sets}


class ValidateAndSortNotesTests(unittest.TestCase):
    def test_validates_counts_and_sorts_each_study_set(self):
        notes = validate_and_sort_notes(make_notes())

        for study_set in notes["studySets"].values():
            vocabulary_levels = [item["level"] for item in study_set["vocabulary"]]
            phrase_levels = [item["level"] for item in study_set["phrases"]]
            self.assertEqual(vocabulary_levels, sorted(vocabulary_levels))
            self.assertEqual(phrase_levels, sorted(phrase_levels))

    def test_rejects_duplicate_learning_terms_across_study_sets(self):
        notes = make_notes()
        notes["studySets"]["advanced"]["vocabulary"][0]["word"] = (
            notes["studySets"]["basic"]["vocabulary"][0]["word"]
        )

        with self.assertRaisesRegex(ValueError, "Duplicate or empty word"):
            validate_and_sort_notes(notes)

    def test_rejects_parts_that_do_not_reconstruct_example(self):
        notes = make_notes()
        notes["studySets"]["intermediate"]["phrases"][0]["exampleParts"][1]["text"] = "wrong"

        with self.assertRaisesRegex(ValueError, "do not reconstruct"):
            validate_and_sort_notes(notes)

    def test_rejects_parts_without_llm_selected_highlight(self):
        notes = make_notes()
        parts = notes["studySets"]["advanced"]["vocabulary"][0]["exampleParts"]
        for part in parts:
            part["highlight"] = False

        with self.assertRaisesRegex(ValueError, "exactly one LLM-selected highlight"):
            validate_and_sort_notes(notes)

    def test_accepts_no_phrases_when_none_are_useful(self):
        notes = make_notes()
        for study_set in notes["studySets"].values():
            study_set["phrases"] = []

        validated = validate_and_sort_notes(notes)

        self.assertTrue(all(not study_set["phrases"] for study_set in validated["studySets"].values()))

    def test_rejects_more_than_the_phrase_limit(self):
        notes = make_notes()
        notes["studySets"]["basic"]["phrases"].append(
            make_item("phrases", "basic-extra", PHRASE_COUNT, "B1")
        )

        with self.assertRaisesRegex(ValueError, f"at most {PHRASE_COUNT} basic phrases"):
            validate_and_sort_notes(notes)

    def test_rejects_cefr_level_outside_study_set(self):
        notes = make_notes()
        notes["studySets"]["basic"]["vocabulary"][0]["level"] = "C1"

        with self.assertRaisesRegex(ValueError, "Unexpected CEFR level"):
            validate_and_sort_notes(notes)

    def test_normalizes_generated_chinese_to_taiwan_traditional(self):
        normalized = normalize_traditional_chinese({
            "summaryZh": "这个节目讨论软件和数据库。",
            "nested": [{"meaningZh": "视频里的词汇。"}],
        })

        self.assertEqual(normalized["summaryZh"], "這個節目討論軟件和數據庫。")
        self.assertEqual(normalized["nested"][0]["meaningZh"], "視頻裡的詞彙。")


class AnalyzeTests(unittest.TestCase):
    def test_retries_when_generated_terms_are_duplicated(self):
        invalid_notes = copy.deepcopy(make_notes())
        invalid_notes["studySets"]["advanced"]["vocabulary"][0]["word"] = (
            invalid_notes["studySets"]["basic"]["vocabulary"][0]["word"]
        )
        responses = Mock()
        responses.create.side_effect = [
            SimpleNamespace(output_text=json.dumps(invalid_notes)),
            SimpleNamespace(output_text=json.dumps(make_notes())),
        ]
        client = SimpleNamespace(responses=responses)
        episode = {"title": "Test episode", "description": "Test description"}

        notes = analyze(client, episode, "Test transcript.")

        self.assertEqual(responses.create.call_count, 2)
        retry_prompt = responses.create.call_args_list[1].kwargs["input"]
        self.assertIn("Duplicate or empty word", retry_prompt)
        self.assertEqual(
            len(notes["studySets"]["advanced"]["vocabulary"]),
            VOCABULARY_COUNT,
        )


if __name__ == "__main__":
    unittest.main()
