"""
definitions.py
==============
Every hardcoded, easy-to-want-to-tweak constant in this module, in ONE
place - so a knob like HIDE_HELP_AND_ACKNOWLEDGEMENT doesn't need hunting
through a 1000+-line file/class body to find. If you're looking for
something to turn on/off or a list to extend, look here first.

Logging's own toggle (DEBUG_LOG_TO_FILE) lives in core/logging_setup.py instead -
it's genuinely logging-specific machinery, not a plain on/off switch, so it
stays next to the handler setup it configures.
"""

from enum import IntEnum

# ---- Developer-UI visibility (GenericSpecimenManagerWidgetBase) ----
# Flip either to False to show that section again. See gui/main_widget.py's
# setup()/enter()/exit() for where these are actually applied.
HIDE_RELOAD_AND_TEST = True
HIDE_HELP_AND_ACKNOWLEDGEMENT = True

# ---- Main module GUI (GenericSpecimenManagerWidgetBase) ----
# The specimen table sizes itself to exactly fit its current row count (no
# empty space with few specimens/after a Group filter) up to this many rows -
# beyond that it stays fixed at that height and scrolls instead of pushing
# the rest of the panel down. See _fitSpecimenTableHeight().
SPECIMEN_TABLE_MAX_VISIBLE_ROWS = 12
# The table also never grows taller than the space left in the module panel
# (so the WHOLE module doesn't become scrollable) - but never shrinks below
# this many rows either, however cramped the panel is.
SPECIMEN_TABLE_MIN_VISIBLE_ROWS = 3

# ---- Config Editor GUI ----
# Images tab - how many text lines tall the "Effective settings" box is (it scrolls for
# more); the images table above gets all the remaining space.
IMAGES_PREVIEW_VISIBLE_LINES = 4

# ---- Data safety (see core/safe_io.py) ----
# database.csv is copied into a .backups folder next to it before it is overwritten:
# at most one copy per this many seconds (so auto-save after every edit doesn't push
# every useful old version out), and only the newest DB_BACKUPS_KEEP are kept.
DB_BACKUPS_KEEP = 10
DB_BACKUP_MIN_INTERVAL_SECONDS = 300
# A study's lock file (who has it open) older than this is treated as stale and ignored.
STUDY_LOCK_STALE_HOURS = 12
# Saving a specimen keeps the version it replaces as <file>.prev (one level).
KEEP_PREVIOUS_SPECIMEN_FILES = True

# ---- Config browsing ----
# Slicer settings key holding the folder of the config used last (see utils/config_location.py).
LAST_CONFIG_DIR_SETTING = "GenericSpecimenManager/LastConfigDir"

# ---- Specimen annotation (workspace.specimen_annotation) text in the views ----
SPECIMEN_ANNOTATION_FONT_SIZE = 11
SPECIMEN_ANNOTATION_COLOR = (1.0, 1.0, 0.0)      # text color, yellow
SPECIMEN_ANNOTATION_BG_COLOR = (0.5, 0.5, 0.5)   # gray
SPECIMEN_ANNOTATION_BG_OPACITY = 0.2             # 0 = fully transparent, 1 = opaque
SPECIMEN_ANNOTATION_BG_PADDING = 6               # pixels between the text and the edge of the background

# ---- Specimen status (the config's status_column in database.csv) ----
# Stored in the CSV as the plain integer value. Empty/unknown -> UNTOUCHED.
class SpecimenStatus(IntEnum):
    UNTOUCHED = 0      # never loaded with data / closed without changes
    IN_PROGRESS = 1    # loaded from its own saved file, or saved at least once
    TO_REVIEW = 2      # marked manually
    FINISHED = 3       # marked manually ("mark as finished"); what Batch export processes


SPECIMEN_STATUS_LABELS = {
    SpecimenStatus.UNTOUCHED: "untouched",
    SpecimenStatus.IN_PROGRESS: "in progress",
    SpecimenStatus.TO_REVIEW: "to review",
    SpecimenStatus.FINISHED: "finished",
}

# Specimen table row background per status (r, g, b): white / light blue / pale yellow / darker pastel green.
SPECIMEN_STATUS_COLORS = {
    SpecimenStatus.UNTOUCHED: (255, 255, 255),
    SpecimenStatus.IN_PROGRESS: (205, 228, 250),
    SpecimenStatus.TO_REVIEW: (255, 248, 200),
    SpecimenStatus.FINISHED: (150, 205, 150),
}


# ---- Specimen save behavior (GenericSpecimen) ----
# When True (default), a loaded image (volume/labelmap) is only written back
# to disk on save if it was actually modified since it was loaded/last
# written (checked via the node's own GetModifiedSinceRead()) - most images
# in a study are read-only source data, not something anyone edits, so
# writing them back every save is pure wasted I/O. Segmentation and markups
# are never affected by this - they're always saved, since those ARE the
# point of this module. Flip to False to go back to always writing every
# loaded image on every save, regardless of whether it changed.
IMAGES_READ_ONLY_BY_DEFAULT = True


# ---- Config Editor: curated (but editable) dropdown choices ----
# None of these lists need to be exhaustive or 100% exact - every combobox
# built from one is editable, so a missing/wrong entry is just a typing
# exercise for the person filling in the config, not a dead end.

# ---- Batch export: default custom segment-statistics metrics ----
# Comma-separated in the Config Editor; "percentile_<N>" is a plain metric
# name here too, not a separate field - see BatchProcessor._compute_metric()
# in study/batch_processor.py.
DEFAULT_STATS_METRICS = ["volume", "min", "max", "mean", "median", "std",
                          "percentile_5", "percentile_25", "percentile_75", "percentile_95"]


# Shown by every optional dropdown in the Config Editor for "nothing chosen" (never a blank entry).
UNSET = "(unset)"

# Point glyph shapes of Slicer's markups display (vtkMRMLMarkupsDisplayNode glyph type names).
# Sphere3D is a real 3D ball: cut by each slice plane, it shows across several neighbouring
# slices (as a shrinking circle), especially with the size given in mm.
MARKUPS_GLYPH_CHOICES = [UNSET, "Sphere3D", "Vertex2D", "Circle2D", "Cross2D", "ThickCross2D",
                         "Diamond2D", "Square2D", "Triangle2D", "StarBurst2D"]

ROLE_CHOICES = ["(none)", "background", "label", "foreground"]
TYPE_CHOICES = ["volume", "labelmap"]
SOURCE_CHOICES = ["file", "empty"]
OVERWRITE_CHOICES = ["none", "all_segments", "visible_segments"]
BRUSH_SHAPE_CHOICES = ["(unset)", "sphere", "circle"]

COLOR_TABLE_CHOICES = [
    UNSET, "Grey", "Rainbow", "Random", "Labels", "GenericAnatomyColors",
    "Warm1", "Warm2", "Warm3", "Cool1", "Cool2", "Cool3",
    "PET-Heat", "PET-Rainbow", "PET-MaximumIntensityProjection", "PET-DICOM",
    "vtkMRMLColorTableNodeRed", "vtkMRMLColorTableNodeGreen", "vtkMRMLColorTableNodeBlue",
    "vtkMRMLColorTableNodeYellow", "vtkMRMLColorTableNodeCyan", "vtkMRMLColorTableNodeMagenta",
]

VR_PRESET_CHOICES = [
    UNSET, "CT-AAA", "CT-AAA2", "CT-Air", "CT-Bone", "CT-Bones", "CT-Cardiac", "CT-Cardiac2", "CT-Cardiac3",
    "CT-Chest-Contrast-Enhanced", "CT-Chest-Vessels", "CT-Coronary-Arteries", "CT-Coronary-Arteries-2",
    "CT-Coronary-Arteries-3", "CT-Cropped-Volume-Bone", "CT-Fat", "CT-Liver-Vasculature", "CT-Lung",
    "CT-MIP", "CT-Muscle", "CT-Pulmonary-Arteries", "CT-Soft-Tissue", "CT-Air",
    "MR-Angio", "MR-Default", "MR-MIP", "MR-T2-Brain",
]

# Curated but not guaranteed-exhaustive/exact Slicer/VTK enum constant names -
# see GenericSpecimen._resolve_enum()'s docstring for how a wrong/unknown
# name here is handled at runtime (skipped with a warning, not a crash).
# Segment Editor effects that can be pre-selected on load (the internal effect names Slicer's
# SetActiveEffectName() takes). The dropdown is editable, so a custom/extension effect can be typed.
SEGMENT_EDITOR_EFFECT_CHOICES = [
    UNSET, "Paint", "Draw", "Erase", "LevelTracing", "GrowFromSeeds", "FillBetweenSlices", "Threshold",
    "Margin", "Hollow", "Smoothing", "Scissors", "Islands", "LogicalOperators", "MaskVolume", "SurfaceCut",
    "SplitVolume", "FloodFilling", "LocalThreshold", "WrapSolidify",
]

CROSSHAIR_MODE_CHOICES = [
    "(unset)", "NoCrosshair", "ShowBasic", "ShowIntersection", "ShowHashmarks",
    "ShowAll", "ShowSmallBasic", "ShowSmallIntersection",
]
CROSSHAIR_BEHAVIOR_CHOICES = [
    "(unset)", "Normal", "Offset", "JumpSlice", "OffsetJumpSlice", "CenteredJumpSlice",
]
CROSSHAIR_THICKNESS_CHOICES = ["(unset)", "Fine", "Medium", "Thick"]
RULER_TYPE_CHOICES = ["(unset)", "None", "Thin", "Thick"]
ORIENTATION_MARKER_TYPE_CHOICES = ["(unset)", "None", "Cube", "Human", "Axes"]
ORIENTATION_MARKER_SIZE_CHOICES = ["(unset)", "Small", "Medium", "Large"]
