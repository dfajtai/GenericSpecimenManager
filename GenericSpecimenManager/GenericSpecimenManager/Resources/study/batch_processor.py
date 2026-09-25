"""
batch_processor.py
==================
Batch export/statistics for GenericSpecimenManager. It works on the Logic object it is
given (its specimens and config) and imports nothing from the GUI.
"""

import os
import gc
from collections import Counter

import slicer
import vtk

from Resources.core.logging_setup import logger
from Resources.definitions import DEFAULT_STATS_METRICS, SpecimenStatus, SPECIMEN_STATUS_LABELS


class BatchProcessor:
    """Runs cfg.batch_export's work for every 'finished' specimen, in ONE pass:
    export segment labelmaps to files, export markups, and/or compute
    custom per-segment statistics into one or more CSVs - any combination,
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
    most of the speedup over the interactive load().

    No separate "per-batch" flag anywhere: cfg.batch_export.output_dir_pattern
    and .stats_output_path are curly-brace patterns resolved PER SPECIMEN
    (the same {column} mechanism as the General tab's own
    output_dir_pattern - any key/database.csv/preseg.csv column, e.g. a
    "batch" column, works simply by being referenced in the pattern).
    Grouping for the stats CSV is entirely emergent: specimens that
    resolve to the same final path share one file; specimens that resolve
    to different paths (because the pattern references a column whose
    value differs) naturally end up in separate files instead."""

    def __init__(self, logic):
        self.logic = logic
        self.cfg = logic.cfg
        self.be_cfg = logic.cfg.batch_export
        self.stats_rows = []       # populated during run() if compute_stats is on
        self.markup_rows = []      # populated during run() if export_markups and markups_report are both on

    def run(self):
        """Entry point: validates config, then iterates every 'finished' specimen doing whichever of export_segments/export_markups/compute_stats is enabled, and finally writes the stats CSV(s) if compute_stats was on."""
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

        if not self.logic.specimens:   # normally the study is already initialized from the GUI - don't rebuild it (and re-log/re-apply everything) for every batch run
            self.logic.initializeStudy()
        finished = [sp for sp in self.logic.specimens.values() if sp.status == SpecimenStatus.FINISHED]
        if not finished:
            counts = Counter(SPECIMEN_STATUS_LABELS[sp.status] for sp in self.logic.specimens.values())
            lines = "\n".join(f"    {name}: {n}" for name, n in sorted(counts.items())) or "    (no specimens)"
            logger.info("[BatchProcessor] no specimen has the status 'finished' - nothing to export")
            self.logic.info(
                "Nothing to export: no specimen is marked 'finished'.\n\n"
                f"Specimens by status:\n{lines}\n\n"
                "Set a specimen's Status to 'finished' in the Specimen browser (or use Close active "
                "specimen > Yes, mark finished), then run Batch export again.")
            return
        logger.info(f"[BatchProcessor] exporting {len(finished)} finished specimen(s)")
        cfg = self.cfg
        # geo_ref_name: single geometry reference for the segment export itself (ExportSegmentsToLabelmapNode
        # needs exactly one reference grid). stats_ref_names: one or more images to SAMPLE intensities from -
        # each produces its own stats row per segment; falls back to [geo_ref_name] if unset.
        geo_ref_name = be_cfg.reference_image or cfg.segmentation.reference_image
        stats_ref_names = be_cfg.stats_reference_images or ([geo_ref_name] if geo_ref_name else [])
        need_ref_image = bool(be_cfg.export_segments or be_cfg.compute_stats)
        self.stats_rows = []
        self.markup_rows = []

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
                if specimen.status != SpecimenStatus.FINISHED:
                    continue
                slicer.mrmlScene.StartState(slicer.mrmlScene.BatchProcessState)
                try:
                    self._process_one(specimen, key, geo_ref_name, stats_ref_names, need_ref_image)
                finally:
                    slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)
                gc.collect()   # drop any lingering Python-side references to just-removed nodes

            if be_cfg.compute_stats:
                self._write_stats_csv()
            if be_cfg.export_markups and be_cfg.markups_report:
                self._write_markups_report()
        finally:
            try:
                import qt
                qt.QTimer.singleShot(1000, _restore_warning_display)
            except Exception:
                _restore_warning_display()

    def _process_one(self, specimen, key, geo_ref_name, stats_ref_names, need_ref_image):
        """Lean-load one specimen, export/compute whatever's enabled for it, then close it again."""
        be_cfg = self.be_cfg

        image_names = sorted(set(([geo_ref_name] if geo_ref_name else []) + (stats_ref_names or []))) \
            if need_ref_image else []
        self.logic.load_specimen_for_batch(key, image_names=image_names)

        geo_ref_node = specimen.node_dict.get(geo_ref_name) if geo_ref_name else None
        if need_ref_image and geo_ref_node is None:
            logger.warning(f"[BatchProcessor] reference image '{geo_ref_name}' not available for {specimen.label}, skipping")
            self.logic.close_active_specimen(no_question=True)
            return

        out_dir = self._resolve_output_dir(specimen)
        stats_path = self._resolve_stats_output_path(specimen) if be_cfg.compute_stats else None

        if (be_cfg.export_segments or be_cfg.compute_stats) and specimen.segmentation_node is not None:
            self._process_segments(specimen, geo_ref_node, stats_ref_names, out_dir, stats_path)

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

            markup_rows = self._extract_markup_rows(specimen)
            self._export_markups_csv(specimen, out_dir, markup_rows)
            if be_cfg.markups_report:
                markups_path = self._resolve_markups_output_path(specimen)
                for row in markup_rows:
                    tagged = dict(zip(self.cfg.key_columns, specimen.key_values))
                    tagged.update(row)
                    tagged["_markups_path"] = markups_path
                    self.markup_rows.append(tagged)

        self.logic.close_active_specimen(no_question=True)

    def _extract_markup_rows(self, specimen):
        """Read every DEFINED control point straight from the live, already-loaded markups node -
        label + world position via Slicer's own GetNthControlPointLabel()/
        GetNthControlPointPositionWorld() (RAS). This is deliberately NOT parsing the raw .mrk.json
        file and multiplying "orientation" into "position" - in Slicer's markups schema, position is
        already the point's full world coordinate, and orientation is a separate, mostly-display-
        only local axis frame (or, at the file level, just the LPS/RAS sign convention) - it is not
        a per-point pose transform to apply on top of position. Reading through the live node's own
        API sidesteps that distinction entirely and is guaranteed correct for whatever coordinate
        system Slicer already resolved the point into. batch_export.markups_coordinate_system
        ("RAS", the default, or "LPS") then decides what actually gets WRITTEN to the CSV - the
        .mrk.json file itself is untouched either way."""
        node = specimen.markups_node
        lps = (self.be_cfg.markups_coordinate_system or "RAS").upper() == "LPS"
        rows = []
        try:
            n = node.GetNumberOfControlPoints()
        except Exception:
            return rows
        for i in range(n):
            try:
                if hasattr(node, "GetNthControlPointPositionStatus") and hasattr(node, "PositionUndefined"):
                    if node.GetNthControlPointPositionStatus(i) == node.PositionUndefined:
                        continue
            except Exception:
                pass   # status check itself failing shouldn't drop a point - include it defensively
            label = node.GetNthControlPointLabel(i)
            pos = [0.0, 0.0, 0.0]
            node.GetNthControlPointPositionWorld(i, pos)
            if lps:
                pos[0], pos[1] = -pos[0], -pos[1]
            rows.append({"label": label, "x": pos[0], "y": pos[1], "z": pos[2]})
        return rows

    def _export_markups_csv(self, specimen, out_dir, rows):
        """Write this specimen's own markup points to a per-specimen CSV (label, x, y, z) alongside
        its .mrk.json - written automatically whenever export_markups is on, independent of the
        markups_report flag (which only controls the additional COMBINED multi-specimen report)."""
        if not rows:
            return
        import csv
        out_file = os.path.join(out_dir, f"{specimen.label}-markups.csv")
        with open(out_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["label", "x", "y", "z"])
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"[BatchProcessor] saved {out_file}")

    def _resolve_markups_output_path(self, specimen):
        """Resolve batch_export.markups_output_path (the "markup summary pattern") for THIS
        specimen - same {column}/{date}/{time}/{datetime}/{index} mechanism, same root-anchoring,
        and same emergent per-resolved-path grouping as _resolve_stats_output_path(). Defaults to
        "markups_report.csv"."""
        return self._resolve_pattern_path(self.be_cfg.markups_output_path, specimen, "markups_report.csv")

    def _write_markups_report(self):
        """Write self.markup_rows to one or more CSVs, grouped purely by each row's already-
        resolved "_markups_path" (see _resolve_markups_output_path()) - specimens that resolved to
        the same path share one file, specimens that resolved to different paths get separate
        files. Each file's rows are sorted by key columns then label."""
        import csv
        if not self.markup_rows:
            logger.warning("[BatchProcessor] markups_report enabled but no markup rows produced (no defined control points in any 'finished' specimen's markups).")
            return

        key_cols = list(self.cfg.key_columns)
        fieldnames = key_cols + ["label", "x", "y", "z"]

        groups = {}
        for row in self.markup_rows:
            groups.setdefault(row["_markups_path"], []).append(row)

        written_paths = []
        total_rows = 0
        for out_path, rows in groups.items():
            rows_sorted = sorted(rows, key=lambda r: tuple(str(r[c]) for c in key_cols) + (str(r["label"]),))
            out_dir = os.path.dirname(out_path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows_sorted)
            logger.info(f"[BatchProcessor] wrote {len(rows_sorted)} markup row(s) -> {out_path}")
            written_paths.append(out_path)
            total_rows += len(rows_sorted)

        n_specimens = len(set(tuple(r[c] for c in key_cols) for r in self.markup_rows))
        dialog_rows = [("markup rows", total_rows), ("specimens", n_specimens)]
        if len(written_paths) == 1:
            dialog_rows.append(("path", written_paths[0]))
        else:
            dialog_rows.append(("files", len(written_paths)))
            for p in written_paths:
                dialog_rows.append(("", p))
        self.logic.show_key_value_dialog("Markups report finished", dialog_rows)

    def _resolve_root(self):
        """batch_export.output_dir - the shared, optional ROOT for this whole batch run: unset -> study_dir; relative -> resolved under study_dir; absolute -> used as-is. Used both for segment/markup export (further combined with output_dir_pattern below) and as the anchor for the statistics pattern - the one thing genuinely shared between them."""
        root = self.be_cfg.output_dir
        if not root:
            return self.logic.study_dir
        if not os.path.isabs(root):
            root = os.path.join(self.logic.study_dir, root)
        return root

    def _resolve_output_dir(self, specimen):
        """Resolve batch_export.output_dir (the shared root, see
        _resolve_root()) + output_dir_pattern (a curly-brace pattern
        resolved PER SPECIMEN via the same {column} mechanism as the
        General tab's own output_dir_pattern - any key/database.csv/
        preseg.csv column; unset defaults the same way too, joining the
        key columns). Governs SEGMENT and MARKUP export only - the
        statistics pattern is anchored to the same root but does NOT go
        through this per-specimen subfolder pattern, see
        _resolve_stats_output_path(). Falls back entirely to the
        specimen's own out_dir when output_dir itself is unset (nothing
        configured here at all)."""
        if not self.be_cfg.output_dir:
            return specimen.out_dir
        root = self._resolve_root()
        pattern = self.be_cfg.output_dir_pattern or "/".join(f"{{{k}}}" for k in self.cfg.key_columns)
        rel = specimen._format(pattern, what="batch output_dir_pattern")
        return os.path.join(root, rel)

    def _resolve_stats_output_path(self, specimen):
        """Resolve batch_export.stats_output_path (the "batch segment
        statistics pattern") for THIS specimen. If the result is
        relative, it's anchored to the SAME root as segment/markup export
        (_resolve_root() - batch_export.output_dir if set, else
        study_dir) - but, unlike segment/markup files, NEVER nested
        through output_dir_pattern; this pattern is its own, separate
        path directly under that root. Defaults to "report.csv". Two
        specimens that resolve to the same final path share one CSV;
        specimens that resolve to different paths (e.g. the pattern
        references a column whose value differs) end up in separate files
        - no separate flag needed for that, see _write_stats_csv()."""
        return self._resolve_pattern_path(self.be_cfg.stats_output_path, specimen, "report.csv")

    def _resolve_pattern_path(self, pattern, specimen, default):
        """Shared resolution for batch_export's stats/markups output-path patterns:
        substitutes {date}/{time}/{datetime} (colon-free {time}, filesystem-safe - Windows
        disallows ':' in filenames), strips the {index} placeholder (see below), then resolves any
        remaining {column} placeholders from this specimen's own context (same mechanism as
        output_dir_pattern). A relative result is anchored under _resolve_root(); an absolute one
        is returned as-is. If the pattern contained {index}, the lowest-available two-digit _NN
        suffix (starting at _01) is appended before the extension, based on what already exists on
        disk - this is the ONLY case where an existing file is not silently overwritten; without
        {index} in the pattern, collisions overwrite exactly as before."""
        import datetime
        out_path = pattern or default
        if "{date}" in out_path:
            out_path = out_path.replace("{date}", datetime.date.today().isoformat())
        if "{time}" in out_path:
            out_path = out_path.replace("{time}", datetime.datetime.now().strftime("%H-%M-%S"))
        if "{datetime}" in out_path:
            out_path = out_path.replace("{datetime}", datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        has_index = "{index}" in out_path
        if has_index:
            out_path = out_path.replace("{index}", "")
        out_path = specimen._format(out_path, what="batch report path")
        if not os.path.isabs(out_path):
            out_path = os.path.join(self._resolve_root(), out_path)
        if has_index:
            out_path = self._insert_free_index(out_path)
        return out_path

    def _insert_free_index(self, path):
        """Insert the lowest-available two-digit _NN suffix (before the extension), starting at
        _01, that doesn't already exist on disk - only called for a pattern that contains
        {index}. Deterministic across specimens sharing the same base pattern within one run,
        since nothing is written to disk until _write_stats_csv()/_write_markups_report() runs at
        the very end - every specimen resolving the same base pattern therefore lands on the same
        final, still-free path, so grouping-by-resolved-path keeps working."""
        base, ext = os.path.splitext(path)
        idx = 1
        while True:
            candidate = f"{base}_{idx:02d}{ext}"
            if not os.path.exists(candidate):
                return candidate
            idx += 1

    def _process_segments(self, specimen, geo_ref_node, stats_ref_names, out_dir, stats_path):
        """Export each segment to its own labelmap via Slicer's native
        ExportSegmentsToLabelmapNode (geometry from geo_ref_node), then -
        depending on cfg.batch_export - write it to a file and/or fold it
        into the stats table (one row per configured sample image), before
        discarding the temporary labelmap node. export_segments and
        compute_stats each apply their OWN, independent segment filter
        (segments_filter / stats_segments_filter respectively) - a segment
        can be exported without being included in the statistics, or vice
        versa; a segment matching neither filter is skipped entirely
        (never exported to a labelmap at all)."""
        be_cfg = self.be_cfg
        export_filter = be_cfg.segments_filter
        stats_filter = be_cfg.stats_segments_filter
        if be_cfg.export_segments and not os.path.isdir(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        seg = specimen.segmentation_node.GetSegmentation()
        slicer.mrmlScene.StartState(slicer.mrmlScene.BatchProcessState)
        try:
            for seg_id in list(seg.GetSegmentIDs()):
                seg_name = seg.GetSegment(seg_id).GetName()
                do_export = be_cfg.export_segments and (not export_filter or seg_name in export_filter)
                do_stats = be_cfg.compute_stats and (not stats_filter or seg_name in stats_filter)
                if not (do_export or do_stats):
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

                if do_export:
                    storage = labelmap.CreateDefaultStorageNode()
                    storage.SetHideFromEditors(True)
                    out_file = os.path.join(out_dir, f"{specimen.label}-{seg_name}.nii.gz")
                    storage.SetFileName(out_file)
                    storage.WriteData(labelmap)
                    logger.info(f"[BatchProcessor] saved {out_file}")
                    slicer.mrmlScene.RemoveNode(storage)

                if do_stats:
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
                        self._add_stats_row(specimen, image_name, seg_name, labelmap, mask_arr, sample_arr, stats_path)

                if slicer.mrmlScene.IsNodePresent(labelmap):
                    slicer.mrmlScene.RemoveNode(labelmap)
                if display_node is not None and slicer.mrmlScene.IsNodePresent(display_node):
                    slicer.mrmlScene.RemoveNode(display_node)
                if (color_node is not None and slicer.mrmlScene.IsNodePresent(color_node)
                        and color_node.GetID() not in self._pre_existing_color_node_ids):
                    slicer.mrmlScene.RemoveNode(color_node)
        finally:
            slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)

    def _add_stats_row(self, specimen, image_name, seg_name, labelmap, mask_arr, sample_arr, stats_path):
        """Compute this one (sample image, segment) pair's metrics (cfg.batch_export.stats_metrics, or the Definitions default) and append a row to self.stats_rows, tagged with this specimen's already-resolved stats_path under a private "_stats_path" key - used only to group/route rows to the right CSV file at write time, never written out as an actual column."""
        np = self._np
        metrics = self.be_cfg.stats_metrics or list(DEFAULT_STATS_METRICS)
        roi_pixels = sample_arr[mask_arr == 1]
        voxel_volume = float(np.prod(labelmap.GetSpacing()))

        row = dict(zip(self.cfg.key_columns, specimen.key_values))
        row["image"] = image_name
        row["segment"] = seg_name
        for metric_name in metrics:
            row[metric_name] = self._compute_metric(metric_name, roi_pixels, voxel_volume)
        row["_stats_path"] = stats_path
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

    def _write_stats_csv(self):
        """Write self.stats_rows to one or more CSVs - grouped purely by
        each row's already-resolved "_stats_path" (see
        _resolve_stats_output_path()): specimens that resolved to the
        same path share one file; specimens that resolved to different
        paths get separate files. No separate grouping flag anywhere -
        it's entirely a function of what the pattern resolves to. Each
        file's rows are sorted by key columns, then image, then segment
        name, via the standard library's csv module."""
        import csv
        if not self.stats_rows:
            logger.warning("[BatchProcessor] compute_stats enabled but no rows produced (no matching segments in any 'finished' specimen - see warnings above).")
            return

        cfg = self.cfg
        key_cols = list(cfg.key_columns)
        metrics = self.be_cfg.stats_metrics or list(DEFAULT_STATS_METRICS)
        fieldnames = key_cols + ["image", "segment"] + list(metrics)

        groups = {}
        for row in self.stats_rows:
            groups.setdefault(row["_stats_path"], []).append(row)

        written_paths = []
        total_rows = 0
        for out_path, rows in groups.items():
            rows_sorted = sorted(
                rows, key=lambda r: tuple(str(r[c]) for c in key_cols) + (str(r["image"]), str(r["segment"])))
            out_dir = os.path.dirname(out_path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                # extrasaction="ignore": rows carry an internal "_stats_path" tag not in fieldnames
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


def batch_exporter(logic):
    """Standalone entry point, kept for Python-console convenience and
    backward compatibility - just runs BatchProcessor(logic).run()."""
    BatchProcessor(logic).run()
