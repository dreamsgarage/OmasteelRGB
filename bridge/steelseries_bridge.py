#!/usr/bin/env python3
"""omastellrgb bridge: line-delimited JSON over stdin/stdout.

QML never touches HID. Service.qml spawns this process and exchanges one JSON
object per line, which keeps the shell responsive and the hardware access in a
process that can be killed independently.

Protocol - one request per line, one response per line:

    {"cmd": "detect"}
    {"cmd": "apply",     "profile": {...}}
    {"cmd": "set_base",  "color": "#4a5cff"}
    {"cmd": "set_group", "group": "arrows", "color": "#ff2a2a"}
    {"cmd": "set_key",   "key": "Esc", "color": "#ff2a2a"}
    {"cmd": "brightness","value": 60}
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
        stored = snapshot.load()
        return stored["profile"] if stored else None

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

    def mutate(self, change):
        """Apply a partial edit on top of the stored profile.

        Editing a group or a single key still writes the whole resolved map,
        because the controller has no notion of our layer stack - but the
        stored profile keeps the layers so later edits compose correctly.
        """
        profile = self.current_profile()
        if profile is None:
            profile = {"base": "#000000", "groups": {}, "keys": {}, "brightness": 100}
        profile.setdefault("groups", {})
        profile.setdefault("keys", {})
        profile.setdefault("brightness", 100)
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
        return {
            "devices": devices,
            "hasSnapshot": stored is not None,
            "profile": stored["profile"] if stored else None,
            "snapshotPath": snapshot.path(),
            "canRestore": stored is not None,
            "message": None if stored else
                       "This plugin has never written a profile. Linux cannot read the "
                       "existing map off the controller, so there is nothing to restore.",
        }

    def cmd_apply(self, req):
        profile = req.get("profile")
        if not isinstance(profile, dict):
            raise ValueError("apply needs a 'profile' object")
        device = self.klc_device()
        result = self.write(profile, device)
        snapshot.save(profile, device_id=device["id"])
        return result

    def cmd_set_base(self, req):
        color = model.format_color(model.parse_color(req.get("color")))
        profile = self.mutate(lambda p: p.__setitem__("base", color))
        device = self.klc_device()
        result = self.write(profile, device)
        snapshot.save(profile, device_id=device["id"])
        return result

    def cmd_set_group(self, req):
        group = req.get("group")
        km = self.keymap()
        km.group_members(group)  # validates, raises KeymapError with the known list
        color = model.format_color(model.parse_color(req.get("color")))
        profile = self.mutate(lambda p: p["groups"].__setitem__(group, color))
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

    def cmd_brightness(self, req):
        value = model.parse_brightness(req.get("value"))
        profile = self.current_profile()
        if profile is None:
            raise RuntimeError("brightness needs a profile: apply a map first")
        profile["brightness"] = value
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
        "apply": cmd_apply, "set_base": cmd_set_base, "set_group": cmd_set_group,
        "set_key": cmd_set_key, "brightness": cmd_brightness,
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


def main(stdin=None, stdout=None):
    if os.geteuid() == 0:
        sys.stderr.write(
            "omastellrgb: refusing to run as root. Install udev/70-steelseries-klc.rules "
            "so the active session user gets access instead.\n")
        return 1

    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    bridge = Bridge()

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
