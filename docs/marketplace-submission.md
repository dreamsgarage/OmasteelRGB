### Repository URL
https://github.com/dreamsgarage/OmasteelRGB
### Category
Hardware
### Tags
bar, quickshell
### Suggest a missing tag
keyboard
### Maintainer notes
Per-key steady RGB for the internal MSI SteelSeries KLC keyboard controller (USB 1038:1122 and 1038:113a), tested on a GS75 Stealth 8SF; keymaps for the GE63 family, GS65 and GS66, chosen from the DMI product name with a panel override. Python 3 plus the Arch python-hidapi package; nothing is downloaded at install or runtime. No sudo or pkexec is required at runtime. The one privileged step is installing the bundled udev rule (uaccess, MODE 0660), which the panel prints and the user runs by hand. Only the steady-colour (0x0e) and commit (0x09) packets validated on hardware are sent; hardware-effect packets are not implemented. The first write replaces the profile the controller replays from onboard memory, which Linux cannot read back; the panel says so and asks once before that write.
### Submission checklist
- [x] The repository is public and contains installation and removal instructions.
- [x] I have documented the plugin license and any external dependencies.
- [x] I confirm that I own or have permission to submit this plugin and its preview assets.
- [x] The plugin does not overwrite user configuration without explicit consent.
- [x] I understand that approval is for listing and is not a security review.
