"""Tests for Resources/safe_io.py (pure Python - no Slicer needed). Run: python -m unittest discover tests"""

import os
import socket
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "GenericSpecimenManager", "GenericSpecimenManager"))
from Resources.core import safe_io  # noqa: E402


def _read(path):
    """The whole text of a file."""
    with open(path) as f:
        return f.read()


def _write(text):
    """A writer for atomic_write that puts `text` in the temp file."""
    def write(path):
        with open(path, "w") as f:
            f.write(text)
    return write


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "database.csv")

    def test_replaces_content_and_leaves_no_temp(self):
        with open(self.path, "w") as f:
            f.write("old")
        safe_io.atomic_write(self.path, _write("new"))
        self.assertEqual(_read(self.path), "new")
        self.assertEqual(os.listdir(self.dir), ["database.csv"])

    def test_temp_keeps_the_extension(self):
        self.assertTrue(safe_io.temp_path_for("/x/segment.seg.nrrd").endswith("segment.seg.nrrd"))

    def test_failed_write_keeps_the_original(self):
        with open(self.path, "w") as f:
            f.write("old")

        def boom(tmp):
            with open(tmp, "w") as f:
                f.write("half")
            raise RuntimeError("disk full")

        with self.assertRaises(RuntimeError):
            safe_io.atomic_write(self.path, boom)
        self.assertEqual(_read(self.path), "old")
        self.assertEqual(os.listdir(self.dir), ["database.csv"])

    def test_rejected_by_verify_keeps_the_original(self):
        with open(self.path, "w") as f:
            f.write("old")

        def reject(tmp):
            raise ValueError("wrong row count")

        with self.assertRaises(ValueError):
            safe_io.atomic_write(self.path, _write("new"), verify=reject)
        self.assertEqual(_read(self.path), "old")

    def test_empty_output_is_refused(self):
        with open(self.path, "w") as f:
            f.write("old")
        with self.assertRaises(IOError):
            safe_io.atomic_write(self.path, _write(""))
        self.assertEqual(_read(self.path), "old")

    def test_keep_previous(self):
        with open(self.path, "w") as f:
            f.write("v1")
        safe_io.atomic_write(self.path, _write("v2"), keep_previous=True)
        self.assertEqual(_read(self.path), "v2")
        self.assertEqual(_read(self.path + ".prev"), "v1")


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "database.csv")
        with open(self.path, "w") as f:
            f.write("data")

    def test_prunes_to_newest_n(self):
        for i in range(6):
            safe_io.backup_file(self.path, keep=3, now=1_000_000 + i * 10)
        backups = safe_io.list_backups(self.path)
        self.assertEqual(len(backups), 3)
        self.assertTrue(backups[0] > backups[-1])   # newest first

    def test_min_interval_throttles(self):
        self.assertIsNotNone(safe_io.backup_file(self.path, keep=5, min_interval_seconds=300, now=2_000_000))
        self.assertIsNone(safe_io.backup_file(self.path, keep=5, min_interval_seconds=300, now=2_000_100))
        self.assertIsNotNone(safe_io.backup_file(self.path, keep=5, min_interval_seconds=300, now=2_000_400))

    def test_missing_file_is_skipped(self):
        self.assertIsNone(safe_io.backup_file(os.path.join(self.dir, "nope.csv"), keep=3))


class SignatureTest(unittest.TestCase):
    def test_detects_a_change(self):
        path = os.path.join(tempfile.mkdtemp(), "database.csv")
        with open(path, "w") as f:
            f.write("a")
        first = safe_io.file_signature(path)
        self.assertEqual(first, safe_io.file_signature(path))
        with open(path, "w") as f:
            f.write("b")
        self.assertNotEqual(first, safe_io.file_signature(path))

    def test_missing_file_has_no_signature(self):
        self.assertIsNone(safe_io.file_signature("/no/such/file.csv"))


class LockTest(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "database.csv")

    def _foreign_lock(self, **overrides):
        info = {"user": "anna", "host": "other-machine", "pid": 1, "started": time.time(), "touched": time.time()}
        info.update(overrides)
        import json
        with open(safe_io.lock_path_for(self.path), "w") as f:
            json.dump(info, f)

    def test_our_own_lock_is_not_foreign(self):
        safe_io.acquire_lock(self.path)
        self.assertIsNone(safe_io.foreign_lock(self.path, stale_after_hours=12))

    def test_other_hosts_fresh_lock_is_foreign(self):
        self._foreign_lock()
        self.assertEqual(safe_io.foreign_lock(self.path, 12)["user"], "anna")

    def test_old_lock_is_stale(self):
        self._foreign_lock(touched=time.time() - 13 * 3600)
        self.assertIsNone(safe_io.foreign_lock(self.path, 12))

    def test_dead_process_on_this_machine_is_stale(self):
        self._foreign_lock(host=socket.gethostname(), pid=2_000_000_000)
        self.assertIsNone(safe_io.foreign_lock(self.path, 12))

    def test_release_removes_only_our_lock(self):
        safe_io.acquire_lock(self.path)
        safe_io.release_lock(self.path)
        self.assertFalse(os.path.exists(safe_io.lock_path_for(self.path)))
        self._foreign_lock()
        safe_io.release_lock(self.path)
        self.assertTrue(os.path.exists(safe_io.lock_path_for(self.path)))


if __name__ == "__main__":
    unittest.main()
