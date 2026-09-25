"""
volume_rendering.py
===================
Volume rendering of a specimen's images: presets, min/max remap and fixed shift of the transfer functions. These
functions manipulate Slicer itself - they take the config entries and nodes as arguments and hold no specimen state.
"""

import slicer

from Resources.core.logging_setup import logger
from Resources.utils.workspace import apply_orientation_marker


def start_volume_rendering(vr_entries, image_nodes, workspace_cfg, markups_node, display_nodes, roi_nodes):
    """Create one volume rendering display node per enabled entry in vr_entries (each with its own preset + optional range shift), then set up the 3D view/camera/orientation-marker and active markups list once, after the whole batch - not per image. `image_nodes` maps image name -> loaded node; the created display and ROI nodes are appended to `display_nodes` / `roi_nodes` as they are made (so the caller can clean them up even if a later entry fails)."""
    logic = slicer.modules.volumerendering.logic()
    any_added = False

    for vr_entry in vr_entries:
        src_node = image_nodes.get(vr_entry.image)
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

        apply_volume_rendering_shift(displayNode, vr_entry)

        display_nodes.append(displayNode)
        roiNode = displayNode.GetROINode()
        if not roiNode:
            displayNode.CreateDefaultROI()
            roiNode = displayNode.GetROINode()
        roi_nodes.append(roiNode)
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
            apply_orientation_marker(viewNode, workspace_cfg.orientation_marker_3d_type, workspace_cfg.orientation_marker_3d_size,
                                     default_type="OrientationMarkerTypeAxes", default_size="OrientationMarkerSizeLarge")
            viewNode.SetBoxVisible(False)
        threeDView.resetFocalPoint()
        threeDView.resetCamera()
    if markups_node is not None:
        selectionNode = slicer.app.applicationLogic().GetSelectionNode()
        selectionNode.SetReferenceActivePlaceNodeID(markups_node.GetID())
        slicer.modules.markups.logic().SetActiveListID(markups_node)


def apply_volume_rendering_shift(displayNode, vr_entry):
    """Shift a (usually preset-derived) volume rendering transfer function.
    Two independent mechanisms, checked in this order:

    1. `offset` - a fixed shift (every control point moves by the same
       amount, spacing/shape untouched) - the classic "Shift" slider
       behavior, matching the community 'shiftVolumeRendering' script
       (https://gist.github.com/cpinter/8a1f71c7eb3ef0ebcaa6c1be6e1c9d4a#file-setpresetoffest-py).
       Wins if both offset and window_level are set.
    2. `window_level` - a full rescale into an explicit [min, max] range
       (or a window/level pair converted to one), via
       remap_transfer_function() - control-point remapping, NOT a
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
            offset_transfer_function(opacity, vr_entry.offset)
            offset_transfer_function(color, vr_entry.offset)
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
        remap_transfer_function(opacity, new_range[0], new_range[1])
        remap_transfer_function(color, new_range[0], new_range[1])
    except Exception as e:
        logger.warning(f"[GenericSpecimen] could not shift volume rendering range for '{image_name}': {e}")


def offset_transfer_function(func, offset):
    """Shift every control point's x value by a fixed amount, leaving
    spacing/shape/y-values untouched - the exact GetNodeValue() ->
    modify x -> RemoveAllPoints()+AddPoint()/AddRGBPoint() technique
    from the community 'shiftVolumeRendering' script (see
    remap_transfer_function() below for the full-rescale variant and
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


def remap_transfer_function(func, new_min, new_max):
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
