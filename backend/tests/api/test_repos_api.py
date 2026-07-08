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
    assert body[0]["stages"]["codeowners_assigned"]["status"] == "pass"
    assert body[0]["stages"]["codeowners_assigned"]["source"] == "auto"


def test_domain_assigned_reflects_repo_domain():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    repo = Repo(name="no-domain-repo", github_url="https://github.com/acme-org/no-domain-repo", domain=None)
    session.add(repo)
    session.commit()
    repo_id = repo.id
    session.close()
    client = TestClient(app)

    # PATCH to materialize the domain_assigned check
    client.patch(f"/repos/{repo_id}", json={"domain": "Growth"})
    response = client.get(f"/repos/{repo_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["stages"]["domain_assigned"]["status"] == "pass"
    assert body["stages"]["domain_assigned"]["source"] == "manual"


def test_domain_assigned_fails_when_domain_missing():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    repo = Repo(name="no-domain-repo", github_url="https://github.com/acme-org/no-domain-repo", domain=None)
    session.add(repo)
    session.commit()
    repo_id = repo.id
    session.close()
    client = TestClient(app)

    # PATCH to materialize the domain_assigned check with empty domain
    client.patch(f"/repos/{repo_id}", json={"domain": ""})
    response = client.get(f"/repos/{repo_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["stages"]["domain_assigned"]["status"] == "fail"
    assert body["stages"]["domain_assigned"]["source"] == "manual"


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


def test_patch_repo_rejects_invalid_migration_wave():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"migration_wave": "bogus"})

    assert response.status_code == 422


def test_post_onboarding_log_creates_entry():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.post(f"/repos/{repo_id}/onboarding-log", json={"engineer_name": "Sam", "hours": 6.5})

    assert response.status_code == 201
    body = response.json()
    assert body["engineer_name"] == "Sam"
    assert body["hours"] == 6.5


def test_patch_repo_updates_team():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    response = client.patch(f"/repos/{repo_id}", json={"team": "Growth"})

    assert response.status_code == 200
    assert response.json()["team"] == "Growth"


def test_repo_out_exposes_github_url_and_last_synced_at():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    body = client.get(f"/repos/{repo_id}").json()

    assert body["github_url"] == "https://github.com/acme-org/checkout-web"
    assert "last_synced_at" in body


def test_patch_repo_domain_materializes_a_real_domain_assigned_check():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)
    client = TestClient(app)

    client.patch(f"/repos/{repo_id}", json={"domain": "Checkout"})
    body = client.get(f"/repos/{repo_id}").json()

    assert body["stages"]["domain_assigned"]["status"] == "pass"
    assert body["stages"]["domain_assigned"]["source"] == "manual"
    assert body["stages"]["domain_assigned"]["updated_at"] is not None
