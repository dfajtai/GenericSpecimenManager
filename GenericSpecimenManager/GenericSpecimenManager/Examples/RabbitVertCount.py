"""
RabbitVertCount
================

Thin wrapper around SpecimenViewerCommon/GenericSpecimenEngine.py, locked to
the rabbit CT rib/vertebra counting study config. Only this file (+ its own
Resources/UI, Resources/Icons, Resources/rabbit_config.json) is specific to
rabbit; all actual behaviour lives in the shared engine.
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


class RabbitVertCount(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Rabbit 2 Segment"
        self.parent.categories = ["Segmentation"]
        self.parent.dependencies = []
        self.parent.contributors = ["Daniel Fajtai"]
        self.parent.helpText = """
Module for rabbit CT rib and vertebra counting.
See more information in <a href="https://github.com/organization/projectname#RabbitVertCount">module documentation</a>.
"""
        self.parent.acknowledgementText = ""

        icon_path = os.path.join(os.path.dirname(__file__), "Resources", "Icons", "RabbitVertCount.png")
        if os.path.exists(icon_path):
            self.parent.icon = qt.QIcon(icon_path)


class RabbitVertCountWidget(GenericSpecimenModuleWidgetBase):
    CONFIG_PATH = os.path.join(os.path.dirname(__file__), "Resources", "rabbit_config.json")
    UI_RESOURCE = "UI/RabbitVertCount.ui"


class RabbitVertCountTest(ScriptedLoadableModuleTest):
    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        # Point Resources/rabbit_config.json at real csvs to exercise this end to end.
        pass
