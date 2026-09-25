"""Layer guard: core <- utils <- study <- gui. A layer may only import from the layers before it.
Run: python -m unittest discover -s tests"""

import glob
import os
import re
import unittest

RESOURCES = os.path.join(os.path.dirname(__file__), "..", "GenericSpecimenManager", "GenericSpecimenManager", "Resources")
ORDER = {"core": 0, "utils": 1, "study": 2, "gui": 3}


class LayerTest(unittest.TestCase):
    def test_no_upward_imports(self):
        offenders = []
        for layer in ORDER:
            for path in glob.glob(os.path.join(RESOURCES, layer, "**", "*.py"), recursive=True):
                with open(path) as f:
                    text = f.read()
                for match in re.finditer(r"^(?:from|import) Resources\.(\w+)", text, re.M):
                    target = match.group(1)
                    if target in ORDER and ORDER[target] > ORDER[layer]:
                        offenders.append(f"{os.path.relpath(path, RESOURCES)} imports {target}")
        self.assertEqual(offenders, [])

    def test_core_has_no_slicer(self):
        offenders = []
        for path in glob.glob(os.path.join(RESOURCES, "core", "**", "*.py"), recursive=True):
            with open(path) as f:
                text = f.read()
            if re.search(r"^(?:import|from) (?:slicer|qt|vtk|ctk)\b", text, re.M):
                offenders.append(os.path.relpath(path, RESOURCES))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
