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
    assert len(seen) == 113


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
