from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"

def test_ping():
    response = client.get("/ping")
    assert response.status_code == 200
    data = response.json()
    assert data.get("message") == "pong"
