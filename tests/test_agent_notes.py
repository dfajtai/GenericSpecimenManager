"""Keeps CLAUDE.md honest: every file it mentions must exist, and AGENTS.md must be an identical copy.
Run: python -m unittest discover -s tests"""

import os
import re
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
MODULE = os.path.join(ROOT, "GenericSpecimenManager", "GenericSpecimenManager")
BASES = [ROOT, MODULE, os.path.join(MODULE, "Resources")]


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class AgentNotesTest(unittest.TestCase):
    def test_mentioned_files_exist(self):
        text = _read(os.path.join(ROOT, "CLAUDE.md"))
        missing = []
        for token in re.findall(r"`([\w./-]+\.(?:py|md|html|txt))`", text):
            if not any(os.path.exists(os.path.join(base, token)) for base in BASES):
                missing.append(token)
        self.assertEqual(missing, [], "CLAUDE.md mentions files that do not exist")

    def test_agents_md_is_a_copy(self):
        self.assertEqual(_read(os.path.join(ROOT, "AGENTS.md")), _read(os.path.join(ROOT, "CLAUDE.md")))


if __name__ == "__main__":
    unittest.main()
