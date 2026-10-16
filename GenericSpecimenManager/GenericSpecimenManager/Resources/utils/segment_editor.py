"""
segment_editor.py
=================
Configures Slicer's Segment Editor from the study config: study-wide defaults (applied once at Initialize Study)
and the hand-off of a freshly loaded specimen's segmentation. These functions manipulate Slicer itself - they take
the config section and nodes as arguments and hold no specimen state.

IMPORTANT: BrushSphere / BrushAbsoluteDiameter / BrushRelativeDiameter / BrushDiameterIsRelative are COMMON
parameters shared by Paint/Erase - they are stored as BARE attribute keys on vtkMRMLSegmentEditorNode, with NO
effect-name prefix (confirmed against a real node's printed Attributes on the Slicer forum). Only EFFECT-SPECIFIC
parameters use the "EffectName.ParamName" form (e.g. "Paint.ColorSmudge"). Earlier versions of this code prefixed
brush keys with "Paint," / "Paint." - that attribute never existed, so nothing ever applied.
"""

import re

import qt
import slicer
import vtk

from Resources.core.logging_setup import logger


_INTEGER_SCALAR_TYPES = ("VTK_CHAR", "VTK_SIGNED_CHAR", "VTK_UNSIGNED_CHAR", "VTK_SHORT", "VTK_UNSIGNED_SHORT",
                         "VTK_INT", "VTK_UNSIGNED_INT", "VTK_LONG", "VTK_UNSIGNED_LONG", "VTK_LONG_LONG",
                         "VTK_UNSIGNED_LONG_LONG", "VTK__INT64", "VTK_UNSIGNED__INT64")


def ensure_integer_labelmap(volume_node):
    """Make sure a label volume has an INTEGER voxel type before it becomes a segment. A float/double label image (some tools save masks as float) imports fine but its binary-labelmap representation cannot then be converted to a surface: 'Show 3D' only logs '[VTK] Convert: Source representation scalar type is not a valid integer type' and shows nothing. Casts in place to short (the voxel values of a mask are small whole numbers); returns True if a cast was needed."""
    image = volume_node.GetImageData()
    if image is None:
        return False
    integer_types = {getattr(vtk, n) for n in _INTEGER_SCALAR_TYPES if hasattr(vtk, n)}
    if image.GetScalarType() in integer_types:
        return False
    caster = vtk.vtkImageCast()
    caster.SetInputData(image)
    caster.SetOutputScalarTypeToShort()
    caster.ClampOverflowOn()
    caster.Update()
    volume_node.SetAndObserveImageData(caster.GetOutput())
    return True


def overwrite_value(overwrite_mode):
    """The vtkMRMLSegmentEditorNode overwrite-mode constant for a config value ('none' | 'all_segments' | 'visible_segments'; unknown -> none), or None when the value is unset - 'none' is a real choice (allow overlap) and must not be confused with 'not configured', which leaves Slicer's own setting alone."""
    if not overwrite_mode:
        return None
    node_class = slicer.vtkMRMLSegmentEditorNode
    return {
        "none": node_class.OverwriteNone,
        "all_segments": node_class.OverwriteAllSegments,
        "visible_segments": node_class.OverwriteVisibleSegments,
    }.get(overwrite_mode, node_class.OverwriteNone)


_MASK_PREFIX = "EditAllowed"
_UNSUPPORTED_MASK_MODES = ("InsideSingleSegment",)   # needs a segment ID, which a study-level config cannot know


def camel_to_snake(text):
    """'InsideAllSegments' -> 'inside_all_segments' (the form used for the config value)."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()


def camel_to_label(text):
    """'InsideAllSegments' -> 'Inside all segments' (first word capitalised, rest lower case - the wording of Slicer's own GUI)."""
    words = camel_to_snake(text).replace("_", " ")
    return words[:1].upper() + words[1:]


def mask_mode_names():
    """[(mode integer, name without the 'EditAllowed' prefix), ...] as Slicer itself reports them, e.g. (1, 'InsideAllSegments'). The EditAllowed* constants are not visible as Python attributes (dir() finds none), but the static vtkMRMLSegmentationNode.ConvertMaskModeToString(int) works (checked in Slicer 5.12: 0 -> 'EditAllowedEverywhere'), so the list is read from Slicer instead of hard-coded: a renamed or renumbered mode cannot silently pick the wrong one. Modes a config cannot express (_UNSUPPORTED_MASK_MODES) are left out."""
    modes = []
    for mode in range(16):   # there are only ~6 modes; stop at the first name that is not an EditAllowed one
        name = slicer.vtkMRMLSegmentationNode.ConvertMaskModeToString(mode)
        if not name or not str(name).startswith(_MASK_PREFIX):
            break
        suffix = str(name)[len(_MASK_PREFIX):]
        if suffix not in _UNSUPPORTED_MASK_MODES:
            modes.append((mode, suffix))
    return modes


def editable_area_choices():
    """{config value: GUI label} for the editable-area dropdown, built from Slicer's own mode names ('InsideAllSegments' -> {'inside_all_segments': 'Inside all segments'}); {} if this Slicer cannot report them."""
    try:
        return {camel_to_snake(suffix): camel_to_label(suffix) for _mode, suffix in mask_mode_names()}
    except Exception as e:
        logger.warning(f"[GenericSpecimenManager] could not read Slicer's editable-area modes: {e}")
        return {}


def editable_area_value(editable_area):
    """The mask-mode integer for a config value ('inside_all_segments'), or None when unset (leave Slicer's own setting alone) or unknown to this Slicer (warned). Callers must test `is None`: Everywhere is 0."""
    if not editable_area:
        return None
    modes = mask_mode_names()
    for mode, suffix in modes:
        if camel_to_snake(suffix) == editable_area:
            return mode
    logger.warning(f"[GenericSpecimenManager] segment_editor.editable_area '{editable_area}' is not supported by this Slicer, "
                   f"ignored (modes it knows: {[camel_to_snake(s) for _m, s in modes]})")
    return None


def editor_attributes(se_cfg):
    """The plain data attributes to set on a Segment Editor node: the brush settings (bare keys - see the module docstring) followed by the config's raw `attributes` escape hatch, all as strings."""
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
    return attrs


def configure_segment_editor_defaults(se_cfg):
    """Apply the segment_editor config ONCE, at study init, instead of on every
    specimen load. Brush/overwrite settings are study-level preferences,
    not per-specimen state, so there's no need to re-touch them on every
    load - and doing it here avoids the whole class of timing/singleton
    problems from poking a live, possibly-not-yet-constructed Segment
    Editor widget mid specimen-load.

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
    if not se_cfg.is_configured():
        return

    overwrite = overwrite_value(se_cfg.overwrite_mode)
    mask_mode = editable_area_value(se_cfg.editable_area)
    attrs = editor_attributes(se_cfg)

    def _apply_common(node):
        """Safe on ANY node, including a bare template with no context:
        overwrite mode and plain data attributes never trigger live
        widget/effect behaviour by themselves."""
        if overwrite is not None:
            node.SetOverwriteMode(overwrite)
        if mask_mode is not None:
            node.SetMaskMode(mask_mode)
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

    logger.info(f"[GenericSpecimenManager] segment editor defaults applied: overwrite={overwrite}, editable_area={mask_mode}, attrs={attrs}, "
                f"active_effect_requested={se_cfg.active_effect}, patched_existing_node={existing_node is not None}")


def _source_volume_of(editor_node):
    """The editor node's current source volume node (Slicer 5.2+: GetSourceVolumeNode, older: GetMasterVolumeNode), or None."""
    getter = getattr(editor_node, "GetSourceVolumeNode", None) or getattr(editor_node, "GetMasterVolumeNode", None)
    return getter() if getter else None


class SourceVolumeLayerKeeper:
    """Keeps the slice views' BACKGROUND where the study config put it when the user picks another source volume in the Segment Editor, and makes the FOREGROUND follow the source volume instead.

    Why: selecting a source volume makes Slicer put it into the slice views' background and switch the foreground off, so
    switching between e.g. two images to segment also swapped away the reference image the user was looking at. Here the
    background that was shown BEFORE the Segment Editor was set up is remembered; whenever the source volume changes it is
    put back, the new source goes to the foreground, and the foreground opacity is left as it was. When the source volume
    is the background itself (the usual reference image), the foreground that was shown before is put back instead.

    The restore is queued with a zero-delay timer, because Slicer changes the layers in response to the same change (possibly after
    our observer ran) - the timer lets that finish first. Behaviour in a live Slicer could not be tested from here."""

    def __init__(self, editor_node, background_id, foreground_id, foreground_opacity):
        """Observe `editor_node`; `background_id` / `foreground_id` / `foreground_opacity` are the layers to keep, taken before the source volume was first set."""
        self._node = editor_node
        self._kept = (background_id, foreground_id, foreground_opacity)
        source = _source_volume_of(editor_node)
        self._last_source_id = source.GetID() if source else None
        self._observer_tag = editor_node.AddObserver(vtk.vtkCommand.ModifiedEvent, self._onNodeModified)

    def stop(self):
        """Stop observing (specimen closed). Safe to call twice."""
        if self._observer_tag is not None:
            try:
                self._node.RemoveObserver(self._observer_tag)
            except Exception:
                pass
            self._observer_tag = None

    def _onNodeModified(self, _caller=None, _event=None):
        """The editor node changed (it does for many reasons): act only if the source volume really is a different one now."""
        source = _source_volume_of(self._node)
        source_id = source.GetID() if source else None
        if source_id == self._last_source_id:
            return
        self._last_source_id = source_id
        qt.QTimer.singleShot(0, self.restoreLayers)

    def restoreLayers(self):
        """Put the kept background back and the source volume into the foreground (or the kept foreground, if the source is the background itself)."""
        background_id, foreground_id, foreground_opacity = self._kept
        source = _source_volume_of(self._node)
        if source is None or not background_id:
            return
        background = slicer.mrmlScene.GetNodeByID(background_id)
        if background is None:
            return
        if source.GetID() == background_id:
            foreground = slicer.mrmlScene.GetNodeByID(foreground_id) if foreground_id else None
        else:
            foreground = source
        kwargs = {"background": background, "foreground": foreground}
        if foreground is not None and foreground_opacity:
            kwargs["foregroundOpacity"] = foreground_opacity
        slicer.util.setSliceViewerLayers(**kwargs)


def _current_slice_layers():
    """(background volume ID, foreground volume ID, foreground opacity) shown in the first slice view that has a background - the layers the study config set up."""
    for composite in slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode"):
        if composite.GetBackgroundVolumeID():
            return composite.GetBackgroundVolumeID(), composite.GetForegroundVolumeID(), composite.GetForegroundOpacity()
    return None, None, None


def activate_segment_editor(se_cfg, segmentation_node, reference_node=None):
    """Switch to the Segment Editor module with the given segmentation
    already selected and configured. Safe (unlike touching a bare template
    node) because we explicitly attach a real segmentation/source volume
    to the widget's node BEFORE activating any effect on it - activating
    an effect with no segmentation/volume context is what crashed before.
    """
    if segmentation_node is None:
        return

    layers = _current_slice_layers()   # BEFORE the source volume is set: Slicer then swaps the layers around

    try:
        segmentEditorWidget = slicer.modules.segmenteditor.widgetRepresentation().self().editor
    except Exception as e:
        logger.warning(f"[GenericSpecimen] could not access the Segment Editor widget: {e}")
        return

    segmentEditorWidget.setSegmentationNode(segmentation_node)

    if reference_node is not None:
        try:
            segmentEditorWidget.setSourceVolumeNode(reference_node)      # Slicer 5.2+
        except AttributeError:
            segmentEditorWidget.setMasterVolumeNode(reference_node)      # older Slicer

    editorNode = segmentEditorWidget.mrmlSegmentEditorNode()
    if editorNode is None:
        logger.warning("[GenericSpecimen] Segment Editor widget produced no live node, skipping")
        return

    overwrite = overwrite_value(se_cfg.overwrite_mode)
    if overwrite is not None:
        editorNode.SetOverwriteMode(overwrite)
    mask_mode = editable_area_value(se_cfg.editable_area)
    if mask_mode is not None:
        editorNode.SetMaskMode(mask_mode)
    for k, v in editor_attributes(se_cfg).items():
        editorNode.SetAttribute(k, v)

    # Safe now: editorNode has a real segmentation (and source volume, if
    # resolved) attached above - NOT a bare template. Deliberately not
    # touching the live effect object (no effect.setParameter(), no
    # manual updateGUIFromMRML()) - SetAttribute()/SetActiveEffectName()
    # already trigger the widget's own automatic MRML->GUI sync; calling
    # into the effect object again on top of that is what caused the
    # signal-blocking GUI freeze in an earlier version.
    if se_cfg.active_effect:
        editorNode.SetActiveEffectName(se_cfg.active_effect)

    keeper = SourceVolumeLayerKeeper(editorNode, *layers)
    keeper.restoreLayers()   # the first source volume (the reference image) also disturbed the layers

    # Bring the module into view LAST, once everything above is already
    # configured, so the user never sees an unconfigured flash of it.
    slicer.util.selectModule("SegmentEditor")
    return keeper
