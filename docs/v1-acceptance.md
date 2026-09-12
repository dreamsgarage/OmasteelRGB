# omastellrgb v1 acceptance

**Status:** approved  
Reference machine: MSI GS75 Stealth 8SF, Omarchy 4.0.3, SteelSeries KLC `1038:1122`.

## Photo fixture

Access confirmed: original file `/home/gaston4kd/Pictures/keyboard.png`. Copy in this repo: [assets/keyboard.png](assets/keyboard.png).

![Reference lighting](assets/keyboard.png)

Physical legends are Spanish ISO (Ñ, Alt Gr, €). Software xkb on the reference machine is `us`. Lighting is position-based; the schematic must still be ISO-capable.

This is **not** a WASD-highlight layout.

| Role | Color | Keys |
|---|---|---|
| Base | cyan / light blue | letters, number row, F-row, Caps, Shifts, Ctrl, Alt, Alt Gr, Space, Enter, Backspace, punctuation, PrtSc, ScrLk, Pause, numpad digits 0–9, numpad Enter / Del |
| Red | red | Esc, Tab, Fn, Windows, arrows, Ins / Home / PgUp / Del / End / PgDn, Num Lock, numpad `/` `*` `-` `+` |

Approximate hex (tweakable):

- base `#00b4ff`
- red `#ff2a2a`

Machine-readable preset: [../presets/gs75-photo.json](../presets/gs75-photo.json).

```text
all          #00b4ff
nav          #ff2a2a
arrows       #ff2a2a
numpad_ops   #ff2a2a
Esc Tab Fn Super  #ff2a2a
```

A single-color backend (kernel `steelseries::kbd_backlight`) **cannot** pass this fixture.

## Hardware checks (later, when implemented)

- Plugin enable does **not** change the current Windows lighting.
- Applying `gs75-photo` matches the photo: cyan base; red Esc/Tab/Fn/Win; red arrows + Ins/Home/PgUp/Del/End/PgDn; red numpad NumLock/`/`/`*`/`-`/`+`; cyan numpad digits.
- After a user-chosen map (base + at least one group + one per-key override), those keys match; reboot keeps the map.
- Off then restore returns the plugin map, not a single fill and not a rainbow default.
- Theme switch with sync off: lights unchanged.
- Theme switch with sync on: base follows `keyboard.rgb`; groups/overrides remain unless the user chose paint-entire-board.
- Typing, Fn combos, and touchpad unaffected.
- `omarchy plugin validate` and `omarchy plugin enable steelseries.keyboard` succeed.
- If OmaRGB is installed later, KLC is not double-driven.

## Probe facts from the reference machine

These were collected before the spec was approved and must still hold:

- DMI product: GS75 Stealth 8SF, board MS-17G1, SKU 17G1.1
- USB: `SteelSeries ApS SteelSeries KLC` `1038:1122`, firmware 2.31, two HID interfaces, USB Full Speed, 300 mA
- HID driver: `hid-generic` (not `hid-steelseries`)
- hidraw: `/dev/hidraw0` and `/dev/hidraw1`, `root:root 600`
- No `/sys/class/leds/*kbd_backlight*`
- Discrete NVIDIA GPU powered off for battery; that is unrelated to keyboard lighting
