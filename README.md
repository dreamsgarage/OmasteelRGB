# OmasteelRGB

Omarchy 4 shell plugin for SteelSeries keyboard lighting.

Plugin id: `steelseries.keyboard`  
Status: **v1 plugin built, running on the reference GS75 (2026-09-21).** Protocol validated on hardware
2026-09-12. Python bridge, bar widget and panel are in; theme sync, the clickable schematic and Apex support
are not (see [docs/v1-implementation-guide.md](docs/v1-implementation-guide.md), phases 7 and 8).

## What this is

A third-party Omarchy shell plugin that controls **per-key solid RGB** on:

- Integrated MSI SteelSeries KLC (this GS75 Stealth 8SF, USB `1038:1122`)
- External SteelSeries Apex-family keyboards

Typing already works. The gap is lighting. The laptop keyboard currently replays a Windows SteelSeries Engine profile from onboard memory. The plugin must not overwrite that until the user applies a map.

## v1 in one sentence

Steady (non-animated) colors, **many colors at once**, as a stack of base fill + named groups + per-key overrides — matching the reference photo, not a single wash across the board. **Confirmed working on real hardware.**

## Documents

| File | Contents |
|---|---|
| [docs/v1-spec.md](docs/v1-spec.md) | Product definition, lighting model, capabilities, non-goals |
| [docs/v1-design.md](docs/v1-design.md) | Architecture, backends, UX, safety, install shape |
| [docs/v1-acceptance.md](docs/v1-acceptance.md) | Photo fixture, `gs75-photo` map, hardware checks |
| [docs/v1-implementation-guide.md](docs/v1-implementation-guide.md) | **Build order, protocol details, gotchas** |
| [docs/approved-plan.md](docs/approved-plan.md) | Full approved plan as captured (historical) |
| [presets/gs75-photo.json](presets/gs75-photo.json) | Machine-readable acceptance preset |
| [presets/gs75-custom.json](presets/gs75-custom.json) | Daily map: full red top row |
| [presets/perkeyrgb/](presets/perkeyrgb/) | Same maps as msi-perkeyrgb configs (hardware-tested) |
| [udev/70-steelseries-klc.rules](udev/70-steelseries-klc.rules) | hidraw access via `uaccess`, no sudo at runtime |
| [docs/assets/keyboard.png](docs/assets/keyboard.png) | Reference photo of the Windows-saved layout |

## Reference photo

![GS75 SteelSeries KLC: blue-violet base, red Esc/Tab/Fn/Win/nav/numpad ops](docs/assets/keyboard.png)

The base colour reads cyan in this photo but is actually blue-violet (`#4a5cff`); the camera carries a blue-cast.

## Layout

| Path | Role |
|---|---|
| `manifest.json` | Plugin manifest: `kinds: ["bar-widget"]`, entry point `Panel.qml` |
| `Panel.qml` | Bar icon + popup panel. Left = panel, right = lights off, middle = restore. |
| `Service.qml` | Owns the bridge process; JSON lines over stdin/stdout, re-reads state after every write |
| `Model.js` | Pure helpers: hex validation, palette, group labels, the udev install commands |
| `bridge/` | Python: detect, keymap, colour model, KLC HID driver, snapshot, JSON IPC |
| `keymaps/` | Per-model key names, X11→HID translation and groups — data, not code |
| `presets/` | Shipped colour maps, listed in the panel |
| `tests/` | `python -m pytest`; nothing here opens the keyboard |

## Install

```bash
omarchy plugin add <git url> --enable
```

Then grant the session user access to the keyboard's HID node — once, with sudo, never at runtime.
The panel shows these exact commands (and a copy button) while access is missing:

```bash
sudo install -m644 -o root -g root ~/.config/omarchy/plugins/steelseries.keyboard/udev/70-steelseries-klc.rules /etc/udev/rules.d/
sudo rm -f /etc/udev/rules.d/99-msi-rgb.rules     # msi-perkeyrgb's world-writable rule, if present
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=hidraw --action=add
```

The rule uses `TAG+="uaccess"` with `MODE="0660"`; the comments in the rule file explain why both matter.
Enabling the plugin sends nothing to the keyboard. The first colour you apply replaces the profile the
controller replays from onboard memory, and Linux cannot read that profile back — the panel says so and
asks before that first write.

Keyboard in the panel: `o` power, `r` restore, `p` photo preset, `b` board target, `e` edit a key, `Esc` close.
IPC: `omarchy-shell steelseries.keyboard status|off|restore|preset <id>|setBase <hex>|setGroup <group> <hex>|setKey <key> <hex>`.

There is no software brightness. The chassis `Fn` keys dim the backlight in firmware, and a plugin-side scale
fought them (and the panel's `h`/`l` keys), so it was removed.

## Development

```bash
python -m pytest
rsync -a --delete --exclude .git --exclude '.venv*' --exclude .pytest_cache --exclude __pycache__ \
  ./ ~/.config/omarchy/plugins/steelseries.keyboard/
omarchy plugin validate ~/.config/omarchy/plugins/steelseries.keyboard
```

The shell hot-reloads the plugin directory, but only re-instantiates objects: an edited `.qml` that the
engine has already compiled keeps serving the old version (the reload's `Qt.clearComponentCache()` call is
guarded on the function existing, and it does not). After changing `Panel.qml` or `Service.qml`, run
`omarchy restart shell`. New files, `Model.js`, presets and the bridge pick up on plain reload.
`omarchy plugin validate` refuses any folder containing a symlink, which is why it is run on the installed
copy rather than a checkout with a `.venv`. Shell log: `journalctl --user _COMM=quickshell`.

## License

MIT. See [LICENSE](LICENSE).
