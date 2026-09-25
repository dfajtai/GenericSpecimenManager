"""
workspace_tab.py
================
Workspace tab: window/level, slice rotation, crosshair, ruler, markers, view convention, annotation.
"""

import qt

from Resources.definitions import (
    CROSSHAIR_BEHAVIOR_CHOICES,
    CROSSHAIR_MODE_CHOICES,
    CROSSHAIR_THICKNESS_CHOICES,
    ORIENTATION_MARKER_SIZE_CHOICES,
    ORIENTATION_MARKER_TYPE_CHOICES,
    RULER_TYPE_CHOICES,
)
from Resources.gui.config_editor.helpers import to_float


class WorkspaceTabMixin:
    """Workspace tab: window/level, slice rotation, crosshair, ruler, markers, view convention, annotation."""


    def _buildWorkspaceTab(self):
        """Everything applied once, per-specimen, to the 3D Slicer workspace itself (not to the data): blanket window/level, slice rotation, crosshair mode/behavior/thickness, ruler, and 3D orientation marker."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)

        wlGroup = qt.QGroupBox("Window/level (every loaded volume)")
        wlForm = qt.QFormLayout(wlGroup)
        self.chkWlEnabled = qt.QCheckBox("Enabled")
        self.chkWlEnabled.setToolTip("Blanket min/max window applied to ALL loaded scalar volumes after a specimen loads - different from an Images-tab row's own per-image window_level.")
        wlForm.addRow(self.chkWlEnabled)
        self.wlMinEdit = qt.QLineEdit()
        self.wlMinEdit.setToolTip("Lower display value, e.g. -150 for a typical CT soft-tissue window.")
        self.wlMaxEdit = qt.QLineEdit()
        self.wlMaxEdit.setToolTip("Upper display value, e.g. 700 for a typical CT soft-tissue window.")
        wlRow = qt.QHBoxLayout()
        wlRow.addWidget(qt.QLabel("Min:"))
        wlRow.addWidget(self.wlMinEdit)
        wlRow.addWidget(qt.QLabel("Max:"))
        wlRow.addWidget(self.wlMaxEdit)
        wlForm.addRow(wlRow)
        layout.addWidget(wlGroup)

        rotGroup = qt.QGroupBox("Slice rotation (in-plane, degrees)")
        rotForm = qt.QFormLayout(rotGroup)
        self.chkSliceRotationEnabled = qt.QCheckBox("Enabled")
        self.chkSliceRotationEnabled.setToolTip(
            "Rotates Red/Yellow/Green in-plane (around each view's own normal) once a specimen loads - "
            "identical to the Reformat module's rotation slider. Leave a view's field empty to leave it alone.")
        rotForm.addRow(self.chkSliceRotationEnabled)
        self.sliceRotRedEdit = qt.QLineEdit()
        self.sliceRotRedEdit.setPlaceholderText("e.g. 180")
        self.sliceRotYellowEdit = qt.QLineEdit()
        self.sliceRotYellowEdit.setPlaceholderText("e.g. -90")
        self.sliceRotGreenEdit = qt.QLineEdit()
        self.sliceRotGreenEdit.setPlaceholderText("e.g. -90")
        rotRow = qt.QHBoxLayout()
        for label, edit in (("Red:", self.sliceRotRedEdit), ("Yellow:", self.sliceRotYellowEdit), ("Green:", self.sliceRotGreenEdit)):
            rotRow.addWidget(qt.QLabel(label))
            rotRow.addWidget(edit)
        rotForm.addRow(rotRow)
        layout.addWidget(rotGroup)

        chGroup = qt.QGroupBox("Crosshair")
        chForm = qt.QFormLayout(chGroup)
        chHint = qt.QLabel("Leave any field at (unset) to keep this module's usual default (ShowBasic / OffsetJumpSlice / Fine).")
        chHint.setWordWrap(True)
        chForm.addRow(chHint)
        self.crosshairModeCombo = qt.QComboBox()
        self.crosshairModeCombo.setEditable(True)
        self.crosshairModeCombo.addItems(CROSSHAIR_MODE_CHOICES)
        self.crosshairModeCombo.setToolTip("Which crosshair lines are drawn.")
        chForm.addRow("Mode:", self.crosshairModeCombo)
        self.crosshairBehaviorCombo = qt.QComboBox()
        self.crosshairBehaviorCombo.setEditable(True)
        self.crosshairBehaviorCombo.addItems(CROSSHAIR_BEHAVIOR_CHOICES)
        self.crosshairBehaviorCombo.setToolTip("OffsetJumpSlice: clicking one view scrolls the others to follow, without recentering them.")
        chForm.addRow("Behavior:", self.crosshairBehaviorCombo)
        self.crosshairThicknessCombo = qt.QComboBox()
        self.crosshairThicknessCombo.setEditable(True)
        self.crosshairThicknessCombo.addItems(CROSSHAIR_THICKNESS_CHOICES)
        chForm.addRow("Thickness:", self.crosshairThicknessCombo)
        layout.addWidget(chGroup)

        rulerGroup = qt.QGroupBox("Ruler")
        rulerForm = qt.QFormLayout(rulerGroup)
        self.rulerTypeCombo = qt.QComboBox()
        self.rulerTypeCombo.setEditable(True)
        self.rulerTypeCombo.addItems(RULER_TYPE_CHOICES)
        self.rulerTypeCombo.setToolTip("Adds a scale ruler to every slice view (Red/Yellow/Green). (unset) leaves Slicer's own default/previous state alone.")
        rulerForm.addRow("Type:", self.rulerTypeCombo)
        layout.addWidget(rulerGroup)

        markerRow = qt.QHBoxLayout()

        marker3dGroup = qt.QGroupBox("3D marker")
        marker3dForm = qt.QFormLayout(marker3dGroup)
        self.orientationMarkerTypeCombo = qt.QComboBox()
        self.orientationMarkerTypeCombo.setEditable(True)
        self.orientationMarkerTypeCombo.addItems(ORIENTATION_MARKER_TYPE_CHOICES)
        self.orientationMarkerTypeCombo.setToolTip(
            "Shape of the orientation marker shown in the 3D view. (unset) leaves it alone - except "
            "Volume rendering, which always shows one (Axes/Large) regardless, unless overridden here.")
        marker3dForm.addRow("Type:", self.orientationMarkerTypeCombo)
        self.orientationMarkerSizeCombo = qt.QComboBox()
        self.orientationMarkerSizeCombo.setEditable(True)
        self.orientationMarkerSizeCombo.addItems(ORIENTATION_MARKER_SIZE_CHOICES)
        marker3dForm.addRow("Size:", self.orientationMarkerSizeCombo)
        markerRow.addWidget(marker3dGroup)

        marker2dGroup = qt.QGroupBox("2D marker")
        marker2dForm = qt.QFormLayout(marker2dGroup)
        self.orientationMarker2dTypeCombo = qt.QComboBox()
        self.orientationMarker2dTypeCombo.setEditable(True)
        self.orientationMarker2dTypeCombo.addItems(ORIENTATION_MARKER_TYPE_CHOICES)
        self.orientationMarker2dTypeCombo.setToolTip(
            "Same marker, shown in every slice view (Red/Yellow/Green) instead of the 3D view - slice "
            "views support the same marker property. (unset) leaves it alone.")
        marker2dForm.addRow("Type:", self.orientationMarker2dTypeCombo)
        self.orientationMarker2dSizeCombo = qt.QComboBox()
        self.orientationMarker2dSizeCombo.setEditable(True)
        self.orientationMarker2dSizeCombo.addItems(ORIENTATION_MARKER_SIZE_CHOICES)
        marker2dForm.addRow("Size:", self.orientationMarker2dSizeCombo)
        markerRow.addWidget(marker2dGroup)

        layout.addLayout(markerRow)

        conventionGroup = qt.QGroupBox("View convention (left/right display)")
        conventionLayout = qt.QVBoxLayout(conventionGroup)
        conventionHint = qt.QLabel(
            "Which side of the screen shows the patient's right. Mutually exclusive - only affects "
            "Axial and Coronal views (Sagittal has no left/right ambiguity to flip).")
        conventionHint.setWordWrap(True)
        conventionLayout.addWidget(conventionHint)
        self.radioRadiological = qt.QRadioButton("Radiological - patient's right on screen-LEFT (Slicer's own default)")
        self.radioNeurological = qt.QRadioButton("Neurological - patient's right on screen-RIGHT")
        self.radioRadiological.setChecked(True)
        conventionRow = qt.QHBoxLayout()
        conventionRow.addWidget(self.radioRadiological)
        conventionRow.addWidget(self.radioNeurological)
        conventionLayout.addLayout(conventionRow)
        layout.addWidget(conventionGroup)

        annotationGroup = qt.QGroupBox("Specimen annotation (optional)")
        annotationLayout = qt.QVBoxLayout(annotationGroup)
        self.chkSpecimenAnnotation = qt.QCheckBox("Show the active specimen's database row in the views")
        self.chkSpecimenAnnotation.setToolTip(
            "<html>While a specimen is loaded, shows yellow text in the top-left of the Red/Yellow/Green "
            "and 3D views:<br>&bull; the ID (the key columns joined with '-')<br>"
            "&bull; a line<br>&bull; one 'column: value' line per remaining Table column (General tab)<br>"
            "&bull; a line<br>&bull; the specimen's status<br>Updated live as the table is edited.</html>")
        annotationLayout.addWidget(self.chkSpecimenAnnotation)
        layout.addWidget(annotationGroup)

        return w

    def _populateWorkspace(self, cfg):
        """Fill the Workspace tab from the raw config dict `cfg`."""
        wl = cfg.get("window_level", {}) or {}
        self.chkWlEnabled.checked = bool(wl.get("enabled"))
        self.wlMinEdit.text = "" if wl.get("min") is None else str(wl["min"])
        self.wlMaxEdit.text = "" if wl.get("max") is None else str(wl["max"])

        rot = cfg.get("slice_rotation", {}) or {}
        self.chkSliceRotationEnabled.checked = bool(rot.get("enabled"))
        self.sliceRotRedEdit.text = "" if rot.get("red") is None else str(rot["red"])
        self.sliceRotYellowEdit.text = "" if rot.get("yellow") is None else str(rot["yellow"])
        self.sliceRotGreenEdit.text = "" if rot.get("green") is None else str(rot["green"])

        ws = cfg.get("workspace", {}) or {}
        self.crosshairModeCombo.currentText = ws.get("crosshair_mode") or "(unset)"
        self.crosshairBehaviorCombo.currentText = ws.get("crosshair_behavior") or "(unset)"
        self.crosshairThicknessCombo.currentText = ws.get("crosshair_thickness") or "(unset)"
        self.rulerTypeCombo.currentText = ws.get("ruler_type") or "(unset)"
        self.orientationMarkerTypeCombo.currentText = ws.get("orientation_marker_3d_type") or "(unset)"
        self.orientationMarkerSizeCombo.currentText = ws.get("orientation_marker_3d_size") or "(unset)"
        self.orientationMarker2dTypeCombo.currentText = ws.get("orientation_marker_2d_type") or "(unset)"
        self.orientationMarker2dSizeCombo.currentText = ws.get("orientation_marker_2d_size") or "(unset)"
        self.radioNeurological.setChecked(ws.get("view_convention") == "neurological")
        self.chkSpecimenAnnotation.checked = bool(ws.get("specimen_annotation"))
        self.radioRadiological.setChecked(ws.get("view_convention") != "neurological")


    def _collectWorkspace(self, cfg):
        """Write the Workspace tab's part of the config into the dict `cfg` (key order = file order)."""
        if self.chkWlEnabled.checked:
            wl = {"enabled": True}
            mn, mx = to_float(self.wlMinEdit.text), to_float(self.wlMaxEdit.text)
            if mn is not None:
                wl["min"] = mn
            if mx is not None:
                wl["max"] = mx
            cfg["window_level"] = wl

        if self.chkSliceRotationEnabled.checked:
            rot = {"enabled": True}
            red, yellow, green = to_float(self.sliceRotRedEdit.text), to_float(self.sliceRotYellowEdit.text), to_float(self.sliceRotGreenEdit.text)
            if red is not None:
                rot["red"] = red
            if yellow is not None:
                rot["yellow"] = yellow
            if green is not None:
                rot["green"] = green
            cfg["slice_rotation"] = rot

        ws = {}
        for combo, key in (
            (self.crosshairModeCombo, "crosshair_mode"),
            (self.crosshairBehaviorCombo, "crosshair_behavior"),
            (self.crosshairThicknessCombo, "crosshair_thickness"),
            (self.rulerTypeCombo, "ruler_type"),
            (self.orientationMarkerTypeCombo, "orientation_marker_3d_type"),
            (self.orientationMarkerSizeCombo, "orientation_marker_3d_size"),
            (self.orientationMarker2dTypeCombo, "orientation_marker_2d_type"),
            (self.orientationMarker2dSizeCombo, "orientation_marker_2d_size"),
        ):
            value = (combo.currentText or "").strip()
            if value and value != "(unset)":
                ws[key] = value

        if self.radioNeurological.isChecked():
            ws["view_convention"] = "neurological"

        if self.chkSpecimenAnnotation.checked:
            ws["specimen_annotation"] = True

        if ws:
            cfg["workspace"] = ws


    def _clearWorkspace(self):
        """Reset the Workspace tab to its blank/default state."""
        for edit in (self.wlMinEdit, self.wlMaxEdit, self.sliceRotRedEdit, self.sliceRotYellowEdit, self.sliceRotGreenEdit):
            edit.text = ""
        for chk in (self.chkWlEnabled, self.chkSliceRotationEnabled, self.chkSpecimenAnnotation):
            chk.checked = False
        self.radioRadiological.setChecked(True)
        for combo in (self.crosshairModeCombo, self.crosshairBehaviorCombo, self.crosshairThicknessCombo,
                      self.rulerTypeCombo, self.orientationMarkerTypeCombo, self.orientationMarkerSizeCombo,
                      self.orientationMarker2dTypeCombo, self.orientationMarker2dSizeCombo):
            combo.currentText = "(unset)"
