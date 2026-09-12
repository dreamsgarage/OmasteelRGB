# omastellrgb

Omarchy 4 plugin **specs and design** for SteelSeries keyboard lighting.

Plugin id (when implemented): `steelseries.keyboard`  
Status: **v1 spec approved** — this repository currently ships design documents, not plugin code.

## What this is

A third-party Omarchy shell plugin that controls **per-key solid RGB** on:

- Integrated MSI SteelSeries KLC (this GS75 Stealth 8SF, USB `1038:1122`)
- External SteelSeries Apex-family keyboards

Typing already works. The gap is lighting. The laptop keyboard currently replays a Windows SteelSeries Engine profile from onboard memory. The plugin must not overwrite that until the user applies a map.

## v1 in one sentence

Steady (non-animated) colors, **many colors at once**, as a stack of base fill + named groups + per-key overrides — matching the reference photo, not a single wash across the board.

## Documents

| File | Contents |
|---|---|
| [docs/v1-spec.md](docs/v1-spec.md) | Product definition, lighting model, capabilities, non-goals |
| [docs/v1-design.md](docs/v1-design.md) | Architecture, backends, UX, safety, install shape |
| [docs/v1-acceptance.md](docs/v1-acceptance.md) | Photo fixture, `gs75-photo` map, hardware checks |
| [docs/approved-plan.md](docs/approved-plan.md) | Full approved plan as captured |
| [presets/gs75-photo.json](presets/gs75-photo.json) | Machine-readable acceptance preset |
| [docs/assets/keyboard.png](docs/assets/keyboard.png) | Reference photo of the Windows-saved layout |

## Reference photo

![GS75 SteelSeries KLC: cyan base, red Esc/Tab/Fn/Win/nav/numpad ops](docs/assets/keyboard.png)

## Not in this repo yet

No QML, Python bridge, udev install, or `omarchy plugin add`. Implementation starts only after this spec drop.

## License

MIT. See [LICENSE](LICENSE).
