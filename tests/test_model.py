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


# --- no brightness layer ---------------------------------------------------

def test_brightness_field_is_ignored(km):
    """A leftover brightness value must not dim anything: the chassis Fn keys
    own dimming, and an old snapshot may still carry the field."""
    assert model.resolve({"base": "#c8c8c8", "brightness": 50}, km)["Q"] == (200, 200, 200)
    assert not hasattr(model, "apply_brightness")


# --- validation ------------------------------------------------------------

@pytest.mark.parametrize("bad", ["#ff", "ff2a2", "nope", "#gggggg", "", None, 42])
def test_bad_colours_rejected(bad):
    with pytest.raises(model.ProfileError):
        model.parse_color(bad)


def test_hex_accepted_with_or_without_hash():
    assert model.parse_color("#ff2a2a") == model.parse_color("ff2a2a") == RED


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


def test_enter_esc_covers_both_enter_keys(km):
    """User report: painting "Esc + Enter" left the numpad Enter untouched."""
    assert km.group_members("enter_esc") == ["Esc", "Return", "KP_Enter"]
    out = model.resolve({"base": "#4a5cff", "groups": {"enter_esc": "#2aff5a"}}, km)
    assert out["Esc"] == out["Return"] == out["KP_Enter"] == (0x2A, 0xFF, 0x5A)
    assert out["KP_Add"] == BASE, "the rest of the numpad stays on the base"


# --- keymap catalogue: inheritance and model selection ---------------------

def test_every_keymap_loads_and_translates():
    for km in keymap_mod.available().values():
        assert km.keys, km.id
        for key in km.keys:
            assert km.hid_for(key) is not None, (km.id, key)


def test_gs65_extends_the_family_with_home_and_end():
    km = keymap_mod.load("GS65")
    assert km.extends == "gs75"
    assert len(km.keys) == 104
    assert km.hid_for("Home") == 74 and km.hid_for("End") == 77
    assert km.group_members("nav") == ["Insert", "Home", "Prior", "Delete", "End", "Next"]
    # Everything else is inherited unchanged.
    base = keymap_mod.load("GS75")
    assert km.hid_for("Esc") == base.hid_for("Esc") == 41
    assert km.group_members("wasd") == base.group_members("wasd")
    assert km.canonical("PrtSc") == "Print", "aliases inherit too"


def test_gs66_adds_the_power_key_on_top_of_gs65():
    from bridge import klc_hid
    km = keymap_mod.load("GS66")
    assert km.extends == "gs65"
    assert len(km.keys) == 105
    assert km.hid_for("Power") == 102
    assert klc_hid.region_for(102) == "numpad"
    assert km.hid_for("Home") == 74, "two-level inheritance"
    assert km.canonical("PowerButton") == "Power"
    out = model.resolve({"base": "#4a5cff", "groups": {"power": "#ff2a2a"}}, km)
    assert out["Power"] == RED and out["Esc"] == BASE


def test_family_keymap_lists_upstream_models_and_marks_what_was_lit():
    km = keymap_mod.load("GS75")
    assert set(km.models) == {"GE63", "GE73", "GE75", "GS63", "GS73", "GS75", "GX63", "GT63", "GL63"}
    assert km.tested == ["GS75"]
    assert sorted(keymap_mod.known_models()) == sorted(km.models + ["GS65", "GS66"])


def test_catalog_lists_each_keymap_once():
    cat = keymap_mod.catalog()
    assert sorted(c["id"] for c in cat) == ["gs65", "gs66", "gs75"]
    by_id = {c["id"]: c for c in cat}
    assert by_id["gs66"]["keys"] == 105 and by_id["gs66"]["extends"] == "gs65"


def test_extends_cycle_and_unknown_base_are_refused(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"id": "a", "extends": "b", "keys": {"Esc": 9}, "x11_to_hid": {"9": 41}}))
    (tmp_path / "b.json").write_text(json.dumps({"id": "b", "extends": "a", "keys": {"Esc": 9}, "x11_to_hid": {"9": 41}}))
    with pytest.raises(keymap_mod.KeymapError, match="circular"):
        keymap_mod.available(str(tmp_path))
    (tmp_path / "b.json").write_text(json.dumps({"id": "b", "extends": "zzz", "keys": {"Esc": 9}, "x11_to_hid": {"9": 41}}))
    with pytest.raises(keymap_mod.KeymapError, match="unknown keymap"):
        keymap_mod.available(str(tmp_path))


@pytest.mark.parametrize("product, token", [
    ("GS75 Stealth 8SF", "GS75"),
    ("GS65 Stealth Thin 8RE", "GS65"),
    ("GS66 Stealth 12UGS", "GS66"),
    ("GE75 Raider 8SF", "GE75"),
    ("Raider GE78HX 13VI", "GE78"),
    ("GP66 Leopard 11UG", "GP66"),
    ("Titan GT77HX 13VH", "GT77"),
    ("Katana 15 B13VFK", None),
    ("Stealth 16 Studio A13VG", None),
    ("", None),
    (None, None),
])
def test_model_token_from_dmi_product_name(product, token):
    from bridge import detect
    assert detect.model_token(product) == token


def test_machine_reads_dmi_read_only(tmp_path):
    from bridge import detect
    (tmp_path / "sys_vendor").write_text("Micro-Star International Co., Ltd.\n")
    (tmp_path / "product_name").write_text("GS66 Stealth 10SE\n")
    (tmp_path / "board_name").write_text("MS-16V1\n")
    m = detect.machine(str(tmp_path))
    assert m["msi"] is True and m["model"] == "GS66" and m["board"] == "MS-16V1"
    assert m["family"] == "", "a missing DMI file reads as empty, never raises"


def test_select_prefers_override_then_dmi_then_default():
    km, info = keymap_mod.select({"model": "GS75"}, override="GS66")
    assert (km.id, info["source"], info["selected"], info["known"]) == ("gs66", "override", "GS66", True)
    km, info = keymap_mod.select({"model": "GS65"})
    assert (km.id, info["source"], info["known"], info["tested"]) == ("gs65", "dmi", True, False)
    km, info = keymap_mod.select({"model": "GS75"})
    assert (km.id, info["source"], info["tested"]) == ("gs75", "dmi", True)
    km, info = keymap_mod.select({"model": "GP66"})
    assert (km.id, info["source"], info["known"], info["detected"]) == ("gs75", "default", False, "GP66")
    km, info = keymap_mod.select({"model": None})
    assert (km.id, info["source"], info["known"]) == ("gs75", "default", False)
    with pytest.raises(keymap_mod.KeymapError):
        keymap_mod.select({"model": "GS75"}, override="Nope")
