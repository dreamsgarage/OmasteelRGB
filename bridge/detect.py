"""Read-only device discovery.

Enumerates SteelSeries HID devices through sysfs. Nothing here opens a device
or writes a byte - enabling the plugin must not disturb the profile the
keyboard is already replaying from onboard memory.

Devices are matched by vendor:product and interface, never by node index: a
machine can easily have /dev/hidraw2 belong to the touchpad.
"""

import glob
import os
import re

VENDOR_STEELSERIES = 0x1038

KLC_PRODUCT_IDS = {0x1122: "KLC", 0x113A: "KLC"}

# Apex family, per OpenRGB's SteelSeriesDevices.h. We do not drive these
# natively; they are reported so the panel can offer the OpenRGB backend.
APEX_PRODUCT_IDS = {
    0x161A: "Apex 3", 0x1622: "Apex 3 TKL", 0x161C: "Apex 5",
    0x1612: "Apex 7", 0x1618: "Apex 7 TKL", 0x1634: "Apex 9 TKL",
    0x1620: "Apex 9 Mini", 0x1610: "Apex Pro", 0x1614: "Apex Pro TKL",
    0x1628: "Apex Pro TKL 2023", 0x1630: "Apex Pro TKL 2023 WL",
    0x1632: "Apex Pro TKL 2023 WL", 0x1642: "Apex Pro TKL Gen3",
    0x1644: "Apex Pro TKL Gen3 WL", 0x1646: "Apex Pro TKL Gen3 WL",
    0x1640: "Apex Pro 3", 0x0616: "Apex M750", 0x1202: "Apex",
    0x1206: "Apex 350",
}


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _uevent(path):
    out = {}
    for line in _read(path).splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            out[key] = value
    return out


def _hidraw_nodes():
    """Every hidraw node with its parsed vendor/product and driver."""
    found = []
    for sysfs in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        name = os.path.basename(sysfs)
        info = _uevent(os.path.join(sysfs, "device", "uevent"))
        hid_id = info.get("HID_ID", "")
        parts = hid_id.split(":")
        if len(parts) != 3:
            continue
        try:
            vendor = int(parts[1], 16)
            product = int(parts[2], 16)
        except ValueError:
            continue
        found.append({
            "node": "/dev/" + name,
            "sysfs": sysfs,
            "vendor_id": vendor,
            "product_id": product,
            "hid_name": info.get("HID_NAME", ""),
            "driver": info.get("DRIVER", ""),
        })
    return found


def _accessible(node):
    return os.access(node, os.R_OK | os.W_OK)


def scan():
    """Group SteelSeries hidraw nodes into devices. Read-only."""
    devices = {}
    for entry in _hidraw_nodes():
        if entry["vendor_id"] != VENDOR_STEELSERIES:
            continue
        product = entry["product_id"]

        if product in KLC_PRODUCT_IDS:
            kind, backend, model = "klc", "klc_hid", KLC_PRODUCT_IDS[product]
        elif product in APEX_PRODUCT_IDS:
            kind, backend, model = "apex", "openrgb", APEX_PRODUCT_IDS[product]
        else:
            kind, backend, model = "unknown", None, None

        device = devices.setdefault(product, {
            "id": "%04x:%04x" % (entry["vendor_id"], product),
            "vendor_id": entry["vendor_id"],
            "product_id": product,
            "name": entry["hid_name"] or "SteelSeries device",
            "model": model,
            "kind": kind,
            "backend": backend,
            "driver": entry["driver"],
            "nodes": [],
            "lights_known": False,
        })
        device["nodes"].append({"path": entry["node"], "accessible": _accessible(entry["node"])})

    out = []
    for device in devices.values():
        device["nodes"].sort(key=lambda n: n["path"])
        device["accessible"] = any(n["accessible"] for n in device["nodes"])
        device["interfaces"] = len(device["nodes"])
        if device["kind"] == "klc" and not device["accessible"]:
            device["status"] = "needs-access"
            device["hint"] = (
                "Install udev/70-steelseries-klc.rules, then "
                "udevadm control --reload && udevadm trigger --subsystem-match=hidraw --action=add"
            )
        elif device["kind"] == "apex":
            device["status"] = "needs-openrgb"
            device["hint"] = "Apex lighting goes through OpenRGB. Install openrgb to control this device."
        elif device["kind"] == "unknown":
            device["status"] = "unsupported"
            device["hint"] = "Unrecognised SteelSeries product id. A keymap contribution may be needed."
        else:
            device["status"] = "ready"
        out.append(device)

    out.sort(key=lambda d: (d["kind"] != "klc", d["product_id"]))
    return out


# -- machine identity ----------------------------------------------------------
#
# The KLC product id is shared across MSI designs, so the keyboard alone does
# not say which key layout it has. DMI does: product_name reads like
# "GS75 Stealth 8SF" or "Raider GE78HX 13VI". The family token (two letters,
# two digits) is what msi-perkeyrgb keymaps are keyed by.

DMI_DIR = "/sys/class/dmi/id"
MODEL_TOKEN_RE = re.compile(r"\b([A-Z]{2}\d{2})[A-Z]{0,2}\b")


def model_token(product_name):
    """'GS75 Stealth 8SF' -> 'GS75', 'Raider GE78HX 13VI' -> 'GE78', else None."""
    match = MODEL_TOKEN_RE.search(str(product_name or "").upper())
    return match.group(1) if match else None


def machine(dmi_dir=None):
    """Vendor, product, board and the model token, read-only from sysfs."""
    directory = dmi_dir or DMI_DIR
    vendor = _read(os.path.join(directory, "sys_vendor")).strip()
    product = _read(os.path.join(directory, "product_name")).strip()
    return {
        "vendor": vendor,
        "product": product,
        "board": _read(os.path.join(directory, "board_name")).strip(),
        "family": _read(os.path.join(directory, "product_family")).strip(),
        "msi": "micro-star" in vendor.lower() or vendor.strip().upper() == "MSI",
        "model": model_token(product),
    }
