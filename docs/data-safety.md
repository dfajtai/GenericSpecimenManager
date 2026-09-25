# Data safety

The module's promise is that the data comes out reliable - so the files it writes are protected against the things
that actually go wrong: an interrupted write, a full disk, a second session, an overwrite by mistake. The building
blocks are in [`core/safe_io.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/core/safe_io.py) (pure Python, covered by
[`tests/test_safeio.py`](../tests/test_safeio.py)); the knobs are in
[`definitions.py`](../GenericSpecimenManager/GenericSpecimenManager/Resources/definitions.py).

## database.csv

Every save (the *Save database CSV* button, *Auto-save database*, the columns created at Initialize Study):

1. **Change detection.** The module remembers a signature (a content hash) of `database.csv` from when it read or last
   wrote it. If the file on disk is different now - another person, another program, a second Slicer - it does **not**
   overwrite silently: a dialog offers *Overwrite (keep a backup)* or *Don't save*.
2. **Backup.** The file about to be replaced is copied into a `.backups/` folder next to it, as
   `database.csv.<YYYYmmdd-HHMMSS>`. At most one backup per `DB_BACKUP_MIN_INTERVAL_SECONDS` (default 5 minutes - so
   auto-save after every edit does not push every useful old version out), and the newest `DB_BACKUPS_KEEP` (default
   10) are kept. A file that was changed on disk is always backed up first, whatever the interval.
3. **Atomic write.** The table is written to a temporary file next to it (`.tmp-<pid>-database.csv`) and checked - the
   number of data rows must match and every column must be present. Only then is it swapped in, in one step. A failed
   or interrupted write leaves the old `database.csv` exactly as it was.

## Study lock

While a study is initialized, a small lock file `.database.csv.lock` (who, on which machine, since when) sits next to
`database.csv`. Initialize Study on the same study from another session shows *Study already open* with that
information and lets you cancel or *Continue anyway* - the lock is advisory, it warns, it never blocks.
The lock is released when the module is closed or Slicer quits. A lock is ignored when it is older than
`STUDY_LOCK_STALE_HOURS` (default 12), or was left by a process on the same machine that no longer exists (a crash).

## Specimen files (segmentation, markups)

*Save progress* / `Ctrl+S` write each file the same atomic way (temp file, then swap). The version being replaced is
kept as `<file>.prev` (one level; `KEEP_PREVIOUS_SPECIMEN_FILES`) - so the previous save is always one rename away.
Source images are not given a `.prev` (they are big, and normally unchanged). *Reset selected specimen* removes the
`.prev` files together with the saved ones, and lists them in its confirmation.

## Config files

The Config Editor saves `config.json` atomically as well, keeping the previous version as `config.json.prev`.

## What is not covered

- Two people editing the **same specimen** at once: the lock only warns at the study level.
- The safety files (`.backups/`, `*.prev`, `.*.lock`, `.tmp-*`) are ignored by this repository's `.gitignore`; if you
  keep your study under version control, ignore them there too.
