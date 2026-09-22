# Publish guide

How OmasteelRGB is distributed, what was checked before calling 0.1.0 publishable, and the procedure for
each release. Verified on Omarchy 4.0.4 on 2026-09-21.

## What publishing means for an Omarchy plugin

Two layers, and they are independent:

1. **Installable from git.** Any public git URL works with `omarchy plugin add`; there is no gatekeeper.
   This is what the checks below verify, and OmasteelRGB is already installable this way:

   ```bash
   omarchy plugin add https://github.com/dreamsgarage/OmasteelRGB.git --enable
   ```

2. **Listed on the marketplace.** Omarchy has an official community marketplace at
   <https://plugins.omarchy.org> (source and registry: <https://github.com/omacom/omarchy-plugin-marketplace>,
   about 3,750 sources listed as of 2026-09-21). Listing is by GitHub issue, reviewed by maintainers. It is
   optional, but it is where users browse, and the Okomart plugin manager reads the same catalog.

Reading `omarchy-plugin-add` (in `/usr/share/omarchy/bin`, on PATH) shows what an install does:

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

## Listing on the marketplace

Rules from the marketplace's `SUBMISSION.md`, `VERIFICATION.md` and `SECURITY.md` (read 2026-09-21):

**Repository requirements**

- Public GitHub repository with one plugin and `manifest.json` at the root. Ours: yes.
- Root README with **installation and removal instructions**. Ours: the Remove section was added for this.
- Root licence file, external dependencies documented. Ours: MIT; `python-hidapi` is named in the README
  requirements, the panel's error text and the bridge.
- Globally unique plugin id outside `omarchy.*`. Ids are permanent and can never be reused, and the
  marketplace prefers a namespaced lowercase id such as `io.github.dreamsgarage.omasteelrgb`. Ours is
  `steelseries.keyboard`, not taken in the registry as of 2026-09-21. Changing it later means every user
  reinstalls, so decide before the first submission.
- Optional root `preview.png` (or jpg, webp, avif); the marketplace generates card images from it. Ours: a
  panel screenshot at the repository root. Retake it when the panel changes.
- Manifest fields the listing reads: `schemaVersion`, `id`, `name`, `version` (max 64 chars), `author`
  (free text, max 120 chars; ours is `Entangled-Forge`), `description`, `kinds`, `entryPoints`. Ours has all of them. The listing card shows `name`, which is
  `OmasteelRGB` to match the repository and the issue title; the bar widget's own display name stays
  "Keyboard lighting" because it appears in the shell's widget picker.

**Submission**

Category is one of Appearance, Desktop, Developer Tools, Hardware, Kids, Productivity, System, Widgets,
Other. Tags are one to three of: ai, bar, education, games, hyprland, kids, launcher, media,
power-management, quickshell, security, system, vpn, workspaces. For us: `Hardware` with `bar, quickshell`.

Either the issue form <https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=submit-plugin.yml>
or the CLI. The ready-to-paste body is `docs/marketplace-submission.md`; it keeps the six required headings
in order and reads:

(see the file; the maintainer notes there are the paragraph that will be scanned for `sudo`/`pkexec` mentions,
so they state the negation explicitly)

```bash
gh issue create --repo omacom/omarchy-plugin-marketplace --title "[Plugin]: OmasteelRGB" --body-file docs/marketplace-submission.md
```

Submit from a commit that is already pushed and that you will not move until the bot has validated it.

**What happens next**

- A bot validates the exact commit at the branch head and runs the Automated Security Baseline, a static
  scan. It does not execute the code. It labels the issue `validated` or `needs-fixes`.
- Any non-negated mention of `sudo` or `pkexec` in the repo is the `privilege` capability, which adds
  `security-review-required`. Ours will trigger it: the README and `Model.js` print the udev install
  commands with sudo. That is allowed; a maintainer reads it and accepts the capability explicitly. Wording
  such as "No sudo or pkexec is required at runtime" is recognised as a negation and helps.
- A maintainer applies `approved-and-verified`, which publishes the listing bound to that exact commit.
  The listing then shows "Snapshot verified".
- If `main` moves after the validated commit and before approval, the bot asks for a fresh validation.
  Do not push to `main` while a submission is open, or resubmit the new SHA.
- **Updates are not automatic.** New commits on `main` reach installed users through `omarchy plugin
  update`, but the marketplace keeps showing the old snapshot as "Update unverified" until you open a
  Plugin verification issue (<https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=verify-plugin.yml>,
  "Verify and publish a newer upstream commit") with the plugin id, the repository URL and the full 40-char
  SHA. Do this once per release, not per commit.

**Existing listings in the same space** (checked 2026-09-21)

- *Keyboard RGB* by bruno-g-soares (`io.github.bruno-g-soares.omarchy-keyboard-rgb`, listed 2026-08-27):
  the same SteelSeries KLC controller, verified on a GS66 12U with USB id `1038:113a`, and it refuses any
  other id. One solid colour for the whole board, software brightness, on/off, saved profiles, startup
  restore and theme sync via hooks. It vendors msi-perkeyrgb. It does not do groups or per-key colours.
  That is the gap OmasteelRGB fills, and the README should say so in one line.
- *Apex Keyboard* (`sonic.apex`) for the external SteelSeries Apex 7, through OpenRGB.
- Several theme-sync plugins built on OpenRGB (omargb, omaglow, omarchy-theme-rgb, omarchy-openrgb). None
  can drive the KLC, because OpenRGB has no controller for `1038:1122`/`113a`.

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

Run on 2026-09-22 against `main`.

| Check | How | Result |
|---|---|---|
| Unit tests | `python3 -m pytest -q` | 126 passed |
| Manifest and layout | `git archive HEAD` into an empty folder, `omarchy plugin validate` on it | valid |
| Real install path | removed the rsync dev copy, `omarchy plugin add <url> --enable --yes` | cloned, validated, enabled in the right section |
| Update path | `omarchy plugin update steelseries.keyboard --yes`, several times with real changes | fast-forwarded and validated each time |
| Shell loads it | `omarchy-shell steelseries.keyboard status` after each update | device accessible, snapshot present, model detected from DMI |
| Bridge runs from the install | `pgrep -af plugins/steelseries.keyboard/bridge` | one bridge per bar instance |
| Hardware writes | off, restore, preset apply, group and key edits through the panel and IPC | all reports accepted by the controller |
| Model selection | detection on the GS75, override to GS66 and back over IPC, picker in the panel | as designed, no QML errors |
| Marketplace repository rules | root manifest, README with install and removal, LICENSE, dependencies named, `preview.png`, unique id | all present |
| Docs match behaviour | README, CHANGELOG, this guide, the submission body in `docs/marketplace-submission.md` | rewritten for 0.1.0 |

Things the checks do **not** cover, and that the announcement should say plainly:

- Three keymaps ship (GE63 family, GS65, GS66) covering eleven MSI model tokens, chosen from the DMI
  product name with a panel override. Only the GS75 Stealth 8SF has been lit by this plugin; the rest are
  upstream tables. An unknown model gets the family table and a visible warning.
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
7. If the plugin is listed on the marketplace, open a Plugin verification issue for the new commit SHA so
   the listing stops showing "Update unverified" (see *Listing on the marketplace*).

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
