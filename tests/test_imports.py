"""Import smoke test: every module of the package can be imported (no Slicer needed - slicer/qt/vtk/ctk are
replaced by stubs). Catches broken imports, import cycles and top-level NameErrors after moving code around.
Run: python -m unittest discover -s tests"""

import importlib
import os
import pkgutil
import sys
import types
import unittest

MODULE_DIR = os.path.join(os.path.dirname(__file__), "..", "GenericSpecimenManager", "GenericSpecimenManager")
sys.path.insert(0, MODULE_DIR)


class _StubModule(types.ModuleType):
    """A module whose every attribute is a fresh dummy class (usable as a base class, callable, subscriptable)."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = type(name, (), {"__init__": lambda self, *a, **k: None})
        setattr(self, name, cls)
        return cls


def _install_stubs():
    for name in ("slicer", "qt", "vtk", "ctk"):
        sys.modules[name] = _StubModule(name)
    slicer = sys.modules["slicer"]
    for sub in ("slicer.util", "slicer.ScriptedLoadableModule"):
        stub = _StubModule(sub)
        sys.modules[sub] = stub
        setattr(slicer, sub.split(".")[1], stub)
    # the main module does `from slicer.ScriptedLoadableModule import *`
    names = ["ScriptedLoadableModule", "ScriptedLoadableModuleWidget", "ScriptedLoadableModuleLogic", "ScriptedLoadableModuleTest"]
    for name in names:
        getattr(sys.modules["slicer.ScriptedLoadableModule"], name)
    sys.modules["slicer.ScriptedLoadableModule"].__all__ = names


class ImportTest(unittest.TestCase):
    def test_every_module_imports(self):
        _install_stubs()
        import Resources
        failures = []
        for info in pkgutil.walk_packages(Resources.__path__, "Resources."):
            try:
                importlib.import_module(info.name)
            except Exception as e:   # noqa: BLE001 - report every broken module, not just the first
                failures.append(f"{info.name}: {type(e).__name__}: {e}")
        self.assertEqual(failures, [])

    def test_main_module_imports(self):
        _install_stubs()
        module = importlib.import_module("GenericSpecimenManager")
        self.assertTrue(hasattr(module, "GenericSpecimenManagerWidget"))


if __name__ == "__main__":
    unittest.main()
