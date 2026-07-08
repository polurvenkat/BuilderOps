from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_test_settings():
    return Settings(
        database_url="sqlite:///:memory:",
        github_token="gh-token",
        github_org="acme-org",
        ado_org="acme-ado",
        ado_project="acme-project",
        ado_pat="ado-pat",
    )


def test_health_endpoint_returns_ok():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
