from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import SyncRun


def make_test_settings():
    return Settings(
        database_url="sqlite:///:memory:",
        github_token="gh-token",
        github_org="acme-org",
        ado_org="acme-ado",
        ado_project="acme-project",
        ado_pat="ado-pat",
    )


def test_sync_status_returns_null_when_nothing_has_run():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/sync/status")

    assert response.status_code == 200
    assert response.json() == {"github": None, "ado": None}


def test_sync_status_returns_latest_run_per_connector():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    session.add(SyncRun(connector="github", started_at=datetime.now(timezone.utc), status="success"))
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get("/sync/status")

    assert response.status_code == 200
    body = response.json()
    assert body["github"]["status"] == "success"
    assert body["ado"] is None


def test_post_sync_github_triggers_a_run(monkeypatch):
    app = create_app(make_test_settings())

    async def fake_run_github_sync(session, client, org, token, now):
        return SyncRun(id=1, connector="github", started_at=now, status="success", finished_at=now)

    monkeypatch.setattr("app.api.sync.run_github_sync", fake_run_github_sync)

    client = TestClient(app)
    response = client.post("/sync/github")

    assert response.status_code == 202
    assert response.json()["status"] == "success"
