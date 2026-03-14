from fastapi.testclient import TestClient

from tender_backend.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "Tender Backend"
