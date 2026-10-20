"""
color_tables.py
===============
Turns the module's built-in colour maps (core/colormaps.py) into Slicer colour table nodes, on demand.
"""

import slicer

from Resources.core.colormaps import colormap_rgb, colormap_names
from Resources.core.logging_setup import logger

COLOR_TABLE_ENTRIES = 256   # the usual size of a Slicer colour table (e.g. Grey)


def builtin_color_node(name):
    """The colour table node for one of the module's own colour maps (e.g. 'gnuplot2', 'inferno'), created in the scene the first time it is asked for and reused afterwards; None if `name` is not one of them. Values outside an image's threshold stay transparent via the image's own threshold setting, and both maps start (almost) black. Node creation follows the Slicer script repository's user colour table recipe but could not be run outside Slicer."""
    if name not in colormap_names():
        return None
    existing = slicer.mrmlScene.GetFirstNodeByName(name)
    if existing is not None and existing.IsA("vtkMRMLColorTableNode"):
        return existing
    rgb = colormap_rgb(name, COLOR_TABLE_ENTRIES)
    node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLColorTableNode", name)
    node.SetTypeToUser()
    node.SetNumberOfColors(COLOR_TABLE_ENTRIES)
    node.GetLookupTable().SetTableRange(0, COLOR_TABLE_ENTRIES - 1)
    for i, (r, g, b) in enumerate(rgb):
        node.SetColor(i, str(i), r, g, b, 1.0)
    node.SetNamesInitialised(True)
    node.SetHideFromEditors(False)
    logger.info(f"[GenericSpecimenManager] created colour table '{name}'")
    return node
