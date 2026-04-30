from __future__ import annotations

from tender_backend.api.settings import _is_safe_test_url


def test_agent_connection_test_url_rejects_private_targets() -> None:
    assert _is_safe_test_url("http://localhost:8000") is False
    assert _is_safe_test_url("http://127.0.0.1:8000") is False
    assert _is_safe_test_url("http://10.0.0.5") is False
    assert _is_safe_test_url("http://169.254.169.254/latest/meta-data") is False


def test_agent_connection_test_url_allows_public_http_urls() -> None:
    assert _is_safe_test_url("https://api.deepseek.com/v1") is True
