"""
Definitions.py
================
Every hardcoded, easy-to-want-to-tweak constant in this module, in ONE
place - so a knob like HIDE_HELP_AND_ACKNOWLEDGEMENT doesn't need hunting
through a 1000+-line file/class body to find. If you're looking for
something to turn on/off or a list to extend, look here first.

Logging's own toggle (DEBUG_LOG_TO_FILE) lives in LoggingSetup.py instead -
it's genuinely logging-specific machinery, not a plain on/off switch, so it
stays next to the handler setup it configures.
"""

# ---- Developer-UI visibility (GenericSpecimenManagerWidgetBase) ----
# Flip either to False to show that section again. See GenericSpecimenEngine.py's
# setup()/enter()/exit() for where these are actually applied.
HIDE_RELOAD_AND_TEST = False
HIDE_HELP_AND_ACKNOWLEDGEMENT = True


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

ROLE_CHOICES = ["(none)", "background", "label", "foreground"]
TYPE_CHOICES = ["volume", "labelmap"]
SOURCE_CHOICES = ["file", "empty"]
OVERWRITE_CHOICES = ["none", "all_segments", "visible_segments"]
BRUSH_SHAPE_CHOICES = ["(unset)", "sphere", "circle"]

COLOR_TABLE_CHOICES = [
    "", "Grey", "Rainbow", "Random", "Labels", "GenericAnatomyColors",
    "Warm1", "Warm2", "Warm3", "Cool1", "Cool2", "Cool3",
    "PET-Heat", "PET-Rainbow", "PET-MaximumIntensityProjection", "PET-DICOM",
    "vtkMRMLColorTableNodeRed", "vtkMRMLColorTableNodeGreen", "vtkMRMLColorTableNodeBlue",
    "vtkMRMLColorTableNodeYellow", "vtkMRMLColorTableNodeCyan", "vtkMRMLColorTableNodeMagenta",
]

VR_PRESET_CHOICES = [
    "", "CT-AAA", "CT-AAA2", "CT-Air", "CT-Bone", "CT-Bones", "CT-Cardiac", "CT-Cardiac2", "CT-Cardiac3",
    "CT-Chest-Contrast-Enhanced", "CT-Chest-Vessels", "CT-Coronary-Arteries", "CT-Coronary-Arteries-2",
    "CT-Coronary-Arteries-3", "CT-Cropped-Volume-Bone", "CT-Fat", "CT-Liver-Vasculature", "CT-Lung",
    "CT-MIP", "CT-Muscle", "CT-Pulmonary-Arteries", "CT-Soft-Tissue", "CT-Air",
    "MR-Angio", "MR-Default", "MR-MIP", "MR-T2-Brain",
]

# Curated but not guaranteed-exhaustive/exact Slicer/VTK enum constant names -
# see GenericSpecimen._resolve_enum()'s docstring for how a wrong/unknown
# name here is handled at runtime (skipped with a warning, not a crash).
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
