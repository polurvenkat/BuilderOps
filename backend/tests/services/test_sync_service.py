from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy.orm import Session

from app.connectors.ado_connector import AdoRepoData
from app.connectors.ado_pipelines_connector import fetch_pipeline_links  # noqa: F401 - imported for readability of intent
from app.db import Base, get_engine, get_sessionmaker
from app.models import AdoRepoSnapshot, PipelineLink, Repo, ReadinessCheck, SyncRun
from app.services.sync_service import run_ado_pipelines_sync, run_ado_sync, run_github_sync, run_test_plans_sync

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
        "readme": {"id": "1"}, "codeowners": {"id": "2"}, "dockerfile": None,
        "branchProtectionRules": {"nodes": [{"pattern": "main", "requiredApprovingReviewCount": 1}]},
        "primaryLanguage": {"name": "TypeScript"}, "languages": {"totalSize": 12345},
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
        "migrated_from_ado", "codeowners_assigned", "readme_present", "branch_protection",
        "naming_standardized", "dockerized", "deployed_aca",
    }


@pytest.mark.asyncio
async def test_run_github_sync_populates_primary_language_and_code_size(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    repo = session.query(Repo).filter_by(name="checkout-web").one()
    assert repo.primary_language == "TypeScript"
    assert repo.total_code_bytes == 12345


@pytest.mark.asyncio
async def test_run_github_sync_is_idempotent_on_rerun(session):
    transport = httpx.MockTransport(github_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://api.github.com") as client:
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)
        await run_github_sync(session, client, org="acme-org", token="gh-token", now=NOW)

    assert session.query(Repo).count() == 1
    assert session.query(ReadinessCheck).count() == 7


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


PIPELINES_LIST = {"value": [{"id": 7, "name": "checkout-web-ci"}]}
# Real ADO pipeline configurations never return a "url" field -- gitHub-backed repos
# identify themselves via "fullName" (org/repo).
PIPELINE_DETAIL = {
    "id": 7, "name": "checkout-web-ci",
    "configuration": {"type": "yaml", "repository": {"type": "gitHub", "fullName": "acme-org/checkout-web"}},
}
ENVIRONMENTS = {"value": [
    {"id": 10, "name": "Dev Deployment"}, {"id": 11, "name": "QA Deployment"},
    {"id": 12, "name": "UAT Deployment"}, {"id": 13, "name": "Prod Deployment"},
]}
EMPTY_GIT_REPOS = {"value": []}


def pipelines_handler(request: httpx.Request) -> httpx.Response:
    path = str(request.url.path)
    if path.endswith("/_apis/pipelines"):
        return httpx.Response(200, json=PIPELINES_LIST)
    if path.endswith("/_apis/git/repositories"):
        return httpx.Response(200, json=EMPTY_GIT_REPOS)
    if path.endswith("/_apis/pipelines/7"):
        return httpx.Response(200, json=PIPELINE_DETAIL)
    if path.endswith("/_apis/pipelines/environments"):
        return httpx.Response(200, json=ENVIRONMENTS)
    env_id = int(request.url.params["resourceId"])
    return httpx.Response(200, json={"value": [{"id": 1}] if env_id in (12, 13) else []})


def release_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"value": []})


PIPELINES_LIST_MULTI = {"value": [{"id": 7, "name": "checkout-web-ci"}, {"id": 8, "name": "billing-api-ci"}]}
PIPELINE_DETAIL_2 = {
    "id": 8, "name": "billing-api-ci",
    "configuration": {"type": "yaml", "repository": {"type": "gitHub", "fullName": "acme-org/billing-api"}},
}


def make_pipelines_handler_with_call_counts(call_counts: dict[str, int]):
    """Build a pipelines handler like pipelines_handler, but for two matched pipelines/repos,
    and counting hits to the environments-list and checks-configurations endpoints."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = str(request.url.path)
        if path.endswith("/_apis/pipelines"):
            return httpx.Response(200, json=PIPELINES_LIST_MULTI)
        if path.endswith("/_apis/git/repositories"):
            return httpx.Response(200, json=EMPTY_GIT_REPOS)
        if path.endswith("/_apis/pipelines/7"):
            return httpx.Response(200, json=PIPELINE_DETAIL)
        if path.endswith("/_apis/pipelines/8"):
            return httpx.Response(200, json=PIPELINE_DETAIL_2)
        if path.endswith("/_apis/pipelines/environments"):
            call_counts["environments"] = call_counts.get("environments", 0) + 1
            return httpx.Response(200, json=ENVIRONMENTS)
        call_counts["checks"] = call_counts.get("checks", 0) + 1
        env_id = int(request.url.params["resourceId"])
        return httpx.Response(200, json={"value": [{"id": 1}] if env_id in (12, 13) else []})

    return handler


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_links_matching_repo_and_computes_checks(session):
    session.add(Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web"))
    session.commit()

    async with httpx.AsyncClient(transport=httpx.MockTransport(pipelines_handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        sync_run = await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "success"
    repo = session.query(Repo).filter_by(name="checkout-web").one()
    link = session.query(PipelineLink).filter_by(repo_id=repo.id).one()
    assert link.ado_pipeline_id == 7
    assert link.is_yaml is True

    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["pipeline_linked"].status == "pass"
    assert checks["pipeline_is_yaml"].status == "pass"
    assert checks["environment_gates_configured"].status == "pass"


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_leaves_unmatched_repo_without_a_link(session):
    session.add(Repo(name="no-pipeline-repo", github_url="https://github.com/acme-org/no-pipeline-repo"))
    session.commit()

    async with httpx.AsyncClient(transport=httpx.MockTransport(pipelines_handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    repo = session.query(Repo).filter_by(name="no-pipeline-repo").one()
    assert session.query(PipelineLink).filter_by(repo_id=repo.id).one_or_none() is None
    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["pipeline_linked"].status == "fail"
    assert checks["environment_gates_configured"].status == "unknown"


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_records_failure_on_connector_error(session):
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing_handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        sync_run = await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "failed"
    assert "500" in sync_run.error or "boom" in sync_run.error


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_fetches_environment_gates_exactly_once_for_multiple_matched_repos(session):
    session.add(Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web"))
    session.add(Repo(name="billing-api", github_url="https://github.com/acme-org/billing-api"))
    session.commit()

    call_counts: dict[str, int] = {}
    handler = make_pipelines_handler_with_call_counts(call_counts)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        sync_run = await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "success"
    # Both repos matched a pipeline link, but the environments-list call and each of the
    # 4 environment checks-configurations calls must happen exactly once, not once per repo.
    assert call_counts["environments"] == 1
    assert call_counts["checks"] == 4

    for repo_name in ("checkout-web", "billing-api"):
        repo = session.query(Repo).filter_by(name=repo_name).one()
        checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
        assert checks["environment_gates_configured"].status == "pass"


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_matches_repo_name_case_insensitively(session):
    session.add(Repo(name="Checkout-Web", github_url="https://github.com/acme-org/checkout-web"))
    session.commit()

    async with httpx.AsyncClient(transport=httpx.MockTransport(pipelines_handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        sync_run = await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "success"
    repo = session.query(Repo).filter_by(name="Checkout-Web").one()
    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["pipeline_linked"].status == "pass"


@pytest.mark.asyncio
async def test_run_ado_pipelines_sync_preserves_a_manually_linked_pipeline(session):
    """A repo whose pipeline was set via PATCH /repos/{id} (source='manual') must not be
    re-matched or overwritten by the next auto-sync, even if auto-matching would disagree."""
    repo = Repo(name="checkout-web", github_url="https://github.com/acme-org/checkout-web")
    session.add(repo)
    session.commit()
    session.add(PipelineLink(
        repo_id=repo.id, ado_pipeline_id=999, ado_pipeline_name="manually-set-pipeline",
        is_yaml=True, source="manual",
    ))
    session.commit()

    async with httpx.AsyncClient(transport=httpx.MockTransport(pipelines_handler), base_url="https://dev.azure.com/acme-ado") as pipelines_client, \
            httpx.AsyncClient(transport=httpx.MockTransport(release_handler), base_url="https://vsrm.dev.azure.com/acme-ado") as release_client:
        sync_run = await run_ado_pipelines_sync(
            session, pipelines_client, release_client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "success"
    link = session.query(PipelineLink).filter_by(repo_id=repo.id).one()
    assert link.ado_pipeline_id == 999
    assert link.source == "manual"
    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["pipeline_linked"].status == "pass"


TEST_RUNS_RESPONSE = {"value": [
    {"id": 500, "state": "Completed", "completedDate": "2026-07-01T00:00:00Z", "totalTests": 20, "passedTests": 20},
]}


def _test_plans_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=TEST_RUNS_RESPONSE)


@pytest.mark.asyncio
async def test_run_test_plans_sync_computes_e2e_covered_for_mapped_repo(session):
    session.add(Repo(
        name="checkout-web", github_url="https://github.com/acme-org/checkout-web", e2e_test_plan_id=42,
    ))
    session.commit()

    transport = httpx.MockTransport(_test_plans_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        sync_run = await run_test_plans_sync(
            session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "success"
    repo = session.query(Repo).filter_by(name="checkout-web").one()
    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["e2e_covered"].status == "pass"
    assert checks["unit_tested"].status == "pending_convention"
    assert checks["integration_tested"].status == "pending_convention"
    assert checks["load_tested"].status == "unknown"


@pytest.mark.asyncio
async def test_run_test_plans_sync_skips_connector_call_for_unmapped_repo(session):
    session.add(Repo(name="no-e2e-repo", github_url="https://github.com/acme-org/no-e2e-repo"))
    session.commit()

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=TEST_RUNS_RESPONSE)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        await run_test_plans_sync(session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW)

    assert len(calls) == 0
    repo = session.query(Repo).filter_by(name="no-e2e-repo").one()
    checks = {c.stage_key: c for c in session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()}
    assert checks["e2e_covered"].status == "pending_convention"


@pytest.mark.asyncio
async def test_run_test_plans_sync_records_failure_on_connector_error(session):
    def failing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    session.add(Repo(
        name="checkout-web", github_url="https://github.com/acme-org/checkout-web", e2e_test_plan_id=42,
    ))
    session.commit()

    transport = httpx.MockTransport(failing_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        sync_run = await run_test_plans_sync(
            session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW,
        )

    assert sync_run.status == "failed"
    assert "500" in sync_run.error or "boom" in sync_run.error


@pytest.mark.asyncio
async def test_run_test_plans_sync_is_idempotent_on_rerun(session):
    session.add(Repo(
        name="checkout-web", github_url="https://github.com/acme-org/checkout-web", e2e_test_plan_id=42,
    ))
    session.commit()

    transport = httpx.MockTransport(_test_plans_handler)
    async with httpx.AsyncClient(transport=transport, base_url="https://dev.azure.com/acme-ado") as client:
        await run_test_plans_sync(session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW)
        await run_test_plans_sync(session, client, org="acme-ado", project="acme-project", pat="ado-pat", now=NOW)

    repo = session.query(Repo).filter_by(name="checkout-web").one()
    assert session.query(ReadinessCheck).filter_by(repo_id=repo.id).count() == 4
