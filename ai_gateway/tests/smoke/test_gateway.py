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
