# Publish guide

How OmasteelRGB is distributed, what was checked before calling 0.1.0 publishable, and the procedure for
each release. Verified on Omarchy 4.0.4 on 2026-09-21.

## What publishing means for an Omarchy plugin

Omarchy 4 has no central plugin registry. A plugin is published by having a public git repository that
`omarchy plugin add` can clone:

```bash
omarchy plugin add https://github.com/dreamsgarage/OmasteelRGB.git --enable
```

Reading `omarchy-plugin-add` (in `/usr/share/omarchy/bin`, on PATH) shows what that does:

1. Warns the user that plugins run unsandboxed inside `omarchy-shell` and asks to confirm.
2. Clones the URL into a staging folder under `~/.config/omarchy/plugins/`.
3. Runs `omarchy plugin validate` on it and refuses the plugin if that fails.
4. Refuses if the manifest `id` is already used by any folder in the plugins directory.
5. Moves the clone to `~/.config/omarchy/plugins/<id>/`, rescans, and with `--enable` adds the widget to the
   bar (asking which section when interactive; the manifest's `barWidget.defaultSection` is the default).

`omarchy plugin update <id>` fetches `origin HEAD`, shows the diff, fast-forwards, validates the result and
rolls back if validation fails. It refuses if the checkout cannot fast-forward. Two consequences for us:

- **Never force-push `main`.** Every installed copy tracks it and a rewritten history breaks their update.
- The repository must stay valid at every commit on `main`, not only at tags.

So "publishing" is: the repository is public, `main` validates, the README explains install and the udev
step, and the manifest `version` matches what we announce.

## What the validator checks

`omarchy-plugin-validate` mirrors the shell's `PluginRegistry.qml`:

- `manifest.json` is valid JSON with `schemaVersion` exactly the number `1`.
- Required fields `id`, `name`, `version`, `kinds`, `entryPoints`.
- `id` matches `^[A-Za-z0-9][A-Za-z0-9._-]*$`, has no `..`, and is not in the reserved `omarchy.*`
  namespace. Ours is `steelseries.keyboard`.
- `kinds` is a non-empty array; each kind that needs an entry point has one (`bar-widget` needs
  `entryPoints.barWidget`). Ours is `Panel.qml`.
- Entry points are relative, contain no `..`, and exist.
- `barWidget.defaultSection`, if present, is `left`, `center` or `right`. Ours is `right`.
- **No symlink anywhere in the folder** (`.git` excluded). A Python virtualenv contains `lib64 -> lib`, so
  a working copy with `.venv/` fails validation. `.venv/` and `.venv-*/` are in `.gitignore`, so a clone is
  clean; validate a clone or a `git archive` export, never the working folder.

## Readiness checks for 0.1.0

All run on 2026-09-21 against `main` after the rename to OmasteelRGB.

| Check | How | Result |
|---|---|---|
| Unit tests | `python3 -m pytest -q` | 102 passed |
| Manifest and layout | `git archive HEAD` into an empty folder, `omarchy plugin validate` on it | valid |
| Real install path | removed the rsync dev copy, `omarchy plugin add <url> --enable --yes` | cloned, validated, enabled in the right section |
| Update path | `omarchy plugin update steelseries.keyboard --yes` on the fresh clone | "up to date" |
| Shell loads it | `omarchy-shell steelseries.keyboard status` after the add | device accessible, snapshot present, lights on |
| Bridge runs from the install | `pgrep -af plugins/steelseries.keyboard/bridge` | one bridge per bar instance |
| Hardware writes | off, restore, preset apply, group and key edits through the panel and IPC | all reports accepted by the controller; see the commit messages for what each fixed |
| Docs match behaviour | README install URL, shortcuts, IPC list, no-brightness note | updated in this release |

Things the checks do **not** cover, and that the announcement should say plainly:

- Only the GS75 keymap ships. The X11-to-HID table was ported from msi-perkeyrgb's GE63 family and the
  keymap lists those models, but only the GS75 Stealth 8SF was tested. Other MSI decks with the SteelSeries
  KLC (USB `1038:1122` or `1038:113a`) probably work; group membership may differ.
- Apex-family external keyboards are detected and reported, not driven. That backend is OpenRGB and is not
  in v1.
- The first write replaces the profile the controller replays from onboard memory, and Linux cannot read
  that profile back. The panel says so and asks before the first write. Say it in the README too (it does).
- Theme sync, the clickable schematic and any animated effects are not included. Effects (opcode `0x0b`)
  are deliberately not implemented; a malformed effect packet bricked a backlight upstream.
- The udev rule is a manual step with `sudo`. The panel shows the exact commands while access is missing.

## The user's install, start to finish

1. `omarchy plugin add https://github.com/dreamsgarage/OmasteelRGB.git --enable`
2. Open the panel from the bar icon. If it says "Needs device access", run the four commands it shows:

   ```bash
   sudo install -m644 -o root -g root ~/.config/omarchy/plugins/steelseries.keyboard/udev/70-steelseries-klc.rules /etc/udev/rules.d/
   sudo rm -f /etc/udev/rules.d/99-msi-rgb.rules
   sudo udevadm control --reload
   sudo udevadm trigger --subsystem-match=hidraw --action=add
   ```

   The rule needs `MODE="0660"` together with `TAG+="uaccess"`; `0600` or a missing `MODE` leaves the ACL
   ineffective. Check with `getfacl -p /dev/hidrawN` and look for the absence of `#effective:---`.
3. Pick a target and colour, or load a preset. The first write asks for confirmation once.
4. Later: `omarchy plugin update steelseries.keyboard`.

## Release procedure

1. Finish the work on `main` with tests green: `python3 -m pytest -q`.
2. Bump `version` in `manifest.json` (semver). Update the README status line if what ships changed.
3. Validate a clean export, not the working folder:

   ```bash
   rm -rf /tmp/omasteelrgb-export && mkdir /tmp/omasteelrgb-export
   git archive HEAD | tar -x -C /tmp/omasteelrgb-export
   omarchy plugin validate /tmp/omasteelrgb-export
   ```

4. Commit and push `main`. Tag the release and push the tag:

   ```bash
   git tag -a v0.1.0 -m "OmasteelRGB 0.1.0"
   git push origin main --tags
   ```

   Tags are for humans and the GitHub release page; `omarchy plugin update` follows `main`.
5. Confirm the update path on this machine, which has the git-managed install:

   ```bash
   omarchy plugin update steelseries.keyboard
   omarchy restart shell     # only needed when a .qml changed
   ```

6. Optionally create a GitHub release from the tag with the changelog. `gh release create v0.1.0 --generate-notes`.

To test the full install path again on this machine, the existing install has to go first, because the
add command refuses an id that any folder in the plugins directory already uses:

```bash
cp -a ~/.config/omarchy/plugins/steelseries.keyboard /tmp/steelseries.keyboard.bak
rm -rf ~/.config/omarchy/plugins/steelseries.keyboard
omarchy plugin add https://github.com/dreamsgarage/OmasteelRGB.git --enable
```

The enabled state and bar placement live in `~/.config/omarchy/shell.json` and survive the remove.
The colour snapshot lives in `~/.local/state/omarchy/steelseries-keyboard/snapshot.json` and also survives.

## Development against the git-managed install

The rsync dev loop still works on top of the clone; `--exclude .git` protects the checkout:

```bash
rsync -a --delete --exclude .git --exclude '.venv*' --exclude .pytest_cache --exclude __pycache__ \
  ./ ~/.config/omarchy/plugins/steelseries.keyboard/
```

That leaves the install dirty, and `omarchy plugin update` will refuse to fast-forward until it is clean.
Reset it before updating:

```bash
git -C ~/.config/omarchy/plugins/steelseries.keyboard checkout -- . && git -C ~/.config/omarchy/plugins/steelseries.keyboard clean -fd
```

## Repository hygiene

- Public repository, MIT licence in `LICENSE`, attribution to msi-perkeyrgb (MIT, Askannz) kept in
  `bridge/klc_hid.py` and `keymaps/gs75.json`.
- GitHub description: "Omarchy shell plugin for per-key RGB on the MSI SteelSeries KLC keyboard (plugin id
  steelseries.keyboard)".
- Nothing generated is committed: `.gitignore` covers virtualenvs, `__pycache__`, `.pytest_cache`.
- `tests/` and `docs/` ship inside the plugin folder. They are small and harmless to the shell, which only
  loads `Panel.qml`; keeping them lets a user run the tests on the installed copy.

## Troubleshooting for issue reports

- Shell log: `journalctl --user _COMM=quickshell`.
- Bridge by hand, from the install folder: `echo '{"cmd":"state"}' | python3 bridge/steelseries_bridge.py`.
- Permission problems: `ls -l /dev/hidraw*` should show `crw-rw----+` on the two KLC nodes and `getfacl`
  should list the session user with effective `rw-`.
- A half-lit board after a write means the controller dropped a report. The driver paces reports (10 ms
  each, 250 ms after a commit) and fails loudly on a refused report; if it still happens, write the map
  again and open an issue with the shell log.
