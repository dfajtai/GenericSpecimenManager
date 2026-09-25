"""
specimen_table.py
=================
The specimen table of the main module: rendering, status dropdown + row colors, filters, selection, height fitting,
and the selected/active status dot.
"""

import qt
import slicer
import vtk

from Resources.core.logging_setup import logger
from Resources.definitions import (
    SPECIMEN_STATUS_COLORS,
    SPECIMEN_STATUS_LABELS,
    SPECIMEN_TABLE_MAX_VISIBLE_ROWS,
    SPECIMEN_TABLE_MIN_VISIBLE_ROWS,
    SpecimenStatus,
)


class _ViewportResizeFilter(qt.QObject):
    """Event filter that calls `callback` whenever the watched widget is resized - used to re-fit
    the specimen table when the module panel's scroll-area viewport changes size."""
    def __init__(self, callback, parent=None):
        qt.QObject.__init__(self, parent)
        self._callback = callback

    def eventFilter(self, obj, event):
        if event.type() == qt.QEvent.Resize:
            qt.QTimer.singleShot(0, self._callback)
        return False


class SpecimenTableMixin:
    """Specimen table behaviour of the module widget (mixed into GenericSpecimenManagerWidgetBase)."""

    def showSpecimenTable(self):
        """(Re)draw the specimen table: one row per specimen (optionally filtered to the current
        batch), rows colored by status (SPECIMEN_STATUS_COLORS). The status column is a dropdown of the four statuses. Any column also listed in cfg.factor_columns
        renders as a checkbox (binary) or a level dropdown (multilevel) instead of free text - see
        _onFactorMultilevelChanged() for the dropdown's write-back path (cell widgets don't fire
        itemChanged, so specimenTblChanged() alone doesn't cover them)."""
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        wasModified = self._parameterNode.StartModify()

        cfg = self.logic.cfg
        columns = self._displayColumns()
        keys = sorted(self.logic.specimens.keys())
        if self._group_filter is not None and cfg.group_by_key.enabled:
            col = cfg.group_by_key.column
            keys = [k for k in keys if self.logic.specimens[k].db_info.get(col, "") == self._group_filter]
        if self._status_filter is not None:
            keys = [k for k in keys if self.logic.specimens[k].status in self._status_filter]
        self._displayed_keys = keys

        tbl = self.ui.tblSpecimens
        tbl.clear()
        tbl.clearContents()
        tbl.setColumnCount(len(columns))
        tbl.setRowCount(len(keys))

        # Populating the table below fires itemChanged (checkbox items) and currentTextChanged
        # (multilevel combos) once per cell, exactly like a real user edit would - table_lock
        # blocks specimenTblChanged()/_onFactorMultilevelChanged() from treating this initial
        # fill-in as hundreds of individual edits (and, before this guard, bogus "column not
        # present" warnings for freshly-added factor columns not yet in the live table).
        self.table_lock = True
        try:
            status_col = cfg.status_column
            factor_by_col = {fc.column: fc for fc in cfg.factor_columns}
            for i, key in enumerate(keys):
                specimen = self.logic.specimens[key]
                specimen.update_status(self.logic.dbTable)
                for j, col in enumerate(columns):
                    factor = factor_by_col.get(col)
                    if col == status_col:
                        combo = qt.QComboBox()
                        for st in SpecimenStatus:
                            combo.addItem(SPECIMEN_STATUS_LABELS[st])
                        combo.currentIndex = int(specimen.status)
                        combo.currentIndexChanged.connect(lambda index, r=i: self._onStatusComboChanged(r, index))
                        tbl.setCellWidget(i, j, combo)
                    elif factor is not None and factor.type == "binary":
                        item = qt.QTableWidgetItem()
                        item.setFlags(qt.Qt.ItemIsUserCheckable | qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable)
                        checked = specimen.db_info.get(col) == str(1)
                        item.setCheckState(qt.Qt.Checked if checked else qt.Qt.Unchecked)
                        item.setTextAlignment(qt.Qt.AlignCenter)
                        tbl.setItem(i, j, item)
                    elif factor is not None and factor.type == "multilevel":
                        combo = qt.QComboBox()
                        combo.addItem("(unset)")
                        combo.addItems(factor.levels)
                        current = specimen.db_info.get(col, "") or ""
                        if current and current not in factor.levels:
                            combo.addItem(current)  # value on disk isn't in the configured levels - show it anyway rather than silently dropping it
                        combo.currentText = current if current else "(unset)"
                        combo.currentTextChanged.connect(lambda text, r=i, cn=col: self._onFactorMultilevelChanged(r, cn, text))
                        tbl.setCellWidget(i, j, combo)
                    else:
                        tbl.setItem(i, j, qt.QTableWidgetItem(specimen.db_info.get(col, "")))
                self._applyStatusRowStyle(i, specimen.status)
        finally:
            self.table_lock = False

        tbl.setHorizontalHeaderLabels(["Status" if c == cfg.status_column else c for c in columns])
        tbl.resizeColumnsToContents()
        if self.tbl_selected_key in keys:   # a redraw (filter change etc.) keeps the selected specimen selected
            tbl.selectRow(keys.index(self.tbl_selected_key))
        self._fitSpecimenTableHeight()
        self._refreshSpecimenStatusLabels()
        self._parameterNode.EndModify(wasModified)

    @staticmethod
    def _qtValue(v):
        """PythonQt exposes some Qt getters as plain attributes and others as methods - accept either."""
        return v() if callable(v) else v

    def _findScrollArea(self):
        """The QScrollArea Slicer wraps this module's panel in, if any."""
        w = self._uiWidget.parent() if callable(self._uiWidget.parent) else self._uiWidget.parent
        while w is not None:
            try:
                if w.inherits("QScrollArea"):
                    return w
            except Exception:
                pass
            w = w.parent() if callable(w.parent) else w.parent
        return None

    def _installScrollAreaWatch(self):
        """Re-fit the specimen table whenever the module panel is resized (idempotent)."""
        if getattr(self, "_scrollWatch", None) is not None:
            return
        area = self._findScrollArea()
        if area is None:
            return
        self._scrollWatch = _ViewportResizeFilter(self._fitSpecimenTableHeight, self._uiWidget)
        area.viewport().installEventFilter(self._scrollWatch)
        self._fitSpecimenTableHeight()

    def _availableTableHeight(self):
        """Pixels the specimen table can use without making the whole module panel scroll:
        the panel viewport's height minus everything else in the module's layout. None if the
        panel/scroll area can't be determined (then only the row-count cap applies)."""
        try:
            area = self._findScrollArea()
            if area is None:
                return None
            tbl = self.ui.tblSpecimens
            self._uiWidget.layout().activate()
            others = self._qtValue(self._qtValue(self._uiWidget.sizeHint).height) - self._qtValue(tbl.height)
            return self._qtValue(area.viewport().height) - others - 8
        except Exception as e:
            logger.debug(f"[GenericSpecimenManager] could not measure available table height: {e}")
            return None

    def _fitSpecimenTableHeight(self):
        """Size the specimen table to exactly fit its current row count (header + rows, no empty
        space when there are only a few specimens/after a Group filter) - up to
        SPECIMEN_TABLE_MAX_VISIBLE_ROWS (definitions.py) AND up to the space actually left in the
        module panel, so the WHOLE module never becomes scrollable because of this table; it
        scrolls internally instead. Never below SPECIMEN_TABLE_MIN_VISIBLE_ROWS rows either - even
        empty (before Initialize Study), so the panel doesn't look collapsed.
        Re-run on panel resize and when the Study settings, Specimen browser or Help block is expanded/collapsed."""
        tbl = self.ui.tblSpecimens
        row_h = tbl.verticalHeader().defaultSectionSize
        header_h = tbl.horizontalHeader().height
        pad = 2 * tbl.frameWidth + 4
        fit_h = header_h + row_h * tbl.rowCount + pad
        max_h = header_h + row_h * SPECIMEN_TABLE_MAX_VISIBLE_ROWS + pad
        min_h = header_h + row_h * SPECIMEN_TABLE_MIN_VISIBLE_ROWS + pad
        capped_h = max(min(fit_h, max_h), min_h)   # min_h floor applies even with 0 rows (before Initialize Study)
        # measure "everything else" with the table at its natural (smallest) size first
        tbl.setMinimumHeight(0)
        tbl.setMaximumHeight(16777215)
        available = self._availableTableHeight()
        if available is not None:
            capped_h = min(capped_h, max(available, min_h))
        tbl.setMinimumHeight(int(capped_h))
        tbl.setMaximumHeight(int(capped_h))

    def selectedSpecimenChanged(self):
        """Track which specimen row is currently selected, by KEY (not row index, since row order can change) - used by the Load button."""
        sel = self.ui.tblSpecimens.selectedIndexes()
        if len(sel) == 0:
            return
        row = sel[0].row()
        key_columns = self.logic.cfg.key_columns
        columns = self._displayColumns()
        key = tuple(self.ui.tblSpecimens.item(row, columns.index(c)).text() for c in key_columns)
        self.tbl_selected_key = key
        self._refreshSpecimenStatusLabels()

    @staticmethod
    def _statusDot(color):
        """A small colored bullet, as a rich-text prefix for a status label."""
        return f'<span style="color:{color};">●</span> '

    def _specimenIsDirty(self, specimen):
        """True if this specimen's segmentation and/or markups node has unsaved changes, via the
        standard MRML GetModifiedSinceRead() check (same mechanism GenericSpecimen.save() itself
        uses for images - see _node_has_changed())."""
        for node in (specimen.segmentation_node, specimen.markups_node):
            if node is not None:
                try:
                    if node.GetModifiedSinceRead():
                        return True
                except Exception:
                    pass
        return False

    def _refreshSpecimenStatusLabels(self):
        """Update the colored status dot in front of the Selected/Active specimen labels: gray =
        the selected table row isn't the currently active specimen, green = it is (or this IS the
        Active label) and clean, orange = it is (or Active) with unsaved segmentation/markups
        changes. Called on table selection, after load/save/close, and whenever the active
        specimen's segmentation/markups node fires a Modified event (see
        _attachActiveSpecimenObservers())."""
        active = self.logic.active_specimen if self.logic.hasActiveSpecimen else None
        active_dirty = self._specimenIsDirty(active) if active is not None else False

        if self.tbl_selected_key is not None:
            color = "#999999"
            if active is not None and self.tbl_selected_key == active.key:
                color = "#d98c00" if active_dirty else "#2e8b2e"
            self.ui.lblSelectedSpecimen.text = self._statusDot(color) + "-".join(self.tbl_selected_key)

        if active is not None:
            color = "#d98c00" if active_dirty else "#2e8b2e"
            self.ui.lblActiveSpecimen.text = self._statusDot(color) + active.label
        else:
            self.ui.lblActiveSpecimen.text = ""

    def _attachActiveSpecimenObservers(self):
        """Observe the active specimen's segmentation/markups nodes for Modified events, so the
        status dot flips to 'unsaved changes' live instead of only on the next table click. A
        no-op if already observing this exact specimen."""
        if not self.logic.hasActiveSpecimen:
            return
        specimen = self.logic.active_specimen
        if self._active_specimen_observed is specimen:
            return
        self._detachActiveSpecimenObservers()
        for node in (specimen.segmentation_node, specimen.markups_node):
            if node is not None:
                self.addObserver(node, vtk.vtkCommand.ModifiedEvent, self._onActiveSpecimenNodeModified)
        self._active_specimen_observed = specimen

    def _detachActiveSpecimenObservers(self):
        """Stop observing whatever specimen _attachActiveSpecimenObservers() last wired up - call before/after closing the active specimen."""
        specimen = self._active_specimen_observed
        if specimen is None:
            return
        for node in (specimen.segmentation_node, specimen.markups_node):
            if node is not None:
                self.removeObserver(node, vtk.vtkCommand.ModifiedEvent, self._onActiveSpecimenNodeModified)
        self._active_specimen_observed = None

    def _onActiveSpecimenNodeModified(self, caller=None, event=None):
        self._refreshSpecimenStatusLabels()

    def specimenTblChanged(self, changed_item=None):
        """Write a manually-edited table cell back to the underlying database vtkTable, by column
        NAME + the specimen's real row_index - deliberately not by the widget's row/column
        position, which can differ from the raw CSV's order once the table is sorted/filtered by
        key or batch. Reads row/col straight off the item the itemChanged signal actually handed
        us - NOT off the current table selection, which (since the table moved to whole-row
        selection) no longer reliably identifies which single cell/checkbox was just toggled.
        Covers plain text cells AND checkbox cells (a binary factor column - detected via
        the item's own checkable flag, not a hardcoded column check) - a multilevel factor
        column's dropdown is a cell WIDGET instead, which doesn't fire itemChanged at all; see
        _onFactorMultilevelChanged() for that path. Auto-saves the database CSV to disk right
        after, if Auto-save database is checked."""
        if self.table_lock:
            return
        self.table_lock = True
        try:
            tbl = self.ui.tblSpecimens
            if changed_item is None:
                return
            row, col = changed_item.row(), changed_item.column()
            if row < 0 or col < 0:
                return
            cfg = self.logic.cfg
            columns = self._displayColumns()

            key = self._displayed_keys[row]
            specimen = self.logic.specimens.get(key)
            if specimen is None or specimen.row_index is None:
                return
            col_name = columns[col]
            if col_name not in self.logic.dbColumnNames:
                logger.warning(f"[GenericSpecimenManager] column '{col_name}' not present in database.csv, not writing back")
                return
            real_col = self.logic.dbColumnNames.index(col_name)
            edited_item = tbl.item(row, col)
            if edited_item is not None and bool(edited_item.flags() & qt.Qt.ItemIsUserCheckable):
                val = "1" if edited_item.checkState() == qt.Qt.Checked else "0"
            else:
                val = edited_item.text() if edited_item is not None else ""
            self.logic.dbTable.SetCellText(specimen.row_index, real_col, val)
            specimen.db_info[col_name] = val
            self._autoSaveDatabaseIfEnabled()
            self._refreshSpecimenAnnotation()
        except Exception as e:
            slicer.util.errorDisplay("Failed to update table: " + str(e))
            import traceback
            traceback.print_exc()
        finally:
            self.table_lock = False

    def _applyStatusRowStyle(self, row, status):
        """Color one table row for `status` (SPECIMEN_STATUS_COLORS): every item cell gets the background (with black text, so it stays readable in a dark theme), and the status dropdown cell widget gets the same via stylesheet."""
        r, g, b = SPECIMEN_STATUS_COLORS[status]
        tbl = self.ui.tblSpecimens
        was_locked = self.table_lock
        self.table_lock = True   # recoloring fires itemChanged per cell - not a user edit
        try:
            for j in range(tbl.columnCount):
                item = tbl.item(row, j)
                if item is not None:
                    item.setBackground(qt.QColor(r, g, b))
                    item.setForeground(qt.QColor("black"))
        finally:
            self.table_lock = was_locked
        idx = self._statusColumnIndex()
        combo = tbl.cellWidget(row, idx) if idx is not None else None
        if combo is not None:
            combo.setStyleSheet(f"QComboBox {{ background-color: rgb({r},{g},{b}); color: black; }}")

    def _displayColumns(self):
        """The specimen table's columns, by database.csv column name: cfg.table_columns without the status column, then the status column always LAST (whatever it's called in the CSV, e.g. 'done') - shown under the header 'Status' and not optional."""
        cfg = self.logic.cfg
        return [c for c in cfg.table_columns if c != cfg.status_column] + [cfg.status_column]

    def _statusColumnIndex(self):
        """Display index of the status column in the specimen table - always the last one."""
        return len(self._displayColumns()) - 1

    def _refreshStatusCell(self, specimen):
        """Update the displayed status dropdown + row color of one specimen in place (no table rebuild, so the row selection survives). No-op if the specimen isn't currently displayed."""
        if specimen.key not in self._displayed_keys:
            return
        row = self._displayed_keys.index(specimen.key)
        idx = self._statusColumnIndex()
        if idx is not None:
            combo = self.ui.tblSpecimens.cellWidget(row, idx)
            if combo is not None:
                combo.blockSignals(True)
                combo.currentIndex = int(specimen.status)
                combo.blockSignals(False)
        self._applyStatusRowStyle(row, specimen.status)

    def _setSpecimenStatus(self, specimen, status, only_raise=False):
        """Set a specimen's status (see Logic.set_specimen_status), refresh its table row, and auto-save the database if that's on."""
        if not self.logic.set_specimen_status(specimen, status, only_raise=only_raise):
            return
        self._refreshStatusCell(specimen)
        self._autoSaveDatabaseIfEnabled()
        self._refreshSpecimenAnnotation()

    def _restoreSelection(self, key):
        """Re-select the row of the specimen with `key`, if it's still displayed."""
        if key in self._displayed_keys:
            self.ui.tblSpecimens.selectRow(self._displayed_keys.index(key))

    def _selectRowOf(self, specimen):
        """Select the table row of `specimen` (if displayed) - a cell widget like the status dropdown doesn't select its own row when used, so without this an edit leaves the selection wherever it was."""
        if specimen.key in self._displayed_keys:
            self.ui.tblSpecimens.selectRow(self._displayed_keys.index(specimen.key))

    def _onStatusComboChanged(self, row, index):
        """Write-back for a manual pick in the status dropdown (a cell WIDGET, so itemChanged never fires for it)."""
        if self.table_lock or row >= len(self._displayed_keys):
            return
        specimen = self.logic.specimens.get(self._displayed_keys[row])
        if specimen is not None:
            self._selectRowOf(specimen)
            self._setSpecimenStatus(specimen, SpecimenStatus(index))

    def _onFactorMultilevelChanged(self, row, col_name, text):
        """Write-back for a multilevel factor column's dropdown (a QComboBox cell WIDGET, wired
        directly in showSpecimenTable() since cell widgets never fire the table's itemChanged
        signal) - writes the level's exact text to the CSV ("(unset)" -> empty string), the same
        row_index-based path specimenTblChanged() uses for everything else."""
        if self.table_lock:
            return
        self.table_lock = True
        try:
            if row >= len(self._displayed_keys):
                return
            key = self._displayed_keys[row]
            specimen = self.logic.specimens.get(key)
            if specimen is None or specimen.row_index is None:
                return
            if col_name not in self.logic.dbColumnNames:
                logger.warning(f"[GenericSpecimenManager] column '{col_name}' not present in database.csv, not writing back")
                return
            self._selectRowOf(specimen)
            val = "" if text == "(unset)" else text
            real_col = self.logic.dbColumnNames.index(col_name)
            self.logic.dbTable.SetCellText(specimen.row_index, real_col, val)
            specimen.db_info[col_name] = val
            self._autoSaveDatabaseIfEnabled()
            self._refreshSpecimenAnnotation()
        except Exception as e:
            slicer.util.errorDisplay("Failed to update table: " + str(e))
            import traceback
            traceback.print_exc()
        finally:
            self.table_lock = False

    def _setupBatchCombo(self):
        """Show/hide the group-select row and (re)populate its combo box from cfg.group_by_key, based on the just-initialized specimen list."""
        self.ui.wStatusFilter.visible = bool(self.logic.cfg.status_filter.enabled)
        self._checkAllStatusFilter()
        gbk_cfg = self.logic.cfg.group_by_key
        self.ui.wGroupByKey.visible = bool(gbk_cfg.enabled)
        if not gbk_cfg.enabled:
            return
        values = self.logic.group_by_key_values()
        self.ui.cmbGroupByKey.blockSignals(True)
        self.ui.cmbGroupByKey.clear()
        self.ui.cmbGroupByKey.addItem("(all)")
        for v in values:
            self.ui.cmbGroupByKey.addItem(v)
        self.ui.cmbGroupByKey.blockSignals(False)

    def _checkAllStatusFilter(self):
        """Tick every status in the status filter (= no filtering), without re-filtering the table for each tick."""
        combo = self.ui.cmbStatusFilter
        combo.blockSignals(True)
        for i in range(len(SpecimenStatus)):
            combo.setCheckState(combo.model().index(i, 0), qt.Qt.Checked)
        combo.blockSignals(False)
        self._status_filter = None

    def onStatusFilterChanged(self):
        """Re-filter the specimen table by the statuses ticked in the status filter (all ticked = no filtering)."""
        ticked = {SpecimenStatus(idx.row()) for idx in self.ui.cmbStatusFilter.checkedIndexes()}
        self._status_filter = None if len(ticked) == len(SpecimenStatus) else ticked
        if self.logic is not None and self.logic.cfg is not None and self._studyInitialized:
            self.showSpecimenTable()

    def onGroupByKeyChanged(self, text):
        """Re-filter the specimen table by the newly selected batch value. Refuses (and reverts the combo back) while a specimen is currently active."""
        if self.logic.hasActiveSpecimen:
            slicer.util.errorDisplay("Close the active specimen before switching group.")
            self.ui.cmbGroupByKey.blockSignals(True)
            self.ui.cmbGroupByKey.currentText = self._group_filter or "(all)"
            self.ui.cmbGroupByKey.blockSignals(False)
            return
        self._group_filter = None if text == "(all)" else text
        self.showSpecimenTable()
