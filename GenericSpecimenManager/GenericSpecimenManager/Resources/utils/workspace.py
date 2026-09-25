"""
workspace.py
============
Sets up the 3D Slicer workspace for a loaded specimen: layout, crosshair, window/level, slice rotation, ruler,
orientation markers and the L/R view convention. These functions manipulate Slicer itself - they take the
relevant config sections and nodes as arguments and hold no specimen state.
"""

import slicer
import vtk

from Resources.core.logging_setup import logger


def customize_workplace(cfg, segmentation_node=None):
    """Per-specimen workspace touch-ups: get-or-create (never replace - see the comment inline for why) the default Segment Editor node, link slice views, switch to the standard Four-Up layout, tune the crosshair, apply the blanket window/level if configured, and set every segment's 2D fill/outline opacity. `cfg` is the StudyConfig."""
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

    apply_workspace_settings(cfg.workspace)

    wl_cfg = cfg.window_level
    if wl_cfg.enabled:
        for v in slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeDisplayNode"):
            v.InterpolateOff()
            v.SetAutoWindowLevel(0)
            v.SetWindowLevelMinMax(wl_cfg.min if wl_cfg.min is not None else -150, wl_cfg.max if wl_cfg.max is not None else 700)

    if segmentation_node is not None:
        seg = segmentation_node.GetSegmentation()
        for seg_id in list(seg.GetSegmentIDs()):
            segmentation_node.GetDisplayNode().SetSegmentOpacity2DFill(seg_id, 0.85)
            segmentation_node.GetDisplayNode().SetSegmentOpacity2DOutline(seg_id, 1)

    apply_slice_rotation(cfg.slice_rotation)


def resolve_enum(obj, name, default=None):
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


def apply_workspace_settings(ws_cfg):
    """Apply the workspace config's crosshair mode/behavior/thickness (falling
    back to this module's long-standing defaults - ShowBasic /
    OffsetJumpSlice / Fine - so an absent 'workspace' section changes
    nothing), plus the purely opt-in ruler, 3D/2D orientation-marker,
    and L/R view convention settings."""
    crosshair = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLCrosshairNode")
    if crosshair:
        mode = resolve_enum(crosshair, ws_cfg.crosshair_mode, "ShowBasic")
        if mode is not None:
            crosshair.SetCrosshairMode(mode)
        behavior = resolve_enum(crosshair, ws_cfg.crosshair_behavior, "OffsetJumpSlice")
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
            ruler_value = resolve_enum(sliceNode, "RulerType" + ws_cfg.ruler_type)
            if ruler_value is not None:
                sliceNode.SetRulerType(ruler_value)

    if ws_cfg.orientation_marker_3d_type or ws_cfg.orientation_marker_3d_size:
        threeDWidget = layoutManager.threeDWidget(0)
        if threeDWidget:
            viewNode = threeDWidget.threeDView().mrmlViewNode()
            if viewNode:
                apply_orientation_marker(viewNode, ws_cfg.orientation_marker_3d_type, ws_cfg.orientation_marker_3d_size)

    if ws_cfg.orientation_marker_2d_type or ws_cfg.orientation_marker_2d_size:
        for color in ("Red", "Yellow", "Green"):
            sliceWidget = layoutManager.sliceWidget(color)
            if sliceWidget is None:
                continue
            sliceNode = sliceWidget.mrmlSliceNode()
            apply_orientation_marker(sliceNode, ws_cfg.orientation_marker_2d_type, ws_cfg.orientation_marker_2d_size)

    apply_view_convention(ws_cfg.view_convention)


def apply_view_convention(convention):
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


def apply_orientation_marker(viewNode, type_name=None, size_name=None, default_type=None, default_size=None):
    """Set a view node's orientation-marker type/size - works for BOTH
    the 3D view and a slice (2D) view, since vtkMRMLSliceNode inherits
    this property from the same vtkMRMLAbstractViewNode base class the
    3D view node uses. type_name/size_name are SHORT names (e.g.
    "Axes"/"Large") - this function adds the OrientationMarkerType/
    OrientationMarkerSize prefix itself. default_type/default_size
    (full constant names, e.g. "OrientationMarkerTypeAxes") are used
    only when type_name/size_name are unset - only volume rendering
    passes defaults (it always wants SOME 3D marker); everywhere else,
    unset just means leave alone."""
    full_type = ("OrientationMarkerType" + type_name) if type_name else default_type
    if full_type:
        v = resolve_enum(viewNode, full_type)
        if v is not None:
            viewNode.SetOrientationMarkerType(v)
    full_size = ("OrientationMarkerSize" + size_name) if size_name else default_size
    if full_size:
        v = resolve_enum(viewNode, full_size)
        if v is not None:
            viewNode.SetOrientationMarkerSize(v)


def apply_slice_rotation(rot_cfg):
    """Apply the slice_rotation config's per-view (Red/Yellow/Green) in-plane rotation, if enabled. No-op for any view whose angle is left unset (None)."""
    if not rot_cfg.enabled:
        return
    layoutManager = slicer.app.layoutManager()
    for color, angle_deg in (("Red", rot_cfg.red), ("Yellow", rot_cfg.yellow), ("Green", rot_cfg.green)):
        if angle_deg is None:
            continue
        sliceWidget = layoutManager.sliceWidget(color)
        if sliceWidget is None:
            continue
        rotate_slice_in_plane(sliceWidget.mrmlSliceNode(), angle_deg)


def rotate_slice_in_plane(sliceNode, angle_deg):
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
