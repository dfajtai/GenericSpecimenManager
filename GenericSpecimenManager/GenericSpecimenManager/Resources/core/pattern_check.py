"""
pattern_check.py
================
Pure-Python (no Slicer/VTK) validation of everything in a StudyConfig that is a *pattern*: the
`{column}` path/file-name patterns. Run at Initialize Study, against the real CSV headers, so a
typo'd column or broken braces are reported in plain words up front instead of failing halfway
through loading a specimen.
"""

import re
import string
from typing import List, Optional, Set, Tuple

# Placeholders that are not CSV columns, per kind of pattern.
IMAGE_SPECIALS = {"name"}
SEGMENT_SPECIALS = {"segment_name"}
MARKUPS_SPECIALS = {"label"}
REPORT_SPECIALS = {"date", "time", "datetime", "index"}


def placeholders(pattern: str) -> List[str]:
    """The `{field}` names used in a format-string pattern (base name only: `{a.b}`/`{a[0]}` -> `a`). Raises ValueError if the pattern is malformed (unbalanced braces...)."""
    names = []
    for _literal, field, _spec, _conv in string.Formatter().parse(pattern):
        if field is not None and field != "":
            names.append(re.split(r"[.\[]", field, maxsplit=1)[0])
    return names


def check_config_patterns(cfg, columns: Set[str]) -> Tuple[List[str], List[str]]:
    """Check every pattern in `cfg` against `columns` (all key/database/preseg column names). Returns (errors, warnings): errors are certain to fail at load time (broken braces, unknown column in output_dir_pattern - it's used for every specimen); warnings are patterns that MAY fail (an unknown column in a path pattern only matters if that pattern is actually used)."""
    errors: List[str] = []
    warnings: List[str] = []
    columns = set(columns)

    def check(pattern: Optional[str], where: str, specials: Set[str], fatal: bool = False):
        """Validate one format-string pattern: malformed -> error; unknown placeholder -> error if `fatal` else warning."""
        if not pattern:
            return
        try:
            names = placeholders(pattern)
        except ValueError as e:
            errors.append(f"{where}: '{pattern}' is not a valid pattern ({e})")
            return
        unknown = sorted({n for n in names if n not in columns and n not in specials})
        if unknown:
            msg = f"{where}: '{pattern}' uses {', '.join('{' + u + '}' for u in unknown)}, which is not a column of the CSVs"
            (errors if fatal else warnings).append(msg)

    check(cfg.output_dir_pattern, "output_dir_pattern", set(), fatal=True)
    check(cfg.defaults.image.path_pattern, "defaults.image.path_pattern", IMAGE_SPECIALS)

    seen_names = set()
    default_pattern = cfg.defaults.image.path_pattern
    for i, img in enumerate(cfg.images):
        if not img.name:
            continue   # nameless entries are skipped silently at load time
        label = f"images[{i}] '{img.name}'"
        check(img.path_pattern, f"{label} path_pattern", IMAGE_SPECIALS)
        if img.csv_column and img.csv_column not in columns and not (img.path_pattern or default_pattern):
            warnings.append(f"{label}: csv_column '{img.csv_column}' is not a preseg column, and there is no path_pattern to fall back to")
        if img.name in seen_names:
            warnings.append(f"image name '{img.name}' is listed more than once - the repeats are skipped")
        seen_names.add(img.name)

    seg = cfg.segmentation
    check(seg.path_pattern, "segmentation.path_pattern", SEGMENT_SPECIALS)
    for i, s in enumerate(seg.segments):
        check(s.path_pattern, f"segmentation.segments[{i}] path_pattern", SEGMENT_SPECIALS)
    check(cfg.markups.path_pattern, "markups.path_pattern", MARKUPS_SPECIALS)

    be = cfg.batch_export
    check(be.output_dir_pattern, "batch_export.output_dir_pattern", set())
    check(be.stats_output_path, "batch_export.stats_output_path", REPORT_SPECIALS)
    check(be.markups_output_path, "batch_export.markups_output_path", REPORT_SPECIALS)
    return errors, warnings
