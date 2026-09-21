import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

// Owns the Python bridge. QML never touches HID: every read and write goes
// through one long-lived process speaking JSON lines, and state is re-read
// after each write so the panel shows what the bridge stored, not what the
// UI hoped.
Item {
  id: root

  readonly property string pluginDir: Model.urlToPath(Qt.resolvedUrl("."))
  readonly property string bridgePath: pluginDir + "/bridge/steelseries_bridge.py"
  readonly property bool bridgeRunning: bridge.running

  property var devices: []
  property var device: null
  readonly property bool hasDevice: device !== null
  readonly property bool accessible: !!device && device.accessible === true
  readonly property bool needsAccess: !!device && device.status === "needs-access"
  readonly property string deviceName: Model.deviceLabel(device)

  property bool hasSnapshot: false
  property var profile: null
  property string snapshotMessage: ""
  readonly property string baseColor: profile && profile.base ? String(profile.base) : ""
  readonly property int brightness: profile && isFinite(Number(profile.brightness)) ? Number(profile.brightness) : 100
  // The controller cannot be read back. The board boots lit, and only an
  // `off` this plugin sent turns this false.
  property bool lightsOn: true

  property var groups: ({})
  property var groupNames: []
  property var keyNames: []
  property var presets: []

  property bool busy: false
  property string lastError: ""
  property string actionStatus: ""

  property var _pending: ({})
  property var _queue: []
  property int _serial: 0
  property bool _ready: false
  property string _stderr: ""

  function send(request, callback) {
    _serial += 1
    request.id = _serial
    _pending[_serial] = callback || null
    busy = true
    var line = JSON.stringify(request) + "\n"
    if (bridge.running && _ready) bridge.write(line)
    else {
      _queue.push(line)
      if (!bridge.running) {
        _stderr = ""
        bridge.running = true
      }
    }
  }

  function _flush() {
    var lines = _queue
    _queue = []
    for (var i = 0; i < lines.length; i++) bridge.write(lines[i])
  }

  function _pendingCount() {
    var n = 0
    for (var id in _pending) n += 1
    return n
  }

  function _fail(message) {
    var waiting = _pending
    _pending = ({})
    _queue = []
    busy = false
    lastError = message
    for (var id in waiting) if (waiting[id]) waiting[id]({ ok: false, error: message })
  }

  function handleLine(line) {
    var text = String(line || "").trim()
    if (text === "") return
    var response
    try { response = JSON.parse(text) } catch (e) {
      lastError = "bridge sent something that is not JSON"
      return
    }
    if (response.event === "ready") {
      _ready = true
      _flush()
      return
    }
    var callback = response.id !== undefined ? _pending[response.id] : null
    if (response.id !== undefined) delete _pending[response.id]
    busy = _pendingCount() > 0
    if (response.ok) lastError = ""
    else {
      lastError = String(response.error || "bridge error")
      if (response.needsAccess) refresh()
    }
    if (callback) callback(response)
  }

  function applyState(r) {
    devices = r.devices || []
    var klc = null
    for (var i = 0; i < devices.length; i++) {
      if (devices[i] && devices[i].kind === "klc") { klc = devices[i]; break }
    }
    device = klc
    hasSnapshot = r.hasSnapshot === true
    profile = r.profile || null
    snapshotMessage = r.message ? String(r.message) : ""
  }

  function refresh() {
    send({ cmd: "state" }, function(r) { if (r.ok) root.applyState(r) })
  }

  function loadKeymap() {
    send({ cmd: "keymap" }, function(r) {
      if (!r.ok) return
      root.groups = r.groups || {}
      root.groupNames = Object.keys(r.groups || {})
      root.keyNames = r.keys || []
    })
  }

  function loadPresets() {
    send({ cmd: "presets" }, function(r) { if (r.ok) root.presets = r.presets || [] })
  }

  function flash(text) {
    actionStatus = text
    statusTimer.restart()
  }

  function _write(request, onOk) {
    send(request, function(r) {
      if (!r.ok) return
      if (onOk) onOk(r)
      root.refresh()
    })
  }

  function apply(profile) {
    _write({ cmd: "apply", profile: profile }, function(r) {
      root.lightsOn = true
      root.flash("Applied " + r.keys + " keys")
    })
  }

  function setBase(color) {
    _write({ cmd: "set_base", color: color }, function() {
      root.lightsOn = true
      root.flash("Board set to " + color)
    })
  }

  function setGroup(group, color) {
    _write({ cmd: "set_group", group: group, color: color }, function() {
      root.lightsOn = true
      root.flash(Model.groupLabel(group) + " set to " + color)
    })
  }

  function setKey(key, color) {
    _write({ cmd: "set_key", key: key, color: color }, function() {
      root.lightsOn = true
      root.flash(key + " set to " + color)
    })
  }

  function setBrightness(value) {
    var pct = Math.round(Model.clamp(value, 0, 100))
    _write({ cmd: "brightness", value: pct }, function() {
      root.lightsOn = true
      root.flash("Brightness " + pct + "%")
    })
  }

  function off() {
    _write({ cmd: "off" }, function() {
      root.lightsOn = false
      root.flash("Lights off")
    })
  }

  function restore() {
    _write({ cmd: "restore" }, function() {
      root.lightsOn = true
      root.flash("Restored the plugin profile")
    })
  }

  function loadPreset(id) {
    for (var i = 0; i < presets.length; i++) {
      if (presets[i].id === id) {
        apply(presets[i].profile)
        return true
      }
    }
    return false
  }

  Timer {
    id: statusTimer
    interval: 2600
    repeat: false
    onTriggered: root.actionStatus = ""
  }

  Process {
    id: bridge
    command: ["python3", root.bridgePath, "--ready"]
    running: false
    stdinEnabled: true
    stdout: SplitParser { onRead: function(data) { root.handleLine(data) } }
    stderr: SplitParser { onRead: function(data) { root._stderr = String(data) } }
    onExited: function(exitCode, exitStatus) {
      root._ready = false
      root._fail(root._stderr !== "" ? root._stderr : ("bridge exited with status " + exitCode))
    }
  }

  Component.onCompleted: {
    refresh()
    loadKeymap()
    loadPresets()
  }
}
