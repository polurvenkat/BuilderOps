from datetime import datetime, timezone
import threading

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


def test_sqlite_in_memory_thread_safety():
    """
    Regression test: Verify that SQLite in-memory databases work across threads.

    FastAPI runs sync path-operation functions and dependencies in a worker thread pool,
    which is different from the thread that calls Base.metadata.create_all(engine) during
    app startup. Without StaticPool + check_same_thread=False, each thread would get its
    own separate empty in-memory database, causing "no such table" errors in worker threads.

    This test proves that tables created on the main thread are accessible from worker threads.
    """
    # Create engine and tables on main thread
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessionmaker_factory = get_sessionmaker(engine)

    # Add a repo on main thread
    main_session = sessionmaker_factory()
    repo = Repo(name="test-repo", github_url="https://github.com/test/repo")
    main_session.add(repo)
    main_session.commit()
    main_session.close()

    # Track any exceptions from the worker thread
    exceptions = []

    def worker_thread_task():
        """Run in a separate thread to simulate FastAPI worker thread behavior."""
        try:
            # Open a fresh session in the worker thread
            worker_session = sessionmaker_factory()

            # Should be able to query Repo table without "no such table" error
            count = worker_session.query(Repo).count()
            assert count == 1, f"Expected 1 repo, got {count}"

            # Verify we can fetch the repo that was created on main thread
            fetched = worker_session.query(Repo).filter_by(name="test-repo").one()
            assert fetched.github_url == "https://github.com/test/repo"

            worker_session.close()
        except Exception as e:
            exceptions.append(e)

    # Run the worker thread task
    thread = threading.Thread(target=worker_thread_task)
    thread.start()
    thread.join()

    # Assert no exceptions occurred in the worker thread
    assert len(exceptions) == 0, f"Worker thread raised exception(s): {exceptions}"
