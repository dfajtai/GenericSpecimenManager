"""
ConfigEditor
=============

Standalone Qt window for building/editing a study config.json without hand
JSON editing. Covers nearly the whole schema:

  General:        paths, key/table/output-dir columns, batch_mode
  Images:         table (name, csv_column, pattern/strip, type, role,
                   required, preset, opacity, color_table) + per-selected-row
                   "advanced" popup for window_level/threshold/interpolate
  Segmentation:   enabled, reference_image, path_pattern, output_filename,
                   segments table (name, source, csv_column, path_pattern,
                   color via per-selected-row popup)
  Landmarks, Volume rendering, global Window/level, Batch export,
  Segment editor: structured fields
  Defaults / Presets: raw JSON (open-ended, rarely hand-tuned per field)

Opens pre-loaded with whatever config is currently active in the main
module widget (pass initial_path=...). "Load from file..." and "New" both
ask to save first if the form has unsaved edits.
"""

import os
import csv
import json

from Resources.LoggingSetup import logger
from Resources.Definitions import (
    ROLE_CHOICES, TYPE_CHOICES, SOURCE_CHOICES, OVERWRITE_CHOICES, BRUSH_SHAPE_CHOICES,
    COLOR_TABLE_CHOICES, VR_PRESET_CHOICES, CROSSHAIR_MODE_CHOICES, CROSSHAIR_BEHAVIOR_CHOICES,
    CROSSHAIR_THICKNESS_CHOICES, RULER_TYPE_CHOICES, ORIENTATION_MARKER_TYPE_CHOICES,
    ORIENTATION_MARKER_SIZE_CHOICES, DEFAULT_STATS_METRICS,
)

import qt


DEFAULT_SEGMENT_COLOR = (0.9, 0.9, 0.2)


def _read_csv_header(path):
    """Read just the header row of a CSV as a list of column names; returns [] on any read error (missing file, not a CSV, etc.) rather than raising."""
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return [h.strip() for h in next(csv.reader(f)) if h.strip()]
    except Exception:
        return []


def _guess_key_columns(header):
    """Best-effort guess at which header column(s) are the specimen key: anything named like id/sid/specimen/specimenid (case-insensitive), falling back to just the first column."""
    guesses = [h for h in header if h.strip().lower() in ("id", "sid", "specimen", "specimenid")]
    return guesses or (header[:1] if header else [])


def _csv_list(text):
    """Split a comma-separated GUI field into a clean list of non-empty, stripped strings."""
    return [c.strip() for c in text.split(",") if c.strip()]


def _f(text):
    """Parse a GUI field's text as a float, or None if it's empty/unparseable - used everywhere a numeric field is optional (opacity, min/max, diameter, ...)."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class _ImageAdvancedPopup(qt.QDialog):
    """Structured popup for an image row's advanced fields: window_level,
    threshold, interpolate. Replaces free-form JSON with actual fields."""

    WL_MODES = ["(none)", "Auto", "Min / Max", "Window / Level"]

    def __init__(self, parent, data):
        """Build the window_level/threshold/interpolate form, pre-filled from `data` (the row's current advanced dict)."""
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Advanced image fields")
        self.resize(460, 380)
        data = dict(data or {})
        layout = qt.QVBoxLayout(self)
        form = qt.QFormLayout()
        layout.addWidget(qt.QLabel("These only apply to THIS image row (on top of defaults/preset)."))
        layout.addLayout(form)

        wl = data.get("window_level") or {}
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
            "NOT the same numbers as Min/Max, see README.")
        form.addRow("Window/level mode:", self.wlModeCombo)

        self.wlAEdit = qt.QLineEdit("" if wl.get("min", wl.get("window")) is None else str(wl.get("min", wl.get("window"))))
        self.wlALabel = qt.QLabel("Min / Window:")
        form.addRow(self.wlALabel, self.wlAEdit)
        self.wlBEdit = qt.QLineEdit("" if wl.get("max", wl.get("level")) is None else str(wl.get("max", wl.get("level"))))
        self.wlBLabel = qt.QLabel("Max / Level:")
        form.addRow(self.wlBLabel, self.wlBEdit)

        sep1 = qt.QFrame()
        sep1.setFrameShape(qt.QFrame.HLine)
        form.addRow(sep1)

        th = data.get("threshold") or {}
        self.chkThreshold = qt.QCheckBox("Enable threshold")
        self.chkThreshold.checked = bool(th)
        form.addRow(self.chkThreshold)
        self.thMinEdit = qt.QLineEdit("" if th.get("min") is None else str(th["min"]))
        form.addRow("Threshold min:", self.thMinEdit)
        self.thMaxEdit = qt.QLineEdit("" if th.get("max") is None else str(th["max"]))
        form.addRow("Threshold max:", self.thMaxEdit)
        self.chkThresholdApply = qt.QCheckBox("Apply (hide values outside range)")
        self.chkThresholdApply.checked = th.get("apply", True)
        form.addRow(self.chkThresholdApply)

        sep2 = qt.QFrame()
        sep2.setFrameShape(qt.QFrame.HLine)
        form.addRow(sep2)

        self.interpolateCombo = qt.QComboBox()
        self.interpolateCombo.addItems(["(unset)", "on", "off"])
        if "interpolate" in data:
            self.interpolateCombo.currentText = "on" if data["interpolate"] else "off"
        form.addRow("Interpolate:", self.interpolateCombo)

        btnRow = qt.QHBoxLayout()
        btnRow.addStretch(1)
        okBtn = qt.QPushButton("OK")
        okBtn.connect('clicked(bool)', lambda checked=False: self.accept())
        cancelBtn = qt.QPushButton("Cancel")
        cancelBtn.connect('clicked(bool)', lambda checked=False: self.reject())
        btnRow.addWidget(okBtn)
        btnRow.addWidget(cancelBtn)
        layout.addLayout(btnRow)

    def result_dict(self):
        """Build the advanced dict (window_level/threshold/interpolate) from the form's current values, omitting anything the user left unset."""
        out = {}
        mode = self.wlModeCombo.currentText
        a, b = _f(self.wlAEdit.text), _f(self.wlBEdit.text)
        if mode == "Auto":
            out["window_level"] = {"auto": True}
        elif mode == "Min / Max" and (a is not None or b is not None):
            out["window_level"] = {k: v for k, v in (("min", a), ("max", b)) if v is not None}
        elif mode == "Window / Level" and (a is not None or b is not None):
            out["window_level"] = {k: v for k, v in (("window", a), ("level", b)) if v is not None}

        if self.chkThreshold.checked:
            th = {"apply": self.chkThresholdApply.checked}
            mn, mx = _f(self.thMinEdit.text), _f(self.thMaxEdit.text)
            if mn is not None:
                th["min"] = mn
            if mx is not None:
                th["max"] = mx
            out["threshold"] = th

        if self.interpolateCombo.currentText != "(unset)":
            out["interpolate"] = self.interpolateCombo.currentText == "on"

        return out


class _TextPopup(qt.QDialog):
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


class ConfigEditorDialog(qt.QDialog):

    """Standalone, non-modal window for building/editing a study config.json without hand-editing JSON. Opens pre-loaded with whatever config is active in the main module (if any); New/Load both confirm before discarding unsaved changes."""
    def __init__(self, parent=None, initial_path=None, on_saved=None):
        """Build the whole dialog and, if initial_path is given, load that config immediately (skipping the discard-changes prompt, since there's nothing to discard yet). on_saved, if given, is called as on_saved(path) after every successful Save - the main module passes its own "load this config into the active scene" logic here, so Save can offer to push the change live instead of requiring a manual re-browse there."""
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Config Editor")
        self.resize(1200, 720)

        self._current_path = None
        self._preseg_abs_path = ""    # true absolute preseg path, tracked separately from its (possibly relative) display text
        self._dirty = False
        self._image_advanced = []    # per-row extra dict: window_level/threshold/interpolate
        self._segment_colors = []    # per-row [r,g,b] or None
        self._on_saved = on_saved

        self._build_ui()

        if initial_path and os.path.exists(initial_path):
            self._load_from_file(initial_path, ask_confirm=False)
        self._dirty = False
        self._updateTitle()

    # ---- top-level UI ----

    def _build_ui(self):
        """Lay out the whole dialog: top New/Load/Help row, the tabbed form, the output-path row, and the Save/Close row - dirty-tracking is wired LAST, once every widget referenced by _connect_dirty_tracking() already exists."""
        outer = qt.QVBoxLayout(self)

        topRow = qt.QHBoxLayout()
        newBtn = qt.QPushButton("New")
        newBtn.connect('clicked(bool)', lambda checked=False: self._onNew())
        loadBtn = qt.QPushButton("Load from file...")
        loadBtn.connect('clicked(bool)', lambda checked=False: self._onLoadFromFile())
        reloadBtn = qt.QPushButton("Reload from disk")
        reloadBtn.setToolTip("Re-reads the CURRENTLY OPEN file from disk - handy after editing it outside this dialog (e.g. hand-editing the JSON, or another process/script writing it), without having to browse again.")
        reloadBtn.connect('clicked(bool)', lambda checked=False: self._onReload())
        helpBtn = qt.QPushButton("Help")
        helpBtn.connect('clicked(bool)', lambda checked=False: self._onShowHelp())
        topRow.addWidget(newBtn)
        topRow.addWidget(loadBtn)
        topRow.addWidget(reloadBtn)
        topRow.addStretch(1)
        topRow.addWidget(helpBtn)
        outer.addLayout(topRow)

        tabs = qt.QTabWidget()
        outer.addWidget(tabs)
        tabs.addTab(self._build_general_tab(), "General")
        tabs.addTab(self._build_images_tab(), "Images")
        tabs.addTab(self._build_segmentation_tab(), "Segmentation")
        tabs.addTab(self._build_landmarks_tab(), "Landmarks")
        tabs.addTab(self._build_workspace_tab(), "Workspace")
        tabs.addTab(self._build_segment_editor_tab(), "Segment editor")
        tabs.addTab(self._build_vr_tab(), "Volume rendering")
        tabs.addTab(self._build_advanced_tab(), "Defaults / Presets (JSON)")
        tabs.addTab(self._build_manual_tab(), "Manual edit config")

        self.outputEdit, outputRow = self._file_row(filter_="JSON files (*.json)", save=True, default_name="config.json")
        form = qt.QFormLayout()
        form.addRow("Output config.json:", outputRow)
        outer.addLayout(form)

        btnRow = qt.QHBoxLayout()
        btnRow.addStretch(1)
        saveBtn = qt.QPushButton("Save config")
        saveBtn.connect('clicked(bool)', lambda checked=False: self._onSave())
        closeBtn = qt.QPushButton("Close")
        closeBtn.connect('clicked(bool)', lambda checked=False: self.close())
        btnRow.addWidget(saveBtn)
        btnRow.addWidget(closeBtn)
        outer.addLayout(btnRow)

        self._connect_dirty_tracking()

    def _connect_dirty_tracking(self):
        """Hook every plain field's change signal to _mark_dirty(). Tables/comboboxes created dynamically per-row (Images/Segments/VR rows) wire their own dirty signal individually, right where each row is built."""
        for w in self.findChildren(qt.QLineEdit):
            w.textChanged.connect(self._mark_dirty)
        for w in self.findChildren(qt.QCheckBox):
            w.stateChanged.connect(self._mark_dirty)
        for w in self.findChildren(qt.QComboBox):
            w.currentIndexChanged.connect(self._mark_dirty)
        for w in self.findChildren(qt.QPlainTextEdit):
            w.textChanged.connect(self._mark_dirty)
        self.imgTable.itemChanged.connect(self._mark_dirty)
        self.segTable.itemChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *_a):
        """Flag the form as having unsaved changes and refresh the title bar's '*' marker."""
        self._dirty = True
        self._updateTitle()

    def _updateTitle(self):
        """Show the current file name (or '(new)') plus a trailing '*' if there are unsaved changes."""
        name = os.path.basename(self._current_path) if self._current_path else "(new)"
        self.setWindowTitle(f"Config Editor - {name}{' *' if self._dirty else ''}")

    # ---- helpers ----

    def _file_row(self, on_change=None, filter_="CSV files (*.csv);;All files (*)",
                  save=False, default_name="", directory=False, relative_to=None):
        """Build a LineEdit+Browse-button pair. Handles three picker modes (open file / save file / existing directory) and, if `relative_to` is given, displays the picked path relative to that folder (falling back to absolute if the path isn't actually inside it). The full absolute path is always kept in the tooltip."""
        container = qt.QWidget()
        rowLayout = qt.QHBoxLayout(container)
        rowLayout.setContentsMargins(0, 0, 0, 0)
        edit = qt.QLineEdit()
        browse = qt.QPushButton("Browse...")
        rowLayout.addWidget(edit)
        rowLayout.addWidget(browse)

        def _starting_path():
            """Resolve the field's current (possibly study-dir-relative) text to an absolute path for the file dialog's starting location."""
            current = edit.text.strip()
            if current and not os.path.isabs(current) and relative_to:
                root = relative_to()
                if root:
                    return os.path.join(root, current)
            return current

        def _browse():
            """Open the appropriate file/save/folder dialog and, on a pick, update the field (relative to `relative_to()` if given) and fire on_change with the true absolute path."""
            start = _starting_path()
            if directory:
                fname = qt.QFileDialog.getExistingDirectory(self, "Select folder", start)
            elif save:
                fname = qt.QFileDialog.getSaveFileName(self, "Save as", start or default_name, filter_)
            else:
                fname = qt.QFileDialog.getOpenFileName(self, "Select file", start, filter_)
            if not fname:
                return

            display = fname
            if relative_to and not directory:
                root = relative_to()
                if root:
                    try:
                        rel = os.path.relpath(fname, root)
                        if not rel.startswith(".."):
                            display = rel
                    except ValueError:
                        pass  # e.g. different drive on Windows - keep absolute

            edit.text = display
            edit.setToolTip(f"Full path: {fname}")
            if on_change:
                on_change(fname)   # callbacks (e.g. CSV header reading) always get the real absolute path

        browse.connect('clicked(bool)', lambda checked=False: _browse())
        return edit, container

    # ---- General tab ----

    def _build_general_tab(self):
        """Study/database/preseg paths, key/table/output-dir columns, and batch mode."""
        w = qt.QWidget()
        form = qt.QFormLayout(w)

        self.studyDirEdit, studyDirRow = self._file_row(directory=True)
        self.studyDirEdit.setPlaceholderText("default: preseg CSV's folder")
        self.studyDirEdit.setToolTip(
            "Base folder every relative path in the config resolves against. Optional, but set this "
            "FIRST if you're going to set it at all - the two CSV pickers below show their path "
            "relative to whatever Study dir already contains at the moment you browse, so setting it "
            "afterward won't retroactively shorten paths you already picked. Leave empty to default "
            "to the preseg CSV's own folder.")
        form.addRow("Study dir (optional, set first):", studyDirRow)

        self.presegEdit, presegRow = self._file_row(
            on_change=self._onPresegChanged,
            relative_to=lambda: self.studyDirEdit.text.strip())
        self.presegEdit.setToolTip("Shown relative to Study dir above if that's set - hover for the full path.")
        self.presegEdit.editingFinished.connect(
            lambda: self._onPresegChanged(self._resolve_csv_path(self.presegEdit.text)))
        form.addRow("Images / preseg CSV:", presegRow)
        self.dbEdit, dbRow = self._file_row(
            relative_to=lambda: self.studyDirEdit.text.strip() or os.path.dirname(self._preseg_abs_path or ""))
        self.dbEdit.setToolTip("Shown relative to Study dir above (or to the preseg CSV's folder if Study dir is empty) - hover for the full path.")
        form.addRow("Database CSV:", dbRow)

        showColsBtn = qt.QPushButton("Show CSV columns (copyable)...")
        showColsBtn.setToolTip("Reads the header row of both CSVs above and lists all columns - copy names from here into the fields below/Images tab.")
        showColsBtn.connect('clicked(bool)', lambda checked=False: self._onShowCsvColumns())
        form.addRow(showColsBtn)

        self.keyColumnsEdit = qt.QLineEdit()
        self.keyColumnsEdit.setPlaceholderText("comma-separated, e.g. ID,measurement")
        self.keyColumnsEdit.setToolTip(
            "The composite specimen ID. MUST exist, with matching values, in BOTH CSVs above - "
            "use 'Show CSV columns...' to see which column names are common to both (likely candidates).")
        form.addRow("Key columns:", self.keyColumnsEdit)
        self.doneColumnEdit = qt.QLineEdit("done")
        self.doneColumnEdit.setToolTip("database.csv column (0/1) marking a specimen as finished - drives table row highlighting and batch export filtering.")
        form.addRow("Done column:", self.doneColumnEdit)
        self.tableColumnsEdit = qt.QLineEdit()
        self.tableColumnsEdit.setPlaceholderText("comma-separated database.csv columns shown in the table")
        self.tableColumnsEdit.setToolTip("Which database.csv columns appear (and are editable) in the main module's specimen table. Any column works, not just done.")
        form.addRow("Table columns:", self.tableColumnsEdit)
        self.outputDirPatternEdit = qt.QLineEdit()
        self.outputDirPatternEdit.setPlaceholderText("e.g. {ID}/{measurement}")
        self.outputDirPatternEdit.setToolTip(
            "Builds each specimen's OWN output folder, where its segmentation/markups/exports get "
            "written. Same {curly-brace} placeholder style as every other 'path pattern' field in this "
            "editor (Segmentation/Landmarks tabs) - anything in {braces} is a column name whose VALUE "
            "gets substituted in; everything else (slashes, dashes, ...) is literal text.\n\n"
            "Worked example: {ID}/{measurement} with a row ID='D001', measurement='baseline' -> output "
            "folder study_dir/D001/baseline/\n\n"
            "A shorter pattern (just {ID}) would instead put every measurement of the same specimen "
            "into one shared folder study_dir/D001/ - only do this if that's actually what you want, "
            "since two rows with the same ID but different measurement would then overwrite each "
            "other's files. Leave empty to default to your Key columns, in order (e.g. Key columns "
            "ID,measurement -> {ID}/{measurement} automatically).")
        form.addRow("Output dir pattern:", self.outputDirPatternEdit)

        sep = qt.QFrame()
        sep.setFrameShape(qt.QFrame.HLine)
        form.addRow(sep)

        self.chkBatchMode = qt.QCheckBox("Group subjects by key")
        self.chkBatchMode.setToolTip(
            "Shows a group-select combo in the main module after Initialize Study, to browse/filter "
            "the specimen table by the key column below. This is purely a main-module VIEWING "
            "convenience - it does NOT affect Batch Export below, which only needs the Group-by key "
            "set (see that section's 'Per-batch operation').")
        form.addRow(self.chkBatchMode)
        self.batchColumnEdit = qt.QLineEdit()
        self.batchColumnEdit.setPlaceholderText("database.csv column to group/filter by, e.g. batch")
        form.addRow("Group by key:", self.batchColumnEdit)

        sep2 = qt.QFrame()
        sep2.setFrameShape(qt.QFrame.HLine)
        form.addRow(sep2)

        beGroup = qt.QGroupBox("Batch export")
        beForm = qt.QFormLayout(beGroup)
        beHint = qt.QLabel(
            "Runs once, against every specimen marked 'done' in the database, without opening the "
            "interactive viewer for each one. Pick any combination of what to produce below - each "
            "is independent, and all of them run in the same single pass per specimen.")
        beHint.setWordWrap(True)
        beForm.addRow(beHint)

        self.chkBeEnabled = qt.QCheckBox("Enabled")
        self.chkBeEnabled.setToolTip("Master switch for this whole section - turn this off and everything below is grayed out (its values are kept, just not used) until turned back on.")
        self.chkBeEnabled.connect('toggled(bool)', self._onBeEnabledToggled)
        beForm.addRow(self.chkBeEnabled)

        self._beChildWidgets = []

        producesSep = qt.QFrame()
        producesSep.setFrameShape(qt.QFrame.HLine)
        beForm.addRow(producesSep)
        beForm.addRow(qt.QLabel("<b>What to produce</b> - check any combination:"))
        producesRow = qt.QHBoxLayout()
        self.chkBeExportSegments = qt.QCheckBox("Export segments")
        self.chkBeExportSegments.setToolTip("Writes each segment to its own labelmap file, one per segment per specimen.")
        producesRow.addWidget(self.chkBeExportSegments)
        self.chkBeExportMarkups = qt.QCheckBox("Export markups")
        self.chkBeExportMarkups.setToolTip("Writes each specimen's markups/landmarks file.")
        producesRow.addWidget(self.chkBeExportMarkups)
        self.chkBeComputeStats = qt.QCheckBox("Custom segment statistics")
        self.chkBeComputeStats.setToolTip(
            "Needs numpy installed. Computed straight from Slicer's own segment export (handles "
            "overlapping segments correctly) - every 'done' specimen's rows go into a combined CSV. "
            "Configured in the 'Segment statistics settings' group further down.")
        producesRow.addWidget(self.chkBeComputeStats)
        producesRow.addStretch(1)
        beForm.addRow(producesRow)
        self._beChildWidgets += [self.chkBeExportSegments, self.chkBeExportMarkups, self.chkBeComputeStats]

        settingsSep = qt.QFrame()
        settingsSep.setFrameShape(qt.QFrame.HLine)
        beForm.addRow(settingsSep)
        beForm.addRow(qt.QLabel("<b>Export segments settings</b>:"))

        refRow = qt.QHBoxLayout()
        self.beReferenceImageEdit = qt.QComboBox()
        self.beReferenceImageEdit.setEditable(True)
        self.beReferenceImageEdit.setToolTip(
            "Reference volume for exporting segments to labelmaps (also the fallback for the stats "
            "reference image(s) below, if those are left empty). If empty, falls back to "
            "segmentation.reference_image. 'Suggest' fills this from the Images tab.")
        refRow.addWidget(self.beReferenceImageEdit)
        refSuggestBtn = qt.QPushButton("Suggest")
        refSuggestBtn.setToolTip("Fills in every image name currently in the Images tab, so you can just pick one.")
        refSuggestBtn.connect('clicked(bool)', lambda checked=False: self._onSuggestReferenceImage())
        refRow.addWidget(refSuggestBtn)
        beForm.addRow("Reference image (name):", refRow)
        self._beChildWidgets += [self.beReferenceImageEdit, refSuggestBtn]

        self.beOutputDirEdit, beOutputDirRow = self._file_row(directory=True)
        self.beOutputDirEdit.setToolTip(
            "Absolute path -> used exactly as given. Relative (or empty) path -> resolved under "
            "study_dir. Optional shared export folder for ALL specimens - a PLAIN literal folder "
            "(no {ID}-style per-specimen placeholders; that's what this tab's Output dir pattern is "
            "for). May contain a literal \"{batch}\" placeholder - see Per-batch operation below. If "
            "empty, each specimen exports into its own out_dir instead.")
        beForm.addRow("Batch export output dir:", beOutputDirRow)
        self._beChildWidgets.append(beOutputDirRow)

        sharedSep = qt.QFrame()
        sharedSep.setFrameShape(qt.QFrame.HLine)
        beForm.addRow(sharedSep)
        beForm.addRow(qt.QLabel("<b>Shared settings</b> - apply across exports AND statistics alike:"))

        segFilterRow = qt.QHBoxLayout()
        self.beSegmentsFilterEdit = qt.QLineEdit()
        self.beSegmentsFilterEdit.setPlaceholderText("comma-separated segment names, empty = all")
        segFilterRow.addWidget(self.beSegmentsFilterEdit)
        segFilterAllBtn = qt.QPushButton("Use all segments")
        segFilterAllBtn.setToolTip("Fills in every segment name currently in the Segmentation tab.")
        segFilterAllBtn.connect('clicked(bool)', lambda checked=False: self._onInsertAllSegmentsFilter())
        segFilterRow.addWidget(segFilterAllBtn)
        beForm.addRow("Segments filter:", segFilterRow)
        self._beChildWidgets += [self.beSegmentsFilterEdit, segFilterAllBtn]

        self.chkBePerBatchOperation = qt.QCheckBox("Per-batch operation")
        self.chkBePerBatchOperation.setToolTip(
            "Splits EVERYTHING this run produces by the Group-by key above - segment files, markup "
            "files, AND the stats CSV: one output_dir/<key value>/... subfolder for files, one "
            "stats CSV per key value (auto-named, or use \"{batch}\" yourself in Batch export stats "
            "output path below). Only needs the Group-by key above to be SET - independent of "
            "\"Group subjects by key\" in the General tab, which is a separate, main-module-only "
            "viewing convenience.")
        beForm.addRow(self.chkBePerBatchOperation)
        self._beChildWidgets.append(self.chkBePerBatchOperation)

        statsSep = qt.QFrame()
        statsSep.setFrameShape(qt.QFrame.HLine)
        beForm.addRow(statsSep)
        beForm.addRow(qt.QLabel(
            "<b>Segment statistics settings</b> - only used when \"Custom segment statistics\" "
            "above is checked:"))

        statsRefRow = qt.QHBoxLayout()
        self.statsReferenceImagesEdit = qt.QLineEdit()
        self.statsReferenceImagesEdit.setPlaceholderText("comma-separated Images-tab names")
        self.statsReferenceImagesEdit.setToolTip(
            "One or more Images-tab names to sample intensities from - a SEPARATE stats row per "
            "(specimen, sample image, segment), added to the ID/segment columns. All of them must "
            "share the segmentation's geometry (same grid). If empty, falls back to Reference image "
            "above, then segmentation.reference_image.")
        statsRefRow.addWidget(self.statsReferenceImagesEdit)
        statsRefAllBtn = qt.QPushButton("Use all loaded images")
        statsRefAllBtn.setToolTip("Fills in every image name currently in the Images tab.")
        statsRefAllBtn.connect('clicked(bool)', lambda checked=False: self._onUseAllImagesForStats())
        statsRefRow.addWidget(statsRefAllBtn)
        beForm.addRow("Stats reference image(s):", statsRefRow)
        self._beChildWidgets += [self.statsReferenceImagesEdit, statsRefAllBtn]

        metricsRow = qt.QHBoxLayout()
        self.statsMetricsEdit = qt.QLineEdit()
        self.statsMetricsEdit.setPlaceholderText("volume,min,max,mean,median,std,percentile_5,percentile_25,percentile_75,percentile_95")
        self.statsMetricsEdit.setToolTip(
            "Comma-separated: volume, min, max, mean, median, std, and/or percentile_<N> (e.g. "
            "percentile_25) - each becomes one CSV column. Leave empty to use that same default "
            "automatically - you don't have to type it yourself unless you want something different.")
        metricsRow.addWidget(self.statsMetricsEdit)
        statsMetricsDefaultBtn = qt.QPushButton("Insert default")
        statsMetricsDefaultBtn.setToolTip("Fills in the default metric list - the same one used automatically if you leave this empty, just visible/editable from here.")
        statsMetricsDefaultBtn.connect('clicked(bool)', lambda checked=False: self._onInsertDefaultStatsMetrics())
        metricsRow.addWidget(statsMetricsDefaultBtn)
        beForm.addRow("Metrics:", metricsRow)
        self._beChildWidgets += [self.statsMetricsEdit, statsMetricsDefaultBtn]

        self.statsOutputPathEdit = qt.QLineEdit()
        self.statsOutputPathEdit.setPlaceholderText("report.csv")
        self.statsOutputPathEdit.setToolTip(
            "Absolute path -> used exactly as given. Relative (or empty) path -> resolved under "
            "study_dir (no need to spell that out yourself). \"{date}\" (YYYY-MM-DD), \"{time}\" "
            "(HH-MM-SS), and/or \"{datetime}\" (YYYY-MM-DD_HH-MM-SS) are substituted if present. With "
            "Per-batch operation on: a literal \"{batch}\" placeholder is substituted per batch "
            "value, or - if you don't include one - the batch value is inserted before the extension "
            "automatically, so per-batch files never collide. Leave empty to default to report.csv.")
        beForm.addRow("Batch export stats output path:", self.statsOutputPathEdit)
        self._beChildWidgets.append(self.statsOutputPathEdit)

        form.addRow(beGroup)
        self._onBeEnabledToggled(self.chkBeEnabled.checked)

        return w

    def _resolve_csv_path(self, text):
        """Resolve a (possibly study-dir-relative) path field to a real
        filesystem path for reading - works whether the value got there via
        Browse (already handled in _file_row) or manual typing/pasting,
        which never went through that relative-path logic."""
        text = (text or "").strip()
        if not text or os.path.isabs(text):
            return text
        study_dir = self.studyDirEdit.text.strip()
        return os.path.join(study_dir, text) if study_dir else text

    def _onShowCsvColumns(self):
        """Read both CSVs' headers (resolving study-dir-relative paths first) and show them side by side - plus the columns common to both, which are the most likely Key Columns candidates."""
        preseg_text = self.presegEdit.text.strip()
        db_text = self.dbEdit.text.strip()
        if not preseg_text and not db_text:
            qt.QMessageBox.information(self, "Config Editor", "Set the preseg and/or database CSV path first.")
            return

        preseg_path = self._resolve_csv_path(preseg_text)
        db_path = self._resolve_csv_path(db_text)
        preseg_header = _read_csv_header(preseg_path) if preseg_path else []
        db_header = _read_csv_header(db_path) if db_path else []
        common = [c for c in preseg_header if c in db_header]

        lines = []
        lines.append(f"PRESEG CSV: {preseg_text or '(not set)'}" + (f"  ->  {preseg_path}" if preseg_path != preseg_text else ""))
        lines.append("  " + (", ".join(preseg_header) if preseg_header else "(could not read - check Study dir / the path above)"))
        lines.append("")
        lines.append(f"DATABASE CSV: {db_text or '(not set)'}" + (f"  ->  {db_path}" if db_path != db_text else ""))
        lines.append("  " + (", ".join(db_header) if db_header else "(could not read - check Study dir / the path above)"))
        lines.append("")
        lines.append("COMMON TO BOTH (likely Key columns candidates):")
        lines.append("  " + (", ".join(common) if common else "(none found - check the paths above)"))
        lines.append("")
        lines.append("Tip: select all (Ctrl+A) and copy (Ctrl+C) any of the lists above to paste")
        lines.append("into Key columns / Table columns / an Images row's CSV column, etc.")

        popup = _TextPopup(self, "CSV columns", "\n".join(lines))
        popup.exec_()

        if not self.keyColumnsEdit.text.strip() and common:
            self.keyColumnsEdit.text = ",".join(_guess_key_columns(common) or common[:1])

    def _onPresegChanged(self, path):
        """Refresh everything that depends on the preseg CSV's header: the quick-add column table (Images tab, key columns excluded) and, if Key Columns is still empty, a best-effort guess."""
        self._preseg_abs_path = path
        header = _read_csv_header(path)
        if hasattr(self, "quickColumnsTable"):
            self.quickColumnsTable.setRowCount(0)
            key_cols = set(_csv_list(self.keyColumnsEdit.text))
            for col in header:
                if col in key_cols:
                    continue
                row = self.quickColumnsTable.rowCount
                self.quickColumnsTable.insertRow(row)
                nameItem = qt.QTableWidgetItem(col)
                nameItem.setFlags(nameItem.flags() & ~qt.Qt.ItemIsEditable)
                self.quickColumnsTable.setItem(row, 0, nameItem)

                addItem = qt.QTableWidgetItem()
                addItem.setFlags(qt.Qt.ItemIsUserCheckable | qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable)
                addItem.setCheckState(qt.Qt.Unchecked)
                self.quickColumnsTable.setItem(row, 1, addItem)

                lmItem = qt.QTableWidgetItem()
                lmItem.setFlags(qt.Qt.ItemIsUserCheckable | qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable)
                lmItem.setCheckState(qt.Qt.Checked if "mask" in col.lower() or "label" in col.lower() else qt.Qt.Unchecked)
                self.quickColumnsTable.setItem(row, 2, lmItem)
        if not self.keyColumnsEdit.text.strip():
            guessed = _guess_key_columns(header)
            if guessed:
                self.keyColumnsEdit.text = ",".join(guessed)

    # ---- Images tab ----

    def _build_images_tab(self):
        """Quick-add table (from preseg CSV columns) + the main images[] table + the live 'Effective settings' preview for whichever row is selected."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)

        quickGroup = qt.QGroupBox("Quick-add from preseg CSV columns")
        quickLayout = qt.QVBoxLayout(quickGroup)
        quickHint = qt.QLabel("From the preseg CSV header. Check 'Add' for columns to add as image rows; check 'Labelmap' if that column is a mask/label image.")
        quickHint.setWordWrap(True)
        quickLayout.addWidget(quickHint)
        self.quickColumnsTable = qt.QTableWidget(0, 3)
        self.quickColumnsTable.setHorizontalHeaderLabels(["Column", "Add", "Labelmap"])
        self.quickColumnsTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.quickColumnsTable.setMaximumHeight(140)
        quickLayout.addWidget(self.quickColumnsTable)
        quickBtn = qt.QPushButton("Add checked columns as image rows")
        quickBtn.connect('clicked(bool)', lambda checked=False: self._onQuickAddImages())
        quickLayout.addWidget(quickBtn)
        layout.addWidget(quickGroup)

        imgHint = qt.QLabel(
            "'Pattern' (regex, e.g. ^seq_.*$) opens ONE image per matching, non-empty preseg.csv "
            "column for a given specimen - 'Strip prefix/suffix' trims that column name into the "
            "image's display name. Leave Pattern empty for a normal single, explicit image. The "
            "'Advanced' column summarizes window/level/threshold/interpolate for that row, if set.")
        imgHint.setWordWrap(True)
        layout.addWidget(imgHint)

        self.imgTable = qt.QTableWidget(0, 12)
        headers = ["Name", "CSV column", "Pattern (regex)", "Strip prefix", "Strip suffix",
                   "Type", "Role", "Required", "Preset", "Opacity", "Color table", "Advanced"]
        header_tips = [
            "Logical name used elsewhere (reference_image, presets, roles).",
            "preseg.csv column holding this image's relative path.",
            "Regex: open one image per matching preseg.csv column instead of a fixed one.",
            "Trim this from the start of the matched column name (Pattern mode only).",
            "Trim this from the end of the matched column name (Pattern mode only).",
            "'volume' (default) or 'labelmap'.",
            "background/label/foreground control slice-view layers; (none) = loaded but not shown as a layer.",
            "If missing/unloadable, initializing the specimen raises an error instead of skipping.",
            "Name of a presets[] entry (Defaults / Presets tab) to inherit visual properties from.",
            "0-1, used when Role is label or foreground.",
            "Slicer color node ID or name, e.g. Grey, Rainbow, vtkMRMLColorTableNodeRed.",
            "Read-only summary of window_level/threshold/interpolate set via 'Edit advanced...' below.",
        ]
        self.imgTable.setHorizontalHeaderLabels(headers)
        for col, tip in enumerate(header_tips):
            hitem = self.imgTable.horizontalHeaderItem(col)
            if hitem:
                hitem.setToolTip(tip)
        self.imgTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.imgTable.itemSelectionChanged.connect(self._onImageRowSelected)
        layout.addWidget(self.imgTable)

        btnRow = qt.QHBoxLayout()
        addBtn = qt.QPushButton("Add image")
        addBtn.connect('clicked(bool)', lambda checked=False: self._onAddImage())
        removeBtn = qt.QPushButton("Remove selected")
        removeBtn.connect('clicked(bool)', lambda checked=False: self._onRemoveImage())
        advBtn = qt.QPushButton("Edit advanced (window/level, threshold, interpolate)...")
        advBtn.setToolTip("Opens a form for the SELECTED row's window/level, threshold, and interpolate settings.")
        advBtn.connect('clicked(bool)', lambda checked=False: self._onEditImageAdvanced())
        btnRow.addWidget(addBtn)
        btnRow.addWidget(removeBtn)
        btnRow.addWidget(advBtn)
        btnRow.addStretch(1)
        layout.addLayout(btnRow)

        previewGroup = qt.QGroupBox("Effective settings for the selected row (defaults.image -> preset -> this row, last wins)")
        previewLayout = qt.QVBoxLayout(previewGroup)
        self.imgPreviewEdit = qt.QPlainTextEdit()
        self.imgPreviewEdit.setReadOnly(True)
        self.imgPreviewEdit.setMaximumHeight(110)
        self.imgPreviewEdit.setPlaceholderText("Select a row above to see exactly what settings actually apply to it, after merging.")
        previewLayout.addWidget(self.imgPreviewEdit)
        layout.addWidget(previewGroup)

        return w

    def _onImageRowSelected(self):
        """Refresh the Effective Settings preview for the newly-selected image row (or clear it if nothing's selected)."""
        row = self.imgTable.currentRow()
        if row < 0:
            self.imgPreviewEdit.plainText = ""
            return
        self._refresh_image_preview(row)

    def _refresh_preview_if_selected(self):
        """Re-run the Effective Settings preview for whatever row is currently selected - used as the handler when defaults.image/presets JSON changes, since those affect the merge result even though no row itself was touched."""
        row = self.imgTable.currentRow()
        if row >= 0:
            self._refresh_image_preview(row)

    def _refresh_image_preview(self, row):
        """Recompute and render the Effective Settings preview text for one row: its own fields, the matched preset (if any), defaults.image, and the final merged result."""
        own, defaults, preset, preset_name, effective = self._compute_effective_image(row)
        lines = []
        lines.append(f"1) defaults.image:        {json.dumps(defaults) if defaults else '(empty)'}")
        if preset_name:
            lines.append(f"2) preset '{preset_name}':  {json.dumps(preset) if preset else '(not found in presets JSON)'}")
        else:
            lines.append("2) preset:                 (none selected on this row)")
        lines.append(f"3) this row's own fields:  {json.dumps(own)}")
        lines.append("")
        lines.append(f"= EFFECTIVE (what actually applies): {json.dumps(effective)}")
        self.imgPreviewEdit.plainText = "\n".join(lines)

    def _compute_effective_image(self, row):
        """Merge defaults.image -> preset (if the row names one) -> the row's
        own fields, exactly like the engine does at runtime. Returns
        (own, defaults, preset, preset_name, effective)."""
        own = self._read_image_row(row) or {}
        try:
            defaults = json.loads(self.defaultsImageEdit.plainText or "{}")
        except Exception:
            defaults = {}
        preset_name = own.get("preset")
        preset = {}
        if preset_name:
            try:
                presets = json.loads(self.presetsEdit.plainText or "{}")
                preset = presets.get(preset_name) or {}
            except Exception:
                preset = {}
        effective = {}
        effective.update(defaults)
        effective.update(preset)
        effective.update(own)
        return own, defaults, preset, preset_name, effective

    def _onQuickAddImages(self):
        """Add one image row per checked column in the quick-add table (Labelmap-checked columns get type='labelmap'), then reset those checkboxes and re-sync the Volume Rendering table's image list."""
        added = 0
        for row in range(self.quickColumnsTable.rowCount):
            addItem = self.quickColumnsTable.item(row, 1)
            if addItem.checkState() == qt.Qt.Checked:
                col = self.quickColumnsTable.item(row, 0).text()
                lmItem = self.quickColumnsTable.item(row, 2)
                d = {"name": col, "csv_column": col}
                if lmItem.checkState() == qt.Qt.Checked:
                    d["type"] = "labelmap"
                self._add_image_row(d)
                addItem.setCheckState(qt.Qt.Unchecked)
                added += 1
        if added == 0:
            qt.QMessageBox.information(self, "Config Editor", "Check 'Add' for at least one column above first.")
        elif hasattr(self, "vrTable"):
            self._refresh_vr_table()

    def _add_image_row(self, d):
        """Append one row to the images table from a dict (name/csv_column/pattern/.../color_table/window_level/threshold/interpolate): builds the Type/Role/Preset/Color-table combo cells, the Required checkbox, and stashes window_level/threshold/interpolate in the parallel _image_advanced list (there's no visible column for those - see 'Advanced')."""
        row = self.imgTable.rowCount
        self.imgTable.insertRow(row)
        self.imgTable.setItem(row, 0, qt.QTableWidgetItem(d.get("name", "")))
        self.imgTable.setItem(row, 1, qt.QTableWidgetItem(d.get("csv_column", "")))
        self.imgTable.setItem(row, 2, qt.QTableWidgetItem(d.get("pattern", "")))
        self.imgTable.setItem(row, 3, qt.QTableWidgetItem(d.get("strip_prefix", "")))
        self.imgTable.setItem(row, 4, qt.QTableWidgetItem(d.get("strip_suffix", "")))

        typeCombo = qt.QComboBox()
        typeCombo.addItems(TYPE_CHOICES)
        typeCombo.currentText = d.get("type", "volume")
        typeCombo.currentIndexChanged.connect(self._mark_dirty)
        self.imgTable.setCellWidget(row, 5, typeCombo)

        roleCombo = qt.QComboBox()
        roleCombo.addItems(ROLE_CHOICES)
        roleCombo.currentText = d.get("role") or "(none)"
        roleCombo.currentIndexChanged.connect(self._mark_dirty)
        self.imgTable.setCellWidget(row, 6, roleCombo)

        reqItem = qt.QTableWidgetItem()
        reqItem.setFlags(qt.Qt.ItemIsUserCheckable | qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable)
        reqItem.setCheckState(qt.Qt.Checked if d.get("required") else qt.Qt.Unchecked)
        self.imgTable.setItem(row, 7, reqItem)

        presetCombo = qt.QComboBox()
        presetCombo.addItem("")
        presetCombo.addItems(self._get_preset_names())
        wanted_preset = d.get("preset", "")
        if wanted_preset and wanted_preset not in self._get_preset_names():
            presetCombo.addItem(wanted_preset)  # keep an unknown/not-yet-defined preset name visible rather than losing it
        presetCombo.currentText = wanted_preset
        presetCombo.currentIndexChanged.connect(self._mark_dirty)
        self.imgTable.setCellWidget(row, 8, presetCombo)

        self.imgTable.setItem(row, 9, qt.QTableWidgetItem("" if d.get("opacity") is None else str(d.get("opacity"))))

        colorCombo = qt.QComboBox()
        colorCombo.setEditable(True)
        colorCombo.addItems(COLOR_TABLE_CHOICES)
        wanted_color = d.get("color_table", "")
        if wanted_color and wanted_color not in COLOR_TABLE_CHOICES:
            colorCombo.addItem(wanted_color)
        colorCombo.currentText = wanted_color
        colorCombo.currentIndexChanged.connect(self._mark_dirty)
        self.imgTable.setCellWidget(row, 10, colorCombo)

        advItem = qt.QTableWidgetItem("")
        advItem.setFlags(advItem.flags() & ~qt.Qt.ItemIsEditable)
        self.imgTable.setItem(row, 11, advItem)

        adv = {k: d[k] for k in ("window_level", "threshold", "interpolate") if k in d}
        self._image_advanced.insert(row, adv)
        self._update_advanced_indicator(row)
        self._mark_dirty()

    def _get_preset_names(self):
        """Current preset names, parsed live from the Presets JSON field - used to populate every image row's Preset dropdown."""
        try:
            return sorted(json.loads(self.presetsEdit.plainText or "{}").keys())
        except Exception:
            return []

    def _refresh_all_preset_combos(self):
        """Re-populate every row's Preset dropdown when presets JSON changes,
        preserving each row's current selection if it's still a valid name."""
        if not hasattr(self, "imgTable"):
            return
        names = self._get_preset_names()
        for row in range(self.imgTable.rowCount):
            combo = self.imgTable.cellWidget(row, 8)
            if combo is None:
                continue
            current = combo.currentText
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            combo.addItems(names)
            if current and current not in names:
                combo.addItem(current)
            combo.currentText = current
            combo.blockSignals(False)

    def _summarize_advanced(self, adv):
        """One-line human summary of a row's advanced dict (window/level, threshold, interpolate), shown in the Advanced column and its tooltip."""
        if not adv:
            return ""
        parts = []
        wl = adv.get("window_level")
        if wl:
            if wl.get("auto"):
                parts.append("WL:auto")
            elif "window" in wl or "level" in wl:
                parts.append(f"WL:{wl.get('window','?')}/{wl.get('level','?')}(w/l)")
            else:
                parts.append(f"WL:{wl.get('min','?')}/{wl.get('max','?')}")
        th = adv.get("threshold")
        if th:
            parts.append(f"thr:{th.get('min','?')}-{th.get('max','?')}")
        if "interpolate" in adv:
            parts.append("interp:" + ("on" if adv["interpolate"] else "off"))
        return ", ".join(parts)

    def _update_advanced_indicator(self, row):
        """Refresh one row's Advanced-column summary text plus the highlight/tooltip on its Name cell, after that row's advanced dict changes."""
        nameItem = self.imgTable.item(row, 0)
        advItem = self.imgTable.item(row, 11)
        adv = self._image_advanced[row] if row < len(self._image_advanced) else {}
        summary = self._summarize_advanced(adv)
        if advItem:
            advItem.setText(summary)
        if nameItem:
            if adv:
                nameItem.setToolTip("Advanced: " + json.dumps(adv))
                nameItem.setBackground(qt.QColor(230, 245, 255))
            else:
                nameItem.setToolTip("")
                nameItem.setBackground(qt.QColor(255, 255, 255))

    def _onAddImage(self):
        """Add one blank image row and re-sync the Volume Rendering table's image list."""
        self._add_image_row({})
        if hasattr(self, "vrTable"):
            self._refresh_vr_table()

    def _onRemoveImage(self):
        """Remove the selected image row(s), keeping the parallel _image_advanced list in sync (same indices), then re-sync the Volume Rendering table's image list."""
        rows = sorted(set(i.row() for i in self.imgTable.selectedIndexes()), reverse=True)
        for r in rows:
            self.imgTable.removeRow(r)
            if 0 <= r < len(self._image_advanced):
                del self._image_advanced[r]
        self._mark_dirty()
        if hasattr(self, "vrTable"):
            self._refresh_vr_table()

    def _onEditImageAdvanced(self):
        """Open the structured window_level/threshold/interpolate popup for the selected row and apply the result."""
        row = self.imgTable.currentRow()
        if row < 0:
            qt.QMessageBox.information(self, "Config Editor", "Select an image row first.")
            return
        popup = _ImageAdvancedPopup(self, self._image_advanced[row])
        if popup.exec_():
            self._image_advanced[row] = popup.result_dict()
            self._update_advanced_indicator(row)
            self._refresh_image_preview(row)
            self._mark_dirty()

    # ---- Segmentation tab ----

    def _build_segmentation_tab(self):
        """Enabled/reference image/path pattern/output filename, plus the segments[] table."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)
        form = qt.QFormLayout()
        self.chkSegEnabled = qt.QCheckBox("Enabled")
        form.addRow(self.chkSegEnabled)
        self.segReferenceImageEdit = qt.QLineEdit()
        self.segReferenceImageEdit.setToolTip(
            "The 'name' of one of your images[] entries (Images tab) - used as the "
            "geometry reference for the segmentation, e.g. 'mask' or 't1'.")
        form.addRow("Reference image (name):", self.segReferenceImageEdit)
        self.segPathPatternEdit = qt.QLineEdit()
        self.segPathPatternEdit.setPlaceholderText("e.g. {ID}/{segment_name}.nii.gz - default naming for segments without their own path")
        self.segPathPatternEdit.setToolTip(
            "Only used as a FALLBACK: when a segment row (below) has Source=file but no csv_column "
            "and no path pattern of its own, this pattern builds that segment's file path instead. "
            "Segments with Source=empty never use this - they're always a blank, manually-drawn "
            "placeholder, no file involved.\n\n"
            "Placeholders in curly braces get replaced per specimen: any key column or database/"
            "preseg CSV column name (e.g. {ID}, {measurement}), plus {segment_name} - THIS segment "
            "row's own Name column.\n\n"
            "Worked example: pattern = {ID}/{measurement}/{ID}-{segment_name}.nii.gz. For specimen "
            "ID='D001', measurement='baseline', and a segment row named 'liver' with no csv_column "
            "-> resolves to study_dir/D001/baseline/D001-liver.nii.gz\n\n"
            "Leave this empty if every segment is Source=empty, or every segment already has its own "
            "csv_column set in the table below.")
        form.addRow("Path pattern (default):", self.segPathPatternEdit)
        self.segOutputFilenameEdit = qt.QLineEdit("segment.seg.nrrd")
        self.segOutputFilenameEdit.setToolTip("Filename (inside each specimen's output folder) the segmentation is saved to/loaded from.")
        form.addRow("Output filename:", self.segOutputFilenameEdit)
        layout.addLayout(form)

        self.segTable = qt.QTableWidget(0, 5)
        seg_headers = ["Name", "Source", "CSV column", "Path pattern", "Color"]
        seg_tips = [
            "Segment name as it appears in the segmentation.",
            "'file': try csv_column / path pattern, falling back to empty if unresolved. 'empty': never try a file - always a manual placeholder.",
            "preseg.csv column holding this segment's label image path (Source=file).",
            "Overrides the segmentation-level default path pattern for just this segment.",
            "Click 'Set color for selected...' below to pick.",
        ]
        self.segTable.setHorizontalHeaderLabels(seg_headers)
        for col, tip in enumerate(seg_tips):
            hitem = self.segTable.horizontalHeaderItem(col)
            if hitem:
                hitem.setToolTip(tip)
        self.segTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        layout.addWidget(self.segTable)

        btnRow = qt.QHBoxLayout()
        addBtn = qt.QPushButton("Add segment")
        addBtn.connect('clicked(bool)', lambda checked=False: self._onAddSegment())
        removeBtn = qt.QPushButton("Remove selected")
        removeBtn.connect('clicked(bool)', lambda checked=False: self._onRemoveSegment())
        colorBtn = qt.QPushButton("Set color for selected...")
        colorBtn.connect('clicked(bool)', lambda checked=False: self._onPickSegmentColor())
        btnRow.addWidget(addBtn)
        btnRow.addWidget(removeBtn)
        btnRow.addWidget(colorBtn)
        btnRow.addStretch(1)
        layout.addLayout(btnRow)

        return w

    def _add_segment_row(self, d):
        """Append one row to the segments table (name/source/csv_column/path_pattern) with its color swatch cell."""
        row = self.segTable.rowCount
        self.segTable.insertRow(row)
        self.segTable.setItem(row, 0, qt.QTableWidgetItem(d.get("name", f"segment_{row + 1}")))
        srcCombo = qt.QComboBox()
        srcCombo.addItems(SOURCE_CHOICES)
        srcCombo.currentText = d.get("source", "file")
        srcCombo.currentIndexChanged.connect(self._mark_dirty)
        self.segTable.setCellWidget(row, 1, srcCombo)
        self.segTable.setItem(row, 2, qt.QTableWidgetItem(d.get("csv_column", "")))
        self.segTable.setItem(row, 3, qt.QTableWidgetItem(d.get("path_pattern", "")))
        colorItem = qt.QTableWidgetItem(str(d.get("color", "")) or "")
        colorItem.setFlags(colorItem.flags() & ~qt.Qt.ItemIsEditable)
        self.segTable.setItem(row, 4, colorItem)
        color = d.get("color")
        self._segment_colors.insert(row, list(color) if color else list(DEFAULT_SEGMENT_COLOR))
        self._apply_segment_color_display(row)
        self._mark_dirty()

    def _apply_segment_color_display(self, row):
        """Paint a segment row's color cell from _segment_colors[row] and show the r,g,b values as its text too."""
        rgb = self._segment_colors[row]
        r, g, b = (int(round(c * 255)) for c in rgb)
        item = self.segTable.item(row, 4)
        item.setBackground(qt.QColor(r, g, b))
        item.setText(f"{rgb[0]:.2f},{rgb[1]:.2f},{rgb[2]:.2f}")

    def _onAddSegment(self):
        """Add one blank segment row."""
        self._add_segment_row({})

    def _onRemoveSegment(self):
        """Remove the selected segment row(s), keeping the parallel _segment_colors list in sync."""
        rows = sorted(set(i.row() for i in self.segTable.selectedIndexes()), reverse=True)
        for r in rows:
            self.segTable.removeRow(r)
            if 0 <= r < len(self._segment_colors):
                del self._segment_colors[r]
        self._mark_dirty()

    def _onPickSegmentColor(self):
        """Open a color picker for the selected segment row and apply the chosen color."""
        row = self.segTable.currentRow()
        if row < 0:
            qt.QMessageBox.information(self, "Config Editor", "Select a segment row first.")
            return
        rgb = self._segment_colors[row]
        current = qt.QColor(*(int(round(c * 255)) for c in rgb))
        color = qt.QColorDialog.getColor(current, self, "Pick segment color")
        if color.isValid():
            self._segment_colors[row] = [color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0]
            self._apply_segment_color_display(row)
            self._mark_dirty()

    # ---- Landmarks tab ----

    def _build_landmarks_tab(self):
        """Enabled/csv column/path pattern/template file/writable/color."""
        w = qt.QWidget()
        form = qt.QFormLayout(w)
        self.chkLmEnabled = qt.QCheckBox("Enabled")
        form.addRow(self.chkLmEnabled)
        self.lmCsvColumnEdit = qt.QLineEdit()
        self.lmCsvColumnEdit.setToolTip("preseg.csv column holding an existing markups file path for this specimen (optional - falls back to Path pattern).")
        form.addRow("CSV column:", self.lmCsvColumnEdit)
        self.lmPathPatternEdit = qt.QLineEdit()
        self.lmPathPatternEdit.setPlaceholderText("default: {label}-markups.mrk.json")
        self.lmPathPatternEdit.setToolTip("Fallback naming when CSV column is empty/unset. {label} = the specimen's key joined with '-', e.g. 'D001'.")
        form.addRow("Path pattern:", self.lmPathPatternEdit)
        self.lmTemplateEdit, lmTemplateRow = self._file_row(filter_="Markups (*.mrk.json *.json);;All files (*)")
        self.lmTemplateEdit.setToolTip("If a specimen has no markups file yet, load THIS file as the starting point (renamed to that specimen) instead of an empty fiducial list.")
        form.addRow("Template file (optional):", lmTemplateRow)
        self.chkLmWritable = qt.QCheckBox("Writable")
        self.chkLmWritable.checked = True
        form.addRow(self.chkLmWritable)
        self.lmColorEdit = qt.QLineEdit()
        self.lmColorEdit.setPlaceholderText("r,g,b (0-1), e.g. 1,1,0")
        form.addRow("Color:", self.lmColorEdit)
        return w

    # ---- Volume rendering tab ----

    def _build_vr_tab(self):
        """Hint text + the per-image Volume Rendering table (Image/Enable/Preset/Min/Max) + its manual Refresh button."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)
        hint = qt.QLabel(
            "One row per image from the Images tab. Check Enable to volume-render that image; "
            "any number can be enabled at once. Preset is a built-in Slicer VR preset name (editable - "
            "type your own if it's not in the list). Min/Max optionally rescale the preset's transfer "
            "function into that scalar range. Offset shifts it by a fixed amount instead, keeping its "
            "shape/spacing (like the 'Shift' slider) - if both Offset and Min/Max are set, Offset wins. "
            "Leave all three empty to use the preset as-is.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.vrTable = qt.QTableWidget(0, 6)
        vr_headers = ["Image", "Enable", "Preset", "Min", "Max", "Offset"]
        self.vrTable.setHorizontalHeaderLabels(vr_headers)
        vr_header = self.vrTable.horizontalHeader()
        vr_header.setSectionResizeMode(0, qt.QHeaderView.Stretch)             # Image - names can be long
        vr_header.setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)    # Enable - just a checkbox
        vr_header.setSectionResizeMode(2, qt.QHeaderView.Stretch)             # Preset - VR preset names are long (e.g. CT-Chest-Contrast-Enhanced)
        # Min/Max/Offset hold empty QLineEdits until typed into, so
        # ResizeToContents would shrink them to near-zero - give them a
        # fixed-but-resizable starting width instead.
        for col in (3, 4, 5):
            vr_header.setSectionResizeMode(col, qt.QHeaderView.Interactive)
            self.vrTable.setColumnWidth(col, 70)
        layout.addWidget(self.vrTable)

        refreshBtn = qt.QPushButton("Refresh image list from Images tab")
        refreshBtn.setToolTip("Re-syncs the rows above with the current Images tab (keeps existing Enable/Preset/Min/Max for images that still exist).")
        refreshBtn.connect('clicked(bool)', lambda checked=False: self._refresh_vr_table())
        layout.addWidget(refreshBtn)

        return w

    def _refresh_vr_table(self):
        """Rebuild the VR table from the current Images tab row names, keeping
        existing per-image settings (by name) for images that still exist."""
        existing = {}
        for row in range(self.vrTable.rowCount):
            name = self.vrTable.item(row, 0).text()
            enableItem = self.vrTable.item(row, 1)
            presetCombo = self.vrTable.cellWidget(row, 2)
            existing[name] = {
                "enabled": enableItem.checkState() == qt.Qt.Checked,
                "preset": presetCombo.currentText if presetCombo else "",
                "min": self.vrTable.item(row, 3).text(),
                "max": self.vrTable.item(row, 4).text(),
                "offset": self.vrTable.item(row, 5).text(),
            }

        image_names = []
        for row in range(self.imgTable.rowCount):
            n = self.imgTable.item(row, 0).text().strip()
            if n:
                image_names.append(n)

        self.vrTable.setRowCount(0)
        for name in image_names:
            prev = existing.get(name, {})
            row = self.vrTable.rowCount
            self.vrTable.insertRow(row)

            nameItem = qt.QTableWidgetItem(name)
            nameItem.setFlags(nameItem.flags() & ~qt.Qt.ItemIsEditable)
            self.vrTable.setItem(row, 0, nameItem)

            enableItem = qt.QTableWidgetItem()
            enableItem.setFlags(qt.Qt.ItemIsUserCheckable | qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable)
            enableItem.setCheckState(qt.Qt.Checked if prev.get("enabled") else qt.Qt.Unchecked)
            self.vrTable.setItem(row, 1, enableItem)

            presetCombo = qt.QComboBox()
            presetCombo.setEditable(True)
            presetCombo.addItems(VR_PRESET_CHOICES)
            wanted = prev.get("preset", "")
            if wanted and wanted not in VR_PRESET_CHOICES:
                presetCombo.addItem(wanted)
            presetCombo.currentText = wanted
            presetCombo.currentIndexChanged.connect(self._mark_dirty)
            self.vrTable.setCellWidget(row, 2, presetCombo)

            self.vrTable.setItem(row, 3, qt.QTableWidgetItem(prev.get("min", "")))
            self.vrTable.setItem(row, 4, qt.QTableWidgetItem(prev.get("max", "")))
            self.vrTable.setItem(row, 5, qt.QTableWidgetItem(prev.get("offset", "")))

        self._mark_dirty()

    def _read_vr_rows(self):
        """Read the VR table into a list of volume_rendering[] entries, skipping rows that are completely untouched (not enabled, no preset, no min/max) - so a study with 10 images and VR set up for just one doesn't write 9 empty entries."""
        entries = []
        for row in range(self.vrTable.rowCount):
            name = self.vrTable.item(row, 0).text().strip()
            if not name:
                continue
            enabled = self.vrTable.item(row, 1).checkState() == qt.Qt.Checked
            presetCombo = self.vrTable.cellWidget(row, 2)
            preset = (presetCombo.currentText or "").strip() if presetCombo else ""
            mn = _f(self.vrTable.item(row, 3).text())
            mx = _f(self.vrTable.item(row, 4).text())
            offset = _f(self.vrTable.item(row, 5).text())
            if not enabled and not preset and mn is None and mx is None and offset is None:
                continue  # untouched row, nothing worth writing
            entry = {"image": name, "enabled": enabled}
            if preset:
                entry["preset"] = preset
            if offset is not None:
                entry["offset"] = offset
            if mn is not None or mx is not None:
                entry["window_level"] = {k: v for k, v in (("min", mn), ("max", mx)) if v is not None}
            entries.append(entry)
        return entries

    # ---- Workspace tab (window/level + slice rotation + crosshair/ruler/orientation marker) ----

    def _build_workspace_tab(self):
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
        wlForm.addRow("Min:", self.wlMinEdit)
        self.wlMaxEdit = qt.QLineEdit()
        self.wlMaxEdit.setToolTip("Upper display value, e.g. 700 for a typical CT soft-tissue window.")
        wlForm.addRow("Max:", self.wlMaxEdit)
        layout.addWidget(wlGroup)

        rotGroup = qt.QGroupBox("Slice rotation (in-plane, degrees)")
        rotForm = qt.QFormLayout(rotGroup)
        self.chkSliceRotationEnabled = qt.QCheckBox("Enabled")
        self.chkSliceRotationEnabled.setToolTip(
            "Rotates Red/Yellow/Green in-plane (around each view's own normal) once a specimen loads - "
            "identical to the Reformat module's rotation slider. Leave a view's field empty to leave it alone.")
        rotForm.addRow(self.chkSliceRotationEnabled)
        self.sliceRotRedEdit = qt.QLineEdit()
        self.sliceRotRedEdit.setPlaceholderText("degrees, e.g. 180")
        rotForm.addRow("Red:", self.sliceRotRedEdit)
        self.sliceRotYellowEdit = qt.QLineEdit()
        self.sliceRotYellowEdit.setPlaceholderText("degrees, e.g. -90")
        rotForm.addRow("Yellow:", self.sliceRotYellowEdit)
        self.sliceRotGreenEdit = qt.QLineEdit()
        self.sliceRotGreenEdit.setPlaceholderText("degrees, e.g. -90")
        rotForm.addRow("Green:", self.sliceRotGreenEdit)
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
        conventionLayout.addWidget(self.radioRadiological)
        conventionLayout.addWidget(self.radioNeurological)
        layout.addWidget(conventionGroup)

        return w

    # ---- Segment editor tab ----

    def _build_segment_editor_tab(self):
        """Overwrite mode/brush shape+size+unit/active effect/raw attributes escape hatch."""
        w = qt.QWidget()
        form = qt.QFormLayout(w)
        self.overwriteModeCombo = qt.QComboBox()
        self.overwriteModeCombo.addItems(OVERWRITE_CHOICES)
        self.overwriteModeCombo.setToolTip("'none' = the Segment Editor's 'Allow overlap' checkbox is ON. 'all_segments'/'visible_segments' restrict painting to not overwrite other segments.")
        form.addRow("Overwrite mode:", self.overwriteModeCombo)
        self.brushShapeCombo = qt.QComboBox()
        self.brushShapeCombo.addItems(BRUSH_SHAPE_CHOICES)
        self.brushShapeCombo.setToolTip("sphere = 3D brush (also paints in the 3D view). circle = Slicer's normal 2D slice brush.")
        form.addRow("Brush shape:", self.brushShapeCombo)
        self.brushDiameterEdit = qt.QLineEdit()
        self.brushDiameterEdit.setToolTip("Fixed brush size - in mm if 'Use absolute size' below is checked, in % of the slice view otherwise.")
        form.addRow("Brush diameter (mm or %):", self.brushDiameterEdit)
        self.chkBrushAbsolute = qt.QCheckBox("Use absolute size (mm)")
        self.chkBrushAbsolute.setToolTip("Checked: fixed size in millimeters, regardless of zoom. Unchecked: size as a percentage of the slice view instead.")
        self.chkBrushAbsolute.checked = True
        form.addRow(self.chkBrushAbsolute)
        self.activeEffectEdit = qt.QLineEdit()
        self.activeEffectEdit.setPlaceholderText("e.g. Paint")
        self.activeEffectEdit.setToolTip("Pre-select this effect whenever a live/default Segment Editor node picks up these settings (best-effort, not forced).")
        form.addRow("Active effect on load:", self.activeEffectEdit)
        self.seAttributesEdit = qt.QPlainTextEdit()
        self.seAttributesEdit.setPlaceholderText('{"BrushSphere": "1"}')
        self.seAttributesEdit.setMaximumHeight(100)
        self.seAttributesEdit.setToolTip(
            "Escape hatch: raw attribute-name -> value pairs, applied last (overrides overwrite_mode/"
            "brush above). Brush params (BrushSphere, BrushAbsoluteDiameter, BrushRelativeDiameter, "
            "BrushDiameterIsRelative) are COMMON parameters with NO effect-name prefix - just the bare "
            "name, e.g. \"BrushSphere\": \"1\" (NOT \"Paint,BrushSphere\"). Only effect-SPECIFIC settings "
            "use an \"EffectName.ParamName\" form, e.g. \"Paint.ColorSmudge\".")
        form.addRow("Raw attributes (JSON):", self.seAttributesEdit)
        return w

    # ---- Defaults / Presets tab ----

    def _build_advanced_tab(self):
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
        self.defaultsImageEdit.textChanged.connect(self._refresh_preview_if_selected)
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
            {name: self._load_example_presets()[name]["preset"]
             for name in ("ct_soft_tissue", "ct_bone") if name in self._load_example_presets()}, indent=2)
        self.presetsEdit.setToolTip(
            "Named, reusable bags of image visual properties. Reference one by name in an "
            "image row's 'Preset' column (Images tab) - merge order is defaults.image -> "
            "this preset -> the image row's own inline values.")
        self.presetsEdit.setMinimumHeight(120)
        presetsForm.addRow("presets (JSON):", self.presetsEdit)
        self.presetsEdit.textChanged.connect(self._refresh_preview_if_selected)
        self.presetsEdit.textChanged.connect(self._refresh_all_preset_combos)
        examplesBtn = qt.QPushButton("Show example presets (copyable)...")
        examplesBtn.setToolTip("Opens a read-only, copyable list of ready-made presets you can paste in above and tweak.")
        examplesBtn.connect('clicked(bool)', lambda checked=False: self._onShowExamplePresets())
        presetsForm.addRow(examplesBtn)

        return w

    def _onBeEnabledToggled(self, checked):
        """Gray out (or restore) every Batch export child widget below the master Enabled checkbox - values are left untouched, just not editable/usable while disabled."""
        for w in getattr(self, "_beChildWidgets", []):
            w.enabled = checked

    def _onInsertAllSegmentsFilter(self):
        """Fill Segments filter with every non-empty Name in the Segmentation tab's segments table."""
        names = []
        for row in range(self.segTable.rowCount):
            item = self.segTable.item(row, 0)
            name = (item.text().strip() if item else "")
            if name:
                names.append(name)
        self.beSegmentsFilterEdit.text = ",".join(names)

    def _get_image_names(self):
        """Every non-empty Name in the Images tab table (pattern-mode rows, which have no fixed literal name, are skipped)."""
        names = []
        for row in range(self.imgTable.rowCount):
            item = self.imgTable.item(row, 0)
            name = (item.text().strip() if item else "")
            if name:
                names.append(name)
        return names

    def _onUseAllImagesForStats(self):
        """Fill Stats reference image(s) with every image name from the Images tab."""
        self.statsReferenceImagesEdit.text = ",".join(self._get_image_names())

    def _onSuggestReferenceImage(self):
        """Populate the Reference image combo with every image name from the Images tab, so the user can just pick one instead of typing it."""
        names = self._get_image_names()
        current = self.beReferenceImageEdit.currentText
        self.beReferenceImageEdit.clear()
        self.beReferenceImageEdit.addItems(names)
        self.beReferenceImageEdit.currentText = current or (names[0] if names else "")

    def _onInsertDefaultStatsMetrics(self):
        """Fill the batch-export stats Metrics field with the same default (Definitions.DEFAULT_STATS_METRICS) that's used automatically when the field is left empty - just makes it visible/editable."""
        self.statsMetricsEdit.text = ",".join(DEFAULT_STATS_METRICS)

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
        self._mark_dirty()

    # ---- Manual edit config tab ----

    def _build_manual_tab(self):
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
        """Regenerate the JSON preview from the current form state (via _build_config())."""
        try:
            cfg = self._build_config()
        except Exception:
            return  # _build_config already showed a JSON error from a field, if any
        self.manualEditor.plainText = json.dumps(cfg, indent=2, ensure_ascii=False)

    def _onApplyManualEdit(self):
        """Parse the hand-edited JSON in the box and push it back into every other tab via _populate_form()."""
        text = self.manualEditor.plainText.strip()
        if not text:
            qt.QMessageBox.information(self, "Config Editor", "Nothing to apply - the box is empty.")
            return
        try:
            cfg = json.loads(text)
        except Exception as e:
            qt.QMessageBox.critical(self, "Config Editor", f"Invalid JSON: {e}")
            return
        self._populate_form(cfg)
        self._mark_dirty()
        qt.QMessageBox.information(self, "Config Editor", "Applied to the other tabs.")

    # ---- example presets / help ----

    def _preset_resource_dir(self):
        """Absolute path to Resources/Presets, where the Config Editor's bundled preset catalogue lives - same idea as _html_resource_dir(), kept as its own method so both resource kinds are equally easy to find/extend."""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Presets")

    def _load_example_presets(self):
        """Read Resources/Presets/example_presets.json (name -> {description, preset}), cached after the first read. Returns {} on any error (missing/invalid file) instead of crashing - callers just see an empty catalogue."""
        cache = getattr(self, "_example_presets_cache", None)
        if cache is not None:
            return cache
        path = os.path.join(self._preset_resource_dir(), "example_presets.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"[ConfigEditor] could not load example_presets.json: {e}")
            data = {}
        data.pop("_comment", None)
        self._example_presets_cache = data
        return data

    def _html_resource_dir(self):
        """Absolute path to Resources/Html, where the Config Editor's bundled HTML content lives (kept out of the .py file so it's easy to read/edit on its own)."""
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Html")

    def _load_html_resource(self, filename):
        """Read one bundled HTML resource file (Resources/Html/<filename>) as text, or a short inline error message if it can't be read."""
        path = os.path.join(self._html_resource_dir(), filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"<p>Could not load {filename}: {e}</p>"

    def _onShowHelp(self):
        """Open the HTML cheat-sheet (Resources/Html/help_cheatsheet.html) in a read-only, scrollable, copyable QTextBrowser popup."""
        popup = qt.QDialog(self)
        popup.setWindowTitle("Config Editor - Cheat Sheet")
        popup.resize(700, 620)
        layout = qt.QVBoxLayout(popup)
        browser = qt.QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(self._load_html_resource("help_cheatsheet.html"))
        layout.addWidget(browser)
        closeBtn = qt.QPushButton("Close")
        closeBtn.connect('clicked(bool)', lambda checked=False: popup.close())
        layout.addWidget(closeBtn)
        popup.exec_()

    def _build_example_presets_html(self):
        """Render the example-presets catalogue (Resources/Presets/example_presets.json) as copyable HTML cards (name, one-line description, the preset's own JSON block), inserted into the static wrapper/style loaded from Resources/Html/example_presets_template.html."""
        rows = []
        for name, entry in self._load_example_presets().items():
            desc = entry.get("description", "")
            preset = entry.get("preset", {})
            rows.append(
                f'<h3>{name}</h3>'
                f'<p class="desc">{desc}</p>'
                f'<pre>{json.dumps({name: preset}, indent=2)}</pre>')
        template = self._load_html_resource("example_presets_template.html")
        return template.replace("{{CONTENT}}", "".join(rows))

    def _onShowExamplePresets(self):
        """Show the example-presets catalogue, with a button to merge all of them into the Presets field at once."""
        popup = qt.QDialog(self)
        popup.setWindowTitle("Example presets")
        popup.resize(560, 620)
        layout = qt.QVBoxLayout(popup)
        browser = qt.QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(self._build_example_presets_html())
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
        current.update({name: entry["preset"] for name, entry in self._load_example_presets().items()})
        self.presetsEdit.plainText = json.dumps(current, indent=2)
        self._mark_dirty()
        popup.close()

    def _confirm_discard(self):
        """If the form is dirty, ask Save/Discard/Cancel and act accordingly; returns True iff it's safe to proceed (saved or discarded), False iff the caller should abort. 'Save' here routes through the real, validated _onSave() - not just clearing the dirty flag."""
        if not self._dirty:
            return True
        ret = qt.QMessageBox.question(
            self, "Config Editor", "Save changes to the current config first?",
            qt.QMessageBox.Save | qt.QMessageBox.Discard | qt.QMessageBox.Cancel)
        if ret == qt.QMessageBox.Cancel:
            return False
        if ret == qt.QMessageBox.Save:
            return self._onSave()
        return True

    def _clear_form(self):
        """Reset every field to its blank/default state (including two starter presets, not a truly empty Presets box) - used by New and as the first step of loading any config."""
        self._preseg_abs_path = ""
        self.quickColumnsTable.setRowCount(0)
        self.vrTable.setRowCount(0)
        for edit in (self.presegEdit, self.dbEdit, self.studyDirEdit, self.keyColumnsEdit,
                     self.tableColumnsEdit, self.outputDirPatternEdit, self.batchColumnEdit,
                     self.segReferenceImageEdit, self.segPathPatternEdit,
                     self.lmCsvColumnEdit, self.lmPathPatternEdit, self.lmTemplateEdit, self.lmColorEdit,
                     self.wlMinEdit, self.wlMaxEdit,
                     self.sliceRotRedEdit, self.sliceRotYellowEdit, self.sliceRotGreenEdit,
                     self.beSegmentsFilterEdit, self.beOutputDirEdit,
                     self.statsReferenceImagesEdit, self.statsMetricsEdit, self.statsOutputPathEdit,
                     self.brushDiameterEdit, self.activeEffectEdit):
            edit.text = ""
        self.beReferenceImageEdit.clear()
        self.doneColumnEdit.text = "done"
        self.segOutputFilenameEdit.text = "segment.seg.nrrd"
        for chk in (self.chkBatchMode, self.chkSegEnabled, self.chkLmEnabled,
                    self.chkWlEnabled, self.chkSliceRotationEnabled, self.chkBeEnabled, self.chkBeExportSegments,
                    self.chkBeExportMarkups, self.chkBePerBatchOperation, self.chkBeComputeStats):
            chk.checked = False
        self._onBeEnabledToggled(False)
        self.chkLmWritable.checked = True
        self.chkBrushAbsolute.checked = True
        self.radioRadiological.setChecked(True)
        self.overwriteModeCombo.currentText = "none"
        self.brushShapeCombo.currentText = "(unset)"
        for combo in (self.crosshairModeCombo, self.crosshairBehaviorCombo, self.crosshairThicknessCombo,
                      self.rulerTypeCombo, self.orientationMarkerTypeCombo, self.orientationMarkerSizeCombo,
                      self.orientationMarker2dTypeCombo, self.orientationMarker2dSizeCombo):
            combo.currentText = "(unset)"
        self.seAttributesEdit.plainText = ""
        self.defaultsImageEdit.plainText = ""
        self.defaultsSegmentEdit.plainText = ""
        self.presetsEdit.plainText = json.dumps(
            {name: self._load_example_presets()[name]["preset"]
             for name in ("ct_soft_tissue", "ct_bone") if name in self._load_example_presets()}, indent=2)
        self.imgTable.setRowCount(0)
        self._image_advanced = []
        self.segTable.setRowCount(0)
        self._segment_colors = []

    def _onNew(self):
        """Start a blank config, after confirming it's OK to discard any unsaved changes."""
        if not self._confirm_discard():
            return
        self._clear_form()
        self._current_path = None
        self.outputEdit.text = ""
        self._dirty = False
        self._updateTitle()

    def _onLoadFromFile(self):
        """Browse for a config.json to load, after confirming it's OK to discard any unsaved changes."""
        if not self._confirm_discard():
            return
        fname = qt.QFileDialog.getOpenFileName(self, "Load config", "", "JSON files (*.json)")
        if fname:
            self._load_from_file(fname)

    def _onReload(self):
        """Re-read the currently open file from disk, without browsing - e.g. after it was edited outside this dialog. No-op with a friendly message if nothing's open yet."""
        if not self._current_path:
            qt.QMessageBox.information(self, "Config Editor", "Nothing to reload - no file is currently open (use 'Load from file...' first).")
            return
        if not self._confirm_discard():
            return
        self._load_from_file(self._current_path, ask_confirm=False)

    def _load_from_file(self, path, ask_confirm=True):
        """Read+parse a config.json from disk and populate the whole form from it."""
        if ask_confirm and not self._confirm_discard():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            qt.QMessageBox.critical(self, "Config Editor", f"Failed to load: {e}")
            return
        self._populate_form(cfg)
        self._current_path = path
        self.outputEdit.text = path
        self._dirty = False
        self._updateTitle()

    # ---- populate from dict ----

    def _populate_form(self, cfg):
        """Fill every tab from a raw config dict, in an order that respects cross-tab dependencies - notably, presets/defaults are loaded BEFORE the images loop, so each row's Preset dropdown already has the right choices the moment it's created (see the comment inline)."""
        self._clear_form()

        self.presegEdit.text = cfg.get("preseg_csv_path", "")
        self.dbEdit.text = cfg.get("database_csv_path", "")
        self.studyDirEdit.text = cfg.get("study_dir", "")
        self.keyColumnsEdit.text = ",".join(cfg.get("key_columns", []))
        preseg_val = self.presegEdit.text.strip()
        if preseg_val:
            self._preseg_abs_path = preseg_val if os.path.isabs(preseg_val) else os.path.join(self.studyDirEdit.text.strip() or ".", preseg_val)
            # Setting .text programmatically does NOT fire editingFinished/the
            # Browse-picked callback - without this explicit call, the
            # quick-add column list (and key-column guessing) never runs when
            # a config is loaded (only when the user browses/types by hand),
            # leaving the Images tab's checklist empty after Load/on open.
            # key_columns is set above FIRST so it's already excluded from
            # the quick-add list this call builds.
            self._onPresegChanged(self._preseg_abs_path)
        self.doneColumnEdit.text = cfg.get("done_column", "done")
        self.tableColumnsEdit.text = ",".join(cfg.get("table_columns", []))
        self.outputDirPatternEdit.text = cfg.get("output_dir_pattern", "") or ""

        bm = cfg.get("batch_mode", {}) or {}
        self.chkBatchMode.checked = bool(bm.get("enabled"))
        self.batchColumnEdit.text = bm.get("column", "") or ""

        # defaults/presets loaded BEFORE the images loop below, so each row's
        # Preset dropdown is populated with the right choices as it's created
        # (rather than showing an empty list until something else refreshes it).
        defaults = cfg.get("defaults", {}) or {}
        if defaults.get("image"):
            self.defaultsImageEdit.plainText = json.dumps(defaults["image"], indent=2)
        if defaults.get("segment"):
            self.defaultsSegmentEdit.plainText = json.dumps(defaults["segment"], indent=2)
        if cfg.get("presets"):
            self.presetsEdit.plainText = json.dumps(cfg["presets"], indent=2)

        for img in cfg.get("images", []):
            self._add_image_row(img)

        seg = cfg.get("segmentation", {}) or {}
        self.chkSegEnabled.checked = bool(seg.get("enabled"))
        self.segReferenceImageEdit.text = seg.get("reference_image", "") or ""
        self.segPathPatternEdit.text = seg.get("path_pattern", "") or ""
        self.segOutputFilenameEdit.text = seg.get("output_filename", "segment.seg.nrrd")
        for s in seg.get("segments", []):
            self._add_segment_row(s)

        lm = cfg.get("landmarks", {}) or {}
        self.chkLmEnabled.checked = bool(lm.get("enabled"))
        self.lmCsvColumnEdit.text = lm.get("csv_column", "") or ""
        self.lmPathPatternEdit.text = lm.get("path_pattern", "") or ""
        self.lmTemplateEdit.text = lm.get("template_path", "") or ""
        self.chkLmWritable.checked = lm.get("writable", True)
        if lm.get("color"):
            self.lmColorEdit.text = ",".join(str(c) for c in lm["color"])

        self._refresh_vr_table()
        vr_by_image = {}
        for e in (cfg.get("volume_rendering") or []):
            if isinstance(e, dict) and e.get("image"):
                vr_by_image[e["image"]] = e
        for row in range(self.vrTable.rowCount):
            name = self.vrTable.item(row, 0).text()
            entry = vr_by_image.get(name)
            if not entry:
                continue
            self.vrTable.item(row, 1).setCheckState(qt.Qt.Checked if entry.get("enabled") else qt.Qt.Unchecked)
            preset = entry.get("preset", "") or ""
            presetCombo = self.vrTable.cellWidget(row, 2)
            if preset and preset not in VR_PRESET_CHOICES:
                presetCombo.addItem(preset)
            presetCombo.currentText = preset
            wl = entry.get("window_level") or {}
            self.vrTable.item(row, 3).setText("" if wl.get("min") is None else str(wl["min"]))
            self.vrTable.item(row, 4).setText("" if wl.get("max") is None else str(wl["max"]))
            self.vrTable.item(row, 5).setText("" if entry.get("offset") is None else str(entry["offset"]))

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
        self.radioRadiological.setChecked(ws.get("view_convention") != "neurological")

        be = cfg.get("batch_export", {}) or {}
        self.chkBeEnabled.checked = bool(be.get("enabled"))
        self._onBeEnabledToggled(self.chkBeEnabled.checked)
        self.chkBeExportSegments.checked = bool(be.get("export_segments"))
        self.chkBeExportMarkups.checked = bool(be.get("export_markups"))
        self.beReferenceImageEdit.currentText = be.get("reference_image", "") or ""
        self.beSegmentsFilterEdit.text = ",".join(be.get("segments_filter") or [])
        self.beOutputDirEdit.text = be.get("output_dir", "") or ""
        self.chkBePerBatchOperation.checked = bool(be.get("per_batch_operation"))
        self.chkBeComputeStats.checked = bool(be.get("compute_stats"))
        self.statsReferenceImagesEdit.text = ",".join(be.get("stats_reference_images") or [])
        self.statsMetricsEdit.text = ",".join(be.get("stats_metrics") or [])
        self.statsOutputPathEdit.text = be.get("stats_output_path", "") or ""

        se = cfg.get("segment_editor", {}) or {}
        self.overwriteModeCombo.currentText = se.get("overwrite_mode", "none") or "none"
        brush = se.get("brush") or {}
        self.brushShapeCombo.currentText = brush.get("shape") or "(unset)"
        self.brushDiameterEdit.text = "" if brush.get("diameter_mm") is None else str(brush["diameter_mm"])
        self.chkBrushAbsolute.checked = not bool(brush.get("relative"))
        self.activeEffectEdit.text = se.get("active_effect", "") or ""
        if se.get("attributes"):
            self.seAttributesEdit.plainText = json.dumps(se["attributes"], indent=2)

    # ---- build config dict ----

    def _read_image_row(self, row):
        """Return the raw (unmerged) dict for one image row, or None if it has no name."""
        d = {}
        name = self.imgTable.item(row, 0).text().strip()
        if not name:
            return None
        d["name"] = name
        for col, key in ((1, "csv_column"), (2, "pattern"), (3, "strip_prefix"), (4, "strip_suffix")):
            val = self.imgTable.item(row, col).text().strip()
            if val:
                d[key] = val
        d["type"] = self.imgTable.cellWidget(row, 5).currentText
        role = self.imgTable.cellWidget(row, 6).currentText
        if role != "(none)":
            d["role"] = role
        if self.imgTable.item(row, 7).checkState() == qt.Qt.Checked:
            d["required"] = True
        preset = (self.imgTable.cellWidget(row, 8).currentText or "").strip()
        if preset:
            d["preset"] = preset
        opacity = _f(self.imgTable.item(row, 9).text())
        if opacity is not None:
            d["opacity"] = opacity
        color_table = (self.imgTable.cellWidget(row, 10).currentText or "").strip()
        if color_table:
            d["color_table"] = color_table
        if row < len(self._image_advanced):
            d.update(self._image_advanced[row])
        return d

    def _read_image_rows(self):
        """Read every named image row into the final images[] list (via _read_image_row per row)."""
        images = []
        for row in range(self.imgTable.rowCount):
            d = self._read_image_row(row)
            if d is not None:
                images.append(d)
        return images

    def _read_segment_rows(self):
        """Read every named segment row into the final segmentation.segments[] list."""
        segments = []
        for row in range(self.segTable.rowCount):
            name = self.segTable.item(row, 0).text().strip()
            if not name:
                continue
            d = {"name": name, "source": self.segTable.cellWidget(row, 1).currentText}
            csv_col = self.segTable.item(row, 2).text().strip()
            if csv_col:
                d["csv_column"] = csv_col
            pattern = self.segTable.item(row, 3).text().strip()
            if pattern:
                d["path_pattern"] = pattern
            if row < len(self._segment_colors):
                d["color"] = [round(c, 3) for c in self._segment_colors[row]]
            segments.append(d)
        return segments

    def _parse_json_field(self, edit, label):
        """Parse a JSON textarea's contents, showing a friendly popup (and re-raising) if it's invalid - callers catch the exception to abort the save/build cleanly without a half-built config."""
        text = (edit.plainText or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception as e:
            qt.QMessageBox.critical(self, "Config Editor", f"Invalid JSON in '{label}': {e}")
            raise

    def _build_config(self):
        """Assemble the full config dict from every tab's current state - the single source of truth for what 'Save config' actually writes to disk."""
        cfg = {
            "study_dir": self.studyDirEdit.text.strip() or os.path.dirname(self.presegEdit.text.strip()) or ".",
            "database_csv_path": self.dbEdit.text.strip(),
            "preseg_csv_path": self.presegEdit.text.strip(),
            "key_columns": _csv_list(self.keyColumnsEdit.text) or ["ID"],
            "done_column": self.doneColumnEdit.text.strip() or "done",
        }
        table_cols = _csv_list(self.tableColumnsEdit.text)
        cfg["table_columns"] = table_cols or (cfg["key_columns"] + [cfg["done_column"]])
        out_pattern = self.outputDirPatternEdit.text.strip()
        if out_pattern:
            cfg["output_dir_pattern"] = out_pattern

        if self.chkBatchMode.checked:
            cfg["batch_mode"] = {"enabled": True, "column": self.batchColumnEdit.text.strip()}

        images = self._read_image_rows()
        if images:
            cfg["images"] = images

        seg_enabled = self.chkSegEnabled.checked
        segments = self._read_segment_rows()
        if seg_enabled or segments:
            seg = {"enabled": seg_enabled}
            if self.segReferenceImageEdit.text.strip():
                seg["reference_image"] = self.segReferenceImageEdit.text.strip()
            if self.segPathPatternEdit.text.strip():
                seg["path_pattern"] = self.segPathPatternEdit.text.strip()
            seg["output_filename"] = self.segOutputFilenameEdit.text.strip() or "segment.seg.nrrd"
            seg["segments"] = segments
            cfg["segmentation"] = seg

        if self.chkLmEnabled.checked:
            lm = {"enabled": True, "writable": self.chkLmWritable.checked}
            if self.lmCsvColumnEdit.text.strip():
                lm["csv_column"] = self.lmCsvColumnEdit.text.strip()
            if self.lmPathPatternEdit.text.strip():
                lm["path_pattern"] = self.lmPathPatternEdit.text.strip()
            if self.lmTemplateEdit.text.strip():
                lm["template_path"] = self.lmTemplateEdit.text.strip()
            if self.lmColorEdit.text.strip():
                lm["color"] = [_f(c) for c in self.lmColorEdit.text.split(",")]
            cfg["landmarks"] = lm

        vr_entries = self._read_vr_rows()
        if vr_entries:
            cfg["volume_rendering"] = vr_entries

        if self.chkWlEnabled.checked:
            wl = {"enabled": True}
            mn, mx = _f(self.wlMinEdit.text), _f(self.wlMaxEdit.text)
            if mn is not None:
                wl["min"] = mn
            if mx is not None:
                wl["max"] = mx
            cfg["window_level"] = wl

        if self.chkSliceRotationEnabled.checked:
            rot = {"enabled": True}
            red, yellow, green = _f(self.sliceRotRedEdit.text), _f(self.sliceRotYellowEdit.text), _f(self.sliceRotGreenEdit.text)
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

        if ws:
            cfg["workspace"] = ws

        if self.chkBeEnabled.checked:
            be = {
                "enabled": True,
                "export_segments": self.chkBeExportSegments.checked,
                "export_markups": self.chkBeExportMarkups.checked,
                "per_batch_operation": self.chkBePerBatchOperation.checked,
                "compute_stats": self.chkBeComputeStats.checked,
            }
            if self.beReferenceImageEdit.currentText.strip():
                be["reference_image"] = self.beReferenceImageEdit.currentText.strip()
            filt = _csv_list(self.beSegmentsFilterEdit.text)
            if filt:
                be["segments_filter"] = filt
            if self.beOutputDirEdit.text.strip():
                be["output_dir"] = self.beOutputDirEdit.text.strip()
            filt = _csv_list(self.statsReferenceImagesEdit.text)
            if filt:
                be["stats_reference_images"] = filt
            metrics_text = self.statsMetricsEdit.text.strip()
            if metrics_text:
                metrics = []
                for m in _csv_list(metrics_text):
                    if m.replace(".", "", 1).isdigit():
                        qt.QMessageBox.critical(
                            self, "Config Editor",
                            f"Stats metric '{m}' looks like a bare number - did you mean 'percentile_{m}'?")
                        raise ValueError(f"invalid stats metric: {m}")
                    metrics.append(m)
                be["stats_metrics"] = metrics
            if self.statsOutputPathEdit.text.strip():
                be["stats_output_path"] = self.statsOutputPathEdit.text.strip()
            cfg["batch_export"] = be

        overwrite = self.overwriteModeCombo.currentText
        brush_shape = self.brushShapeCombo.currentText
        diameter = _f(self.brushDiameterEdit.text)
        active_effect = self.activeEffectEdit.text.strip()
        se_attrs = self._parse_json_field(self.seAttributesEdit, "segment_editor attributes") or {}
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

        defaults = {}
        di = self._parse_json_field(self.defaultsImageEdit, "defaults.image")
        if di:
            defaults["image"] = di
        ds = self._parse_json_field(self.defaultsSegmentEdit, "defaults.segment")
        if ds:
            defaults["segment"] = ds
        if defaults:
            cfg["defaults"] = defaults

        presets = self._parse_json_field(self.presetsEdit, "presets")
        if presets:
            cfg["presets"] = presets

        return cfg

    def _onSave(self):
        """Validate + build + write the config.json, prompting for an output path first if none is set yet. Returns True on success, False on any failure (invalid JSON field, no preseg CSV, write error, ...) so callers (e.g. _confirm_discard) know whether it's safe to proceed."""
        if not self.presegEdit.text.strip():
            qt.QMessageBox.warning(self, "Config Editor", "Select an images/preseg CSV first.")
            return False
        if not self.outputEdit.text.strip():
            fname = qt.QFileDialog.getSaveFileName(self, "Save config as", self._current_path or "config.json", "JSON files (*.json)")
            if not fname:
                return False
            self.outputEdit.text = fname

        try:
            cfg = self._build_config()
        except Exception:
            return False   # _parse_json_field already showed the error

        out_path = self.outputEdit.text.strip()
        try:
            out_dir = os.path.dirname(out_path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception as e:
            qt.QMessageBox.critical(self, "Config Editor", f"Failed to save: {e}")
            return False

        self._current_path = out_path
        self._dirty = False
        self._updateTitle()

        if self._on_saved:
            ret = qt.QMessageBox.question(
                self, "Config Editor",
                f"Saved: {out_path}\n\nReload this config in the active module now?",
                qt.QMessageBox.Yes | qt.QMessageBox.No)
            if ret == qt.QMessageBox.Yes:
                try:
                    self._on_saved(out_path)
                except Exception as e:
                    qt.QMessageBox.critical(self, "Config Editor", f"Saved, but reload failed: {e}")
        else:
            qt.QMessageBox.information(self, "Config Editor", f"Saved: {out_path}")
        return True

    def closeEvent(self, event):
        """Ask to save unsaved changes before actually closing. Defensively wrapped: any failure in that check still lets the window close rather than leaving it stuck open (see the inline comment for why that mattered in practice)."""
        try:
            if self._dirty and not self._confirm_discard():
                event.ignore()
                return
        except Exception as e:
            logger.warning(f"[ConfigEditor] closeEvent check failed, closing anyway: {e}")
        event.accept()
