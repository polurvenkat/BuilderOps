from datetime import datetime, timedelta, timezone

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


def test_list_repos_includes_derived_stage_info():
    app = create_app(make_test_settings())
    repo_id = seed_repo(app)  # seed_repo only sets codeowners_assigned=pass; everything else defaults missing/fail
    client = TestClient(app)

    body = client.get(f"/repos/{repo_id}").json()

    assert body["current_stage"] in ("onboarded", "standardized")
    assert isinstance(body["is_stuck"], bool)
    if body["is_stuck"]:
        assert body["stuck_reason"] is not None
        assert isinstance(body["dwell_days"], int)


def test_list_repos_filters_by_stage():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    onboarded_repo = Repo(name="stuck-in-migration", github_url="https://github.com/acme-org/stuck-in-migration")
    standardized_repo = Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web")
    session.add_all([onboarded_repo, standardized_repo])
    session.commit()
    now = datetime.now(timezone.utc)
    session.add(ReadinessCheck(
        repo_id=onboarded_repo.id, stage_key="migrated_from_ado", status="fail", source="auto",
        detail=None, updated_at=now,
    ))
    # Add passing checks to standardized_repo to move it past onboarded stage
    for key in ["migrated_from_ado", "codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"]:
        session.add(ReadinessCheck(
            repo_id=standardized_repo.id, stage_key=key, status="pass", source="auto",
            detail=None, updated_at=now,
        ))
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get("/repos", params={"stage": "onboarded"})

    names = {r["name"] for r in response.json()}
    assert names == {"stuck-in-migration"}


def test_list_repos_filters_by_domain():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    session.add_all([
        Repo(name="growth-repo", github_url="https://github.com/acme-org/growth-repo", domain="Growth"),
        Repo(name="platform-repo", github_url="https://github.com/acme-org/platform-repo", domain="Platform"),
    ])
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get("/repos", params={"domain": "Growth"})

    names = {r["name"] for r in response.json()}
    assert names == {"growth-repo"}


def test_list_repos_sorts_by_dwell_desc():
    app = create_app(make_test_settings())
    session = app.state.sessionmaker()
    short_stuck = Repo(name="short-stuck", github_url="https://github.com/acme-org/short-stuck")
    long_stuck = Repo(name="long-stuck", github_url="https://github.com/acme-org/long-stuck")
    not_stuck = Repo(name="all-clear", github_url="https://github.com/acme-org/all-clear")
    session.add_all([short_stuck, long_stuck, not_stuck])
    session.commit()
    now = datetime.now(timezone.utc)

    def add_all_standardized_checks(repo, extra_status="pass", extra_changed=now):
        for key in ["migrated_from_ado", "codeowners_assigned", "domain_assigned", "branch_protection", "readme_present"]:
            status = extra_status if key == "codeowners_assigned" else "pass"
            changed = extra_changed if key == "codeowners_assigned" else now
            session.add(ReadinessCheck(
                repo_id=repo.id, stage_key=key, status=status, source="auto",
                detail=None, updated_at=now, status_changed_at=changed,
            ))

    add_all_standardized_checks(short_stuck, "fail", now - timedelta(days=3))
    add_all_standardized_checks(long_stuck, "fail", now - timedelta(days=30))
    add_all_standardized_checks(not_stuck, "pass", now)
    session.commit()
    session.close()

    client = TestClient(app)
    response = client.get("/repos", params={"sort": "dwell_desc"})

    names_in_order = [r["name"] for r in response.json()]
    assert names_in_order.index("long-stuck") < names_in_order.index("short-stuck") < names_in_order.index("all-clear")
