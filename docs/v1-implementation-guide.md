# omastellrgb v1 implementation guide

**Status:** ready to build
**Prerequisite:** [v1-spec.md](v1-spec.md), [v1-design.md](v1-design.md), [v1-acceptance.md](v1-acceptance.md)
**Hardware validation:** passed 2026-09-12 — see [v1-acceptance.md](v1-acceptance.md#validation-results--2026-09-12)

## What validation changed

The riskiest assumption in the plan — *can we drive per-key RGB on this controller at all* — is answered. It works,
the GE63-family keymap is correct for the GS75, and typing is unaffected. Three specifics changed:

| Was | Now |
|---|---|
| Base `#00b4ff` (cyan) | `#4a5cff` (blue-violet, hue ~234) |
| `nav` = 6 keys | `nav` = 4 keys; `Home`/`End` have no LED |
| udev `GROUP="input"` | `TAG+="uaccess"` |

You are no longer reverse-engineering a protocol. You are wrapping a known-good one in an Omarchy UI.

## The protocol, concretely

From `msi_perkeyrgb/msiprotocol.py` (MIT — vendoring is permitted, keep the notice).

**Feature report — 524 bytes, one per region:**

```
[0x0e, 0x00, <region_id>, 0x00]          4-byte header
<42 key fragments x 12 bytes>            504 bytes
[0x00 x14, 0x08, 0x39]                   16-byte trailer
```

Each key fragment is 12 bytes:

```
[R, G, B, 0,0,0,0,0,0, 0x01, 0x00, <hid_keycode>]
```

Unused fragment slots are 12 zero bytes. Region ids:

| Region | id |
|---|---|
| `alphanum` | `0x2a` |
| `enter` | `0x0b` |
| `modifiers` | `0x18` |
| `numpad` | `0x24` |

**Commit — 64 bytes:** `[0x09] + [0x00] * 63`, sent once after all four region reports.

Write all four regions, then commit. The controller stores the result in onboard memory, so lighting survives
reboot with no daemon running.

**Do not implement opcode `0x0b` effects.** Upstream reverted them after a malformed packet bricked a backlight
(Askannz/msi-perkeyrgb#24). v1 is steady colors only.

## Keymap indirection

There are two keycode spaces and confusing them is the main source of "wrong key lights up":

- **X11 keycodes** (`9`=Esc, `133`=Super) — what configs and users speak.
- **HID keycodes** — what the packet carries.

`msi_keymaps.py` maps X11 -> HID per model family. The GS75 entry covers
`GE63, GE73, GE75, GS63, GS73, GS75, GX63, GT63, GL63` — 101 keys plus the literal `fn`.

**Make keymaps data, not code.** Ship `keymaps/*.json`, load by model. This is the single highest-leverage
decision in the build: it is what lets a stranger with a GE66 contribute support without touching Python, and
it is the only realistic answer to the portability ceiling documented below.

## Build order

Each phase is independently testable. Do not start a phase before the previous one passes.

### Phase 0 — keymap + color model (no hardware)

Pure functions, fully unit-testable:

```
keymap.py    load_keymap(model) -> {x11_keycode: hid_keycode}
             GROUPS = {"arrows": [...], "nav": [...], ...}
model.py     resolve(base, groups, keys, keymap) -> {x11_keycode: [r,g,b]}
```

`resolve()` implements the stack: base fill, then groups, then per-key overrides.

**Decide group precedence before writing this.** Groups overlap (`wasd` is inside `characters`,
`numpad_ops` overlaps `numpad`). "Later layers win" only orders the three tiers, not two groups against each
other. Pick one and write it down: declared-order (later key in the map wins) or specificity (smaller group
wins). Specificity is more intuitive — `wasd` red over `characters` blue does what a user expects — but
declared-order is simpler to explain and to serialize. Either is fine; silence is not.

**Name the two `Delete` keys distinctly.** `nav` has `Del` and `numpad` has numpad `Del`; the fixture needs them
different colors. Use `Delete` and `KP_Delete`.

Test: resolve `gs75-photo` and assert 102/102 keys addressed, 17 red, numpad digits on base.

### Phase 1 — detect, read-only

```
detect.py    scan() -> [{vid, pid, name, interfaces, backend, hidraw_paths}]
```

Enumerate `1038:*`, classify KLC vs Apex by PID, return JSON. **Open nothing. Write nothing.**

Match by `vid:pid` and interface, never by node index — this machine has three `hidraw` nodes and `hidraw2` is
the touchpad. Verify: `1038:1122`, two interfaces, `hid-generic`.

### Phase 2 — permissions

Ship [../udev/99-steelseries-keyboard.rules](../udev/99-steelseries-keyboard.rules) using `TAG+="uaccess"`.
Do **not** copy it into `/etc` during `omarchy plugin add`. The panel shows a "grant access" state with the exact
commands for the user to run.

The bridge must refuse to run as root.

### Phase 3 — KLC write path

```
drivers/klc_hid.py   build_region_packet(region, {hid_keycode: rgb}) -> bytes
                     commit() -> bytes
                     apply(color_map)
```

Port the packet builders from `msiprotocol.py`. Group the resolved map by region, emit four feature reports, then
the commit packet.

Brightness is a global RGB scale applied *after* resolution — there is no separate backlight channel on this
hardware. Clamp in the bridge, not only in QML.

Rate-limit writes: a 524-byte report per region per frame while dragging a color slider will flood the
controller. Coalesce drags and write on release.

Test against a fake HID device asserting exact byte sequences before touching real hardware.

### Phase 4 — snapshot and restore

First apply writes a full `{key: color}` snapshot plus brightness to
`~/.local/state/omarchy/steelseries-keyboard/snapshot.json`.

Restore reapplies that map. If no snapshot exists, the UI must say *"Linux cannot read the original profile off
this controller"* rather than guessing a color. Define what `off` means relative to `brightness = 0` — they look
identical on this hardware but should not be the same state.

### Phase 5 — JSON IPC

Line-delimited JSON on stdin/stdout. One request per line, one response per line:

```json
{"cmd": "detect"}
{"cmd": "apply", "base": "#4a5cff", "groups": {...}, "keys": {...}, "brightness": 100}
{"cmd": "set_group", "group": "arrows", "color": "#ff2a2a"}
{"cmd": "set_key", "key": "Esc", "color": "#ff2a2a"}
{"cmd": "off"} {"cmd": "restore"} {"cmd": "brightness", "value": 60}
```

Validate hex and ranges here, not only in the UI.

### Phase 6 — shell plugin

`manifest.json` (`schemaVersion: 1`, id `steelseries.keyboard`, kinds `service` + `bar-widget`), `Service.qml`
owning the bridge process, `Panel.qml`, `Model.js`. No symlinks. Mirror OmaRGB's layout so
`omarchy plugin validate` passes.

**Ship the schematic last.** A clickable ISO-capable GS75 keyboard is plausibly more work than the entire driver.
Group chips alone make `gs75-photo` fully expressible — base + three groups + four overrides — so the acceptance
test does not depend on it. Chips first, schematic second.

### Phase 7 — theme sync

Opt-in, default off, base fill only. Watch `~/.local/state/omarchy/current/theme/keyboard.rgb`. Never patch
`/usr/share/omarchy/`. Theme changes with sync off must leave lighting untouched.

### Phase 8 — hardening

Packet builder tests, no-root enforcement, no-write-on-start, claim policy so OmaRGB cannot double-drive the KLC.

## Gotchas found during validation

1. **msi-perkeyrgb crashes on blank lines** in config files — `line.replace(" ", "")[0]` runs before the
   empty-line guard. If you shell out to it or port its parser, emit no blank lines. Unfixed since 2019.
2. **`uaccess` needs a re-trigger** — `udevadm trigger --action=add --subsystem-match=hidraw`. Built-in devices
   cannot be replugged; a reboot may be required. Handle "rule installed but ACL not yet applied" in the UI.
3. **The photo is not a color reference.** It carries a camera blue-cast — its red measures at hue 336 (crimson)
   rather than 0. Acceptance must test key->color *assignment*, not pixel equality.
4. **The original profile is gone and unrecoverable.** Say so plainly in the UI before the first write.

## Portability ceiling

Upstream contains exactly **two** keymaps covering **10** models, all 2018–2019 hardware:

| Keymap | Models |
|---|---|
| A | GE63, GE73, GE75, GS63, GS73, GS75, GX63, GT63, GL63 |
| B | GS65 |

Everything newer — GE66, GP66, Raider, Vector, Stealth 14/16/17, Creator Z16 — has **no keymap**. They often
share PID `1122`/`113a` while arranging keys differently, so the failure is silent: the write succeeds and the
wrong keys light.

Advertise accordingly: *"GS75 and same-generation MSI decks supported; other models experimental pending a
contributed keymap."* Ship the calibration flow — light one key at a time, let the user say which one lit — and
the ceiling becomes a community problem rather than a hardware-acquisition problem.

Apex adds little: OpenRGB already covers 19+ Apex PIDs and OmaRGB already exposes them. Consider deferring Apex
to v1.1 entirely.

## Definition of done for v1

- `omarchy plugin validate` and `omarchy plugin enable steelseries.keyboard` succeed
- Enabling the plugin sends zero HID packets
- `gs75-photo` applies and matches the acceptance table
- A user map (base + one group + one per-key override) applies and survives reboot
- Off then restore returns the plugin map, not a fill and not a rainbow
- Theme switch with sync off leaves lighting untouched
- Typing, Fn combos and touchpad unaffected
- Bridge refuses to run as root
- Packet builders have byte-exact tests against a fake HID device
