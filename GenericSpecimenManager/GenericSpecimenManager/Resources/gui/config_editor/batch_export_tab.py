"""
batch_export_tab.py
===================
Batch export tab: what to produce, where it goes, the segment/markup reports.
"""

import qt

from Resources.definitions import DEFAULT_STATS_METRICS
from Resources.gui.config_editor.helpers import csv_list


class BatchExportTabMixin:
    """Batch export tab: what to produce, where it goes, the segment/markup reports."""


    def _buildBatchExportTab(self):
        """Batch Export - runs once, against every specimen marked 'finished', in one pass, without opening the interactive viewer for each one. Split into its own tab since it had grown too large to sit comfortably inside General."""
        w = qt.QWidget()
        layout = qt.QVBoxLayout(w)

        def new_group(title):
            group = qt.QGroupBox(title)
            layout.addWidget(group)
            return qt.QFormLayout(group)

        beForm = new_group("Batch export")
        self.chkBeEnabled = qt.QCheckBox("Enable batch export")
        self.chkBeEnabled.setToolTip(
            "Runs once, against every specimen marked 'finished' in the database, without opening the "
            "interactive viewer for each one. Pick any combination of what to produce below - each "
            "is independent, and all of them run in the same single pass per specimen.")
        self.chkBeEnabled.connect('toggled(bool)', self._onBeEnabledToggled)
        beForm.addRow(self.chkBeEnabled)

        self._beChildWidgets = []

        self.beOutputDirEdit, beOutputDirRow = self._fileRow(directory=True)
        self.beOutputDirEdit.setToolTip(
            "The root every pattern below is anchored to - segment/markup files, and (unless "
            "absolute) the Segment export/Report/Markup summary patterns too. Empty -> study_dir. "
            "Relative -> resolved under study_dir. Absolute -> used exactly as given.")
        beForm.addRow("Batch export root dir:", beOutputDirRow)
        self._beChildWidgets.append(beOutputDirRow)

        beForm = new_group("Batch operations")
        opsGrid = qt.QGridLayout()
        self.chkBeExportSegments = qt.QCheckBox("Export segments")
        self.chkBeExportSegments.setToolTip("Writes each segment to its own labelmap file, one per segment per specimen.")
        self.chkBeComputeStats = qt.QCheckBox("Custom segment statistics")
        self.chkBeComputeStats.setToolTip(
            "Needs numpy installed. Computed straight from Slicer's own segment export (handles "
            "overlapping segments correctly) - every 'finished' specimen's rows go into a combined CSV. "
            "Configured in the 'Segment statistics settings' group further down.")
        self.chkBeExportMarkups = qt.QCheckBox("Export markups")
        self.chkBeExportMarkups.setToolTip(
            "Writes each specimen's markups .mrk.json file, PLUS a per-specimen markups CSV (label, "
            "x, y, z - world/RAS position, read straight from the live markups node) automatically "
            "alongside it - no separate switch needed for that part.")
        self.chkBeMarkupsReport = qt.QCheckBox("Markup summary")
        self.chkBeMarkupsReport.setToolTip(
            "Needs Export markups above also checked. In addition to the automatic per-specimen "
            "markups CSV, combines every specimen's markup points into one or more CSVs (one row "
            "per point, key columns prepended) - configured in 'Markup summary settings' further "
            "down.")
        opsGrid.addWidget(self.chkBeExportSegments, 0, 0)
        opsGrid.addWidget(self.chkBeComputeStats, 0, 1)
        opsGrid.addWidget(self.chkBeExportMarkups, 1, 0)
        opsGrid.addWidget(self.chkBeMarkupsReport, 1, 1)
        opsGrid.setColumnStretch(0, 1)
        opsGrid.setColumnStretch(1, 1)
        beForm.addRow(opsGrid)
        self._beChildWidgets += [self.chkBeExportSegments, self.chkBeComputeStats, self.chkBeExportMarkups, self.chkBeMarkupsReport]

        beForm = new_group("Segment export settings")

        self.beReferenceImageEdit = qt.QComboBox()
        self.beReferenceImageEdit.setEditable(True)
        self.beReferenceImageEdit.setToolTip(
            "Reference volume for exporting segments to labelmaps (also the fallback for the stats "
            "reference image(s) below, if those are left empty). Pick one of the Images-tab names. "
            "If empty, falls back to segmentation.reference_image.")
        beForm.addRow("Reference image (name):", self.beReferenceImageEdit)
        self._beChildWidgets.append(self.beReferenceImageEdit)

        segFilterRow = qt.QHBoxLayout()
        self.beSegmentsFilterEdit = qt.QLineEdit()
        self.beSegmentsFilterEdit.setPlaceholderText("comma-separated segment names, empty = all")
        segFilterRow.addWidget(self.beSegmentsFilterEdit)
        segFilterAllBtn = qt.QPushButton("Use all segments")
        segFilterAllBtn.setToolTip("Fills in every segment name currently in the Segmentation tab.")
        segFilterAllBtn.connect('clicked(bool)', lambda checked=False: self._onInsertAllSegmentsFilter())
        segFilterRow.addWidget(segFilterAllBtn)
        beForm.addRow("Segments filter:", segFilterRow)
        self.beSegmentsFilterEdit.setToolTip("Which segments get exported to their own labelmap file. Independent of the Segment statistics settings' own filter below.")
        self._beChildWidgets += [self.beSegmentsFilterEdit, segFilterAllBtn]

        self.beOutputDirPatternEdit = qt.QLineEdit()
        self.beOutputDirPatternEdit.setPlaceholderText("e.g. {ID}/{measurement}")
        self.beOutputDirPatternEdit.setToolTip(
            "<html>Per-specimen subfolder, joined onto the Batch export root dir above.<br>"
            "Placeholder:<br>"
            "&bull; {column} - any key/database.csv/preseg.csv column value, e.g. {batch}/{ID}<br>"
            "Empty -> your key columns, joined.<br>"
            "See Help for more.</html>")
        beForm.addRow("Segment export pattern:", self.beOutputDirPatternEdit)
        self._beChildWidgets.append(self.beOutputDirPatternEdit)

        beForm = new_group("Segment statistics settings")

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

        statsSegFilterRow = qt.QHBoxLayout()
        self.statsSegmentsFilterEdit = qt.QLineEdit()
        self.statsSegmentsFilterEdit.setPlaceholderText("comma-separated segment names, empty = all")
        statsSegFilterRow.addWidget(self.statsSegmentsFilterEdit)
        statsSegFilterAllBtn = qt.QPushButton("Use all segments")
        statsSegFilterAllBtn.setToolTip("Fills in every segment name currently in the Segmentation tab.")
        statsSegFilterAllBtn.connect('clicked(bool)', lambda checked=False: self._onInsertAllStatsSegmentsFilter())
        statsSegFilterRow.addWidget(statsSegFilterAllBtn)
        beForm.addRow("Segments filter:", statsSegFilterRow)
        self.statsSegmentsFilterEdit.setToolTip(
            "Which segments get a statistics row. Independent of the Segment export settings' own "
            "filter above - a segment can be included here without being exported to a file, or "
            "vice versa.")
        self._beChildWidgets += [self.statsSegmentsFilterEdit, statsSegFilterAllBtn]

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
            "<html>File path, anchored directly to Batch export root dir above (never nested "
            "through the Segment export pattern).<br>"
            "Placeholders:<br>"
            "&bull; {column} - any key/database.csv/preseg.csv column value<br>"
            "&bull; {date} - YYYY-MM-DD<br>"
            "&bull; {time} - HH-MM-SS<br>"
            "&bull; {datetime} - YYYY-MM-DD_HH-MM-SS<br>"
            "&bull; {index} - only if present: 01-based counter before the extension, lowest free "
            "number on disk, so an existing report is never overwritten (without it, an existing "
            "file IS overwritten)<br>"
            "Same final path -> one shared CSV; different paths -> separate files.<br>"
            "Empty -> report.csv.<br>"
            "See Help for more.</html>")
        beForm.addRow("Report pattern:", self.statsOutputPathEdit)
        self._beChildWidgets.append(self.statsOutputPathEdit)

        beForm = new_group("Markup summary settings")
        self.markupsCoordinateSystemCombo = qt.QComboBox()
        self.markupsCoordinateSystemCombo.addItems(["RAS", "LPS"])
        self.markupsCoordinateSystemCombo.setToolTip(
            "Coordinate convention for the point x/y/z values written to BOTH the per-specimen "
            "markups CSV (from Export markups) and the combined Markup summary CSV below - the "
            ".mrk.json file itself is untouched either way. RAS (default) is Slicer's own world "
            "coordinate, written as-is. LPS flips x and y (LPS = -x, -y, z relative to RAS) - use "
            "this if the CSV feeds an ITK/DICOM-based pipeline that expects LPS.")
        beForm.addRow("Markup CSV coordinate encoding:", self.markupsCoordinateSystemCombo)
        self._beChildWidgets.append(self.markupsCoordinateSystemCombo)
        self.markupsOutputPathEdit = qt.QLineEdit()
        self.markupsOutputPathEdit.setPlaceholderText("markups_report.csv")
        self.markupsOutputPathEdit.setToolTip(
            "<html>File path, anchored directly to Batch export root dir above (never nested "
            "through the Segment export pattern).<br>"
            "Placeholders:<br>"
            "&bull; {column} - any key/database.csv/preseg.csv column value<br>"
            "&bull; {date} - YYYY-MM-DD<br>"
            "&bull; {time} - HH-MM-SS<br>"
            "&bull; {datetime} - YYYY-MM-DD_HH-MM-SS<br>"
            "&bull; {index} - only if present: 01-based counter before the extension, lowest free "
            "number on disk, so an existing summary is never overwritten (without it, an existing "
            "file IS overwritten)<br>"
            "Same final path -> one shared CSV; different paths -> separate files.<br>"
            "Empty -> markups_report.csv.<br>"
            "See Help for more.</html>")
        beForm.addRow("Markup summary pattern:", self.markupsOutputPathEdit)
        self._beChildWidgets.append(self.markupsOutputPathEdit)

        layout.addStretch(1)
        self._onBeEnabledToggled(self.chkBeEnabled.checked)

        return w

    def _onBeEnabledToggled(self, checked):
        """Enable/disable every Batch export child widget together with Enable batch export - values are left untouched either way."""
        for w in getattr(self, "_beChildWidgets", []):
            w.enabled = checked

    def _onInsertAllSegmentsFilter(self):
        """Fill Segment export settings' Segments filter with every non-empty Name in the Segmentation tab's segments table."""
        self.beSegmentsFilterEdit.text = ",".join(self._getSegmentNames())

    def _onInsertAllStatsSegmentsFilter(self):
        """Fill Segment statistics settings' own Segments filter with every non-empty Name in the Segmentation tab's segments table - independent of Segment export settings' filter."""
        self.statsSegmentsFilterEdit.text = ",".join(self._getSegmentNames())

    def _onUseAllImagesForStats(self):
        """Fill Stats reference image(s) with every image name from the Images tab."""
        self.statsReferenceImagesEdit.text = ",".join(self._getImageNames())

    def _onInsertDefaultStatsMetrics(self):
        """Fill the batch-export stats Metrics field with the same default (Definitions.DEFAULT_STATS_METRICS) that's used automatically when the field is left empty - just makes it visible/editable."""
        self.statsMetricsEdit.text = ",".join(DEFAULT_STATS_METRICS)

    def _populateBatchExport(self, cfg):
        """Fill the Batch export tab from the raw config dict `cfg`."""
        be = cfg.get("batch_export", {}) or {}
        self.chkBeEnabled.checked = bool(be.get("enabled"))
        self._onBeEnabledToggled(self.chkBeEnabled.checked)
        self.chkBeExportSegments.checked = bool(be.get("export_segments"))
        self.chkBeExportMarkups.checked = bool(be.get("export_markups"))
        self.beReferenceImageEdit.currentText = be.get("reference_image", "") or ""
        self.beSegmentsFilterEdit.text = ",".join(be.get("segments_filter") or [])
        self.beOutputDirEdit.text = be.get("output_dir", "") or ""
        self.beOutputDirPatternEdit.text = be.get("output_dir_pattern", "") or ""
        self.chkBeComputeStats.checked = bool(be.get("compute_stats"))
        self.statsReferenceImagesEdit.text = ",".join(be.get("stats_reference_images") or [])
        self.statsSegmentsFilterEdit.text = ",".join(be.get("stats_segments_filter") or [])
        self.statsMetricsEdit.text = ",".join(be.get("stats_metrics") or [])
        self.statsOutputPathEdit.text = be.get("stats_output_path", "") or ""
        self.markupsCoordinateSystemCombo.currentText = be.get("markups_coordinate_system", "RAS") or "RAS"
        self.chkBeMarkupsReport.checked = bool(be.get("markups_report"))
        self.markupsOutputPathEdit.text = be.get("markups_output_path", "") or ""


    def _collectBatchExport(self, cfg):
        """Write the Batch export tab's part of the config into the dict `cfg` (key order = file order)."""
        if self.chkBeEnabled.checked:
            be = {
                "enabled": True,
                "export_segments": self.chkBeExportSegments.checked,
                "export_markups": self.chkBeExportMarkups.checked,
                "compute_stats": self.chkBeComputeStats.checked,
                "markups_report": self.chkBeMarkupsReport.checked,
            }
            if self.beReferenceImageEdit.currentText.strip():
                be["reference_image"] = self.beReferenceImageEdit.currentText.strip()
            filt = csv_list(self.beSegmentsFilterEdit.text)
            if filt:
                be["segments_filter"] = filt
            if self.beOutputDirEdit.text.strip():
                be["output_dir"] = self.beOutputDirEdit.text.strip()
            if self.beOutputDirPatternEdit.text.strip():
                be["output_dir_pattern"] = self.beOutputDirPatternEdit.text.strip()
            filt = csv_list(self.statsReferenceImagesEdit.text)
            if filt:
                be["stats_reference_images"] = filt
            filt = csv_list(self.statsSegmentsFilterEdit.text)
            if filt:
                be["stats_segments_filter"] = filt
            metrics_text = self.statsMetricsEdit.text.strip()
            if metrics_text:
                metrics = []
                for m in csv_list(metrics_text):
                    if m.replace(".", "", 1).isdigit():
                        qt.QMessageBox.critical(
                            self, "Config Editor",
                            f"Stats metric '{m}' looks like a bare number - did you mean 'percentile_{m}'?")
                        raise ValueError(f"invalid stats metric: {m}")
                    metrics.append(m)
                be["stats_metrics"] = metrics
            if self.statsOutputPathEdit.text.strip():
                be["stats_output_path"] = self.statsOutputPathEdit.text.strip()
            if self.markupsCoordinateSystemCombo.currentText != "RAS":
                be["markups_coordinate_system"] = self.markupsCoordinateSystemCombo.currentText
            if self.markupsOutputPathEdit.text.strip():
                be["markups_output_path"] = self.markupsOutputPathEdit.text.strip()
            cfg["batch_export"] = be


    def _clearBatchExport(self):
        """Reset the Batch export tab to its blank/default state."""
        for edit in (self.beSegmentsFilterEdit, self.beOutputDirEdit, self.beOutputDirPatternEdit,
                     self.statsReferenceImagesEdit, self.statsSegmentsFilterEdit, self.statsMetricsEdit,
                     self.statsOutputPathEdit, self.markupsOutputPathEdit):
            edit.text = ""
        self.beReferenceImageEdit.currentText = ""
        self.markupsCoordinateSystemCombo.currentText = "RAS"
        for chk in (self.chkBeEnabled, self.chkBeExportSegments, self.chkBeExportMarkups, self.chkBeComputeStats,
                    self.chkBeMarkupsReport):
            chk.checked = False
        self._onBeEnabledToggled(False)
