"""
dialog.py
=========
ConfigEditorDialog: the standalone window for building/editing a study config.json. Each tab's behaviour (build, populate,
collect, clear) lives in its own tab mixin in this folder; this class ties them together (load / save / dirty tracking).
"""

import json
import os

import qt

from Resources.core import safe_io
from Resources.core.logging_setup import logger
from Resources.gui.config_editor.batch_export_tab import BatchExportTabMixin
from Resources.gui.config_editor.defaults_tab import DefaultsTabMixin
from Resources.gui.config_editor.general_tab import GeneralTabMixin
from Resources.gui.config_editor.images_tab import ImagesTabMixin
from Resources.gui.config_editor.manual_tab import ManualTabMixin
from Resources.gui.config_editor.markups_tab import MarkupsTabMixin
from Resources.gui.config_editor.segment_editor_tab import SegmentEditorTabMixin
from Resources.gui.config_editor.segmentation_tab import SegmentationTabMixin
from Resources.gui.config_editor.volume_rendering_tab import VolumeRenderingTabMixin
from Resources.gui.config_editor.workspace_tab import WorkspaceTabMixin
from Resources.gui.help_dialog import show_cheatsheet_dialog
from Resources.utils.config_location import default_config_dir, remember_config_path


CONFIG_EDITOR_HELP_SECTIONS = [
    ("Workflow", "workflow"), ("General", "general"), ("Batch export", "batch-export"),
    ("Images", "images"), ("Segmentation", "segmentation"), ("Markups", "markups"),
    ("Workspace", "workspace"), ("Segment editor", "segment-editor"),
    ("Volume rendering", "volume-rendering"), ("Defaults / Presets", "defaults-presets"),
    ("Manual edit config", "manual-edit-config"), ("Key reference", "key-reference"),
]


class ConfigEditorDialog(qt.QDialog, GeneralTabMixin, BatchExportTabMixin, ImagesTabMixin, SegmentationTabMixin,
                         MarkupsTabMixin, VolumeRenderingTabMixin, WorkspaceTabMixin, SegmentEditorTabMixin,
                         DefaultsTabMixin, ManualTabMixin):
    """Standalone, non-modal window for building/editing a study config.json without hand-editing JSON. Opens pre-loaded with whatever config is active in the main module (if any); New/Load both confirm before discarding unsaved changes."""
    def __init__(self, parent=None, initial_path=None, on_saved=None):
        """Build the whole dialog and, if initial_path is given, load that config immediately (skipping the discard-changes prompt, since there's nothing to discard yet). on_saved, if given, is called as on_saved(path) after every successful Save - the main module passes its own "load this config into the active scene" logic here, so Save can offer to push the change live instead of requiring a manual re-browse there."""
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle("Config Editor")
        self.resize(1200, 720)

        self._current_path = None
        self._preseg_abs_path = ""    # true absolute preseg path, tracked separately from its (possibly relative) display text
        self._dirty = False
        self._image_advanced = []    # per-row extra dict: path_pattern/window_level/threshold/interpolate
        self._segment_colors = []    # per-row [r,g,b] or None
        self._on_saved = on_saved

        self._buildUi()

        if initial_path and os.path.isfile(initial_path):
            self._loadFromFile(initial_path, ask_confirm=False)
        self._dirty = False
        self._updateTitle()

    def _buildUi(self):
        """Lay out the whole dialog: top New/Load/Help row, the tabbed form, the output-path row, and the Save/Close row - dirty-tracking is wired LAST, once every widget referenced by _connectDirtyTracking() already exists."""
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
        tabs.addTab(self._buildGeneralTab(), "General")
        tabs.addTab(self._buildBatchExportTab(), "Batch export")
        tabs.addTab(self._buildImagesTab(), "Images")
        tabs.addTab(self._buildSegmentationTab(), "Segmentation")
        tabs.addTab(self._buildMarkupsTab(), "Markups")
        tabs.addTab(self._buildWorkspaceTab(), "Workspace")
        tabs.addTab(self._buildSegmentEditorTab(), "Segment editor")
        tabs.addTab(self._buildVrTab(), "Volume rendering")
        tabs.addTab(self._buildAdvancedTab(), "Defaults / Presets (JSON)")
        tabs.addTab(self._buildManualTab(), "Manual edit config")

        self.outputEdit, outputRow = self._fileRow(filter_="JSON files (*.json)", save=True, default_name="config.json")
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

        self._connectDirtyTracking()

    def _connectDirtyTracking(self):
        """Hook every plain field's change signal to _markDirty(). Tables/comboboxes created dynamically per-row (Images/Segments/VR rows) wire their own dirty signal individually, right where each row is built."""
        for w in self.findChildren(qt.QLineEdit):
            w.textChanged.connect(self._markDirty)
        for w in self.findChildren(qt.QCheckBox):
            w.stateChanged.connect(self._markDirty)
        for w in self.findChildren(qt.QComboBox):
            w.currentIndexChanged.connect(self._markDirty)
        for w in self.findChildren(qt.QPlainTextEdit):
            w.textChanged.connect(self._markDirty)
        self.imgTable.itemChanged.connect(self._markDirty)
        self.imgTable.itemChanged.connect(lambda item: self._refreshReferenceImageChoices() if item.column() == 0 else None)
        self.segTable.itemChanged.connect(self._markDirty)

    def _markDirty(self, *_a):
        """Flag the form as having unsaved changes and refresh the title bar's '*' marker."""
        self._dirty = True
        self._updateTitle()

    def _updateTitle(self):
        """Show the current file name (or '(new)') plus a trailing '*' if there are unsaved changes."""
        name = os.path.basename(self._current_path) if self._current_path else "(new)"
        self.setWindowTitle(f"Config Editor - {name}{' *' if self._dirty else ''}")

    def _fileRow(self, on_change=None, filter_="CSV files (*.csv);;All files (*)",
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

    def _onShowHelp(self):
        """Open the Config Editor cheat sheet (Resources/Html/config_editor_help_cheatsheet.html) in the shared search/jump popup."""
        show_cheatsheet_dialog(self, "Config Editor - Cheat Sheet", "config_editor_help_cheatsheet.html", CONFIG_EDITOR_HELP_SECTIONS)

    def _confirmDiscard(self):
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

    def _clearForm(self):
        """Reset every field to its blank/default state (including two starter presets, not a truly empty Presets box) - used by New and as the first step of loading any config."""
        self._clearGeneral()
        self._clearImages()
        self._clearSegmentation()
        self._clearMarkups()
        self._clearVolumeRendering()
        self._clearWorkspace()
        self._clearBatchExport()
        self._clearSegmentEditor()
        self._clearDefaults()

    def _onNew(self):
        """Start a blank config, after confirming it's OK to discard any unsaved changes."""
        if not self._confirmDiscard():
            return
        self._clearForm()
        self._current_path = None
        self.outputEdit.text = ""
        self._dirty = False
        self._updateTitle()

    def _onLoadFromFile(self):
        """Browse for a config.json to load, after confirming it's OK to discard any unsaved changes."""
        if not self._confirmDiscard():
            return
        fname = qt.QFileDialog.getOpenFileName(self, "Load config", os.path.dirname(self._current_path) if self._current_path else default_config_dir(), "JSON files (*.json)")
        if fname:
            self._loadFromFile(fname)

    def _onReload(self):
        """Re-read the currently open file from disk, without browsing - e.g. after it was edited outside this dialog. No-op with a friendly message if nothing's open yet."""
        if not self._current_path:
            qt.QMessageBox.information(self, "Config Editor", "Nothing to reload - no file is currently open (use 'Load from file...' first).")
            return
        if not self._confirmDiscard():
            return
        self._loadFromFile(self._current_path, ask_confirm=False)

    def _loadFromFile(self, path, ask_confirm=True):
        """Read+parse a config.json from disk and populate the whole form from it."""
        if ask_confirm and not self._confirmDiscard():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            qt.QMessageBox.critical(self, "Config Editor", f"Failed to load: {e}")
            return
        self._populateForm(cfg)
        self._current_path = path
        remember_config_path(path)
        self.outputEdit.text = path
        self._dirty = False
        self._updateTitle()

    def _populateForm(self, cfg):
        """Fill every tab from a raw config dict, in an order that respects cross-tab dependencies - notably, presets/defaults are loaded BEFORE the images loop, so each row's Preset dropdown already has the right choices the moment it's created."""
        self._clearForm()
        self._populateGeneral(cfg)
        self._populateDefaults(cfg)
        self._populateImages(cfg)
        self._populateSegmentation(cfg)
        self._populateMarkups(cfg)
        self._populateVolumeRendering(cfg)
        self._populateWorkspace(cfg)
        self._populateBatchExport(cfg)
        self._populateSegmentEditor(cfg)

    def _parseJsonField(self, edit, label):
        """Parse a JSON textarea's contents, showing a friendly popup (and re-raising) if it's invalid - callers catch the exception to abort the save/build cleanly without a half-built config."""
        text = (edit.plainText or "").strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception as e:
            qt.QMessageBox.critical(self, "Config Editor", f"Invalid JSON in '{label}': {e}")
            raise

    def _buildConfig(self):
        """Assemble the full config dict from every tab's current state - the single source of truth for what 'Save config' actually writes to disk. Each tab adds its own part, in the order the keys appear in the file."""
        cfg = {}
        self._collectGeneral(cfg)
        self._collectImages(cfg)
        self._collectSegmentation(cfg)
        self._collectMarkups(cfg)
        self._collectVolumeRendering(cfg)
        self._collectWorkspace(cfg)
        self._collectBatchExport(cfg)
        self._collectSegmentEditor(cfg)
        self._collectDefaults(cfg)
        return cfg

    def _onSave(self):
        """Validate + build + write the config.json, prompting for an output path first if none is set yet. Returns True on success, False on any failure (invalid JSON field, no preseg CSV, write error, ...) so callers (e.g. _confirmDiscard) know whether it's safe to proceed."""
        if not self.presegEdit.text.strip():
            qt.QMessageBox.warning(self, "Config Editor", "Select an images/preseg CSV first.")
            return False
        if not self.outputEdit.text.strip():
            fname = qt.QFileDialog.getSaveFileName(self, "Save config as", self._current_path or os.path.join(default_config_dir(), "config.json"), "JSON files (*.json)")
            if not fname:
                return False
            self.outputEdit.text = fname

        try:
            cfg = self._buildConfig()
        except Exception:
            return False   # _parseJsonField already showed the error

        out_path = self.outputEdit.text.strip()
        try:
            out_dir = os.path.dirname(out_path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            def write_json(tmp_path):
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
            safe_io.atomic_write(out_path, write_json, keep_previous=True)
        except Exception as e:
            qt.QMessageBox.critical(self, "Config Editor", f"Failed to save: {e}")
            return False

        self._current_path = out_path
        remember_config_path(out_path)
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
            if self._dirty and not self._confirmDiscard():
                event.ignore()
                return
        except Exception as e:
            logger.warning(f"[ConfigEditor] closeEvent check failed, closing anyway: {e}")
        event.accept()
