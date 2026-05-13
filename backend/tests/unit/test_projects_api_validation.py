from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from tender_backend.api.projects import ProjectCreate, _assert_category_enabled


def test_project_create_requires_category_code() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="demo")


def test_project_create_rejects_blank_category_code() -> None:
    with pytest.raises(ValidationError):
        ProjectCreate(name="demo", category_code="")


def test_project_create_accepts_valid_payload() -> None:
    payload = ProjectCreate(name="demo", category_code="sgcc_distribution")
    assert payload.category_code == "sgcc_distribution"


class _FakeCursor:
    def __init__(self, result):
        self._result = result

    def execute(self, *_args, **_kwargs):
        return self

    def fetchone(self):
        return self._result


class _FakeConn:
    def __init__(self, result):
        self._result = result

    @contextmanager
    def cursor(self, **_kwargs):
        yield _FakeCursor(self._result)


def test_assert_category_enabled_passes_when_row_found() -> None:
    conn = _FakeConn(result={"?column?": 1})
    _assert_category_enabled(conn, category_code="sgcc_distribution")


def test_assert_category_enabled_raises_when_missing() -> None:
    conn = _FakeConn(result=None)
    with pytest.raises(HTTPException) as exc_info:
        _assert_category_enabled(conn, category_code="bogus_code")
    assert exc_info.value.status_code == 400
    assert "bogus_code" in exc_info.value.detail
