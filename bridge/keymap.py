"""Keymap loading for OmasteelRGB.

Keymaps are data, not code. Each file in keymaps/*.json describes one model
family: the key names it exposes, the X11 -> HID keycode translation, and the
named groups. Adding support for a new MSI deck means contributing a JSON file,
not editing Python.

A keymap may `"extends"` another by id: keys, x11_to_hid, aliases, notes and
groups are merged on top of the base (a redefined group replaces the whole
list). The GS65 and GS66 maps are two and three lines on top of the GE63
family this way, instead of three copies of a 100-entry table.

Model selection (`select`) turns the machine's DMI model token into a keymap:
an explicit override wins, then the detected token, then the default map with
`known: false` so the UI can say the layout is a guess.
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
        self.name = doc.get("name") or self.id
        self.extends = doc.get("extends")
        self.models = list(doc.get("models") or [])
        # Models someone has actually lit with this table, as opposed to
        # models upstream lists as sharing it.
        self.tested = list(doc.get("tested") or [])
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


MERGED_FIELDS = ("keys", "x11_to_hid", "aliases", "notes", "groups")
OWN_FIELDS = ("id", "name", "models", "layouts", "provenance", "tested", "extends")


def _read_doc(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise KeymapError("cannot read keymap %s: %s" % (path, exc)) from exc


def _resolve(doc_id, docs, chain=()):
    """Flatten an `extends` chain into one document."""
    doc, name = docs[doc_id]
    base_id = doc.get("extends")
    if not base_id:
        return dict(doc)
    if base_id not in docs:
        raise KeymapError("keymap %r extends unknown keymap %r" % (name, base_id))
    if base_id in chain or base_id == doc_id:
        raise KeymapError("keymap %r has a circular extends chain" % (name,))
    base = _resolve(base_id, docs, chain + (doc_id,))
    merged = dict(base)
    for field in MERGED_FIELDS:
        combined = dict(base.get(field) or {})
        combined.update(doc.get(field) or {})
        merged[field] = combined
    for field in OWN_FIELDS:
        if field in doc:
            merged[field] = doc[field]
    return merged


def available(keymap_dir=None):
    """Every keymap on disk, keyed by keymap id, with extends resolved."""
    directory = keymap_dir or KEYMAP_DIR
    out = {}
    if not os.path.isdir(directory):
        return out
    docs = {}
    for name in sorted(os.listdir(directory)):
        if name.endswith(".json"):
            doc = _read_doc(os.path.join(directory, name))
            doc_id = doc.get("id") or name[:-5]
            if doc_id in docs:
                raise KeymapError("two keymaps claim id %r: %s and %s" % (doc_id, docs[doc_id][1], name))
            docs[doc_id] = (doc, name)
    for doc_id, (_doc, name) in docs.items():
        out[doc_id] = Keymap(_resolve(doc_id, docs), source=name)
    return out


def known_models(keymap_dir=None):
    """Every model token any keymap claims, sorted."""
    return sorted({m.upper() for km in available(keymap_dir).values() for m in km.models})


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


def catalog(keymap_dir=None):
    """What the panel lists: each keymap with the models it claims."""
    return [{
        "id": km.id,
        "name": km.name,
        "models": km.models,
        "tested": km.tested,
        "keys": len(km.keys),
        "extends": km.extends,
    } for km in available(keymap_dir).values()]


def select(machine=None, override=None, default="GS75", keymap_dir=None):
    """Choose the keymap for this machine.

    Returns (keymap, info). info["source"] is "override", "dmi" or "default";
    info["known"] is False when the machine's model token matched nothing and
    the default table is a guess.
    """
    detected = (machine or {}).get("model")
    if override:
        km = load(override, keymap_dir)  # raises on an unknown override
        model = str(override).strip().upper()
        return km, {"selected": model, "detected": detected, "keymap": km.id,
                    "source": "override", "known": True, "tested": model in [t.upper() for t in km.tested]}
    if detected:
        try:
            km = load(detected, keymap_dir)
            return km, {"selected": detected, "detected": detected, "keymap": km.id,
                        "source": "dmi", "known": True, "tested": detected in [t.upper() for t in km.tested]}
        except KeymapError:
            pass
    km = load(default, keymap_dir)
    return km, {"selected": default, "detected": detected, "keymap": km.id,
                "source": "default", "known": False, "tested": False}
