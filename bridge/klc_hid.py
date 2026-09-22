"""SteelSeries KLC per-key RGB over HID.

Packet layout ported from msi-perkeyrgb (MIT, Askannz) -
https://github.com/Askannz/msi-perkeyrgb - and validated on an MSI GS75
Stealth 8SF (USB 1038:1122) on 2026-09-12.

A full profile is four feature reports of 524 bytes, one per keyboard region,
followed by a 64-byte commit:

    [0x0e, 0x00, <region id>, 0x00]     4-byte header
    <42 key fragments x 12 bytes>       504 bytes
    [0x00 x14, 0x08, 0x39]              16-byte trailer

Each fragment is [R, G, B, 0,0,0,0,0,0, 0x01, 0x00, <hid keycode>]; unused
slots are twelve zero bytes.

Effect packets (opcode 0x0b) are deliberately NOT implemented. Upstream
reverted them after a malformed packet bricked a backlight
(Askannz/msi-perkeyrgb#24). This driver writes steady colours only.

Pacing matters as much as the bytes. The controller ACKs every report at USB
level and then parses it at its own speed; a report that lands while it is
still chewing the previous one is dropped without any error reaching the host.
Upstream sleeps after every send ("The RGB controller derps if commands are
sent too fast"). Without that pause a four-region write can lose a region, and
the board comes back with, say, the letters dark and the modifiers lit. The
commit is worse: it stores the map to onboard memory, so the next write has to
wait for that to finish.
"""

import os
import time

VENDOR_ID = 0x1038
KLC_PRODUCT_IDS = (0x1122, 0x113A)

SLOTS_PER_REGION = 42
FRAGMENT_SIZE = 12
PACKET_SIZE = 524
COMMIT_SIZE = 64

OPCODE_COLORS = 0x0E
OPCODE_COMMIT = 0x09

# Pause after every report, as upstream does. 10 ms is the value msi-perkeyrgb
# has shipped for years; four regions plus the commit cost 50 ms per write.
REPORT_DELAY = 0.01
# How long the controller gets to store a committed map before the next write
# may start. Enforced lazily, so an isolated write pays nothing and only a
# rapid off -> restore (or slider drag) waits.
COMMIT_SETTLE = 0.25
# A refused report is retried this many times after RETRY_DELAY.
RETRIES = 2
RETRY_DELAY = 0.05
TRAILER = bytes([0x00] * 14 + [0x08, 0x39])

REGION_IDS = {"alphanum": 0x2A, "enter": 0x0B, "modifiers": 0x18, "numpad": 0x24}

# Which HID keycodes live in which region. Fixed by the controller, not the model.
REGION_KEYCODES = {
    "alphanum": [
        4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24,
        25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 58, 59, 60, 61, 62,
        63
    ],
    "enter": [
        40, 49, 50, 100, 135, 136, 137, 138, 139, 144, 145, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    ],
    "modifiers": [
        41, 42, 43, 44, 45, 46, 47, 48, 51, 52, 53, 54, 55, 56, 57, 101, 224, 225, 226,
        227, 228, 229, 230, 240, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
    ],
    # 102 is the power key's RGB element on the GS66 (Bergmann89's msi-perkeyrgb
    # fork adds it to this region). Other models have no LED there; a keymap
    # that does not name it never sends it.
    "numpad": [
        64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83,
        84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 102, 0, 0, 0, 0, 0
    ],
}


class KLCError(Exception):
    pass


# Each region list is padded to 42 slots with 0, so 0 appears in three of them.
# It is an empty slot, never a key - excluding it keeps the lookup unambiguous.
EMPTY_SLOT = 0
_REGION_OF = {
    code: region
    for region, codes in REGION_KEYCODES.items()
    for code in codes
    if code != EMPTY_SLOT
}


def region_for(hid_keycode):
    """Which region packet a HID keycode belongs in, or None if it is not addressable."""
    return _REGION_OF.get(hid_keycode)


def build_region_packet(region, hid_colors):
    """One 524-byte feature report. hid_colors is {hid_keycode: (r, g, b)}."""
    if region not in REGION_IDS:
        raise KLCError("unknown region %r" % (region,))
    if len(hid_colors) > SLOTS_PER_REGION:
        raise KLCError(
            "region %s holds %d keys, got %d" % (region, SLOTS_PER_REGION, len(hid_colors))
        )

    packet = bytearray([OPCODE_COLORS, 0x00, REGION_IDS[region], 0x00])
    for keycode, rgb in hid_colors.items():
        r, g, b = rgb
        for channel in (r, g, b):
            if not 0 <= channel <= 255:
                raise KLCError("colour channel out of range: %r" % (rgb,))
        packet += bytes([r, g, b, 0, 0, 0, 0, 0, 0, 0x01, 0x00, keycode])
    packet += bytes(FRAGMENT_SIZE * (SLOTS_PER_REGION - len(hid_colors)))
    packet += TRAILER

    if len(packet) != PACKET_SIZE:
        raise KLCError("built a %d-byte packet, expected %d" % (len(packet), PACKET_SIZE))
    return bytes(packet)


def build_commit_packet():
    """The 64-byte output report that latches a written profile."""
    return bytes([OPCODE_COMMIT] + [0x00] * (COMMIT_SIZE - 1))


def build_packets(hid_colors):
    """Bucket a whole map by region and build every packet it needs.

    Returns [(region, packet), ...]. Only regions with keys to set are emitted,
    so a single-key change costs one 524-byte report rather than four.
    """
    by_region = {}
    for keycode, rgb in hid_colors.items():
        region = region_for(keycode)
        if region is None:
            raise KLCError("HID keycode %r is not in any region" % (keycode,))
        by_region.setdefault(region, {})[keycode] = rgb
    return [(r, build_region_packet(r, by_region[r])) for r in REGION_IDS if r in by_region]


class KLCDevice:
    """Thin hidapi wrapper. Import of hidapi is deferred so the pure-model code
    and its tests run on machines without the library.

    `hid_module`, `sleep` and `clock` exist for the tests; production callers
    leave them at their defaults."""

    # When the last commit went out, process-wide: the controller is one
    # device however many KLCDevice objects a caller opens.
    _last_commit = None

    def __init__(self, product_id=0x1122, path=None, hid_module=None, sleep=None, clock=None):
        if os.geteuid() == 0:
            raise KLCError(
                "refusing to run as root - install the udev rule instead "
                "(udev/70-steelseries-klc.rules)"
            )
        if hid_module is None:
            try:
                import hid as hid_module
            except ImportError as exc:  # pragma: no cover - depends on host
                raise KLCError(
                    "python-hidapi is not installed (pacman -S python-hidapi)"
                ) from exc
        self._hid = hid_module
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic
        self._device = hid_module.device()
        if path:
            self._device.open_path(path)
        else:
            self._device.open(VENDOR_ID, product_id)

    def _send(self, method, data, label):
        """Send one report, paced, and refuse to continue if the controller
        did not take all of it. hidapi returns -1 on failure instead of
        raising, so an unchecked call would report success for a report that
        never landed."""
        result = None
        for attempt in range(RETRIES + 1):
            if attempt:
                self._sleep(RETRY_DELAY)
            result = method(data)
            self._sleep(REPORT_DELAY)
            if result == len(data):
                return attempt
        raise KLCError(
            "the controller did not accept the %s report (hidapi returned %r for %d bytes, "
            "%d attempts). The board may be showing a partial map; write it again."
            % (label, result, len(data), RETRIES + 1)
        )

    def _wait_for_settle(self):
        last = KLCDevice._last_commit
        if last is None:
            return 0.0
        remaining = last + COMMIT_SETTLE - self._clock()
        if remaining > 0:
            self._sleep(remaining)
            return remaining
        return 0.0

    def apply(self, hid_colors):
        """Write a colour map and latch it. Returns the number of reports sent.

        Every region report is checked and paced; the commit only goes out
        once all of them were accepted, so a refused region raises instead
        of latching a half-written map."""
        packets = build_packets(hid_colors)
        self._wait_for_settle()
        for region, packet in packets:
            self._send(self._device.send_feature_report, packet, "%s region" % region)
        self._send(self._device.write, build_commit_packet(), "commit")
        KLCDevice._last_commit = self._clock()
        return len(packets) + 1

    def close(self):
        try:
            self._device.close()
        except Exception:  # pragma: no cover - best effort
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
