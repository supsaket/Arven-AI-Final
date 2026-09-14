"""Day 2 focused tests: Report Builder (72), Collaboration (73),
Escalation & Human Handoff (75). Uses temp KV paths and temp output dirs;
no real network."""

import os

import pytest

from core.collaboration import CollabBoard
from core.escalation import EscalationManager
from core.kv import KeyValueStore
from core.reports import ReportBuilder


@pytest.fixture
def kv(tmp_path):
    return KeyValueStore(str(tmp_path / "kv.json"))


# ----------------------------------------------------------------------
# 72 Report Builder
# ----------------------------------------------------------------------

class TestReportBuilder:

    def test_template_structure(self, kv, tmp_path):
        builder = ReportBuilder(kv=kv, output_dir=str(tmp_path / "out"))
        template = builder.from_template("summary")
        assert template["title"] == "Executive Summary"
        assert "Overview" in template["sections"]
        assert builder.from_template("status")["sections"] == [
            "Current Status", "Blockers", "Completed"
        ]
        with pytest.raises(ValueError):
            builder.from_template("nope")

    def test_markdown_shape(self, kv):
        builder = ReportBuilder(kv=kv)
        builder.add_section("Overview", "ARVEN is alive", name="summary")
        builder.add_table("Metrics", ["tool", "count"],
                          [["files", 3], ["runs", 1]], name="summary")
        md = builder.render("summary")
        assert md.startswith("# Executive Summary")
        assert "## Overview" in md
        assert "ARVEN is alive" in md
        assert "| tool | count |" in md
        assert "| --- | --- |" in md
        assert "| files | 3 |" in md
        assert "Prepared" in md

    def test_export_file_exists(self, kv, tmp_path):
        out = tmp_path / "out"
        builder = ReportBuilder(kv=kv, output_dir=str(out))
        builder.add_section("Overview", "hello", name="weekly")
        path = builder.export("weekly")
        assert os.path.exists(path)
        assert path.endswith(".md")
        assert "# Weekly Report" in open(path, encoding="utf-8").read()


# ----------------------------------------------------------------------
# 73 Collaboration / Team board
# ----------------------------------------------------------------------

class TestCollabBoard:

    def test_board_lifecycle(self, kv):
        board = CollabBoard(kv=kv)
        board_id = board.create_board("Sprint", ["To Do", "Done"])
        assert board_id
        board.create_column(board_id, "Review", wip_limit=3)
        assert len(board.get_board(board_id)["columns"]) == 3

        card_id = board.add_card(board_id, "Ship feature", priority="high",
                                 assignee="alice", due="2026-09-10")
        assert card_id
        with pytest.raises(ValueError):
            board.add_card(board_id, "bad", priority="urgentest")

        board.move_card(card_id, "Done", by="alice")
        card = board.get_board(board_id)["columns"][1]["cards"][0]
        assert card["id"] == card_id
        assert card["column"] == board.get_board(board_id)["columns"][1]["id"]
        assert len(card["transitions"]) >= 2

    def test_mentions(self):
        board = CollabBoard()
        assert board.mentions("ping @alice and @bob.dev") == \
            ["alice", "bob.dev"]
        assert board.mentions("no one here") == []

    def test_board_summary_wip(self, kv):
        board = CollabBoard(kv=kv)
        board_id = board.create_board("Ops", ["Backlog", "Doing", "Done"])
        board.add_card(board_id, "one", priority="low", column="Doing")
        board.add_card(board_id, "two", priority="medium", column="Doing")
        board.add_card(board_id, "three", priority="high", column="Done")
        summary = board.board_summary(board_id)
        counts = {c["title"]: c["count"] for c in summary["columns"]}
        assert counts == {"Backlog": 0, "Doing": 2, "Done": 1}
        assert board.wip(board_id) == 3
        assert board.activity()

    def test_persisted_restore(self, tmp_path):
        path = str(tmp_path / "kv.json")
        kv_1 = KeyValueStore(path)
        board_1 = CollabBoard(kv=kv_1)
        board_id = board_1.create_board("Restored")
        card_id = board_1.add_card(board_id, "persist me", priority="low")
        board_2 = CollabBoard(kv=KeyValueStore(path))
        restored = board_2.get_board(board_id)
        assert restored is not None
        assert any(c["id"] == card_id
                   for c in restored["columns"][0]["cards"])


# ----------------------------------------------------------------------
# 75 Escalation & Human Handoff
# ----------------------------------------------------------------------

class TestEscalation:

    def test_lifecycle(self, kv, tmp_path):
        manager = EscalationManager(kv=kv)
        esc = manager.escalate("user blocked at checkout", to="saket",
                               priority="high", reason="payment API error")
        assert esc["status"] == "open"
        assert esc["ticket"].startswith("ARV-ESC-")
        assert esc["priority"] == "high"

        resolved = manager.resolve(esc["id"], resolution="handled manually",
                                   by="saket")
        assert resolved["status"] == "resolved"
        assert resolved["resolved_at"]
        # archive: record still present, not deleted
        assert manager.get(esc["id"])["status"] == "resolved"

    def test_stale_remind(self, kv):
        from datetime import datetime, timedelta
        base = datetime(2026, 9, 6, 9, 0, 0)
        manager = EscalationManager(kv=kv, now_fn=lambda: base)
        old = manager.escalate("stale item", to="saket", reason="old",
                               deadline_minutes=5)
        manager = EscalationManager(kv=kv,
                                    now_fn=lambda: base + timedelta(minutes=30))
        stale = manager.auto_remind()
        assert any(s["id"] == old["id"] for s in stale)
        assert manager.get(old["id"])["stale"] is True
        assert manager.get(old["id"])["status"] == "escalated"

    def test_handoff_content(self, kv, tmp_path):
        manager = EscalationManager(kv=kv)
        esc = manager.escalate(
            "deploy failed", to="ops", priority="urgent", reason="missing cert",
            context="prod deploy halted",
            attempted_actions=["rotated secrets", "restarted worker"],
            assets=["deploy.yaml", "logs/deploy.log"],
            next_steps=["verify cert chain", "re-run pipeline"],
        )
        out = manager.handoff_summary(esc["id"], directory=str(tmp_path / "esc"))
        assert "Human Handoff" in out["content"]
        assert "deploy failed" in out["content"]
        assert "rotated secrets" in out["content"]
        assert "deploy.yaml" in out["content"]
        assert "verify cert chain" in out["content"]
        assert os.path.exists(out["path"])

    def test_channel_honest_not_configured(self, kv):
        manager = EscalationManager(kv=kv)
        esc = manager.escalate("need email", to="saket", reason="n/a")
        result = manager.notify_channel(esc["id"], "email")
        assert result["status"] == "NOT_CONFIGURED"