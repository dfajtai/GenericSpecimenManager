"""
LoggingSetup.py
================
One shared logger ("GenericSpecimenManager"), used by every file in this
module instead of bare print(). Default level is DEBUG, so everything
shows in the terminal out of the box - the level split is:

  DEBUG    full itemized detail (e.g. every loaded/saved item, one row each)
  INFO     one short summary line per action (e.g. "loaded X: 5 items")
  WARNING  something skipped/unusual but not fatal
  ERROR    something actually went wrong

NOTE on color: Slicer's Python console is a Qt text widget, not a real
terminal - it does NOT interpret ANSI color escape codes, it just shows
them as raw, garbled text (`\x1b[33m...`). There is also no built-in,
reliable way (as of this writing) to get Slicer to color plain Python log
messages by level - this was a still-open Slicer feature request as of
Feb 2025 (discourse.slicer.org/t/different-colors-for-warnings-and-errors,
topic 41835). What we CAN do, and this does: split output by the standard
Python-logging convention - DEBUG/INFO to stdout, WARNING/ERROR/CRITICAL to
stderr. Some terminals/consoles style stderr differently on their own; if
yours doesn't, you still get correctly-leveled messages, just not colored -
better than broken escape-code garbage either way.

To ALSO write everything to a log file (with timestamps), alongside the
terminal, flip DEBUG_LOG_TO_FILE below to True. Hardcoded on purpose, for a
quick, obvious one-line edit; no config file or GUI toggle needed.
"""
import logging
import os
import sys

DEBUG_LOG_TO_FILE = False   # flip to True to also log to LOG_FILE_PATH, with timestamps
LOG_FILE_PATH = os.path.join(os.path.expanduser("~"), "GenericSpecimenManager.log")


class _MaxLevelFilter(logging.Filter):
    """Only let records AT OR BELOW max_level through - used to keep DEBUG/INFO off the stderr handler (which starts at WARNING) and, symmetrically, WARNING+ off the stdout one."""

    def __init__(self, max_level):
        super().__init__()
        self.max_level = max_level

    def filter(self, record):
        return record.levelno <= self.max_level


logger = logging.getLogger("GenericSpecimenManager")
logger.setLevel(logging.DEBUG)
logger.propagate = False   # don't also hand lines up to the root logger - avoids duplicate lines in Slicer's own log

if not logger.handlers:   # guard against duplicate handlers if this module gets reloaded (Slicer's "Reload" button)
    plain_formatter = logging.Formatter("%(message)s")

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.addFilter(_MaxLevelFilter(logging.INFO))
    stdout_handler.setFormatter(plain_formatter)
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(plain_formatter)
    logger.addHandler(stderr_handler)

    if DEBUG_LOG_TO_FILE:
        try:
            file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            logger.addHandler(file_handler)
            logger.info(f"[LoggingSetup] also logging to file: {LOG_FILE_PATH}")
        except Exception as e:
            logger.warning(f"[LoggingSetup] could not open log file '{LOG_FILE_PATH}', file logging disabled: {e}")


