"""Day 3 lifecycle tracker state machine (T9)."""

import json

import pytest

import day3_lifecycle as tracker


@pytest.fixture()
def hermetic_state(tmp_path, monkeypatch):
    path = tmp_path / "day3_state.json"
    monkeypatch.setattr(tracker, "_STATE_FILE", str(path))
    return str(path)


def test_init_creates_nine_targets(hermetic_state):
    doc = tracker.init()
    assert set(doc["targets"]) == {
        "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9"}
    for target in doc["targets"].values():
        assert target["state"] == "TO_ADD"
        assert target["started_at"]
        assert target["updated_at"]


def test_legal_forward_transitions_full_cycle(hermetic_state):
    tracker.init()
    for state in ("WORK", "IN_PROGRESS", "WORK", "USABLE",
                  "TEST", "STRONG", "COMPLETE", "FINAL"):
        tracker.advance("T1", state)
    target = tracker._load()["targets"]["T1"]
    assert target["state"] == "FINAL"
    assert target["finalized_at"]


def test_final_is_terminal(hermetic_state):
    tracker.init()
    for state in ("WORK", "IN_PROGRESS", "WORK", "USABLE",
                  "TEST", "STRONG", "COMPLETE", "FINAL"):
        tracker.advance("T2", state)
    with pytest.raises(ValueError, match="FINAL"):
        tracker.advance("T2", "WORK")


def test_illegal_forward_transition_raises(hermetic_state):
    tracker.init()
    with pytest.raises(ValueError, match="illegal transition"):
        tracker.advance("T3", "TEST")          # TEST before any WORK


def test_failure_bounce_back_to_work_allowed(hermetic_state):
    tracker.init()
    tracker.advance("T4", "WORK")
    tracker.advance("T4", "IN_PROGRESS")
    tracker.advance("T4", "WORK")
    tracker.advance("T4", "USABLE")
    tracker.advance("T4", "WORK")              # defect discovered -> bounce
    assert tracker._load()["targets"]["T4"]["state"] == "WORK"


def test_same_state_advance_is_noop_and_illegal_reverse_raises(hermetic_state):
    tracker.init()
    tracker.advance("T5", "WORK")
    tracker.advance("T5", "WORK")          # idempotent no-op (advance safe)
    assert tracker._load()["targets"]["T5"]["state"] == "WORK"
    with pytest.raises(ValueError, match="illegal transition"):
        tracker.advance("T5", "TO_ADD")    # cannot regress the machine


def test_link_records_and_dedupes(hermetic_state):
    tracker.init()
    tracker.link("T6", "core/cyber_toolkit.py", "evidence")
    tracker.link("T6", "core/cyber_toolkit.py", "evidence")
    tracker.link("T8", "tests/day3/test_day3_terminal.py", "tests")
    target = tracker._load()["targets"]["T6"]
    assert len(target["evidence"]) == 1
    assert tracker._load()["targets"]["T8"]["tests"][0]["path"].endswith(
        "test_day3_terminal.py")


def test_failure_and_limitation_recorded(hermetic_state):
    tracker.init()
    tracker.advance("T2", "WORK")
    tracker.record_failure("T2", "infinite loop on escalation")
    tracker.record_limitation("T2", "empty-list results wrap to success=False")
    target = tracker._load()["targets"]["T2"]
    assert any("infinite loop" in f["note"] for f in target["failures"])
    assert any("success=False" in l["note"] for l in target["limitations"])


def test_unknown_target_rejected(hermetic_state):
    tracker.init()
    with pytest.raises(ValueError, match="unknown target"):
        tracker.advance("TX", "WORK")


def test_verify_reports_valid(hermetic_state):
    tracker.init()
    result = tracker.verify()
    assert result == {"valid": True, "errors": [], "targets": 9}


def test_verify_flags_final_without_finalized_at(hermetic_state):
    tracker.init()
    doc = tracker._load()
    doc["targets"]["T7"]["state"] = "FINAL"
    doc["targets"]["T7"]["finalized_at"] = None
    tracker._save(doc)
    result = tracker.verify()
    assert result["valid"] is False


def test_live_state_file_is_valid_json():
    with open("day3_state.json", "r", encoding="utf-8") as handle:
        doc = json.load(handle)
    assert isinstance(doc, dict)
    assert len(doc.get("targets", {})) == 9
    for target_id, target in doc["targets"].items():
        assert target_id in ("T1", "T2", "T3", "T4", "T5",
                             "T6", "T7", "T8", "T9")
        assert target["state"] in tracker._ORDER
        assert target["started_at"]
        assert target["updated_at"]


def test_live_state_transitions_are_legal():
    doc = json.load(open("day3_state.json", "r", encoding="utf-8"))
    for target in doc["targets"].values():
        if target["state"] == "FINAL":
            assert target["finalized_at"]