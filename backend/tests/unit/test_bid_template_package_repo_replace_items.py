from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from tender_backend.db.repositories.bid_template_package_repo import (
    BidTemplateItemCreate,
    BidTemplateItemRow,
    BidTemplatePackageRepository,
)


class _RecordingCursor:
    def __init__(self, response_rows: list[dict]) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self._responses = list(response_rows)

    def execute(self, sql: str, params: tuple | None = None) -> "_RecordingCursor":
        self.executed.append((sql, params))
        return self

    def fetchone(self) -> dict | None:
        return self._responses.pop(0) if self._responses else None

    def fetchall(self) -> list[dict]:
        return []

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_: object) -> bool:
        return False


class _FakeConn:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self._cursor = cursor

    def cursor(self, **_: object) -> _RecordingCursor:
        return self._cursor


def _existing_row(*, item_id: UUID, package_id: UUID, relative_path: str, item_name: str = "商务偏差表") -> BidTemplateItemRow:
    return BidTemplateItemRow(
        id=item_id,
        package_id=package_id,
        item_code="1",
        item_name=item_name,
        filename=relative_path,
        relative_path=relative_path,
        source_kind="docx",
        item_type="table",
        render_mode="templated",
        is_required=True,
        sort_order=0,
        created_at=datetime(2026, 4, 29, 0, 0, 0),
    )


def _incoming_item(*, relative_path: str, item_name: str) -> BidTemplateItemCreate:
    return BidTemplateItemCreate(
        item_code="1",
        item_name=item_name,
        filename=relative_path,
        relative_path=relative_path,
        source_kind="docx",
        item_type="table",
        render_mode="templated",
        is_required=True,
        sort_order=0,
    )


def _row_payload(*, item_id: UUID, package_id: UUID, relative_path: str, item_name: str) -> dict:
    return {
        "id": item_id,
        "package_id": package_id,
        "item_code": "1",
        "item_name": item_name,
        "filename": relative_path,
        "relative_path": relative_path,
        "source_kind": "docx",
        "item_type": "table",
        "render_mode": "templated",
        "is_required": True,
        "sort_order": 0,
        "created_at": datetime(2026, 4, 29, 0, 0, 0),
    }


def _classify(executed: list[tuple[str, tuple]]) -> dict[str, list[tuple[str, tuple]]]:
    buckets: dict[str, list[tuple[str, tuple]]] = {"INSERT": [], "UPDATE": [], "DELETE": []}
    for sql, params in executed:
        head = sql.strip().split()[0].upper()
        if head in buckets:
            buckets[head].append((sql, params))
    return buckets


def test_replace_items_preserves_id_when_relative_path_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    package_id = uuid4()
    existing_id = uuid4()
    relative_path = "1.商务偏差表.docx"

    repo = BidTemplatePackageRepository()
    monkeypatch.setattr(
        repo,
        "list_items",
        lambda conn, *, package_id: [_existing_row(item_id=existing_id, package_id=package_id, relative_path=relative_path)],
    )

    incoming = [_incoming_item(relative_path=relative_path, item_name="商务偏差表 V2")]
    cursor = _RecordingCursor([
        _row_payload(item_id=existing_id, package_id=package_id, relative_path=relative_path, item_name="商务偏差表 V2"),
    ])

    rows = repo.replace_items(_FakeConn(cursor), package_id=package_id, items=incoming)

    buckets = _classify(cursor.executed)
    assert not buckets["DELETE"], "re-import must not delete rows whose relative_path is unchanged"
    assert not buckets["INSERT"], "matching relative_path must reuse the existing row, not insert"
    assert len(buckets["UPDATE"]) == 1

    _, update_params = buckets["UPDATE"][0]
    assert update_params[-1] == existing_id, "UPDATE must target the existing template_item_id (preserves bindings)"

    assert len(rows) == 1
    assert rows[0].id == existing_id


def test_replace_items_inserts_new_paths_and_deletes_missing_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    package_id = uuid4()
    kept_id = uuid4()
    removed_id = uuid4()
    new_id_placeholder = uuid4()

    kept_path = "1.商务偏差表.docx"
    removed_path = "2.声明.docx"
    new_path = "3.授权委托书.docx"

    repo = BidTemplatePackageRepository()
    monkeypatch.setattr(
        repo,
        "list_items",
        lambda conn, *, package_id: [
            _existing_row(item_id=kept_id, package_id=package_id, relative_path=kept_path, item_name="商务偏差表"),
            _existing_row(item_id=removed_id, package_id=package_id, relative_path=removed_path, item_name="声明"),
        ],
    )

    incoming = [
        _incoming_item(relative_path=kept_path, item_name="商务偏差表"),
        _incoming_item(relative_path=new_path, item_name="授权委托书"),
    ]
    cursor = _RecordingCursor([
        # First DELETE has no fetchone consumer; UPDATE for kept then INSERT for new.
        _row_payload(item_id=kept_id, package_id=package_id, relative_path=kept_path, item_name="商务偏差表"),
        _row_payload(item_id=new_id_placeholder, package_id=package_id, relative_path=new_path, item_name="授权委托书"),
    ])

    rows = repo.replace_items(_FakeConn(cursor), package_id=package_id, items=incoming)

    buckets = _classify(cursor.executed)
    assert len(buckets["DELETE"]) == 1, "rows whose relative_path is no longer present must be deleted"
    delete_sql, delete_params = buckets["DELETE"][0]
    assert "ANY(%s)" in delete_sql
    assert delete_params[0] == package_id
    assert delete_params[1] == [removed_path]

    assert len(buckets["UPDATE"]) == 1, "kept relative_path must reuse the existing row via UPDATE"
    _, update_params = buckets["UPDATE"][0]
    assert update_params[-1] == kept_id

    assert len(buckets["INSERT"]) == 1, "new relative_path must be inserted exactly once"

    assert {row.id for row in rows} == {kept_id, new_id_placeholder}


def test_replace_items_makes_no_writes_when_existing_and_incoming_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    package_id = uuid4()
    repo = BidTemplatePackageRepository()
    monkeypatch.setattr(repo, "list_items", lambda conn, *, package_id: [])

    cursor = _RecordingCursor([])

    rows = repo.replace_items(_FakeConn(cursor), package_id=package_id, items=[])

    assert rows == []
    assert _classify(cursor.executed) == {"INSERT": [], "UPDATE": [], "DELETE": []}
