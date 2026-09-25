"""
main_widget.py
==============
The module GUI: GenericSpecimenManagerWidgetBase - setup, module enter/exit, parameter node, scene events. The behaviour
is split across the mixins in this folder (specimen table, annotation, study setup, specimen actions).
"""

import qt
import slicer
import vtk
from slicer.ScriptedLoadableModule import ScriptedLoadableModuleWidget
from slicer.util import VTKObservationMixin

from Resources.definitions import (
    HIDE_HELP_AND_ACKNOWLEDGEMENT as _DEFINITIONS_HIDE_HELP_AND_ACKNOWLEDGEMENT,
    HIDE_RELOAD_AND_TEST as _DEFINITIONS_HIDE_RELOAD_AND_TEST,
    SPECIMEN_STATUS_LABELS,
    SpecimenStatus,
)
from Resources.gui.annotation import AnnotationMixin
from Resources.gui.help_dialog import show_cheatsheet_dialog
from Resources.gui.specimen_actions import SpecimenActionsMixin
from Resources.gui.specimen_table import SpecimenTableMixin
from Resources.gui.study_setup import StudySetupMixin
from Resources.utils.config_location import default_config_dir
from Resources.study.logic import GenericSpecimenManagerLogic
from Resources.utils.slicer_ui import SaveShortcut, set_help_section_visible


# (label, anchor) pairs of Resources/Html/module_help_cheatsheet.html, for the Help popup's section-jump combo
MODULE_HELP_SECTIONS = [
    ("Workflow", "workflow"), ("Study buttons & settings", "study-settings"), ("Specimen table", "specimen-table"),
    ("Status", "status"), ("Load, Save, Close", "load-save-close"), ("Reset selected specimen", "reset"),
    ("Batch export", "batch-export"), ("Config", "config"),
]


class GenericSpecimenManagerWidgetBase(SpecimenTableMixin, AnnotationMixin, StudySetupMixin, SpecimenActionsMixin,
                                       ScriptedLoadableModuleWidget, VTKObservationMixin):
    """The actual module GUI: config/CSV path pickers, the specimen table, group-select combo, and the load/save/close/batch-export buttons. Subclassed per named wrapper module (CONFIG_PATH set) or used directly for the general-purpose config-picker module (CONFIG_PATH=None)."""
    CONFIG_PATH = None

    # Actual on/off values live in Resources/definitions.py (one place for
    # every hardcoded toggle in this module) - kept as class attributes here
    # too, so a subclass could still override just its own instance if ever
    # needed, without touching the shared default.
    HIDE_RELOAD_AND_TEST = _DEFINITIONS_HIDE_RELOAD_AND_TEST
    HIDE_HELP_AND_ACKNOWLEDGEMENT = _DEFINITIONS_HIDE_HELP_AND_ACKNOWLEDGEMENT
    UI_RESOURCE = "UI/GenericSpecimenManager.ui"

    def __init__(self, parent=None):
        """Per-instance GUI state: the Logic object (created in setup()), the observed parameter node, and small bits of transient UI state (selected specimen key, current batch filter, a re-entrancy guard for table edits)."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False
        self.tbl_selected_key = None
        self.table_lock = False
        self._displayed_keys = []
        self._group_filter = None
        self._status_filter = None               # set of SpecimenStatus ticked in the status filter, None = all (no filtering)
        self._annotationActors = []              # (view, renderer, vtkTextActor) of the specimen annotation, if shown
        self._studyInitialized = False           # True only after a fully successful Initialize Study
        self._active_specimen_observed = None    # the GenericSpecimen currently wired to _onActiveSpecimenNodeModified, if any
        self._saveShortcut = None                # the Ctrl+S shortcut (utils/slicer_ui.SaveShortcut), created in setup()

    def setup(self):
        """Slicer calls this once when the module widget is first shown: load the .ui, wire every button/field, hide the config picker if CONFIG_PATH locks this wrapper to one study, and initialize the parameter node."""
        ScriptedLoadableModuleWidget.setup(self)
        uiWidget = slicer.util.loadUI(self.resourcePath(self.UI_RESOURCE))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        self._uiWidget = uiWidget
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.logic = GenericSpecimenManagerLogic()
        self.logic.default_config_path = self.CONFIG_PATH

        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        self.ui.tbConfigPath.textChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.tbDBPath.textChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.tbPresegPath.textChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.tbConfigPath.textChanged.connect(lambda: self._validatePathField(self.ui.tbConfigPath))
        self.ui.tbDBPath.textChanged.connect(lambda: self._validatePathField(self.ui.tbDBPath))
        self.ui.tbPresegPath.textChanged.connect(lambda: self._validatePathField(self.ui.tbPresegPath))
        self.ui.tblSpecimens.selectionModel().selectionChanged.connect(self.selectedSpecimenChanged)
        self.ui.tblSpecimens.itemChanged.connect(self.specimenTblChanged)

        self.ui.btnSelectConfig.connect('clicked(bool)', self.onBtnSelectConfig)
        self.ui.btnInitializeStudy.connect('clicked(bool)', self.onBtnInitializeStudy)
        self.ui.btnSelectDB.connect('clicked(bool)', self.onBtnSelectDB)
        self.ui.btnSelectPreseg.connect('clicked(bool)', self.onBtnSelectPreseg)
        self.ui.btnBatchExport.connect('clicked(bool)', self.onBtnBatchExport)
        self.ui.btnConfigEditor.connect('clicked(bool)', self.onBtnConfigEditor)
        slicer.app.connect('aboutToQuit()', lambda: self.logic.release_study_lock() if self.logic is not None else None)
        # Ctrl+S runs this module's save while a specimen is loaded (active only then - see _syncSaveShortcut)
        self._saveShortcut = SaveShortcut(self._onSaveShortcut)
        self.ui.btnModuleHelp.connect('clicked(bool)', lambda checked=False: show_cheatsheet_dialog(
            slicer.util.mainWindow(), "Generic Specimen Manager - Cheat Sheet", "module_help_cheatsheet.html", MODULE_HELP_SECTIONS))
        self.ui.btnLoadSelected.connect('clicked(bool)', self.onBtnLoadSelected)
        self.ui.btnSaveActiveSpecimen.connect('clicked(bool)', self.onBtnSaveActiveSpecimen)
        self.ui.btnCloseActiveSpecimen.connect('clicked(bool)', self.onBtnCloseActiveSpecimen)
        self.ui.btnResetSelectedSpecimen.connect('clicked(bool)', self.onBtnResetSelectedSpecimen)
        self.ui.btnSaveDB.connect('clicked(bool)', self.onBtnSaveDB)
        self.ui.studySettingsCollapsibleButton.connect('toggled(bool)', lambda checked=False: qt.QTimer.singleShot(0, self._fitSpecimenTableHeight))
        self.ui.helpCollapsibleButton.connect('toggled(bool)', lambda checked=False: qt.QTimer.singleShot(0, self._fitSpecimenTableHeight))
        self.ui.wOps.connect('toggled(bool)', lambda checked=False: qt.QTimer.singleShot(0, self._fitSpecimenTableHeight))
        self.ui.cmbGroupByKey.currentTextChanged.connect(self.onGroupByKeyChanged)
        self.ui.wGroupByKey.visible = False
        for st in SpecimenStatus:
            self.ui.cmbStatusFilter.addItem(SPECIMEN_STATUS_LABELS[st])
        self._checkAllStatusFilter()
        self.ui.cmbStatusFilter.checkedIndexesChanged.connect(self.onStatusFilterChanged)

        if self.CONFIG_PATH:
            self.ui.lblConfig.visible = False
            self.ui.btnSelectConfig.visible = False
            self.ui.tbConfigPath.visible = False

        # ScriptedLoadableModuleWidget.setup() above only builds this when
        # Slicer's global Edit > Application Settings > Developer > "Enable
        # developer mode" is on. Gated by HIDE_RELOAD_AND_TEST (class
        # attribute above) - flip that to False to keep showing it.
        if self.HIDE_RELOAD_AND_TEST and hasattr(self, "reloadCollapsibleButton"):
            self.reloadCollapsibleButton.hide()

        self.initializeParameterNode()
        self._updatePostInitButtonStates()
        self._fitSpecimenTableHeight()

    def _updatePostInitButtonStates(self):
        """Enable/disable/show the controls that only make sense once a study has actually been
        initialized: Load selected specimen, Save progress, Close active specimen, Reset and the
        Status filter start disabled, and Save database CSV / Batch export start hidden (each
        shown only if the config wants it) - so a clean/blank module can't be clicked into a
        confusing failure before Initialize Study has run. The Initialize Study button itself is
        pastel green until a study is initialized. Called after setup(), after a successful
        Initialize Study, and after every load/save/close of the active specimen."""
        ready = self.logic is not None and self.logic.cfg is not None and self._studyInitialized
        active = ready and self.logic.hasActiveSpecimen
        # Initialize Study nudges (pastel green) until a study is initialized; then the buttons
        # that need one appear below it - Save database CSV unless the config auto-saves it,
        # Batch export only if the config enables it.
        self.ui.btnInitializeStudy.setStyleSheet("" if ready else "QPushButton { background-color: #cdeccd; color: black; }")
        self.ui.btnSaveDB.visible = bool(ready and not self.logic.cfg.auto_save_database)
        self.ui.btnBatchExport.visible = bool(ready and self.logic.cfg.batch_export.enabled)
        self.ui.cmbStatusFilter.enabled = ready
        self.ui.btnLoadSelected.enabled = ready and not active
        self.ui.btnSaveActiveSpecimen.enabled = active
        self.ui.btnCloseActiveSpecimen.enabled = active
        self.ui.btnResetSelectedSpecimen.enabled = ready
        self._syncSaveShortcut()

    def cleanup(self):
        """Standard ScriptedLoadableModuleWidget hook: Slicer calls this when the widget is being destroyed."""
        self.removeObservers()
        if self.logic is not None:
            self.logic.release_study_lock()
        if self._saveShortcut is not None:
            self._saveShortcut.dispose()
            self._saveShortcut = None

    def enter(self):
        """Standard hook: Slicer calls this every time the user switches into this module."""
        self.initializeParameterNode()
        self._installScrollAreaWatch()
        if self.HIDE_HELP_AND_ACKNOWLEDGEMENT:
            set_help_section_visible(False)

    def exit(self):
        """Standard hook: Slicer calls this every time the user switches away from this module."""
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        if self.HIDE_HELP_AND_ACKNOWLEDGEMENT:
            set_help_section_visible(True)

    def onSceneStartClose(self, caller, event):
        """Close the active specimen (without confirmation - the scene is going away regardless) before the MRML scene is actually torn down."""
        if self.logic and self.logic.hasActiveSpecimen:
            self.logic.close_active_specimen(no_question=True)
            self._detachActiveSpecimenObservers()
            self._clearSpecimenAnnotation()
            self._syncSaveShortcut()
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """Re-attach a fresh parameter node once a new (empty) scene is ready, if this module is currently the one shown."""
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        """Fetch (or create) this module's parameter node and hand it to setParameterNode()."""
        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode):
        """Swap the observed parameter node, re-wiring the Modified-event observer so the GUI fields stay in sync whenever the node changes (including from outside this widget, e.g. scene load)."""
        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """Push the parameter node's saved values into the path text fields (an empty ConfigPath is pre-filled with the folder config browsing starts in - see ConfigLocation.default_config_dir()), then live-validate each field's existence."""
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        self._updatingGUIFromParameterNode = True
        start_dir = default_config_dir()
        if start_dir and str(self._parameterNode.GetParameter("ConfigPath")) == "":
            self.ui.tbConfigPath.text = start_dir
        else:
            self.ui.tbConfigPath.text = str(self._parameterNode.GetParameter("ConfigPath"))
        self.ui.tbDBPath.text = str(self._parameterNode.GetParameter("DatabaseCSVPath"))
        self.ui.tbPresegPath.text = str(self._parameterNode.GetParameter("PresegCSVPath"))
        for edit in (self.ui.tbConfigPath, self.ui.tbDBPath, self.ui.tbPresegPath):
            self._validatePathField(edit)
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """Push the path text fields' current values back into the parameter node, so they persist with the scene."""
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        wasModified = self._parameterNode.StartModify()
        self._parameterNode.SetParameter("ConfigPath", str(self.ui.tbConfigPath.text))
        self._parameterNode.SetParameter("DatabaseCSVPath", str(self.ui.tbDBPath.text))
        self._parameterNode.SetParameter("PresegCSVPath", str(self.ui.tbPresegPath.text))
        self._parameterNode.EndModify(wasModified)
