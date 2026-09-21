# omastellrgb v1 design

**Status:** approved  
Companion to [v1-spec.md](v1-spec.md).

## Architecture

```
Panel.qml (bar widget + KeyboardPanel)
    │
Service.qml  (one per shell; owns the bridge process)
    │  JSON lines on stdin/stdout
bridge/steelseries_bridge.py
    ├── detect.py              USB/HID scan, claim policy
    ├── drivers/klc_hid.py     msi-perkeyrgb-style packets
    ├── drivers/klc_leds.py    sysfs LED class if present (not for multi-color maps)
    ├── drivers/apex_openrgb.py  optional SDK
    ├── keymap.py              GS75 groups, key names, Linux keycodes
    └── snapshot.py            last plugin-applied color map
```

QML has no TCP/HID. Follow OmaRGB: spawn a Python bridge, exchange JSON lines, re-read after writes so the panel shows hardware truth rather than optimistic color. Coalesce color-slider drags.

### Plugin contract

- `schemaVersion`: 1
- `id`: `steelseries.keyboard` (not `omarchy.*`)
- `kinds`: `["service", "bar-widget"]`
- `entryPoints.service`: `Service.qml`
- `entryPoints.barWidget`: `Panel.qml`
- `barWidget.defaultSection`: `right`
- `barWidget.schema`: `themeSync` (bool, false), `vividAccent` (bool, true), `apexBackend` (bool, true)
- No symlinks in the plugin folder

> **Implementation note (2026-09-21).** The shipped manifest declares `kinds: ["bar-widget"]` only, and
> `Service.qml` is instantiated inside `Panel.qml` — the shape of the first-party `panels/dropbox` plugin,
> which also wraps a Python helper. A separately mounted `service` kind would have to be found from the
> widget through `shell.serviceFor()`, which the host scopes per plugin and which no third-party plugin was
> found exercising; the media widget uses `firstPartyServiceFor()`, unavailable to us. Keeping the service
> inside the widget removes that lookup entirely, and the widget is mounted for as long as the plugin is
> enabled, so the bridge's lifetime is the same either way. `Service.qml` stays a separate file so the split
> can be revisited without moving code.

Install later (not this spec drop):

```text
omarchy plugin add <git-url> --enable
```

Planned implementation layout (mirrors OmaRGB so `omarchy plugin validate` is happy):

- `manifest.json`
- `Service.qml`
- `Panel.qml`
- `Model.js`
- `bridge/` Python (stdlib + hidapi for KLC)
- `udev/70-steelseries-klc.rules` (documented; not auto-copied into `/etc`)
- `tests/` for packet builders and JSON protocol against a fake hid device

Python 3 is already on Omarchy. hidapi is extra (`python-hidapi` / `hidapi`). OpenRGB is optional.

## Hardware backends

### Integrated KLC (primary)

USB vendor `1038`. Known keyboard PIDs:

| PID | Name | Notes |
|---|---|---|
| `1122` | KLC | GS75 Stealth 8SF. msi-perkeyrgb default ID. `--model GS75` |
| `113a` | KLC | Later Stealth / Vector / GP66 |
| others in the same KLC family | treat as KLC if HID report layout matches | |

Protocol:

- Feature report ~524 bytes, opcode `0x0e` / `0x0c` depending on generation
- Commit packet 64 bytes, opcode `0x09`
- Regions: alphanum, enter, modifiers, numpad — packets carry **per-key** RGB, not 3-zone
- Two HID interfaces; RGB is not the typing interface
- Profile lives in controller memory
- Write-only plus plugin snapshot; cannot read the Windows map back
- GS75 shares the GE63/GE73/GE75/GS63 keymap in msi-perkeyrgb
- v1 adds `wasd`, `nav`, `numpad_ops` on top of stock aliases

**HID userspace is mandatory** for v1 multi-color maps.

Kernel `hid-steelseries` can expose `steelseries::kbd_backlight` as a **single** multicolor LED (one RGB for every key). That cannot reproduce the photo. On the reference machine the device is bound to `hid-generic` (no LED class node).

If LED class later binds:

1. Do not switch a multi-color map onto LED class.
2. HID userspace remains the lighting backend for maps with more than one color.
3. LED class may only be used for global brightness if it can sit beside hidraw without stealing the RGB interface. If the kernel claims the device and hidraw disappears, treat that as a blocker and keep HID (unbind/rebind) rather than flattening to one color.

### External Apex

Apex 3/5/7/Pro/9 use a different HID protocol from KLC. OpenRGB already has Apex controllers.

v1 Apex path: optional OpenRGB SDK client, used only for devices the KLC driver does not claim. If OpenRGB is missing, list the USB device as “detected, Apex backend needs OpenRGB” rather than failing the plugin.

v1.1: native Apex HID in the same Python bridge.

## Claim policy

- One plugin owns lighting for a given `vid:pid`.
- KLC HID wins over OpenRGB for KLC PIDs so OmaRGB cannot double-drive the laptop deck.
- Apex goes to OpenRGB only if this plugin’s Apex driver is enabled and OpenRGB reports the device.
- Detection is read-only. Opening the panel must not send a color packet.

## Permissions

On the reference machine `/dev/hidraw0` and `/dev/hidraw1` are `root:root 600`.

Ship `70-steelseries-klc.rules` matching vendor `1038` keyboard PIDs with `TAG+="uaccess"`.

> **Use `uaccess`, not `GROUP="input"`.** `uaccess` grants an ACL to the user of the active login session, so it
> needs no group membership and no re-login. The original `GROUP="input"` proposal would have granted nothing on
> the reference machine, whose user is not in `input`.
>
> **The file number is load-bearing: it must sort below 73.** `/usr/lib/udev/rules.d/73-seat-late.rules` runs
> `RUN{builtin}+="uaccess"` at priority 73. A `TAG+="uaccess"` set in a `99-*` file is evaluated after that line,
> so the tag shows up in `CURRENT_TAGS` while the builtin never fires and the node stays `root:root 0600`. This
> failure is silent and looks exactly like a seat problem. Stock rules use 70; see
> [../udev/70-steelseries-klc.rules](../udev/70-steelseries-klc.rules).
>
> **Never ship `MODE="0666"` for these nodes.** The `msi-perkeyrgb` AUR package installs
> `/etc/udev/rules.d/99-msi-rgb.rules` with world read/write on the keyboard's raw HID interfaces, which lets any
> local process read keystrokes. Remove it when installing this rule.
>
> udev never applies rules retroactively: after installing, `udevadm control --reload` **and**
> `udevadm trigger --subsystem-match=hidraw --action=add` are both required, or the change takes effect only at
> next boot. Document: copy to `/etc/udev/rules.d/`, reload, trigger. Do **not** install the rule during `omarchy plugin add`. The panel shows a “grant access” action that opens a terminal with the exact commands.

hidapi: prefer **libusb backend** for KLC. Detach the kernel driver only on the RGB interface, never on the typing interface. Refuse to run the bridge as root.

## Theme integration

Do not patch `/usr/share/omarchy/bin/omarchy-theme-set-keyboard`.

Opt-in only (default off):

1. Plugin setting `themeSync`. Service watches `~/.local/state/omarchy/current/theme/keyboard.rgb` (or the shell theme singleton) and pushes accent when enabled.
2. Optional later: `omarchy hook install theme-set` calling plugin IPC.

When theme sync is off, theme changes leave the onboard/Windows look alone. Default theme-sync target is **base fill only**.

## Brightness keys

Stock binds (`XF86KbdBrightnessUp/Down`) call `omarchy-brightness-keyboard`, which exits on this laptop (no `*kbd_backlight*` LED). v1 does not edit Hyprland defaults. Document a user bind that calls plugin IPC. v1.1 may install a **user** snippet under `~/.config/hypr/` if the user opts in from the panel. Never write `/usr/share/omarchy/`.

Sleep: stock `keyboard-backlight` hook only hits sysfs `*kbd_backlight*`. A HID off-before-hibernate hook is not v1 unless testing shows a hang.

## UX

Follow first-party `KeyboardPanel` and OmaRGB.

**Bar**

- Glyph: keyboard with light. Color = last known plugin **base** color.
- If lights are on from Windows and the plugin never wrote: glyph on, color chip “unknown” (outline, not a fake hex).
- Left click: open panel.
- Right click: lights off (stealth). Does not guess a restore color if none was snapshotted.
- Middle click: toggle theme sync only after the user has used the panel once.

**Panel**

1. Device list (usually one row on the GS75).
2. Power. On without a snapshot = leave onboard as-is; if a snapshot exists, re-apply the full map.
3. Brightness slider, disabled until a map has been applied (or LED class reports brightness).
4. Swatch + palette + hex, applied to the **current target**: whole board, a named group, or selected key(s).
5. Compact GS75 schematic (ISO extra key / Alt Gr). Group chips: Arrows, Nav, Numpad ops, WASD, and so on. Click keys to set the target. Preview before Apply. “Load photo preset” applies `gs75-photo`.
6. Follow theme accent, default off, with warning: *This replaces the profile saved from Windows.*
7. Empty/error: no device, no hidraw permission, Apex present but OpenRGB missing.

Keyboard: `j/k` devices, `h/l` brightness, `o` off, `t` theme sync, `Esc` close.

## Safety

- v1 writes steady per-key colors + brightness + off only. No effect packets (`0x0b` etc.).
- First run detect-only.
- First apply snapshots a full key→color map. Restore cannot recover the original Windows profile.
- UI copy: once you apply a map, the Windows look is gone until you set it again in Engine on Windows or re-enter the map here.
- Validate hex and brightness in the bridge, not only in QML.
- Rate-limit writes. No 524-byte storms while dragging.

## Implementation phases (when coding starts)

1. Probe — enumerate `1038:*` HID, classify KLC vs Apex, print JSON, no writes. Verify GS75 `1038:1122`, two interfaces, firmware 2.31.
2. Permissions — udev rule + panel “needs access” state.
3. KLC write path — off, base, groups, per-key, brightness, snapshot/restore. Mixed map must survive reboot.
4. Shell plugin — service + bar widget + schematic + IPC. `omarchy plugin validate` clean.
5. Theme sync — opt-in.
6. Apex — optional OpenRGB; degrade if missing.
7. Fn brightness — documented user bind.
8. Hardening — packet tests, no-root, no-write-on-start, claim policy vs OmaRGB.

## Risks

- KLC PID/firmware variants (`1122` vs `113a`) need a table and a GS75 vs GS65 keymap. Wrong map = wrong keys lit, not a brick.
- Cannot round-trip the Windows profile.
- hidraw vs libusb detach must not steal the typing interface.
- OpenRGB Apex support is per-model.
- If `hid-steelseries` starts binding after a kernel update, hidraw may disappear; do not silently degrade multi-color maps to one LED.
