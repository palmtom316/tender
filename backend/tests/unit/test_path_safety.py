from __future__ import annotations

from pathlib import Path

import pytest

from tender_backend.core.path_safety import ensure_path_within_root, ensure_path_within_roots, parse_root_list


def test_ensure_path_within_root_allows_nested_path(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = root / "nested" / "file.txt"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")

    assert ensure_path_within_root(target, root, label="target") == target.resolve()


def test_ensure_path_within_root_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside.txt"
    root.mkdir()
    outside.write_text("bad", encoding="utf-8")

    with pytest.raises(ValueError, match="target must be within"):
        ensure_path_within_root(root / ".." / "outside.txt", root, label="target")


def test_ensure_path_within_roots_accepts_any_allowed_root(tmp_path: Path) -> None:
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    target = root_b / "file.txt"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")

    assert ensure_path_within_roots(target, [root_a, root_b], label="target") == target.resolve()


def test_parse_root_list_ignores_empty_parts(tmp_path: Path) -> None:
    raw = f"{tmp_path / 'a'}:{tmp_path / 'b'}:"

    assert parse_root_list(raw) == [(tmp_path / "a").resolve(), (tmp_path / "b").resolve()]
