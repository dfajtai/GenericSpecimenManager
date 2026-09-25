"""
defaults_tab.py
===============
Defaults / Presets tab: defaults.image / defaults.segment / presets, and the example-presets catalogue.
"""

import json
import os

import qt

from Resources.core.logging_setup import logger
from Resources.paths import HTML_DIR, PRESETS_DIR


class DefaultsTabMixin:
    """Defaults / Presets tab: defaults.image / defaults.segment / presets, and the example-presets catalogue."""


    def _buildAdvancedTab(self):
        """The defaults.image / defaults.segment / presets JSON fields, with the merge-order explanation up top and the starter-example / example-presets-catalogue helper buttons."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)

        intro = qt.QLabel(
            "Fills in visual properties (window/level, color, threshold, ...) without repeating "
            "them on every row. Rule: defaults.image -> preset (if the row names one) -> the row's "
            "own fields - last one wins, per field. See the live \"Effective settings\" box on the "
            "Images tab for exactly what a given row ends up with.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        defaultsGroup = qt.QGroupBox("1) Defaults - apply to every row")
        defaultsForm = qt.QFormLayout(defaultsGroup)
        layout.addWidget(defaultsGroup)

        self.defaultsImageEdit = qt.QPlainTextEdit()
        self.defaultsImageEdit.setPlaceholderText('{"required": true, "window_level": {"min": -150, "max": 700}}')
        self.defaultsImageEdit.setMaximumHeight(80)
        self.defaultsImageEdit.setToolTip(
            "Fields applied to EVERY image (Images tab), before its own 'preset' and inline "
            "values override them. Any ImageConfig field works here: type, role, required, "
            "opacity, window_level, color_table, threshold, interpolate, path_pattern.")
        defaultsForm.addRow("defaults.image (JSON):", self.defaultsImageEdit)
        self.defaultsImageEdit.textChanged.connect(self._refreshPreviewIfSelected)
        defaultsImgExampleBtn = qt.QPushButton("Insert example...")
        defaultsImgExampleBtn.setToolTip("Fills defaults.image above with a starter example (only if it's currently empty).")
        defaultsImgExampleBtn.connect('clicked(bool)', lambda checked=False: self._onInsertDefaultsImageExample())
        defaultsForm.addRow(defaultsImgExampleBtn)

        self.defaultsSegmentEdit = qt.QPlainTextEdit()
        self.defaultsSegmentEdit.setPlaceholderText('{"color": [1, 1, 1]}')
        self.defaultsSegmentEdit.setMaximumHeight(70)
        self.defaultsSegmentEdit.setToolTip("Same idea as defaults.image, but for every segment row (Segmentation tab): e.g. {\"color\": [1,1,1]}.")
        defaultsForm.addRow("defaults.segment (JSON):", self.defaultsSegmentEdit)

        presetsGroup = qt.QGroupBox("2) Presets - named looks, opt-in per image row")
        presetsForm = qt.QFormLayout(presetsGroup)
        layout.addWidget(presetsGroup)

        self.presetsEdit = qt.QPlainTextEdit()
        self.presetsEdit.plainText = json.dumps(
            {name: self._loadExamplePresets()[name]["preset"]
             for name in ("ct_soft_tissue", "ct_bone") if name in self._loadExamplePresets()}, indent=2)
        self.presetsEdit.setToolTip(
            "Named, reusable bags of image visual properties. Reference one by name in an "
            "image row's 'Preset' column (Images tab) - merge order is defaults.image -> "
            "this preset -> the image row's own inline values.")
        self.presetsEdit.setMinimumHeight(120)
        presetsForm.addRow("presets (JSON):", self.presetsEdit)
        self.presetsEdit.textChanged.connect(self._refreshPreviewIfSelected)
        self.presetsEdit.textChanged.connect(self._refreshAllPresetCombos)
        examplesBtn = qt.QPushButton("Show example presets (copyable)...")
        examplesBtn.setToolTip("Opens a read-only, copyable list of ready-made presets you can paste in above and tweak.")
        examplesBtn.connect('clicked(bool)', lambda checked=False: self._onShowExamplePresets())
        presetsForm.addRow(examplesBtn)

        return w

    def _getPresetNames(self):
        """Current preset names, parsed live from the Presets JSON field - used to populate every image row's Preset dropdown."""
        try:
            return sorted(json.loads(self.presetsEdit.plainText or "{}").keys())
        except Exception:
            return []

    def _onInsertDefaultsImageExample(self):
        """Fill defaults.image with a small starter example, asking for confirmation first if the field isn't already empty."""
        if self.defaultsImageEdit.plainText.strip():
            ret = qt.QMessageBox.question(
                self, "Config Editor", "defaults.image is not empty - overwrite it with the example?",
                qt.QMessageBox.Yes | qt.QMessageBox.No)
            if ret != qt.QMessageBox.Yes:
                return
        self.defaultsImageEdit.plainText = json.dumps(
            {"required": False, "type": "volume", "window_level": {"min": -150, "max": 700}}, indent=2)
        self._markDirty()

    def _presetResourceDir(self):
        """Absolute path to Resources/Presets, where the Config Editor's bundled preset catalogue lives - same idea as _htmlResourceDir(), kept as its own method so both resource kinds are equally easy to find/extend."""
        return PRESETS_DIR

    def _loadExamplePresets(self):
        """Read Resources/Presets/example_presets.json (name -> {description, preset}), cached after the first read. Returns {} on any error (missing/invalid file) instead of crashing - callers just see an empty catalogue."""
        cache = getattr(self, "_example_presets_cache", None)
        if cache is not None:
            return cache
        path = os.path.join(self._presetResourceDir(), "example_presets.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"[ConfigEditor] could not load example_presets.json: {e}")
            data = {}
        data.pop("_comment", None)
        self._example_presets_cache = data
        return data

    def _htmlResourceDir(self):
        """Absolute path to Resources/Html, where the Config Editor's bundled HTML content lives (kept out of the .py file so it's easy to read/edit on its own)."""
        return HTML_DIR

    def _loadHtmlResource(self, filename):
        """Read one bundled HTML resource file (Resources/Html/<filename>) as text, or a short inline error message if it can't be read."""
        path = os.path.join(self._htmlResourceDir(), filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"<p>Could not load {filename}: {e}</p>"

    def _buildExamplePresetsHtml(self):
        """Render the example-presets catalogue (Resources/Presets/example_presets.json) as copyable HTML cards (name, one-line description, the preset's own JSON block), inserted into the static wrapper/style loaded from Resources/Html/example_presets_template.html."""
        rows = []
        for name, entry in self._loadExamplePresets().items():
            desc = entry.get("description", "")
            preset = entry.get("preset", {})
            rows.append(
                f'<h3>{name}</h3>'
                f'<p class="desc">{desc}</p>'
                f'<pre>{json.dumps({name: preset}, indent=2)}</pre>')
        template = self._loadHtmlResource("example_presets_template.html")
        return template.replace("{{CONTENT}}", "".join(rows))

    def _onShowExamplePresets(self):
        """Show the example-presets catalogue, with a button to merge all of them into the Presets field at once."""
        popup = qt.QDialog(self)
        popup.setWindowTitle("Example presets")
        popup.resize(560, 620)
        layout = qt.QVBoxLayout(popup)
        browser = qt.QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(self._buildExamplePresetsHtml())
        layout.addWidget(browser)

        btnRow = qt.QHBoxLayout()
        insertAllBtn = qt.QPushButton("Insert ALL into presets field")
        insertAllBtn.setToolTip("Merges every example above into the presets JSON field (existing entries with the same name are overwritten).")
        insertAllBtn.connect('clicked(bool)', lambda checked=False: self._onInsertAllExamplePresets(popup))
        closeBtn = qt.QPushButton("Close")
        closeBtn.connect('clicked(bool)', lambda checked=False: popup.close())
        btnRow.addWidget(insertAllBtn)
        btnRow.addStretch(1)
        btnRow.addWidget(closeBtn)
        layout.addLayout(btnRow)
        popup.exec_()

    def _onInsertAllExamplePresets(self, popup):
        """Merge every entry from example_presets.json into the current Presets JSON (existing entries with the same name are overwritten) and close the catalogue popup."""
        try:
            current = json.loads(self.presetsEdit.plainText or "{}")
        except Exception:
            current = {}
        current.update({name: entry["preset"] for name, entry in self._loadExamplePresets().items()})
        self.presetsEdit.plainText = json.dumps(current, indent=2)
        self._markDirty()
        popup.close()

    def _populateDefaults(self, cfg):
        """Fill the Defaults / Presets tab from the raw config dict `cfg`."""
        # defaults/presets loaded BEFORE the images loop below, so each row's
        # Preset dropdown is populated with the right choices as it's created
        # (rather than showing an empty list until something else refreshes it).
        defaults = cfg.get("defaults", {}) or {}
        if defaults.get("image"):
            defaults_image = dict(defaults["image"])
            # defaults.image.path_pattern has its own field on the Images tab - keep it out of the JSON box
            self.imgDefaultPathPatternEdit.text = defaults_image.pop("path_pattern", "") or ""
            if defaults_image:
                self.defaultsImageEdit.plainText = json.dumps(defaults_image, indent=2)
        if defaults.get("segment"):
            self.defaultsSegmentEdit.plainText = json.dumps(defaults["segment"], indent=2)
        if cfg.get("presets"):
            self.presetsEdit.plainText = json.dumps(cfg["presets"], indent=2)


    def _collectDefaults(self, cfg):
        """Write the Defaults / Presets tab's part of the config into the dict `cfg` (key order = file order)."""
        defaults = {}
        di = self._parseJsonField(self.defaultsImageEdit, "defaults.image") or {}
        if self.imgDefaultPathPatternEdit.text.strip():
            di["path_pattern"] = self.imgDefaultPathPatternEdit.text.strip()
        if di:
            defaults["image"] = di
        ds = self._parseJsonField(self.defaultsSegmentEdit, "defaults.segment")
        if ds:
            defaults["segment"] = ds
        if defaults:
            cfg["defaults"] = defaults

        presets = self._parseJsonField(self.presetsEdit, "presets")
        if presets:
            cfg["presets"] = presets


    def _clearDefaults(self):
        """Reset the Defaults / Presets tab to its blank/default state."""
        self.defaultsImageEdit.plainText = ""
        self.imgDefaultPathPatternEdit.text = ""
        self.defaultsSegmentEdit.plainText = ""
        self.presetsEdit.plainText = json.dumps(
            {name: self._loadExamplePresets()[name]["preset"]
             for name in ("ct_soft_tissue", "ct_bone") if name in self._loadExamplePresets()}, indent=2)
