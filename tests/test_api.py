from fastapi.testclient import TestClient

from vacancy_radar.api import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_not_yet_implemented() -> None:
    response = client.post("/analyze", params={"jd_text": "placeholder"})
    assert response.status_code == 501
