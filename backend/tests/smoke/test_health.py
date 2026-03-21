from tender_backend.main import app
from tender_backend.test_support.asgi_client import SyncASGIClient


def test_health() -> None:
    client = SyncASGIClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "Tender Backend"
