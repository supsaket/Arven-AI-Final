"""Day 2 focused tests: Life OS (91), Events & Dates (92),
Project Memory (103). Uses temp kv and output dirs; real datetime math."""

import os
from datetime import datetime

import pytest

from core.events import EventsCalendar
from core.kv import KeyValueStore
from core.life_os import LifeOS
from core.project_memory import ProjectVault


@pytest.fixture
def kv(tmp_path):
    return KeyValueStore(str(tmp_path / "kv.json"))


# ----------------------------------------------------------------------
# 91 Life OS
# ----------------------------------------------------------------------

class TestLifeOS:

    def test_default_rituals(self):
        life = LifeOS()
        assert "health" in life.domains
        assert life.default_rituals("health") == LifeOS.DEFAULT_RITUALS["health"]
        assert life.default_rituals("money")
        with pytest.raises(ValueError):
            life.default_rituals("nope")

    def test_add_ritual_and_checklist(self, kv):
        life = LifeOS(kv=kv)
        life.add_ritual("growth", "Ship one small thing daily")
        assert "Ship one small thing daily" in life.rituals("growth")
        assert life.checklist("work") == LifeOS.DEFAULT_CHECKLISTS["work"]

    def test_satisfaction_averages(self, kv):
        life = LifeOS(kv=kv)
        assert life.track_mood_satisfaction("health", 6)["average"] == 6.0
        assert life.track_mood_satisfaction("health", 8)["average"] == 7.0
        assert life.satisfaction("health")["average"] == 7.0
        assert life.satisfaction("fun")["average"] is None
        with pytest.raises(ValueError):
            life.track_mood_satisfaction("health", 12)

    def test_weekly_review_exists(self, kv):
        life = LifeOS(kv=kv)
        life.track_mood_satisfaction("work", 7)
        life.track_mood_satisfaction("work", 9)
        review = life.weekly_review("2026-W36")
        assert "ARVEN Weekly Review — 2026-W36" in review
        assert "Work" in review
        assert "satisfaction: 8.0" in review
        assert any("not medical advice" in line.lower()
                   for line in review.splitlines())

    def test_health_non_diagnostic_disclaimer(self):
        life = LifeOS()
        assert "NOT medical advice" in life.health_disclaimer


# ----------------------------------------------------------------------
# 92 Events & Important Dates
# ----------------------------------------------------------------------

NOW = datetime(2026, 9, 6, 9, 0, 0)


class TestEventsCalendar:

    def test_add_and_list(self, kv):
        calendar = EventsCalendar(kv=kv)
        calendar.add("Standup", "2026-09-07", time="09:30",
                     reminder_offset_min=15)
        assert calendar.list()[0]["title"] == "Standup"
        assert calendar.list()[0]["date"] == "2026-09-07"

    def test_upcoming_filtering(self, kv):
        calendar = EventsCalendar(kv=kv, now_fn=lambda: NOW)
        calendar.add("Soon", "2026-09-07")
        calendar.add("Later", "2026-12-25")
        upcoming = calendar.upcoming(days=7, now=NOW)
        titles = [e["title"] for e in upcoming]
        assert "Soon" in titles
        assert "Later" not in titles

    def test_recurring_year_rollover(self, kv):
        calendar = EventsCalendar(kv=kv)
        calendar.add("Birthday", "2026-01-01", recurring="yearly")
        occurrences = calendar.upcoming(
            days=5, now=datetime(2026, 12, 31, 23, 0))
        # next instance is 2027-01-01, across the year rollover
        assert occurrences and occurrences[0]["timestamp"].startswith("2027-01-01")

    def test_conflicts(self, kv):
        calendar = EventsCalendar(kv=kv)
        calendar.add("Planning", "2026-09-10", time="10:00")
        calendar.add("Other", "2026-09-10")
        conflicts = calendar.conflicts("2026-09-10")
        assert len(conflicts) == 2
        assert calendar.conflicts("2026-09-11") == []

    def test_export_structure(self, kv, tmp_path):
        calendar = EventsCalendar(kv=kv)
        calendar.add("Launch", "2026-09-20", time="10:00")
        out = calendar.export(directory=str(tmp_path / "events"))
        assert os.path.exists(out["path"])
        text = out["text"]
        assert text.startswith("BEGIN:VCALENDAR")
        assert "VERSION:2.0" in text
        assert "BEGIN:VEVENT" in text
        assert "SUMMARY:Launch" in text
        assert "END:VCALENDAR" in text


# ----------------------------------------------------------------------
# 103 Project Memory
# ----------------------------------------------------------------------

class TestProjectVault:

    def test_lifecycle_and_decisions(self, kv):
        vault = ProjectVault(kv=kv)
        vault.create_project("Arven Day 2", phases=[
            {"id": "spec", "title": "Spec", "status": "open"},
            {"id": "build", "title": "Build", "status": "open"},
        ])
        vault.check_in("Arven Day 2", "spec", "finalised module list")
        assert len(vault.query_project("Arven Day 2")["decisions"]) == 1
        phases = vault.advance_phase("Arven Day 2", "spec")
        status = {p["id"]: p["status"] for p in phases}
        assert status["spec"] == "complete"
        vault.update_risk("Arven Day 2", "scope creep",
                          likelihood=0.4, impact=0.8)
        assert len(vault.query_project("Arven Day 2")["risk_register"]) == 1
        status = vault.project_status("Arven Day 2")
        assert status["decisions"] == 1
        assert status["risks"] == 1

    def test_restart_persistence(self, tmp_path):
        path = str(tmp_path / "kv.json")
        vault_1 = ProjectVault(kv=KeyValueStore(path))
        vault_1.create_project("Resume Me")
        vault_1.check_in("Resume Me", "spec", "notes survive restart")
        vault_2 = ProjectVault(kv=KeyValueStore(path))
        assert vault_2.query_project("Resume Me")["decisions"][0]["text"] == \
            "notes survive restart"