"""Packaging guard: every file under Resources/ must be listed in the module's CMakeLists.txt (only listed files are
installed with the extension), and nothing listed may be missing. Run: python -m unittest discover -s tests"""

import os
import re
import unittest

MODULE_DIR = os.path.join(os.path.dirname(__file__), "..", "GenericSpecimenManager", "GenericSpecimenManager")


class PackagingTest(unittest.TestCase):
    def test_cmake_lists_every_resource(self):
        with open(os.path.join(MODULE_DIR, "CMakeLists.txt")) as f:
            cmake = f.read()
        block = re.search(r"set\(MODULE_PYTHON_RESOURCES\n(.*?)\n\s*\)", cmake, re.S).group(1)
        listed = {line.strip().replace("${MODULE_NAME}", "GenericSpecimenManager") for line in block.splitlines() if line.strip()}
        actual = set()
        for root, dirs, files in os.walk(os.path.join(MODULE_DIR, "Resources")):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if not name.endswith(".pyc"):
                    actual.add(os.path.relpath(os.path.join(root, name), MODULE_DIR).replace(os.sep, "/"))
        self.assertEqual(sorted(actual - listed), [], "files missing from CMakeLists.txt MODULE_PYTHON_RESOURCES")
        self.assertEqual(sorted(listed - actual), [], "CMakeLists.txt lists files that do not exist")


if __name__ == "__main__":
    unittest.main()
