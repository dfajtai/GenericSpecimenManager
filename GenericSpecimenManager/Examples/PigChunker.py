"""
PigChunker
==========

Thin wrapper around SpecimenViewerCommon/GenericSpecimenEngine.py, locked to
the pig chunk-segmentation study config. Only this file (+ its own
Resources/UI, Resources/Icons, Resources/pig_config.json) is specific to
pig; all actual behaviour lives in the shared engine.
"""

import os
import sys

_THIS_DIR = os.path.dirname(__file__)
_COMMON_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", "SpecimenViewerCommon"))
if _COMMON_DIR not in sys.path:
    sys.path.append(_COMMON_DIR)

from GenericSpecimenManager.GenericSpecimenManager.GenericSpecimenManager.Resources.GenericSpecimenEngine import GenericSpecimenModuleWidgetBase  # noqa: E402

import qt
import slicer
from slicer.ScriptedLoadableModule import *


class PigChunker(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "PigChunker"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Daniel Fajtai"]
        self.parent.helpText = """
Module for pig chunk segmentation.
See more information in <a href="https://github.com/organization/projectname#PigChunker">module documentation</a>.
"""
        self.parent.acknowledgementText = ""

        icon_path = os.path.join(os.path.dirname(__file__), "Resources", "Icons", "PigChunker.png")
        if os.path.exists(icon_path):
            self.parent.icon = qt.QIcon(icon_path)


class PigChunkerWidget(GenericSpecimenModuleWidgetBase):
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "Resources", "pig_config.json")
    UI_RESOURCE = "UI/PigChunker.ui"


class PigChunkerTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        # Point Resources/pig_config.json at real csvs to exercise this end to end.
        pass
