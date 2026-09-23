"""
ConfigModel
============

Typed, attribute-accessed representation of a study config.json - the
dataclass counterpart to the raw dict the JSON parses into. Nothing in
GenericSpecimenEngine.py should need to reach into a plain dict with
`.get("x", {}).get("y", [])` chains anymore; it reads `cfg.segmentation.segments`,
`cfg.landmarks.enabled`, etc.

Two kinds of dataclasses live here:

1. "Section" dataclasses (StudyConfig, SegmentationConfig, LandmarksConfig,
   GlobalWindowLevelConfig, BatchExportConfig,
   SegmentEditorConfig, BrushConfig, DefaultsConfig) - one meaning, one
   place in the schema, built once from the raw dict at load time.

2. "Override" dataclasses (ImageConfig, SegmentConfig, WindowLevel,
   Threshold) - every field is Optional and defaults to None (meaning
   "unspecified / inherit"). The SAME dataclass shape is used for
   cfg.defaults.image, cfg.presets[name], and each images[] entry, and
   merge_image_overrides() layers them (defaults -> preset -> inline,
   later non-None values win) into the final, per-specimen-image config.
   merge_segment_overrides() does the same for cfg.defaults.segment vs. a
   segments[] entry. Only at the point of use do semantic defaults apply
   (e.g. `img_cfg.type or "volume"`), so merging never confuses "the field
   wasn't set" with "the field's default value was set".

3. VolumeRenderingEntry - cfg.volume_rendering is a LIST of these, one per
   image, each independently enabled/preset/shifted (min/max or
   window/level, reusing the WindowLevel shape), mirroring how images[]
   entries work.

See README.md for the JSON schema this mirrors.
"""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field, fields, replace
from typing import Optional, List, Dict, Any


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------

def _from_dict(cls, d: Optional[dict]):
    """Build a dataclass instance from a dict, ignoring unknown keys."""
    d = d or {}
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in known})


def _overlay(cls, *sources):
    """Merge any number of instances of an all-Optional dataclass `cls`:
    later, non-None field values win. None sources are skipped."""
    result = cls()
    for src in sources:
        if src is None:
            continue
        for f in fields(cls):
            val = getattr(src, f.name)
            if val is not None:
                setattr(result, f.name, val)
    return result


# ---------------------------------------------------------------------------
# small override dataclasses shared by defaults.image / presets[name] / images[]
# ---------------------------------------------------------------------------

@dataclass
class WindowLevel:
    """Per-image or global window/level override. Supports three mutually-exclusive forms: {auto:true} (Slicer auto-windows it), {min,max} (explicit display range), or {window,level} (width/center form, e.g. matching a historical SetWindowLevel(w,l) call). All fields None = 'not set'."""
    auto: Optional[bool] = None
    min: Optional[float] = None
    max: Optional[float] = None
    window: Optional[float] = None
    level: Optional[float] = None

    @classmethod
    def from_dict(cls, d):
        """Build a WindowLevel override from a raw dict, or None if the dict is empty/missing (meaning 'not set', not 'set to defaults')."""
        return _from_dict(cls, d) if d else None


@dataclass
class Threshold:
    """Per-image display threshold override (SetThreshold + ApplyThresholdOn/Off)."""
    min: Optional[float] = None
    max: Optional[float] = None
    apply: Optional[bool] = None

    @classmethod
    def from_dict(cls, d):
        """Build a Threshold override from a raw dict, or None if the dict is empty/missing."""
        return _from_dict(cls, d) if d else None


@dataclass
class ImageConfig:
    """One images[] entry - OR the result of merging defaults.image ->
    presets[name] -> an entry, via merge_image_overrides(). Every field is
    Optional; apply semantic defaults ("volume", False, ...) at the point
    of use, not here."""
    name: Optional[str] = None
    csv_column: Optional[str] = None
    path_pattern: Optional[str] = None
    pattern: Optional[str] = None            # dynamic column-matching regex (unexpanded entries only)
    strip_prefix: Optional[str] = None
    strip_suffix: Optional[str] = None
    type: Optional[str] = None               # "volume" (default) | "labelmap"
    role: Optional[str] = None               # "background" | "label" | "foreground" | None
    required: Optional[bool] = None          # default False
    preset: Optional[str] = None
    opacity: Optional[float] = None
    window_level: Optional[WindowLevel] = None
    color_table: Optional[str] = None
    threshold: Optional[Threshold] = None
    interpolate: Optional[bool] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build one ImageConfig override (a raw images[] entry, defaults.image, or a presets[name] entry - same shape for all three) from a dict, parsing its nested window_level/threshold sub-dicts first since they need their own from_dict."""
        d = dict(d or {})
        wl = WindowLevel.from_dict(d.pop("window_level", None))
        th = Threshold.from_dict(d.pop("threshold", None))
        inst = _from_dict(cls, d)
        inst.window_level = wl
        inst.threshold = th
        return inst


def merge_image_overrides(*sources: Optional[ImageConfig]) -> ImageConfig:
    """Layer any number of ImageConfig overrides in order (typically defaults.image -> the named preset -> the image's own entry) into one final ImageConfig - the last non-None value per field wins. Plain dataclass field overlay, no regex/pattern matching."""
    return _overlay(ImageConfig, *sources)


@dataclass
class SegmentConfig:
    """One segmentation.segments[] entry - OR the result of merging
    defaults.segment -> an entry, via merge_segment_overrides()."""
    name: Optional[str] = None
    csv_column: Optional[str] = None
    path_pattern: Optional[str] = None
    source: Optional[str] = None             # "file" (default) | "empty"
    color: Optional[List[float]] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build one SegmentConfig override (a raw segments[] entry or defaults.segment) from a dict."""
        return _from_dict(cls, d)


def merge_segment_overrides(*sources: Optional[SegmentConfig]) -> SegmentConfig:
    """Layer defaults.segment and a segment's own entry into one final SegmentConfig - same idea as merge_image_overrides but one level (segments have no named presets)."""
    return _overlay(SegmentConfig, *sources)


# ---------------------------------------------------------------------------
# top-level sections (one meaning, one place - not merged/overridden)
# ---------------------------------------------------------------------------

@dataclass
class DefaultsConfig:
    """cfg.defaults - the 'applies to every row' base layer for images and segments (see merge_image_overrides/merge_segment_overrides)."""
    image: ImageConfig = field(default_factory=ImageConfig)
    segment: SegmentConfig = field(default_factory=SegmentConfig)

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build DefaultsConfig from the config's 'defaults' block: its 'image' and 'segment' sub-dicts, each parsed as their own override type."""
        d = d or {}
        return cls(
            image=ImageConfig.from_dict(d.get("image")),
            segment=SegmentConfig.from_dict(d.get("segment")),
        )


@dataclass
class SegmentationConfig:
    """cfg.segmentation - whether/how to build or load this study's segmentations, and the list of segments each specimen should have."""
    enabled: bool = False
    reference_image: Optional[str] = None
    path_pattern: Optional[str] = None
    segments: List[SegmentConfig] = field(default_factory=list)
    output_filename: str = "segment.seg.nrrd"
    opacity: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build SegmentationConfig from the config's 'segmentation' block, including its list of segments[] (each parsed as a SegmentConfig)."""
        d = d or {}
        return cls(
            enabled=bool(d.get("enabled", False)),
            reference_image=d.get("reference_image"),
            path_pattern=d.get("path_pattern"),
            segments=[SegmentConfig.from_dict(s) for s in d.get("segments", [])],
            output_filename=d.get("output_filename", "segment.seg.nrrd"),
            opacity=d.get("opacity"),
        )


@dataclass
class LandmarksConfig:
    """cfg.landmarks - whether/how to load or create each specimen's markups (fiducial) file."""
    enabled: bool = False
    csv_column: Optional[str] = None
    path_pattern: Optional[str] = None
    template_path: Optional[str] = None
    writable: Optional[bool] = None          # default True
    color: Optional[List[float]] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build LandmarksConfig from the config's 'landmarks' block."""
        return _from_dict(cls, d or {})


@dataclass
class VolumeRenderingEntry:
    """One entry in the volume_rendering LIST - one image, independently
    enable-able, with its own preset and an optional shift: either a fixed
    'offset' (moves every control point by the same amount, preserving
    spacing - the classic "Shift" slider behavior), or window_level
    (min/max or window/level, same forms as ImageConfig.window_level - a
    full rescale into a target range). If both are set, offset wins (see
    GenericSpecimen._apply_volume_rendering_shift)."""
    image: Optional[str] = None
    enabled: Optional[bool] = None
    preset: Optional[str] = None
    window_level: Optional[WindowLevel] = None
    offset: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build one VolumeRenderingEntry from a volume_rendering[] list item, parsing its nested window_level sub-dict first."""
        d = dict(d or {})
        wl = WindowLevel.from_dict(d.pop("window_level", None))
        inst = _from_dict(cls, d)
        inst.window_level = wl
        return inst


@dataclass
class GlobalWindowLevelConfig:
    """The blanket window/level applied to EVERY loaded scalar volume
    display node in _customize_workplace() - distinct from the per-image
    ImageConfig.window_level override."""
    enabled: bool = False
    min: Optional[float] = None
    max: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build GlobalWindowLevelConfig from the config's top-level 'window_level' block - the blanket setting applied to every loaded volume, distinct from an image row's own per-image window_level."""
        return _from_dict(cls, d or {})


@dataclass
class SliceRotationConfig:
    """cfg.slice_rotation - an in-plane rotation (degrees, around each slice
    view's own normal) applied to Red/Yellow/Green once a specimen loads -
    identical to the Reformat module's rotation slider. Useful to correct a
    systematic scan orientation across a whole study. Each view's angle is
    independently optional (None = leave that view alone)."""
    enabled: bool = False
    red: Optional[float] = None
    yellow: Optional[float] = None
    green: Optional[float] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build SliceRotationConfig from the config's top-level 'slice_rotation' block."""
        return _from_dict(cls, d or {})


@dataclass
class WorkspaceConfig:
    """cfg.workspace - crosshair, slice-view ruler, orientation-marker (3D
    view and/or 2D slice views), and L/R view convention, applied once per
    specimen load (_customize_workplace() / _apply_workspace_settings()).
    Every field is optional; unset means "leave Slicer's own default/
    previous value alone" - EXCEPT the three crosshair fields, which fall
    back to this module's long-standing defaults (ShowBasic /
    OffsetJumpSlice / Fine) when unset, so leaving cfg.workspace out
    entirely changes nothing from before this feature existed. Values are
    the exact Slicer/VTK enum constant NAME as a string (e.g. "ShowBasic",
    "OffsetJumpSlice") for crosshair fields; ruler_type/
    orientation_marker_*_type/orientation_marker_*_size use a SHORT name
    (e.g. "Thin", "Axes", "Large") that the engine prefixes itself
    (RulerType/OrientationMarkerType/OrientationMarkerSize) - see
    GenericSpecimen._apply_workspace_settings()."""
    crosshair_mode: Optional[str] = None
    crosshair_behavior: Optional[str] = None
    crosshair_thickness: Optional[str] = None
    ruler_type: Optional[str] = None
    # vtkMRMLSliceNode inherits the same OrientationMarkerType/Size property
    # as the 3D view node (both extend vtkMRMLAbstractViewNode), so the
    # marker can be shown in the 3D view, the slice views, or both -
    # independently configured here.
    orientation_marker_3d_type: Optional[str] = None
    orientation_marker_3d_size: Optional[str] = None
    orientation_marker_2d_type: Optional[str] = None
    orientation_marker_2d_size: Optional[str] = None
    # "radiological" (Slicer's own default: patient's right on screen-left)
    # or "neurological" (patient's right on screen-right). Unset = leave
    # Slicer's current slice orientation presets alone.
    view_convention: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build WorkspaceConfig from the config's top-level 'workspace' block."""
        return _from_dict(cls, d or {})


@dataclass
class BatchExportConfig:
    """cfg.batch_export - what BatchProcessor (GenericSpecimenEngine.py) does
    with every 'done' specimen, in ONE pass: export segment labelmaps to
    files, export markups, and/or compute custom per-segment statistics
    into one or more CSVs - any combination. Whichever of these is turned
    on decides what gets loaded per specimen (a lean load, skipping
    workspace/volume-rendering/Segment-Editor setup - see
    GenericSpecimen.load_for_batch())."""
    enabled: bool = False
    export_segments: bool = False
    export_markups: bool = False
    # Custom per-segment statistics (volume/min/max/mean/median/std/
    # percentile_<N>), computed straight from Slicer's own per-segment
    # labelmap export + slicer.util.arrayFromVolume() - not from any
    # external file-reading library, so overlapping segments are handled
    # correctly (each segment's mask is independently exported, not
    # decoded from one shared multi-label array).
    compute_stats: bool = False
    reference_image: Optional[str] = None
    # Affects segment file export, markup file export, AND which segments
    # get stats rows - the one field genuinely shared across everything.
    segments_filter: Optional[List[str]] = None
    # Governs SEGMENT and MARKUP export only (not statistics - see
    # stats_output_path below, which shares this same root but is never
    # nested through output_dir_pattern). output_dir is
    # the optional ROOT: unset -> study_dir; relative -> resolved under
    # study_dir; absolute -> used as-is. output_dir_pattern is a
    # curly-brace pattern resolved PER SPECIMEN and joined onto that root -
    # the exact same mechanism as the General tab's own output_dir_pattern
    # (any key/database.csv/preseg.csv column name in {braces}; unset
    # defaults the same way too, joining the key columns). This lets a
    # database column - e.g. a "batch" column - route different
    # specimens' exports into different subfolders, simply by referencing
    # {batch} in the pattern; no separate on/off flag needed for that.
    output_dir: Optional[str] = None
    output_dir_pattern: Optional[str] = None
    # One or more Images-tab names to sample intensities from - one stats
    # row per (specimen, sample image, segment). Falls back to
    # `reference_image` above, then segmentation.reference_image, wrapped
    # in a single-item list, if unset. All sample images must share the
    # segment labelmap's geometry (same grid) - a mismatched one is
    # skipped with a warning, not silently misread.
    stats_reference_images: Optional[List[str]] = None
    # Comma-separated in the Config Editor; each entry is volume/min/max/
    # mean/median/std or percentile_<N> (e.g. percentile_25). Unset/empty
    # falls back to Definitions.DEFAULT_STATS_METRICS.
    stats_metrics: Optional[List[str]] = None
    # The "batch segment statistics pattern": a curly-brace pattern (same
    # {column} mechanism as output_dir_pattern above, plus "{date}"/
    # "{time}"/"{datetime}") resolved PER SPECIMEN. Defaults to
    # "report.csv". If the result is a relative path, it's anchored to
    # output_dir above (the SAME shared root segment/markup files use) -
    # or to study_dir directly if output_dir itself is unset - but,
    # unlike segment/markup files, this is NEVER nested through
    # output_dir_pattern; it's its own separate path straight under that
    # root. Grouping is automatic and needs no separate flag: specimens
    # that resolve to the SAME final path share one CSV;
    # if the pattern references a column that varies (e.g. "{batch}/
    # report.csv"), specimens with different values naturally end up in
    # separate files instead.
    stats_output_path: Optional[str] = None
    # Combines every specimen's landmark points into one or more CSVs -
    # one row per landmark (identified by its label), key columns
    # prepended, same grouping-by-resolved-path mechanism as
    # stats_output_path (see landmarks_output_path below). Only
    # meaningful together with export_markups (that's what actually
    # loads the markups node this reads from). A PER-SPECIMEN landmarks
    # CSV is written automatically whenever export_markups is on,
    # regardless of this flag - this only controls the additional,
    # combined multi-specimen report.
    landmarks_report: bool = False
    # The "landmarks report pattern" - same {column}/{date}/{time}/
    # {datetime} mechanism and same root-anchoring as stats_output_path
    # (batch_export.output_dir if set, else study_dir; never nested
    # through output_dir_pattern). Defaults to "landmarks_report.csv".
    landmarks_output_path: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build BatchExportConfig from the config's 'batch_export' block."""
        return _from_dict(cls, d or {})


@dataclass
class BatchModeConfig:
    """Optional filtering of specimens by a database.csv column (e.g. "batch"),
    for the MAIN MODULE'S interactive specimen table only. When enabled,
    the GUI shows a batch-select combo box after Initialize Study,
    re-filtering the specimen table to the selected batch value. This is
    purely a viewing convenience - batch_export's own output_dir_pattern/
    stats_output_path can reference any database.csv column directly
    (including this one, by name), with no dependency on this section at
    all."""
    enabled: bool = False
    column: Optional[str] = None             # database.csv column to group/filter by

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build BatchModeConfig from the config's 'batch_mode' block."""
        return _from_dict(cls, d or {})


@dataclass
class BrushConfig:
    """segment_editor.brush - Segment Editor's Paint-effect brush shape/size, applied to the segment editor node's attributes (see GenericSpecimenEngine._configure_segment_editor_defaults / _activate_segment_editor)."""
    shape: Optional[str] = None              # "sphere" | "circle"
    diameter_mm: Optional[float] = None
    relative: Optional[bool] = None          # default False

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build BrushConfig from segment_editor's nested 'brush' sub-dict, or None if it's absent."""
        return _from_dict(cls, d) if d else None


@dataclass
class SegmentEditorConfig:
    """cfg.segment_editor - Segment Editor defaults (overwrite mode, brush, which effect to pre-select, and a raw attribute escape hatch) applied once at Study Init and again per-specimen once a real segmentation exists."""
    overwrite_mode: Optional[str] = None     # "none" (default = allow overlap) | "all_segments" | "visible_segments"
    brush: Optional[BrushConfig] = None
    active_effect: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)

    def is_configured(self) -> bool:
        """True if any field here was actually set in the config - used to decide whether to touch the Segment Editor at all (an all-default/empty block means 'leave Slicer's own defaults alone')."""
        return bool(self.overwrite_mode or self.brush or self.active_effect or self.attributes)

    @classmethod
    def from_dict(cls, d: Optional[dict]):
        """Build SegmentEditorConfig from the config's 'segment_editor' block, parsing its nested 'brush' sub-dict first."""
        d = dict(d or {})
        brush = BrushConfig.from_dict(d.pop("brush", None))
        inst = _from_dict(cls, d)
        inst.brush = brush
        return inst


# ---------------------------------------------------------------------------
# StudyConfig - the whole thing
# ---------------------------------------------------------------------------

@dataclass
class StudyConfig:
    """The whole parsed config.json. Everything GenericSpecimenEngine.py needs is reachable from here via attributes - no raw dict.get() chains."""
    study_dir: str = "."
    database_csv_path: str = ""
    preseg_csv_path: str = ""
    key_columns: List[str] = field(default_factory=lambda: ["ID"])
    done_column: str = "done"
    table_columns: List[str] = field(default_factory=list)
    # Where a specimen's own files (segmentation, markups, and any image
    # explicitly saved) live for INTERACTIVE work - resolved per specimen
    # (any key/database.csv/preseg.csv column in {braces}) and used every
    # time you load/save a specimen through the normal GUI ("Load selected
    # specimen"/"Save progress" buttons). This is DIFFERENT from
    # batch_export's own output_dir/output_dir_pattern, which only apply
    # during a headless Batch Export run and never touch interactive
    # work - the two are independent, and either can be set without the
    # other.
    output_dir_pattern: Optional[str] = None

    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    presets: Dict[str, ImageConfig] = field(default_factory=dict)
    images: List[ImageConfig] = field(default_factory=list)

    segmentation: SegmentationConfig = field(default_factory=SegmentationConfig)
    landmarks: LandmarksConfig = field(default_factory=LandmarksConfig)
    volume_rendering: List[VolumeRenderingEntry] = field(default_factory=list)
    window_level: GlobalWindowLevelConfig = field(default_factory=GlobalWindowLevelConfig)
    slice_rotation: SliceRotationConfig = field(default_factory=SliceRotationConfig)
    workspace: WorkspaceConfig = field(default_factory=WorkspaceConfig)
    batch_export: BatchExportConfig = field(default_factory=BatchExportConfig)
    segment_editor: SegmentEditorConfig = field(default_factory=SegmentEditorConfig)
    batch_mode: BatchModeConfig = field(default_factory=BatchModeConfig)

    @classmethod
    def from_dict(cls, raw: Optional[dict], base_dir: str = "."):
        """Parse a whole raw config dict into a StudyConfig, building every nested section and override collection in one place. base_dir is the config file's own folder, used as the default study_dir when the config doesn't set one explicitly."""
        raw = dict(raw or {})
        key_columns = raw.get("key_columns", ["ID"])
        done_column = raw.get("done_column", "done")

        return cls(
            study_dir=raw.get("study_dir", base_dir),
            database_csv_path=raw.get("database_csv_path", ""),
            preseg_csv_path=raw.get("preseg_csv_path", ""),
            key_columns=list(key_columns),
            done_column=done_column,
            table_columns=list(raw.get("table_columns", list(key_columns) + [done_column])),
            output_dir_pattern=raw.get("output_dir_pattern") or "/".join(f"{{{k}}}" for k in key_columns),

            defaults=DefaultsConfig.from_dict(raw.get("defaults")),
            presets={name: ImageConfig.from_dict(d) for name, d in raw.get("presets", {}).items()},
            images=[ImageConfig.from_dict(d) for d in raw.get("images", [])],

            segmentation=SegmentationConfig.from_dict(raw.get("segmentation")),
            landmarks=LandmarksConfig.from_dict(raw.get("landmarks")),
            volume_rendering=[VolumeRenderingEntry.from_dict(d) for d in (raw.get("volume_rendering") or [])],
            window_level=GlobalWindowLevelConfig.from_dict(raw.get("window_level")),
            slice_rotation=SliceRotationConfig.from_dict(raw.get("slice_rotation")),
            workspace=WorkspaceConfig.from_dict(raw.get("workspace")),
            batch_export=BatchExportConfig.from_dict(raw.get("batch_export")),
            segment_editor=SegmentEditorConfig.from_dict(raw.get("segment_editor")),
            batch_mode=BatchModeConfig.from_dict(raw.get("batch_mode")),
        )


def load_config(path: str) -> StudyConfig:
    """Load and parse a study config.json into a StudyConfig."""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return StudyConfig.from_dict(raw, base_dir=os.path.dirname(path))
