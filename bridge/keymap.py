"""Keymap loading for OmasteelRGB.

Keymaps are data, not code. Each file in keymaps/*.json describes one model
family: the key names it exposes, the X11 -> HID keycode translation, and the
named groups. Adding support for a new MSI deck means contributing a JSON file,
not editing Python.
"""

import json
import os

KEYMAP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "keymaps")


class KeymapError(Exception):
    pass


class Keymap:
    """One model family's key names, HID translation and groups."""

    def __init__(self, doc, source=""):
        self.source = source
        self.id = doc.get("id") or ""
        self.models = list(doc.get("models") or [])
        self.keys = dict(doc.get("keys") or {})
        self.groups = dict(doc.get("groups") or {})
        self.notes = dict(doc.get("notes") or {})
        self.aliases = dict(doc.get("aliases") or {})
        self._x11_to_hid = dict(doc.get("x11_to_hid") or {})

        if not self.keys:
            raise KeymapError("keymap %r declares no keys" % (source or self.id))

        # An alias that shadows a real key, or points nowhere, would resolve silently
        # to the wrong LED. Both are keymap authoring errors, so fail at load.
        for alias, target in self.aliases.items():
            if alias in self.keys:
                raise KeymapError("keymap %r alias %r shadows a real key" % (source or self.id, alias))
            if target not in self.keys:
                raise KeymapError(
                    "keymap %r alias %r points at unknown key %r" % (source or self.id, alias, target)
                )

        # Typed names arrive in whatever case the user used: "esc", "kp_delete",
        # "prtsc". Exact spelling wins; otherwise match ignoring case.
        self._folded = {}
        for name in list(self.keys) + list(self.aliases):
            self._folded.setdefault(name.lower(), name)

        # Group membership must reference real keys, or a colour silently vanishes.
        for group, members in self.groups.items():
            unknown = [m for m in members if self.canonical(m) not in self.keys]
            if unknown:
                raise KeymapError(
                    "keymap %r group %r references unknown keys: %s"
                    % (source or self.id, group, ", ".join(sorted(unknown)))
                )

        # Declaration order is the documented tie-break for equal-sized groups.
        self._group_order = {name: i for i, name in enumerate(self.groups)}

    def canonical(self, key):
        """Resolve a friendly name to its canonical one: 'PrtSc' -> 'Print', 'esc' -> 'Esc'."""
        name = str(key or "").strip()
        if name not in self.keys and name not in self.aliases:
            name = self._folded.get(name.lower(), name)
        return self.aliases.get(name, name)

    def hid_for(self, key):
        """HID keycode for a key name, or None if this key has no addressable LED."""
        code = self.keys.get(self.canonical(key))
        if code is None:
            return None
        return self._x11_to_hid.get(str(code))

    def group_members(self, group):
        if group not in self.groups:
            raise KeymapError("unknown group %r (have: %s)" % (group, ", ".join(sorted(self.groups))))
        return [self.canonical(k) for k in self.groups[group]]

    def group_rank(self, group):
        """Sort key for precedence: smallest group wins, ties by declaration order.

        Groups overlap by design - `wasd` sits inside `characters`. Applying in
        descending size order means the smaller, more specific group is written
        last and therefore wins, which is what a user expects when they colour
        WASD over a lettered base.
        """
        if group not in self.groups:
            raise KeymapError("unknown group %r (have: %s)" % (group, ", ".join(sorted(self.groups))))
        return (-len(self.groups[group]), -self._group_order[group])

    def __repr__(self):
        return "<Keymap %s: %d keys, %d groups>" % (self.id, len(self.keys), len(self.groups))


def _load_file(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return Keymap(json.load(fh), source=os.path.basename(path))
    except (OSError, ValueError) as exc:
        raise KeymapError("cannot read keymap %s: %s" % (path, exc)) from exc


def available(keymap_dir=None):
    """Every keymap on disk, keyed by keymap id."""
    directory = keymap_dir or KEYMAP_DIR
    out = {}
    if not os.path.isdir(directory):
        return out
    for name in sorted(os.listdir(directory)):
        if name.endswith(".json"):
            km = _load_file(os.path.join(directory, name))
            out[km.id] = km
    return out


def load(model, keymap_dir=None):
    """Look up a keymap by model name (e.g. "GS75") or keymap id (e.g. "gs75")."""
    maps = available(keymap_dir)
    if model in maps:
        return maps[model]
    wanted = str(model).strip().upper()
    for km in maps.values():
        if wanted in [m.upper() for m in km.models]:
            return km
    known = sorted({m for km in maps.values() for m in km.models})
    raise KeymapError(
        "no keymap for model %r. Known models: %s. "
        "Other MSI decks need a contributed keymaps/*.json." % (model, ", ".join(known))
    )
