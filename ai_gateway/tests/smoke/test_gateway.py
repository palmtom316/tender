from fastapi.testclient import TestClient

from tender_ai_gateway.main import app


def test_gateway_health() -> None:
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["service"] == "Tender AI Gateway"


def test_create_credential_contract() -> None:
    client = TestClient(app)
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
    client = TestClient(app)

    monkeypatch.setattr(
        "tender_ai_gateway.api.chat.call_with_fallback",
        lambda **kwargs: type("Result", (), {
            "content": '[{"clause_no":"1","clause_text":"测试条文"}]',
            "model": "deepseek-chat",
            "provider": "override-primary",
            "input_tokens": 12,
            "output_tokens": 34,
            "estimated_cost": 0.01,
            "latency_ms": 123,
            "used_fallback": False,
        })(),
    )

    response = client.post(
        "/api/ai/chat",
        json={
            "task_type": "tag_clauses",
            "messages": [{"role": "user", "content": "test"}],
            "primary_override": {
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "override-key",
                "model": "deepseek-chat",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content"] == '[{"clause_no":"1","clause_text":"测试条文"}]'
    assert payload["resolved_provider"] == "override-primary"
