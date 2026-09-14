"""MemoryDatabase offline contract tests (sqlite, no network)."""

from memory.database import MemoryDatabase


class TestMemoryDatabase:

    def test_initialize_and_add(self, tmp_path):
        db = MemoryDatabase(db_path=str(tmp_path / "test.db"))
        mid = db.add("Boss likes red", category="preference", importance=7)
        assert mid > 0

    def test_get_all_returns_stored(self, tmp_path):
        db = MemoryDatabase(db_path=str(tmp_path / "test.db"))
        db.add("favorite game is ghost of tsushima", category="preference", value="ghost of tsushima")
        db.add("plan to move to germany", category="goal", value="germany", memory_type="plan")
        all_rows = db.get_all()
        assert len(all_rows) == 2
        assert any(row[1] == "favorite game is ghost of tsushima" for row in all_rows)

    def test_update_existing(self, tmp_path):
        db = MemoryDatabase(db_path=str(tmp_path / "test.db"))
        mid = db.add("old content", value="v1")
        assert db.update(mid, "new content", "preference", 8, "fact", "v2") is True
        rows = db.get_all()
        assert rows[0][1] == "new content"

    def test_delete(self, tmp_path):
        db = MemoryDatabase(db_path=str(tmp_path / "test.db"))
        mid = db.add("to delete", value="x")
        db.delete(mid)
        assert db.get_all() == []

    def test_isolated_db_files(self, tmp_path):
        db_a = MemoryDatabase(db_path=str(tmp_path / "a.db"))
        db_b = MemoryDatabase(db_path=str(tmp_path / "b.db"))
        db_a.add("only in a")
        assert len(db_b.get_all()) == 0