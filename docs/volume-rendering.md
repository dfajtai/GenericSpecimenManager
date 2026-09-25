# Volume Rendering - a per-image list + the correct VTK API

`volume_rendering` is a **list**, not a single object - any number of
images can be `enabled` at once, each with its own preset and an optional
min/max (or window/level) shift.

For the shift, **I searched before coding** - my first attempt would have
used a nonexistent `vtkPiecewiseFunction.AdjustRange()` /
`vtkColorTransferFunction.AdjustRange()` method (a plausible-sounding but
invented API). A real, community-verified Slicer script (the
"shiftVolumeRendering" gist) shows the actual, documented pattern:

```python
volProp = volumePropertyNode.GetVolumeProperty()
scalarOpacity = volProp.GetScalarOpacity()   # vtkPiecewiseFunction
# per control point: GetNodeValue() -> modify x -> RemoveAllPoints() + AddPoint()
```

`remap_transfer_function()` (in `utils/volume_rendering.py`) does the same thing, but
instead of a fixed offset (like the original gist), it linearly rescales
the control points into an **arbitrary target range** (preserving shape and
color/opacity values, only moving the x-position) - this works for both the
opacity (`vtkPiecewiseFunction`) and color (`vtkColorTransferFunction`)
transfer functions (the latter's write-back method is `AddRGBPoint`, with a
6-value node `[x,r,g,b,midpoint,sharpness]`, versus opacity's 4-value node
`[x,y,midpoint,sharpness]`).

Verified with a mocked test (`tests/test_utils.py`): control points originally spanning
`[-450..1000]` correctly shift/rescale into a new `[-200..800]` range, with
relative positions (fractions) and y/RGB values left unchanged.

Each entry also supports a plain `offset` (a fixed shift, no rescale - the
gist's original technique, via `offset_transfer_function()`) as an
alternative to `window_level`; if both are set, `offset` wins. Note: this
shifts the actual render correctly, but Slicer's own Volume Rendering
module's "Shift" slider won't reflect it - cosmetic only.
