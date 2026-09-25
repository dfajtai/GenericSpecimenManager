"""
specimen_actions.py
===================
Load / Save / Close / Reset of the active specimen, Ctrl+S, and saving the database.
"""

import os

import qt
import slicer

from Resources.core import safe_io
from Resources.core.logging_setup import logger
from Resources.definitions import SPECIMEN_STATUS_COLORS, SpecimenStatus
from Resources.study.batch_processor import batch_exporter


class SpecimenActionsMixin:
    """Specimen action buttons of the module widget (mixed into GenericSpecimenManagerWidgetBase)."""

    def onBtnLoadSelected(self):
        """Load the currently-selected specimen, start observing it for the status dot, and update the active-specimen label/button state."""
        try:
            if not self.tbl_selected_key:
                return
            self.logic.load_specimen(self.tbl_selected_key)
            specimen = self.logic.active_specimen
            if specimen is not None and specimen.loaded_own_data:
                self._setSpecimenStatus(specimen, SpecimenStatus.IN_PROGRESS, only_raise=True)
            self._attachActiveSpecimenObservers()
            self._updatePostInitButtonStates()
            self._refreshSpecimenStatusLabels()
            self._refreshSpecimenAnnotation()
        except Exception as e:
            slicer.util.errorDisplay("Failed to load specimen: " + str(e))
            import traceback
            traceback.print_exc()

    def onBtnSaveActiveSpecimen(self):
        """Save button: save the active specimen (with the 'Specimen saved' popup)."""
        self._saveActiveSpecimen(inform_user=True)

    def _onSaveShortcut(self):
        """Ctrl+S while a specimen is loaded: same save as the button, without the popup (a status-bar note instead) - it can be pressed often."""
        if self.logic is not None and self.logic.hasActiveSpecimen:
            self._saveActiveSpecimen(inform_user=False)
            slicer.util.showStatusMessage(f"Saved {self.logic.active_specimen.label}", 3000)

    def _syncSaveShortcut(self):
        """Ctrl+S belongs to this module ONLY while a specimen is loaded (see utils/slicer_ui.SaveShortcut) - otherwise Slicer's own Save scene shortcut keeps working."""
        if self._saveShortcut is not None:
            self._saveShortcut.set_active(bool(self.logic is not None and self.logic.hasActiveSpecimen))

    def _saveActiveSpecimen(self, inform_user):
        """Save the active specimen's writeable nodes, promote its status to in progress, and refresh the status dot back to clean."""
        try:
            self.logic.save_active_specimen(inform_user=inform_user)
            if self.logic.active_specimen is not None:
                self._setSpecimenStatus(self.logic.active_specimen, SpecimenStatus.IN_PROGRESS, only_raise=True)
            self._refreshSpecimenStatusLabels()
        except Exception as e:
            slicer.util.errorDisplay("Failed to save specimen: " + str(e))
            import traceback
            traceback.print_exc()

    def onBtnCloseActiveSpecimen(self):
        """Close the active specimen: asks Yes / Yes, mark to-review / Yes, mark finished / No instead of a plain
        Yes/No confirm, so a specimen's status can be set without a separate trip to the table
        dropdown first. This NEVER saves the specimen's own segmentation/markups - use Save
        progress for that before closing if you want to keep unsaved work. The status update goes
        through the same path as a manual dropdown pick - auto-saved to disk right away if
        Auto-save database is checked (see _autoSaveDatabaseIfEnabled())."""
        if not self.logic.hasActiveSpecimen:
            self.logic.info("There is no active specimen to close.")
            return
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setIcon(qt.QMessageBox.Question)
        box.setWindowTitle("Close active specimen")
        box.setText(f"Close {self.logic.active_specimen.label}?")
        # Buttons are told apart by their text, not by object identity - PythonQt doesn't
        # guarantee clickedButton() hands back the very same wrapper object addButton() returned.
        choices = {"Yes": None, "Yes, mark to review": SpecimenStatus.TO_REVIEW, "Yes, mark finished": SpecimenStatus.FINISHED}
        yesBtn = None
        for text, status in choices.items():
            btn = box.addButton(text, qt.QMessageBox.YesRole)
            if status is not None:
                r, g, b = SPECIMEN_STATUS_COLORS[status]   # same colors as the table rows
                btn.setStyleSheet(f"QPushButton {{ background-color: rgb({r},{g},{b}); color: black; }}")
            if yesBtn is None:
                yesBtn = btn
        box.addButton("No", qt.QMessageBox.NoRole)
        box.setDefaultButton(yesBtn)
        box.exec_()
        clicked = box.clickedButton()
        text = str(clicked.text) if clicked is not None else ""
        if text not in choices:
            return
        self._restoreSelectionAfter(self._closeActiveSpecimen, choices[text])

    def _restoreSelectionAfter(self, action, *args):
        """Run `action(*args)` with the specimen table disabled, then re-select the row that was selected before. Closing/resetting a specimen makes the table grab focus, and a table with no current cell answers that by selecting its first row - a disabled table can't take focus."""
        tbl = self.ui.tblSpecimens
        selected_key = self.tbl_selected_key
        tbl.enabled = False

        def finish():
            if selected_key is not None:
                self._restoreSelection(selected_key)
            tbl.enabled = True

        try:
            action(*args)
        finally:
            qt.QTimer.singleShot(0, finish)

    def _closeActiveSpecimen(self, new_status):
        """Close the active specimen, first setting `new_status` (a SpecimenStatus, or None to leave the status alone)."""
        try:
            specimen = self.logic.active_specimen
            if new_status is not None:
                self.logic.set_specimen_status(specimen, new_status)
                self._refreshStatusCell(specimen)
                self._autoSaveDatabaseIfEnabled()
            self.logic.close_active_specimen(no_question=True)
            self._detachActiveSpecimenObservers()
            self._updatePostInitButtonStates()
            self._refreshSpecimenStatusLabels()
            self._refreshSpecimenAnnotation()
        except Exception as e:
            slicer.util.errorDisplay("Failed to close specimen: " + str(e))
            import traceback
            traceback.print_exc()

    def onBtnResetSelectedSpecimen(self):
        """Reset the specimen selected in the table (it doesn't have to be loaded): after a clearly worded confirmation - the specimen ID, the exact files, and the word RESET typed in - DELETES its saved segmentation and markups files from disk and sets its status back to 'untouched'. If it happens to be the active specimen it is closed too (unsaved work is discarded); load it again to start from the config's starting state. Source images are never touched. Cannot be undone."""
        key = self.tbl_selected_key
        specimen = self.logic.specimens.get(key) if key else None
        if specimen is None:
            self.logic.info("Select a specimen in the table first.")
            return
        cfg = self.logic.cfg
        paths = []
        if cfg.segmentation.enabled:
            paths.append(specimen.segmentation_out_path())
        if cfg.markups.enabled:
            paths.append(specimen.markups_out_path())
        paths += [p + safe_io.PREVIOUS_SUFFIX for p in paths]   # the previous versions kept by earlier saves
        existing = [p for p in paths if os.path.exists(p)]

        dlg = qt.QDialog(slicer.util.mainWindow())
        dlg.setWindowTitle("Reset specimen")
        layout = qt.QVBoxLayout(dlg)
        files = "".join(f"<li>{p}</li>" for p in existing) or "<li>(no saved files found)</li>"
        msg = qt.QLabel(
            f"<h3 style='color:#b00020'>Reset {specimen.label}?</h3>"
            f"<p>These saved files will be <b>permanently deleted</b> from disk:</p><ul>{files}</ul>"
            "<p>Its status will be set back to <b>untouched</b>."
            + (" It is currently loaded: it will be closed and any unsaved work discarded." if self.logic.active_specimen is specimen else "")
            + "<br>This cannot be undone.</p>")
        msg.setWordWrap(True)
        layout.addWidget(msg)
        layout.addWidget(qt.QLabel("Type <b>RESET</b> to confirm:"))
        confirmEdit = qt.QLineEdit()
        layout.addWidget(confirmEdit)
        btnRow = qt.QHBoxLayout()
        btnRow.addStretch(1)
        resetBtn = qt.QPushButton("Delete files and reset")
        resetBtn.setStyleSheet("QPushButton { background-color: #f4c7c3; color: black; }")
        resetBtn.enabled = False
        resetBtn.connect('clicked(bool)', lambda checked=False: dlg.accept())
        cancelBtn = qt.QPushButton("Cancel")
        cancelBtn.setDefault(True)
        cancelBtn.connect('clicked(bool)', lambda checked=False: dlg.reject())
        confirmEdit.textChanged.connect(lambda text: setattr(resetBtn, "enabled", text.strip() == "RESET"))
        btnRow.addWidget(resetBtn)
        btnRow.addWidget(cancelBtn)
        layout.addLayout(btnRow)
        if dlg.exec_() != qt.QDialog.Accepted:
            return
        self._restoreSelectionAfter(self._resetSpecimen, specimen, existing)

    def _resetSpecimen(self, specimen, existing):
        """Delete the specimen's saved files (`existing`), close it if it's the active one, and set its status back to untouched."""
        try:
            for path in existing:
                os.remove(path)
                logger.info(f"[GenericSpecimenManager] reset {specimen.label}: deleted {path}")
            if self.logic.active_specimen is specimen:
                self.logic.close_active_specimen(no_question=True)
                self._detachActiveSpecimenObservers()
            self._setSpecimenStatus(specimen, SpecimenStatus.UNTOUCHED)
            self._updatePostInitButtonStates()
            self._refreshSpecimenStatusLabels()
            self._refreshSpecimenAnnotation()
        except Exception as e:
            slicer.util.errorDisplay("Failed to reset specimen: " + str(e))
            import traceback
            traceback.print_exc()

    def _isAutoSaveDBEnabled(self):
        """True iff a study is initialized and its config has auto_save_database on."""
        return bool(self._studyInitialized and self.logic.cfg is not None and self.logic.cfg.auto_save_database)

    def _autoSaveDatabaseIfEnabled(self):
        """If the config's auto_save_database is on, write the database CSV to disk right away - no
        confirmation popup, since this runs silently after every edit (a manual table cell, the
        status dropdown, or a status set on close), not just once on a deliberate click."""
        if self._isAutoSaveDBEnabled():
            self.logic.save_db(inform_user=False)

    def onBtnSaveDB(self):
        """Save the live database table back to its CSV file."""
        try:
            self.logic.save_db()
        except Exception as e:
            slicer.util.errorDisplay("Failed to save database: " + str(e))
            import traceback
            traceback.print_exc()

    def onBtnBatchExport(self):
        """Run the standalone batch_exporter() against this widget's Logic."""
        batch_exporter(self.logic)
