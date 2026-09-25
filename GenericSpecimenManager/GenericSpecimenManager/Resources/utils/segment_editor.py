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

import slicer

from Resources.core.logging_setup import logger


def overwrite_value(overwrite_mode):
    """The vtkMRMLSegmentEditorNode overwrite-mode constant for a config value ('none' | 'all_segments' | 'visible_segments'; unset/unknown -> none)."""
    node_class = slicer.vtkMRMLSegmentEditorNode
    return {
        "none": node_class.OverwriteNone,
        "all_segments": node_class.OverwriteAllSegments,
        "visible_segments": node_class.OverwriteVisibleSegments,
    }.get(overwrite_mode or "none", node_class.OverwriteNone)


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
    attrs = editor_attributes(se_cfg)

    def _apply_common(node):
        """Safe on ANY node, including a bare template with no context:
        overwrite mode and plain data attributes never trigger live
        widget/effect behaviour by themselves."""
        node.SetOverwriteMode(overwrite)
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

    logger.info(f"[GenericSpecimenManager] segment editor defaults applied: overwrite={overwrite}, attrs={attrs}, "
                f"active_effect_requested={se_cfg.active_effect}, patched_existing_node={existing_node is not None}")


def activate_segment_editor(se_cfg, segmentation_node, reference_node=None):
    """Switch to the Segment Editor module with the given segmentation
    already selected and configured. Safe (unlike touching a bare template
    node) because we explicitly attach a real segmentation/source volume
    to the widget's node BEFORE activating any effect on it - activating
    an effect with no segmentation/volume context is what crashed before.
    """
    if segmentation_node is None:
        return

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

    editorNode.SetOverwriteMode(overwrite_value(se_cfg.overwrite_mode))
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

    # Bring the module into view LAST, once everything above is already
    # configured, so the user never sees an unconfigured flash of it.
    slicer.util.selectModule("SegmentEditor")
