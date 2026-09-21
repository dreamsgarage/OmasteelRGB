"""Bridge protocol and snapshot tests. No hardware required.

Hardware-touching commands are exercised through their failure paths, which is
where the user-facing behaviour actually matters: a missing device, a locked
hidraw node, or an empty snapshot must produce a clear message rather than a
traceback.
"""

import io
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bridge import snapshot  # noqa: E402
from bridge import steelseries_bridge as bridge_mod  # noqa: E402


@pytest.fixture
def bridge():
    return bridge_mod.Bridge()


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Never touch the user's real snapshot while testing."""
    monkeypatch.setattr(snapshot, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(snapshot, "SNAPSHOT_PATH", str(tmp_path / "snapshot.json"))
    yield


def run(lines):
    """Drive main() the way Service.qml will: JSON lines in, JSON lines out."""
    out = io.StringIO()
    bridge_mod.main(stdin=io.StringIO("\n".join(lines) + "\n"), stdout=out)
    return [json.loads(line) for line in out.getvalue().splitlines()]


# --- protocol --------------------------------------------------------------

def test_every_request_gets_exactly_one_response():
    responses = run(['{"cmd":"detect"}', '{"cmd":"state"}', '{"cmd":"keymap"}'])
    assert len(responses) == 3
    assert all("ok" in r for r in responses)


def test_request_id_is_echoed_back():
    responses = run(['{"cmd":"detect","id":7}'])
    assert responses[0]["id"] == 7


def test_result_cannot_clobber_the_request_id():
    """The keymap result used to carry its own 'id', silently replacing the
    request id and breaking response correlation."""
    responses = run(['{"cmd":"keymap","id":3}'])
    assert responses[0]["id"] == 3
    assert responses[0]["keymap"] == "gs75"


def test_reserved_key_collision_is_caught(bridge, monkeypatch):
    monkeypatch.setitem(bridge.HANDLERS, "detect", lambda self, req: {"ok": "nope"})
    response = bridge.handle({"cmd": "detect", "id": 1})
    assert response["ok"] is False
    assert "reserved keys" in response["error"]


def test_blank_lines_are_ignored():
    assert len(run(['{"cmd":"detect"}', "", "   ", '{"cmd":"state"}'])) == 2


def test_malformed_json_does_not_kill_the_bridge():
    responses = run(["not json", '{"cmd":"detect"}'])
    assert responses[0]["ok"] is False and "bad JSON" in responses[0]["error"]
    assert responses[1]["ok"] is True, "the bridge must survive a bad line"


def test_non_object_request_is_rejected():
    assert run(["[1,2,3]"])[0]["ok"] is False


def test_unknown_command_lists_the_known_ones():
    response = run(['{"cmd":"levitate"}'])[0]
    assert response["ok"] is False
    assert "apply" in response["error"] and "restore" in response["error"]


# --- read-only commands ----------------------------------------------------

def test_detect_is_read_only_and_reports_status():
    response = run(['{"cmd":"detect"}'])[0]
    assert response["ok"] is True
    for device in response["devices"]:
        assert device["status"] in ("ready", "needs-access", "needs-openrgb", "unsupported")
        assert "accessible" in device


def test_keymap_exposes_names_groups_and_aliases():
    response = run(['{"cmd":"keymap"}'])[0]
    assert len(response["keys"]) == 102
    assert response["groups"]["nav"] == ["Insert", "Prior", "Delete", "Next"]
    assert response["aliases"]["PrtSc"] == "Print"


def test_keymap_for_unknown_model_errors_cleanly():
    response = run(['{"cmd":"keymap","model":"Raider-A18"}'])[0]
    assert response["ok"] is False and "GS75" in response["error"]


# --- snapshot and restore --------------------------------------------------

def test_state_reports_no_snapshot_honestly():
    response = run(['{"cmd":"state"}'])[0]
    assert response["hasSnapshot"] is False
    assert response["canRestore"] is False
    assert "cannot read" in response["message"]


def test_restore_without_a_snapshot_explains_why():
    response = run(['{"cmd":"restore"}'])[0]
    assert response["ok"] is False
    assert "never written" in response["error"]


def test_brightness_without_a_profile_is_refused():
    response = run(['{"cmd":"brightness","value":50}'])[0]
    assert response["ok"] is False
    assert "apply a map first" in response["error"]


def test_snapshot_round_trips():
    profile = {"base": "#4a5cff", "groups": {"arrows": "#ff2a2a"}, "brightness": 80}
    snapshot.save(profile, device_id="1038:1122")
    stored = snapshot.load()
    assert stored["profile"] == profile
    assert stored["device"] == "1038:1122"
    assert stored["schemaVersion"] == 1


def test_snapshot_write_is_atomic(tmp_path):
    snapshot.save({"base": "#000000"})
    leftovers = [p for p in os.listdir(snapshot.STATE_DIR) if p.startswith(".snapshot-")]
    assert leftovers == [], "a temp file survived the write"


def test_corrupt_snapshot_reads_as_absent():
    os.makedirs(snapshot.STATE_DIR, exist_ok=True)
    with open(snapshot.SNAPSHOT_PATH, "w", encoding="utf-8") as fh:
        fh.write("{ not json")
    assert snapshot.load() is None


def test_state_sees_a_saved_profile():
    snapshot.save({"base": "#4a5cff"}, device_id="1038:1122")
    response = run(['{"cmd":"state"}'])[0]
    assert response["hasSnapshot"] is True
    assert response["profile"]["base"] == "#4a5cff"
    assert response["message"] is None


# --- validation happens in the bridge, not only in QML --------------------

def test_apply_rejects_a_bad_hex_before_reaching_hardware():
    response = run(['{"cmd":"apply","profile":{"base":"#zzzzzz"}}'])[0]
    assert response["ok"] is False


def test_apply_requires_a_profile_object():
    response = run(['{"cmd":"apply","profile":"blue"}'])[0]
    assert response["ok"] is False and "profile" in response["error"]


def test_set_group_rejects_an_unknown_group():
    response = run(['{"cmd":"set_group","group":"nope","color":"#ff0000"}'])[0]
    assert response["ok"] is False and "unknown group" in response["error"]


@pytest.mark.parametrize("value", [-1, 101, "loud"])
def test_brightness_range_is_enforced(value):
    snapshot.save({"base": "#4a5cff"})
    response = run(['{"cmd":"brightness","value":%s}' % json.dumps(value)])[0]
    assert response["ok"] is False


def test_locked_device_reports_needs_access_with_a_fix(monkeypatch):
    """On a machine without the udev rule, apply must explain the fix.

    The device is faked as present-but-locked so this never opens hardware.
    Sending a real apply and skipping if it succeeds would, on a machine where
    access works, overwrite the map the controller is replaying."""
    from bridge import detect
    monkeypatch.setattr(detect, "scan", lambda: [{
        "id": "1038:1122", "kind": "klc", "product_id": 0x1122, "accessible": False,
        "status": "needs-access",
        "hint": "Install udev/70-steelseries-klc.rules, then udevadm control --reload",
    }])
    response = run(['{"cmd":"apply","profile":{"base":"#4a5cff"}}'])[0]
    assert response["ok"] is False
    assert response["needsAccess"] is True
    assert "70-steelseries-klc.rules" in response["error"]


# --- presets and the snapshot contract ------------------------------------

def test_presets_are_listed_with_profile_split_from_metadata():
    response = run(['{"cmd":"presets"}'])[0]
    assert response["ok"] is True
    ids = [p["id"] for p in response["presets"]]
    assert "gs75-photo" in ids
    assert "gs75-custom" in ids
    photo = next(p for p in response["presets"] if p["id"] == "gs75-photo")
    assert set(photo["profile"]) <= set(bridge_mod.PROFILE_FIELDS)
    assert "notes" not in photo["profile"]
    assert photo["profile"]["base"] == "#4a5cff"
    assert photo["model"] == "GS75"


def test_apply_snapshots_only_the_layer_stack(bridge, monkeypatch):
    """A preset document carries notes and provenance; the snapshot must not."""
    monkeypatch.setattr(bridge, "klc_device", lambda: {"id": "1038:1122", "product_id": 0x1122})
    monkeypatch.setattr(bridge, "write", lambda profile, device=None: {"keys": 1, "reports": 2})
    doc = {"base": "#4a5cff", "notes": {"x": "y"}, "hardware": {"model": "GS75"}, "brightness": 100}
    response = bridge.handle({"cmd": "apply", "profile": doc})
    assert response["ok"] is True
    assert snapshot.load()["profile"] == {"base": "#4a5cff", "brightness": 100}


def test_ready_handshake_is_opt_in():
    """Service.qml passes --ready and waits for the event before writing, so a
    request queued during process start-up is never lost. Plain runs, and
    these tests, must not see it."""
    out = io.StringIO()
    bridge_mod.main(stdin=io.StringIO('{"cmd":"detect","id":1}\n'), stdout=out, argv=["--ready"])
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert lines[0] == {"ok": True, "event": "ready"}
    assert lines[1]["id"] == 1
    assert "event" not in run(['{"cmd":"detect"}'])[0]
