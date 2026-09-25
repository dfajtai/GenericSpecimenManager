"""
GenericSpecimenEngine
======================

Shared, JSON-config-driven engine. Not a Slicer module on its own.
Config handling lives in ConfigModel.py (StudyConfig) - consumed here via
attribute access, not raw dict.get().
"""

import os
import re
import csv
from dataclasses import replace

import qt
import vtk
import ctk

from qt import QFileDialog

import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

from Resources.ConfigModel import (
    StudyConfig, ImageConfig, SegmentConfig, SegmentationConfig,
    MarkupsConfig, VolumeRenderingEntry, load_config,
    merge_image_overrides, merge_segment_overrides,
)
from Resources.ConfigEditor import ConfigEditorDialog
from Resources.HelpDialog import show_cheatsheet_dialog
from Resources.BatchProcessor import BatchProcessor, batch_exporter
from Resources.LoggingSetup import logger
from Resources.Definitions import (
    HIDE_RELOAD_AND_TEST as _DEFINITIONS_HIDE_RELOAD_AND_TEST,
    HIDE_HELP_AND_ACKNOWLEDGEMENT as _DEFINITIONS_HIDE_HELP_AND_ACKNOWLEDGEMENT,
    IMAGES_READ_ONLY_BY_DEFAULT,
    DEFAULT_STATS_METRICS,
    SPECIMEN_TABLE_MAX_VISIBLE_ROWS,
    SPECIMEN_TABLE_MIN_VISIBLE_ROWS,
    SpecimenStatus,
    SPECIMEN_STATUS_LABELS,
    SPECIMEN_STATUS_COLORS,
    SPECIMEN_ANNOTATION_FONT_SIZE,
    SPECIMEN_ANNOTATION_COLOR,
    SPECIMEN_ANNOTATION_BG_COLOR,
    SPECIMEN_ANNOTATION_BG_OPACITY,
    SPECIMEN_ANNOTATION_BG_PADDING,
)


def parse_status(text):
    """A database.csv status cell (str/int/None) -> SpecimenStatus; empty or anything unrecognized is UNTOUCHED."""
    try:
        return SpecimenStatus(int(str(text).strip()))
    except (ValueError, TypeError):
        return SpecimenStatus.UNTOUCHED


# (label, anchor) pairs of Resources/Html/module_help_cheatsheet.html, for the Help popup's section-jump combo
MODULE_HELP_SECTIONS = [
    ("Workflow", "workflow"), ("Study buttons & settings", "study-settings"), ("Specimen table", "specimen-table"),
    ("Status", "status"), ("Load, Save, Close", "load-save-close"), ("Reset selected specimen", "reset"),
    ("Batch export", "batch-export"), ("Config", "config"),
]


# ---------------------------------------------------------------------------
# GenericSpecimen
# ---------------------------------------------------------------------------

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
        rel = self.cfg.output_dir_pattern.format(**self._context())
        return os.path.join(self.study_dir, rel)

    def _context(self, extra=None):
        """Build the placeholder dict used to .format() path_pattern strings: every key column + every database.csv/preseg.csv column for this specimen, optionally topped up with extra keys (e.g. {'name': ...} for images, {'segment_name': ...} for segments)."""
        ctx = dict(self.context)
        ctx.update(self.db_info)
        ctx.update(self.preseg_info)
        if extra:
            ctx.update(extra)
        return ctx

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
            rel = pattern.format(**self._context({"label": self.label}))
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
        """Turn cfg.images into a concrete per-specimen job list. A normal entry (csv_column/path_pattern) -> exactly one job. A 'pattern' (regex) entry -> zero or more jobs, one per non-key preseg.csv column whose name matches the regex AND is non-empty for THIS specimen - so different specimens can end up with different numbers of images."""
        jobs = []
        for img_cfg in self.cfg.images:
            if not img_cfg.pattern:
                jobs.append(img_cfg)
                continue
            regex = re.compile(img_cfg.pattern)
            for col, val in self.preseg_info.items():
                if col in self.key_columns or not val or not regex.match(col):
                    continue
                name = col
                if img_cfg.strip_prefix and name.startswith(img_cfg.strip_prefix):
                    name = name[len(img_cfg.strip_prefix):]
                if img_cfg.strip_suffix and name.endswith(img_cfg.strip_suffix):
                    name = name[:-len(img_cfg.strip_suffix)]
                jobs.append(replace(img_cfg, name=name, csv_column=col,
                                     pattern=None, strip_prefix=None, strip_suffix=None))
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
            rel = img_cfg.path_pattern.format(**self._context({"name": img_cfg.name}))
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
            return self._to_abs(pattern.format(**self._context({"segment_name": seg_def.name})))
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
        _customize_workplace() (crosshair/window-level/Four-Up layout),
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

        self._customize_workplace()

        vr_entries = [e for e in self.cfg.volume_rendering if e.enabled]
        if vr_entries:
            self._start_volume_rendering(vr_entries)

        if seg_cfg.enabled and self.cfg.segment_editor.is_configured():
            self._activate_segment_editor()

    def _activate_segment_editor(self):
        """Switch to the Segment Editor module with THIS specimen's segmentation
        already selected and configured. Safe (unlike touching a bare template
        node) because we explicitly attach a real segmentation/source volume
        to the widget's node BEFORE activating any effect on it - activating
        an effect with no segmentation/volume context is what crashed before.
        """
        if self.segmentation_node is None:
            return

        try:
            segmentEditorWidget = slicer.modules.segmenteditor.widgetRepresentation().self().editor
        except Exception as e:
            logger.warning(f"[GenericSpecimen] could not access the Segment Editor widget: {e}")
            return

        segmentEditorWidget.setSegmentationNode(self.segmentation_node)

        ref_name = self.cfg.segmentation.reference_image
        ref_node = self.node_dict.get(ref_name) if ref_name else None
        if ref_node is not None:
            try:
                segmentEditorWidget.setSourceVolumeNode(ref_node)      # Slicer 5.2+
            except AttributeError:
                segmentEditorWidget.setMasterVolumeNode(ref_node)      # older Slicer

        editorNode = segmentEditorWidget.mrmlSegmentEditorNode()
        if editorNode is None:
            logger.warning("[GenericSpecimen] Segment Editor widget produced no live node, skipping")
            return

        se_cfg = self.cfg.segment_editor
        overwrite_map = {
            "none": slicer.vtkMRMLSegmentEditorNode.OverwriteNone,
            "all_segments": slicer.vtkMRMLSegmentEditorNode.OverwriteAllSegments,
            "visible_segments": slicer.vtkMRMLSegmentEditorNode.OverwriteVisibleSegments,
        }
        editorNode.SetOverwriteMode(overwrite_map.get(se_cfg.overwrite_mode or "none", slicer.vtkMRMLSegmentEditorNode.OverwriteNone))

        brush_cfg = se_cfg.brush
        if brush_cfg:
            if brush_cfg.shape == "sphere":
                editorNode.SetAttribute("BrushSphere", "1")
            elif brush_cfg.shape == "circle":
                editorNode.SetAttribute("BrushSphere", "0")
            if brush_cfg.diameter_mm is not None:
                if brush_cfg.relative:
                    editorNode.SetAttribute("BrushDiameterIsRelative", "1")
                    editorNode.SetAttribute("BrushRelativeDiameter", str(brush_cfg.diameter_mm))
                else:
                    editorNode.SetAttribute("BrushDiameterIsRelative", "0")
                    editorNode.SetAttribute("BrushAbsoluteDiameter", str(brush_cfg.diameter_mm))

        for k, v in se_cfg.attributes.items():
            editorNode.SetAttribute(k, str(v))

        # Safe now: editorNode has a real segmentation (and source volume, if
        # resolved) attached above - NOT a bare template. Deliberately not
        # touching the live effect object (no effect.setParameter(), no
        # manual updateGUIFromMRML()) - SetAttribute()/SetActiveEffectName()
        # already trigger the widget's own automatic MRML->GUI sync; calling
        # into the effect object again on top of that is what caused the
        # signal-blocking GUI freeze in an earlier version.
        if se_cfg.active_effect:
            editorNode.SetActiveEffectName(se_cfg.active_effect)

        # Bring the module into view LAST, once everything above is already
        # configured, so the user never sees an unconfigured flash of it.
        slicer.util.selectModule("SegmentEditor")

    def _customize_workplace(self):
        """Per-specimen workspace touch-ups: get-or-create (never replace - see the comment inline for why) the default Segment Editor node, link slice views, switch to the standard Four-Up layout, tune the crosshair, apply the blanket window/level if configured, and set every segment's 2D fill/outline opacity."""
        slicer.app.layoutManager().setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)

        defaultSegmentEditorNode = slicer.mrmlScene.GetDefaultNodeByClass("vtkMRMLSegmentEditorNode")
        if defaultSegmentEditorNode is None:
            defaultSegmentEditorNode = slicer.vtkMRMLSegmentEditorNode()
            slicer.mrmlScene.AddDefaultNode(defaultSegmentEditorNode)

        sliceCompositeNodes = slicer.util.getNodesByClass('vtkMRMLSliceCompositeNode')
        defaultSliceCompositeNode = slicer.mrmlScene.GetDefaultNodeByClass('vtkMRMLSliceCompositeNode')
        if not defaultSliceCompositeNode:
            defaultSliceCompositeNode = slicer.mrmlScene.CreateNodeByClass('vtkMRMLSliceCompositeNode')
            defaultSliceCompositeNode.UnRegister(None)
            slicer.mrmlScene.AddDefaultNode(defaultSliceCompositeNode)
        sliceCompositeNodes.append(defaultSliceCompositeNode)
        for n in sliceCompositeNodes:
            n.SetLinkedControl(True)

        self._apply_workspace_settings()

        wl_cfg = self.cfg.window_level
        if wl_cfg.enabled:
            for v in slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeDisplayNode"):
                v.InterpolateOff()
                v.SetAutoWindowLevel(0)
                v.SetWindowLevelMinMax(wl_cfg.min if wl_cfg.min is not None else -150, wl_cfg.max if wl_cfg.max is not None else 700)

        if self.segmentation_node is not None:
            seg = self.segmentation_node.GetSegmentation()
            for seg_id in list(seg.GetSegmentIDs()):
                self.segmentation_node.GetDisplayNode().SetSegmentOpacity2DFill(seg_id, 0.85)
                self.segmentation_node.GetDisplayNode().SetSegmentOpacity2DOutline(seg_id, 1)

        self._apply_slice_rotation()

    def _resolve_enum(self, obj, name, default=None):
        """Look up a named constant on a live MRML/VTK node instance by
        string (e.g. crosshair, "ShowBasic" -> crosshair.ShowBasic) - lets
        config authors specify Slicer/VTK enum values by their exact name
        without us hardcoding every possible one. Falls back to `default`
        if name is falsy; returns None (caller skips that setting) with a
        printed warning if the resulting name doesn't exist on obj, so a
        typo never crashes the load."""
        value_name = name or default
        if not value_name:
            return None
        if not hasattr(obj, value_name):
            logger.warning(f"[GenericSpecimen] unknown enum constant '{value_name}' on {type(obj).__name__}, skipping")
            return None
        return getattr(obj, value_name)

    def _apply_workspace_settings(self):
        """Apply cfg.workspace's crosshair mode/behavior/thickness (falling
        back to this module's long-standing defaults - ShowBasic /
        OffsetJumpSlice / Fine - so an absent 'workspace' section changes
        nothing), plus the purely opt-in ruler, 3D/2D orientation-marker,
        and L/R view convention settings."""
        ws_cfg = self.cfg.workspace

        crosshair = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLCrosshairNode")
        if crosshair:
            mode = self._resolve_enum(crosshair, ws_cfg.crosshair_mode, "ShowBasic")
            if mode is not None:
                crosshair.SetCrosshairMode(mode)
            behavior = self._resolve_enum(crosshair, ws_cfg.crosshair_behavior, "OffsetJumpSlice")
            if behavior is not None:
                crosshair.SetCrosshairBehavior(behavior)
            thickness_name = ws_cfg.crosshair_thickness or "Fine"
            thickness_setter = getattr(crosshair, f"SetCrosshairTo{thickness_name}", None)
            if thickness_setter:
                thickness_setter()
            else:
                logger.warning(f"[GenericSpecimen] unknown crosshair thickness '{thickness_name}', skipping")

        layoutManager = slicer.app.layoutManager()

        if ws_cfg.ruler_type:
            for color in ("Red", "Yellow", "Green"):
                sliceWidget = layoutManager.sliceWidget(color)
                if sliceWidget is None:
                    continue
                sliceNode = sliceWidget.mrmlSliceNode()
                ruler_value = self._resolve_enum(sliceNode, "RulerType" + ws_cfg.ruler_type)
                if ruler_value is not None:
                    sliceNode.SetRulerType(ruler_value)

        if ws_cfg.orientation_marker_3d_type or ws_cfg.orientation_marker_3d_size:
            threeDWidget = layoutManager.threeDWidget(0)
            if threeDWidget:
                viewNode = threeDWidget.threeDView().mrmlViewNode()
                if viewNode:
                    self._apply_orientation_marker(viewNode, ws_cfg.orientation_marker_3d_type, ws_cfg.orientation_marker_3d_size)

        if ws_cfg.orientation_marker_2d_type or ws_cfg.orientation_marker_2d_size:
            for color in ("Red", "Yellow", "Green"):
                sliceWidget = layoutManager.sliceWidget(color)
                if sliceWidget is None:
                    continue
                sliceNode = sliceWidget.mrmlSliceNode()
                self._apply_orientation_marker(sliceNode, ws_cfg.orientation_marker_2d_type, ws_cfg.orientation_marker_2d_size)

        self._apply_view_convention(ws_cfg.view_convention)

    def _apply_view_convention(self, convention):
        """Flip the default Axial/Coronal slice-orientation presets between
        Slicer's own default ("radiological": patient's right shown on
        screen-left) and "neurological" (patient's right on screen-right) -
        the exact technique from Slicer's own documented script ("Change
        default slice view orientation", slicer.readthedocs.io/en/latest/
        developer_guide/script_repository.html). Sagittal is left untouched
        by design: a sagittal slice has no left/right ambiguity to flip.
        No-op if convention is unset."""
        if not convention:
            return
        axial = vtk.vtkMatrix3x3()      # identity - Slicer's own radiological default
        coronal = vtk.vtkMatrix3x3()    # identity unless flipped below
        if convention == "neurological":
            coronal.SetElement(1, 1, 0)
            coronal.SetElement(1, 2, -1)
            coronal.SetElement(2, 1, 1)
            coronal.SetElement(2, 2, 0)
        elif convention != "radiological":
            logger.warning(f"[GenericSpecimen] unknown view_convention '{convention}' (expected 'radiological' or 'neurological'), skipping")
            return

        sliceNodes = list(slicer.util.getNodesByClass("vtkMRMLSliceNode") or [])
        defaultNode = slicer.mrmlScene.GetDefaultNodeByClass("vtkMRMLSliceNode")
        if defaultNode:
            sliceNodes.append(defaultNode)
        for sliceNode in sliceNodes:
            orientationPresetName = sliceNode.GetOrientation()
            sliceNode.RemoveSliceOrientationPreset("Axial")
            sliceNode.AddSliceOrientationPreset("Axial", axial)
            sliceNode.RemoveSliceOrientationPreset("Coronal")
            sliceNode.AddSliceOrientationPreset("Coronal", coronal)
            sliceNode.SetOrientation(orientationPresetName)

    def _apply_orientation_marker(self, viewNode, type_name=None, size_name=None, default_type=None, default_size=None):
        """Set a view node's orientation-marker type/size - works for BOTH
        the 3D view and a slice (2D) view, since vtkMRMLSliceNode inherits
        this property from the same vtkMRMLAbstractViewNode base class the
        3D view node uses. type_name/size_name are SHORT names (e.g.
        "Axes"/"Large") - this method adds the OrientationMarkerType/
        OrientationMarkerSize prefix itself. default_type/default_size
        (full constant names, e.g. "OrientationMarkerTypeAxes") are used
        only when type_name/size_name are unset - only
        _start_volume_rendering() passes defaults (it always wants SOME 3D
        marker); everywhere else, unset just means leave alone."""
        full_type = ("OrientationMarkerType" + type_name) if type_name else default_type
        if full_type:
            v = self._resolve_enum(viewNode, full_type)
            if v is not None:
                viewNode.SetOrientationMarkerType(v)
        full_size = ("OrientationMarkerSize" + size_name) if size_name else default_size
        if full_size:
            v = self._resolve_enum(viewNode, full_size)
            if v is not None:
                viewNode.SetOrientationMarkerSize(v)

    def _apply_slice_rotation(self):
        """Apply cfg.slice_rotation's per-view (Red/Yellow/Green) in-plane rotation, if enabled. No-op for any view whose angle is left unset (None)."""
        rot_cfg = self.cfg.slice_rotation
        if not rot_cfg.enabled:
            return
        layoutManager = slicer.app.layoutManager()
        for color, angle_deg in (("Red", rot_cfg.red), ("Yellow", rot_cfg.yellow), ("Green", rot_cfg.green)):
            if angle_deg is None:
                continue
            sliceWidget = layoutManager.sliceWidget(color)
            if sliceWidget is None:
                continue
            self._rotate_slice_in_plane(sliceWidget.mrmlSliceNode(), angle_deg)

    def _rotate_slice_in_plane(self, sliceNode, angle_deg):
        """In-plane rotation of one slice view, around its own normal - the
        exact effect of the Reformat module's rotation slider. SliceToRAS's
        local Z axis IS the slice's normal, so a plain RotateZ on a
        vtkTransform seeded from the current matrix does it directly; no
        need to decompose into RAS-space axes."""
        sliceToRAS = sliceNode.GetSliceToRAS()
        transform = vtk.vtkTransform()
        transform.SetMatrix(sliceToRAS)
        transform.RotateZ(angle_deg)
        sliceNode.GetSliceToRAS().DeepCopy(transform.GetMatrix())
        sliceNode.UpdateMatrices()

    def _start_volume_rendering(self, vr_entries):
        """Create one volume rendering display node per enabled entry in vr_entries (each with its own preset + optional range shift), then set up the 3D view/camera/orientation-marker and active markups list once, after the whole batch - not per image."""
        logic = slicer.modules.volumerendering.logic()
        any_added = False

        for vr_entry in vr_entries:
            src_node = self.node_dict.get(vr_entry.image)
            if src_node is None:
                logger.warning(f"[GenericSpecimen] volume rendering source '{vr_entry.image}' not loaded, skipping")
                continue

            displayNode = logic.CreateVolumeRenderingDisplayNode()
            displayNode.UnRegister(logic)
            slicer.mrmlScene.AddNode(displayNode)
            src_node.AddAndObserveDisplayNodeID(displayNode.GetID())
            logic.UpdateDisplayNodeFromVolumeNode(displayNode, src_node)

            if vr_entry.preset:
                preset = logic.GetPresetByName(vr_entry.preset)
                if preset:
                    displayNode.GetVolumePropertyNode().Copy(preset)

            self._apply_volume_rendering_shift(displayNode, vr_entry)

            self.volume_rendering_nodes.append(displayNode)
            roiNode = displayNode.GetROINode()
            if not roiNode:
                displayNode.CreateDefaultROI()
                roiNode = displayNode.GetROINode()
            self.volume_rendering_roi.append(roiNode)
            any_added = True

        if not any_added:
            return

        slicer.app.processEvents()
        layoutManager = slicer.app.layoutManager()
        threeDWidget = layoutManager.threeDWidget(0)
        if threeDWidget:
            threeDView = threeDWidget.threeDView()
            viewNode = threeDView.mrmlViewNode()
            if viewNode:
                ws_cfg = self.cfg.workspace
                self._apply_orientation_marker(viewNode, ws_cfg.orientation_marker_3d_type, ws_cfg.orientation_marker_3d_size,
                                                default_type="OrientationMarkerTypeAxes", default_size="OrientationMarkerSizeLarge")
                viewNode.SetBoxVisible(False)
            threeDView.resetFocalPoint()
            threeDView.resetCamera()
        if self.markups_node is not None:
            selectionNode = slicer.app.applicationLogic().GetSelectionNode()
            selectionNode.SetReferenceActivePlaceNodeID(self.markups_node.GetID())
            slicer.modules.markups.logic().SetActiveListID(self.markups_node)

    def _apply_volume_rendering_shift(self, displayNode, vr_entry):
        """Shift a (usually preset-derived) volume rendering transfer function.
        Two independent mechanisms, checked in this order:

        1. `offset` - a fixed shift (every control point moves by the same
           amount, spacing/shape untouched) - the classic "Shift" slider
           behavior, matching the community 'shiftVolumeRendering' script
           referenced in TODO.md. Wins if both offset and window_level are set.
        2. `window_level` - a full rescale into an explicit [min, max] range
           (or a window/level pair converted to one), via
           _remap_transfer_function() - control-point remapping, NOT a
           mythical AdjustRange() method (see that method's docstring).

        No-op if neither is set. Wrapped defensively: if anything about this
        differs on your Slicer/VTK version, it prints a message and leaves
        the plain preset in place rather than failing the whole load.
        """
        image_name = vr_entry.image
        try:
            volPropNode = displayNode.GetVolumePropertyNode()
            try:
                opacity = volPropNode.GetScalarOpacity()
                color = volPropNode.GetColor()
            except AttributeError:
                vp = volPropNode.GetVolumeProperty()
                opacity = vp.GetScalarOpacity()
                color = vp.GetRGBTransferFunction()
        except Exception as e:
            logger.warning(f"[GenericSpecimen] could not access volume rendering transfer functions for '{image_name}': {e}")
            return

        if vr_entry.offset:
            try:
                self._offset_transfer_function(opacity, vr_entry.offset)
                self._offset_transfer_function(color, vr_entry.offset)
            except Exception as e:
                logger.warning(f"[GenericSpecimen] could not offset volume rendering range for '{image_name}': {e}")
            return

        window_level = vr_entry.window_level
        if window_level is None:
            return
        if window_level.min is not None and window_level.max is not None:
            new_range = [window_level.min, window_level.max]
        elif window_level.window is not None and window_level.level is not None:
            half = window_level.window / 2.0
            new_range = [window_level.level - half, window_level.level + half]
        else:
            return
        try:
            self._remap_transfer_function(opacity, new_range[0], new_range[1])
            self._remap_transfer_function(color, new_range[0], new_range[1])
        except Exception as e:
            logger.warning(f"[GenericSpecimen] could not shift volume rendering range for '{image_name}': {e}")

    def _offset_transfer_function(self, func, offset):
        """Shift every control point's x value by a fixed amount, leaving
        spacing/shape/y-values untouched - the exact GetNodeValue() ->
        modify x -> RemoveAllPoints()+AddPoint()/AddRGBPoint() technique
        from the community 'shiftVolumeRendering' script (see
        _remap_transfer_function() below for the full-rescale variant and
        why AdjustRange() is not a real method to reach for here)."""
        n = func.GetSize()
        if n == 0 or not offset:
            return
        is_color = hasattr(func, "AddRGBPoint")
        width = 6 if is_color else 4
        points = []
        for i in range(n):
            val = [0.0] * width
            func.GetNodeValue(i, val)
            points.append(val)
        for val in points:
            val[0] += offset
        func.RemoveAllPoints()
        for val in points:
            if is_color:
                func.AddRGBPoint(*val)
            else:
                func.AddPoint(*val)
        func.Modified()

    def _remap_transfer_function(self, func, new_min, new_max):
        """Linearly remap an existing vtkPiecewiseFunction (opacity) or
        vtkColorTransferFunction (color)'s control points from their current
        x-range into [new_min, new_max], keeping their relative shape/values.

        Neither class has an AdjustRange() method (a plausible-sounding but
        nonexistent API) - the actual, community-verified way to do this is
        reading each control point with GetNodeValue(), rewriting its x
        value, then replacing all points via RemoveAllPoints()+AddPoint()/
        AddRGBPoint(). See e.g. the widely-referenced "shiftVolumeRendering"
        Slicer script (mikebind/88e19559c6b1c104d71f75083bcffb7c), which uses
        this same GetNodeValue/RemoveAllPoints/AddPoint pattern to move a VR
        preset's transfer function (there for a fixed offset; here for an
        arbitrary target range).
        """
        n = func.GetSize()
        if n == 0:
            return
        is_color = hasattr(func, "AddRGBPoint")
        width = 6 if is_color else 4   # color node: [x,r,g,b,midpoint,sharpness]; opacity node: [x,y,midpoint,sharpness]
        points = []
        for i in range(n):
            val = [0.0] * width
            func.GetNodeValue(i, val)
            points.append(val)
        old_min, old_max = points[0][0], points[-1][0]
        old_span = old_max - old_min
        new_span = new_max - new_min
        for val in points:
            frac = (val[0] - old_min) / old_span if old_span else 0.0
            val[0] = new_min + frac * new_span
        func.RemoveAllPoints()
        for val in points:
            if is_color:
                func.AddRGBPoint(*val)
            else:
                func.AddPoint(*val)
        func.Modified()


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
            storage = node.CreateDefaultStorageNode()
            storage.SetHideFromEditors(True)
            storage.SetFileName(path)
            storage.WriteData(node)
            if slicer.mrmlScene.IsNodePresent(storage):
                slicer.mrmlScene.RemoveNode(storage)
            save_rows.append((item, status, path))

        logger.info(f"[GenericSpecimen] saved {self.label}: {len(save_rows)} item(s) -> {self.out_dir}")
        self._print_table(f"saved {self.label} -> {self.out_dir}", ["item", "status", "path"], save_rows)

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


# ---------------------------------------------------------------------------
# GenericSpecimenManagerLogic
# ---------------------------------------------------------------------------

class GenericSpecimenManagerLogic(ScriptedLoadableModuleLogic):

    """Owns the parsed StudyConfig, the database/preseg tables, and the dict of all specimens for the current study. No GUI code here - the Widget class below is the only thing that talks to Qt."""
    def __init__(self):
        """Holds the parsed StudyConfig plus the live database/preseg table nodes and the in-memory specimen dict - one instance per module widget."""
        ScriptedLoadableModuleLogic.__init__(self)
        self.cfg: StudyConfig = None
        self.study_dir = None
        self.dbTable = None
        self.presegTable = None
        self.dbDictList = []
        self.presegDictList = []
        self.dbColumnNames = []
        self.specimens = {}
        self.active_specimen = None
        self.default_config_path = None

    def load_config(self, config_path):
        """Parse config_path into self.cfg (a StudyConfig) and remember its study_dir."""
        self.cfg = load_config(config_path)
        self.study_dir = self.cfg.study_dir
        return self.cfg

    def _abs_path(self, rel):
        """Resolve rel against study_dir if it isn't already absolute."""
        if not rel:
            return rel
        return rel if os.path.isabs(rel) else os.path.join(self.study_dir, rel)

    def setDefaultParameters(self, parameterNode):
        """Called by Slicer when a parameter node is first attached to this module: seed ConfigPath from default_config_path (set by the wrapper module) or an existing saved parameter, load that config if it exists, and pre-fill the Database/Preseg CSV path parameters from it."""
        if not parameterNode.GetParameter("ConfigPath"):
            parameterNode.SetParameter("ConfigPath", self.default_config_path or "")
        if self.cfg is None:
            config_path = parameterNode.GetParameter("ConfigPath") or self.default_config_path
            if config_path and os.path.exists(config_path):
                try:
                    self.load_config(config_path)
                except Exception as e:
                    logger.warning(f"[GenericSpecimenManager] failed to load config '{config_path}': {e}")
        if self.cfg:
            if not parameterNode.GetParameter("DatabaseCSVPath"):
                parameterNode.SetParameter("DatabaseCSVPath", self._abs_path(self.cfg.database_csv_path))
            if not parameterNode.GetParameter("PresegCSVPath"):
                parameterNode.SetParameter("PresegCSVPath", self._abs_path(self.cfg.preseg_csv_path))

    def get_node_if_loaded(self, file_path):
        """Return the name of an already-loaded scene node backed by file_path, or '' if none - lets Initialize Study reuse an already-open table instead of reloading it from disk (and losing any in-scene edits)."""
        for n in slicer.mrmlScene.GetNodes():
            try:
                if n.GetStorageNode().GetFileName() == file_path:
                    return n.GetName()
            except Exception:
                continue
        return ""

    def initializeStudy(self):
        """Load (or reuse) the database and preseg tables, intersect their key-column values, and build one GenericSpecimen per matching row. Then apply segment_editor config once (see _configure_segment_editor_defaults)."""
        if self.cfg is None:
            raise RuntimeError("No config loaded. Select a config.json first.")
        db_path = self.getParameterNode().GetParameter("DatabaseCSVPath")
        preseg_path = self.getParameterNode().GetParameter("PresegCSVPath")

        try:
            node = slicer.util.getNode(self.get_node_if_loaded(db_path))
            self.dbTable = node
        except slicer.util.MRMLNodeNotFoundException:
            self.dbTable = slicer.util.loadTable(db_path)
        try:
            node = slicer.util.getNode(self.get_node_if_loaded(preseg_path))
            self.presegTable = node
        except slicer.util.MRMLNodeNotFoundException:
            self.presegTable = slicer.util.loadTable(preseg_path)

        self.dbDictList, self.dbColumnNames = self._table_to_dicts(self.dbTable, return_columns=True)
        self.presegDictList = self._table_to_dicts(self.presegTable)

        key_columns = self.cfg.key_columns
        status_col = self.cfg.status_column
        db_keys = [tuple(row.get(c, "") for c in key_columns) for row in self.dbDictList]
        preseg_keys = [tuple(row.get(c, "") for c in key_columns) for row in self.presegDictList]
        common_keys = sorted(set(db_keys).intersection(set(preseg_keys)))

        self.specimens = {}
        for key in common_keys:
            db_idx = db_keys.index(key)
            db_row = self.dbDictList[db_idx]
            preseg_row = next((r for r in self.presegDictList if tuple(r.get(c, "") for c in key_columns) == key), {})
            specimen = GenericSpecimen(key, self.cfg, db_row, preseg_row, self.study_dir)
            specimen.row_index = db_idx
            specimen.status_col_index = self.dbColumnNames.index(status_col) if status_col in self.dbColumnNames else None
            self.specimens[key] = specimen

        logger.info(f"[GenericSpecimenManager] initialized {len(self.specimens)} specimens")
        self._configure_segment_editor_defaults()

    def _configure_segment_editor_defaults(self):
        """Apply segment_editor config ONCE, at study init, instead of on every
        specimen load. Brush/overwrite settings are study-level preferences,
        not per-specimen state, so there's no need to re-touch them on every
        load() - and doing it here avoids the whole class of timing/singleton
        problems from poking a live, possibly-not-yet-constructed Segment
        Editor widget mid specimen-load.

        IMPORTANT: BrushSphere / BrushAbsoluteDiameter / BrushRelativeDiameter /
        BrushDiameterIsRelative are COMMON parameters shared by Paint/Erase -
        they are stored as BARE attribute keys on vtkMRMLSegmentEditorNode,
        with NO effect-name prefix (confirmed against a real node's printed
        Attributes on the Slicer forum). Only EFFECT-SPECIFIC parameters use
        the "EffectName.ParamName" form (e.g. "Paint.ColorSmudge"). Earlier
        versions of this code prefixed brush keys with "Paint," / "Paint." -
        that attribute never existed, so nothing ever applied.

        Two scenarios, both handled:
          1. Fresh scene, Segment Editor never opened yet: configure the
             DEFAULT/template node (AddDefaultNode) - any node Slicer creates
             later when the module first opens inherits these values via
             its normal node-Copy-from-default mechanism.
          2. A live vtkMRMLSegmentEditorNode already exists (Segment Editor
             was already opened this session): default-node changes don't
             retroactively affect it, so patch that instance directly too.

        active_effect is intentionally NEVER set on the default/template node
        - only on an already-in-use existing node (one with a segmentation
        attached). Setting it on a bare template makes the real widget try to
        activate that effect the instant it clones the template, before any
        segmentation/volume exists - several effects crash the whole app
        natively (no Python traceback) when that context is missing.
        """
        se_cfg = self.cfg.segment_editor
        if not se_cfg.is_configured():
            return

        overwrite_map = {
            "none": slicer.vtkMRMLSegmentEditorNode.OverwriteNone,
            "all_segments": slicer.vtkMRMLSegmentEditorNode.OverwriteAllSegments,
            "visible_segments": slicer.vtkMRMLSegmentEditorNode.OverwriteVisibleSegments,
        }
        overwrite_value = overwrite_map.get(se_cfg.overwrite_mode or "none", slicer.vtkMRMLSegmentEditorNode.OverwriteNone)

        attrs = {}
        brush_cfg = se_cfg.brush
        if brush_cfg:
            if brush_cfg.shape == "sphere":
                attrs["BrushSphere"] = "1"
            elif brush_cfg.shape == "circle":
                attrs["BrushSphere"] = "0"
            if brush_cfg.diameter_mm is not None:
                if brush_cfg.relative:
                    attrs["BrushDiameterIsRelative"] = "1"
                    attrs["BrushRelativeDiameter"] = str(brush_cfg.diameter_mm)
                else:
                    attrs["BrushDiameterIsRelative"] = "0"
                    attrs["BrushAbsoluteDiameter"] = str(brush_cfg.diameter_mm)
        attrs.update({k: str(v) for k, v in se_cfg.attributes.items()})

        def _apply_common(node):
            """Safe on ANY node, including a bare template with no context:
            overwrite mode and plain data attributes never trigger live
            widget/effect behaviour by themselves."""
            node.SetOverwriteMode(overwrite_value)
            for k, v in attrs.items():
                node.SetAttribute(k, v)

        def _has_segmentation(node):
            """True if this segment editor node already has a real segmentation attached (i.e. it's genuinely in use, not a bare template) - see the caller for why that matters."""
            try:
                return node.GetSegmentationNode() is not None
            except Exception:
                return False

        default_node = slicer.mrmlScene.GetDefaultNodeByClass("vtkMRMLSegmentEditorNode")
        if default_node is None:
            default_node = slicer.vtkMRMLSegmentEditorNode()
            slicer.mrmlScene.AddDefaultNode(default_node)
        # NEVER SetActiveEffectName on this node: it's a template with no
        # segmentation/source-volume attached. Forcing an effect active on it
        # makes the real Segment Editor widget try to activate that effect the
        # instant it clones the template - before anything is selected - and
        # several effects crash natively (whole-app crash, no traceback) when
        # that context is missing. This is exactly what regressed here.
        _apply_common(default_node)

        existing_node = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLSegmentEditorNode")
        if existing_node is not None and existing_node is not default_node:
            _apply_common(existing_node)
            if se_cfg.active_effect and _has_segmentation(existing_node):
                # Only safe here because this node is already genuinely in use
                # (has a segmentation attached) - not a bare/template node.
                existing_node.SetActiveEffectName(se_cfg.active_effect)

        logger.info(f"[GenericSpecimenManager] segment editor defaults applied: overwrite={overwrite_value}, attrs={attrs}, "
              f"active_effect_requested={se_cfg.active_effect}, patched_existing_node={existing_node is not None}")

    def group_by_key_values(self):
        """Unique, sorted values of cfg.group_by_key.column across all specimens."""
        col = self.cfg.group_by_key.column
        if not col:
            return []
        return sorted({s.db_info.get(col, "") for s in self.specimens.values()} - {""})

    def _table_to_dicts(self, table, return_columns=False):
        """Convert a loaded vtkMRMLTableNode into a list of {column_name: value} dicts (optionally also returning the raw, ordered column name list, needed for name-based cell write-back)."""
        dict_list = []
        _t = table.GetTable()
        ncol, nrow = _t.GetNumberOfColumns(), _t.GetNumberOfRows()
        colnames = [_t.GetColumnName(j) for j in range(ncol)]
        for i in range(nrow):
            row = _t.GetRow(i)
            dict_list.append({colnames[j]: row.GetValue(j).ToString() for j in range(ncol)})
        return (dict_list, colnames) if return_columns else dict_list

    def confirm(self, text):
        """Simple Yes/No modal dialog. Returns True iff the user picked Yes."""
        c = ctk.ctkMessageBox()
        c.setIcon(qt.QMessageBox.Information)
        c.setText(text)
        c.setStandardButtons(qt.QMessageBox.Yes | qt.QMessageBox.No)
        c.setDefaultButton(qt.QMessageBox.Ok)
        return c.exec_() == qt.QMessageBox.Yes

    def info(self, text):
        """Simple OK-only modal information dialog."""
        c = ctk.ctkMessageBox()
        c.setIcon(qt.QMessageBox.Information)
        c.setText(text)
        c.setStandardButtons(qt.QMessageBox.Ok)
        c.setDefaultButton(qt.QMessageBox.Ok)
        c.exec_()

    def show_key_value_dialog(self, title, rows):
        """Show a small, nicely-formatted OK-only dialog: a grid of bold-label/value rows, built from real widgets instead of one plain QMessageBox text blob - used for the Save confirmations, where a flat wall of text was hard to scan. `rows` is a list of (label, value) pairs."""
        dlg = qt.QDialog(slicer.util.mainWindow())
        dlg.setWindowTitle(title)
        layout = qt.QVBoxLayout(dlg)

        titleLabel = qt.QLabel(f"<h3>{title}</h3>")
        layout.addWidget(titleLabel)

        grid = qt.QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(16)
        for i, (label, value) in enumerate(rows):
            lbl = qt.QLabel(f"<b>{label}</b>")
            val = qt.QLabel(str(value))
            val.setWordWrap(True)
            val.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
            grid.addWidget(lbl, i, 0, qt.Qt.AlignTop)
            grid.addWidget(val, i, 1)
        layout.addLayout(grid)

        btnRow = qt.QHBoxLayout()
        btnRow.addStretch(1)
        okBtn = qt.QPushButton("OK")
        okBtn.setDefault(True)
        okBtn.connect('clicked(bool)', lambda checked=False: dlg.accept())
        btnRow.addWidget(okBtn)
        layout.addLayout(btnRow)

        dlg.exec_()

    def load_specimen(self, key):
        """Load the specimen for `key` and make it the active one - refuses (with an info popup) if a specimen is already active."""
        target = self.specimens.get(key)
        if isinstance(self.active_specimen, GenericSpecimen):
            self.info("A specimen has already been loaded.")
            return False
        if target is None:
            raise ValueError(f"Specimen {key} not initialized")
        target.load()
        self.active_specimen = target
        return True

    def load_specimen_for_batch(self, key, image_names=None):
        """Lean equivalent of load_specimen() for headless batch operations
        (BatchProcessor) - calls GenericSpecimen.load_for_batch() instead
        of the full load(), so workspace/volume-rendering/Segment-Editor
        setup is skipped entirely. Same active-specimen bookkeeping/guard
        as load_specimen()."""
        target = self.specimens.get(key)
        if isinstance(self.active_specimen, GenericSpecimen):
            self.info("A specimen has already been loaded.")
            return False
        if target is None:
            raise ValueError(f"Specimen {key} not initialized")
        target.load_for_batch(image_names=image_names)
        self.active_specimen = target
        return True

    def close_active_specimen(self, no_question=False):
        """Close the active specimen, asking for confirmation first unless no_question=True (used for scene-close/re-init flows where the caller already confirmed)."""
        if no_question:
            if self.active_specimen is not None:
                self.active_specimen.close()
                self.active_specimen = None
            return
        if not isinstance(self.active_specimen, GenericSpecimen):
            self.info("There is no active specimen to close.")
            return
        if not self.confirm("Do you really want to close the active specimen?"):
            return
        self.active_specimen.close()
        self.active_specimen = None

    def save_active_specimen(self, inform_user=True):
        """Save the active specimen's writeable nodes to disk; optionally show a confirmation popup."""
        if not isinstance(self.active_specimen, GenericSpecimen):
            self.info("There is no active specimen to save.")
            return
        sp = self.active_specimen
        sp.save()
        if inform_user:
            rows = list(zip(self.cfg.key_columns, sp.key_values))
            rows.append(("folder", sp.out_dir))
            self.show_key_value_dialog("Specimen saved", rows)

    def ensure_db_column(self, name):
        """Add `name` as a new, empty column to the live database table if it isn't there yet -
        used when a Table/Factor column is configured for a name that doesn't actually exist in
        database.csv, so editing it in the GUI creates the column instead of refusing to write
        back. Returns True once the column exists (already did, or was just added)."""
        if name in self.dbColumnNames:
            return True
        if self.dbTable is None:
            return False
        col = vtk.vtkStringArray()
        col.SetName(name)
        col.SetNumberOfValues(self.dbTable.GetNumberOfRows())
        for i in range(self.dbTable.GetNumberOfRows()):
            col.SetValue(i, "")
        self.dbTable.AddColumn(col)
        self.dbColumnNames.append(name)
        logger.info(f"[GenericSpecimenManager] added new database.csv column '{name}'")
        return True

    def set_specimen_status(self, specimen, status, only_raise=False):
        """Write `status` (a SpecimenStatus) into the specimen's status column, in the live database table AND its cached db_info - creating the column first if it's missing. With only_raise=True a specimen already at or above `status` is left alone (automatic promotions never downgrade a manual to-review/finished). Returns True if the value actually changed."""
        if specimen is None or specimen.row_index is None:
            return False
        status_col = self.cfg.status_column
        if not self.ensure_db_column(status_col):
            return False
        current = specimen.status
        if current == status or (only_raise and current >= status):
            return False
        real_col = self.dbColumnNames.index(status_col)
        self.dbTable.SetCellText(specimen.row_index, real_col, str(int(status)))
        written = self.dbTable.GetCellText(specimen.row_index, real_col)
        if written != str(int(status)):
            logger.warning(f"[GenericSpecimenManager] status write to '{status_col}' did not stick (read back '{written}') - is the column numeric?")
        specimen.db_info[status_col] = str(int(status))
        specimen.status_col_index = real_col
        return True

    def save_db(self, inform_user=True):
        """Write the live database table back to its CSV file; optionally show a confirmation popup. Always logged at DEBUG level (not INFO), since this can fire silently and often - e.g. Auto-save database after every table edit."""
        db_path = self.getParameterNode().GetParameter("DatabaseCSVPath")
        storage = self.dbTable.CreateDefaultStorageNode()
        storage.SetHideFromEditors(True)
        storage.SetFileName(db_path)
        storage.WriteData(self.dbTable)
        if slicer.mrmlScene.IsNodePresent(storage):
            slicer.mrmlScene.RemoveNode(storage)
        logger.debug(f"[GenericSpecimenManager] saved database CSV -> {db_path}")
        if inform_user:
            self.show_key_value_dialog("Database saved", [("path", db_path)])

    @property
    def hasActiveSpecimen(self):
        """True if a specimen is currently loaded."""
        return isinstance(self.active_specimen, GenericSpecimen)


# ---------------------------------------------------------------------------
# GenericSpecimenManagerWidgetBase
# ---------------------------------------------------------------------------

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


class GenericSpecimenManagerWidgetBase(ScriptedLoadableModuleWidget, VTKObservationMixin):

    """The actual module GUI: config/CSV path pickers, the specimen table, group-select combo, and the load/save/close/batch-export buttons. Subclassed per named wrapper module (CONFIG_PATH set) or used directly for the general-purpose config-picker module (CONFIG_PATH=None)."""
    CONFIG_PATH = None

    # Actual on/off values live in Resources/Definitions.py (one place for
    # every hardcoded toggle in this module) - kept as class attributes here
    # too, so a subclass could still override just its own instance if ever
    # needed, without touching the shared default.
    HIDE_RELOAD_AND_TEST = _DEFINITIONS_HIDE_RELOAD_AND_TEST
    HIDE_HELP_AND_ACKNOWLEDGEMENT = _DEFINITIONS_HIDE_HELP_AND_ACKNOWLEDGEMENT
    UI_RESOURCE = "UI/GenericSpecimenManager.ui"

    import os as _os
    from pathlib import Path as _Path
    BASE_DIR = _Path(_os.path.abspath(__file__)).resolve().parent
    DEFAULT_CONFIG_FOLDER = str(BASE_DIR.parent / "Config")

    def __init__(self, parent=None):
        """Per-instance GUI state: the Logic object (created in setup()), the observed parameter node, and small bits of transient UI state (selected specimen key, current batch filter, a re-entrancy guard for table edits)."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False
        self.tbl_selected_key = None
        self.table_lock = False
        self._displayed_keys = []
        self._group_filter = None
        self._status_filter = None               # set of SpecimenStatus ticked in the status filter, None = all (no filtering)
        self._annotationActors = []              # (view, renderer, vtkTextActor) of the specimen annotation, if shown
        self._studyInitialized = False           # True only after a fully successful Initialize Study
        self._active_specimen_observed = None    # the GenericSpecimen currently wired to _onActiveSpecimenNodeModified, if any
        self._displacedSaveActions = []          # (QAction, QKeySequence) of Slicer's own Ctrl+S actions while this module owns the shortcut

    def setup(self):
        """Slicer calls this once when the module widget is first shown: load the .ui, wire every button/field, hide the config picker if CONFIG_PATH locks this wrapper to one study, and initialize the parameter node."""
        ScriptedLoadableModuleWidget.setup(self)
        uiWidget = slicer.util.loadUI(self.resourcePath(self.UI_RESOURCE))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        self._uiWidget = uiWidget
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.logic = GenericSpecimenManagerLogic()
        self.logic.default_config_path = self.CONFIG_PATH

        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene, slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        self.ui.tbConfigPath.textChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.tbDBPath.textChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.tbPresegPath.textChanged.connect(self.updateParameterNodeFromGUI)
        self.ui.tbConfigPath.textChanged.connect(lambda: self._validatePathField(self.ui.tbConfigPath))
        self.ui.tbDBPath.textChanged.connect(lambda: self._validatePathField(self.ui.tbDBPath))
        self.ui.tbPresegPath.textChanged.connect(lambda: self._validatePathField(self.ui.tbPresegPath))
        self.ui.tblSpecimens.selectionModel().selectionChanged.connect(self.selected_specimen_changed)
        self.ui.tblSpecimens.itemChanged.connect(self.specimen_tbl_changed)

        self.ui.btnSelectConfig.connect('clicked(bool)', self.onBtnSelectConfig)
        self.ui.btnInitializeStudy.connect('clicked(bool)', self.onBtnInitializeStudy)
        self.ui.btnSelectDB.connect('clicked(bool)', self.onBtnSelectDB)
        self.ui.btnSelectPreseg.connect('clicked(bool)', self.onBtnSelectPreseg)
        self.ui.btnBatchExport.connect('clicked(bool)', self.onBtnBatchExport)
        self.ui.btnConfigEditor.connect('clicked(bool)', self.onBtnConfigEditor)
        # Ctrl+S runs this module's save while a specimen is loaded (enabled only then - see
        # _syncSaveShortcut). It collides with Slicer's own Save scene shortcut, so both the
        # normal and the 'ambiguous' activation are handled.
        self._saveShortcut = qt.QShortcut(qt.QKeySequence("Ctrl+S"), slicer.util.mainWindow())
        self._saveShortcut.setContext(qt.Qt.ApplicationShortcut)
        self._saveShortcut.enabled = False
        self._saveShortcut.connect('activated()', self._onSaveShortcut)
        self._saveShortcut.connect('activatedAmbiguously()', self._onSaveShortcut)
        self.ui.btnModuleHelp.connect('clicked(bool)', lambda checked=False: show_cheatsheet_dialog(
            slicer.util.mainWindow(), "Generic Specimen Manager - Cheat Sheet", "module_help_cheatsheet.html", MODULE_HELP_SECTIONS))
        self.ui.btnLoadSelected.connect('clicked(bool)', self.onBtnLoadSelected)
        self.ui.btnSaveActiveSpecimen.connect('clicked(bool)', self.onBtnSaveActiveSpecimen)
        self.ui.btnCloseActiveSpecimen.connect('clicked(bool)', self.onBtnCloseActiveSpecimen)
        self.ui.btnResetSelectedSpecimen.connect('clicked(bool)', self.onBtnResetSelectedSpecimen)
        self.ui.btnSaveDB.connect('clicked(bool)', self.onBtnSaveDB)
        self.ui.studySettingsCollapsibleButton.connect('toggled(bool)', lambda checked=False: qt.QTimer.singleShot(0, self._fitSpecimenTableHeight))
        self.ui.helpCollapsibleButton.connect('toggled(bool)', lambda checked=False: qt.QTimer.singleShot(0, self._fitSpecimenTableHeight))
        self.ui.wOps.connect('toggled(bool)', lambda checked=False: qt.QTimer.singleShot(0, self._fitSpecimenTableHeight))
        self.ui.cmbGroupByKey.currentTextChanged.connect(self.onGroupByKeyChanged)
        self.ui.wGroupByKey.visible = False
        for st in SpecimenStatus:
            self.ui.cmbStatusFilter.addItem(SPECIMEN_STATUS_LABELS[st])
        self._checkAllStatusFilter()
        self.ui.cmbStatusFilter.checkedIndexesChanged.connect(self.onStatusFilterChanged)

        if self.CONFIG_PATH:
            self.ui.lblConfig.visible = False
            self.ui.btnSelectConfig.visible = False
            self.ui.tbConfigPath.visible = False

        # ScriptedLoadableModuleWidget.setup() above only builds this when
        # Slicer's global Edit > Application Settings > Developer > "Enable
        # developer mode" is on. Gated by HIDE_RELOAD_AND_TEST (class
        # attribute above) - flip that to False to keep showing it.
        if self.HIDE_RELOAD_AND_TEST and hasattr(self, "reloadCollapsibleButton"):
            self.reloadCollapsibleButton.hide()

        self.initializeParameterNode()
        self._updatePostInitButtonStates()
        self._fitSpecimenTableHeight()

    def _clearSpecimenAnnotation(self):
        """Remove the yellow specimen-data text actors from every view."""
        for view, renderer, actor in self._annotationActors:
            try:
                renderer.RemoveViewProp(actor)
                view.scheduleRender()
            except Exception:
                pass
        self._annotationActors = []

    def _refreshSpecimenAnnotation(self):
        """(Re)draw the active specimen's database row as yellow text, top-left, in the Red/
        Yellow/Green and 3D views - only if workspace.specimen_annotation is on and a specimen is
        loaded (otherwise just clears). Layout: the ID (key columns joined with '-'), a rule, one
        'column: value' line per remaining table_columns entry (status column excluded), a rule, then
        the status line.
        Own vtkTextActor (not the shared corner annotation) so DataProbe can't overwrite it."""
        self._clearSpecimenAnnotation()
        cfg = self.logic.cfg if self.logic else None
        if cfg is None or not cfg.workspace.specimen_annotation or not self.logic.hasActiveSpecimen:
            return
        sp = self.logic.active_specimen
        id_line = "-".join(str(v) for v in sp.key_values)
        kv_lines = [f"{col}: {sp.db_info.get(col, '')}" for col in cfg.table_columns
                    if col not in cfg.key_columns and col != cfg.status_column]
        status_line = SPECIMEN_STATUS_LABELS[sp.status]
        width = max(len(l) for l in [id_line, status_line] + kv_lines)
        rule = "-" * width
        lines = [id_line, rule] + (kv_lines + [rule] if kv_lines else []) + [status_line]
        text = "\n".join(lines)
        try:
            lm = slicer.app.layoutManager()
            views = [lm.sliceWidget(n).sliceView() for n in lm.sliceViewNames()]
            views.append(lm.threeDWidget(0).threeDView())
            for view in views:
                renderer = view.renderWindow().GetRenderers().GetFirstRenderer()
                actor = vtk.vtkTextActor()
                actor.SetInput(text)
                prop = actor.GetTextProperty()
                prop.SetColor(*SPECIMEN_ANNOTATION_COLOR)
                prop.SetFontSize(SPECIMEN_ANNOTATION_FONT_SIZE)
                prop.SetBackgroundColor(*SPECIMEN_ANNOTATION_BG_COLOR)
                prop.SetBackgroundOpacity(SPECIMEN_ANNOTATION_BG_OPACITY)
                if hasattr(prop, "SetBackgroundPadding"):   # VTK 9+
                    prop.SetBackgroundPadding(SPECIMEN_ANNOTATION_BG_PADDING)
                prop.SetVerticalJustificationToTop()
                actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
                actor.SetPosition(0.01, 0.98)
                renderer.AddViewProp(actor)
                self._annotationActors.append((view, renderer, actor))
                view.scheduleRender()
        except Exception as e:
            logger.warning(f"[GenericSpecimenManager] could not draw specimen annotation: {e}")

    def _updatePostInitButtonStates(self):
        """Enable/disable/show the controls that only make sense once a study has actually been
        initialized: Load selected specimen, Save progress, Close active specimen, Reset and the
        Status filter start disabled, and Save database CSV / Batch export start hidden (each
        shown only if the config wants it) - so a clean/blank module can't be clicked into a
        confusing failure before Initialize Study has run. The Initialize Study button itself is
        pastel green until a study is initialized. Called after setup(), after a successful
        Initialize Study, and after every load/save/close of the active specimen."""
        ready = self.logic is not None and self.logic.cfg is not None and self._studyInitialized
        active = ready and self.logic.hasActiveSpecimen
        # Initialize Study nudges (pastel green) until a study is initialized; then the buttons
        # that need one appear below it - Save database CSV unless the config auto-saves it,
        # Batch export only if the config enables it.
        self.ui.btnInitializeStudy.setStyleSheet("" if ready else "QPushButton { background-color: #cdeccd; color: black; }")
        self.ui.btnSaveDB.visible = bool(ready and not self.logic.cfg.auto_save_database)
        self.ui.btnBatchExport.visible = bool(ready and self.logic.cfg.batch_export.enabled)
        self.ui.cmbStatusFilter.enabled = ready
        self.ui.btnLoadSelected.enabled = ready and not active
        self.ui.btnSaveActiveSpecimen.enabled = active
        self.ui.btnCloseActiveSpecimen.enabled = active
        self.ui.btnResetSelectedSpecimen.enabled = ready
        self._syncSaveShortcut()

    def cleanup(self):
        """Standard ScriptedLoadableModuleWidget hook: Slicer calls this when the widget is being destroyed."""
        self.removeObservers()
        shortcut = getattr(self, "_saveShortcut", None)
        if shortcut is not None:
            shortcut.enabled = False
            shortcut.deleteLater()
            self._saveShortcut = None
        self._restoreSlicerSaveShortcut()

    def enter(self):
        """Standard hook: Slicer calls this every time the user switches into this module."""
        self.initializeParameterNode()
        self._installScrollAreaWatch()
        if self.HIDE_HELP_AND_ACKNOWLEDGEMENT:
            self._setHelpSectionVisible(False)

    def exit(self):
        """Standard hook: Slicer calls this every time the user switches away from this module."""
        self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        if self.HIDE_HELP_AND_ACKNOWLEDGEMENT:
            self._setHelpSectionVisible(True)

    def _setHelpSectionVisible(self, visible):
        """Show/hide the module panel's Help & Acknowledgement section via slicer.util.setModuleHelpSectionVisible() - a module-panel-wide (not per-module) setting, hence toggled in enter()/exit() rather than once in setup(). Defensively wrapped: an older Slicer build without this helper just leaves the section as-is instead of raising."""
        try:
            slicer.util.setModuleHelpSectionVisible(visible)
        except Exception as e:
            logger.warning(f"[GenericSpecimenManager] could not toggle the Help section (older Slicer build?): {e}")

    def onSceneStartClose(self, caller, event):
        """Close the active specimen (without confirmation - the scene is going away regardless) before the MRML scene is actually torn down."""
        if self.logic and self.logic.hasActiveSpecimen:
            self.logic.close_active_specimen(no_question=True)
            self._detach_active_specimen_observers()
            self._clearSpecimenAnnotation()
            self._syncSaveShortcut()
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """Re-attach a fresh parameter node once a new (empty) scene is ready, if this module is currently the one shown."""
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        """Fetch (or create) this module's parameter node and hand it to setParameterNode()."""
        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode):
        """Swap the observed parameter node, re-wiring the Modified-event observer so the GUI fields stay in sync whenever the node changes (including from outside this widget, e.g. scene load)."""
        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)
        if self._parameterNode is not None:
            self.removeObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """Push the parameter node's saved values into the path text fields (falling back to the bundled Config/ folder for a first-run/empty ConfigPath), then live-validate each field's existence."""
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        self._updatingGUIFromParameterNode = True
        if os.path.exists(self.DEFAULT_CONFIG_FOLDER) and str(self._parameterNode.GetParameter("ConfigPath")) == "":
            self.ui.tbConfigPath.text = str(self.DEFAULT_CONFIG_FOLDER)
        else:
            self.ui.tbConfigPath.text = str(self._parameterNode.GetParameter("ConfigPath"))
        self.ui.tbDBPath.text = str(self._parameterNode.GetParameter("DatabaseCSVPath"))
        self.ui.tbPresegPath.text = str(self._parameterNode.GetParameter("PresegCSVPath"))
        for edit in (self.ui.tbConfigPath, self.ui.tbDBPath, self.ui.tbPresegPath):
            self._validatePathField(edit)
        self._updatingGUIFromParameterNode = False

    def _validatePathField(self, edit):
        """Live, passive feedback (border color + tooltip) on whether a path
        field currently points at a real file - instead of only finding out
        via a popup error after clicking Initialize Study."""
        path = str(edit.text).strip()
        if not path:
            edit.setStyleSheet("")
            edit.setToolTip("")
        elif not os.path.exists(path):
            edit.setStyleSheet("border: 1px solid #cc3333; background-color: #fff0f0;")
            edit.setToolTip("Not found: " + path)
        elif os.path.isdir(path):
            edit.setStyleSheet("border: 1px solid #cc8800; background-color: #fff8e8;")
            edit.setToolTip("This is a folder, not a file: " + path)
        else:
            edit.setStyleSheet("border: 1px solid #33aa33;")
            edit.setToolTip(path)

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """Push the path text fields' current values back into the parameter node, so they persist with the scene."""
        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return
        wasModified = self._parameterNode.StartModify()
        self._parameterNode.SetParameter("ConfigPath", str(self.ui.tbConfigPath.text))
        self._parameterNode.SetParameter("DatabaseCSVPath", str(self.ui.tbDBPath.text))
        self._parameterNode.SetParameter("PresegCSVPath", str(self.ui.tbPresegPath.text))
        self._parameterNode.EndModify(wasModified)

    # ---- GUI actions ----

    def onBtnSelectConfig(self):
        """Browse for a config.json, load it immediately, and pre-fill the Database/Preseg CSV path fields from it."""
        fname = QFileDialog.getOpenFileName(None, 'Open config', str(self.ui.tbConfigPath.text), "JSON files (*.json)")
        if not fname:
            return
        self._loadConfigIntoScene(fname)

    def _loadConfigIntoScene(self, path):
        """Load `path` into this module's active Logic/parameter node and pre-fill the Database/Preseg CSV path fields from it - exactly what onBtnSelectConfig does after a browse, but reusable with an already-known path (e.g. the Config Editor's "reload after save" prompt, which calls this instead of making the user browse again)."""
        self._parameterNode.SetParameter("ConfigPath", path)
        try:
            self.logic.load_config(path)
            self._parameterNode.SetParameter("DatabaseCSVPath", self.logic._abs_path(self.logic.cfg.database_csv_path))
            self._parameterNode.SetParameter("PresegCSVPath", self.logic._abs_path(self.logic.cfg.preseg_csv_path))
        except Exception as e:
            slicer.util.errorDisplay(f"Failed to load config: {e}")

    def onBtnConfigEditor(self):
        """Open the Config Editor, pre-loaded with whatever config is currently active in this module. Passes _loadConfigIntoScene as the post-save reload hook, so Save can offer to push the change live. If the current config path field doesn't point at an actual file - empty, still the default Config/ folder from a clean start, or a path that's been moved/deleted - offers a real choice instead of letting the Config Editor fail with a raw error popup (or, for empty, silently open blank with no explanation)."""
        current_path = str(self.ui.tbConfigPath.text).strip()
        if not os.path.isfile(current_path):
            self._promptInvalidConfigPath(current_path)
            return
        self._openConfigEditor(current_path)

    def _openConfigEditor(self, initial_path):
        """Actually construct and show the Config Editor, given an already-validated (or intentionally None) initial path."""
        self._configEditorDialog = ConfigEditorDialog(slicer.util.mainWindow(), initial_path=initial_path, on_saved=self._loadConfigIntoScene)
        self._configEditorDialog.setWindowModality(qt.Qt.NonModal)
        self._configEditorDialog.show()

    def _showStudySetupPrompt(self, message, browse_path=""):
        """Shared 3-button prompt (Browse for config.json / Open clean Config Editor / Cancel) for
        anywhere the module needs a valid, fully-set-up config but doesn't have one yet - replaces
        a dead-end warningDisplay with something actionable. Returns 'browse', 'editor', or None
        (Cancel or the dialog closed another way)."""
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setIcon(qt.QMessageBox.Question)
        box.setWindowTitle("Study Settings")
        box.setText(message)
        browseBtn = box.addButton("Browse for config.json...", qt.QMessageBox.AcceptRole)
        editorBtn = box.addButton("Open clean Config Editor", qt.QMessageBox.ActionRole)
        box.addButton("Cancel", qt.QMessageBox.RejectRole)
        box.setDefaultButton(browseBtn)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is browseBtn:
            fname = QFileDialog.getOpenFileName(None, 'Open config', browse_path, "JSON files (*.json)")
            return "browse" if fname else None, fname
        if clicked is editorBtn:
            return "editor", None
        return None, None

    def _promptInvalidConfigPath(self, path):
        """The config path field doesn't point at a loadable config.json - empty, a folder (most
        commonly the default Config/ browse starting point on a clean Slicer start), or a file
        that no longer exists - ask what to do instead of opening the Config Editor straight into
        a load failure, or silently opening it blank with no explanation."""
        if not path:
            what = "empty - no config selected yet"
        elif os.path.isdir(path):
            what = "a folder"
        else:
            what = "a file that no longer exists"
        detail = f":\n\n{path}" if path else ""
        choice, fname = self._showStudySetupPrompt(
            f"The current config path is {what}{detail}.\n\nWhat would you like to do?", browse_path=path)
        if choice == "browse":
            self._loadConfigIntoScene(fname)
            self._openConfigEditor(fname)
        elif choice == "editor":
            self._openConfigEditor(None)
        # Cancel (or the dialog closed another way): do nothing, no Config Editor opens.

    def _promptStudyNotReady(self, reason):
        """Same 3-button prompt as _promptInvalidConfigPath, used from Initialize Study whenever
        it can't proceed because the config/CSV setup isn't complete yet (empty/invalid config
        path, or the database/preseg CSV paths are empty) - Browse starts from the current Study
        config field's path (same as 'Select .json file'), loads the picked config straight into
        the scene (no Config Editor involved), and immediately retries Initialize Study so picking
        a valid config actually finishes the job in one go. Open clean Config Editor opens a blank
        one to build a config from scratch instead."""
        current_path = str(self.ui.tbConfigPath.text).strip()
        choice, fname = self._showStudySetupPrompt(f"{reason}\n\nWhat would you like to do?", browse_path=current_path)
        if choice == "browse":
            self._loadConfigIntoScene(fname)
            self.onBtnInitializeStudy()
        elif choice == "editor":
            self._openConfigEditor(None)

    def onBtnSelectDB(self):
        """Browse for an override Database CSV path (normally this is auto-filled from the loaded config)."""
        fname = QFileDialog.getOpenFileName(None, 'Open file', str(self.ui.tbDBPath.text), "CSV files (*.csv)")
        if fname:
            self._parameterNode.SetParameter("DatabaseCSVPath", fname)

    def onBtnSelectPreseg(self):
        """Browse for an override Preseg CSV path (normally this is auto-filled from the loaded config)."""
        fname = QFileDialog.getOpenFileName(None, 'Open file', str(self.ui.tbPresegPath.text), "CSV files (*.csv)")
        if fname:
            self._parameterNode.SetParameter("PresegCSVPath", fname)

    def _preflight_check(self, db_path, preseg_path):
        """Pure-Python (no Slicer/VTK calls) sanity check, run before ever
        calling slicer.util.loadTable()/self.logic.initializeStudy(). Catches
        the most common real-world mistakes - a typo'd key column, an empty
        or malformed CSV - with a plain-language message, instead of letting
        them surface as a native VTK/Slicer error dialog that's confusing for
        non-technical users. Returns None if everything looks fine, otherwise
        a ready-to-show message string."""

        key_columns = None
        if self.logic.cfg is not None:
            key_columns = self.logic.cfg.key_columns
        else:
            config_path = str(self.ui.tbConfigPath.text).strip() or self.CONFIG_PATH
            try:
                import json
                with open(config_path, "r", encoding="utf-8") as f:
                    raw_cfg = json.load(f)
                key_columns = raw_cfg.get("key_columns") or ["ID"]
            except Exception as e:
                return f"The config file couldn't be read as JSON:\n{e}\n\nOpen it in the Config Editor to fix it."

        def _read_header(path, label):
            """Read one CSV's header row with plain Python csv (no Slicer/VTK) and return (header, error_message) - error_message is None on success."""
            try:
                with open(path, "r", encoding="utf-8-sig", newline="") as f:
                    header = next(csv.reader(f), None)
            except Exception as e:
                return None, f"{label} couldn't be read as a CSV file:\n{path}\n\n{e}"
            if not header or not any(h.strip() for h in header):
                return None, f"{label} appears to be empty (no header row):\n{path}"
            return header, None

        db_header, err = _read_header(db_path, "The database CSV")
        if err:
            return err
        preseg_header, err = _read_header(preseg_path, "The preseg CSV")
        if err:
            return err

        missing_db = [c for c in key_columns if c not in db_header]
        missing_preseg = [c for c in key_columns if c not in preseg_header]
        if missing_db or missing_preseg:
            lines = ["The key column(s) from the config don't match the actual CSV columns:"]
            if missing_db:
                lines.append(f"  - missing from database CSV: {missing_db}")
            if missing_preseg:
                lines.append(f"  - missing from preseg CSV: {missing_preseg}")
            lines.append("")
            lines.append(f"Database CSV columns:  {db_header}")
            lines.append(f"Preseg CSV columns:    {preseg_header}")
            lines.append("")
            lines.append("Fix 'Key columns' in the Config Editor's General tab (or use 'Show CSV columns...' there to check the exact names).")
            return "\n".join(lines)

        return None

    def onBtnInitializeStudy(self):
        """(Re)build the specimen list: if a specimen is already open, warn and offer to save first; validate the config/CSV paths (folder-vs-file, then a pure-Python CSV/key-column sanity check) before ever calling Slicer's table loader; finally call Logic.initializeStudy() and refresh the table/batch combo."""
        if self.logic.hasActiveSpecimen:
            ret = qt.QMessageBox.warning(
                slicer.util.mainWindow(), "Re-initialize study",
                "A specimen is currently open. Re-initializing the study reloads the "
                "database/preseg tables and rebuilds the specimen list - any unsaved "
                "work on the open specimen (and unsaved database table edits) can be "
                "lost or end up misattributed if you continue without saving first.\n\n"
                "Save the active specimen and the database CSV before continuing?",
                qt.QMessageBox.Save | qt.QMessageBox.Discard | qt.QMessageBox.Cancel)
            if ret == qt.QMessageBox.Cancel:
                return
            if ret == qt.QMessageBox.Save:
                try:
                    self.logic.save_active_specimen(inform_user=False)
                    self.logic.save_db()
                except Exception as e:
                    slicer.util.errorDisplay("Failed to save before re-initializing: " + str(e))
                    return
            self.logic.close_active_specimen(no_question=True)
            self._detach_active_specimen_observers()
            self._updatePostInitButtonStates()
            self._refresh_specimen_status_labels()
            self._refreshSpecimenAnnotation()

        try:
            if self.logic.cfg is None:
                config_path = str(self.ui.tbConfigPath.text).strip() or self.CONFIG_PATH
                if not config_path:
                    self._promptStudyNotReady("No study config selected yet.")
                    return
                if not os.path.exists(config_path):
                    self._promptStudyNotReady(f"Config file not found:\n{config_path}")
                    return
                if os.path.isdir(config_path):
                    # This is the Config/ folder pre-filled as a Browse starting
                    # point (see updateGUIFromParameterNode) - it was never
                    # actually picked as a file. Opening a directory as a config
                    # raises IsADirectoryError, which used to surface as a
                    # confusing generic "Failed to load config" message.
                    self._promptStudyNotReady(f"That's a folder, not a config file yet:\n{config_path}")
                    return
                self.logic.load_config(config_path)
        except Exception as e:
            slicer.util.errorDisplay("Failed to load config: " + str(e))
            return

        db_path = str(self.ui.tbDBPath.text).strip()
        preseg_path = str(self.ui.tbPresegPath.text).strip()
        if not db_path or not preseg_path:
            self._promptStudyNotReady(
                "Database CSV and Preseg CSV paths must both be set. They're normally filled in "
                "automatically from the config - if they're empty, the loaded config may be missing "
                "database_csv_path/preseg_csv_path, or you cleared the fields by hand.")
            return
        if not os.path.exists(db_path):
            slicer.util.warningDisplay(f"Database CSV not found:\n{db_path}")
            return
        if not os.path.exists(preseg_path):
            slicer.util.warningDisplay(f"Preseg CSV not found:\n{preseg_path}")
            return

        problem = self._preflight_check(db_path, preseg_path)
        if problem:
            slicer.util.warningDisplay(problem)
            return

        try:
            self._studyInitialized = False
            self.logic.initializeStudy()
            if not self._resolveMissingDbColumns():
                self.logic.specimens = {}
                self.ui.tblSpecimens.setRowCount(0)
                self._updatePostInitButtonStates()
                return
            self._studyInitialized = True
            self._group_filter = None
            self._setup_batch_combo()
            self.show_specimen_table()
            self._updatePostInitButtonStates()
        except Exception as e:
            slicer.util.errorDisplay("Failed to initialize study: " + str(e))
            import traceback
            traceback.print_exc()

    def _resolveMissingDbColumns(self):
        """Right after the tables load: any configured Factor column missing from database.csv is
        surely intentional (not a typo), so offer to create it; a plain table_columns entry that's
        missing MAY be a typo, so those are listed separately and only created if explicitly
        ticked. Returns False if the user cancels (Initialize Study is then aborted), else True
        with the chosen columns already added to the live database table."""
        cfg = self.logic.cfg
        existing = set(self.logic.dbColumnNames)
        factor_cols = [fc.column for fc in cfg.factor_columns if fc.column and fc.column not in existing]
        if cfg.status_column not in existing and cfg.status_column not in factor_cols:
            factor_cols.insert(0, cfg.status_column)   # the status column is never a typo - always offered for creation
        table_cols = [c for c in cfg.table_columns if c not in existing and c not in factor_cols]
        if not factor_cols and not table_cols:
            return True

        dlg = qt.QDialog(slicer.util.mainWindow())
        dlg.setWindowTitle("Columns missing from database.csv")
        layout = qt.QVBoxLayout(dlg)
        layout.addWidget(qt.QLabel("Some configured columns don't exist in the database CSV yet."))
        if factor_cols:
            lbl = qt.QLabel("<b>Status / factor columns</b> - will be created (empty):<br>" + ", ".join(factor_cols))
            lbl.setWordWrap(True)
            layout.addWidget(lbl)
        table_checks = []
        if table_cols:
            layout.addWidget(qt.QLabel("<b>Table columns</b> - possibly typos; tick only the ones to create:"))
            for c in table_cols:
                chk = qt.QCheckBox(c)
                table_checks.append(chk)
                layout.addWidget(chk)
        btnRow = qt.QHBoxLayout()
        addBtn = qt.QPushButton("Add columns and continue")
        addBtn.connect('clicked(bool)', lambda checked=False: dlg.accept())
        cancelBtn = qt.QPushButton("Cancel initialization")
        cancelBtn.connect('clicked(bool)', lambda checked=False: dlg.reject())
        btnRow.addStretch(1)
        btnRow.addWidget(addBtn)
        btnRow.addWidget(cancelBtn)
        layout.addLayout(btnRow)
        if dlg.exec_() != qt.QDialog.Accepted:
            return False

        added = list(factor_cols) + [c for c, chk in zip(table_cols, table_checks) if chk.checked]
        for c in added:
            self.logic.ensure_db_column(c)
        if added:
            self.logic.save_db(inform_user=False)   # write the new columns to database.csv right away
        return True

    def _setup_batch_combo(self):
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
            self.show_specimen_table()

    def onGroupByKeyChanged(self, text):
        """Re-filter the specimen table by the newly selected batch value. Refuses (and reverts the combo back) while a specimen is currently active."""
        if self.logic.hasActiveSpecimen:
            slicer.util.errorDisplay("Close the active specimen before switching group.")
            self.ui.cmbGroupByKey.blockSignals(True)
            self.ui.cmbGroupByKey.currentText = self._group_filter or "(all)"
            self.ui.cmbGroupByKey.blockSignals(False)
            return
        self._group_filter = None if text == "(all)" else text
        self.show_specimen_table()

    def show_specimen_table(self):
        """(Re)draw the specimen table: one row per specimen (optionally filtered to the current
        batch), rows colored by status (SPECIMEN_STATUS_COLORS). The status column is a dropdown of the four statuses. Any column also listed in cfg.factor_columns
        renders as a checkbox (binary) or a level dropdown (multilevel) instead of free text - see
        _onFactorMultilevelChanged() for the dropdown's write-back path (cell widgets don't fire
        itemChanged, so specimen_tbl_changed() alone doesn't cover them)."""
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
        # blocks specimen_tbl_changed()/_onFactorMultilevelChanged() from treating this initial
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
        self._refresh_specimen_status_labels()
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
        SPECIMEN_TABLE_MAX_VISIBLE_ROWS (Definitions.py) AND up to the space actually left in the
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

    def selected_specimen_changed(self):
        """Track which specimen row is currently selected, by KEY (not row index, since row order can change) - used by the Load button."""
        sel = self.ui.tblSpecimens.selectedIndexes()
        if len(sel) == 0:
            return
        row = sel[0].row()
        key_columns = self.logic.cfg.key_columns
        columns = self._displayColumns()
        key = tuple(self.ui.tblSpecimens.item(row, columns.index(c)).text() for c in key_columns)
        self.tbl_selected_key = key
        self._refresh_specimen_status_labels()

    @staticmethod
    def _status_dot(color):
        """A small colored bullet, as a rich-text prefix for a status label."""
        return f'<span style="color:{color};">●</span> '

    def _specimen_is_dirty(self, specimen):
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

    def _refresh_specimen_status_labels(self):
        """Update the colored status dot in front of the Selected/Active specimen labels: gray =
        the selected table row isn't the currently active specimen, green = it is (or this IS the
        Active label) and clean, orange = it is (or Active) with unsaved segmentation/markups
        changes. Called on table selection, after load/save/close, and whenever the active
        specimen's segmentation/markups node fires a Modified event (see
        _attach_active_specimen_observers())."""
        active = self.logic.active_specimen if self.logic.hasActiveSpecimen else None
        active_dirty = self._specimen_is_dirty(active) if active is not None else False

        if self.tbl_selected_key is not None:
            color = "#999999"
            if active is not None and self.tbl_selected_key == active.key:
                color = "#d98c00" if active_dirty else "#2e8b2e"
            self.ui.lblSelectedSpecimen.text = self._status_dot(color) + "-".join(self.tbl_selected_key)

        if active is not None:
            color = "#d98c00" if active_dirty else "#2e8b2e"
            self.ui.lblActiveSpecimen.text = self._status_dot(color) + active.label
        else:
            self.ui.lblActiveSpecimen.text = ""

    def _attach_active_specimen_observers(self):
        """Observe the active specimen's segmentation/markups nodes for Modified events, so the
        status dot flips to 'unsaved changes' live instead of only on the next table click. A
        no-op if already observing this exact specimen."""
        if not self.logic.hasActiveSpecimen:
            return
        specimen = self.logic.active_specimen
        if self._active_specimen_observed is specimen:
            return
        self._detach_active_specimen_observers()
        for node in (specimen.segmentation_node, specimen.markups_node):
            if node is not None:
                self.addObserver(node, vtk.vtkCommand.ModifiedEvent, self._onActiveSpecimenNodeModified)
        self._active_specimen_observed = specimen

    def _detach_active_specimen_observers(self):
        """Stop observing whatever specimen _attach_active_specimen_observers() last wired up - call before/after closing the active specimen."""
        specimen = self._active_specimen_observed
        if specimen is None:
            return
        for node in (specimen.segmentation_node, specimen.markups_node):
            if node is not None:
                self.removeObserver(node, vtk.vtkCommand.ModifiedEvent, self._onActiveSpecimenNodeModified)
        self._active_specimen_observed = None

    def _onActiveSpecimenNodeModified(self, caller=None, event=None):
        self._refresh_specimen_status_labels()

    def specimen_tbl_changed(self, changed_item=None):
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
        directly in show_specimen_table() since cell widgets never fire the table's itemChanged
        signal) - writes the level's exact text to the CSV ("(unset)" -> empty string), the same
        row_index-based path specimen_tbl_changed() uses for everything else."""
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

    def onBtnLoadSelected(self):
        """Load the currently-selected specimen, start observing it for the status dot, and update the active-specimen label/button state."""
        try:
            if not self.tbl_selected_key:
                return
            self.logic.load_specimen(self.tbl_selected_key)
            specimen = self.logic.active_specimen
            if specimen is not None and specimen.loaded_own_data:
                self._setSpecimenStatus(specimen, SpecimenStatus.IN_PROGRESS, only_raise=True)
            self._attach_active_specimen_observers()
            self._updatePostInitButtonStates()
            self._refresh_specimen_status_labels()
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
        """Ctrl+S belongs to this module ONLY while a specimen is loaded. Then Slicer's own Ctrl+S action (File > Save scene) has its shortcut cleared - two owners of one key sequence make Qt refuse to pick either ("Ambiguous shortcut overload") - and given back the moment no specimen is loaded, so Save scene works as usual otherwise."""
        shortcut = getattr(self, "_saveShortcut", None)
        if shortcut is None:
            return
        take = bool(self.logic is not None and self.logic.hasActiveSpecimen)
        shortcut.enabled = take
        if take and not self._displacedSaveActions:
            for action in slicer.util.mainWindow().findChildren(qt.QAction):
                if action.shortcut.toString() == "Ctrl+S":
                    self._displacedSaveActions.append((action, action.shortcut))
                    action.setShortcut(qt.QKeySequence())
        elif not take:
            self._restoreSlicerSaveShortcut()

    def _restoreSlicerSaveShortcut(self):
        """Give Slicer's own Ctrl+S action(s) their shortcut back."""
        for action, sequence in self._displacedSaveActions:
            action.setShortcut(sequence)
        self._displacedSaveActions = []

    def _saveActiveSpecimen(self, inform_user):
        """Save the active specimen's writeable nodes, promote its status to in progress, and refresh the status dot back to clean."""
        try:
            self.logic.save_active_specimen(inform_user=inform_user)
            if self.logic.active_specimen is not None:
                self._setSpecimenStatus(self.logic.active_specimen, SpecimenStatus.IN_PROGRESS, only_raise=True)
            self._refresh_specimen_status_labels()
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
            self._detach_active_specimen_observers()
            self._updatePostInitButtonStates()
            self._refresh_specimen_status_labels()
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
                self._detach_active_specimen_observers()
            self._setSpecimenStatus(specimen, SpecimenStatus.UNTOUCHED)
            self._updatePostInitButtonStates()
            self._refresh_specimen_status_labels()
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
