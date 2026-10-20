"""Tests for the pure-logic parts of Resources/utils/ (Slicer, Qt and VTK are stubbed out - see test_imports.py).
Run: python -m unittest discover -s tests"""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "GenericSpecimenManager", "GenericSpecimenManager"))


class _StubModule(types.ModuleType):
    """A module whose every attribute is a fresh dummy class."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = type(name, (), {"__init__": lambda self, *a, **k: None})
        setattr(self, name, cls)
        return cls


for _name in ("slicer", "qt", "vtk", "ctk"):
    sys.modules.setdefault(_name, _StubModule(_name))

from Resources.core.config_model import SegmentEditorConfig  # noqa: E402
from Resources.utils.segment_editor import camel_to_label, camel_to_snake, editor_attributes  # noqa: E402
from Resources.utils.volume_rendering import offset_transfer_function, remap_transfer_function  # noqa: E402


class FakeOpacityFunction:
    """Just enough of a vtkPiecewiseFunction: nodes are [x, y, midpoint, sharpness]."""

    def __init__(self, nodes):
        self.nodes = [list(n) for n in nodes]

    def GetSize(self):
        return len(self.nodes)

    def GetNodeValue(self, i, out):
        out[:] = self.nodes[i]

    def RemoveAllPoints(self):
        self.nodes = []

    def AddPoint(self, *values):
        self.nodes.append(list(values))

    def Modified(self):
        pass


class EditorAttributesTest(unittest.TestCase):
    def test_absolute_sphere_brush(self):
        cfg = SegmentEditorConfig.from_dict({"brush": {"shape": "sphere", "diameter_mm": 20}})
        self.assertEqual(editor_attributes(cfg), {"BrushSphere": "1", "BrushDiameterIsRelative": "0", "BrushAbsoluteDiameter": "20"})

    def test_relative_circle_brush(self):
        cfg = SegmentEditorConfig.from_dict({"brush": {"shape": "circle", "diameter_mm": 5, "relative": True}})
        self.assertEqual(editor_attributes(cfg), {"BrushSphere": "0", "BrushDiameterIsRelative": "1", "BrushRelativeDiameter": "5"})

    def test_raw_attributes_come_last_and_win(self):
        cfg = SegmentEditorConfig.from_dict({"brush": {"shape": "sphere"}, "attributes": {"BrushSphere": "0", "Paint.ColorSmudge": 1}})
        attrs = editor_attributes(cfg)
        self.assertEqual(attrs["BrushSphere"], "0")
        self.assertEqual(attrs["Paint.ColorSmudge"], "1")

    def test_empty_config_sets_nothing(self):
        self.assertEqual(editor_attributes(SegmentEditorConfig.from_dict({})), {})


class TransferFunctionTest(unittest.TestCase):
    def test_offset_moves_only_x(self):
        func = FakeOpacityFunction([[0, 0.0, 0.5, 0.0], [100, 1.0, 0.5, 0.0]])
        offset_transfer_function(func, 50)
        self.assertEqual(func.nodes, [[50, 0.0, 0.5, 0.0], [150, 1.0, 0.5, 0.0]])

    def test_remap_keeps_relative_shape(self):
        func = FakeOpacityFunction([[0, 0.0, 0.5, 0.0], [50, 0.5, 0.5, 0.0], [100, 1.0, 0.5, 0.0]])
        remap_transfer_function(func, -100, 300)
        self.assertEqual([n[0] for n in func.nodes], [-100, 100, 300])
        self.assertEqual([n[1] for n in func.nodes], [0.0, 0.5, 1.0])

    def test_remap_of_an_empty_function_is_a_no_op(self):
        func = FakeOpacityFunction([])
        remap_transfer_function(func, 0, 1)
        self.assertEqual(func.nodes, [])


class CamelCaseTest(unittest.TestCase):
    """Slicer's CamelCase mode names -> config value and GUI label."""

    def test_snake(self):
        self.assertEqual(camel_to_snake("Everywhere"), "everywhere")
        self.assertEqual(camel_to_snake("InsideAllSegments"), "inside_all_segments")
        self.assertEqual(camel_to_snake("OutsideVisibleSegments"), "outside_visible_segments")

    def test_label(self):
        self.assertEqual(camel_to_label("Everywhere"), "Everywhere")
        self.assertEqual(camel_to_label("InsideVisibleSegments"), "Inside visible segments")


class ColormapTest(unittest.TestCase):
    """The built-in colour maps (core/colormaps.py)."""

    def test_gnuplot2_goes_from_black_to_white(self):
        from Resources.core.colormaps import colormap_rgb
        rgb = colormap_rgb("gnuplot2", 256)
        self.assertEqual(len(rgb), 256)
        self.assertEqual(rgb[0], (0.0, 0.0, 0.0))
        self.assertEqual(rgb[-1], (1.0, 1.0, 1.0))

    def test_inferno_starts_almost_black_and_values_are_valid(self):
        from Resources.core.colormaps import colormap_rgb
        rgb = colormap_rgb("inferno", 256)
        self.assertLess(max(rgb[0]), 0.02)
        self.assertTrue(all(0.0 <= c <= 1.0 for color in rgb for c in color))

    def test_unknown_name(self):
        from Resources.core.colormaps import colormap_rgb
        self.assertIsNone(colormap_rgb("nope"))


class ColumnLabelTest(unittest.TestCase):
    """database.csv column names as readable table headers."""

    def test_labels(self):
        from Resources.core.naming import column_label
        self.assertEqual(column_label("batch_id"), "Batch id")
        self.assertEqual(column_label("specimenID"), "Specimen ID")
        self.assertEqual(column_label("sampleName"), "Sample name")
        self.assertEqual(column_label("ID"), "ID")
        self.assertEqual(column_label("done"), "Done")
        self.assertEqual(column_label("left-femur length"), "Left femur length")


class MoveTargetTest(unittest.TestCase):
    """The Config Editor's Move up/down rule (images and segments tables)."""

    def test_middle_row_can_move_both_ways(self):
        from Resources.gui.config_editor.helpers import move_target
        self.assertEqual(move_target(1, -1, 3), 0)
        self.assertEqual(move_target(1, +1, 3), 2)

    def test_first_and_last_row_are_blocked(self):
        from Resources.gui.config_editor.helpers import move_target
        self.assertIsNone(move_target(0, -1, 3))
        self.assertIsNone(move_target(2, +1, 3))

    def test_nothing_selected_or_empty_table(self):
        from Resources.gui.config_editor.helpers import move_target
        self.assertIsNone(move_target(-1, +1, 3))
        self.assertIsNone(move_target(0, +1, 0))
        self.assertIsNone(move_target(0, -1, 1))
        self.assertIsNone(move_target(0, +1, 1))


if __name__ == "__main__":
    unittest.main()
