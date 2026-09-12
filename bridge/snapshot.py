"""Persistence of the last profile this plugin applied.

The KLC is write-only: Linux cannot read the per-key map back out of the
controller. So "restore" can only ever restore a profile *this plugin* wrote.
If none exists, callers must say so plainly rather than inventing a colour -
the profile saved from Windows is gone the moment the first map is applied.
"""

import json
import os
import tempfile

STATE_DIR = os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
    "omarchy", "steelseries-keyboard",
)
SNAPSHOT_PATH = os.path.join(STATE_DIR, "snapshot.json")

SCHEMA_VERSION = 1


def path():
    return SNAPSHOT_PATH


def exists():
    return os.path.isfile(SNAPSHOT_PATH)


def load():
    """The stored profile, or None if this plugin has never written one."""
    if not exists():
        return None
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or "profile" not in doc:
        return None
    return doc


def save(profile, device_id=None):
    """Write the full profile atomically, so a crash cannot leave a half file."""
    doc = {
        "schemaVersion": SCHEMA_VERSION,
        "device": device_id,
        "profile": profile,
    }
    os.makedirs(STATE_DIR, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=STATE_DIR, prefix=".snapshot-", suffix=".json")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, SNAPSHOT_PATH)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return SNAPSHOT_PATH


def clear():
    try:
        os.unlink(SNAPSHOT_PATH)
        return True
    except OSError:
        return False
