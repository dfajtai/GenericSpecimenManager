"""
specimen.py
===========
GenericSpecimen: one specimen - its database/preseg rows, the Slicer nodes it owns, and its load/save/close lifecycle.
"""

import os

import slicer

from Resources.core import safe_io
from Resources.core.config_model import (
    ImageConfig,
    MarkupsConfig,
    SegmentConfig,
    SegmentationConfig,
    StudyConfig,
    merge_image_overrides,
    merge_segment_overrides,
)
from Resources.core.logging_setup import logger
from Resources.core.status import parse_status
from Resources.definitions import IMAGES_READ_ONLY_BY_DEFAULT, KEEP_PREVIOUS_SPECIMEN_FILES
from Resources.utils.segment_editor import activate_segment_editor
from Resources.utils.volume_rendering import start_volume_rendering
from Resources.utils.workspace import customize_workplace


class GenericSpecimen:
    """One specimen: its database/preseg CSV rows, the Slicer nodes it currently owns, and the load/save/close lifecycle. Built and tracked by GenericSpecimenManagerLogic, one instance per (currently-loaded-or-just-closed) specimen."""
    def __init__(self, key_values, cfg: StudyConfig, db_row, preseg_row, study_dir):
        """One row of preseg.csv/database.csv (one specimen), plus the live Slicer nodes it owns once loaded via load()."""
        self.cfg = cfg
        self.key_columns = cfg.key_columns
        self.key_values = tuple(key_values)
        self.context = dict(zip(self.key_columns, self.key_values))
        self.db_info = dict(db_row or {})
        self.preseg_info = dict(preseg_row or {})
        self.study_dir = study_dir

        self.node_dict = {}
        self.writeable = {}
        self.segmentation_node = None
        self.markups_node = None
        self.volume_rendering_nodes = []
        self.volume_rendering_roi = []

        self.row_index = None
        self.status_col_index = None
        self.markups_source = None     # how the markups node came to be: "loaded" / "from template" / "new (empty)"
        self.loaded_own_data = False   # True once a segmentation/markups file this specimen previously saved was loaded

    @property
    def key(self):
        """The specimen's composite key as a tuple, e.g. ('D001',) or ('20180109','R12','L')."""
        return self.key_values

    @property
    def label(self):
        """Human-readable specimen id - the key tuple joined with '-'. Used for node names and default output filenames."""
        return "-".join(str(v) for v in self.key_values)

    @property
    def out_dir(self):
        """This specimen's output folder under study_dir, built from output_dir_pattern - a curly-brace format string (e.g. "{ID}/{measurement}"), same placeholder rules as any other path_pattern in this schema."""
        rel = self._format(self.cfg.output_dir_pattern, what="output_dir_pattern")
        return os.path.join(self.study_dir, rel)

    def _context(self, extra=None):
        """Build the placeholder dict used to .format() path_pattern strings: every key column + every database.csv/preseg.csv column for this specimen, optionally topped up with extra keys (e.g. {'name': ...} for images, {'segment_name': ...} for segments)."""
        ctx = dict(self.context)
        ctx.update(self.db_info)
        ctx.update(self.preseg_info)
        if extra:
            ctx.update(extra)
        return ctx

    def _format(self, pattern, extra=None, what="pattern"):
        """Fill in a `{column}` pattern for this specimen. A pattern that names a column this specimen doesn't have, or is malformed (unbalanced braces...), raises a ValueError that says which pattern and which column - instead of a bare KeyError like `'volume'`."""
        context = self._context(extra)
        try:
            return pattern.format(**context)
        except KeyError as e:
            raise ValueError(f"{what} '{pattern}' uses {{{e.args[0]}}}, but there is no such column for specimen {self.label} "
                             f"(available: {', '.join(sorted(context))})") from None
        except (ValueError, IndexError) as e:
            raise ValueError(f"{what} '{pattern}' is not a valid pattern: {e}") from None

    def _to_abs(self, rel):
        """Resolve a path to absolute: study_dir-relative unless already absolute. Also collapses an accidental doubled path separator (e.g. from a CSV value that already had a leading slash)."""
        rel = str(rel).replace(2 * os.sep, os.sep)
        if os.path.isabs(rel):
            return rel
        return os.path.join(self.study_dir, rel)

    def markups_out_path(self):
        """Where this specimen's markups file lives/will be saved: markups.csv_column's value if set, else markups.path_pattern.format(...) (default '{label}-markups.mrk.json')."""
        markups_cfg = self.cfg.markups
        rel = self.preseg_info.get(markups_cfg.csv_column) if markups_cfg.csv_column else None
        if not rel:
            pattern = markups_cfg.path_pattern or "{label}-markups.mrk.json"
            rel = self._format(pattern, {"label": self.label}, "markups path_pattern")
        return self._to_abs(rel)

    def segmentation_out_path(self):
        """Where this specimen's segmentation file lives/will be saved, inside out_dir - segmentation.output_filename (default 'segment.seg.nrrd')."""
        seg_cfg = self.cfg.segmentation
        return os.path.join(self.out_dir, seg_cfg.output_filename or "segment.seg.nrrd")

    @property
    def status(self):
        """This specimen's SpecimenStatus, from its cached database row (empty/unknown -> UNTOUCHED)."""
        return parse_status(self.db_info.get(self.cfg.status_column))

    def update_status(self, table):
        """Refresh this specimen's cached status value from the live database table - call after the user edits that cell in the GUI so db_info stays in sync."""
        if self.row_index is None or self.status_col_index is None:
            return
        try:
            self.db_info[self.cfg.status_column] = table.GetCellText(self.row_index, self.status_col_index)
        except Exception as e:
            slicer.util.errorDisplay("Failed to update status: " + str(e))

    def _expand_image_entries(self):
        """The per-specimen image job list: every named images[] entry, in order. Entries without a name (e.g. leftovers of removed options in an old config) are skipped silently. Image names are node_dict keys - two entries with the same name would overwrite each other (leaving the first loaded node orphaned in the scene), so the first is kept and the rest are skipped with a warning."""
        jobs, seen = [], set()
        for img_cfg in self.cfg.images:
            if not img_cfg.name:
                continue
            if img_cfg.name in seen:
                logger.warning(f"[GenericSpecimen] {self.label}: image name '{img_cfg.name}' is listed more than once - the repeats are skipped")
                continue
            seen.add(img_cfg.name)
            jobs.append(img_cfg)
        return jobs

    def _resolve_image_cfg(self, img_cfg: ImageConfig) -> ImageConfig:
        """Merge defaults.image -> the named preset (if img_cfg.preset is set) -> img_cfg's own fields into the final, effective ImageConfig for this image job."""
        preset = self.cfg.presets.get(img_cfg.preset) if img_cfg.preset else None
        return merge_image_overrides(self.cfg.defaults.image, preset, img_cfg)

    def resolve_image_path(self, img_cfg: ImageConfig):
        """Turn an already-merged ImageConfig into an absolute file path: its csv_column's value if present and non-empty, else path_pattern.format(...), else raise (caller decides whether that's fatal via 'required')."""
        if img_cfg.csv_column and self.preseg_info.get(img_cfg.csv_column):
            rel = self.preseg_info[img_cfg.csv_column]
        elif img_cfg.path_pattern:
            rel = self._format(img_cfg.path_pattern, {"name": img_cfg.name}, f"image '{img_cfg.name}' path_pattern")
        else:
            raise ValueError(f"Cannot resolve path for image '{img_cfg.name}': no csv_column value and no path_pattern given")
        return self._to_abs(rel)

    def _resolve_color_node(self, name_or_id):
        """Look up a Slicer color table node by ID first, then by name - returns None if neither resolves (caller just skips applying it)."""
        try:
            node = slicer.mrmlScene.GetNodeByID(name_or_id)
            if node:
                return node
        except Exception:
            pass
        try:
            return slicer.util.getNode(name_or_id)
        except Exception:
            return None

    def _apply_visual_props(self, node, props: ImageConfig):
        """Apply window/level (auto, min/max, or width/level form), interpolate, color table, and threshold from a merged ImageConfig onto a just-loaded volume's display node."""
        disp = node.GetDisplayNode()
        if disp is None:
            return
        wl = props.window_level
        if wl:
            if wl.auto:
                disp.SetAutoWindowLevel(1)
            elif wl.window is not None or wl.level is not None:
                disp.SetAutoWindowLevel(0)
                disp.SetWindowLevel(wl.window if wl.window is not None else 1, wl.level if wl.level is not None else 0)
            else:
                disp.SetAutoWindowLevel(0)
                disp.SetWindowLevelMinMax(wl.min if wl.min is not None else -150, wl.max if wl.max is not None else 700)
        if props.interpolate is not None:
            disp.SetInterpolate(1 if props.interpolate else 0)
        if props.color_table:
            color_node = self._resolve_color_node(props.color_table)
            if color_node:
                disp.SetAndObserveColorNodeID(color_node.GetID())
        th = props.threshold
        if th:
            disp.SetThreshold(th.min if th.min is not None else 0, th.max if th.max is not None else 0)
            (disp.ApplyThresholdOn() if (th.apply if th.apply is not None else True) else disp.ApplyThresholdOff())

    def _resolve_segment_cfg(self, seg_def: SegmentConfig) -> SegmentConfig:
        """Merge defaults.segment -> the segment's own fields into the final, effective SegmentConfig."""
        return merge_segment_overrides(self.cfg.defaults.segment, seg_def)

    def resolve_segment_path(self, seg_cfg: SegmentationConfig, seg_def: SegmentConfig):
        """Resolve one segment's label-image path: its own csv_column value, else its own or the segmentation-level shared path_pattern, else None (meaning 'build an empty placeholder instead', regardless of source)."""
        if seg_def.csv_column and self.preseg_info.get(seg_def.csv_column):
            return self._to_abs(self.preseg_info[seg_def.csv_column])
        pattern = seg_def.path_pattern or seg_cfg.path_pattern
        if pattern:
            return self._to_abs(self._format(pattern, {"segment_name": seg_def.name}, f"segment '{seg_def.name}' path_pattern"))
        return None

    def _add_empty_segment(self, segmentation_node, name, reference_volume_node, color=None):
        """Create a same-geometry, all-zero labelmap and add it as a new (empty) segment. Used both for source='empty' segments and as the fallback when a 'file' segment's path can't be resolved or loaded."""
        if reference_volume_node is None:
            logger.warning(f"[GenericSpecimen] no reference volume, skipping empty segment '{name}'")
            return
        dummy = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        slicer.modules.volumes.logic().CreateLabelVolumeFromVolume(slicer.mrmlScene, dummy, reference_volume_node)
        dummy.GetImageData().GetPointData().GetScalars().Fill(0)
        img = slicer.modules.segmentations.logic().CreateOrientedImageDataFromVolumeNode(dummy)
        if color:
            segmentation_node.AddSegmentFromBinaryLabelmapRepresentation(img, name, color)
        else:
            segmentation_node.AddSegmentFromBinaryLabelmapRepresentation(img, name)
        slicer.mrmlScene.RemoveNode(dummy)

    def _build_segment(self, seg_def: SegmentConfig, segmentation_node, reference_volume_node):
        """Build one segment into segmentation_node: an empty placeholder if source='empty' (or its path never resolves/loads), otherwise the loaded label image, colored if a color was given."""
        seg_def = self._resolve_segment_cfg(seg_def)
        name, color, source = seg_def.name, seg_def.color, (seg_def.source or "file")

        if source == "empty":
            self._add_empty_segment(segmentation_node, name, reference_volume_node, color)
            return
        try:
            path = self.resolve_segment_path(self.cfg.segmentation, seg_def)
        except Exception:
            path = None
        if path is None:
            logger.warning(f"[GenericSpecimen] segment '{name}': no path resolvable, creating empty segment instead")
            self._add_empty_segment(segmentation_node, name, reference_volume_node, color)
            return
        try:
            mask_node = slicer.util.loadLabelVolume(path)
            img = slicer.modules.segmentations.logic().CreateOrientedImageDataFromVolumeNode(mask_node)
            if color:
                segmentation_node.AddSegmentFromBinaryLabelmapRepresentation(img, name, color)
            else:
                segmentation_node.AddSegmentFromBinaryLabelmapRepresentation(img, name)
            slicer.mrmlScene.RemoveNode(mask_node)
        except Exception:
            logger.warning(f"[GenericSpecimen] unable to load segment image '{path}', creating empty segment '{name}'")
            self._add_empty_segment(segmentation_node, name, reference_volume_node, color)

    def load_for_batch(self, image_names=None):
        """Lean load path for headless batch operations (BatchProcessor):
        loads ONLY the segmentation (if configured, and only if its file
        already exists - never builds a fresh empty one here, since batch
        operations only ever run on 'finished' specimens that should already
        have one saved) and, if given, the SPECIFIC named images in
        image_names - typically just one reference/"master" volume, not
        the full configured image set. Unlike load(), this skips markups,
        customize_workplace() (crosshair/window-level/Four-Up layout),
        volume rendering, and Segment Editor activation entirely - none of
        that is needed for a headless export/stats run, and skipping it is
        most of the speedup over load(). Every node loaded here is also
        marked SetHideFromEditors(True) - they're headless/transient
        (removed right after processing, never shown to the user), and
        letting Subject Hierarchy track them is what causes a
        'GetSubjectHierarchyNode: Invalid scene given' warning storm when
        several get removed in a row via close()."""
        wanted = set(image_names or [])
        if wanted:
            for raw_img_cfg in self._expand_image_entries():
                img_cfg = self._resolve_image_cfg(raw_img_cfg)
                if img_cfg.name not in wanted:
                    continue
                itype = img_cfg.type or "volume"
                try:
                    path = self.resolve_image_path(img_cfg)
                    node = slicer.util.loadLabelVolume(path) if itype == "labelmap" else slicer.util.loadVolume(path)
                    node.SetName(img_cfg.name)
                except Exception as e:
                    logger.warning(f"[GenericSpecimen] (batch) could not load image '{img_cfg.name}' for {self.label}: {e}")
                    continue
                node.SetHideFromEditors(True)
                self.node_dict[img_cfg.name] = node
                self.writeable[img_cfg.name] = path

        seg_cfg = self.cfg.segmentation
        if seg_cfg.enabled and os.path.exists(self.segmentation_out_path()):
            self._load_segmentation(seg_cfg)
            if self.segmentation_node is not None:
                self.segmentation_node.SetHideFromEditors(True)

    def _load_segmentation(self, seg_cfg: SegmentationConfig):
        """Load this specimen's segmentation file if it already exists on disk, otherwise build a fresh vtkMRMLSegmentationNode from segmentation.segments[]."""
        out_path = self.segmentation_out_path()
        ref_node = self.node_dict.get(seg_cfg.reference_image) if seg_cfg.reference_image else None

        if os.path.exists(out_path):
            logger.info("[GenericSpecimen] loading existing segmentation...")
            self.loaded_own_data = True
            seg_node = slicer.util.loadSegmentation(out_path)
            if ref_node is not None:
                seg_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_node)
        else:
            logger.info("[GenericSpecimen] initializing new segmentation...")
            seg_node = slicer.vtkMRMLSegmentationNode()
            slicer.mrmlScene.AddNode(seg_node)
            seg_node.CreateDefaultDisplayNodes()
            if ref_node is not None:
                seg_node.SetReferenceImageGeometryParameterFromVolumeNode(ref_node)
            for seg_def in seg_cfg.segments:
                self._build_segment(seg_def, seg_node, ref_node)
            seg_node.SetName("Segmentation")

        self.segmentation_node = seg_node
        self.writeable["__segmentation__"] = out_path

    def _load_markups(self, markups_cfg: MarkupsConfig):
        """Load this specimen's markups file; if it doesn't exist yet, fall back to markups.template_path (if set, renamed to this specimen) or an empty new fiducial list."""
        m_path = self.markups_out_path()
        try:
            m_node = slicer.util.loadMarkups(m_path)
            self.loaded_own_data = True
            self.markups_source = "loaded"
        except Exception:
            if markups_cfg.template_path and os.path.exists(markups_cfg.template_path):
                m_node = slicer.util.loadMarkups(markups_cfg.template_path)
                m_node.SetName(f"{self.label}-markups")
                self.markups_source = "from template"
            else:
                m_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", f"{self.label}-markups")
                self.markups_source = "new (empty)"
        if markups_cfg.color and m_node.GetDisplayNode():
            m_node.GetDisplayNode().SetColor(*markups_cfg.color)
        display = m_node.GetDisplayNode()
        if display is not None:
            try:
                if markups_cfg.glyph_type:
                    display.SetGlyphTypeFromString(markups_cfg.glyph_type)
                if markups_cfg.size is not None:
                    if markups_cfg.size_absolute:
                        display.SetUseGlyphScale(False)          # size in mm instead of the relative scale
                        display.SetGlyphSize(float(markups_cfg.size))
                    else:
                        display.SetUseGlyphScale(True)
                        display.SetGlyphScale(float(markups_cfg.size))
            except Exception as e:
                logger.warning(f"[GenericSpecimen] could not apply the markups glyph/size settings: {e}")
        self.markups_node = m_node
        self.node_dict["__markups__"] = m_node
        if markups_cfg.writable if markups_cfg.writable is not None else True:
            self.writeable["__markups__"] = m_path

    def load(self):
        """Load everything configured for this specimen, in order: images (background/label/foreground slice-view layers applied once, after the loop), segmentation, markups, workspace setup (crosshair/blanket window-level/segment opacity/default Four-Up layout), volume rendering, then - if segment_editor is configured - hand off to the Segment Editor. Prints an itemized table of what was actually loaded (and what was skipped, with why) at the end."""
        self.loaded_own_data = False
        background_node = None
        label_node, label_opacity = None, None
        foreground_node, foreground_opacity = None, None
        load_rows = []

        for raw_img_cfg in self._expand_image_entries():
            img_cfg = self._resolve_image_cfg(raw_img_cfg)
            name = img_cfg.name
            required = img_cfg.required or False
            itype = img_cfg.type or "volume"
            try:
                path = self.resolve_image_path(img_cfg)
                node = slicer.util.loadLabelVolume(path) if itype == "labelmap" else slicer.util.loadVolume(path)
                node.SetName(name)
            except Exception as e:
                if required:
                    raise
                logger.warning(f"[GenericSpecimen] optional image '{name}' not loaded: {e}")
                load_rows.append((name, itype, img_cfg.role or "-", "skipped", str(e)))
                continue

            self.node_dict[name] = node
            self.writeable[name] = path
            self._apply_visual_props(node, img_cfg)
            load_rows.append((name, itype, img_cfg.role or "-", "loaded", path))
            opacity = img_cfg.opacity
            role = img_cfg.role
            if role == "background":
                background_node = node
            elif role == "label":
                label_node = node
                if opacity is not None:
                    label_opacity = opacity
            elif role == "foreground":
                foreground_node = node
                if opacity is not None:
                    foreground_opacity = opacity

        slice_kwargs = {}
        if background_node is not None:
            slice_kwargs["background"] = background_node
        if label_node is not None:
            slice_kwargs["label"] = label_node
            slice_kwargs["labelOpacity"] = label_opacity if label_opacity is not None else 0.15
        if foreground_node is not None:
            slice_kwargs["foreground"] = foreground_node
            slice_kwargs["foregroundOpacity"] = foreground_opacity if foreground_opacity is not None else 0.5
        if slice_kwargs:
            slicer.util.setSliceViewerLayers(**slice_kwargs)

        seg_cfg = self.cfg.segmentation
        if seg_cfg.enabled:
            seg_on_disk = os.path.exists(self.segmentation_out_path())
            self._load_segmentation(seg_cfg)
            seg_status = ("loaded" if seg_on_disk else "new (empty)") if self.segmentation_node else "skipped"
            load_rows.append(("segmentation", "-", "-", seg_status, self.segmentation_out_path()))

        markups_cfg = self.cfg.markups
        if markups_cfg.enabled:
            self._load_markups(markups_cfg)
            load_rows.append(("markups", "-", "-", self.markups_source if self.markups_node else "skipped", self.markups_out_path()))

        logger.info(f"[GenericSpecimen] loaded {self.label}: {len(load_rows)} item(s) -> {self.out_dir}")
        self._print_table(f"loaded {self.label}", ["item", "type", "role", "status", "path"], load_rows)

        customize_workplace(self.cfg, self.segmentation_node)

        vr_entries = [e for e in self.cfg.volume_rendering if e.enabled]
        if vr_entries:
            start_volume_rendering(vr_entries, self.node_dict, self.cfg.workspace, self.markups_node,
                                   self.volume_rendering_nodes, self.volume_rendering_roi)

        if seg_cfg.enabled and self.cfg.segment_editor.is_configured():
            ref_name = self.cfg.segmentation.reference_image
            activate_segment_editor(self.cfg.segment_editor, self.segmentation_node,
                                    self.node_dict.get(ref_name) if ref_name else None)


    def save(self):
        """Write this specimen's writeable nodes back to disk. Segmentation and markups are always attempted. Images (volumes/labelmaps) are skipped entirely - not written, not even logged - if IMAGES_READ_ONLY_BY_DEFAULT is True and the node hasn't actually changed since it was loaded (see _node_has_changed()); this is the common case, since most images in a study are read-only source data. Logs one short INFO summary line (item count + output folder), plus the full itemized detail at DEBUG level."""
        if not os.path.isdir(self.out_dir):
            os.makedirs(self.out_dir, exist_ok=True)
        save_rows = []
        for logical_name, path in self.writeable.items():
            item = logical_name.strip("_") or logical_name
            is_volume = logical_name not in ("__segmentation__", "__markups__")
            node = (self.segmentation_node if logical_name == "__segmentation__" else
                    self.markups_node if logical_name == "__markups__" else
                    self.node_dict.get(logical_name))
            if node is None:
                save_rows.append((item, "skipped (no node)", path))
                continue

            status = "written"
            if is_volume and IMAGES_READ_ONLY_BY_DEFAULT:
                if not self._node_has_changed(node):
                    continue  # read-only and unchanged: skip silently, don't even log it
                status = "changed"

            out_dir = os.path.dirname(path)
            if out_dir and not os.path.isdir(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            self._write_node_safely(node, path, keep_previous=KEEP_PREVIOUS_SPECIMEN_FILES and not is_volume)
            save_rows.append((item, status, path))

        logger.info(f"[GenericSpecimen] saved {self.label}: {len(save_rows)} item(s) -> {self.out_dir}")
        self._print_table(f"saved {self.label} -> {self.out_dir}", ["item", "status", "path"], save_rows)

    def _write_node_safely(self, node, path, keep_previous):
        """Write one node to `path` without ever leaving a half-written file: the node is written to a temp file next to it, and only if that worked is it swapped in (see safe_io.atomic_write). With keep_previous the version being replaced stays as `<path>.prev` (one level) - used for the segmentation and markups, not for big source images."""
        def write(tmp_path):
            storage = node.CreateDefaultStorageNode()
            storage.SetHideFromEditors(True)
            storage.SetFileName(tmp_path)
            ok = storage.WriteData(node)
            if slicer.mrmlScene.IsNodePresent(storage):
                slicer.mrmlScene.RemoveNode(storage)
            if ok is not None and not ok:
                raise IOError(f"Slicer could not write '{os.path.basename(path)}'")
        safe_io.atomic_write(path, write, keep_previous=keep_previous)

    def _node_has_changed(self, node):
        """True if a storable node has been modified since it was last read/written, via the standard MRML GetModifiedSinceRead() check. Defensive: if the check itself isn't available/fails on your Slicer version, assume changed - safer to over-save than to silently lose an edit."""
        try:
            return bool(node.GetModifiedSinceRead())
        except Exception as e:
            logger.warning(f"[GenericSpecimen] could not check modified-state for '{node.GetName() if hasattr(node, 'GetName') else node}', assuming changed: {e}")
            return True

    def _print_table(self, title, headers, rows):
        """Print a simple, aligned ASCII table - the itemized load/save detail, at DEBUG level (see load()/save() for the short INFO-level summary line). Pure stdlib, no external table library needed."""
        logger.debug(f"[GenericSpecimen] {title}:")
        if not rows:
            logger.debug("  (nothing)")
            return
        widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], len(str(cell)))

        def fmt_row(cells):
            return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))

        logger.debug("  " + fmt_row(headers))
        logger.debug("  " + "-" * (sum(widths) + 2 * (len(widths) - 1)))
        for row in rows:
            logger.debug("  " + fmt_row(row))

    def close(self):
        """Remove every Slicer node this specimen created (images, segmentation, markups, volume rendering + its ROI) - called when switching to a different specimen or when the scene is closing. Wrapped in a BatchProcessState block (the standard Slicer technique for removing several nodes contiguously - see slicer.readthedocs.io's script repository) so observers like the Subject Hierarchy plugin defer their per-node bookkeeping until the whole removal is done, instead of reacting - sometimes with a harmless but noisy 'Invalid scene given' warning - to each node individually. Each node is also checked for a still-valid GetScene() right before removal - IsNodePresent() alone can say True while the node's own scene reference is already stale (i.e. it's effectively already detached), which is exactly what triggers that warning if we call RemoveNode on it anyway."""
        if slicer.mrmlScene.IsClosing():
            return
        logger.info(f"[GenericSpecimen] closing {self.label}")
        slicer.mrmlScene.StartState(slicer.mrmlScene.BatchProcessState)
        try:
            for vr_node in self.volume_rendering_nodes:
                if vr_node and self._node_removable(vr_node):
                    slicer.mrmlScene.RemoveNode(vr_node)
            self.volume_rendering_nodes = []
            for roi in self.volume_rendering_roi:
                if roi and self._node_removable(roi):
                    slicer.mrmlScene.RemoveNode(roi)
            self.volume_rendering_roi = []
            all_nodes = list(self.node_dict.values())
            if self.segmentation_node is not None and self.segmentation_node not in all_nodes:
                all_nodes.append(self.segmentation_node)
            for node in all_nodes:
                try:
                    if node and self._node_removable(node):
                        slicer.mrmlScene.RemoveNode(node)
                except Exception:
                    pass
        finally:
            slicer.mrmlScene.EndState(slicer.mrmlScene.BatchProcessState)
        self.node_dict = {}
        self.segmentation_node = None
        self.markups_node = None

    def _node_removable(self, node):
        """True if `node` is actually still safe to RemoveNode() - present in the scene AND its own GetScene() reference is still valid. A node can be IsNodePresent()==True yet already have a stale/None scene reference (e.g. after an earlier removal in the same batch touched something it was linked to) - calling RemoveNode on it anyway is exactly what triggers Subject Hierarchy's 'Invalid scene given' warning, so we just skip it: the node is already effectively gone."""
        try:
            return bool(slicer.mrmlScene.IsNodePresent(node)) and node.GetScene() is not None
        except Exception:
            return False
