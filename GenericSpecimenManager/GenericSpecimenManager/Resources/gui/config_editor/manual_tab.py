"""
manual_tab.py
=============
Manual edit config tab: the raw JSON preview and round trip.
"""

import json

import qt


class ManualTabMixin:
    """Manual edit config tab: the raw JSON preview and round trip."""


    def _buildManualTab(self):
        """The raw-JSON preview/edit surface: Refresh pulls the current form state as JSON; Apply parses hand-edited JSON back into every other tab. Save always saves from the tabs, so hand edits here need Apply first to actually take effect."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)
        hint = qt.QLabel(
            "This is the actual config.json that 'Save config' would write, built from every tab above. "
            "Click Refresh any time to see the current state. You can also edit the JSON directly here and "
            "click 'Apply to form' to push your edits back into all the other tabs - Save always saves "
            "from the tabs, so Apply first if you hand-edited something here.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.manualEditor = qt.QPlainTextEdit()
        layout.addWidget(self.manualEditor)

        btnRow = qt.QHBoxLayout()
        refreshBtn = qt.QPushButton("Refresh from form")
        refreshBtn.setToolTip("Regenerate the JSON below from the current state of every tab.")
        refreshBtn.connect('clicked(bool)', lambda checked=False: self._onRefreshManualEdit())
        applyBtn = qt.QPushButton("Apply to form")
        applyBtn.setToolTip("Parse the JSON below and load it into all the other tabs (like Load from file, but from this text).")
        applyBtn.connect('clicked(bool)', lambda checked=False: self._onApplyManualEdit())
        btnRow.addWidget(refreshBtn)
        btnRow.addWidget(applyBtn)
        btnRow.addStretch(1)
        layout.addLayout(btnRow)

        return w

    def _onRefreshManualEdit(self):
        """Regenerate the JSON preview from the current form state (via _buildConfig())."""
        try:
            cfg = self._buildConfig()
        except Exception:
            return  # _buildConfig already showed a JSON error from a field, if any
        self.manualEditor.plainText = json.dumps(cfg, indent=2, ensure_ascii=False)

    def _onApplyManualEdit(self):
        """Parse the hand-edited JSON in the box and push it back into every other tab via _populateForm()."""
        text = self.manualEditor.plainText.strip()
        if not text:
            qt.QMessageBox.information(self, "Config Editor", "Nothing to apply - the box is empty.")
            return
        try:
            cfg = json.loads(text)
        except Exception as e:
            qt.QMessageBox.critical(self, "Config Editor", f"Invalid JSON: {e}")
            return
        self._populateForm(cfg)
        self._markDirty()
        qt.QMessageBox.information(self, "Config Editor", "Applied to the other tabs.")
