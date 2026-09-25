"""
paths.py
========
Where the module's bundled data lives, resolved from this file's location so it doesn't matter how
deep the code that needs it sits (core/, study/, gui/ ...). The data folders themselves (UI/, Html/,
Presets/, Icons/) stay directly under Resources/ - that is where Slicer's packaging expects them.
"""

import os

RESOURCES_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_DIR = os.path.join(RESOURCES_DIR, "Html")
PRESETS_DIR = os.path.join(RESOURCES_DIR, "Presets")
# <repo root>/examples/config - only exists in a git checkout (Resources -> module -> extension -> repo root)
EXAMPLES_CONFIG_DIR = os.path.normpath(os.path.join(RESOURCES_DIR, "..", "..", "..", "examples", "config"))
