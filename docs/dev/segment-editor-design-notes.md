# Segment Editor design notes

The story of how the Segment Editor integration ended up the way it is - kept as a record of what did **not** work.

This section is deliberately detailed because **it broke across several
iterations**, and the final, working solution isn't obvious. If this ever
needs touching again, re-read this first.

## Bug 1: wrong attribute-key format

The brush parameters (`BrushSphere`, `BrushAbsoluteDiameter`,
`BrushRelativeDiameter`, `BrushDiameterIsRelative`) are **common
(effect-independent) attributes** on `vtkMRMLSegmentEditorNode` - they have
**no effect prefix**. Only effect-specific settings use an
`EffectName.ParamName` form (e.g. `Paint.ColorSmudge`, a literal **dot**,
not a comma). A real node's attribute dump:

```
BrushAbsoluteDiameter: 25
BrushDiameterIsRelative: 1
BrushSphere: 0
Paint.ColorSmudge: 0
Threshold.MinimumThreshold: 69.75
```

For a while the code wrote `"Paint,BrushSphere"` / `"Paint.BrushSphere"` -
neither of which ever existed, so the config **had zero effect** on
anything, completely silently.

## Bug 2: `active_effect` on a "bare" (context-less) node

An earlier version registered the `vtkMRMLSegmentEditorNode` as a
class-level DEFAULT/template node (`AddDefaultNode`), and also set
`active_effect` on it. That node has no attached segmentation and no source
volume. When the real Segment Editor widget clones this template and tries
to immediately activate the effect with no context - **several effects
crash natively (no Python traceback at all)**. This caused a full Slicer
crash on module switch.

**Fix**: `active_effect` is **never** set on the bare default/template
node. It's only applied once the node actually has a segmentation attached
(`node.GetSegmentationNode() is not None`) - i.e. it's genuinely in use.

## Bug 3: redundant duplicate write → GUI freeze

An intermediate version called `effect.setParameter(...)` and
`effect.updateGUIFromMRML()` by hand, AFTER the node-attribute write, "just
to be safe". `SetAttribute()` ALREADY triggers the widget's own automatic
MRML→GUI sync (via the Modified event) - the extra manual call caused a
**nested, double GUI update** that, on an exception between a
`blockSignals(True)`/`(False)` pair, **permanently left the widget's
signals blocked** → every brush control froze in the GUI.

**Fix**: only ONE write path - `SetAttribute()` on the node, no manual
poking at the effect object.

## Bug 4: ordering - brush written BEFORE activation, not after

`SetActiveEffectName(...)` can itself run something like a
`setMRMLDefaults()` routine that **overwrites** the brush attributes with
its own factory defaults (e.g. a 3% relative brush size) - if the brush
write happened before this call, our config was immediately clobbered.

**Fix**: activate first, write brush attributes after - ours needs to be
the last (winning) write.

## The final, two-layer solution

1. **Once, at Study Init**
   (`configure_segment_editor_defaults()` in `utils/segment_editor.py`, called from `Logic.initializeStudy`):
   applies safe defaults - to the default/template node AND to any
   already-existing live node, but only sets `active_effect` if that live
   node already has a segmentation attached.
2. **Per specimen, on load**
   (`activate_segment_editor()` in `utils/segment_editor.py`, called by `GenericSpecimen.load`): via the Segment Editor
   widget, **first** set the segmentation + source volume (real context),
   **then** write brush attributes, **then** activate the effect (now
   safe), and **finally** switch to that module - so it appears
   automatically, already configured, every time a specimen loads.
