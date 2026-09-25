"""
study_setup.py
==============
Picking the config/CSVs, the prompts around them, the pre-flight checks and Initialize Study.
"""

import csv
import os

import qt
import slicer
from qt import QFileDialog

from Resources.gui.config_editor.dialog import ConfigEditorDialog
from Resources.core import safe_io
from Resources.core.logging_setup import logger
from Resources.core.pattern_check import check_config_patterns
from Resources.definitions import STUDY_LOCK_STALE_HOURS
from Resources.utils.config_location import default_config_dir, remember_config_path


class StudySetupMixin:
    """Study setup behaviour of the module widget (mixed into GenericSpecimenManagerWidgetBase)."""

    def onBtnSelectConfig(self):
        """Browse for a config.json, load it immediately, and pre-fill the Database/Preseg CSV path fields from it."""
        fname = QFileDialog.getOpenFileName(None, 'Open config', str(self.ui.tbConfigPath.text) or default_config_dir(), "JSON files (*.json)")
        if not fname:
            return
        self._loadConfigIntoScene(fname)

    def _loadConfigIntoScene(self, path):
        """Load `path` into this module's active Logic/parameter node and pre-fill the Database/Preseg CSV path fields from it - exactly what onBtnSelectConfig does after a browse, but reusable with an already-known path (e.g. the Config Editor's "reload after save" prompt, which calls this instead of making the user browse again)."""
        self._parameterNode.SetParameter("ConfigPath", path)
        remember_config_path(path)
        try:
            self.logic.load_config(path)
            self._parameterNode.SetParameter("DatabaseCSVPath", self.logic._abs_path(self.logic.cfg.database_csv_path))
            self._parameterNode.SetParameter("PresegCSVPath", self.logic._abs_path(self.logic.cfg.preseg_csv_path))
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load config: {e}")

    def onBtnConfigEditor(self):
        """Open the Config Editor, pre-loaded with whatever config is currently active in this module. Passes _loadConfigIntoScene as the post-save reload hook, so Save can offer to push the change live. If the current config path field doesn't point at an actual file - empty, still the pre-filled browse starting folder from a clean start, or a path that's been moved/deleted - offers a real choice instead of letting the Config Editor fail with a raw error popup (or, for empty, silently open blank with no explanation)."""
        current_path = str(self.ui.tbConfigPath.text).strip()
        if not os.path.isfile(current_path):
            self._promptInvalidConfigPath(current_path)
            return
        self._openConfigEditor(current_path)

    def _openConfigEditor(self, initial_path):
        """Actually construct and show the Config Editor, given an already-validated (or intentionally None) initial path."""
        self._configEditorDialog = ConfigEditorDialog(slicer.util.mainWindow(), initial_path=initial_path, on_saved=self._loadConfigIntoScene)
        self._configEditorDialog.setWindowModality(qt.Qt.NonModal)
        self._configEditorDialog.show()

    def _showStudySetupPrompt(self, message, browse_path=""):
        """Shared 3-button prompt (Browse for config.json / Open clean Config Editor / Cancel) for
        anywhere the module needs a valid, fully-set-up config but doesn't have one yet - replaces
        a dead-end warningDisplay with something actionable. Returns 'browse', 'editor', or None
        (Cancel or the dialog closed another way)."""
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setIcon(qt.QMessageBox.Question)
        box.setWindowTitle("Study Settings")
        box.setText(message)
        browseBtn = box.addButton("Browse for config.json...", qt.QMessageBox.AcceptRole)
        editorBtn = box.addButton("Open clean Config Editor", qt.QMessageBox.ActionRole)
        box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(browseBtn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is browseBtn:
            fname = QFileDialog.getOpenFileName(None, 'Open config', browse_path or default_config_dir(), "JSON files (*.json)")
            return "browse" if fname else None, fname
        if clicked is editorBtn:
            return "editor", None
        return None, None

    def _promptInvalidConfigPath(self, path):
        """The config path field doesn't point at a loadable config.json - empty, a folder (most
        commonly the pre-filled browse starting folder on a clean Slicer start), or a file
        that no longer exists - ask what to do instead of opening the Config Editor straight into
        a load failure, or silently opening it blank with no explanation."""
        if not path:
            what = "empty - no config selected yet"
        elif os.path.isdir(path):
            what = "a folder"
        else:
            what = "a file that no longer exists"
        detail = f":\n\n{path}" if path else ""
        choice, fname = self._showStudySetupPrompt(
            f"The current config path is {what}{detail}.\n\nWhat would you like to do?", browse_path=path)
        if choice == "browse":
            self._loadConfigIntoScene(fname)
            self._openConfigEditor(fname)
        elif choice == "editor":
            self._openConfigEditor(None)

    def _promptStudyNotReady(self, reason):
        """Same 3-button prompt as _promptInvalidConfigPath, used from Initialize Study whenever
        it can't proceed because the config/CSV setup isn't complete yet (empty/invalid config
        path, or the database/preseg CSV paths are empty) - Browse starts from the current Study
        config field's path (same as 'Select .json file'), loads the picked config straight into
        the scene (no Config Editor involved), and immediately retries Initialize Study so picking
        a valid config actually finishes the job in one go. Open clean Config Editor opens a blank
        one to build a config from scratch instead."""
        current_path = str(self.ui.tbConfigPath.text).strip()
        choice, fname = self._showStudySetupPrompt(f"{reason}\n\nWhat would you like to do?", browse_path=current_path)
        if choice == "browse":
            self._loadConfigIntoScene(fname)
            self.onBtnInitializeStudy()
        elif choice == "editor":
            self._openConfigEditor(None)

    def onBtnSelectDB(self):
        """Browse for an override Database CSV path (normally this is auto-filled from the loaded config)."""
        fname = QFileDialog.getOpenFileName(None, 'Open file', str(self.ui.tbDBPath.text), "CSV files (*.csv)")
        if fname:
            self._parameterNode.SetParameter("DatabaseCSVPath", fname)

    def onBtnSelectPreseg(self):
        """Browse for an override Preseg CSV path (normally this is auto-filled from the loaded config)."""
        fname = QFileDialog.getOpenFileName(None, 'Open file', str(self.ui.tbPresegPath.text), "CSV files (*.csv)")
        if fname:
            self._parameterNode.SetParameter("PresegCSVPath", fname)

    def _preflightCheck(self, db_path, preseg_path):
        """Pure-Python (no Slicer/VTK calls) sanity check, run before ever
        calling slicer.util.loadTable()/self.logic.initializeStudy(). Catches
        the most common real-world mistakes - a typo'd key column, an empty
        or malformed CSV - with a plain-language message, instead of letting
        them surface as a native VTK/Slicer error dialog that's confusing for
        non-technical users. Returns None if everything looks fine, otherwise
        a ready-to-show message string."""

        key_columns = None
        if self.logic.cfg is not None:
            key_columns = self.logic.cfg.key_columns
        else:
            config_path = str(self.ui.tbConfigPath.text).strip() or self.CONFIG_PATH
            try:
                import json
                with open(config_path, "r", encoding="utf-8") as f:
                    raw_cfg = json.load(f)
                key_columns = raw_cfg.get("key_columns") or ["ID"]
            except Exception as e:
                return f"The config file couldn't be read as JSON:\n{e}\n\nOpen it in the Config Editor to fix it."

        def _read_header(path, label):
            """Read one CSV's header row with plain Python csv (no Slicer/VTK) and return (header, error_message) - error_message is None on success."""
            try:
                with open(path, "r", encoding="utf-8-sig", newline="") as f:
                    header = next(csv.reader(f), None)
            except Exception as e:
                return None, f"{label} couldn't be read as a CSV file:\n{path}\n\n{e}"
            if not header or not any(h.strip() for h in header):
                return None, f"{label} appears to be empty (no header row):\n{path}"
            return header, None

        db_header, err = _read_header(db_path, "The database CSV")
        if err:
            return err
        preseg_header, err = _read_header(preseg_path, "The preseg CSV")
        if err:
            return err

        missing_db = [c for c in key_columns if c not in db_header]
        missing_preseg = [c for c in key_columns if c not in preseg_header]
        if missing_db or missing_preseg:
            lines = ["The key column(s) from the config don't match the actual CSV columns:"]
            if missing_db:
                lines.append(f"  - missing from database CSV: {missing_db}")
            if missing_preseg:
                lines.append(f"  - missing from preseg CSV: {missing_preseg}")
            lines.append("")
            lines.append(f"Database CSV columns:  {db_header}")
            lines.append(f"Preseg CSV columns:    {preseg_header}")
            lines.append("")
            lines.append("Fix 'Key columns' in the Config Editor's General tab (or use 'Show CSV columns...' there to check the exact names).")
            return "\n".join(lines)

        if self.logic.cfg is not None:
            errors, warnings = check_config_patterns(self.logic.cfg, set(db_header) | set(preseg_header))
            for w in warnings:
                logger.warning(f"[GenericSpecimenManager] config check: {w}")
            if errors:
                return ("The config has pattern problems that would make specimens fail to load:\n\n  - "
                        + "\n  - ".join(errors)
                        + "\n\nFix them in the Config Editor (or use 'Show CSV columns...' there to check the exact column names).")

        return None

    def onBtnInitializeStudy(self):
        """(Re)build the specimen list: if a specimen is already open, warn and offer to save first; validate the config/CSV paths (folder-vs-file, then a pure-Python CSV/key-column sanity check) before ever calling Slicer's table loader; finally call Logic.initializeStudy() and refresh the table/batch combo."""
        if self.logic.hasActiveSpecimen:
            ret = qt.QMessageBox.warning(
                slicer.util.mainWindow(), "Re-initialize study",
                "A specimen is currently open. Re-initializing the study reloads the "
                "database/preseg tables and rebuilds the specimen list - any unsaved "
                "work on the open specimen (and unsaved database table edits) can be "
                "lost or end up misattributed if you continue without saving first.\n\n"
                "Save the active specimen and the database CSV before continuing?",
                qt.QMessageBox.Save | qt.QMessageBox.Discard | qt.QMessageBox.Cancel)
            if ret == qt.QMessageBox.Cancel:
                return
            if ret == qt.QMessageBox.Save:
                try:
                    self.logic.save_active_specimen(inform_user=False)
                    self.logic.save_db()
                except Exception as e:
                    slicer.util.errorDisplay("Failed to save before re-initializing: " + str(e))
                    return
            self.logic.close_active_specimen(no_question=True)
            self._detachActiveSpecimenObservers()
            self._updatePostInitButtonStates()
            self._refreshSpecimenStatusLabels()
            self._refreshSpecimenAnnotation()

        try:
            if self.logic.cfg is None:
                config_path = str(self.ui.tbConfigPath.text).strip() or self.CONFIG_PATH
                if not config_path:
                    self._promptStudyNotReady("No study config selected yet.")
                    return
                if not os.path.exists(config_path):
                    self._promptStudyNotReady(f"Config file not found:\n{config_path}")
                    return
                if os.path.isdir(config_path):
                    # This is the browse starting folder pre-filled into the field
                    # (see updateGUIFromParameterNode) - it was never
                    # actually picked as a file. Opening a directory as a config
                    # raises IsADirectoryError, which used to surface as a
                    # confusing generic "Failed to load config" message.
                    self._promptStudyNotReady(f"That's a folder, not a config file yet:\n{config_path}")
                    return
                self.logic.load_config(config_path)
        except Exception as e:
            slicer.util.errorDisplay("Failed to load config: " + str(e))
            return

        db_path = str(self.ui.tbDBPath.text).strip()
        preseg_path = str(self.ui.tbPresegPath.text).strip()
        if not db_path or not preseg_path:
            self._promptStudyNotReady(
                "Database CSV and Preseg CSV paths must both be set. They're normally filled in "
                "automatically from the config - if they're empty, the loaded config may be missing "
                "database_csv_path/preseg_csv_path, or you cleared the fields by hand.")
            return
        if not os.path.exists(db_path):
            slicer.util.warningDisplay(f"Database CSV not found:\n{db_path}")
            return
        if not os.path.exists(preseg_path):
            slicer.util.warningDisplay(f"Preseg CSV not found:\n{preseg_path}")
            return

        problem = self._preflightCheck(db_path, preseg_path)
        if problem:
            slicer.util.warningDisplay(problem)
            return

        foreign_lock = safe_io.foreign_lock(db_path, STUDY_LOCK_STALE_HOURS)
        if foreign_lock and not self._confirmStudyAlreadyOpen(foreign_lock):
            return

        try:
            self._studyInitialized = False
            self.logic.initializeStudy()
            if not self._resolveMissingDbColumns():
                self.logic.specimens = {}
                self.ui.tblSpecimens.setRowCount(0)
                self._updatePostInitButtonStates()
                return
            self._studyInitialized = True
            self.logic.acquire_study_lock(db_path)
            self._group_filter = None
            self._setupBatchCombo()
            self.showSpecimenTable()
            self._updatePostInitButtonStates()
        except Exception as e:
            slicer.util.errorDisplay("Failed to initialize study: " + str(e))
            import traceback
            traceback.print_exc()

    def _confirmStudyAlreadyOpen(self, lock_info):
        """The study's lock file says someone else has it open. Ask whether to continue anyway (the lock is advisory) - two sessions editing the same database.csv can overwrite each other's status changes. True = continue."""
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setIcon(qt.QMessageBox.Warning)
        box.setWindowTitle("Study already open")
        box.setText(f"This study looks open in another session:\n\n{safe_io.describe_lock(lock_info)}\n\n"
                    "Working on the same study from two places at once can lose changes. If that session is gone "
                    "(closed Slicer, crashed), it is safe to continue.")
        continueBtn = box.addButton("Continue anyway", qt.QMessageBox.AcceptRole)
        cancelBtn = box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(cancelBtn)
        box.exec_()
        clicked = box.clickedButton()
        return clicked is not None and str(clicked.text) == "Continue anyway"

    def _resolveMissingDbColumns(self):
        """Right after the tables load: any configured Factor column missing from database.csv is
        surely intentional (not a typo), so offer to create it; a plain table_columns entry that's
        missing MAY be a typo, so those are listed separately and only created if explicitly
        ticked. Returns False if the user cancels (Initialize Study is then aborted), else True
        with the chosen columns already added to the live database table."""
        cfg = self.logic.cfg
        existing = set(self.logic.dbColumnNames)
        factor_cols = [fc.column for fc in cfg.factor_columns if fc.column and fc.column not in existing]
        if cfg.status_column not in existing and cfg.status_column not in factor_cols:
            factor_cols.insert(0, cfg.status_column)   # the status column is never a typo - always offered for creation
        table_cols = [c for c in cfg.table_columns if c not in existing and c not in factor_cols]
        if not factor_cols and not table_cols:
            return True

        dlg = qt.QDialog(slicer.util.mainWindow())
        dlg.setWindowTitle("Columns missing from database.csv")
        layout = qt.QVBoxLayout(dlg)
        layout.addWidget(qt.QLabel("Some configured columns don't exist in the database CSV yet."))
        if factor_cols:
            lbl = qt.QLabel("<b>Status / factor columns</b> - will be created (empty):<br>" + ", ".join(factor_cols))
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
        table_checks = []
        if table_cols:
            layout.addWidget(qt.QLabel("<b>Table columns</b> - possibly typos; tick only the ones to create:"))
            for c in table_cols:
                chk = qt.QCheckBox(c)
                table_checks.append(chk)
                layout.addWidget(chk)
        btnRow = qt.QHBoxLayout()
        addBtn = qt.QPushButton("Add columns and continue")
        addBtn.connect('clicked(bool)', lambda checked=False: dlg.accept())
        cancelBtn = qt.QPushButton("Cancel initialization")
        cancelBtn.connect('clicked(bool)', lambda checked=False: dlg.reject())
        btnRow.addStretch(1)
        btnRow.addWidget(addBtn)
        btnRow.addWidget(cancelBtn)
        layout.addLayout(btnRow)
        if dlg.exec_() != qt.QDialog.Accepted:
            return False

        added = list(factor_cols) + [c for c, chk in zip(table_cols, table_checks) if chk.checked]
        for c in added:
            self.logic.ensure_db_column(c)
        if added:
            self.logic.save_db(inform_user=False)   # write the new columns to database.csv right away
        return True

    def _validatePathField(self, edit):
        """Live, passive feedback (border color + tooltip) on whether a path
        field currently points at a real file - instead of only finding out
        via a popup error after clicking Initialize Study."""
        path = str(edit.text).strip()
        if not path:
            edit.setStyleSheet("")
            edit.setToolTip("")
        elif not os.path.exists(path):
            edit.setStyleSheet("border: 1px solid #cc3333; background-color: #fff0f0;")
            edit.setToolTip("Not found: " + path)
        elif os.path.isdir(path):
            edit.setStyleSheet("border: 1px solid #cc8800; background-color: #fff8e8;")
            edit.setToolTip("This is a folder, not a file: " + path)
        else:
            edit.setStyleSheet("border: 1px solid #33aa33;")
            edit.setToolTip(path)
