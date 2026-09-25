"""
logic.py
========
GenericSpecimenManagerLogic: the parsed StudyConfig, the database/preseg tables, the dict of specimens, and the
safe saving of database.csv. No GUI code here.
"""

import csv
import os

import ctk
import qt
import slicer
import vtk
from slicer.ScriptedLoadableModule import ScriptedLoadableModuleLogic

from Resources.core import safe_io
from Resources.core.config_model import StudyConfig, load_config
from Resources.core.logging_setup import logger
from Resources.definitions import DB_BACKUPS_KEEP, DB_BACKUP_MIN_INTERVAL_SECONDS
from Resources.study.specimen import GenericSpecimen
from Resources.utils.segment_editor import configure_segment_editor_defaults


class GenericSpecimenManagerLogic(ScriptedLoadableModuleLogic):

    """Owns the parsed StudyConfig, the database/preseg tables, and the dict of all specimens for the current study. No GUI code here - the Widget class below is the only thing that talks to Qt."""
    def __init__(self):
        """Holds the parsed StudyConfig plus the live database/preseg table nodes and the in-memory specimen dict - one instance per module widget."""
        ScriptedLoadableModuleLogic.__init__(self)
        self.cfg: StudyConfig = None
        self.study_dir = None
        self.dbTable = None
        self._db_signature = None      # content signature of database.csv when we last read/wrote it (change detection)
        self._db_signature_path = None
        self._locked_db_path = None    # database.csv whose study lock we hold
        self.presegTable = None
        self.dbDictList = []
        self.presegDictList = []
        self.dbColumnNames = []
        self.specimens = {}
        self.active_specimen = None
        self.default_config_path = None

    def load_config(self, config_path):
        """Parse config_path into self.cfg (a StudyConfig) and remember its study_dir."""
        self.cfg = load_config(config_path)
        self.study_dir = self.cfg.study_dir
        return self.cfg

    def _abs_path(self, rel):
        """Resolve rel against study_dir if it isn't already absolute."""
        if not rel:
            return rel
        return rel if os.path.isabs(rel) else os.path.join(self.study_dir, rel)

    def setDefaultParameters(self, parameterNode):
        """Called by Slicer when a parameter node is first attached to this module: seed ConfigPath from default_config_path (set by the wrapper module) or an existing saved parameter, load that config if it exists, and pre-fill the Database/Preseg CSV path parameters from it."""
        if not parameterNode.GetParameter("ConfigPath"):
            parameterNode.SetParameter("ConfigPath", self.default_config_path or "")
        if self.cfg is None:
            config_path = parameterNode.GetParameter("ConfigPath") or self.default_config_path
            if config_path and os.path.exists(config_path):
                try:
                    self.load_config(config_path)
                except Exception as e:
                    logger.warning(f"[GenericSpecimenManager] failed to load config '{config_path}': {e}")
        if self.cfg:
            if not parameterNode.GetParameter("DatabaseCSVPath"):
                parameterNode.SetParameter("DatabaseCSVPath", self._abs_path(self.cfg.database_csv_path))
            if not parameterNode.GetParameter("PresegCSVPath"):
                parameterNode.SetParameter("PresegCSVPath", self._abs_path(self.cfg.preseg_csv_path))

    def get_node_if_loaded(self, file_path):
        """Return the name of an already-loaded scene node backed by file_path, or '' if none - lets Initialize Study reuse an already-open table instead of reloading it from disk (and losing any in-scene edits)."""
        for n in slicer.mrmlScene.GetNodes():
            try:
                if n.GetStorageNode().GetFileName() == file_path:
                    return n.GetName()
            except Exception:
                continue
        return ""

    def initializeStudy(self):
        """Load (or reuse) the database and preseg tables, intersect their key-column values, and build one GenericSpecimen per matching row. Then apply segment_editor config once (see _configure_segment_editor_defaults)."""
        if self.cfg is None:
            raise RuntimeError("No config loaded. Select a config.json first.")
        db_path = self.getParameterNode().GetParameter("DatabaseCSVPath")
        preseg_path = self.getParameterNode().GetParameter("PresegCSVPath")

        try:
            node = slicer.util.getNode(self.get_node_if_loaded(db_path))
            self.dbTable = node
            if self._db_signature_path != db_path:   # table node reused, but we haven't seen this file yet
                self._db_signature = safe_io.file_signature(db_path)
                self._db_signature_path = db_path
        except slicer.util.MRMLNodeNotFoundException:
            self.dbTable = slicer.util.loadTable(db_path)
            self._db_signature = safe_io.file_signature(db_path)
            self._db_signature_path = db_path
        try:
            node = slicer.util.getNode(self.get_node_if_loaded(preseg_path))
            self.presegTable = node
        except slicer.util.MRMLNodeNotFoundException:
            self.presegTable = slicer.util.loadTable(preseg_path)

        self.dbDictList, self.dbColumnNames = self._table_to_dicts(self.dbTable, return_columns=True)
        self.presegDictList = self._table_to_dicts(self.presegTable)

        key_columns = self.cfg.key_columns
        status_col = self.cfg.status_column
        db_keys = [tuple(row.get(c, "") for c in key_columns) for row in self.dbDictList]
        preseg_keys = [tuple(row.get(c, "") for c in key_columns) for row in self.presegDictList]
        common_keys = sorted(set(db_keys).intersection(set(preseg_keys)))

        self.specimens = {}
        for key in common_keys:
            db_idx = db_keys.index(key)
            db_row = self.dbDictList[db_idx]
            preseg_row = next((r for r in self.presegDictList if tuple(r.get(c, "") for c in key_columns) == key), {})
            specimen = GenericSpecimen(key, self.cfg, db_row, preseg_row, self.study_dir)
            specimen.row_index = db_idx
            specimen.status_col_index = self.dbColumnNames.index(status_col) if status_col in self.dbColumnNames else None
            self.specimens[key] = specimen

        logger.info(f"[GenericSpecimenManager] initialized {len(self.specimens)} specimens")
        configure_segment_editor_defaults(self.cfg.segment_editor)

    def group_by_key_values(self):
        """Unique, sorted values of cfg.group_by_key.column across all specimens."""
        col = self.cfg.group_by_key.column
        if not col:
            return []
        return sorted({s.db_info.get(col, "") for s in self.specimens.values()} - {""})

    def _table_to_dicts(self, table, return_columns=False):
        """Convert a loaded vtkMRMLTableNode into a list of {column_name: value} dicts (optionally also returning the raw, ordered column name list, needed for name-based cell write-back)."""
        dict_list = []
        _t = table.GetTable()
        ncol, nrow = _t.GetNumberOfColumns(), _t.GetNumberOfRows()
        colnames = [_t.GetColumnName(j) for j in range(ncol)]
        for i in range(nrow):
            row = _t.GetRow(i)
            dict_list.append({colnames[j]: row.GetValue(j).ToString() for j in range(ncol)})
        return (dict_list, colnames) if return_columns else dict_list

    def confirm(self, text):
        """Simple Yes/No modal dialog. Returns True iff the user picked Yes."""
        c = ctk.ctkMessageBox()
        c.setIcon(qt.QMessageBox.Information)
        c.setText(text)
        c.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
        c.setDefaultButton(qt.QMessageBox.Ok)
        return c.exec_() == qt.QMessageBox.Yes

    def info(self, text):
        """Simple OK-only modal information dialog."""
        c = ctk.ctkMessageBox()
        c.setIcon(qt.QMessageBox.Information)
        c.setText(text)
        c.setStandardButtons(qt.QMessageBox.Ok)
        c.setDefaultButton(qt.QMessageBox.Ok)
        c.exec_()

    def show_key_value_dialog(self, title, rows):
        """Show a small, nicely-formatted OK-only dialog: a grid of bold-label/value rows, built from real widgets instead of one plain QMessageBox text blob - used for the Save confirmations, where a flat wall of text was hard to scan. `rows` is a list of (label, value) pairs."""
        dlg = qt.QDialog(slicer.util.mainWindow())
        dlg.setWindowTitle(title)
        layout = qt.QVBoxLayout(dlg)

        titleLabel = qt.QLabel(f"<h3>{title}</h3>")
        layout.addWidget(titleLabel)

        grid = qt.QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(16)
        for i, (label, value) in enumerate(rows):
            lbl = qt.QLabel(f"<b>{label}</b>")
            val = qt.QLabel(str(value))
            val.setWordWrap(True)
            val.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            grid.addWidget(lbl, i, 0, qt.Qt.AlignTop)
            grid.addWidget(val, i, 1)
        layout.addLayout(grid)

        btnRow = qt.QHBoxLayout()
        btnRow.addStretch(1)
        okBtn = qt.QPushButton("OK")
        okBtn.setDefault(True)
        okBtn.connect('clicked(bool)', lambda checked=False: dlg.accept())
        btnRow.addWidget(okBtn)
        layout.addLayout(btnRow)

        dlg.exec_()

    def load_specimen(self, key):
        """Load the specimen for `key` and make it the active one - refuses (with an info popup) if a specimen is already active."""
        target = self.specimens.get(key)
        if isinstance(self.active_specimen, GenericSpecimen):
            self.info("A specimen has already been loaded.")
            return False
        if target is None:
            raise ValueError(f"Specimen {key} not initialized")
        target.load()
        self.active_specimen = target
        return True

    def load_specimen_for_batch(self, key, image_names=None):
        """Lean equivalent of load_specimen() for headless batch operations
        (batch_processor.py) - calls GenericSpecimen.load_for_batch() instead
        of the full load(), so workspace/volume-rendering/Segment-Editor
        setup is skipped entirely. Same active-specimen bookkeeping/guard
        as load_specimen()."""
        target = self.specimens.get(key)
        if isinstance(self.active_specimen, GenericSpecimen):
            self.info("A specimen has already been loaded.")
            return False
        if target is None:
            raise ValueError(f"Specimen {key} not initialized")
        target.load_for_batch(image_names=image_names)
        self.active_specimen = target
        return True

    def close_active_specimen(self, no_question=False):
        """Close the active specimen, asking for confirmation first unless no_question=True (used for scene-close/re-init flows where the caller already confirmed)."""
        if no_question:
            if self.active_specimen is not None:
                self.active_specimen.close()
                self.active_specimen = None
            return
        if not isinstance(self.active_specimen, GenericSpecimen):
            self.info("There is no active specimen to close.")
            return
        if not self.confirm("Do you really want to close the active specimen?"):
            return
        self.active_specimen.close()
        self.active_specimen = None

    def save_active_specimen(self, inform_user=True):
        """Save the active specimen's writeable nodes to disk; optionally show a confirmation popup."""
        if not isinstance(self.active_specimen, GenericSpecimen):
            self.info("There is no active specimen to save.")
            return
        sp = self.active_specimen
        sp.save()
        if inform_user:
            rows = list(zip(self.cfg.key_columns, sp.key_values))
            rows.append(("folder", sp.out_dir))
            self.show_key_value_dialog("Specimen saved", rows)

    def ensure_db_column(self, name):
        """Add `name` as a new, empty column to the live database table if it isn't there yet -
        used when a Table/Factor column is configured for a name that doesn't actually exist in
        database.csv, so editing it in the GUI creates the column instead of refusing to write
        back. Returns True once the column exists (already did, or was just added)."""
        if name in self.dbColumnNames:
            return True
        if self.dbTable is None:
            return False
        col = vtk.vtkStringArray()
        col.SetName(name)
        col.SetNumberOfValues(self.dbTable.GetNumberOfRows())
        for i in range(self.dbTable.GetNumberOfRows()):
            col.SetValue(i, "")
        self.dbTable.AddColumn(col)
        self.dbColumnNames.append(name)
        logger.info(f"[GenericSpecimenManager] added new database.csv column '{name}'")
        return True

    def set_specimen_status(self, specimen, status, only_raise=False):
        """Write `status` (a SpecimenStatus) into the specimen's status column, in the live database table AND its cached db_info - creating the column first if it's missing. With only_raise=True a specimen already at or above `status` is left alone (automatic promotions never downgrade a manual to-review/finished). Returns True if the value actually changed."""
        if specimen is None or specimen.row_index is None:
            return False
        status_col = self.cfg.status_column
        if not self.ensure_db_column(status_col):
            return False
        current = specimen.status
        if current == status or (only_raise and current >= status):
            return False
        real_col = self.dbColumnNames.index(status_col)
        self.dbTable.SetCellText(specimen.row_index, real_col, str(int(status)))
        written = self.dbTable.GetCellText(specimen.row_index, real_col)
        if written != str(int(status)):
            logger.warning(f"[GenericSpecimenManager] status write to '{status_col}' did not stick (read back '{written}') - is the column numeric?")
        specimen.db_info[status_col] = str(int(status))
        specimen.status_col_index = real_col
        return True

    def save_db(self, inform_user=True):
        """Write the live database table back to its CSV file - safely. The table is written to a temp file and checked (same number of data rows, every column present) before it replaces database.csv in one step, so an interrupted or failed write leaves the old file intact; the version being replaced is first copied into a .backups folder (throttled, newest DB_BACKUPS_KEEP kept); and if database.csv was changed on disk by someone/something else since we last read or wrote it, we ask before overwriting. Returns True if the file was written. Always logged at DEBUG level (not INFO), since this can fire silently and often - e.g. Auto-save database after every table edit."""
        db_path = self.getParameterNode().GetParameter("DatabaseCSVPath")
        changed_on_disk = self._db_signature is not None and safe_io.file_signature(db_path) != self._db_signature
        if changed_on_disk and not self._confirmOverwriteChangedDb(db_path):
            return False

        expected_rows = self.dbTable.GetNumberOfRows()
        expected_columns = list(self.dbColumnNames)

        def write(tmp_path):
            storage = self.dbTable.CreateDefaultStorageNode()
            storage.SetHideFromEditors(True)
            storage.SetFileName(tmp_path)
            ok = storage.WriteData(self.dbTable)
            if slicer.mrmlScene.IsNodePresent(storage):
                slicer.mrmlScene.RemoveNode(storage)
            if ok is not None and not ok:
                raise IOError("Slicer could not write the database table")

        def verify(tmp_path):
            with open(tmp_path, "r", encoding="utf-8-sig", newline="") as f:
                rows = list(csv.reader(f))
            header, data = (rows[0] if rows else []), rows[1:]
            missing = [c for c in expected_columns if c not in header]
            if missing or len(data) != expected_rows:
                raise IOError(f"the written database looks wrong (rows {len(data)} of {expected_rows}, missing columns {missing}) - "
                              "the old database.csv was NOT replaced")

        # Before replacing: a backup of what is on disk now (always when it was changed under us).
        safe_io.backup_file(db_path, keep=DB_BACKUPS_KEEP,
                           min_interval_seconds=0 if changed_on_disk else DB_BACKUP_MIN_INTERVAL_SECONDS)
        safe_io.atomic_write(db_path, write, verify=verify)
        self._db_signature = safe_io.file_signature(db_path)
        self._db_signature_path = db_path
        if self._locked_db_path == db_path:
            safe_io.acquire_lock(db_path)   # refresh our "touched" time
        logger.debug(f"[GenericSpecimenManager] saved database CSV -> {db_path}")
        if inform_user:
            self.show_key_value_dialog("Database saved", [("path", db_path)])
        return True

    def _confirmOverwriteChangedDb(self, db_path):
        """database.csv changed on disk since we read/wrote it: ask whether to overwrite it with this session's table anyway (the disk version is backed up first, so it stays recoverable). True = overwrite."""
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setIcon(qt.QMessageBox.Warning)
        box.setWindowTitle("database.csv changed on disk")
        box.setText(f"{db_path}\n\nwas changed on disk after this session read it - by another person, another program, "
                    "or a second Slicer.\n\nSaving now replaces that version with this session's table. "
                    "The version on disk is backed up first (in the .backups folder next to it).")
        overwriteBtn = box.addButton("Overwrite (keep a backup)", qt.QMessageBox.DestructiveRole)
        cancelBtn = box.addButton("Don't save", qt.QMessageBox.RejectRole)
        box.setDefaultButton(cancelBtn)
        box.exec_()
        clicked = box.clickedButton()
        return clicked is not None and str(clicked.text) == "Overwrite (keep a backup)"

    def acquire_study_lock(self, db_path):
        """Mark the study (identified by its database.csv) as open by this session; releases a lock on a previous database first."""
        if self._locked_db_path and self._locked_db_path != db_path:
            self.release_study_lock()
        safe_io.acquire_lock(db_path)
        self._locked_db_path = db_path

    def release_study_lock(self):
        """Remove this session's study lock, if it holds one."""
        if self._locked_db_path:
            safe_io.release_lock(self._locked_db_path)
            self._locked_db_path = None

    @property
    def hasActiveSpecimen(self):
        """True if a specimen is currently loaded."""
        return isinstance(self.active_specimen, GenericSpecimen)
