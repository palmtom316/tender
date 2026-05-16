import pytest

from tender_ai_gateway.core.config import get_settings
from tender_ai_gateway.main import app
from tender_ai_gateway.test_support.asgi_client import SyncASGIClient


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AI_GATEWAY_SHARED_SECRET", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _fake_chat_result(
    *,
    content: str = "[]",
    provider: str = "stub",
):
    return type("Result", (), {
        "content": content,
        "model": "deepseek-v4-flash",
        "provider": provider,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": 0.0,
        "latency_ms": 0,
        "used_fallback": False,
        "finish_reason": None,
        "prompt_cache_hit_tokens": 0,
        "prompt_cache_miss_tokens": 0,
        "reasoning_tokens": 0,
    })()


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_gateway_health() -> None:
    client = SyncASGIClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["service"] == "Tender AI Gateway"


def test_create_credential_contract() -> None:
    client = SyncASGIClient(app)
    response = client.post(
        "/api/credentials",
        json={
            "provider": "deepseek",
            "display_name": "debug-key",
            "api_key": "test-api-key",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deepseek"
    assert payload["mode"] == "server-proxy-byok"


def test_chat_uses_override_even_without_env_keys(monkeypatch) -> None:
    _clear_settings_cache()
    client = SyncASGIClient(app)

    monkeypatch.setattr(
        "tender_ai_gateway.api.chat.call_with_fallback",
        lambda **kwargs: _fake_chat_result(
            content='[{"clause_no":"1","clause_text":"测试条文"}]',
            provider="override-primary",
        ),
    )

    response = client.post(
        "/api/ai/chat",
        json={
            "task_type": "tag_clauses",
            "messages": [{"role": "user", "content": "test"}],
            "primary_override": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "override-key",
                "model": "deepseek-v4-flash",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == '[{"clause_no":"1","clause_text":"测试条文"}]'
    assert payload["resolved_provider"] == "override-primary"


def test_chat_requires_shared_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("AI_GATEWAY_SHARED_SECRET", "gateway-secret")
    _clear_settings_cache()
    client = SyncASGIClient(app)

    response = client.post(
        "/api/ai/chat",
        json={"task_type": "tag_clauses", "messages": [{"role": "user", "content": "test"}]},
    )

    assert response.status_code == 401


def test_chat_accepts_configured_shared_secret(monkeypatch) -> None:
    monkeypatch.setenv("AI_GATEWAY_SHARED_SECRET", "gateway-secret")
    _clear_settings_cache()
    client = SyncASGIClient(app)
    monkeypatch.setattr(
        "tender_ai_gateway.api.chat.call_with_fallback",
        lambda **kwargs: _fake_chat_result(),
    )

    response = client.post(
        "/api/ai/chat",
        headers={"Authorization": "Bearer gateway-secret"},
        json={
            "task_type": "tag_clauses",
            "messages": [{"role": "user", "content": "test"}],
            "primary_override": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "override-key",
                "model": "deepseek-v4-flash",
            },
        },
    )

    assert response.status_code == 200


def test_chat_rejects_disallowed_provider_override_host(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AI_GATEWAY_SHARED_SECRET", "gateway-secret")
    monkeypatch.setenv("PROVIDER_OVERRIDE_ALLOWED_HOSTS", "api.deepseek.com")
    _clear_settings_cache()
    client = SyncASGIClient(app)

    response = client.post(
        "/api/ai/chat",
        headers={"Authorization": "Bearer gateway-secret"},
        json={
            "task_type": "tag_clauses",
            "messages": [{"role": "user", "content": "test"}],
            "primary_override": {
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "override-key",
                "model": "deepseek-v4-flash",
            },
        },
    )

    assert response.status_code == 400
