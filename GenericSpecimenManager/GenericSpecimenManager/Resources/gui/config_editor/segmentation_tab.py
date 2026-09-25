"""
segmentation_tab.py
===================
Segmentation tab: reference image, path pattern, the segments table.
"""

import qt

from Resources.definitions import SOURCE_CHOICES
from Resources.gui.config_editor.helpers import DEFAULT_SEGMENT_COLOR


class SegmentationTabMixin:
    """Segmentation tab: reference image, path pattern, the segments table."""


    def _buildSegmentationTab(self):
        """Enabled/reference image/path pattern/output filename, plus the segments[] table."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)
        form = qt.QFormLayout()
        self.chkSegEnabled = qt.QCheckBox("Enabled")
        form.addRow(self.chkSegEnabled)
        self.segReferenceImageEdit = qt.QComboBox()
        self.segReferenceImageEdit.setEditable(True)
        self.segReferenceImageEdit.setToolTip(
            "Pick one of the images from the Images tab (its Name) - used as the geometry "
            "reference for the segmentation, e.g. 'mask' or 't1'. The list follows the Images tab.")
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
        seg_header = self.segTable.horizontalHeader()
        seg_header.setSectionResizeMode(0, qt.QHeaderView.Stretch)             # Name
        seg_header.setSectionResizeMode(1, qt.QHeaderView.ResizeToContents)    # Source - a small file/empty dropdown
        seg_header.setSectionResizeMode(2, qt.QHeaderView.Stretch)             # CSV column
        seg_header.setSectionResizeMode(3, qt.QHeaderView.Stretch)             # Path pattern - the longest text
        seg_header.setSectionResizeMode(4, qt.QHeaderView.ResizeToContents)    # Color - a short r,g,b swatch
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

    def _addSegmentRow(self, d):
        """Append one row to the segments table (name/source/csv_column/path_pattern) with its color swatch cell."""
        row = self.segTable.rowCount
        self.segTable.insertRow(row)
        self.segTable.setItem(row, 0, qt.QTableWidgetItem(d.get("name", f"segment_{row + 1}")))
        srcCombo = qt.QComboBox()
        srcCombo.addItems(SOURCE_CHOICES)
        srcCombo.currentText = d.get("source", "file")
        srcCombo.currentIndexChanged.connect(self._markDirty)
        self.segTable.setCellWidget(row, 1, srcCombo)
        self.segTable.setItem(row, 2, qt.QTableWidgetItem(d.get("csv_column", "")))
        self.segTable.setItem(row, 3, qt.QTableWidgetItem(d.get("path_pattern", "")))
        colorItem = qt.QTableWidgetItem(str(d.get("color", "")) or "")
        colorItem.setFlags(colorItem.flags() & ~qt.Qt.ItemIsEditable)
        self.segTable.setItem(row, 4, colorItem)
        color = d.get("color")
        self._segment_colors.insert(row, list(color) if color else list(DEFAULT_SEGMENT_COLOR))
        self._applySegmentColorDisplay(row)
        self._markDirty()

    def _applySegmentColorDisplay(self, row):
        """Paint a segment row's color cell from _segment_colors[row] and show the r,g,b values as its text too."""
        rgb = self._segment_colors[row]
        r, g, b = (int(round(c * 255)) for c in rgb)
        item = self.segTable.item(row, 4)
        item.setBackground(qt.QColor(r, g, b))
        item.setText(f"{rgb[0]:.2f},{rgb[1]:.2f},{rgb[2]:.2f}")

    def _onAddSegment(self):
        """Add one blank segment row."""
        self._addSegmentRow({})

    def _onRemoveSegment(self):
        """Remove the selected segment row(s), keeping the parallel _segment_colors list in sync."""
        rows = sorted(set(i.row() for i in self.segTable.selectedIndexes()), reverse=True)
        for r in rows:
            self.segTable.removeRow(r)
            if 0 <= r < len(self._segment_colors):
                del self._segment_colors[r]
        self._markDirty()

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
            self._applySegmentColorDisplay(row)
            self._markDirty()

    def _readSegmentRows(self):
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

    def _getSegmentNames(self):
        """Every non-empty Name in the Segmentation tab's segments table."""
        names = []
        for row in range(self.segTable.rowCount):
            item = self.segTable.item(row, 0)
            name = (item.text().strip() if item else "")
            if name:
                names.append(name)
        return names

    def _populateSegmentation(self, cfg):
        """Fill the Segmentation tab from the raw config dict `cfg`."""
        seg = cfg.get("segmentation", {}) or {}
        self.chkSegEnabled.checked = bool(seg.get("enabled"))
        self.segReferenceImageEdit.currentText = seg.get("reference_image", "") or ""
        self.segPathPatternEdit.text = seg.get("path_pattern", "") or ""
        self.segOutputFilenameEdit.text = seg.get("output_filename", "segment.seg.nrrd")
        for s in seg.get("segments", []):
            self._addSegmentRow(s)


    def _collectSegmentation(self, cfg):
        """Write the Segmentation tab's part of the config into the dict `cfg` (key order = file order)."""
        seg_enabled = self.chkSegEnabled.checked
        segments = self._readSegmentRows()
        if seg_enabled or segments:
            seg = {"enabled": seg_enabled}
            if self.segReferenceImageEdit.currentText.strip():
                seg["reference_image"] = self.segReferenceImageEdit.currentText.strip()
            if self.segPathPatternEdit.text.strip():
                seg["path_pattern"] = self.segPathPatternEdit.text.strip()
            seg["output_filename"] = self.segOutputFilenameEdit.text.strip() or "segment.seg.nrrd"
            seg["segments"] = segments
            cfg["segmentation"] = seg


    def _clearSegmentation(self):
        """Reset the Segmentation tab to its blank/default state."""
        self.segPathPatternEdit.text = ""
        self.segOutputFilenameEdit.text = "segment.seg.nrrd"
        self.chkSegEnabled.checked = False
        self.segReferenceImageEdit.currentText = ""
        self.segTable.setRowCount(0)
        self._segment_colors = []
