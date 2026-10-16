"""
segment_editor_tab.py
=====================
Segment editor tab: overwrite mode, brush, active effect, raw attributes.
"""

import json

import qt

from Resources.definitions import BRUSH_SHAPE_LABELS, OVERWRITE_LABELS, SEGMENT_EDITOR_EFFECT_CHOICES
from Resources.utils.segment_editor import editable_area_choices
from Resources.gui.config_editor.helpers import (
    combo_value, fill_labeled_combo, labeled_combo_value, set_combo_value, set_labeled_combo, to_float)


class SegmentEditorTabMixin:
    """Segment editor tab: overwrite mode, brush, active effect, raw attributes."""


    def _buildSegmentEditorTab(self):
        """Masking (editable area, modify other segments)/brush shape+size+unit/active effect/raw attributes escape hatch."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)

        maskingGroup = qt.QGroupBox("Masking")
        maskingForm = qt.QFormLayout(maskingGroup)
        self.editableAreaCombo = qt.QComboBox()
        self._editableAreaLabels = editable_area_choices()   # read from Slicer's own mode names
        fill_labeled_combo(self.editableAreaCombo, self._editableAreaLabels)
        self.editableAreaCombo.setToolTip(
            "Where painting is allowed (editable_area). (unset) = leave Slicer's own setting (Everywhere). "
            "Inside/Outside all segments = only on/off any segment; ...visible segments = counting only "
            "the segments that are currently shown.")
        maskingForm.addRow("Editable area:", self.editableAreaCombo)
        self.overwriteModeCombo = qt.QComboBox()
        fill_labeled_combo(self.overwriteModeCombo, OVERWRITE_LABELS)
        self.overwriteModeCombo.setToolTip(
            "What painting may do to the other segments (overwrite_mode). (unset) = leave Slicer's own setting alone. "
            "Allow overlap = the Segment Editor's 'Allow overlap' is ON. Overwrite all / visible segments = painting "
            "takes the voxels from the other (all / only the visible) segments.")
        maskingForm.addRow("Modify other segments:", self.overwriteModeCombo)
        layout.addWidget(maskingGroup)

        brushGroup = qt.QGroupBox("Brush")
        brushForm = qt.QFormLayout(brushGroup)
        self.brushShapeCombo = qt.QComboBox()
        fill_labeled_combo(self.brushShapeCombo, BRUSH_SHAPE_LABELS)
        self.brushShapeCombo.setToolTip("Sphere = 3D brush (also paints in the 3D view). Circle = Slicer's normal 2D slice brush.")
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
        set_labeled_combo(self.overwriteModeCombo, OVERWRITE_LABELS, se.get("overwrite_mode"))
        set_labeled_combo(self.editableAreaCombo, self._editableAreaLabels, se.get("editable_area"))
        brush = se.get("brush") or {}
        set_labeled_combo(self.brushShapeCombo, BRUSH_SHAPE_LABELS, brush.get("shape"))
        self.brushDiameterEdit.text = "" if brush.get("diameter_mm") is None else str(brush["diameter_mm"])
        self.chkBrushAbsolute.checked = not bool(brush.get("relative"))
        set_combo_value(self.activeEffectEdit, se.get("active_effect", "") or "")
        if se.get("attributes"):
            self.seAttributesEdit.plainText = json.dumps(se["attributes"], indent=2)


    def _collectSegmentEditor(self, cfg):
        """Write the Segment editor tab's part of the config into the dict `cfg` (key order = file order)."""
        overwrite = labeled_combo_value(self.overwriteModeCombo, OVERWRITE_LABELS)   # '' = (unset); 'none' is a real value and is written
        editable_area = labeled_combo_value(self.editableAreaCombo, self._editableAreaLabels)
        brush_shape = labeled_combo_value(self.brushShapeCombo, BRUSH_SHAPE_LABELS)
        diameter = to_float(self.brushDiameterEdit.text)
        active_effect = combo_value(self.activeEffectEdit)
        se_attrs = self._parseJsonField(self.seAttributesEdit, "segment_editor attributes") or {}
        if overwrite or editable_area or brush_shape or diameter is not None or active_effect or se_attrs:
            se = {}
            if overwrite:
                se["overwrite_mode"] = overwrite
            if editable_area:
                se["editable_area"] = editable_area
            if brush_shape or diameter is not None:
                brush = {}
                if brush_shape:
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
        set_labeled_combo(self.overwriteModeCombo, OVERWRITE_LABELS, "")
        set_labeled_combo(self.editableAreaCombo, self._editableAreaLabels, "")
        set_labeled_combo(self.brushShapeCombo, BRUSH_SHAPE_LABELS, "")
        self.seAttributesEdit.plainText = ""
