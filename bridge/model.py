"""Colour resolution for omastellrgb.

A profile is a stack. Later layers win:

    1. base fill      one colour for every addressable key
    2. named groups   smallest group wins where groups overlap
    3. per-key        individual overrides, always final

The stack describes how a stored profile resolves. Editing is a separate
matter: the bridge makes the latest edit visible by removing the per-key
overrides and nested groups that a group edit covers (see
Bridge.cmd_set_group), otherwise a pinned key would swallow the change.

There is no brightness layer: the KLC has no separate backlight channel and
the chassis Fn keys already handle dimming in firmware, so a software scale
only fought them.

Everything here is pure: no hardware, no I/O. That is what makes the colour
model testable without a keyboard attached.
"""

import re

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


class ProfileError(Exception):
    pass


def parse_color(value):
    """'#4a5cff' or '4a5cff' -> (74, 92, 255). Raises on anything else."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        rgb = tuple(int(c) for c in value)
        if any(c < 0 or c > 255 for c in rgb):
            raise ProfileError("colour channel out of range 0-255: %r" % (value,))
        return rgb
    if not isinstance(value, str):
        raise ProfileError("not a colour: %r" % (value,))
    match = HEX_RE.match(value.strip())
    if not match:
        raise ProfileError("not a 6-digit hex colour: %r" % (value,))
    digits = match.group(1)
    return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))


def format_color(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def resolve(profile, keymap):
    """Flatten a profile into {key_name: (r, g, b)} for every addressable key.

    Keys with no addressable LED are skipped rather than raising - on the GS75,
    Home and End are Fn-layer functions and simply cannot be lit.
    """
    if not isinstance(profile, dict):
        raise ProfileError("profile must be an object, got %r" % type(profile).__name__)

    colors = {}

    # 1. base fill
    base = profile.get("base")
    if base is not None:
        rgb = parse_color(base)
        for key in keymap.keys:
            colors[key] = rgb

    # 2. groups, largest first so the smallest wins
    groups = profile.get("groups") or {}
    if not isinstance(groups, dict):
        raise ProfileError("profile 'groups' must be an object")
    for name in sorted(groups, key=keymap.group_rank):
        rgb = parse_color(groups[name])
        for key in keymap.group_members(name):
            colors[key] = rgb

    # 3. per-key overrides
    keys = profile.get("keys") or {}
    if not isinstance(keys, dict):
        raise ProfileError("profile 'keys' must be an object")
    for key, value in keys.items():
        canonical = keymap.canonical(key)
        if canonical not in keymap.keys:
            near = sorted(k for k in keymap.keys if k.lower().startswith(str(key)[:2].lower()))[:6]
            raise ProfileError(
                "unknown key %r for keymap %s%s"
                % (key, keymap.id, (". Did you mean: " + ", ".join(near) + "?") if near else "")
            )
        colors[canonical] = parse_color(value)

    if not colors:
        raise ProfileError("profile sets no colours: needs at least a base, a group or a key")

    return colors


def to_hid_map(colors, keymap):
    """{key_name: rgb} -> {hid_keycode: rgb}, dropping keys with no LED."""
    out = {}
    for key, rgb in colors.items():
        hid = keymap.hid_for(key)
        if hid is not None:
            out[hid] = rgb
    return out


def blackout(keymap):
    """Every addressable key off. Used by the `off` command."""
    return {key: (0, 0, 0) for key in keymap.keys}
