"""
images_tab.py
=============
Images tab: the images[] table, quick add, advanced popup, effective-settings preview.
"""

import json

import qt

from Resources.definitions import (
    COLOR_TABLE_CHOICES,
    IMAGES_PREVIEW_VISIBLE_LINES,
    ROLE_CHOICES,
    TYPE_CHOICES,
    UNSET,
)
from Resources.gui.config_editor.helpers import combo_value, set_combo_value, to_float
from Resources.gui.config_editor.popups import ImageAdvancedPopup


class ImagesTabMixin:
    """Images tab: the images[] table, quick add, advanced popup, effective-settings preview."""


    def _buildImagesTab(self):
        """The main images[] table (quick-add from preseg columns is a popup, see _onOpenQuickAdd) + the live 'Effective settings' preview for whichever row is selected."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)

        # Quick add lives in a modal popup (built once, refilled whenever the preseg CSV changes)
        # so the images table below gets the whole tab.
        self._quickAddDialog = qt.QDialog(self)
        self._quickAddDialog.setWindowTitle("Quick add images from preseg columns")
        self._quickAddDialog.resize(420, 480)
        quickLayout = qt.QVBoxLayout(self._quickAddDialog)
        quickHint = qt.QLabel("From the preseg CSV header. Check <b>Add</b> for the columns to add as image rows; check <b>Labelmap</b> if that column is a mask/label image.")
        quickHint.setWordWrap(True)
        quickLayout.addWidget(quickHint)
        self.quickColumnsTable = qt.QTableWidget(0, 3)
        self.quickColumnsTable.setHorizontalHeaderLabels(["Column", "Add", "Labelmap"])
        self.quickColumnsTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        quickLayout.addWidget(self.quickColumnsTable, 1)
        quickButtons = qt.QHBoxLayout()
        quickButtons.addStretch(1)
        quickAddBtn = qt.QPushButton("Add checked columns")
        quickAddBtn.connect('clicked(bool)', lambda checked=False: self._onQuickAddImages())
        quickCloseBtn = qt.QPushButton("Close")
        quickCloseBtn.connect('clicked(bool)', lambda checked=False: self._quickAddDialog.reject())
        quickButtons.addWidget(quickAddBtn)
        quickButtons.addWidget(quickCloseBtn)
        quickLayout.addLayout(quickButtons)

        imgHint = qt.QLabel(
            "One row per image. The file comes from the row's CSV column when that has a value for the "
            "specimen; otherwise from the Default path pattern below - so an image that is NOT in the preseg "
            "CSV can be added as a name-only row. The 'Advanced' column summarizes path pattern/window/level/"
            "threshold/interpolate for that row, if set.")
        imgHint.setWordWrap(True)
        layout.addWidget(imgHint)

        defaultPatternRow = qt.QHBoxLayout()
        defaultPatternRow.addWidget(qt.QLabel("Default path pattern:"))
        self.imgDefaultPathPatternEdit = qt.QLineEdit()
        self.imgDefaultPathPatternEdit.setPlaceholderText("e.g. {ID}/{measurement}/{name}.nii.gz")
        self.imgDefaultPathPatternEdit.setToolTip(
            "<html>Fallback for every image whose CSV column is empty (or not set) for a specimen "
            "(defaults.image.path_pattern):<br>"
            "&bull; {column} - any key/database.csv/preseg.csv column value<br>"
            "&bull; {name} - the image row's Name<br>"
            "Relative to Study dir. See Help for more.</html>")
        self.imgDefaultPathPatternEdit.textChanged.connect(self._refreshPreviewIfSelected)
        defaultPatternRow.addWidget(self.imgDefaultPathPatternEdit, 1)
        layout.addLayout(defaultPatternRow)

        self.imgTable = qt.QTableWidget(0, 9)
        headers = ["Name", "CSV column", "Type", "Role", "Required", "Preset", "Opacity", "Color table", "Advanced"]
        header_tips = [
            "Logical name used elsewhere (reference_image, presets, roles) - and {name} in the path pattern.",
            "preseg.csv column holding this image's relative path. Leave empty (or name a column that isn't there) to use the Default path pattern.",
            "'volume' (default) or 'labelmap'.",
            "background/label/foreground control slice-view layers; (none) = loaded but not shown as a layer.",
            "If missing/unloadable, initializing the specimen raises an error instead of skipping.",
            "Name of a presets[] entry (Defaults / Presets tab) to inherit visual properties from.",
            "0-1, used when Role is label or foreground.",
            "Slicer color node ID or name, e.g. Grey, Rainbow, vtkMRMLColorTableNodeRed.",
            "Read-only summary of path pattern/window_level/threshold/interpolate set via 'Edit advanced...' below.",
        ]
        self.imgTable.setHorizontalHeaderLabels(headers)
        for col, tip in enumerate(header_tips):
            hitem = self.imgTable.horizontalHeaderItem(col)
            if hitem:
                hitem.setToolTip(tip)
        self.imgTable.horizontalHeader().setSectionResizeMode(0, qt.QHeaderView.Stretch)
        self.imgTable.itemSelectionChanged.connect(self._onImageRowSelected)
        layout.addWidget(self.imgTable, 1)

        btnRow = qt.QHBoxLayout()
        addBtn = qt.QPushButton("Add image")
        addBtn.connect('clicked(bool)', lambda checked=False: self._onAddImage())
        removeBtn = qt.QPushButton("Remove selected")
        removeBtn.connect('clicked(bool)', lambda checked=False: self._onRemoveImage())
        advBtn = qt.QPushButton("Edit advanced...")
        advBtn.setToolTip("Opens a form for the SELECTED row's path pattern, window/level, threshold, and interpolate settings.")
        advBtn.connect('clicked(bool)', lambda checked=False: self._onEditImageAdvanced())
        quickBtn = qt.QPushButton("Quick add from preseg columns...")
        quickBtn.setToolTip("Pick image columns from the preseg CSV header in a popup and add them as rows.")
        quickBtn.connect('clicked(bool)', lambda checked=False: self._onOpenQuickAdd())
        btnRow.addWidget(quickBtn)
        btnRow.addWidget(addBtn)
        btnRow.addWidget(removeBtn)
        btnRow.addWidget(advBtn)
        btnRow.addStretch(1)
        layout.addLayout(btnRow)

        previewGroup = qt.QGroupBox("Effective settings of the selected row (defaults.image -> preset -> row, last wins)")
        previewLayout = qt.QVBoxLayout(previewGroup)
        self.imgPreviewEdit = qt.QPlainTextEdit()
        self.imgPreviewEdit.setReadOnly(True)
        self.imgPreviewEdit.setLineWrapMode(qt.QPlainTextEdit.NoWrap)
        line_height = self.imgPreviewEdit.fontMetrics().lineSpacing
        line_height = line_height() if callable(line_height) else line_height
        self.imgPreviewEdit.setFixedHeight(int(line_height) * IMAGES_PREVIEW_VISIBLE_LINES + 14)
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
        self._refreshImagePreview(row)

    def _refreshPreviewIfSelected(self):
        """Re-run the Effective Settings preview for whatever row is currently selected - used as the handler when defaults.image/presets JSON changes, since those affect the merge result even though no row itself was touched."""
        row = self.imgTable.currentRow()
        if row >= 0:
            self._refreshImagePreview(row)

    def _refreshImagePreview(self, row):
        """Recompute and render the Effective Settings preview text for one row: its own fields, the matched preset (if any), defaults.image, and the final merged result."""
        own, defaults, preset, preset_name, effective = self._computeEffectiveImage(row)
        lines = [f"EFFECTIVE (what applies): {json.dumps(effective)}"]
        lines.append(f"1) defaults.image:        {json.dumps(defaults) if defaults else '(empty)'}")
        if preset_name:
            lines.append(f"2) preset '{preset_name}':  {json.dumps(preset) if preset else '(not found in presets JSON)'}")
        else:
            lines.append("2) preset:                 (none selected on this row)")
        lines.append(f"3) this row's own fields:  {json.dumps(own)}")
        self.imgPreviewEdit.plainText = "\n".join(lines)

    def _computeEffectiveImage(self, row):
        """Merge defaults.image -> preset (if the row names one) -> the row's
        own fields, exactly like the engine does at runtime. Returns
        (own, defaults, preset, preset_name, effective)."""
        own = self._readImageRow(row) or {}
        try:
            defaults = json.loads(self.defaultsImageEdit.plainText or "{}")
        except Exception:
            defaults = {}
        if self.imgDefaultPathPatternEdit.text.strip():
            defaults["path_pattern"] = self.imgDefaultPathPatternEdit.text.strip()
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
                self._addImageRow(d)
                addItem.setCheckState(qt.Qt.Unchecked)
                added += 1
        if added == 0:
            qt.QMessageBox.information(self._quickAddDialog, "Config Editor", "Check 'Add' for at least one column first.")
            return
        if hasattr(self, "vrTable"):
            self._refreshVrTable()
        self._quickAddDialog.accept()

    def _onOpenQuickAdd(self):
        """Show the quick-add popup (modal) - or explain what's missing if the preseg CSV hasn't been read yet."""
        if self.quickColumnsTable.rowCount == 0:
            qt.QMessageBox.information(self, "Config Editor", "No columns to offer yet - set the preseg CSV on the General tab first (key columns are left out).")
            return
        self._quickAddDialog.exec_()

    def _addImageRow(self, d):
        """Append one row to the images table from a dict (name/csv_column/.../color_table/path_pattern/window_level/threshold/interpolate): builds the Type/Role/Preset/Color-table combo cells, the Required checkbox, and stashes path_pattern/window_level/threshold/interpolate in the parallel _image_advanced list (there's no visible column for those - see 'Advanced')."""
        row = self.imgTable.rowCount
        self.imgTable.insertRow(row)
        self.imgTable.setItem(row, 0, qt.QTableWidgetItem(d.get("name", "")))
        self.imgTable.setItem(row, 1, qt.QTableWidgetItem(d.get("csv_column", "")))

        typeCombo = qt.QComboBox()
        typeCombo.addItems(TYPE_CHOICES)
        typeCombo.currentText = d.get("type", "volume")
        typeCombo.currentIndexChanged.connect(self._markDirty)
        self.imgTable.setCellWidget(row, 2, typeCombo)

        roleCombo = qt.QComboBox()
        roleCombo.addItems(ROLE_CHOICES)
        roleCombo.currentText = d.get("role") or "(none)"
        roleCombo.currentIndexChanged.connect(self._markDirty)
        self.imgTable.setCellWidget(row, 3, roleCombo)

        reqItem = qt.QTableWidgetItem()
        reqItem.setFlags(qt.Qt.ItemIsUserCheckable | qt.Qt.ItemIsEnabled | qt.Qt.ItemIsSelectable)
        reqItem.setCheckState(qt.Qt.Checked if d.get("required") else qt.Qt.Unchecked)
        self.imgTable.setItem(row, 4, reqItem)

        presetCombo = qt.QComboBox()
        presetCombo.addItem(UNSET)
        presetCombo.addItems(self._getPresetNames())
        wanted_preset = d.get("preset", "")
        if wanted_preset and wanted_preset not in self._getPresetNames():
            presetCombo.addItem(wanted_preset)  # keep an unknown/not-yet-defined preset name visible rather than losing it
        set_combo_value(presetCombo, wanted_preset)
        presetCombo.currentIndexChanged.connect(self._markDirty)
        self.imgTable.setCellWidget(row, 5, presetCombo)

        self.imgTable.setItem(row, 6, qt.QTableWidgetItem("" if d.get("opacity") is None else str(d.get("opacity"))))

        colorCombo = qt.QComboBox()
        colorCombo.setEditable(True)
        colorCombo.addItems(COLOR_TABLE_CHOICES)
        wanted_color = d.get("color_table", "")
        if wanted_color and wanted_color not in COLOR_TABLE_CHOICES:
            colorCombo.addItem(wanted_color)
        set_combo_value(colorCombo, wanted_color)
        colorCombo.currentIndexChanged.connect(self._markDirty)
        self.imgTable.setCellWidget(row, 7, colorCombo)

        advItem = qt.QTableWidgetItem("")
        advItem.setFlags(advItem.flags() & ~qt.Qt.ItemIsEditable)
        self.imgTable.setItem(row, 8, advItem)

        adv = {k: d[k] for k in ("path_pattern", "window_level", "threshold", "interpolate") if k in d}
        self._image_advanced.insert(row, adv)
        self._updateAdvancedIndicator(row)
        self._markDirty()

    def _refreshAllPresetCombos(self):
        """Re-populate every row's Preset dropdown when presets JSON changes,
        preserving each row's current selection if it's still a valid name."""
        if not hasattr(self, "imgTable"):
            return
        names = self._getPresetNames()
        for row in range(self.imgTable.rowCount):
            combo = self.imgTable.cellWidget(row, 5)
            if combo is None:
                continue
            current = combo_value(combo)
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(UNSET)
            combo.addItems(names)
            if current and current not in names:
                combo.addItem(current)
            set_combo_value(combo, current)
            combo.blockSignals(False)

    def _summarizeAdvanced(self, adv):
        """One-line human summary of a row's advanced dict (path pattern, window/level, threshold, interpolate), shown in the Advanced column and its tooltip."""
        if not adv:
            return ""
        parts = []
        if adv.get("path_pattern"):
            parts.append(f"path:{adv['path_pattern']}")
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

    def _updateAdvancedIndicator(self, row):
        """Refresh one row's Advanced-column summary text plus the highlight/tooltip on its Name cell, after that row's advanced dict changes."""
        nameItem = self.imgTable.item(row, 0)
        advItem = self.imgTable.item(row, 8)
        adv = self._image_advanced[row] if row < len(self._image_advanced) else {}
        summary = self._summarizeAdvanced(adv)
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
        self._addImageRow({})
        if hasattr(self, "vrTable"):
            self._refreshVrTable()

    def _onRemoveImage(self):
        """Remove the selected image row(s), keeping the parallel _image_advanced list in sync (same indices), then re-sync the Volume Rendering table's image list."""
        rows = sorted(set(i.row() for i in self.imgTable.selectedIndexes()), reverse=True)
        for r in rows:
            self.imgTable.removeRow(r)
            if 0 <= r < len(self._image_advanced):
                del self._image_advanced[r]
        self._markDirty()
        if hasattr(self, "vrTable"):
            self._refreshVrTable()

    def _onEditImageAdvanced(self):
        """Open the structured window_level/threshold/interpolate popup for the selected row and apply the result."""
        row = self.imgTable.currentRow()
        if row < 0:
            qt.QMessageBox.information(self, "Config Editor", "Select an image row first.")
            return
        popup = ImageAdvancedPopup(self, self._image_advanced[row])
        if popup.exec_():
            self._image_advanced[row] = popup.resultDict()
            self._updateAdvancedIndicator(row)
            self._refreshImagePreview(row)
            self._markDirty()

    def _readImageRow(self, row):
        """Return the raw (unmerged) dict for one image row, or None if it has no name."""
        d = {}
        name = self.imgTable.item(row, 0).text().strip()
        if not name:
            return None
        d["name"] = name
        csv_column = self.imgTable.item(row, 1).text().strip()
        if csv_column:
            d["csv_column"] = csv_column
        d["type"] = self.imgTable.cellWidget(row, 2).currentText
        role = self.imgTable.cellWidget(row, 3).currentText
        if role != "(none)":
            d["role"] = role
        if self.imgTable.item(row, 4).checkState() == qt.Qt.Checked:
            d["required"] = True
        preset = combo_value(self.imgTable.cellWidget(row, 5))
        if preset:
            d["preset"] = preset
        opacity = to_float(self.imgTable.item(row, 6).text())
        if opacity is not None:
            d["opacity"] = opacity
        color_table = combo_value(self.imgTable.cellWidget(row, 7))
        if color_table:
            d["color_table"] = color_table
        if row < len(self._image_advanced):
            d.update(self._image_advanced[row])
        return d

    def _readImageRows(self):
        """Read every named image row into the final images[] list (via _readImageRow per row)."""
        images = []
        for row in range(self.imgTable.rowCount):
            d = self._readImageRow(row)
            if d is not None:
                images.append(d)
        return images

    def _getImageNames(self):
        """Every non-empty Name in the Images tab table (pattern-mode rows, which have no fixed literal name, are skipped)."""
        names = []
        for row in range(self.imgTable.rowCount):
            item = self.imgTable.item(row, 0)
            name = (item.text().strip() if item else "")
            if name:
                names.append(name)
        return names

    def _refreshReferenceImageChoices(self):
        """Refill the two Reference image dropdowns (Segmentation and Batch export tabs) with the Images tab's names, keeping whatever is currently selected/typed - even a name that isn't in the table (yet)."""
        names = self._getImageNames()
        for combo in (self.segReferenceImageEdit, self.beReferenceImageEdit):
            current = combo.currentText
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            combo.currentText = current
            combo.blockSignals(False)
            combo.lineEdit().setPlaceholderText(UNSET)   # empty = fall back, shown as (unset) rather than blank

    def _populateImages(self, cfg):
        """Fill the Images tab from the raw config dict `cfg`."""
        for img in cfg.get("images", []):
            self._addImageRow(img)


    def _collectImages(self, cfg):
        """Write the Images tab's part of the config into the dict `cfg` (key order = file order)."""
        images = self._readImageRows()
        if images:
            cfg["images"] = images


    def _clearImages(self):
        """Reset the Images tab to its blank/default state."""
        self.quickColumnsTable.setRowCount(0)
        self.imgTable.setRowCount(0)
        self._image_advanced = []
