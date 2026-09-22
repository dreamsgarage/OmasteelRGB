#!/usr/bin/env python3
"""OmasteelRGB bridge: line-delimited JSON over stdin/stdout.

QML never touches HID. Service.qml spawns this process and exchanges one JSON
object per line, which keeps the shell responsive and the hardware access in a
process that can be killed independently.

Protocol - one request per line, one response per line:

    {"cmd": "detect"}
    {"cmd": "apply",     "profile": {...}}
    {"cmd": "set_base",  "color": "#4a5cff"}
    {"cmd": "set_group", "group": "arrows", "color": "#ff2a2a"}
    {"cmd": "set_key",   "key": "Esc", "color": "#ff2a2a"}
    {"cmd": "off"}
    {"cmd": "restore"}
    {"cmd": "state"}
    {"cmd": "keymap",    "model": "GS75"}

Every response carries "ok". Failures carry "error" and never raise.

Validation lives here, not only in QML: the bridge is the last line of defence
before a 524-byte report reaches a firmware controller.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge import detect, keymap as keymap_mod, klc_hid, model, snapshot  # noqa: E402

DEFAULT_MODEL = "GS75"
PRESET_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "presets")
# The layer stack. Everything else in a preset document is metadata.
PROFILE_FIELDS = ("base", "groups", "keys")
# Base fill for a first edit when no preset is flagged "default".
DEFAULT_BASE = "#4a5cff"


class Bridge:
    def __init__(self):
        self._keymap = None
        self._model = DEFAULT_MODEL
        self._device = None

    # -- helpers ----------------------------------------------------------

    def keymap(self, name=None):
        wanted = name or self._model
        if self._keymap is None or wanted != self._model:
            self._keymap = keymap_mod.load(wanted)
            self._model = wanted
        return self._keymap

    def klc_device(self):
        """The first accessible KLC, or a helpful error."""
        devices = [d for d in detect.scan() if d["kind"] == "klc"]
        if not devices:
            raise RuntimeError("no SteelSeries KLC keyboard found")
        device = devices[0]
        if not device["accessible"]:
            raise PermissionError(device["hint"])
        return device

    def current_profile(self):
        """The stored layer stack, dropping fields this version no longer
        knows (a snapshot from before brightness was removed still carries
        one; it must not ride along into the next write)."""
        stored = snapshot.load()
        if not stored:
            return None
        return {k: v for k, v in stored["profile"].items() if k in PROFILE_FIELDS}

    def write(self, profile, device=None):
        """Resolve, translate, and push a profile to the hardware."""
        device = device or self.klc_device()
        km = self.keymap()
        colors = model.resolve(profile, km)
        hid_colors = model.to_hid_map(colors, km)
        if not hid_colors:
            raise ValueError("profile resolved to no addressable keys")
        with klc_hid.KLCDevice(product_id=device["product_id"]) as dev:
            reports = dev.apply(hid_colors)
        return {"keys": len(hid_colors), "reports": reports}

    def default_preset(self):
        """The preset flagged "default": true, or None."""
        for preset in self.cmd_presets({})["presets"]:
            if preset["default"]:
                return preset
        return None

    def starting_profile(self):
        """What a partial edit builds on when this plugin has never written.

        The controller cannot be read, so the rest of the board has to come
        from somewhere. The default preset is the plugin's known-good look;
        without one, a plain base fill. Never black: "I changed one key and
        the whole board went dark" is the wrong first experience.
        """
        preset = self.default_preset()
        if preset is not None:
            return json.loads(json.dumps(preset["profile"]))
        return {"base": DEFAULT_BASE}

    def mutate(self, change, fresh=None):
        """Apply a partial edit on top of the stored profile.

        Editing a group or a single key still writes the whole resolved map,
        because the controller has no notion of our layer stack - but the
        stored profile keeps the layers so later edits compose correctly.

        With no stored profile the edit lands on `fresh` if given, else on
        `starting_profile()`.
        """
        profile = self.current_profile()
        if profile is None:
            profile = dict(fresh) if fresh is not None else self.starting_profile()
        profile.setdefault("base", DEFAULT_BASE)
        profile.setdefault("groups", {})
        profile.setdefault("keys", {})
        change(profile)
        return profile

    # -- commands ---------------------------------------------------------

    def cmd_detect(self, _req):
        return {"devices": detect.scan()}

    def cmd_keymap(self, req):
        km = self.keymap(req.get("model"))
        return {
            "keymap": km.id,
            "models": km.models,
            "keys": sorted(km.keys),
            "groups": {g: km.group_members(g) for g in km.groups},
            "aliases": km.aliases,
            "notes": km.notes,
        }

    def cmd_state(self, _req):
        stored = snapshot.load()
        devices = detect.scan()
        start = self.default_preset()
        return {
            "devices": devices,
            "hasSnapshot": stored is not None,
            "profile": stored["profile"] if stored else None,
            "snapshotPath": snapshot.path(),
            "canRestore": stored is not None,
            # What a first group/key edit fills the rest of the board with.
            "startingFrom": {"id": start["id"], "name": start["name"]} if start else None,
            "message": None if stored else
                       "This plugin has never written a profile. Linux cannot read the "
                       "existing map off the controller, so there is nothing to restore.",
        }

    def cmd_presets(self, _req):
        """The colour maps shipped in presets/*.json, with metadata split from
        the applicable profile so a caller can hand the profile straight back
        to `apply`."""
        out = []
        if os.path.isdir(PRESET_DIR):
            for name in sorted(os.listdir(PRESET_DIR)):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(PRESET_DIR, name), "r", encoding="utf-8") as fh:
                        doc = json.load(fh)
                except (OSError, ValueError):
                    continue
                if not isinstance(doc, dict):
                    continue
                profile = {k: doc[k] for k in PROFILE_FIELDS if k in doc}
                if not any(k in profile for k in ("base", "groups", "keys")):
                    continue
                out.append({
                    "id": doc.get("id") or name[:-5],
                    "name": doc.get("name") or name[:-5],
                    "description": doc.get("description") or "",
                    "model": (doc.get("hardware") or {}).get("model"),
                    "default": doc.get("default") is True,
                    "profile": profile,
                })
        return {"presets": out}

    def cmd_apply(self, req):
        profile = req.get("profile")
        if not isinstance(profile, dict):
            raise ValueError("apply needs a 'profile' object")
        # The snapshot is the layer stack and nothing else; a preset document's
        # notes and provenance must not ride along into it.
        profile = {k: v for k, v in profile.items() if k in PROFILE_FIELDS}
        device = self.klc_device()
        result = self.write(profile, device)
        snapshot.save(profile, device_id=device["id"])
        return result

    def cmd_set_base(self, req):
        color = model.format_color(model.parse_color(req.get("color")))
        # "Board" as the first write means paint the whole board, so it does
        # not inherit the default preset's groups the way a key edit does.
        profile = self.mutate(lambda p: p.__setitem__("base", color), fresh={"base": color})
        device = self.klc_device()
        result = self.write(profile, device)
        snapshot.save(profile, device_id=device["id"])
        return result

    def cmd_set_group(self, req):
        group = req.get("group")
        km = self.keymap()
        members = set(km.group_members(group))  # validates, raises KeymapError with the known list
        color = model.format_color(model.parse_color(req.get("color")))

        def change(p):
            p["groups"][group] = color
            # The edit must be visible. Per-key overrides and smaller groups
            # inside this one sit above it in the stack and would mask it
            # completely - "Esc + Enter" did nothing while both keys were
            # pinned red. The latest edit wins, so drop what it covers.
            for key in list(p["keys"]):
                if km.canonical(key) in members:
                    del p["keys"][key]
            for other in list(p["groups"]):
                if other != group and other in km.groups and set(km.group_members(other)) <= members:
                    del p["groups"][other]

        profile = self.mutate(change)
        device = self.klc_device()
        result = self.write(profile, device)
        snapshot.save(profile, device_id=device["id"])
        return result

    def cmd_set_key(self, req):
        km = self.keymap()
        key = km.canonical(req.get("key"))
        if key not in km.keys:
            raise ValueError("unknown key %r for keymap %s" % (req.get("key"), km.id))
        color = model.format_color(model.parse_color(req.get("color")))
        profile = self.mutate(lambda p: p["keys"].__setitem__(key, color))
        device = self.klc_device()
        result = self.write(profile, device)
        snapshot.save(profile, device_id=device["id"])
        return result

    def cmd_off(self, _req):
        """Black the board without destroying the stored profile, so restore works."""
        device = self.klc_device()
        km = self.keymap()
        hid_colors = model.to_hid_map(model.blackout(km), km)
        with klc_hid.KLCDevice(product_id=device["product_id"]) as dev:
            reports = dev.apply(hid_colors)
        return {"keys": len(hid_colors), "reports": reports, "off": True}

    def cmd_restore(self, _req):
        profile = self.current_profile()
        if profile is None:
            raise RuntimeError(
                "nothing to restore: this plugin has never written a profile, and Linux "
                "cannot read the original map off the controller"
            )
        return self.write(profile)

    # -- dispatch ---------------------------------------------------------

    HANDLERS = {
        "detect": cmd_detect, "state": cmd_state, "keymap": cmd_keymap,
        "presets": cmd_presets,
        "apply": cmd_apply, "set_base": cmd_set_base, "set_group": cmd_set_group,
        "set_key": cmd_set_key,
        "off": cmd_off, "restore": cmd_restore,
    }

    # Protocol-owned keys. A command result must never overwrite these or the
    # caller loses response correlation.
    RESERVED = ("ok", "cmd", "id", "error")

    def handle(self, request):
        command = request.get("cmd")
        handler = self.HANDLERS.get(command)
        response = {"ok": False, "cmd": command}
        if "id" in request:
            response["id"] = request["id"]
        if handler is None:
            response["error"] = "unknown command %r. Known: %s" % (
                command, ", ".join(sorted(self.HANDLERS)))
            return response
        try:
            result = handler(self, request)
        except PermissionError as exc:
            response["error"] = str(exc)
            response["needsAccess"] = True
        except (keymap_mod.KeymapError, model.ProfileError, klc_hid.KLCError,
                ValueError, RuntimeError, OSError) as exc:
            response["error"] = str(exc)
        else:
            collisions = [k for k in result if k in self.RESERVED]
            if collisions:
                response["error"] = "handler %r returned reserved keys: %s" % (
                    command, ", ".join(collisions))
                return response
            response["ok"] = True
            response.update(result)
        return response


def main(stdin=None, stdout=None, argv=None):
    if os.geteuid() == 0:
        sys.stderr.write(
            "OmasteelRGB: refusing to run as root. Install udev/70-steelseries-klc.rules "
            "so the active session user gets access instead.\n")
        return 1

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    argv = sys.argv[1:] if argv is None else argv
    bridge = Bridge()

    # Service.qml queues requests until it sees this, because data written to
    # a process that has not finished starting is dropped. Opt-in so plain
    # pipelines and the tests keep one response per request.
    if "--ready" in argv:
        stdout.write(json.dumps({"ok": True, "event": "ready"}) + "\n")
        stdout.flush()

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be a JSON object")
        except ValueError as exc:
            response = {"ok": False, "error": "bad JSON: %s" % exc}
        else:
            response = bridge.handle(request)
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
