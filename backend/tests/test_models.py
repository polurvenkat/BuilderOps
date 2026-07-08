from datetime import datetime, timezone

from app.db import Base, get_engine, get_sessionmaker
from app.models import AdoRepoSnapshot, OnboardingLog, Repo, ReadinessCheck, SyncRun


def make_session():
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return get_sessionmaker(engine)()


def test_create_and_query_repo():
    session = make_session()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()

    fetched = session.query(Repo).filter_by(name="checkout-web").one()
    assert fetched.github_url == "https://github.com/acme/checkout-web"
    assert fetched.migration_wave == "not_started"
    assert fetched.domain is None


def test_readiness_check_composite_key_and_upsert_via_merge():
    session = make_session()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()

    check = ReadinessCheck(
        repo_id=repo.id,
        stage_key="codeowners_assigned",
        status="pass",
        source="auto",
        detail={"reviewers": 3},
        updated_at=datetime.now(timezone.utc),
    )
    session.add(check)
    session.commit()

    # upsert via merge: same composite key, new status
    updated = ReadinessCheck(
        repo_id=repo.id,
        stage_key="codeowners_assigned",
        status="fail",
        source="auto",
        detail=None,
        updated_at=datetime.now(timezone.utc),
    )
    session.merge(updated)
    session.commit()

    rows = session.query(ReadinessCheck).filter_by(repo_id=repo.id, stage_key="codeowners_assigned").all()
    assert len(rows) == 1
    assert rows[0].status == "fail"


def test_ado_snapshot_onboarding_log_and_sync_run():
    session = make_session()
    session.add(AdoRepoSnapshot(name="legacy-batch", last_activity=None, synced_at=datetime.now(timezone.utc)))
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()

    session.add(OnboardingLog(repo_id=repo.id, engineer_name="Sam", hours=6.5, logged_at=datetime.now(timezone.utc)))
    session.add(SyncRun(connector="github", started_at=datetime.now(timezone.utc), status="running"))
    session.commit()

    assert session.query(AdoRepoSnapshot).count() == 1
    assert session.query(OnboardingLog).count() == 1
    assert session.query(SyncRun).filter_by(connector="github").one().status == "running"
