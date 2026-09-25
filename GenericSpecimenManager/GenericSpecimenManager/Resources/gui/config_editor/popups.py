"""
popups.py
=========
The Config Editor's small popups: the image row's advanced fields and the copyable text popup.
"""

import qt

from Resources.gui.config_editor.helpers import to_float


class ImageAdvancedPopup(qt.QDialog):
    """Structured popup for an image row's advanced fields: path_pattern,
    window_level, threshold, interpolate. Replaces free-form JSON with actual fields."""

    WL_MODES = ["(unset)", "Auto", "Min / Max", "Window / Level"]

    def __init__(self, parent, data):
        """Build the path_pattern/window_level/threshold/interpolate form, pre-filled from `data` (the row's current advanced dict)."""
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Advanced image fields")
        self.setMinimumWidth(540)   # wide enough for the path pattern; the height follows the content
        data = dict(data or {})
        layout = qt.QVBoxLayout(self)

        intro = qt.QLabel("These settings apply to <b>this image row only</b> - on top of the defaults and the row's preset.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # ---- File location ----
        fileGroup = qt.QGroupBox("File location")
        fileLayout = qt.QVBoxLayout(fileGroup)
        fileForm = qt.QFormLayout()
        self.pathPatternEdit = qt.QLineEdit(data.get("path_pattern") or "")
        self.pathPatternEdit.setPlaceholderText("e.g. {ID}_{measurement}_{name}.nii.gz")
        fileForm.addRow("Path pattern:", self.pathPatternEdit)
        fileLayout.addLayout(fileForm)
        fileHint = qt.QLabel(
            "Used when this row's CSV column is empty for a specimen. <code>{column}</code> = any CSV column value, "
            "<code>{name}</code> = this image's name; relative to Study dir. Leave empty to use the Default path pattern.")
        fileHint.setWordWrap(True)
        fileHint.setStyleSheet("color: gray;")
        fileLayout.addWidget(fileHint)
        layout.addWidget(fileGroup)

        # ---- Window / level ----
        wl = data.get("window_level") or {}
        wlGroup = qt.QGroupBox("Window / level")
        wlLayout = qt.QVBoxLayout(wlGroup)
        modeForm = qt.QFormLayout()
        self.wlModeCombo = qt.QComboBox()
        self.wlModeCombo.addItems(self.WL_MODES)
        if wl.get("auto"):
            self.wlModeCombo.currentText = "Auto"
        elif "window" in wl or "level" in wl:
            self.wlModeCombo.currentText = "Window / Level"
        elif "min" in wl or "max" in wl:
            self.wlModeCombo.currentText = "Min / Max"
        self.wlModeCombo.setToolTip(
            "Auto: let Slicer auto-window. Min/Max: display range (e.g. CT -150..700).\n"
            "Window/Level: width+center form (e.g. a ratio map with SetWindowLevel(1,2)) -\n"
            "NOT the same numbers as Min/Max, see the Help cheat sheet.")
        modeForm.addRow("Mode:", self.wlModeCombo)
        wlLayout.addLayout(modeForm)
        valueRow = qt.QHBoxLayout()
        self.wlALabel = qt.QLabel("Min:")
        self.wlAEdit = qt.QLineEdit("" if wl.get("min", wl.get("window")) is None else str(wl.get("min", wl.get("window"))))
        self.wlBLabel = qt.QLabel("Max:")
        self.wlBEdit = qt.QLineEdit("" if wl.get("max", wl.get("level")) is None else str(wl.get("max", wl.get("level"))))
        for widget in (self.wlALabel, self.wlAEdit, self.wlBLabel, self.wlBEdit):
            valueRow.addWidget(widget, 1 if isinstance(widget, qt.QLineEdit) else 0)
        wlLayout.addLayout(valueRow)
        self.wlModeCombo.connect('currentIndexChanged(int)', lambda _i: self._updateWlFields())
        layout.addWidget(wlGroup)
        self._updateWlFields()

        # ---- Threshold ----
        th = data.get("threshold") or {}
        self.thresholdGroup = qt.QGroupBox("Threshold")
        self.thresholdGroup.setCheckable(True)
        self.thresholdGroup.checked = bool(th)
        thLayout = qt.QVBoxLayout(self.thresholdGroup)
        thRow = qt.QHBoxLayout()
        self.thMinEdit = qt.QLineEdit("" if th.get("min") is None else str(th["min"]))
        self.thMaxEdit = qt.QLineEdit("" if th.get("max") is None else str(th["max"]))
        thRow.addWidget(qt.QLabel("Min:"))
        thRow.addWidget(self.thMinEdit, 1)
        thRow.addWidget(qt.QLabel("Max:"))
        thRow.addWidget(self.thMaxEdit, 1)
        thLayout.addLayout(thRow)
        self.chkThresholdApply = qt.QCheckBox("Apply (hide values outside the range)")
        self.chkThresholdApply.checked = th.get("apply", True)
        thLayout.addWidget(self.chkThresholdApply)
        layout.addWidget(self.thresholdGroup)

        # ---- Display ----
        displayGroup = qt.QGroupBox("Display")
        displayForm = qt.QFormLayout(displayGroup)
        self.interpolateCombo = qt.QComboBox()
        self.interpolateCombo.addItems(["(unset)", "on", "off"])
        if "interpolate" in data:
            self.interpolateCombo.currentText = "on" if data["interpolate"] else "off"
        displayForm.addRow("Interpolate:", self.interpolateCombo)
        layout.addWidget(displayGroup)

        buttons = qt.QDialogButtonBox(qt.QDialogButtonBox.Ok | qt.QDialogButtonBox.Cancel)
        buttons.connect('accepted()', self.accept)
        buttons.connect('rejected()', self.reject)
        layout.addWidget(buttons)

    def _updateWlFields(self):
        """Relabel the two window/level value fields for the chosen mode (Min/Max vs Window/Level) and grey them out when the mode takes no numbers."""
        mode = self.wlModeCombo.currentText
        window_level = mode == "Window / Level"
        self.wlALabel.text = "Window:" if window_level else "Min:"
        self.wlBLabel.text = "Level:" if window_level else "Max:"
        takes_values = mode in ("Min / Max", "Window / Level")
        for widget in (self.wlALabel, self.wlAEdit, self.wlBLabel, self.wlBEdit):
            widget.enabled = takes_values

    def resultDict(self):
        """Build the advanced dict (path_pattern/window_level/threshold/interpolate) from the form's current values, omitting anything the user left unset."""
        out = {}
        if self.pathPatternEdit.text.strip():
            out["path_pattern"] = self.pathPatternEdit.text.strip()
        mode = self.wlModeCombo.currentText
        a, b = to_float(self.wlAEdit.text), to_float(self.wlBEdit.text)
        if mode == "Auto":
            out["window_level"] = {"auto": True}
        elif mode == "Min / Max" and (a is not None or b is not None):
            out["window_level"] = {k: v for k, v in (("min", a), ("max", b)) if v is not None}
        elif mode == "Window / Level" and (a is not None or b is not None):
            out["window_level"] = {k: v for k, v in (("window", a), ("level", b)) if v is not None}

        if self.thresholdGroup.checked:
            th = {"apply": self.chkThresholdApply.checked}
            mn, mx = to_float(self.thMinEdit.text), to_float(self.thMaxEdit.text)
            if mn is not None:
                th["min"] = mn
            if mx is not None:
                th["max"] = mx
            out["threshold"] = th

        if self.interpolateCombo.currentText != "(unset)":
            out["interpolate"] = self.interpolateCombo.currentText == "on"

        return out


class TextPopup(qt.QDialog):
    """Read-only, scrollable, copyable text popup (help text, examples, CSV columns)."""

    def __init__(self, parent, title, text):
        """Read-only, scrollable, copyable text popup - used for the CSV-columns viewer."""
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self.resize(560, 480)
        layout = qt.QVBoxLayout(self)
        edit = qt.QPlainTextEdit()
        edit.plainText = text
        edit.setReadOnly(True)
        layout.addWidget(edit)
        closeBtn = qt.QPushButton("Close")
        closeBtn.connect('clicked(bool)', lambda checked=False: self.close())
        layout.addWidget(closeBtn)
