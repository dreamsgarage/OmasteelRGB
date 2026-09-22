import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "steelseries.keyboard"
  ipcTarget: "steelseries.keyboard"
  manageIpc: false

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  readonly property bool ready: keyboard.hasDevice && keyboard.accessible
  readonly property bool canEdit: ready && !keyboard.busy
  readonly property string startingName: keyboard.startingFrom ? String(keyboard.startingFrom.name) : ""
  readonly property var keySuggestions: Model.keySuggestions(keyField.text, keyboard.keyNames, keyboard.aliasNames, 12)
  readonly property string accentHex: Model.normalizeHex(String(Color.accent))
  readonly property var swatches: Model.palette(accentHex)
  readonly property string accessCommands: Model.accessCommands(keyboard.pluginDir)

  // PanelHero upper-cases and elides its meta line; keep these short.
  readonly property string statusLine: !keyboard.hasDevice ? "No keyboard found"
    : keyboard.needsAccess ? "Needs device access"
    : !keyboard.hasSnapshot ? "Onboard profile, untouched"
    : keyboard.lightsOn ? "Plugin profile · " + keyboard.baseColor
    : "Lights off"

  readonly property color barIconColor: ready && keyboard.lightsOn && keyboard.baseColor !== ""
    ? keyboard.baseColor
    : (ready ? barForeground : Qt.darker(barForeground, 1.55))

  // "board", a group name, or "key" (with keyField naming the key).
  property string target: "board"
  property bool confirmPending: false
  property var pendingWrite: null
  // True while the pending first write is a partial edit (group or key)
  // that the bridge seeds from the default preset.
  property bool pendingIsPartial: false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onOpenedChanged: if (opened) {
    confirmPending = false
    pendingWrite = null
    keyboard.refresh()
    if (panelFlick) panelFlick.contentY = 0
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  Service { id: keyboard }

  // The first write destroys the profile the controller replays from Windows,
  // and nothing on Linux can read it back. Ask once, inline, before that write.
  function requestWrite(fn, partial) {
    if (!ready) return
    if (!keyboard.hasSnapshot) {
      pendingWrite = fn
      pendingIsPartial = partial === true
      confirmPending = true
      return
    }
    fn()
  }

  function confirmWrite() {
    var fn = pendingWrite
    pendingWrite = null
    confirmPending = false
    if (fn) fn()
  }

  function cancelWrite() {
    pendingWrite = null
    confirmPending = false
  }

  function selectKey(name) {
    target = "key"
    keyField.text = name
    Qt.callLater(function() { hexField.forceActiveFocus(); hexField.selectAll() })
  }

  function applyColor() {
    var hex = Model.normalizeHex(hexField.text)
    if (!hex) {
      keyboard.lastError = "Enter a 6-digit hex colour, like #4a5cff"
      return
    }
    hexField.text = hex
    if (target === "board") {
      requestWrite(function() { keyboard.setBase(hex) })
    } else if (target === "key") {
      var key = keyField.text.trim()
      if (!key) {
        keyboard.lastError = "Name a key first, like Esc or KP_Delete"
        return
      }
      requestWrite(function() { keyboard.setKey(key, hex) }, true)
    } else {
      var group = target
      requestWrite(function() { keyboard.setGroup(group, hex) }, true)
    }
  }

  // `off` commits a blackout to onboard memory, so it is a first write like
  // any other and goes through the same confirmation.
  function togglePower() {
    if (!ready || keyboard.busy) return
    if (keyboard.lightsOn) requestWrite(function() { keyboard.off() })
    else if (keyboard.hasSnapshot) keyboard.restore()
  }

  function loadPreset(id) {
    requestWrite(function() { keyboard.loadPreset(id) })
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function off(): string { keyboard.off(); return "ok" }
    function restore(): string { keyboard.restore(); return "ok" }
    // IPC callers are explicit, like `off` and `preset` above: no panel
    // confirmation, the bridge seeds a first partial edit from the default preset.
    function setBase(color: string): string {
      var hex = Model.normalizeHex(color)
      if (!hex) return "bad colour, want #rrggbb"
      keyboard.setBase(hex); return "ok"
    }
    function setGroup(group: string, color: string): string {
      var hex = Model.normalizeHex(color)
      if (!hex) return "bad colour, want #rrggbb"
      keyboard.setGroup(group, hex); return "ok"
    }
    function setKey(key: string, color: string): string {
      var hex = Model.normalizeHex(color)
      if (!hex) return "bad colour, want #rrggbb"
      keyboard.setKey(key, hex); return "ok"
    }
    function preset(id: string): string { return keyboard.loadPreset(id) ? "ok" : "unknown preset" }
    function status(): string {
      return JSON.stringify({
        device: keyboard.deviceName,
        accessible: keyboard.accessible,
        hasSnapshot: keyboard.hasSnapshot,
        lightsOn: keyboard.lightsOn,
        base: keyboard.baseColor
      })
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component {
      Item {
        Text {
          anchors.centerIn: parent
          textFormat: Text.PlainText
          text: "󰌌"
          color: root.barIconColor
          font.family: root.fontFamily
          font.pixelSize: Style.font.icon
        }
      }
    }
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.RightButton) {
        if (!root.ready) return
        if (keyboard.hasSnapshot) keyboard.off()
        else {
          // The confirmation lives in the panel; a silent blackout from the
          // bar would be the destructive first write with no warning shown.
          root.requestWrite(function() { keyboard.off() })
          root.open()
        }
      }
      else if (buttonCode === Qt.MiddleButton) { if (root.ready && keyboard.hasSnapshot) keyboard.restore() }
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(400))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(620))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: hexField.activeFocus || keyField.activeFocus
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      // h/j/k/l and the arrows never reach textKey: the catcher turns them
      // into moves, which this panel does not use.
      onTextKey: function(t) {
        if (t === "o" || t === "O") root.togglePower()
        else if (t === "r" || t === "R") { if (root.ready && keyboard.hasSnapshot) keyboard.restore() }
        else if (t === "p" || t === "P") root.loadPreset("gs75-photo")
        else if (t === "b" || t === "B") root.target = "board"
        else if (t === "e" || t === "E") {
          // Edit one key: jump to the key target and start typing its name.
          root.target = "key"
          Qt.callLater(function() { keyField.forceActiveFocus(); keyField.selectAll() })
        }
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: column
          width: panelFlick.width
          spacing: Style.space(12)

          PanelHero {
            id: hero
            width: parent.width
            title: keyboard.deviceName
            meta: root.statusLine
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconOpacity: root.ready && keyboard.lightsOn ? 1.0 : 0.5
            iconComponent: Component {
              Text {
                textFormat: Text.PlainText
                text: "󰌌"
                color: root.ready && keyboard.lightsOn && keyboard.baseColor !== "" ? keyboard.baseColor : root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
              }
            }
            trailingControl: Component {
              ToggleSwitch {
                id: powerSwitch
                visible: root.ready
                checked: keyboard.lightsOn
                busy: keyboard.busy
                // Without a snapshot there is nothing to switch back on.
                interactive: keyboard.lightsOn || keyboard.hasSnapshot
                foreground: hero.foreground
                onToggled: root.togglePower()

                PanelToolTip {
                  visible: powerSwitch.containsMouse
                  text: keyboard.lightsOn ? "Lights off" : (keyboard.hasSnapshot ? "Restore the plugin profile" : "Nothing to restore yet")
                  fontFamily: hero.fontFamily
                }
              }
            }
          }

          Text {
            textFormat: Text.PlainText
            visible: keyboard.actionStatus !== "" || keyboard.lastError !== ""
            width: parent.width
            text: keyboard.actionStatus !== "" ? keyboard.actionStatus : keyboard.lastError
            color: keyboard.lastError !== "" && keyboard.actionStatus === "" ? root.urgent : root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          // ---------- needs access ----------
          Column {
            visible: keyboard.needsAccess
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              text: "DEVICE ACCESS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: "The keyboard's HID node is root-only. Install the plugin's udev rule once; it grants the active session user access with an ACL, no sudo at runtime and no world-readable keystrokes."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: root.accessCommands
              color: root.foreground
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WrapAnywhere
            }

            Row {
              spacing: Style.space(8)

              Button {
                text: "Copy commands"
                iconText: "󰆏"
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: if (root.bar) root.bar.run("wl-copy " + root.bar.shellQuote(root.accessCommands))
              }

              Button {
                text: "Check again"
                iconText: "󰑐"
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: keyboard.refresh()
              }
            }
          }

          // ---------- first-write confirmation ----------
          Column {
            visible: root.confirmPending
            width: parent.width
            spacing: Style.space(8)

            Text {
              textFormat: Text.PlainText
              width: parent.width
              text: "This replaces the profile saved from Windows. Linux cannot read it back, so the only way to get that look again is SteelSeries Engine on Windows or rebuilding it here."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Text {
              visible: root.pendingIsPartial
              textFormat: Text.PlainText
              width: parent.width
              text: root.startingName !== ""
                ? "Everything you have not set starts from the \"" + root.startingName + "\" preset. Change the rest afterwards, key by key or with Board."
                : "Everything you have not set starts as the plugin's default blue-violet fill."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              wrapMode: Text.WordWrap
            }

            Row {
              spacing: Style.space(8)

              Button {
                text: "Replace it"
                foreground: root.urgent
                fontFamily: root.fontFamily
                onClicked: root.confirmWrite()
              }

              Button {
                text: "Cancel"
                foreground: root.foreground
                fontFamily: root.fontFamily
                onClicked: root.cancelWrite()
              }
            }
          }

          PanelSeparator {
            visible: root.ready
            foreground: root.foreground
          }

          // ---------- target ----------
          Column {
            visible: root.ready
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              text: "TARGET"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Flow {
              width: parent.width
              spacing: Style.space(6)

              Button {
                text: "Board"
                selected: root.target === "board"
                foreground: root.foreground
                fontFamily: root.fontFamily
                fontSize: Style.font.bodySmall
                onClicked: root.target = "board"
              }

              Repeater {
                model: keyboard.groupNames
                Button {
                  required property var modelData
                  text: Model.groupLabel(modelData)
                  selected: root.target === modelData
                  enabled: root.ready
                  opacity: enabled ? 1.0 : 0.45
                  tooltipText: (keyboard.groups[modelData] || []).join(", ")
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: Style.font.bodySmall
                  onClicked: root.target = modelData
                }
              }

              Button {
                text: "Key…"
                selected: root.target === "key"
                enabled: root.ready
                opacity: enabled ? 1.0 : 0.45
                foreground: root.foreground
                fontFamily: root.fontFamily
                fontSize: Style.font.bodySmall
                onClicked: {
                  root.target = "key"
                  Qt.callLater(function() { keyField.forceActiveFocus() })
                }
              }
            }

            TextField {
              id: keyField
              visible: root.target === "key"
              width: parent.width
              placeholderText: "Key name — esc, tab, f5, kp_delete, super…"
              foreground: root.foreground
              onAccepted: {
                // Enter on a partial name picks the first suggestion, so
                // "es" + Enter targets Esc instead of failing as unknown.
                if (root.keySuggestions.length > 0 && !Model.knownKey(text, keyboard.keyNames, keyboard.aliasNames))
                  text = root.keySuggestions[0]
                root.applyColor()
              }
            }

            Flow {
              visible: root.target === "key" && root.keySuggestions.length > 0
              width: parent.width
              spacing: Style.space(4)

              Repeater {
                model: root.keySuggestions
                Button {
                  required property var modelData
                  text: modelData
                  selected: keyField.text === modelData
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: Style.font.caption
                  onClicked: root.selectKey(modelData)
                }
              }
            }

            Text {
              visible: root.target === "key" && keyField.text.trim() !== "" && root.keySuggestions.length === 0
              textFormat: Text.PlainText
              width: parent.width
              text: "No key called \"" + keyField.text.trim() + "\". Letters are A-Z, digits 0-9; others like Esc, Return, Space, KP_Enter, Prior (PgUp), Next (PgDn)."
              color: root.urgent
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }
          }

          // ---------- colour ----------
          Column {
            visible: root.ready
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              text: "COLOUR"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Flow {
              width: parent.width
              spacing: Style.space(6)

              Repeater {
                model: root.swatches
                Rectangle {
                  id: swatch
                  required property var modelData
                  readonly property bool current: Model.normalizeHex(hexField.text) === modelData.hex
                  width: Style.space(26)
                  height: Style.space(26)
                  radius: Style.cornerRadius > 0 ? Style.space(6) : 0
                  color: modelData.hex
                  border.width: current ? 2 : 1
                  border.color: current ? root.foreground : root.dim

                  MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: hexField.text = swatch.modelData.hex
                    onEntered: if (root.bar) root.bar.showTooltip(swatch, swatch.modelData.name)
                    onExited: if (root.bar) root.bar.hideTooltip(swatch)
                  }
                }
              }
            }

            Row {
              width: parent.width
              spacing: Style.space(8)

              TextField {
                id: hexField
                width: parent.width - applyButton.width - parent.spacing
                text: "#4a5cff"
                placeholderText: "#rrggbb"
                foreground: root.foreground
                onAccepted: root.applyColor()
              }

              Button {
                id: applyButton
                text: root.target === "board" ? "Apply to board"
                  : root.target === "key" ? "Apply to key"
                  : "Apply to " + Model.groupLabel(root.target)
                iconText: "󰸞"
                foreground: root.foreground
                fontFamily: root.fontFamily
                enabled: root.ready && !keyboard.busy && !root.confirmPending
                opacity: enabled ? 1.0 : 0.45
                onClicked: root.applyColor()
              }
            }
          }

          PanelSeparator {
            visible: root.ready && keyboard.presets.length > 0
            foreground: root.foreground
          }

          // ---------- presets ----------
          Column {
            visible: root.ready && keyboard.presets.length > 0
            width: parent.width
            spacing: Style.space(8)

            PanelSectionHeader {
              text: "PRESETS"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Flow {
              width: parent.width
              spacing: Style.space(6)

              Repeater {
                model: keyboard.presets
                Button {
                  required property var modelData
                  text: modelData.name
                  iconText: "󰏫"
                  tooltipText: modelData.description || ""
                  foreground: root.foreground
                  fontFamily: root.fontFamily
                  fontSize: Style.font.bodySmall
                  enabled: root.ready && !keyboard.busy && !root.confirmPending
                  opacity: enabled ? 1.0 : 0.45
                  onClicked: root.loadPreset(modelData.id)
                }
              }
            }
          }

          Text {
            visible: root.ready && !keyboard.hasSnapshot && !root.confirmPending
            textFormat: Text.PlainText
            width: parent.width
            text: keyboard.snapshotMessage + " Pick a target and a colour, or load a preset, to start the plugin's own map."
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }
        }
      }
    }
  }
}
