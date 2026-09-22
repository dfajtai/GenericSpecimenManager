"""
BatchProcessor.py
==================
Batch export/statistics for GenericSpecimenManager, split out from
GenericSpecimenEngine.py for readability. Depends only on GenericSpecimen/
GenericSpecimenManagerLogic (imported lazily below to avoid a circular
import, since GenericSpecimenEngine.py imports batch_exporter from here).
"""

import os
import gc

import slicer
import vtk

from Resources.LoggingSetup import logger
from Resources.Definitions import DEFAULT_STATS_METRICS


class BatchProcessor:
    """Runs cfg.batch_export's work for every 'done' specimen, in ONE pass:
    export segment labelmaps to files, export markups, and/or compute
    custom per-segment statistics into one combined CSV - any combination,
    driven entirely by cfg.batch_export. No GUI involved - callable
    standalone from the Python console with just a Logic instance
    (`BatchProcessor(logic).run()`).

    Statistics are computed straight from Slicer's own per-segment
    labelmap export (the SAME ExportSegmentsToLabelmapNode call used for
    file export - each segment gets its own independently-exported
    labelmap, so overlapping segments are handled correctly, unlike
    decoding one shared multi-label array from a file) via
    slicer.util.arrayFromVolume() + plain numpy, and written with the
    standard library's csv module - no pandas, no third-party
    segmentation-file-reading library.

    Each specimen is loaded through the LEAN GenericSpecimen.load_for_batch()
    path (only the segmentation + at most one reference/"master" volume -
    never the full configured image set), which also skips workspace
    settings, volume rendering, and Segment Editor activation entirely -
    none of that is needed for a headless batch run, and skipping it is
    most of the speedup over the interactive load()."""

    def __init__(self, logic):
        self.logic = logic
        self.cfg = logic.cfg
        self.be_cfg = logic.cfg.batch_export
        self.stats_rows = []   # populated during run() if compute_stats is on

    def run(self):
        """Entry point: validates config, then iterates every 'done' specimen doing whichever of export_segments/export_markups/compute_stats is enabled, and finally writes the combined stats CSV if compute_stats was on."""
        if self.logic.hasActiveSpecimen:
            logger.warning("[BatchProcessor] please close the active specimen before running a batch export.")
            return
        be_cfg = self.be_cfg
        if not be_cfg.enabled:
            logger.warning("[BatchProcessor] batch_export is not enabled in the config.")
            return
        if not (be_cfg.export_segments or be_cfg.export_markups or be_cfg.compute_stats):
            logger.warning("[BatchProcessor] batch_export is enabled but export_segments/export_markups/compute_stats are all off - nothing to do.")
            return

        np = None
        if be_cfg.compute_stats:
            try:
                import numpy as np
            except ImportError as e:
                logger.error(f"[BatchProcessor] numpy is required for compute_stats: {e}")
                slicer.util.errorDisplay(f"Batch statistics need numpy installed: {e}")
                return
        self._np = np

        self.logic.initializeStudy()
        cfg = self.cfg
        done_col = cfg.done_column
        # per_batch: splits everything (segment/markup files AND stats CSVs) by batch_mode.column's
        # value. Only needs that column to be SET - deliberately independent of batch_mode.enabled,
        # which only controls the interactive specimen-table filter combo in the main GUI and has
        # no bearing on batch export/stats behavior.
        per_batch = bool(cfg.batch_mode.column) and be_cfg.per_batch_operation
        # geo_ref_name: single geometry reference for the segment export itself (ExportSegmentsToLabelmapNode
        # needs exactly one reference grid). stats_ref_names: one or more images to SAMPLE intensities from -
        # each produces its own stats row per segment; falls back to [geo_ref_name] if unset.
        geo_ref_name = be_cfg.reference_image or cfg.segmentation.reference_image
        stats_ref_names = be_cfg.stats_reference_images or ([geo_ref_name] if geo_ref_name else [])
        need_ref_image = bool(be_cfg.export_segments or be_cfg.compute_stats)
        self.stats_rows = []

        # Snapshot every ColorTableNode already in the scene before we touch anything - Slicer's
        # own ExportSegmentsToLabelmapNode auto-creates a fresh display node + color table for
        # each temporary labelmap it produces (confirmed in Slicer's own script repository
        # cleanup example), and since we never pass it a pre-existing color table of our own,
        # these are genuinely new nodes each time, not shared ones. Only nodes NOT in this
        # snapshot are ever removed later - anything that already existed (built-in/shared color
        # tables) is left completely alone, however the leftover ones are identified.
        self._pre_existing_color_node_ids = set()
        _color_collection = slicer.mrmlScene.GetNodesByClass("vtkMRMLColorTableNode")
        for _i in range(_color_collection.GetNumberOfItems()):
            self._pre_existing_color_node_ids.add(_color_collection.GetItemAsObject(_i).GetID())

        # Removing several nodes in a row (per-specimen images + segmentation) can trigger a
        # harmless but noisy "GetSubjectHierarchyNode: Invalid scene given" warning storm from
        # Slicer's own Subject Hierarchy plugin - a VTK-level message, unrelated to our own
        # logging above. Muted for the run; restored shortly after via a short delay rather than
        # immediately, since the warnings appear to surface only once control returns to Qt's
        # event loop, after run() itself has already returned - restoring too early would let
        # them straight back through.
        previous_warning_display = vtk.vtkObject.GetGlobalWarningDisplay()
        vtk.vtkObject.GlobalWarningDisplayOff()

        def _restore_warning_display():
            vtk.vtkObject.SetGlobalWarningDisplay(previous_warning_display)

        try:
            for key, specimen in self.logic.specimens.items():
                if specimen.db_info.get(done_col) != "1":
                    continue
                slicer.mrmlScene.StartState(slicer.mrmlScene.BatchProcessState)
                try:
                    self._process_one(specimen, key, geo_ref_name, stats_ref_names, need_ref_image, per_batch)
                finally:
                    slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)
                gc.collect()   # drop any lingering Python-side references to just-removed nodes

            if be_cfg.compute_stats:
                self._write_stats_csv(per_batch)
        finally:
            try:
                import qt
                qt.QTimer.singleShot(1000, _restore_warning_display)
            except Exception:
                _restore_warning_display()

    def _process_one(self, specimen, key, geo_ref_name, stats_ref_names, need_ref_image, per_batch):
        """Lean-load one specimen, export/compute whatever's enabled for it, then close it again."""
        cfg = self.cfg
        be_cfg = self.be_cfg

        image_names = sorted(set(([geo_ref_name] if geo_ref_name else []) + (stats_ref_names or []))) \
            if need_ref_image else []
        self.logic.load_specimen_for_batch(key, image_names=image_names)

        geo_ref_node = specimen.node_dict.get(geo_ref_name) if geo_ref_name else None
        if need_ref_image and geo_ref_node is None:
            logger.warning(f"[BatchProcessor] reference image '{geo_ref_name}' not available for {specimen.label}, skipping")
            self.logic.close_active_specimen(no_question=True)
            return

        batch_val = specimen.batch_value() if per_batch else None
        out_dir = self._resolve_output_dir(specimen, batch_val)

        if (be_cfg.export_segments or be_cfg.compute_stats) and specimen.segmentation_node is not None:
            self._process_segments(specimen, geo_ref_node, stats_ref_names, out_dir, batch_val)

        if be_cfg.export_markups and specimen.markups_node is not None:
            if not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            out_file = os.path.join(out_dir, f"{specimen.label}-markups.mrk.json")
            storage = specimen.markups_node.CreateDefaultStorageNode()
            storage.SetHideFromEditors(True)
            storage.SetFileName(out_file)
            storage.WriteData(specimen.markups_node)
            logger.info(f"[BatchProcessor] saved {out_file}")
            slicer.mrmlScene.RemoveNode(storage)

        self.logic.close_active_specimen(no_question=True)

    def _resolve_output_dir(self, specimen, batch_val):
        """Resolve batch_export.output_dir - a PLAIN literal folder path,
        study_dir-relative unless absolute (no per-specimen {ID}-style
        placeholders here; that's what output_dir_pattern/out_dir is for).
        May contain a literal "{batch}" placeholder, substituted with the
        specimen's batch_mode.column value when per-batch grouping is on
        (batch_val is not None); if per-batch is on and output_dir doesn't
        mention "{batch}" at all, a "/<batch value>" suffix is appended
        automatically so files from different batches never collide.
        Falls back to the specimen's own out_dir (built from
        output_dir_pattern) when output_dir itself is unset."""
        base_dir = self.be_cfg.output_dir
        batch_str = str(batch_val) if batch_val else "unknown"
        if base_dir:
            if "{batch}" in base_dir:
                base_dir = base_dir.replace("{batch}", batch_str)
            elif batch_val is not None:
                base_dir = os.path.join(base_dir, batch_str)
            if not os.path.isabs(base_dir):
                base_dir = os.path.join(self.logic.study_dir, base_dir)
            return base_dir
        out_dir = specimen.out_dir
        if batch_val is not None:
            out_dir = os.path.join(out_dir, batch_str)
        return out_dir

    def _process_segments(self, specimen, geo_ref_node, stats_ref_names, out_dir, batch_val):
        """Export each (filtered) segment to its own labelmap via Slicer's
        native ExportSegmentsToLabelmapNode (geometry from geo_ref_node),
        then - depending on cfg.batch_export - write it to a file and/or
        fold it into the stats table (one row per configured sample
        image), before discarding the temporary labelmap node."""
        be_cfg = self.be_cfg
        segments_filter = be_cfg.segments_filter
        if be_cfg.export_segments and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        seg = specimen.segmentation_node.GetSegmentation()
        slicer.mrmlScene.StartState(slicer.mrmlScene.BatchProcessState)
        try:
            for seg_id in list(seg.GetSegmentIDs()):
                seg_name = seg.GetSegment(seg_id).GetName()
                if segments_filter and seg_name not in segments_filter:
                    continue

                labelmap = slicer.vtkMRMLLabelMapVolumeNode()
                labelmap.SetHideFromEditors(True)  # scratch node, never shown in Subject Hierarchy - avoids SH warning spam on rapid add/remove
                slicer.mrmlScene.AddNode(labelmap)
                ids = vtk.vtkStringArray()
                ids.InsertNextValue(seg_id)
                slicer.vtkSlicerSegmentationsModuleLogic.ExportSegmentsToLabelmapNode(
                    specimen.segmentation_node, ids, labelmap, geo_ref_node)
                # ExportSegmentsToLabelmapNode auto-creates a display node (and, via that, a fresh
                # color table matching this segment's name/color) as a side effect - captured here
                # so both get cleaned up alongside the labelmap itself below, instead of leaking.
                display_node = labelmap.GetDisplayNode()
                color_node = display_node.GetColorNode() if display_node else None

                if be_cfg.export_segments:
                    storage = labelmap.CreateDefaultStorageNode()
                    storage.SetHideFromEditors(True)
                    out_file = os.path.join(out_dir, f"{specimen.label}-{seg_name}.nii.gz")
                    storage.SetFileName(out_file)
                    storage.WriteData(labelmap)
                    logger.info(f"[BatchProcessor] saved {out_file}")
                    slicer.mrmlScene.RemoveNode(storage)

                if be_cfg.compute_stats:
                    mask_arr = slicer.util.arrayFromVolume(labelmap)
                    for image_name in stats_ref_names:
                        sample_node = specimen.node_dict.get(image_name)
                        if sample_node is None:
                            logger.warning(f"[BatchProcessor] sample image '{image_name}' not available for {specimen.label}, skipping")
                            continue
                        sample_arr = slicer.util.arrayFromVolume(sample_node)
                        if sample_arr.shape != mask_arr.shape:
                            logger.warning(f"[BatchProcessor] '{image_name}' geometry doesn't match the segmentation's for {specimen.label}, skipping")
                            continue
                        self._add_stats_row(specimen, image_name, seg_name, labelmap, mask_arr, sample_arr, batch_val)

                if slicer.mrmlScene.IsNodePresent(labelmap):
                    slicer.mrmlScene.RemoveNode(labelmap)
                if display_node is not None and slicer.mrmlScene.IsNodePresent(display_node):
                    slicer.mrmlScene.RemoveNode(display_node)
                if (color_node is not None and slicer.mrmlScene.IsNodePresent(color_node)
                        and color_node.GetID() not in self._pre_existing_color_node_ids):
                    slicer.mrmlScene.RemoveNode(color_node)
        finally:
            slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)

    def _add_stats_row(self, specimen, image_name, seg_name, labelmap, mask_arr, sample_arr, batch_val):
        """Compute this one (sample image, segment) pair's metrics (cfg.batch_export.stats_metrics, or the Definitions default) and append a row to self.stats_rows. batch_val (if per-batch grouping is on) is stashed under a private "_batch" key, used only to group/route rows to the right CSV file at write time - never written out as an actual column."""
        np = self._np
        metrics = self.be_cfg.stats_metrics or list(DEFAULT_STATS_METRICS)
        roi_pixels = sample_arr[mask_arr == 1]
        voxel_volume = float(np.prod(labelmap.GetSpacing()))

        row = dict(zip(self.cfg.key_columns, specimen.key_values))
        row["image"] = image_name
        row["segment"] = seg_name
        for metric_name in metrics:
            row[metric_name] = self._compute_metric(metric_name, roi_pixels, voxel_volume)
        if batch_val is not None:
            row["_batch"] = batch_val
        self.stats_rows.append(row)

    def _compute_metric(self, metric_name, roi_pixels, voxel_volume):
        """One metric's value for one segment's ROI pixels - volume/min/max/
        mean/median/std, or percentile_<N> (e.g. percentile_25). NaN for an
        empty ROI (except volume, which is legitimately 0.0). Raises
        ValueError for an unrecognized metric name - caught by the caller's
        config-validation path, not silently ignored."""
        np = self._np
        if metric_name == "volume":
            return float(roi_pixels.size * voxel_volume)
        if roi_pixels.size == 0:
            return float("nan")
        if metric_name == "min":
            return float(np.min(roi_pixels))
        if metric_name == "max":
            return float(np.max(roi_pixels))
        if metric_name == "mean":
            return float(np.mean(roi_pixels))
        if metric_name == "median":
            return float(np.median(roi_pixels))
        if metric_name == "std":
            return float(np.std(roi_pixels))  # ddof=0 (population std)
        if metric_name.startswith("percentile_"):
            try:
                p = float(metric_name[len("percentile_"):])
            except ValueError:
                raise ValueError(f"invalid percentile metric '{metric_name}' - expected e.g. 'percentile_25'")
            return float(np.percentile(roi_pixels, p))
        raise ValueError(f"unknown stats metric '{metric_name}' - expected volume/min/max/mean/median/std or percentile_<N>")

    def _write_stats_csv(self, per_batch):
        """Write self.stats_rows to one or more CSVs. When per_batch is
        False, everything goes into a single combined file
        (cfg.batch_export.stats_output_path, defaulting to "report.csv").
        When True, rows are grouped by their "_batch" tag and ONE CSV is
        written per batch value (see _resolve_stats_output_path for how
        the "{batch}" placeholder / auto-suffix works), each sorted by key
        columns then segment name, via the standard library's csv
        module."""
        import csv
        if not self.stats_rows:
            logger.warning("[BatchProcessor] compute_stats enabled but no rows produced (no matching segments in any 'done' specimen - see warnings above).")
            return

        cfg = self.cfg
        key_cols = list(cfg.key_columns)
        metrics = self.be_cfg.stats_metrics or list(DEFAULT_STATS_METRICS)
        fieldnames = key_cols + ["image", "segment"] + list(metrics)

        if per_batch:
            groups = {}
            for row in self.stats_rows:
                groups.setdefault(row.get("_batch", "unknown"), []).append(row)
        else:
            groups = {None: self.stats_rows}

        written_paths = []
        total_rows = 0
        for batch_val, rows in groups.items():
            rows_sorted = sorted(
                rows, key=lambda r: tuple(str(r[c]) for c in key_cols) + (str(r["image"]), str(r["segment"])))
            out_path = self._resolve_stats_output_path(batch_val)
            out_dir = os.path.dirname(out_path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                # extrasaction="ignore": rows may carry an internal "_batch" tag not in fieldnames
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows_sorted)
            logger.info(f"[BatchProcessor] wrote {len(rows_sorted)} row(s) -> {out_path}")
            written_paths.append(out_path)
            total_rows += len(rows_sorted)

        n_specimens = len(set(tuple(r[c] for c in key_cols) for r in self.stats_rows))
        dialog_rows = [("stats rows", total_rows), ("specimens", n_specimens)]
        if len(written_paths) == 1:
            dialog_rows.append(("path", written_paths[0]))
        else:
            dialog_rows.append(("files", len(written_paths)))
            for p in written_paths:
                dialog_rows.append(("", p))
        self.logic.show_key_value_dialog("Batch export finished", dialog_rows)

    def _resolve_stats_output_path(self, batch_val):
        """Resolve cfg.batch_export.stats_output_path (plain, study_dir-
        relative unless absolute; defaults to "report.csv") for one
        output file. "{date}"/"{time}"/"{datetime}" are substituted first if
        present. If batch_val is not None (per-batch grouping is on):
        a literal "{batch}" placeholder is substituted with the batch
        value; if the path doesn't mention "{batch}" at all, the batch
        value is inserted before the file extension instead, so per-batch
        files never collide with each other."""
        import datetime
        out_path = self.be_cfg.stats_output_path or "report.csv"
        if "{date}" in out_path:
            out_path = out_path.replace("{date}", datetime.date.today().isoformat())
        if "{time}" in out_path:
            out_path = out_path.replace("{time}", datetime.datetime.now().strftime("%H-%M-%S"))  # colon-free, filesystem-safe (Windows disallows ':' in filenames)
        if "{datetime}" in out_path:
            out_path = out_path.replace("{datetime}", datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        if batch_val is not None:
            batch_str = str(batch_val) if batch_val else "unknown"
            if "{batch}" in out_path:
                out_path = out_path.replace("{batch}", batch_str)
            else:
                root, ext = os.path.splitext(out_path)
                out_path = f"{root}_{batch_str}{ext}"
        if not os.path.isabs(out_path):
            out_path = os.path.join(self.cfg.study_dir, out_path)
        return out_path


def batch_exporter(logic):
    """Standalone entry point, kept for Python-console convenience and
    backward compatibility - just runs BatchProcessor(logic).run()."""
    BatchProcessor(logic).run()
