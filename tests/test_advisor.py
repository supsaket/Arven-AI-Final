"""Tests for Advisor modules (86, 87, 88, 89, 90).
Each test uses isolated temp paths for kv storage."""

from core.advisor import (
    AdvisorRegistry,
    InteractionsCoordinator,
    PersonalTutor,
    CareerCoach,
    RelationshipCoach,
    CommunicationCoach,
    _DISCLAIMER,
)


# ------------------------------------------------------------------
# Interactions Coordinator (86)
# ------------------------------------------------------------------


class _FakeKV:
    """In-memory kv backed fake for advisor tests."""

    def __init__(self):
        self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value


class TestInteractionsCoordinator:

    def test_plan_interaction(self, tmp_path):
        coord = InteractionsCoordinator(_FakeKV())
        plan = coord.plan_interaction("executive", "Quarterly review", cadence_days=7)
        assert plan["role"] == "executive"
        assert plan["cadence_days"] == 7

    def test_add_and_pending_followup(self, tmp_path):
        coord = InteractionsCoordinator(_FakeKV())
        fu = coord.add_followup("Alice", "Send report", "2025-12-01")
        pending = coord.pending_followups()
        assert len(pending) == 1
        assert pending[0]["description"] == "Send report"

    def test_complete_followup(self, tmp_path):
        coord = InteractionsCoordinator(_FakeKV())
        fu = coord.add_followup("Bob", "Call client", "2025-12-05")
        coord.complete_followup(fu["id"])
        assert coord.pending_followups() == []


# ------------------------------------------------------------------
# Personal Tutor (87)
# ------------------------------------------------------------------


class TestPersonalTutor:

    def test_build_curriculum(self, tmp_path):
        kv = _FakeKV()
        tutor = PersonalTutor(kv)
        curriculum = tutor.build_curriculum(
            "Python", ["Basics", "Functions", "Classes"], level="beginner"
        )
        assert curriculum["topic"] == "Python"
        assert len(curriculum["modules"]) == 3
        assert curriculum["modules"][0]["quiz_draft"]["answer"] == 0

    def test_assess_scores(self, tmp_path):
        kv = _FakeKV()
        tutor = PersonalTutor(kv)
        result = tutor.assess([
            {"correct_index": 0, "selected_index": 0},
            {"correct_index": 1, "selected_index": 0},
        ])
        assert result["score"] == 1
        assert result["total"] == 2
        assert result["percentage"] == 50.0

    def test_next_lesson(self, tmp_path):
        kv = _FakeKV()
        tutor = PersonalTutor(kv)
        curriculum = tutor.build_curriculum("Math", ["Algebra", "Geometry"])
        nxt = tutor.next_lesson(curriculum["id"])
        assert nxt["module"]["title"] == "Algebra"

    def test_session_flow(self, tmp_path):
        kv = _FakeKV()
        tutor = PersonalTutor(kv)
        sid = tutor.start_session("Learn Python")
        tutor.log_exchange(sid, "Explain variables", "Variables store data")
        summary = tutor.session_summary(sid)
        assert summary["exchange_count"] == 1


# ------------------------------------------------------------------
# Career Coach (88)
# ------------------------------------------------------------------


class TestCareerCoach:

    def test_skills_gap_math(self, tmp_path):
        kv = _FakeKV()
        coach = CareerCoach(kv)
        result = coach.skills_gap(
            "software_engineer",
            ["python", "git", "sql"]
        )
        assert len(result["gaps"]) > 0
        assert "python" in result["matched"]
        assert result["gap_count"] == len(result["gaps"])
        assert len(result["action_plan"]) == result["gap_count"]

    def test_no_gaps(self, tmp_path):
        kv = _FakeKV()
        coach = CareerCoach(kv)
        result = coach.skills_gap(
            "software_engineer",
            ["python", "javascript", "git", "sql", "testing",
             "system_design", "algorithms", "docker", "linux", "api_design"]
        )
        assert result["gap_count"] == 0

    def test_interview_prep(self, tmp_path):
        kv = _FakeKV()
        coach = CareerCoach(kv)
        result = coach.interview_prep("software_engineer")
        assert len(result["checklist"]) >= 3
        assert result["disclaimer"] == _DISCLAIMER

    def test_disclaimer_present(self, tmp_path):
        kv = _FakeKV()
        coach = CareerCoach(kv)
        result = coach.skills_gap("data_scientist", ["python"])
        assert "disclaimer" in result
        assert "informational" in result["disclaimer"]


# ------------------------------------------------------------------
# Relationship Coach (89)
# ------------------------------------------------------------------


class TestRelationshipCoach:

    def test_interaction_patterns(self, tmp_path):
        kv = _FakeKV()
        coach = RelationshipCoach(kv)
        result = coach.interaction_patterns()
        assert len(result["suggestions"]) > 0
        assert result["disclaimer"] == _DISCLAIMER

    def test_schedule_and_list_checkin(self, tmp_path):
        kv = _FakeKV()
        coach = RelationshipCoach(kv)
        entry = coach.schedule_checkin("Mom", "2025-11-20", "Weekly call")
        checkins = coach.list_checkins()
        assert len(checkins) == 1
        assert checkins[0]["contact"] == "Mom"
        assert checkins[0]["date"] == "2025-11-20"

    def test_log_appreciation(self, tmp_path):
        kv = _FakeKV()
        coach = RelationshipCoach(kv)
        entry = coach.log_appreciation("Partner", "Thank you for your support")
        log = coach._kv.get("_appreciation_log", [])
        assert len(log) == 1
        assert "support" in log[0]["message"]

    def test_conflict_frameworks(self, tmp_path):
        kv = _FakeKV()
        coach = RelationshipCoach(kv)
        result = coach.conflict_resolution()
        assert len(result["frameworks"]) >= 2
        assert result["frameworks"][0]["name"]


# ------------------------------------------------------------------
# Communication Coach (90)
# ------------------------------------------------------------------


class TestCommunicationCoach:

    def test_draft_structure(self, tmp_path):
        kv = _FakeKV()
        coach = CommunicationCoach(kv)
        result = coach.draft("formal", "HR Team", ["Point 1", "Point 2"])
        assert result["draft"]["greeting"] == "Dear HR Team,"
        assert len(result["draft"]["body"]) == 2
        assert result["disclaimer"] == _DISCLAIMER

    def test_tone_check_aggressive(self, tmp_path):
        kv = _FakeKV()
        coach = CommunicationCoach(kv)
        result = coach.tone_check("You must do this immediately")
        assert result["flags"]["aggressive"]["detected"] is True

    def test_tone_check_friendly(self, tmp_path):
        kv = _FakeKV()
        coach = CommunicationCoach(kv)
        result = coach.tone_check("Thanks so much, great work, love this")
        assert result["flags"]["friendly"]["detected"] is True

    def test_tone_check_suggestions(self, tmp_path):
        kv = _FakeKV()
        coach = CommunicationCoach(kv)
        result = coach.tone_check("You must deal with this immediately")
        assert len(result["suggestions"]) > 0

    def test_speaking_tips(self, tmp_path):
        kv = _FakeKV()
        coach = CommunicationCoach(kv)
        result = coach.speaking_tips()
        assert len(result["tips"]) >= 3
        assert result["disclaimer"] == _DISCLAIMER


# ------------------------------------------------------------------
# Advisor Registry
# ------------------------------------------------------------------


class TestAdvisorRegistry:

    def test_get_advisor(self, tmp_path):
        reg = AdvisorRegistry(kv_path=str(tmp_path / "adv.json"))
        tutor = reg.get("tutor")
        assert isinstance(tutor, PersonalTutor)
        career = reg.get("career")
        assert isinstance(career, CareerCoach)

    def test_available_names(self, tmp_path):
        reg = AdvisorRegistry(kv_path=str(tmp_path / "adv.json"))
        available = reg.available()
        assert "coordinator" in available
        assert "tutor" in available
        assert "career" in available
        assert "relationship" in available
        assert "communication" in available

    def test_unknown_returns_none(self, tmp_path):
        reg = AdvisorRegistry(kv_path=str(tmp_path / "adv.json"))
        assert reg.get("nonexistent") is None
