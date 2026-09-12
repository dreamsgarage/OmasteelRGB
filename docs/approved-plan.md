# Approved v1 plan

# SteelSeries Keyboard plugin for Omarchy

Plan only. No code, no install, no deploy.

## Goal

Build a third-party Omarchy 4 shell plugin that controls **lighting** on SteelSeries keyboards, both:

- **Integrated** MSI laptop decks (SteelSeries KLC, this GS75 Stealth 8SF, USB `1038:1122`)
- **External** Apex-family USB keyboards (Apex 3 / 5 / 7 / Pro / 9, TKL and full-size)

Typing already works through HID. The gap is RGB: Omarchy has no SteelSeries backend, stock OpenRGB does not drive KLC, and this keyboard is currently replaying the **Windows SteelSeries Engine profile stored in onboard memory**. The plugin must respect that until the user explicitly changes lights.

## Why this plugin, not an existing one

| Existing piece | Why it is not the product |
|---|---|
| `omarchy.keyboard-layout` | Layout indicator only |
| `omarchy-theme-set-keyboard` | ASUS `asusctl` + Framework `qmk_hid` only |
| `omarchy brightness keyboard` | Needs `/sys/class/leds/*kbd_backlight*`; this GS75 has none |
| OmaRGB (`io.github.ilkaydnc.omargb`) | Right UX shape, wrong backend. Stock OpenRGB does not enumerate KLC `1038:1122`. Support lives in unmerged OpenRGB MRs |
| `steelseries.mouse-controller` | Rival mice via `rivalcfg`, not keyboards |
| `msi-perkeyrgb` CLI | Correct KLC protocol, no Omarchy UI, effects disabled for safety |
| `msi-klc` / `msiklm` | Older 3-zone MSI boards, not per-key KLC |

Closest UX to copy: **OmaRGB** (bar dot + panel + theme sync + stealth) and **Bluetooth** (native `KeyboardPanel`, keyboard-driven, theme colors). Closest protocol to copy: **msi-perkeyrgb** for KLC, **OpenRGB SteelSeries Apex controllers** for external boards.

Do **not** fork OmaRGB. Do **not** require OpenRGB for the laptop keyboard. Do **not** run SteelSeries GG under Wine.

## Product

**Name:** SteelSeries Keyboard  
**Plugin id:** `steelseries.keyboard` (same namespace as the mouse plugin; not `omarchy.*`)  
**Kinds:** `service` + `bar-widget`  
**Default bar section:** right  
**Target:** Omarchy 4 / Quattro shell (this machine is 4.0.3)

The bar shows a keyboard-light glyph tinted with the last **known** base color (or a muted “unknown onboard” state). Click opens a panel. The service owns a Python HID bridge; QML never talks HID itself.

**“Solid” means steady (non-animated) colors, not one color for the whole board.** Multiple solid colors at once are required: each key or group holds its own fixed hex. The photo uses two (cyan + red); v1 is **not** capped at two — any number of distinct solid colors is valid (WASD green, arrows amber, Esc red, rest cyan, etc.). No breathe, wave, or reactive in v1. The KLC on this GS75 is per-key RGB. Hardware cannot currently *read* that Windows map back; the plugin recreates it from a saved map.

### Reference config (confirmed from photo)

Access confirmed: `/home/gaston4kd/Pictures/keyboard.png` (readable, 80840 bytes). This is the **v1 acceptance fixture**.

Photo is this GS75 SteelSeries deck, Spanish ISO legends (Ñ, Alt Gr, €), two steady colors:

| Role | Color in photo | Keys |
|---|---|---|
| **Base** | cyan / light blue | letters, number row, F-row, Caps, Shifts, Ctrl, Alt, Alt Gr, Space, Enter, Backspace, ` [ ] ; ' , . / \ , PrtSc, ScrLk, Pause, numpad digits 0–9 and numpad Enter / Del |
| **Red group + keys** | red | Esc, Tab, Fn, Windows, arrows, Ins / Home / PgUp / Del / End / PgDn, Num Lock, numpad `/` `*` `-` `+` |

This is **not** a WASD-highlight layout. v1 must support this split: cyan base, red on navigation cluster + a few named keys + numpad operators, while numpad **digits** stay on the base color.

Approximate hex from the photo (for the fixture; user can tweak later):

- base `#00b4ff`
- red `#ff2a2a`

### Lighting model (v1, required)

A profile is a stack of steady colors. Later layers win:

1. **Base fill** — one color for every key (or off).
2. **Named groups** — each group has its own solid color. Built-in groups for GS75 (US and ISO position maps):
   - `wasd`, `arrows`, `nav` (Ins/Home/PgUp/Del/End/PgDn), `numpad`, `numpad_ops` (NumLock `/` `*` `-` `+`), `num_row`, `f_row`, `modifiers` (Ctrl/Alt/Shift; **not** Super), `fn`, `enter_esc`, `characters`
3. **Per-key overrides** — individual keys by name (`Esc`, `Tab`, `Super`/`Win`, `Fn`) or Linux keycode, each with its own hex color.

**Photo profile expressed in that model (must be representable and writable in v1):**

- all keys `#00b4ff`
- `nav` `#ff2a2a`
- `arrows` `#ff2a2a`
- `numpad_ops` `#ff2a2a`
- `Esc` `#ff2a2a`
- `Tab` `#ff2a2a`
- `Fn` `#ff2a2a`
- `Super` `#ff2a2a`

Brightness is a global scale applied after the map (0–100). Theme sync, when on, can replace **only the base fill**, or replace base+groups by user choice; it must not silently wipe per-key overrides unless the user picks “paint entire board.”

The snapshot stored on disk is this full map, not a single hex. Restore reapplies the map. IPC can set a group or a key, not only the whole board.

### v1 capabilities

1. Detect connected SteelSeries keyboards (KLC and Apex) without writing to them.
2. Show identity: name, USB `vid:pid`, backend, whether lights are known vs “onboard / unknown”.
3. **Off / restore** (stealth): black flush that can be undone from a snapshot the plugin itself wrote. If the plugin never wrote a profile, restore is “cannot restore Windows look from Linux” and must say so.
4. **Steady color map**: base fill + named groups + per-key overrides (see lighting model).
5. **Brightness** as a global RGB scale on top of the map (KLC has no separate backlight sysfs node).
6. Opt-in **follow Omarchy theme accent** for the base fill (and optionally groups). Default **off** so the Windows look is not overwritten on first enable.
7. Persist the full color map under `~/.config/omarchy/` (plugin settings in `shell.json` + a state file for snapshots).
8. IPC for scripts and Fn remaps: toggle, off, restore, set base, set group, set key, brightness, theme-sync.
9. Panel includes a **GS75 schematic** (ISO-capable; this machine’s keycaps are Spanish ISO even if xkb is `us`) so groups and individual keys can be assigned colors without a config file. Import/export of the map as JSON (and msi-perkeyrgb-style text).
10. Ship the photo-derived map as a named preset, e.g. `gs75-photo`, used as the first hardware acceptance test.

### Explicit non-goals for v1

- Live hardware animation / breathe / reactive / colorshift packets (msi-perkeyrgb pulled these for safety)
- A SteelSeries Engine clone with drag-drop image-to-keyboard mapping from a photo
- Macros, GameSense, PrismSync
- Mice, headsets, ALC lightbars (ALC can be a later driver)
- Replacing the built-in keyboard-layout widget
- Shipping as a first-party `omarchy.*` plugin
- Binding OpenRGB as a required dependency

Per-key **steady** mapping is in v1. A full visual “painter with every Engine effect” is not.

## Hardware matrix

### Integrated (KLC) — primary, this machine

USB vendor `1038` (SteelSeries). Known keyboard PIDs:

| PID | Name | Notes |
|---|---|---|
| `1122` | KLC | GS75 Stealth 8SF (this laptop). msi-perkeyrgb default ID. `--model GS75` |
| `113a` | KLC | Later Stealth / Vector / GP66 |
| others in the same KLC family | treat as KLC if HID report layout matches |

Protocol (already reverse-engineered; GS75 is a listed msi-perkeyrgb model):

- Feature report ~524 bytes, opcode `0x0e` / `0x0c` depending on generation
- Commit packet 64 bytes, opcode `0x09`
- Regions: alphanum, enter, modifiers, numpad — packets carry **per-key** RGB, not 3-zone
- Two HID interfaces; RGB is **not** the typing interface
- Profile lives in **controller memory**; Linux does not need a daemon for lights to stay as last written
- Linux cannot read the current per-key map back from the controller; the plugin is write-only plus its own snapshot
- GS75 shares the GE63/GE73/GE75/GS63 keymap in msi-perkeyrgb; stock aliases (`arrows`, `numpad`, `f_row`, `characters`, `fn`) are reused. v1 adds `wasd`, `nav`, `numpad_ops` because the photo needs red arrows/nav/ops without recoloring numpad digits.

Kernel note: recent `hid-steelseries` can bind MSI KLC and expose `steelseries::kbd_backlight` as a **single** multicolor LED (one RGB for every key). That **cannot** reproduce the photo. Per-key **HID userspace is mandatory** for v1.

If LED class later binds:

1. Do **not** switch the photo profile onto LED class (it would flatten cyan+red to one color).
2. HID userspace remains the lighting backend for maps with more than one color.
3. LED class may only be used for global brightness if it can sit beside hidraw without stealing the RGB interface. If the kernel driver claims the device and hidraw disappears, document that as a blocker and keep HID (unbind/rebind) rather than silently degrading to one color.

### External (Apex) — same plugin, second driver

Apex 3/5/7/Pro/9 (and TKL/mini) use a **different** HID protocol from KLC. OpenRGB already has Apex controllers in-tree.

v1 Apex path: optional **OpenRGB SDK client** (same idea as OmaRGB’s bridge), used **only** for devices the KLC driver does not claim. If OpenRGB is missing, the panel lists the USB device as “detected, Apex backend needs OpenRGB” rather than failing the whole plugin.

v1.1 (after KLC is solid): native Apex HID in the same Python bridge so OpenRGB is not required for common Apex PIDs.

## Architecture

```
Panel.qml (bar widget + KeyboardPanel)
    │
Service.qml  (one per shell; owns the bridge process)
    │  JSON lines on stdin/stdout
bridge/steelseries_bridge.py
    ├── detect.py          USB/HID scan, claim policy
    ├── drivers/klc_hid.py     msi-perkeyrgb-style packets
    ├── drivers/klc_leds.py    sysfs LED class if present
    ├── drivers/apex_openrgb.py  optional SDK
    ├── keymap.py          GS75 groups, key names, Linux keycodes
    └── snapshot.py        last plugin-applied color map
```

QML has no TCP/HID. Follow OmaRGB: spawn a Python bridge, exchange JSON lines, re-read after writes so the panel shows hardware truth rather than optimistic color. Coalesce color-slider drags.

### Claim policy

- One plugin owns lighting for a given `vid:pid`.
- KLC HID / LED class wins over OpenRGB for KLC PIDs so OmaRGB and this plugin cannot both paint the laptop deck.
- Apex goes to OpenRGB only if this plugin’s Apex driver is enabled **and** OpenRGB actually reports the device.
- Detection is read-only. Opening the panel must not send a color packet.

### Permissions

Today `/dev/hidraw0` and `/dev/hidraw1` are `root:root 600`. The plugin will not work without a udev rule.

Ship `99-steelseries-keyboard.rules` matching SteelSeries vendor `1038` keyboard PIDs, `MODE="0660"`, `GROUP="input"` (or `plugdev`). Document: copy to `/etc/udev/rules.d/`, reload, replug not required for built-in KLC (trigger udev). Do **not** install the rule during `omarchy plugin add`; the panel shows a “grant access” action that opens a terminal with the exact commands (same pattern as OmaRGB’s OpenRGB installer).

hidapi: prefer **libusb backend** for KLC (msi-klc documents hidraw issues). Detach kernel driver only on the RGB interface, never on the typing interface.

### Theme integration

Do **not** patch `/usr/share/omarchy/bin/omarchy-theme-set-keyboard`. That file is package-owned.

Two sync paths, both opt-in:

1. Plugin setting `themeSync` (default false). Service watches Omarchy current theme (`~/.local/state/omarchy/current/theme/keyboard.rgb` or shell theme singleton) and pushes accent when the user enabled sync.
2. Optional user hook later: `omarchy hook install theme-set` calling plugin IPC. Not required if the service already watches theme state.

When theme sync is off, theme changes leave the onboard/Windows look alone.

### Brightness keys

Stock binds (`XF86KbdBrightnessUp/Down`) call `omarchy-brightness-keyboard`, which exits on this laptop. v1 does not edit Hyprland defaults.

Document a user bind that calls plugin IPC. v1.1 can install a **user** Hyprland snippet under `~/.config/hypr/` only if the user opts in from the panel (“use Fn brightness keys”). Never write `/usr/share/omarchy/`.

Sleep: stock `keyboard-backlight` sleep hook only hits sysfs `*kbd_backlight*`. If LED class is absent, a later hook can black the KLC over HID before hibernate. Not v1 unless testing shows hang (ASUS-specific comment in the stock hook).

## UX

Follow first-party `KeyboardPanel` + OmaRGB:

**Bar**

- Glyph: keyboard with light. Color = last known plugin color.
- If lights are on from Windows and plugin never wrote: glyph on, but color chip is “unknown” (outline, not a fake hex).
- Left click: open panel.
- Right click: lights off (stealth). Does not guess a restore color if none was snapshotted.
- Middle click: toggle theme sync (only after user has used the panel once, so a mis-click does not paint the theme over Windows).

**Panel**

1. Device list (usually one row on this laptop).
2. Power (off / on). On without a snapshot = “leave onboard as-is” if we never wrote; if we wrote, re-apply the full color map.
3. Brightness slider (0–100), disabled until the plugin has applied a map at least once **or** LED class reports brightness.
4. Accent swatch + palette + hex field, applied to the **current target**: whole board, a named group, or the selected key(s).
5. Compact GS75 layout schematic (ISO extra key / Alt Gr). Click a group chip (`Arrows`, `Nav`, `Numpad ops`, `WASD`, …) or click keys on the schematic to set the target. Selected keys preview the color before Apply. A “Load photo preset” action applies the accepted cyan/red map.
6. “Follow theme accent” toggle, default off, with a one-line warning: *This replaces the profile saved from Windows.* Theme sync default = base fill only.
7. Empty/error states: no device, no hidraw permission, Apex present but OpenRGB missing.

Keyboard navigation: `j/k` devices, `h/l` brightness, `o` off, `t` theme sync, `Esc` close. Match OmaRGB / Bluetooth.

Settings schema in `manifest.json` (`barWidget.schema`): `themeSync` (bool, false), `vividAccent` (bool, true), `apexBackend` (bool, true).

## Safety

This is HID to a firmware controller. Constraints:

- v1 writes **steady per-key colors + brightness + off only**. No effect packets (`0x0b` etc.).
- First run is detect-only. Enabling the plugin must not send HID.
- First apply snapshots “plugin took ownership” as a **full key→color map**. Restore can only restore plugin snapshots, never the original Windows profile (Linux cannot read KLC onboard memory).
- UI copy must say that once you apply a map, the Windows look is gone until you set it again in SteelSeries Engine on Windows **or** re-enter the same map here.
- Validate hex and brightness in the bridge, not only in QML.
- Rate-limit writes. No full 524-byte storms while dragging.
- Refuse to run the bridge as root. udev, not sudo.
- Plugin folder: no symlinks (validator rejects them), `schemaVersion: 1`, id not `omarchy.*`.

## Repo / install shape

Community plugin, git-installable:

```text
omarchy plugin add <git-url> --enable
```

Layout (mirrors OmaRGB so the shell validator is happy):

- `manifest.json`
- `Service.qml`
- `Panel.qml`
- `Model.js`
- `bridge/` Python, stdlib + hidapi only for KLC
- `udev/99-steelseries-keyboard.rules` (documented, not auto-copied into `/etc`)
- `README.md` with GS75 and Apex test notes
- `tests/` for packet builders and JSON protocol against a fake hid device

Python 3 is already on Omarchy. hidapi is an extra package (`python-hidapi` / `hidapi`). OpenRGB is optional.

## Implementation phases (when coding starts; not this turn)

1. **Probe** — enumerate `1038:*` HID, classify KLC vs Apex vs other, print JSON. No writes. Verify on this GS75 (`1038:1122`, two interfaces, firmware 2.31).
2. **Permissions** — udev rule + panel “needs access” state.
3. **KLC write path** — off, base fill, group colors, per-key overrides, brightness scale, snapshot/restore. Manual test: mixed map visible (e.g. WASD ≠ arrows ≠ rest); reboot still shows last plugin map.
4. **Shell plugin** — service + bar widget + panel with schematic + group chips, IPC, settings. `omarchy plugin validate` clean.
5. **Theme sync** — opt-in only; default preserves Windows profile.
6. **Apex** — OpenRGB optional backend; degrade if missing.
7. **Fn brightness** — documented user bind; optional Hyprland user snippet.
8. **Hardening** — tests for packets, no-root, no-write-on-start, claim policy vs OmaRGB.

## Validation on this machine (later)

- Plugin enable does **not** change the current Windows lighting.
- Applying the `gs75-photo` map matches `/home/gaston4kd/Pictures/keyboard.png`: cyan base, red Esc/Tab/Fn/Win, red arrows + Ins/Home/PgUp/Del/End/PgDn, red numpad NumLock/`/`/`*`/`-`/`+`, cyan numpad digits.
- After a user-chosen map (base + at least one group + one per-key override), those keys match; reboot keeps the map.
- Off then restore returns the plugin map, not a single fill and not a rainbow default.
- Theme switch with sync off: lights unchanged.
- Theme switch with sync on: lights follow `keyboard.rgb`.
- Typing, Fn combos, and touchpad unaffected.
- `omarchy plugin validate` and `omarchy plugin enable steelseries.keyboard` succeed.
- If OmaRGB is installed later, KLC is not double-driven.

## Risks

- KLC firmware variants (`1122` vs `113a`) need a PID table and a `--model` equivalent (GS75 vs GS65 key maps). Wrong map = wrong keys lit, not a brick, but ugly.
- Cannot round-trip the Windows profile. Honesty in the UI is the mitigation.
- hidraw vs libusb detach can steal the RGB interface; must not detach the input interface.
- OpenRGB Apex support is per-model; some Apex boards will show “unsupported” until native HID exists.
- Kernel `hid-steelseries` MSI RGB, if it starts binding after an Omarchy kernel update, will hide hidraw from userspace. LED-class backend must be ready or the plugin “loses” the device.

## Decision summary

1. **Lighting plugin**, not layout / OSK / macros — that is the actual gap.
2. **Native KLC HID first**, OpenRGB only as an Apex helper — because this hardware is KLC and OpenRGB does not support it yet.
3. **Detect-only until the user paints** — preserve the Windows onboard profile.
4. **Steady per-key maps in v1** — skip hardware animation effects; do not reduce “solid” to a single board color.
5. **Third-party `steelseries.keyboard`** — do not patch Omarchy package files.
6. **Service + bar-widget** — same shape as OmaRGB and Bluetooth.

## Out of scope until asked

- Writing any QML, Python, udev, or hooks
- Installing hidapi, OpenRGB, or msi-perkeyrgb
- Enabling the plugin
- Changing Hyprland binds
- Upstreaming into Omarchy
