"""
volume_rendering_tab.py
=======================
Volume rendering tab: the per-image rendering table.
"""

import qt

from Resources.definitions import VR_PRESET_CHOICES
from Resources.gui.config_editor.helpers import combo_value, set_combo_value, to_float


class VolumeRenderingTabMixin:
    """Volume rendering tab: the per-image rendering table."""


    def _buildVrTab(self):
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
        refreshBtn.connect('clicked(bool)', lambda checked=False: self._refreshVrTable())
        layout.addWidget(refreshBtn)

        return w

    def _refreshVrTable(self):
        """Rebuild the VR table from the current Images tab row names, keeping
        existing per-image settings (by name) for images that still exist. Also refreshes
        the Reference image dropdowns, since both follow the image list."""
        self._refreshReferenceImageChoices()
        existing = {}
        for row in range(self.vrTable.rowCount):
            name = self.vrTable.item(row, 0).text()
            enableItem = self.vrTable.item(row, 1)
            presetCombo = self.vrTable.cellWidget(row, 2)
            existing[name] = {
                "enabled": enableItem.checkState() == qt.Qt.Checked,
                "preset": combo_value(presetCombo) if presetCombo else "",
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
            set_combo_value(presetCombo, wanted)
            presetCombo.currentIndexChanged.connect(self._markDirty)
            self.vrTable.setCellWidget(row, 2, presetCombo)

            self.vrTable.setItem(row, 3, qt.QTableWidgetItem(prev.get("min", "")))
            self.vrTable.setItem(row, 4, qt.QTableWidgetItem(prev.get("max", "")))
            self.vrTable.setItem(row, 5, qt.QTableWidgetItem(prev.get("offset", "")))

        self._markDirty()

    def _readVrRows(self):
        """Read the VR table into a list of volume_rendering[] entries, skipping rows that are completely untouched (not enabled, no preset, no min/max) - so a study with 10 images and VR set up for just one doesn't write 9 empty entries."""
        entries = []
        for row in range(self.vrTable.rowCount):
            name = self.vrTable.item(row, 0).text().strip()
            if not name:
                continue
            enabled = self.vrTable.item(row, 1).checkState() == qt.Qt.Checked
            presetCombo = self.vrTable.cellWidget(row, 2)
            preset = combo_value(presetCombo) if presetCombo else ""
            mn = to_float(self.vrTable.item(row, 3).text())
            mx = to_float(self.vrTable.item(row, 4).text())
            offset = to_float(self.vrTable.item(row, 5).text())
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

    def _populateVolumeRendering(self, cfg):
        """Fill the Volume rendering tab from the raw config dict `cfg`."""
        self._refreshVrTable()
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
            set_combo_value(presetCombo, preset)
            wl = entry.get("window_level") or {}
            self.vrTable.item(row, 3).setText("" if wl.get("min") is None else str(wl["min"]))
            self.vrTable.item(row, 4).setText("" if wl.get("max") is None else str(wl["max"]))
            self.vrTable.item(row, 5).setText("" if entry.get("offset") is None else str(entry["offset"]))


    def _collectVolumeRendering(self, cfg):
        """Write the Volume rendering tab's part of the config into the dict `cfg` (key order = file order)."""
        vr_entries = self._readVrRows()
        if vr_entries:
            cfg["volume_rendering"] = vr_entries


    def _clearVolumeRendering(self):
        """Reset the Volume rendering tab to its blank/default state."""
        self.vrTable.setRowCount(0)
