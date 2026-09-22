"""Packet builder tests. No hardware required.

The differential tests compare our port against the upstream msi-perkeyrgb
implementation byte for byte. They skip when upstream is not importable, so the
suite still runs on a machine that has never installed it.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bridge import keymap as keymap_mod  # noqa: E402
from bridge import klc_hid  # noqa: E402
from bridge import model  # noqa: E402

# Upstream lives in the system site-packages, which a venv does not see by default.
for candidate in sys.path + ["/usr/lib/python3.14/site-packages", "/usr/lib/python3/dist-packages"]:
    if os.path.isdir(os.path.join(candidate, "msi_perkeyrgb")):
        sys.path.append(candidate)
        break
try:
    from msi_perkeyrgb.msiprotocol import make_key_colors_packet, make_refresh_packet
    HAVE_UPSTREAM = True
except ImportError:  # pragma: no cover - depends on host
    HAVE_UPSTREAM = False

needs_upstream = pytest.mark.skipif(not HAVE_UPSTREAM, reason="msi-perkeyrgb not installed")


@pytest.fixture(scope="module")
def km():
    return keymap_mod.load("GS75")


# --- structure -------------------------------------------------------------

def test_packet_is_exactly_524_bytes():
    packet = klc_hid.build_region_packet("alphanum", {4: (1, 2, 3)})
    assert len(packet) == klc_hid.PACKET_SIZE == 524


def test_packet_header_carries_the_region_id():
    packet = klc_hid.build_region_packet("numpad", {})
    assert packet[:4] == bytes([0x0E, 0x00, 0x24, 0x00])


def test_key_fragment_layout():
    packet = klc_hid.build_region_packet("alphanum", {7: (255, 42, 42)})
    assert list(packet[4:16]) == [255, 42, 42, 0, 0, 0, 0, 0, 0, 0x01, 0x00, 7]


def test_unused_slots_are_zero_filled():
    packet = klc_hid.build_region_packet("alphanum", {4: (9, 9, 9)})
    assert packet[16:-16] == bytes(12 * 41)


def test_trailer_is_constant():
    packet = klc_hid.build_region_packet("enter", {})
    assert packet[-16:] == bytes([0] * 14 + [0x08, 0x39])


def test_commit_packet():
    commit = klc_hid.build_commit_packet()
    assert len(commit) == 64
    assert commit[0] == 0x09
    assert commit[1:] == bytes(63)


def test_no_effect_opcode_is_reachable():
    """0x0b effects bricked a backlight upstream. They must not exist here."""
    source = open(os.path.join(ROOT, "bridge", "klc_hid.py"), encoding="utf-8").read()
    assert "0x0B" not in source.upper().replace("0X0B", "0x0B") or "OPCODE_EFFECT" not in source
    assert not hasattr(klc_hid, "build_effect_packet")


# --- bucketing -------------------------------------------------------------

def test_every_region_is_42_slots():
    assert all(len(v) == 42 for v in klc_hid.REGION_KEYCODES.values())


def test_regions_do_not_overlap():
    """Ignoring the 0 padding, no real keycode may appear in two regions -
    it would be written twice, in two different packets."""
    seen = set()
    for codes in klc_hid.REGION_KEYCODES.values():
        real = {c for c in codes if c != klc_hid.EMPTY_SLOT}
        assert not (seen & real), "a keycode in two regions would be written twice"
        seen |= real
    assert len(seen) == 114  # 113 upstream + 102, the GS66 power key


def test_padding_slot_is_not_addressable():
    """0 pads three of the four region lists; it must never bucket as a key."""
    assert klc_hid.region_for(klc_hid.EMPTY_SLOT) is None
    with pytest.raises(klc_hid.KLCError, match="not in any region"):
        klc_hid.build_packets({0: (255, 0, 0)})


def test_single_key_change_emits_one_packet():
    packets = klc_hid.build_packets({4: (255, 0, 0)})
    assert len(packets) == 1
    assert packets[0][0] == "alphanum"


def test_full_profile_emits_four_packets(km):
    colors = model.resolve({"base": "#4a5cff"}, km)
    packets = klc_hid.build_packets(model.to_hid_map(colors, km))
    assert sorted(r for r, _ in packets) == ["alphanum", "enter", "modifiers", "numpad"]


def test_overfull_region_is_rejected():
    with pytest.raises(klc_hid.KLCError, match="holds 42 keys"):
        klc_hid.build_region_packet("alphanum", {i: (0, 0, 0) for i in range(43)})


def test_out_of_range_channel_is_rejected():
    with pytest.raises(klc_hid.KLCError, match="out of range"):
        klc_hid.build_region_packet("alphanum", {4: (0, 300, 0)})


def test_unknown_region_is_rejected():
    with pytest.raises(klc_hid.KLCError, match="unknown region"):
        klc_hid.build_region_packet("spacebar", {})


# --- differential against upstream ----------------------------------------

@needs_upstream
def test_matches_upstream_for_a_single_key():
    ours = klc_hid.build_region_packet("alphanum", {4: (255, 42, 42)})
    theirs = bytes(make_key_colors_packet("alphanum", {4: [255, 42, 42]}))
    assert ours == theirs


@needs_upstream
@pytest.mark.parametrize("region", ["alphanum", "enter", "modifiers", "numpad"])
def test_matches_upstream_for_a_full_region(region):
    colors = {code: [(code * 7) % 256, (code * 13) % 256, (code * 29) % 256]
              for code in klc_hid.REGION_KEYCODES[region]}
    ours = klc_hid.build_region_packet(region, colors)
    theirs = bytes(make_key_colors_packet(region, colors))
    assert ours == theirs


@needs_upstream
def test_matches_upstream_for_the_acceptance_fixture(km):
    import json
    with open(os.path.join(ROOT, "presets", "gs75-photo.json"), encoding="utf-8") as fh:
        profile = json.load(fh)
    hid_colors = model.to_hid_map(model.resolve(profile, km), km)

    by_region = {}
    for code, rgb in hid_colors.items():
        by_region.setdefault(klc_hid.region_for(code), {})[code] = list(rgb)

    ours = dict(klc_hid.build_packets(hid_colors))
    assert set(ours) == set(by_region)
    for region, colors in by_region.items():
        assert ours[region] == bytes(make_key_colors_packet(region, colors)), region


@needs_upstream
def test_commit_matches_upstream():
    assert klc_hid.build_commit_packet() == bytes(make_refresh_packet())


# --- sending ---------------------------------------------------------------
#
# The controller drops reports that arrive too fast and hidapi signals a
# refused report with -1 rather than an exception. These pin the pacing and
# the checking, with a fake hid module in place of the library.

class FakeHidDevice:
    def __init__(self, log, refuse=None):
        self.log = log
        # {call index: return value} to simulate a refused report.
        self.refuse = refuse or {}
        self.calls = 0

    def open(self, vid, pid):
        self.log.append(("open", vid, pid))

    def open_path(self, path):
        self.log.append(("open_path", path))

    def _result(self, data):
        self.calls += 1
        return self.refuse.get(self.calls, len(data))

    def send_feature_report(self, data):
        self.log.append(("feature", bytes(data)[2], len(data)))
        return self._result(data)

    def write(self, data):
        self.log.append(("write", bytes(data)[0], len(data)))
        return self._result(data)

    def close(self):
        self.log.append(("close",))


class FakeHid:
    def __init__(self, refuse=None):
        self.log = []
        self.refuse = refuse

    def device(self):
        return FakeHidDevice(self.log, self.refuse)


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def sleep(self, seconds):
        self.slept.append(round(seconds, 4))
        self.now += seconds

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def fresh_controller():
    """The settle timestamp is process-wide; tests must not leak it."""
    klc_hid.KLCDevice._last_commit = None
    yield
    klc_hid.KLCDevice._last_commit = None


def open_fake(refuse=None):
    fake, clock = FakeHid(refuse), FakeClock()
    dev = klc_hid.KLCDevice(hid_module=fake, sleep=clock.sleep, clock=clock)
    return dev, fake, clock


def full_map(km):
    return model.to_hid_map(model.resolve({"base": "#4a5cff"}, km), km)


def test_every_report_is_paced(km):
    dev, fake, clock = open_fake()
    sent = dev.apply(full_map(km))
    assert sent == 5
    # Four feature reports, region order fixed, then the commit as an output report.
    kinds = [entry[0] for entry in fake.log if entry[0] in ("feature", "write")]
    assert kinds == ["feature"] * 4 + ["write"]
    regions = [entry[1] for entry in fake.log if entry[0] == "feature"]
    assert regions == [klc_hid.REGION_IDS[r] for r in ("alphanum", "enter", "modifiers", "numpad")]
    # One REPORT_DELAY after each of the five sends, nothing else.
    assert clock.slept == [klc_hid.REPORT_DELAY] * 5


def test_refused_region_raises_and_never_commits(km):
    dev, fake, clock = open_fake(refuse={2: -1, 3: -1, 4: -1})
    with pytest.raises(klc_hid.KLCError, match="enter region"):
        dev.apply(full_map(km))
    assert not any(entry[0] == "write" for entry in fake.log), "a half-written map must not be latched"


def test_short_write_counts_as_refused(km):
    dev, fake, clock = open_fake(refuse={1: 100, 2: 100, 3: 100})
    with pytest.raises(klc_hid.KLCError, match="returned 100 for 524 bytes"):
        dev.apply(full_map(km))


def test_refused_report_is_retried_then_accepted(km):
    dev, fake, clock = open_fake(refuse={1: -1})
    assert dev.apply(full_map(km)) == 5
    features = [entry for entry in fake.log if entry[0] == "feature"]
    assert len(features) == 5, "alphanum once refused, once accepted, then three more regions"
    assert clock.slept[:3] == [klc_hid.REPORT_DELAY, klc_hid.RETRY_DELAY, klc_hid.REPORT_DELAY]


def test_refused_commit_raises():
    dev, fake, clock = open_fake(refuse={2: -1, 3: -1, 4: -1})
    with pytest.raises(klc_hid.KLCError, match="commit report"):
        dev.apply({4: (1, 2, 3)})


def test_back_to_back_writes_wait_for_the_commit_to_settle(km):
    """off then restore in quick succession: the second write must give the
    controller COMMIT_SETTLE after the first commit before it starts."""
    dev, fake, clock = open_fake()
    dev.apply(full_map(km))
    first_commit = clock.now
    clock.now += 0.05
    dev.apply(full_map(km))
    # The first sleep of the second write is the remaining settle time.
    settle = clock.slept[5]
    assert settle == pytest.approx(klc_hid.COMMIT_SETTLE - 0.05, abs=1e-6)
    assert first_commit + klc_hid.COMMIT_SETTLE <= first_commit + 0.05 + settle + 1e-9


def test_settle_is_shared_across_device_objects(km):
    """The bridge opens a fresh KLCDevice per command; the pause must survive that."""
    dev1, fake1, clock = open_fake()
    dev1.apply(full_map(km))
    dev2 = klc_hid.KLCDevice(hid_module=FakeHid(), sleep=clock.sleep, clock=clock)
    dev2.apply(full_map(km))
    assert clock.slept[5] == pytest.approx(klc_hid.COMMIT_SETTLE, abs=1e-6)


def test_isolated_write_does_not_wait(km):
    dev, fake, clock = open_fake()
    dev.apply(full_map(km))
    clock.now += 5.0
    before = len(clock.slept)
    dev.apply(full_map(km))
    assert clock.slept[before:] == [klc_hid.REPORT_DELAY] * 5


def test_report_delay_matches_upstream():
    """msi-perkeyrgb has shipped DELAY = 0.01 for years; drift here is a hardware regression."""
    assert klc_hid.REPORT_DELAY == pytest.approx(0.01)
    assert klc_hid.COMMIT_SETTLE >= klc_hid.REPORT_DELAY
