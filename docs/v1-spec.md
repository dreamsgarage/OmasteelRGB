# omastellrgb v1 product spec

**Status:** approved  
**Plugin id:** `steelseries.keyboard`  
**Name:** SteelSeries Keyboard  
**Kinds:** `service` + `bar-widget`  
**Default bar section:** right  
**Target:** Omarchy 4 / Quattro (validated against 4.0.3)

## Goal

Control lighting on SteelSeries keyboards from the Omarchy bar:

- **Integrated** MSI laptop decks (SteelSeries KLC). Primary hardware: MSI GS75 Stealth 8SF, USB `1038:1122`.
- **External** Apex-family USB keyboards (Apex 3 / 5 / 7 / Pro / 9, TKL and full-size).

Typing already works through HID. This product does not replace `omarchy.keyboard-layout`.

## Solid colors, many at once

**“Solid” means steady (non-animated), not one color for the whole board.**

Each key or group holds its own fixed hex. The reference photo uses two colors (cyan + red). v1 is **not** capped at two. Any number of distinct solid colors is valid (WASD green, arrows amber, Esc red, rest cyan, and so on).

v1 does **not** write breathe, wave, reactive, or other hardware animation packets.

The KLC is per-key RGB. Linux cannot read the current Windows Engine map off the controller. The plugin recreates a map from saved state.

## Lighting model

A profile is a stack. Later layers win.

1. **Base fill** — one color for every key, or off.
2. **Named groups** — each group has its own solid color.
3. **Per-key overrides** — individual keys by name or Linux keycode.

Brightness is a global 0–100 scale applied after the map.

### Built-in groups (GS75, US and ISO position maps)

| Group | Keys |
|---|---|
| `wasd` | W A S D |
| `arrows` | Up Down Left Right |
| `nav` | Ins Home PgUp Del End PgDn |
| `numpad` | numpad digits, numpad Enter, numpad Del |
| `numpad_ops` | NumLock `/` `*` `-` `+` |
| `num_row` | `` ` `` 1–0 `-` `=` |
| `f_row` | F1–F12 |
| `modifiers` | Ctrl Alt Shift (not Super) |
| `fn` | Fn |
| `enter_esc` | Enter Esc |
| `characters` | letter/punctuation block excluding num row |

### Photo profile (must be representable and writable)

See [v1-acceptance.md](v1-acceptance.md) and [../presets/gs75-photo.json](../presets/gs75-photo.json).

```text
all          #00b4ff
nav          #ff2a2a
arrows       #ff2a2a
numpad_ops   #ff2a2a
Esc Tab Fn Super  #ff2a2a
```

Numpad **digits** stay on the base color. Theme sync, when on, may replace **only the base fill** by default; it must not silently wipe group or per-key overrides unless the user picks “paint entire board.”

The on-disk snapshot is this full map, not a single hex. Restore reapplies the map. IPC can set a group or a key, not only the whole board.

## v1 capabilities

1. Detect connected SteelSeries keyboards (KLC and Apex) without writing to them.
2. Show identity: name, USB `vid:pid`, backend, lights known vs “onboard / unknown”.
3. Off / restore (stealth). Restore uses a snapshot **this plugin** wrote. If it never wrote, say so — Linux cannot restore the original Windows look.
4. Steady color map: base + groups + per-key overrides.
5. Brightness as a global RGB scale on top of the map.
6. Opt-in follow Omarchy theme accent for the base fill (optional groups). Default **off**.
7. Persist the full color map (plugin settings in `shell.json` + a state file).
8. IPC: toggle, off, restore, set base, set group, set key, brightness, theme-sync.
9. GS75 schematic (ISO-capable; this machine’s keycaps are Spanish ISO even if xkb is `us`). Group chips and click-to-select keys. Import/export JSON and msi-perkeyrgb-style text.
10. Named preset `gs75-photo` as the first hardware acceptance test.

Enabling the plugin must **not** send HID. First run is detect-only so the Windows onboard profile survives.

## Non-goals for v1

- Hardware animation / breathe / reactive / colorshift packets
- SteelSeries Engine clone with drag-drop image-to-keyboard mapping
- Macros, GameSense, PrismSync
- Mice, headsets, ALC lightbars
- Replacing `omarchy.keyboard-layout`
- Shipping as first-party `omarchy.*`
- Requiring OpenRGB for the laptop KLC

Per-key **steady** mapping is in v1. A full Engine-style painter with every effect is not.

## Why not existing pieces

| Existing piece | Why it is not this product |
|---|---|
| `omarchy.keyboard-layout` | Layout indicator only |
| `omarchy-theme-set-keyboard` | ASUS `asusctl` + Framework `qmk_hid` only |
| `omarchy brightness keyboard` | Needs `/sys/class/leds/*kbd_backlight*`; GS75 has none |
| OmaRGB | Right UX shape, wrong backend. Stock OpenRGB does not enumerate KLC `1038:1122` |
| `steelseries.mouse-controller` | Rival mice via `rivalcfg` |
| `msi-perkeyrgb` CLI | Correct KLC protocol, no Omarchy UI; effects disabled for safety |
| `msi-klc` / `msiklm` | Older 3-zone MSI boards |

Do not fork OmaRGB. Do not require OpenRGB for the laptop keyboard. Do not run SteelSeries GG under Wine.

## Decision summary

1. Lighting plugin, not layout / OSK / macros.
2. Native KLC HID first; OpenRGB only as an Apex helper.
3. Detect-only until the user paints.
4. Steady per-key maps in v1; “solid” is not a single board color.
5. Third-party `steelseries.keyboard`; do not patch Omarchy package files.
6. Service + bar-widget, same shape as OmaRGB and Bluetooth.
