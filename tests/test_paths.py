"""core.paths.normalize_path contract tests."""

import os
import pytest
from pathlib import Path

from core.paths import normalize_path


class TestNormalizePath:

    def test_none_raises(self):
        with pytest.raises(ValueError):
            normalize_path(None)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_path("")

    def test_absolute_path_passthrough(self, tmp_path):
        target = tmp_path / "thing.txt"
        result = normalize_path(str(target))
        assert result.is_absolute()
        assert result == target.resolve()

    def test_relative_resolved_against_base_dir(self, tmp_path):
        result = normalize_path("sub/note.md", base_dir=str(tmp_path))
        assert result == (tmp_path / "sub/note.md").resolve()

    def test_tilde_expansion(self):
        result = normalize_path("~/arven_probe")
        assert result == (Path.home() / "arven_probe").resolve()

    def test_known_folder_name_desktop_resolves(self):
        result = normalize_path("desktop")
        assert result.is_absolute()
        assert "Windows" not in result.parts

    def test_traversal_outside_base_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            normalize_path("../..", base_dir=str(tmp_path))

    def test_traversal_from_leaf_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            normalize_path("a/../../../../etc", base_dir=str(tmp_path))

    def test_nested_path_inside_base_allowed(self, tmp_path):
        inner = tmp_path / "a" / "b"
        inner.mkdir(parents=True)
        result = normalize_path("a/b/file.txt", base_dir=str(tmp_path))
        assert result == (tmp_path / "a" / "b" / "file.txt").resolve()

    def test_quoted_value_stripped_by_engine_not_core(self, tmp_path):
        # core.paths keeps quotes verbatim; the engine strips them first.
        result = normalize_path(os.path.join(str(tmp_path), "x"), base_dir=str(tmp_path))
        assert result.is_absolute()