// Pure helpers for the keyboard lighting panel. No QML, no I/O.

var PALETTE = [
  { name: "Blue-violet", hex: "#4a5cff" },
  { name: "Red", hex: "#ff2a2a" },
  { name: "White", hex: "#ffffff" },
  { name: "Green", hex: "#2aff5a" },
  { name: "Cyan", hex: "#2ad8ff" },
  { name: "Magenta", hex: "#ff2ad8" },
  { name: "Amber", hex: "#ffb02a" },
  { name: "Off", hex: "#000000" }
]

var GROUP_LABELS = {
  enter_esc: "Esc + Enter",
  wasd: "WASD",
  arrows: "Arrows",
  nav: "Nav",
  numpad_ops: "Numpad ops",
  modifiers: "Modifiers",
  fn: "Fn",
  numpad: "Numpad",
  f_row: "F row",
  num_row: "Number row",
  characters: "Letters"
}

function urlToPath(url) {
  var s = String(url || "")
  if (s.indexOf("file://") === 0) s = s.substring(7)
  try { s = decodeURIComponent(s) } catch (e) {}
  return s.replace(/\/+$/, "")
}

// "#4a5cff", "4a5cff" and Qt's "#ff4a5cff" all become "#4a5cff"; anything else "".
function normalizeHex(value) {
  var s = String(value || "").trim().toLowerCase()
  if (s.charAt(0) === "#") s = s.substring(1)
  if (s.length === 8) s = s.substring(2)
  if (!/^[0-9a-f]{6}$/.test(s)) return ""
  return "#" + s
}

function textOn(hex) {
  var h = normalizeHex(hex)
  if (!h) return "#ffffff"
  var r = parseInt(h.substring(1, 3), 16)
  var g = parseInt(h.substring(3, 5), 16)
  var b = parseInt(h.substring(5, 7), 16)
  var luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
  return luma > 140 ? "#000000" : "#ffffff"
}

function palette(accentHex) {
  var list = PALETTE.slice()
  var accent = normalizeHex(accentHex)
  if (accent) list.unshift({ name: "Theme accent", hex: accent })
  return list
}

function groupLabel(name) {
  var key = String(name || "")
  if (GROUP_LABELS[key]) return GROUP_LABELS[key]
  return key.replace(/_/g, " ").replace(/^\w/, function(c) { return c.toUpperCase() })
}

function deviceLabel(device) {
  if (!device) return "No SteelSeries keyboard"
  var name = String(device.name || "SteelSeries keyboard")
  return name.replace(/^SteelSeries SteelSeries\b/, "SteelSeries")
}

function clamp(value, lo, hi) {
  var n = Number(value)
  if (!isFinite(n)) return lo
  return Math.max(lo, Math.min(hi, n))
}

function accessCommands(pluginDir) {
  var rule = String(pluginDir || ".") + "/udev/70-steelseries-klc.rules"
  return "sudo install -m644 -o root -g root '" + rule + "' /etc/udev/rules.d/ && " +
    "sudo rm -f /etc/udev/rules.d/99-msi-rgb.rules && " +
    "sudo udevadm control --reload && " +
    "sudo udevadm trigger --subsystem-match=hidraw --action=add"
}
