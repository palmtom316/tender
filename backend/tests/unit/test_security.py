from __future__ import annotations

from tender_backend.core.config import Settings
from tender_backend.core.security import _load_token_map


def test_dev_token_fallback_is_disabled_outside_development(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_TOKENS", raising=False)

    tokens = _load_token_map(Settings(app_env="production"))

    assert "dev-token" not in tokens


def test_dev_token_fallback_remains_available_for_tests(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_TOKENS", raising=False)

    tokens = _load_token_map(Settings(app_env="test"))

    assert tokens["dev-token"].role == "admin"
