"""Colour model tests. No hardware required."""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bridge import keymap as keymap_mod  # noqa: E402
from bridge import model  # noqa: E402

RED = (255, 42, 42)
BASE = (74, 92, 255)  # #4a5cff


@pytest.fixture(scope="module")
def km():
    return keymap_mod.load("GS75")


def preset(name):
    with open(os.path.join(ROOT, "presets", name), encoding="utf-8") as fh:
        return json.load(fh)


# --- keymap ----------------------------------------------------------------

def test_keymap_loads_by_model_and_by_id(km):
    assert km.id == "gs75"
    assert "GS75" in km.models
    assert keymap_mod.load("gs75").id == "gs75"
    assert keymap_mod.load("ge63").id == "gs75", "sibling models share one keymap"


def test_unknown_model_names_known_ones():
    with pytest.raises(keymap_mod.KeymapError, match="GS75"):
        keymap_mod.load("Raider-A18")


def test_every_key_translates_to_a_hid_code(km):
    assert len(km.keys) == 102
    missing = [k for k in km.keys if km.hid_for(k) is None]
    assert missing == []


def test_aliases_resolve(km):
    assert km.canonical("PrtSc") == "Print"
    assert km.canonical("Win") == "Super"
    assert km.hid_for("ScrollLock") == km.hid_for("Scroll_Lock")


def test_home_and_end_are_absent(km):
    """They appear lit in the reference photo but have no addressable LED."""
    assert "Home" not in km.keys
    assert "End" not in km.keys


def test_the_two_delete_keys_are_distinct(km):
    assert km.hid_for("Delete") != km.hid_for("KP_Delete")
    assert "Delete" in km.group_members("nav")
    assert "KP_Delete" in km.group_members("numpad")


# --- precedence ------------------------------------------------------------

def test_smallest_group_wins_over_larger_overlapping_group(km):
    """wasd (4 keys) beats characters (35 keys) regardless of dict order."""
    for groups in (
        {"characters": "#00ff00", "wasd": "#ff0000"},
        {"wasd": "#ff0000", "characters": "#00ff00"},
    ):
        out = model.resolve({"base": "#000000", "groups": groups}, km)
        assert out["W"] == (255, 0, 0)
        assert out["Q"] == (0, 255, 0)


def test_per_key_override_beats_every_group(km):
    out = model.resolve(
        {"base": "#000000", "groups": {"wasd": "#ff0000"}, "keys": {"W": "#0000ff"}}, km
    )
    assert out["W"] == (0, 0, 255)
    assert out["A"] == (255, 0, 0)


def test_numpad_ops_beats_numpad(km):
    out = model.resolve(
        {"base": "#000000", "groups": {"numpad": "#00ff00", "numpad_ops": "#ff0000"}}, km
    )
    assert out["KP_Add"] == (255, 0, 0)
    assert out["KP_5"] == (0, 255, 0)


# --- the acceptance fixture ------------------------------------------------

def test_gs75_photo_resolves_completely(km):
    out = model.resolve(preset("gs75-photo.json"), km)
    assert len(out) == 102, "every addressable key must get a colour"
    assert sum(1 for c in out.values() if c == RED) == 17
    assert sum(1 for c in out.values() if c == BASE) == 85
    assert set(out.values()) == {RED, BASE}


def test_gs75_photo_keeps_numpad_digits_on_base(km):
    out = model.resolve(preset("gs75-photo.json"), km)
    digits = [f"KP_{n}" for n in range(10)] + ["KP_Delete", "KP_Enter"]
    assert all(out[k] == BASE for k in digits)
    assert all(out[k] == RED for k in ("Num_Lock", "KP_Divide", "KP_Multiply", "KP_Subtract", "KP_Add"))


def test_gs75_photo_red_keys_are_exactly_the_documented_set(km):
    out = model.resolve(preset("gs75-photo.json"), km)
    expected = {
        "Esc", "Tab", "Fn", "Super",
        "Up", "Down", "Left", "Right",
        "Insert", "Prior", "Delete", "Next",
        "Num_Lock", "KP_Divide", "KP_Multiply", "KP_Subtract", "KP_Add",
    }
    assert {k for k, c in out.items() if c == RED} == expected


def test_gs75_custom_reddens_the_whole_top_row(km):
    out = model.resolve(preset("gs75-custom.json"), km)
    assert len(out) == 102
    top_row = ["Esc"] + [f"F{n}" for n in range(1, 13)] + ["Print", "Scroll_Lock", "Pause"]
    assert all(out[k] == RED for k in top_row)
    assert sum(1 for c in out.values() if c == RED) == 32


# --- brightness ------------------------------------------------------------

def test_brightness_scales_every_channel(km):
    out = model.resolve({"base": "#c8c8c8", "brightness": 50}, km)
    assert set(out.values()) == {(100, 100, 100)}


def test_brightness_100_is_lossless(km):
    assert model.resolve({"base": "#4a5cff", "brightness": 100}, km)["Q"] == BASE


def test_brightness_zero_is_black(km):
    assert set(model.resolve({"base": "#ffffff", "brightness": 0}, km).values()) == {(0, 0, 0)}


# --- validation ------------------------------------------------------------

@pytest.mark.parametrize("bad", ["#ff", "ff2a2", "nope", "#gggggg", "", None, 42])
def test_bad_colours_rejected(bad):
    with pytest.raises(model.ProfileError):
        model.parse_color(bad)


def test_hex_accepted_with_or_without_hash():
    assert model.parse_color("#ff2a2a") == model.parse_color("ff2a2a") == RED


@pytest.mark.parametrize("bad", [-1, 101, "high", None])
def test_bad_brightness_rejected(bad):
    with pytest.raises(model.ProfileError):
        model.parse_brightness(bad)


def test_unknown_key_is_rejected_with_a_suggestion(km):
    with pytest.raises(model.ProfileError, match="Esc"):
        model.resolve({"base": "#000000", "keys": {"Escp": "#ffffff"}}, km)


def test_unknown_group_is_rejected(km):
    with pytest.raises(keymap_mod.KeymapError, match="unknown group"):
        model.resolve({"base": "#000000", "groups": {"nope": "#ffffff"}}, km)


def test_empty_profile_is_rejected(km):
    with pytest.raises(model.ProfileError, match="sets no colours"):
        model.resolve({}, km)


# --- translation to the wire ----------------------------------------------

def test_to_hid_map_covers_every_key(km):
    out = model.resolve(preset("gs75-photo.json"), km)
    hid = model.to_hid_map(out, km)
    assert len(hid) == 102, "no key may be dropped on the way to the packet"


def test_blackout_is_all_zero(km):
    out = model.blackout(km)
    assert len(out) == 102
    assert set(out.values()) == {(0, 0, 0)}
