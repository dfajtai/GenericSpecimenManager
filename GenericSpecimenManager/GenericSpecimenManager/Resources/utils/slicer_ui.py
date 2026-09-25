"""
slicer_ui.py
============
Small pieces of Slicer's own application UI that this module has to bend: the module panel's Help section and the
Ctrl+S shortcut. Both manipulate Slicer itself; they hold only their own bookkeeping.
"""

import qt
import slicer

from Resources.core.logging_setup import logger


def set_help_section_visible(visible):
    """Show/hide the module panel's Help & Acknowledgement section via slicer.util.setModuleHelpSectionVisible() - a module-panel-wide (not per-module) setting, hence toggled when the module is entered/left rather than once at setup. Defensively wrapped: an older Slicer build without this helper just leaves the section as-is instead of raising."""
    try:
        slicer.util.setModuleHelpSectionVisible(visible)
    except Exception as e:
        logger.warning(f"[GenericSpecimenManager] could not toggle the Help section (older Slicer build?): {e}")


class SaveShortcut:
    """A Ctrl+S shortcut that belongs to this module ONLY while it is active.

    Slicer's own Ctrl+S action (File > Save scene) collides with it - two owners of one key sequence make Qt
    refuse to pick either ("Ambiguous shortcut overload"). So while active, Slicer's own Ctrl+S action(s) have
    their shortcut cleared, and it is given back the moment the shortcut is deactivated (or disposed), so Save
    scene works as usual otherwise. Both the normal and the 'ambiguous' activation call `handler`."""

    KEY = "Ctrl+S"

    def __init__(self, handler):
        """Create the (initially inactive) shortcut on the main window; `handler()` runs when it fires."""
        self._displaced = []   # (QAction, QKeySequence) of Slicer's own Ctrl+S actions while we own the key
        self._shortcut = qt.QShortcut(qt.QKeySequence(self.KEY), slicer.util.mainWindow())
        self._shortcut.setContext(qt.Qt.ApplicationShortcut)
        self._shortcut.enabled = False
        self._shortcut.connect('activated()', handler)
        self._shortcut.connect('activatedAmbiguously()', handler)

    def set_active(self, active):
        """Take (True) or give back (False) the Ctrl+S key."""
        if self._shortcut is None:
            return
        self._shortcut.enabled = bool(active)
        if active and not self._displaced:
            for action in slicer.util.mainWindow().findChildren(qt.QAction):
                if action.shortcut.toString() == self.KEY:
                    self._displaced.append((action, action.shortcut))
                    action.setShortcut(qt.QKeySequence())
        elif not active:
            self._restore()

    def dispose(self):
        """Deactivate, give Slicer's shortcut back, and delete the shortcut object."""
        if self._shortcut is not None:
            self._shortcut.enabled = False
            self._shortcut.deleteLater()
            self._shortcut = None
        self._restore()

    def _restore(self):
        """Give Slicer's own Ctrl+S action(s) their shortcut back."""
        for action, sequence in self._displaced:
            action.setShortcut(sequence)
        self._displaced = []
