from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from app.connectors.ado_connector import AdoRepoData
from app.db import Base, get_engine, get_sessionmaker
from app.models import AdoRepoSnapshot, Repo, ReadinessCheck, SyncRun
from app.services.sync_service import run_ado_sync, run_github_sync

NOW = datetime(2026, 7, 7, tzinfo=timezone.utc)


def _naive(dt):
    """Strip tzinfo from datetime for SQLite round-trip tolerance."""
    return dt.replace(tzinfo=None) if dt is not None and dt.tzinfo is not None else dt


@pytest.fixture
def session() -> Session:
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return get_sessionmaker(engine)()


def github_handler(request: httpx.Request) -> httpx.Response:
    body = request.content.decode()
    if "repositories(first:" in body:
        return httpx.Response(200, json={"data": {"organization": {"repositories": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [{"name": "checkout-web", "url": "https://github.com/acme-org/checkout-web"}],
        }}}})
    return httpx.Response(200, json={"data": {"r0": {
        "readme": {"id": "1"}, "codeowners": {"id": "2"},
        "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 1}]},
    }}})


@pytest.mark.asyncio
async def test_run_github_sync_creates_repo_and_readiness_checks(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        sync_run = await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert sync_run.status == "success"
    repo = session.query(Repo).filter_by(name="checkout-web").one()
    assert _naive(repo.last_synced_at) == _naive(NOW)
    checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    assert {c.stage_key for c in checks} == {
        "migrated_from_ado", "codeowners_assigned", "readme_present", "branch_protection", "naming_standardized",
    }


@pytest.mark.asyncio
async def test_run_github_sync_is_idempotent_on_rerun(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert session.query(Repo).count() == 1
    assert session.query(ReadinessCheck).count() == 5


@pytest.mark.asyncio
async def test_run_github_sync_records_failure_on_connector_error(session):
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(failing_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        sync_run = await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert sync_run.status == "failed"
    assert "500" in sync_run.error or "boom" in sync_run.error


@pytest.mark.asyncio
async def test_run_ado_sync_stores_snapshot():
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = get_sessionmaker(engine)()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": [{"name": "legacy-batch", "project": {"lastUpdateTime": "2026-05-01T00:00:00Z"}}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        sync_run = await run_ado_sync(session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW)

    assert sync_run.status == "success"
    snapshot = session.query(AdoRepoSnapshot).one()
    assert snapshot.name == "legacy-batch"


@pytest.mark.asyncio
async def test_run_github_sync_preserves_status_changed_at_across_unchanged_runs(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    later = NOW.replace(year=NOW.year + 1)  # clearly-later timestamp, same mocked (unchanged) data
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=later)

    repo = session.query(Repo).filter_by(name="checkout-web").one()
    check = session.query(ReadinessCheck).filter_by(repo_id=repo.id, stage_key="codeowners_assigned").one()
    assert _naive(check.updated_at) == _naive(later)          # touched every sync
    assert _naive(check.status_changed_at) == _naive(NOW)     # unchanged, since status didn't change
