from fastapi.testclient import TestClient

from research_agent.api import app


def test_health_and_homepage():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True
        assert client.get("/").status_code == 200


def test_missing_task_is_404():
    with TestClient(app) as client:
        response = client.get("/api/research/does-not-exist")
        assert response.status_code == 404

