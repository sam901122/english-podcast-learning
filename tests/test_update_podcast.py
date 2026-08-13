import unittest

from scripts.update_podcast import validate_and_sort_notes


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
        "highlightTerms": [surface],
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
                for index in range(20)
            ],
            "phrases": [
                make_item("phrases", study_level, index, levels[index % 2])
                for index in range(10)
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

    def test_rejects_highlight_term_missing_from_example(self):
        notes = make_notes()
        notes["studySets"]["intermediate"]["phrases"][0]["highlightTerms"] = ["not present"]

        with self.assertRaisesRegex(ValueError, "Invalid highlight term"):
            validate_and_sort_notes(notes)

    def test_rejects_cefr_level_outside_study_set(self):
        notes = make_notes()
        notes["studySets"]["basic"]["vocabulary"][0]["level"] = "C1"

        with self.assertRaisesRegex(ValueError, "Unexpected CEFR level"):
            validate_and_sort_notes(notes)


if __name__ == "__main__":
    unittest.main()
