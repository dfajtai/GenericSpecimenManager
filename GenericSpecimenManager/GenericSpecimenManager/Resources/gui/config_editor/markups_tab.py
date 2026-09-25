"""
markups_tab.py
==============
Markups tab: markups file/template, color, size, shape.
"""

import qt

from Resources.definitions import MARKUPS_GLYPH_CHOICES, UNSET
from Resources.gui.config_editor.helpers import (
    DEFAULT_SEGMENT_COLOR,
    combo_value,
    set_combo_value,
    to_float,
)


class MarkupsTabMixin:
    """Markups tab: markups file/template, color, size, shape."""


    def _buildMarkupsTab(self):
        """Enabled/csv column/path pattern/template file/writable/color."""
        w = qt.QWidget()
        form = qt.QFormLayout(w)
        self.chkMarkupsEnabled = qt.QCheckBox("Enabled")
        form.addRow(self.chkMarkupsEnabled)
        self.markupsCsvColumnEdit = qt.QLineEdit()
        self.markupsCsvColumnEdit.setToolTip("preseg.csv column holding an existing markups file path for this specimen (optional - falls back to Path pattern).")
        form.addRow("CSV column:", self.markupsCsvColumnEdit)
        self.markupsPathPatternEdit = qt.QLineEdit()
        self.markupsPathPatternEdit.setPlaceholderText("default: {label}-markups.mrk.json")
        self.markupsPathPatternEdit.setToolTip("Fallback naming when CSV column is empty/unset. {label} = the specimen's key joined with '-', e.g. 'D001'.")
        form.addRow("Path pattern:", self.markupsPathPatternEdit)
        self.markupsTemplateEdit, markupsTemplateRow = self._fileRow(filter_="Markups (*.mrk.json *.json);;All files (*)")
        self.markupsTemplateEdit.setToolTip("If a specimen has no markups file yet, load THIS file as the starting point (renamed to that specimen) instead of an empty fiducial list.")
        form.addRow("Template file (optional):", markupsTemplateRow)
        self.chkMarkupsWritable = qt.QCheckBox("Writable")
        self.chkMarkupsWritable.checked = True
        form.addRow(self.chkMarkupsWritable)
        self.markupsColorEdit = qt.QLineEdit()
        self.markupsColorEdit.setReadOnly(True)
        self.markupsColorEdit.setPlaceholderText("(unset - Slicer's default)")
        self.markupsColorEdit.setToolTip("Markup point color as r,g,b (0-1). Use 'Set color...' to pick.")
        self.markupsColorEdit.textChanged.connect(lambda _text: self._applyMarkupsColorDisplay())
        colorBtn = qt.QPushButton("Set color...")
        colorBtn.connect('clicked(bool)', lambda checked=False: self._onPickMarkupsColor())
        clearColorBtn = qt.QPushButton("Clear")
        clearColorBtn.setToolTip("Unset the color - Slicer's default is used.")
        clearColorBtn.connect('clicked(bool)', lambda checked=False: self._onClearMarkupsColor())
        colorRow = qt.QHBoxLayout()
        colorRow.addWidget(self.markupsColorEdit)
        colorRow.addWidget(colorBtn)
        colorRow.addWidget(clearColorBtn)
        form.addRow("Color:", colorRow)
        self.markupsSizeEdit = qt.QLineEdit()
        self.markupsSizeEdit.setPlaceholderText(UNSET)
        self.markupsSizeEdit.setToolTip("Markup point size - the 'Scale' of Slicer's Markups display settings (e.g. 3 = Slicer's usual, larger = bigger points). Empty leaves Slicer's default.")
        self.chkMarkupsSizeMm = qt.QCheckBox("in mm")
        self.chkMarkupsSizeMm.setToolTip("Checked: the size is a real-world size in millimetres. Combined with the Sphere3D shape the point is a ball that shows across several neighbouring slices. Unchecked: Slicer's relative 'Scale'.")
        sizeRow = qt.QHBoxLayout()
        sizeRow.addWidget(self.markupsSizeEdit, 1)
        sizeRow.addWidget(self.chkMarkupsSizeMm)
        form.addRow("Size:", sizeRow)
        self.markupsGlyphCombo = qt.QComboBox()
        self.markupsGlyphCombo.setEditable(True)
        self.markupsGlyphCombo.addItems(MARKUPS_GLYPH_CHOICES)
        self.markupsGlyphCombo.setToolTip("Point shape. Sphere3D is a real 3D ball - cut by each slice plane it is visible on several neighbouring slices (best with the size in mm). The *2D shapes are flat markers seen only on the slice they sit on. (unset) leaves Slicer's default.")
        form.addRow("Shape:", self.markupsGlyphCombo)
        return w

    def _markupsColorRgb(self):
        """The markups color field as [r, g, b] floats (0-1), or None if unset/unparseable."""
        try:
            rgb = [float(c) for c in self.markupsColorEdit.text.split(",")]
        except ValueError:
            return None
        return rgb if len(rgb) == 3 else None

    def _applyMarkupsColorDisplay(self):
        """Paint the markups color field's background from its r,g,b text (cleared when unset)."""
        rgb = self._markupsColorRgb()
        if not rgb:
            self.markupsColorEdit.setStyleSheet("")
            return
        r, g, b = (int(round(c * 255)) for c in rgb)
        text_color = "black" if (0.299 * r + 0.587 * g + 0.114 * b) > 128 else "white"
        self.markupsColorEdit.setStyleSheet(f"background-color: rgb({r},{g},{b}); color: {text_color};")

    def _onPickMarkupsColor(self):
        """Open a color picker, starting from the current markups color (or the default segment color), and apply the chosen one."""
        rgb = self._markupsColorRgb() or list(DEFAULT_SEGMENT_COLOR)
        current = qt.QColor(*(int(round(c * 255)) for c in rgb))
        color = qt.QColorDialog.getColor(current, self, "Pick markups color")
        if color.isValid():
            self.markupsColorEdit.text = f"{color.red() / 255.0:.2f},{color.green() / 255.0:.2f},{color.blue() / 255.0:.2f}"
            self._markDirty()

    def _onClearMarkupsColor(self):
        """Unset the markups color."""
        self.markupsColorEdit.text = ""
        self._markDirty()

    def _populateMarkups(self, cfg):
        """Fill the Markups tab from the raw config dict `cfg`."""
        markups = cfg.get("markups", {}) or {}
        self.chkMarkupsEnabled.checked = bool(markups.get("enabled"))
        self.markupsCsvColumnEdit.text = markups.get("csv_column", "") or ""
        self.markupsPathPatternEdit.text = markups.get("path_pattern", "") or ""
        self.markupsTemplateEdit.text = markups.get("template_path", "") or ""
        self.chkMarkupsWritable.checked = markups.get("writable", True)
        if markups.get("color"):
            self.markupsColorEdit.text = ",".join(str(c) for c in markups["color"])
        if markups.get("size") is not None:
            self.markupsSizeEdit.text = str(markups["size"])
        self.chkMarkupsSizeMm.checked = bool(markups.get("size_absolute"))
        set_combo_value(self.markupsGlyphCombo, markups.get("glyph_type") or "")


    def _collectMarkups(self, cfg):
        """Write the Markups tab's part of the config into the dict `cfg` (key order = file order)."""
        if self.chkMarkupsEnabled.checked:
            markups = {"enabled": True, "writable": self.chkMarkupsWritable.checked}
            if self.markupsCsvColumnEdit.text.strip():
                markups["csv_column"] = self.markupsCsvColumnEdit.text.strip()
            if self.markupsPathPatternEdit.text.strip():
                markups["path_pattern"] = self.markupsPathPatternEdit.text.strip()
            if self.markupsTemplateEdit.text.strip():
                markups["template_path"] = self.markupsTemplateEdit.text.strip()
            if self.markupsColorEdit.text.strip():
                markups["color"] = [to_float(c) for c in self.markupsColorEdit.text.split(",")]
            size = to_float(self.markupsSizeEdit.text)
            if size is not None:
                markups["size"] = size
                if self.chkMarkupsSizeMm.checked:
                    markups["size_absolute"] = True
            if combo_value(self.markupsGlyphCombo):
                markups["glyph_type"] = combo_value(self.markupsGlyphCombo)
            cfg["markups"] = markups


    def _clearMarkups(self):
        """Reset the Markups tab to its blank/default state."""
        for edit in (self.markupsCsvColumnEdit, self.markupsPathPatternEdit, self.markupsTemplateEdit,
                     self.markupsColorEdit, self.markupsSizeEdit):
            edit.text = ""
        self.chkMarkupsSizeMm.checked = False
        set_combo_value(self.markupsGlyphCombo, "")
        self.chkMarkupsEnabled.checked = False
        self.chkMarkupsWritable.checked = True
