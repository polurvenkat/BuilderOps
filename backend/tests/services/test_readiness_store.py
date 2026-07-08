from datetime import datetime, timedelta, timezone

from app.db import Base, get_engine, get_sessionmaker
from app.models import ReadinessCheck, Repo
from app.services.readiness_store import upsert_readiness_check

T0 = datetime(2026, 7, 1, tzinfo=timezone.utc)
T1 = T0 + timedelta(days=5)


def _naive(dt):
    """Strip tzinfo from datetime for SQLite round-trip tolerance."""
    return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo is not None else dt


def make_session():
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = get_sessionmaker(engine)()
    repo = Repo(name="checkout-web", github_url="https://github.com/acme/checkout-web")
    session.add(repo)
    session.commit()
    return session, repo.id


def test_first_write_sets_status_changed_at_to_updated_at():
    session, repo_id = make_session()

    check = ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="fail",
        source="auto", detail=None, updated_at=T0,
    )
    upsert_readiness_check(session, check)
    session.commit()

    row = session.query(ReadinessCheck).filter_by(repo_id=repo_id, stage_key="codeowners_assigned").one()
    assert _naive(row.status_changed_at) == _naive(T0)


def test_status_unchanged_preserves_original_status_changed_at():
    session, repo_id = make_session()
    upsert_readiness_check(session, ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="fail",
        source="auto", detail=None, updated_at=T0,
    ))
    session.commit()

    # second sync, same status, later timestamp
    upsert_readiness_check(session, ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="fail",
        source="auto", detail=None, updated_at=T1,
    ))
    session.commit()

    row = session.query(ReadinessCheck).filter_by(repo_id=repo_id, stage_key="codeowners_assigned").one()
    assert _naive(row.updated_at) == _naive(T1)
    assert _naive(row.status_changed_at) == _naive(T0)  # unchanged, since status didn't change


def test_status_change_updates_status_changed_at():
    session, repo_id = make_session()
    upsert_readiness_check(session, ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="fail",
        source="auto", detail=None, updated_at=T0,
    ))
    session.commit()

    upsert_readiness_check(session, ReadinessCheck(
        repo_id=repo_id, stage_key="codeowners_assigned", status="pass",
        source="auto", detail=None, updated_at=T1,
    ))
    session.commit()

    row = session.query(ReadinessCheck).filter_by(repo_id=repo_id, stage_key="codeowners_assigned").one()
    assert row.status == "pass"
    assert _naive(row.status_changed_at) == _naive(T1)
