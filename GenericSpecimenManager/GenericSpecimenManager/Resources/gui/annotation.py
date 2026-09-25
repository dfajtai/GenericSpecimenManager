"""
annotation.py
=============
The optional on-screen specimen annotation (ID, table values, status) in the slice and 3D views.
"""

import slicer
import vtk

from Resources.core.logging_setup import logger
from Resources.definitions import (
    SPECIMEN_ANNOTATION_BG_COLOR,
    SPECIMEN_ANNOTATION_BG_OPACITY,
    SPECIMEN_ANNOTATION_BG_PADDING,
    SPECIMEN_ANNOTATION_COLOR,
    SPECIMEN_ANNOTATION_FONT_SIZE,
    SPECIMEN_STATUS_LABELS,
)


class AnnotationMixin:
    """Specimen annotation drawing (mixed into GenericSpecimenManagerWidgetBase)."""

    def _clearSpecimenAnnotation(self):
        """Remove the yellow specimen-data text actors from every view."""
        for view, renderer, actor in self._annotationActors:
            try:
                renderer.RemoveViewProp(actor)
                view.scheduleRender()
            except Exception:
                pass
        self._annotationActors = []

    def _refreshSpecimenAnnotation(self):
        """(Re)draw the active specimen's database row as yellow text, top-left, in the Red/
        Yellow/Green and 3D views - only if workspace.specimen_annotation is on and a specimen is
        loaded (otherwise just clears). Layout: the ID (key columns joined with '-'), a rule, one
        'column: value' line per remaining table_columns entry (status column excluded), a rule, then
        the status line.
        Own vtkTextActor (not the shared corner annotation) so DataProbe can't overwrite it."""
        self._clearSpecimenAnnotation()
        cfg = self.logic.cfg if self.logic else None
        if cfg is None or not cfg.workspace.specimen_annotation or not self.logic.hasActiveSpecimen:
            return
        sp = self.logic.active_specimen
        id_line = "-".join(str(v) for v in sp.key_values)
        kv_lines = [f"{col}: {sp.db_info.get(col, '')}" for col in cfg.table_columns
                    if col not in cfg.key_columns and col != cfg.status_column]
        status_line = SPECIMEN_STATUS_LABELS[sp.status]
        width = max(len(l) for l in [id_line, status_line] + kv_lines)
        rule = "-" * width
        lines = [id_line, rule] + (kv_lines + [rule] if kv_lines else []) + [status_line]
        text = "\n".join(lines)
        try:
            lm = slicer.app.layoutManager()
            views = [lm.sliceWidget(n).sliceView() for n in lm.sliceViewNames()]
            views.append(lm.threeDWidget(0).threeDView())
            for view in views:
                renderer = view.renderWindow().GetRenderers().GetFirstRenderer()
                actor = vtk.vtkTextActor()
                actor.SetInput(text)
                prop = actor.GetTextProperty()
                prop.SetColor(*SPECIMEN_ANNOTATION_COLOR)
                prop.SetFontSize(SPECIMEN_ANNOTATION_FONT_SIZE)
                prop.SetBackgroundColor(*SPECIMEN_ANNOTATION_BG_COLOR)
                prop.SetBackgroundOpacity(SPECIMEN_ANNOTATION_BG_OPACITY)
                if hasattr(prop, "SetBackgroundPadding"):   # VTK 9+
                    prop.SetBackgroundPadding(SPECIMEN_ANNOTATION_BG_PADDING)
                prop.SetVerticalJustificationToTop()
                actor.GetPositionCoordinate().SetCoordinateSystemToNormalizedViewport()
                actor.SetPosition(0.01, 0.98)
                renderer.AddViewProp(actor)
                self._annotationActors.append((view, renderer, actor))
                view.scheduleRender()
        except Exception as e:
            logger.warning(f"[GenericSpecimenManager] could not draw specimen annotation: {e}")
