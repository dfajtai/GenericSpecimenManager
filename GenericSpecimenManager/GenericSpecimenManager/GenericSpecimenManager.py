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
        A JSON-configurable specimen manager: load, segment and annotate a whole study
        from one config file, instead of writing a new module per species / study.<br>
        <ol>
        <li>Pick the study <b>config.json</b> (or create one with <b>Config Editor</b>) and press <b>Initialize Study</b>.</li>
        <li>Select a specimen in the table and <b>Load selected specimen</b> - its images, segmentation and markups open in the configured layout.</li>
        <li>Segment / place markups, then <b>Save active specimen</b>. <b>Close active specimen</b> can also mark it <i>to review</i> or <i>finished</i>.</li>
        <li>Edit the table (status, factor columns) - <b>Save database</b>, or turn on <b>Auto-save database</b>.</li>
        <li><b>Batch export</b> processes every <i>finished</i> specimen: segment files, segment statistics, markups and a markup summary.</li>
        </ol>
        Full config schema and key reference:
        <a href="https://github.com/dfajtai/GenericSpecimenManager#readme">README on GitHub</a>.
        The same reference is also available offline: open the Config Editor and press its <b>Help</b> button.
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
