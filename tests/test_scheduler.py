"""Scheduler contract (row 18) — parse, schedule, cancel, fire, safety."""

from datetime import datetime, timedelta

from core.scheduler import (
    Scheduler,
    SchedulerEngine,
    TaskStore,
    extract_action,
    parse,
)

NOW = datetime(2026, 9, 6, 9, 0, 0)


class TestParse:

    def test_parse_one_time_clock(self):
        parsed = parse("remind me to water the plants at 18:00", now=NOW)
        assert parsed is not None
        assert parsed["kind"] == "one_time"
        assert parsed["run_at"] == "2026-09-06 18:00"
        assert "water" in parsed["text"]

    def test_parse_relative_minutes(self):
        parsed = parse("remind me to stretch in 30 minutes", now=NOW)
        assert parsed is not None
        assert parsed["kind"] == "one_time"
        assert parsed["run_at"] == (NOW + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")

    def test_parse_daily(self):
        parsed = parse("every day at 8am", now=NOW)
        assert parsed is not None
        assert parsed["kind"] == "daily"
        assert parsed["at_time"] == "08:00"

    def test_parse_weekly_monday(self):
        parsed = parse("every monday at 9am", now=NOW)
        assert parsed is not None
        assert parsed["kind"] == "weekly"
        assert parsed["weekday"] == 0
        assert parsed["at_time"] == "09:00"

    def test_parse_tomorrow_no_clock(self):
        parsed = parse("remind me to call dad tomorrow", now=NOW)
        assert parsed is not None
        assert parsed["kind"] == "one_time"
        assert parsed["run_at"] == "2026-09-07 09:00"

    def test_gibberish_returns_none(self):
        assert parse("banana monkey pizza", now=NOW) is None

    def test_action_only_strips_schedule_words(self):
        action, verdict = extract_action("remind me to water the plants at 18:00")
        assert "water the plants" in action.lower()


class TestScheduler:

    def test_schedule_and_list(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        engine = Scheduler(store)
        result = engine.schedule("remind me to water the plants at 18:00", now=NOW)
        assert result["success"] is True
        listed = engine.list()
        assert listed["count"] == 1

    def test_duplicate_prevented(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        engine = Scheduler(store)
        engine.schedule("remind me to water the plants at 18:00", now=NOW)
        second = engine.schedule("remind me to water the plants at 18:00", now=NOW)
        assert second["success"] is False

    def test_cancel_by_description(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        engine = Scheduler(store)
        engine.schedule("remind me to water the plants at 18:00", now=NOW)
        cancelled = engine.cancel(text="cancel my water plants reminder")
        assert cancelled["success"] is True
        assert engine.list()["count"] == 0

    def test_destructive_not_scheduled(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        engine = Scheduler(store)
        result = engine.schedule("remind me to delete all photos at 18:00", now=NOW)
        assert result["success"] is False


class TestSchedulerEngine:

    def test_one_time_fires_only_when_reached(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        fired = []
        engine = SchedulerEngine(store=store, notify=lambda t: fired.append(t),
                                 now_fn=lambda: NOW)
        task = {"kind": "one_time", "run_at": "2026-09-06 10:00", "text": "water plants"}
        store.add(task)
        assert engine.fire(now=NOW + timedelta(hours=0, minutes=30)) == []
        due = engine.fire(now=NOW + timedelta(hours=1))
        assert len(due) == 1

    def test_daily_recurrence_injected_time(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        engine = SchedulerEngine(store=store, now_fn=lambda: NOW)
        store.add({"kind": "daily", "at_time": "09:00", "text": "stand up"})
        fired = engine.fire(now=NOW + timedelta(minutes=1))
        assert len(fired) == 1

    def test_destructive_not_auto_executed(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        fired = []
        engine = SchedulerEngine(store=store, notify=lambda t: fired.append(t),
                                 now_fn=lambda: NOW)
        store.add({"kind": "one_time", "run_at": "2026-09-06 09:00",
                   "text": "delete the report"})
        fired_list = engine.fire(now=NOW)
        assert len(fired_list) == 1
        assert fired_list[0].get("blocked_destructive") is True
        assert fired == []

    def test_fire_marks_run(self, tmp_path):
        store = TaskStore(path=tmp_path / "tasks.json")
        engine = SchedulerEngine(store=store, now_fn=lambda: NOW)
        task_id = store.add({"kind": "one_time", "run_at": "2026-09-06 09:00",
                             "text": "water plants"})
        engine.fire(now=NOW + timedelta(minutes=1))
        task = store.get(task_id)
        assert task["status"] == "run"