from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Repo, ReadinessCheck


def make_test_settings():
    return Settings(
        database_url="sqlite:///:memory:",
        github_token="gh-token",
        github_org="acme-org",
        ado_org="acme-ado",
        ado_project="acme-project",
        ado_pat="ado-pat",
    )


def seed_repo(app):
    session = app.state.sessionmaker()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web", domain="Growth")
    session.add(repo)
    session.commit()
    session.add(ReadinessCheck(
        repo_id=repo.id, stage_key="codeowners_assigned", status="pass", source="auto",
        detail=None, updated_at=datetime.now(timezone.utc),
    ))
    session.commit()
    session.close()
    return repo.id


def test_list_repos_returns_stage_map():
    app = create_app(make_test_settings())
    seed_repo(app)
    client = TestClient(app)

    response = client.get("/repos")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "checkout-web"
    assert body[0]["stages"]["codeowners_assigned"] == "pass"


def test_get_single_repo_404_when_missing():
    app = create_app(make_test_settings())
    client = TestClient(app)

    response = client.get("/repos/999")

    assert response.status_code == 404


def test_patch_repo_updates_manual_fields_only():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"domain": "Checkout", "migration_wave": "pilot"})

    assert response.status_code == 200
    body = response.json()
    assert body["domain"] == "Checkout"
    assert body["migration_wave"] == "pilot"


def test_post_onboarding_log_creates_entry():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.post(f"/repos/{repo_id}/onboarding-log", json={"engineer_name": "Sam", "hours": 6.5})

    assert response.status_code == 201
    body = response.json()
    assert body["engineer_name"] == "Sam"
    assert body["hours"] == 6.5
