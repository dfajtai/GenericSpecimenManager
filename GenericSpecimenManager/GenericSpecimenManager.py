"""
GenericSpecimenManager
======================

Thin wrapper around Resources/GenericSpecimenEngine.py.

Unlike the per-species wrappers (DeerSegmentor, PigChunker, RabbitVertCount),
this one does NOT lock a CONFIG_PATH - the "Select .json file" row stays
visible so you can point it at any study config.json at runtime. Good for
trying out a new config before "graduating" it into its own thin wrapper
module with its own name/icon.
"""

import os
import sys

# --- bootstrap import of the shared engine (lives in ./Resources, a subfolder of this module) ---
_THIS_DIR = os.path.dirname(__file__)
if _THIS_DIR not in sys.path:
    sys.path.append(_THIS_DIR)

from Resources.GenericSpecimenEngine import GenericSpecimenManagerWidgetBase  # noqa: E402

import slicer
from slicer.ScriptedLoadableModule import *


class GenericSpecimenManager(ScriptedLoadableModule):
    """The Slicer module registration - title/icon/CONFIG_PATH live here; all real behavior is in Resources/GenericSpecimenEngine.py."""
    def __init__(self, parent):
        """Register this module with Slicer: sets title/category/contributors and, if present, a custom icon from Resources/Icons/<ModuleName>.png."""
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Generic Specimen Manager"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Daniel Fajtai"]
        self.parent.helpText = """
        A generic, JSON-configurable specimen loader / segmenter / landmarker.
        Point it at a study config.json (see README.md for the schema) instead of
        writing a new scripted module for every species / study.
        """
        self.parent.acknowledgementText = ""
       
        

class GenericSpecimenManagerWidget(GenericSpecimenManagerWidgetBase):
    """This module's concrete widget - CONFIG_PATH=None keeps the config picker visible (a general-purpose module, not locked to one study)."""
    CONFIG_PATH = None   # no fixed config -> config picker stays visible
    UI_RESOURCE = "UI/GenericSpecimenManager.ui"
    


class GenericSpecimenManagerTest(ScriptedLoadableModuleTest):
    """Placeholder self-test hook (ScriptedLoadableModuleTest) - see runTest()."""
    def setUp(self):
        """Reset the MRML scene before a test run."""
        slicer.mrmlScene.Clear()

    def runTest(self):
        """Entry point Slicer calls to run this module's self-test. Currently a no-op placeholder - point a real config.json + CSVs at the widget and exercise Initialize Study / load / save manually to test end to end."""
        self.setUp()
        # Config-driven module: no fixed self-test data set.
        pass
