"""
segment_editor_tab.py
=====================
Segment editor tab: overwrite mode, brush, active effect, raw attributes.
"""

import json

import qt

from Resources.definitions import BRUSH_SHAPE_CHOICES, OVERWRITE_CHOICES, SEGMENT_EDITOR_EFFECT_CHOICES
from Resources.gui.config_editor.helpers import combo_value, set_combo_value, to_float


class SegmentEditorTabMixin:
    """Segment editor tab: overwrite mode, brush, active effect, raw attributes."""


    def _buildSegmentEditorTab(self):
        """Overwrite mode/brush shape+size+unit/active effect/raw attributes escape hatch."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)

        overwriteGroup = qt.QGroupBox("Overwrite mode")
        overwriteForm = qt.QFormLayout(overwriteGroup)
        self.overwriteModeCombo = qt.QComboBox()
        self.overwriteModeCombo.addItems(OVERWRITE_CHOICES)
        self.overwriteModeCombo.setToolTip("'none' = the Segment Editor's 'Allow overlap' checkbox is ON. 'all_segments'/'visible_segments' restrict painting to not overwrite other segments.")
        overwriteForm.addRow("Mode:", self.overwriteModeCombo)
        layout.addWidget(overwriteGroup)

        brushGroup = qt.QGroupBox("Brush")
        brushForm = qt.QFormLayout(brushGroup)
        self.brushShapeCombo = qt.QComboBox()
        self.brushShapeCombo.addItems(BRUSH_SHAPE_CHOICES)
        self.brushShapeCombo.setToolTip("sphere = 3D brush (also paints in the 3D view). circle = Slicer's normal 2D slice brush.")
        brushForm.addRow("Shape:", self.brushShapeCombo)
        self.brushDiameterEdit = qt.QLineEdit()
        self.brushDiameterEdit.setToolTip("Fixed brush size - in mm if 'Use absolute size' below is checked, in % of the slice view otherwise.")
        brushForm.addRow("Diameter (mm or %):", self.brushDiameterEdit)
        self.chkBrushAbsolute = qt.QCheckBox("Use absolute size (mm)")
        self.chkBrushAbsolute.setToolTip("Checked: fixed size in millimeters, regardless of zoom. Unchecked: size as a percentage of the slice view instead.")
        self.chkBrushAbsolute.checked = True
        brushForm.addRow(self.chkBrushAbsolute)
        layout.addWidget(brushGroup)

        effectGroup = qt.QGroupBox("Active effect")
        effectForm = qt.QFormLayout(effectGroup)
        self.activeEffectEdit = qt.QComboBox()
        self.activeEffectEdit.setEditable(True)
        self.activeEffectEdit.addItems(SEGMENT_EDITOR_EFFECT_CHOICES)
        self.activeEffectEdit.setToolTip("Pre-select this effect whenever a live/default Segment Editor node picks up these settings (best-effort, not forced).")
        effectForm.addRow("On load:", self.activeEffectEdit)
        layout.addWidget(effectGroup)

        attrGroup = qt.QGroupBox("Raw attributes (JSON)")
        attrLayout = qt.QVBoxLayout(attrGroup)
        self.seAttributesEdit = qt.QPlainTextEdit()
        self.seAttributesEdit.setPlaceholderText('{"BrushSphere": "1"}')
        self.seAttributesEdit.setToolTip(
            "Escape hatch: raw attribute-name -> value pairs, applied last (overrides overwrite_mode/"
            "brush above). Brush params (BrushSphere, BrushAbsoluteDiameter, BrushRelativeDiameter, "
            "BrushDiameterIsRelative) are COMMON parameters with NO effect-name prefix - just the bare "
            "name, e.g. \"BrushSphere\": \"1\" (NOT \"Paint,BrushSphere\"). Only effect-SPECIFIC settings "
            "use an \"EffectName.ParamName\" form, e.g. \"Paint.ColorSmudge\".")
        attrLayout.addWidget(self.seAttributesEdit)
        layout.addWidget(attrGroup, 1)   # the raw attributes box takes all the remaining height
        return w

    def _populateSegmentEditor(self, cfg):
        """Fill the Segment editor tab from the raw config dict `cfg`."""
        se = cfg.get("segment_editor", {}) or {}
        self.overwriteModeCombo.currentText = se.get("overwrite_mode", "none") or "none"
        brush = se.get("brush") or {}
        self.brushShapeCombo.currentText = brush.get("shape") or "(unset)"
        self.brushDiameterEdit.text = "" if brush.get("diameter_mm") is None else str(brush["diameter_mm"])
        self.chkBrushAbsolute.checked = not bool(brush.get("relative"))
        set_combo_value(self.activeEffectEdit, se.get("active_effect", "") or "")
        if se.get("attributes"):
            self.seAttributesEdit.plainText = json.dumps(se["attributes"], indent=2)


    def _collectSegmentEditor(self, cfg):
        """Write the Segment editor tab's part of the config into the dict `cfg` (key order = file order)."""
        overwrite = self.overwriteModeCombo.currentText
        brush_shape = self.brushShapeCombo.currentText
        diameter = to_float(self.brushDiameterEdit.text)
        active_effect = combo_value(self.activeEffectEdit)
        se_attrs = self._parseJsonField(self.seAttributesEdit, "segment_editor attributes") or {}
        if overwrite != "none" or brush_shape != "(unset)" or diameter is not None or active_effect or se_attrs:
            se = {"overwrite_mode": overwrite}
            if brush_shape != "(unset)" or diameter is not None:
                brush = {}
                if brush_shape != "(unset)":
                    brush["shape"] = brush_shape
                if diameter is not None:
                    brush["diameter_mm"] = diameter
                brush["relative"] = not self.chkBrushAbsolute.checked
                se["brush"] = brush
            if active_effect:
                se["active_effect"] = active_effect
            if se_attrs:
                se["attributes"] = se_attrs
            cfg["segment_editor"] = se


    def _clearSegmentEditor(self):
        """Reset the Segment editor tab to its blank/default state."""
        self.brushDiameterEdit.text = ""
        set_combo_value(self.activeEffectEdit, "")
        self.chkBrushAbsolute.checked = True
        self.overwriteModeCombo.currentText = "none"
        self.brushShapeCombo.currentText = "(unset)"
        self.seAttributesEdit.plainText = ""
