"""
LoggingSetup.py
================
One shared logger ("GenericSpecimenManager"), used by every file in this
module instead of bare print(). Terminal output looks exactly like plain
print() did before (just the message itself, no extra noise).

To ALSO write everything to a log file (with timestamps), alongside the
terminal - handy when troubleshooting something after the fact, or a crash
that scrolled the terminal away - flip DEBUG_LOG_TO_FILE below to True.
Hardcoded on purpose, for a quick, obvious one-line edit; no config file or
GUI toggle needed.
"""
import logging
import os

DEBUG_LOG_TO_FILE = False   # flip to True to also log to LOG_FILE_PATH, with timestamps
LOG_FILE_PATH = os.path.join(os.path.expanduser("~"), "GenericSpecimenManager.log")

logger = logging.getLogger("GenericSpecimenManager")
logger.setLevel(logging.DEBUG)
logger.propagate = False   # don't also hand lines up to the root logger - avoids duplicate lines in Slicer's own log

if not logger.handlers:   # guard against duplicate handlers if this module gets reloaded (Slicer's "Reload" button)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(console_handler)

    if DEBUG_LOG_TO_FILE:
        try:
            file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            logger.addHandler(file_handler)
            logger.info(f"[LoggingSetup] also logging to file: {LOG_FILE_PATH}")
        except Exception as e:
            logger.warning(f"[LoggingSetup] could not open log file '{LOG_FILE_PATH}', file logging disabled: {e}")
