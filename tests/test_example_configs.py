"""Every config in examples/config must parse with the current schema, and use only keys the schema knows (unknown
keys are ignored silently at runtime, so a typo or an outdated key would otherwise go unnoticed).
Run: python -m unittest discover -s tests"""

import dataclasses
import glob
import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "GenericSpecimenManager", "GenericSpecimenManager"))

from Resources.core.config_model import StudyConfig  # noqa: E402

CONFIGS = sorted(glob.glob(os.path.join(ROOT, "examples", "config", "*.json")))


def _section_fields(cls):
    """The field names of a config dataclass."""
    return {f.name for f in dataclasses.fields(cls)}


class ExampleConfigTest(unittest.TestCase):
    def test_there_are_examples(self):
        self.assertGreater(len(CONFIGS), 3)

    def test_every_example_parses(self):
        for path in CONFIGS:
            with self.subTest(config=os.path.basename(path)):
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                cfg = StudyConfig.from_dict(raw)
                self.assertTrue(cfg.key_columns)

    def test_no_unknown_top_level_or_section_keys(self):
        known_top = _section_fields(StudyConfig)
        sections = {
            name: type(getattr(StudyConfig(), name))
            for name in ("segmentation", "markups", "batch_export", "workspace", "window_level", "slice_rotation",
                         "segment_editor", "group_by_key", "status_filter")
        }
        for path in CONFIGS:
            with self.subTest(config=os.path.basename(path)):
                with open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                self.assertEqual(sorted(set(raw) - known_top), [], "unknown top-level keys")
                for name, cls in sections.items():
                    if isinstance(raw.get(name), dict):
                        self.assertEqual(sorted(set(raw[name]) - _section_fields(cls)), [], f"unknown keys in '{name}'")


if __name__ == "__main__":
    unittest.main()
