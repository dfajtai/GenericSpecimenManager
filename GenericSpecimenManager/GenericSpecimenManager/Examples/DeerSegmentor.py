"""
DeerSegmentor
=============

Thin wrapper around SpecimenViewerCommon/GenericSpecimenEngine.py, locked to
the deer-liver study config. This is the module that historically had its
own hand-written Widget/Logic/Deer classes (~5 years of tailor-made,
pre-generic-engine code) plus a separate batch_exporter.py loaded via
importlib. Behaviourally this wrapper reproduces both, driven by
Resources/deer_config.json instead.

Only this file (+ its own Resources/UI, Resources/Icons, Resources/*.json)
is specific to deer; all actual behaviour lives in the shared engine.
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


class DeerSegmentor(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Deer Segmentor"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Daniel Fajtai (Medicopus Nonprofit Ltd.)"]
        self.parent.helpText = """
In-house module for the deer liver segmentation project.
See more information in <a href="https://github.com/dfajtai/3dslicer-ext">module documentation</a>.
"""
        self.parent.acknowledgementText = """Medicopus Nonprofit Ltd."""

        # Own icon in the module selector / Modules toolbar.
        # Drop a square PNG at Resources/Icons/DeerSegmentor.png (this repo
        # only ships a placeholder README there - no artwork was generated).
        icon_path = os.path.join(os.path.dirname(__file__), "Resources", "Icons", "DeerSegmentor.png")
        if os.path.exists(icon_path):
            self.parent.icon = qt.QIcon(icon_path)


class DeerSegmentorWidget(GenericSpecimenModuleWidgetBase):
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "Resources", "deer_config.json")
    UI_RESOURCE = "UI/DeerSegmentor.ui"


class DeerSegmentorTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        # Point Resources/deer_config.json at real csvs to exercise this end to end.
        pass
