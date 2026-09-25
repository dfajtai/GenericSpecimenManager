"""
safe_io.py
==========
Pure-Python (no Slicer/VTK) building blocks that keep the study's data from being damaged:

* atomic replacement of a file (write a temp file, verify, then swap it in in one step - an
  interrupted write never leaves a half-written file behind);
* time-stamped backups of a file, pruned to the newest N;
* a one-level "previous version" copy (`<file>.prev`);
* change detection: a signature of a file, to notice that it was changed on disk by someone/
  something else since we read it;
* a small advisory lock file saying who has a study open.

Nothing here knows about Slicer - study/logic.py and study/specimen.py plug the actual writers in.
"""

import getpass
import hashlib
import json
import os
import shutil
import socket
import time
from datetime import datetime
from typing import Callable, Optional

BACKUP_DIR_NAME = ".backups"
PREVIOUS_SUFFIX = ".prev"


# ---- atomic replacement --------------------------------------------------------------------

def temp_path_for(path: str) -> str:
    """A temp path next to `path` that keeps its full extension (Slicer picks the file writer by extension): <dir>/.tmp-<pid>-<name>."""
    directory, name = os.path.split(path)
    return os.path.join(directory, f".tmp-{os.getpid()}-{name}")


def atomic_write(path: str, write: Callable[[str], None], verify: Optional[Callable[[str], None]] = None,
                 keep_previous: bool = False) -> None:
    """Replace `path` with what `write(tmp_path)` produces, safely. `write` must create the file at the temp path it is given; `verify(tmp_path)` (optional) may raise to reject it. Only if both succeed is the temp file swapped in (os.replace - atomic on the same filesystem); with keep_previous the file being replaced is first moved to `<path>.prev`. On any failure the temp file is removed and the original is untouched."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    tmp = temp_path_for(path)
    try:
        write(tmp)
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            raise IOError(f"writing '{os.path.basename(path)}' produced no data")
        if verify is not None:
            verify(tmp)
        _fsync(tmp)
        if keep_previous and os.path.exists(path):
            shutil.copy2(path, path + PREVIOUS_SUFFIX)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _fsync(path: str) -> None:
    """Flush a file's data to disk (best effort)."""
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


# ---- backups -------------------------------------------------------------------------------

def backup_dir(path: str) -> str:
    """The folder holding time-stamped backups of `path`: <its folder>/.backups."""
    return os.path.join(os.path.dirname(os.path.abspath(path)), BACKUP_DIR_NAME)


def list_backups(path: str):
    """All backups of `path`, newest first, as full paths."""
    folder = backup_dir(path)
    prefix = os.path.basename(path) + "."
    if not os.path.isdir(folder):
        return []
    found = [os.path.join(folder, f) for f in os.listdir(folder) if f.startswith(prefix)]
    return sorted(found, reverse=True)   # the timestamp in the name sorts chronologically


def backup_file(path: str, keep: int, min_interval_seconds: float = 0, now: Optional[float] = None) -> Optional[str]:
    """Copy `path` into its .backups folder as `<name>.<YYYYmmdd-HHMMSS>` and prune to the newest `keep`. Skipped (returns None) if the file doesn't exist or the newest backup is younger than `min_interval_seconds` - so an auto-save after every edit doesn't push all the useful old versions out. Returns the backup path when one was made."""
    if not os.path.isfile(path):
        return None
    now = time.time() if now is None else now
    existing = list_backups(path)
    if existing and min_interval_seconds and (now - os.path.getmtime(existing[0])) < min_interval_seconds:
        return None
    folder = backup_dir(path)
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.fromtimestamp(now).strftime("%Y%m%d-%H%M%S")
    target = os.path.join(folder, f"{os.path.basename(path)}.{stamp}")
    shutil.copy2(path, target)
    os.utime(target, (now, now))
    for old in list_backups(path)[max(keep, 1):]:
        try:
            os.remove(old)
        except OSError:
            pass
    return target


# ---- change detection ----------------------------------------------------------------------

def file_signature(path: str) -> Optional[str]:
    """A short signature of a file's CONTENT (sha1), or None if it doesn't exist - compare two signatures to know whether the file changed in between."""
    try:
        digest = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


# ---- advisory lock -------------------------------------------------------------------------

def lock_path_for(path: str) -> str:
    """The lock file for a study file: <folder>/.<name>.lock."""
    directory, name = os.path.split(os.path.abspath(path))
    return os.path.join(directory, f".{name}.lock")


def _pid_alive(pid: int) -> bool:
    """True if a process with this id exists on this machine."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


def read_lock(path: str) -> Optional[dict]:
    """The lock info of a study file ({user, host, pid, started, touched}), or None if there is no (readable) lock."""
    try:
        with open(lock_path_for(path), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def foreign_lock(path: str, stale_after_hours: float, now: Optional[float] = None) -> Optional[dict]:
    """The lock on `path` if ANOTHER live session holds it, else None. A lock is ignored (stale) when it is ours, has not been touched for `stale_after_hours`, or was made on this machine by a process that no longer exists."""
    info = read_lock(path)
    if not info:
        return None
    now = time.time() if now is None else now
    if info.get("host") == socket.gethostname() and info.get("pid") == os.getpid():
        return None
    if now - float(info.get("touched", 0)) > stale_after_hours * 3600:
        return None
    if info.get("host") == socket.gethostname() and isinstance(info.get("pid"), int) and not _pid_alive(info["pid"]):
        return None
    return info


def acquire_lock(path: str) -> None:
    """Write (or refresh) our lock on a study file. Advisory only - it warns the next person, it doesn't block anyone. Never raises (a read-only folder just means no lock)."""
    now = time.time()
    info = read_lock(path) or {}
    ours = info.get("host") == socket.gethostname() and info.get("pid") == os.getpid()
    data = {
        "user": _user(), "host": socket.gethostname(), "pid": os.getpid(),
        "started": info.get("started", now) if ours else now, "touched": now,
    }
    try:
        with open(lock_path_for(path), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def release_lock(path: str) -> None:
    """Remove our lock on a study file (a lock held by someone else is left alone)."""
    info = read_lock(path)
    if info and info.get("host") == socket.gethostname() and info.get("pid") == os.getpid():
        try:
            os.remove(lock_path_for(path))
        except OSError:
            pass


def describe_lock(info: dict) -> str:
    """A human sentence about who holds a lock and since when."""
    started = datetime.fromtimestamp(float(info.get("started", 0))).strftime("%Y-%m-%d %H:%M")
    return f"{info.get('user', '?')}@{info.get('host', '?')} (since {started})"


def _user() -> str:
    """The current user's name, best effort."""
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"
