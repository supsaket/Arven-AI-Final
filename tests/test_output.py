"""Output management contract (row 34) — no overwrite, sidecars, cleanup."""

import json
import os

from core.output import OutputManager, output_manager


class TestSafeFilename:

    def test_sanitizes(self):
        filename = output_manager.safe_filename("My <Report>: plan!")
        assert "<" not in filename
        assert ":" not in filename
        assert "/" not in filename

    def test_empty_falls_back(self):
        assert output_manager.safe_filename("") == "unnamed"

    def test_invalid_chars_removed(self):
        cleaned = output_manager.safe_filename('a"b|c?d*e:<>/\\')
        assert not any(ch in cleaned for ch in '":|?*<>/\\')


class TestNoOverwrite:

    def test_next_rw_path_increments(self, tmp_path):
        manager = OutputManager(root=tmp_path)
        first = manager.next_rw_path(tmp_path, "notes")
        first.write_text("a", encoding="utf-8")
        second = manager.next_rw_path(tmp_path, "notes")
        assert first != second
        assert second.name.startswith("notes_")

    def test_overwrite_flag_allowed(self, tmp_path):
        manager = OutputManager(root=tmp_path)
        target = manager.next_rw_path(tmp_path, "notes", overwrite=True)
        target.write_text("x", encoding="utf-8")
        again = manager.next_rw_path(tmp_path, "notes", overwrite=True)
        assert target == again

    def test_unique_filenames(self, tmp_path):
        manager = OutputManager(root=tmp_path)
        names = manager.unique_filenames(tmp_path, "app", count=2)
        assert len(set(names)) == 2


class TestSidecar:

    def test_metadata_sidecar_written(self, tmp_path):
        manager = OutputManager(root=tmp_path)
        target = tmp_path / "note.txt"
        target.write_text("hello", encoding="utf-8")
        sidecar = manager.metadata_sidecar(target, {"kind": "test"})
        assert os.path.exists(sidecar)
        data = json.load(open(sidecar, encoding="utf-8"))
        assert data["filename"] == "note.txt"

    def test_write_returns_paths(self, tmp_path):
        manager = OutputManager(root=tmp_path / "Output")
        outcome = manager.write("output", "hello.txt", "content")
        assert os.path.exists(outcome["path"])
        assert os.path.exists(outcome["sidecar"])


class TestCleanup:

    def test_cleanup_only_old_files(self, tmp_path):
        manager = OutputManager(root=tmp_path)
        directory = tmp_path / "files"
        directory.mkdir(exist_ok=True)
        keep = directory / "keep.txt"
        keep.write_text("keep", encoding="utf-8")
        remove = directory / "old.txt"
        remove.write_text("old", encoding="utf-8")
        os.utime(remove, (0, 0))
        removed = manager.cleanup(directory, max_age_seconds=3600,
                                  criteria=lambda p: p.name.endswith(".txt"))
        assert str(remove) in removed
        assert keep.exists()

    def test_cleanup_empty_dir_ok(self, tmp_path):
        manager = OutputManager(root=tmp_path)
        directory = tmp_path / "empty"
        directory.mkdir(exist_ok=True)
        assert manager.cleanup(directory) == []


class TestStructuredRecords:

    def test_structured_records_are_files(self, tmp_path):
        manager = OutputManager(root=tmp_path)
        records = manager.structured_records()
        assert isinstance(records, list)
        for record in records:
            assert isinstance(record["size"], int)
            assert record["name"]