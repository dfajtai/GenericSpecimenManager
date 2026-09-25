"""
general_tab.py
==============
General tab: study files, specimens, filtering, factor columns.
"""

import os

import qt

from Resources.core.config_model import normalize_output_dir_pattern
from Resources.gui.config_editor.helpers import csv_list, guess_key_columns, read_csv_header
from Resources.gui.config_editor.popups import TextPopup


class GeneralTabMixin:
    """General tab: study files, specimens, filtering, factor columns."""


    def _buildGeneralTab(self):
        """Study/database/preseg paths, key/table/output-dir columns, and batch mode."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)

        def new_group(title):
            group = qt.QGroupBox(title)
            layout.addWidget(group)
            return qt.QFormLayout(group)

        form = new_group("Study files")
        self.studyDirEdit, studyDirRow = self._fileRow(directory=True)
        self.studyDirEdit.setPlaceholderText("default: preseg CSV's folder")
        self.studyDirEdit.setToolTip(
            "Base folder every relative path in the config resolves against. Optional, but set this "
            "FIRST if you're going to set it at all - the two CSV pickers below show their path "
            "relative to whatever Study dir already contains at the moment you browse, so setting it "
            "afterward won't retroactively shorten paths you already picked. Leave empty to default "
            "to the preseg CSV's own folder.")
        form.addRow("Study dir (optional, set first):", studyDirRow)

        self.presegEdit, presegRow = self._fileRow(
            on_change=self._onPresegChanged,
            relative_to=lambda: self.studyDirEdit.text.strip())
        self.presegEdit.setToolTip("Shown relative to Study dir above if that's set - hover for the full path.")
        self.presegEdit.editingFinished.connect(
            lambda: self._onPresegChanged(self._resolveCsvPath(self.presegEdit.text)))
        form.addRow("Images / preseg CSV:", presegRow)
        self.dbEdit, dbRow = self._fileRow(
            relative_to=lambda: self.studyDirEdit.text.strip() or os.path.dirname(self._preseg_abs_path or ""))
        self.dbEdit.setToolTip("Shown relative to Study dir above (or to the preseg CSV's folder if Study dir is empty) - hover for the full path.")
        form.addRow("Database CSV:", dbRow)
        self.chkAutoSaveDb = qt.QCheckBox("Auto-save database")
        self.chkAutoSaveDb.setToolTip("Writes database.csv to disk after every table edit; the main module then hides its Save database CSV button.")
        form.addRow(self.chkAutoSaveDb)

        showColsBtn = qt.QPushButton("Show CSV columns (copyable)...")
        showColsBtn.setToolTip("Reads the header row of both CSVs above and lists all columns - copy names from here into the fields below/Images tab.")
        showColsBtn.connect('clicked(bool)', lambda checked=False: self._onShowCsvColumns())
        form.addRow(showColsBtn)

        form = new_group("Specimens")
        self.keyColumnsEdit = qt.QLineEdit()
        self.keyColumnsEdit.setPlaceholderText("comma-separated, e.g. ID,measurement")
        self.keyColumnsEdit.setToolTip(
            "The composite specimen ID. MUST exist, with matching values, in BOTH CSVs above - "
            "use 'Show CSV columns...' to see which column names are common to both (likely candidates).")
        form.addRow("Key columns:", self.keyColumnsEdit)
        self.statusColumnEdit = qt.QLineEdit("status")
        self.statusColumnEdit.setToolTip(
            "<html>database.csv column holding each specimen's status (created if missing):<br>"
            "&bull; 0 untouched<br>&bull; 1 in progress<br>&bull; 2 to review<br>&bull; 3 finished<br>"
            "The column can have any name (e.g. 'done'). Always shown as the table's last column, headed 'Status', as a dropdown; colors the row. Batch export only processes 'finished'.</html>")
        form.addRow("Status column:", self.statusColumnEdit)
        self.tableColumnsEdit = qt.QLineEdit()
        self.tableColumnsEdit.setPlaceholderText("comma-separated database.csv columns shown in the table")
        self.tableColumnsEdit.setToolTip("Which database.csv columns appear (and are editable) in the main module's specimen table. Any column works, not just status.")
        form.addRow("Table columns:", self.tableColumnsEdit)
        self.outputDirPatternEdit = qt.QLineEdit()
        self.outputDirPatternEdit.setPlaceholderText("e.g. {ID}/{measurement}")
        self.outputDirPatternEdit.setToolTip(
            "<html>Builds each specimen's OWN output folder for interactive work (segmentation/"
            "markups/saved images), under study_dir.<br>"
            "Placeholder:<br>"
            "&bull; {column} - any key/database.csv/preseg.csv column value, e.g. {ID}/{measurement} "
            "-> study_dir/D001/baseline/<br>"
            "A shorter pattern (just {ID}) puts every measurement of the same specimen into one "
            "shared folder - only do this if two rows with the same ID but different measurement "
            "overwriting each other's files is actually what you want.<br>"
            "Empty -> your Key columns, in order.<br>"
            "See Help for more.</html>")
        form.addRow("Output dir pattern:", self.outputDirPatternEdit)

        form = new_group("Filtering")
        self.chkGroupByKey = qt.QCheckBox("Group specimens by key")
        self.chkGroupByKey.setToolTip(
            "Shows a group-select combo in the main module after Initialize Study, to browse/filter "
            "the specimen table by the key column below. This is purely a main-module VIEWING "
            "convenience - it does NOT affect the Batch Export tab, which only needs the Group-by "
            "key set (its Segment export pattern/Report pattern/Markup summary pattern fields can "
            "reference it directly).")
        self.groupByKeyColumnEdit = qt.QLineEdit()
        self.groupByKeyColumnEdit.setPlaceholderText("database.csv column to group/filter by, e.g. batch")
        groupRow = qt.QHBoxLayout()
        groupRow.addWidget(self.chkGroupByKey, 1)          # 1 : 3 - checkbox : key column
        groupRow.addWidget(self.groupByKeyColumnEdit, 3)
        form.addRow(groupRow)
        self.chkStatusFilter = qt.QCheckBox("Filter by status")
        self.chkStatusFilter.checked = True
        self.chkStatusFilter.setToolTip(
            "Shows a status checklist above the main module's specimen table, to show only the "
            "specimens in the ticked statuses. A main-module VIEWING convenience only - Batch export "
            "ignores it (it always processes 'finished' specimens). On by default.")
        form.addRow(self.chkStatusFilter)

        form = new_group("Factor columns")

        self.factorColumnsTable = qt.QTableWidget(0, 3)
        factor_headers = ["Column", "Type", "Levels (multilevel only)"]
        factor_tips = [
            "database.csv column name to treat as a factor, instead of free text.",
            "binary: renders as a checkbox (0/1) in the main module's specimen table. multilevel: renders as a dropdown of the Levels column.",
            "Comma-separated level values, e.g. control,low,high - written to the CSV as the exact text (never a numeric index), so the file stays readable by anything else too.",
        ]
        self.factorColumnsTable.setHorizontalHeaderLabels(factor_headers)
        for col, tip in enumerate(factor_tips):
            hitem = self.factorColumnsTable.horizontalHeaderItem(col)
            if hitem:
                hitem.setToolTip(tip)
        self.factorColumnsTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.factorColumnsTable.horizontalHeader().setSectionResizeMode(2, qt.QHeaderView.Stretch)
        form.addRow(self.factorColumnsTable)

        factorBtnRow = qt.QHBoxLayout()
        addFactorBtn = qt.QPushButton("Add factor column")
        addFactorBtn.connect('clicked(bool)', lambda checked=False: self._onAddFactorColumn())
        removeFactorBtn = qt.QPushButton("Remove selected")
        removeFactorBtn.connect('clicked(bool)', lambda checked=False: self._onRemoveFactorColumn())
        factorBtnRow.addWidget(addFactorBtn)
        factorBtnRow.addWidget(removeFactorBtn)
        factorBtnRow.addStretch(1)
        form.addRow(factorBtnRow)

        layout.addStretch(1)
        return w

    def _addFactorColumnRow(self, d):
        """Append one row to the Factor columns table (column name/type/comma-separated levels)."""
        row = self.factorColumnsTable.rowCount
        self.factorColumnsTable.insertRow(row)
        self.factorColumnsTable.setItem(row, 0, qt.QTableWidgetItem(d.get("column", "")))
        typeCombo = qt.QComboBox()
        typeCombo.addItems(["binary", "multilevel"])
        typeCombo.currentText = d.get("type", "binary") or "binary"
        typeCombo.currentIndexChanged.connect(self._markDirty)
        self.factorColumnsTable.setCellWidget(row, 1, typeCombo)
        self.factorColumnsTable.setItem(row, 2, qt.QTableWidgetItem(",".join(d.get("levels") or [])))
        self._markDirty()

    def _onAddFactorColumn(self):
        """Add one blank factor column row."""
        self._addFactorColumnRow({})

    def _onRemoveFactorColumn(self):
        """Remove the selected factor column row(s)."""
        rows = sorted(set(i.row() for i in self.factorColumnsTable.selectedIndexes()), reverse=True)
        for r in rows:
            self.factorColumnsTable.removeRow(r)
        self._markDirty()

    def _readFactorColumnRows(self):
        """Read the Factor columns table into a list of factor_columns[] entries, skipping rows with no column name. multilevel rows with no levels typed in still get written (an empty dropdown just means only the '(unset)' entry shows up in the main module until levels are added)."""
        entries = []
        for row in range(self.factorColumnsTable.rowCount):
            item = self.factorColumnsTable.item(row, 0)
            column = (item.text().strip() if item else "")
            if not column:
                continue
            typeCombo = self.factorColumnsTable.cellWidget(row, 1)
            ftype = (typeCombo.currentText or "binary") if typeCombo else "binary"
            entry = {"column": column, "type": ftype}
            if ftype == "multilevel":
                levels_item = self.factorColumnsTable.item(row, 2)
                levels = csv_list(levels_item.text() if levels_item else "")
                if levels:
                    entry["levels"] = levels
            entries.append(entry)
        return entries

    def _resolveCsvPath(self, text):
        """Resolve a (possibly study-dir-relative) path field to a real
        filesystem path for reading - works whether the value got there via
        Browse (already handled in _fileRow) or manual typing/pasting,
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

        preseg_path = self._resolveCsvPath(preseg_text)
        db_path = self._resolveCsvPath(db_text)
        preseg_header = read_csv_header(preseg_path) if preseg_path else []
        db_header = read_csv_header(db_path) if db_path else []
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

        popup = TextPopup(self, "CSV columns", "\n".join(lines))
        popup.exec_()

        if not self.keyColumnsEdit.text.strip() and common:
            self.keyColumnsEdit.text = ",".join(guess_key_columns(common) or common[:1])

    def _onPresegChanged(self, path):
        """Refresh everything that depends on the preseg CSV's header: the quick-add column table (Images tab, key columns excluded) and, if Key Columns is still empty, a best-effort guess."""
        self._preseg_abs_path = path
        header = read_csv_header(path)
        if hasattr(self, "quickColumnsTable"):
            self.quickColumnsTable.setRowCount(0)
            key_cols = set(csv_list(self.keyColumnsEdit.text))
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
            guessed = guess_key_columns(header)
            if guessed:
                self.keyColumnsEdit.text = ",".join(guessed)

    def _populateGeneral(self, cfg):
        """Fill the General tab from the raw config dict `cfg`."""
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
        self.statusColumnEdit.text = cfg.get("status_column", "status")
        self.tableColumnsEdit.text = ",".join(cfg.get("table_columns", []))
        self.outputDirPatternEdit.text = normalize_output_dir_pattern(cfg.get("output_dir_pattern"), []) if cfg.get("output_dir_pattern") else ""

        self.chkStatusFilter.checked = bool((cfg.get("status_filter", {}) or {}).get("enabled", True))
        gbk = cfg.get("group_by_key", {}) or {}
        self.chkGroupByKey.checked = bool(gbk.get("enabled"))
        self.chkAutoSaveDb.checked = bool(cfg.get("auto_save_database", False))
        self.groupByKeyColumnEdit.text = gbk.get("column", "") or ""

        for fc in cfg.get("factor_columns", []) or []:
            self._addFactorColumnRow(fc)


    def _collectGeneral(self, cfg):
        """Write the General tab's part of the config into the dict `cfg` (key order = file order)."""
        cfg.update({
            "study_dir": self.studyDirEdit.text.strip() or os.path.dirname(self.presegEdit.text.strip()) or ".",
            "database_csv_path": self.dbEdit.text.strip(),
            "preseg_csv_path": self.presegEdit.text.strip(),
            "key_columns": csv_list(self.keyColumnsEdit.text) or ["ID"],
            "status_column": self.statusColumnEdit.text.strip() or "status",
        })
        table_cols = csv_list(self.tableColumnsEdit.text)
        cfg["table_columns"] = table_cols or (cfg["key_columns"] + [cfg["status_column"]])
        out_pattern = self.outputDirPatternEdit.text.strip()
        if out_pattern:
            cfg["output_dir_pattern"] = out_pattern

        if self.chkAutoSaveDb.checked:
            cfg["auto_save_database"] = True

        if not self.chkStatusFilter.checked:
            cfg["status_filter"] = {"enabled": False}   # on is the default, so only the off state is written
        if self.chkGroupByKey.checked:
            cfg["group_by_key"] = {"enabled": True, "column": self.groupByKeyColumnEdit.text.strip()}

        factor_columns = self._readFactorColumnRows()
        if factor_columns:
            cfg["factor_columns"] = factor_columns


    def _clearGeneral(self):
        """Reset the General tab to its blank/default state."""
        self._preseg_abs_path = ""
        for edit in (self.presegEdit, self.dbEdit, self.studyDirEdit, self.keyColumnsEdit, self.tableColumnsEdit,
                     self.outputDirPatternEdit, self.groupByKeyColumnEdit):
            edit.text = ""
        self.statusColumnEdit.text = "status"
        for chk in (self.chkGroupByKey, self.chkAutoSaveDb):
            chk.checked = False
        self.chkStatusFilter.checked = True
        self.factorColumnsTable.setRowCount(0)
