# Changelog

## 0.1.0 — unreleased

First release. Everything below was exercised on an MSI GS75 Stealth 8SF (SteelSeries KLC, USB `1038:1122`)
running Omarchy 4.0.4.

- Bar widget and panel: base colour, eleven named groups, single keys, a swatch palette and a hex field,
  presets, lights off and restore, a one-time confirmation before the first write.
- Layered colour model: base fill, groups (smallest wins where they overlap), per-key overrides. A group edit
  removes the per-key overrides and nested groups it covers so the edit is always visible.
- Keymaps for every MSI model the msi-perkeyrgb ecosystem knows: the GE63 family (GE63, GE73, GE75, GS63,
  GS73, GS75, GX63, GT63, GL63), GS65 (Home and End LEDs) and GS66 (power-key LED). Keymaps can extend one
  another.
- Model detection from the DMI product name, with a panel picker and an IPC override that persists.
- HID driver paced like upstream (10 ms per report, 250 ms after a commit) with every return value checked,
  so a dropped region packet is an error instead of a silently half-lit board.
- Only the steady-colour and commit packets are sent. Hardware effects are deliberately not implemented.
- IPC: `status`, `off`, `restore`, `preset`, `setBase`, `setGroup`, `setKey`, `setModel`, `models`.
- udev rule with `uaccess` so the runtime never needs sudo or pkexec.

Not in this release: theme sync, animated effects, external SteelSeries Apex keyboards (detected, not
driven), software brightness (removed; the chassis `Fn` keys dim in firmware).
