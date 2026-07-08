from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.connectors.ado_connector import fetch_ado_repos
from app.connectors.ado_pipelines_connector import fetch_environment_checks, fetch_pipeline_links, fetch_release_definitions
from app.connectors.ado_test_plans_connector import fetch_test_plan_latest_run
from app.connectors.github_connector import fetch_repos
from app.models import AdoRepoSnapshot, PipelineLink, Repo, SyncRun
from app.services.readiness import compute_readiness_checks
from app.services.readiness_pipeline import compute_pipeline_readiness_checks
from app.services.readiness_store import upsert_readiness_check
from app.services.test_readiness import compute_e2e_readiness_checks


def _parse_iso_datetime(iso_string: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string to datetime object."""
    if not iso_string:
        return None
    return datetime.fromisoformat(iso_string.replace('Z', '+00:00'))


async def run_github_sync(
    session: Session, client: httpx.AsyncClient, org: str, token: str, now: datetime
) -> SyncRun:
    sync_run = SyncRun(connector="github", started_at=now, status="running")
    session.add(sync_run)
    session.commit()

    try:
        github_repos = await fetch_repos(client, org=org, token=token)
        ado_repo_names = {row.name for row in session.query(AdoRepoSnapshot).all()}

        for github_repo in github_repos:
            repo = session.query(Repo).filter_by(name=github_repo.name).one_or_none()
            if repo is None:
                repo = Repo(name=github_repo.name, github_url=github_repo.url)
                session.add(repo)
                session.flush()  # assigns repo.id before building checks
            repo.github_url = github_repo.url
            repo.last_synced_at = now

            for check in compute_readiness_checks(
                github_repo, ado_repo_names, repo.id, now, dockerize_eligible=repo.dockerize_eligible,
            ):
                upsert_readiness_check(session, check)

        sync_run.status = "success"
        sync_run.finished_at = now
        session.commit()
    except Exception as exc:  # noqa: BLE001 - deliberately broad: record any failure on the SyncRun
        session.rollback()
        sync_run.status = "failed"
        sync_run.error = str(exc)
        sync_run.finished_at = now
        session.add(sync_run)
        session.commit()

    return sync_run


async def run_ado_sync(
    session: Session, client: httpx.AsyncClient, org: str, project: str, pat: str, now: datetime
) -> SyncRun:
    sync_run = SyncRun(connector="ado", started_at=now, status="running")
    session.add(sync_run)
    session.commit()

    try:
        ado_repos = await fetch_ado_repos(client, org=org, project=project, pat=pat)

        session.query(AdoRepoSnapshot).delete()
        for repo in ado_repos:
            session.add(AdoRepoSnapshot(
                name=repo.name,
                last_activity=_parse_iso_datetime(repo.last_activity),
                synced_at=now
            ))

        sync_run.status = "success"
        sync_run.finished_at = now
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        sync_run.status = "failed"
        sync_run.error = str(exc)
        sync_run.finished_at = now
        session.add(sync_run)
        session.commit()

    return sync_run


_GATE_ENVIRONMENT_NAMES = ["dev", "qa", "uat", "prod"]


def _normalize_repo_url(url: str) -> str:
    """Normalize a repo URL for comparison.

    ADO's configuration.repository.url and GitHub's GraphQL url field can differ by
    trivial formatting (a trailing `.git` suffix, a trailing slash, or letter casing)
    while still referring to the same repository. Normalize both sides before comparing.
    """
    normalized = (url or "").strip().lower()
    normalized = normalized.rstrip("/")
    if normalized.endswith(".git"):
        normalized = normalized[: -len(".git")]
    normalized = normalized.rstrip("/")
    return normalized


async def run_ado_pipelines_sync(
    session: Session,
    pipelines_client: httpx.AsyncClient,
    release_client: httpx.AsyncClient,
    org: str,
    project: str,
    pat: str,
    now: datetime,
) -> SyncRun:
    sync_run = SyncRun(connector="ado_pipelines", started_at=now, status="running")
    session.add(sync_run)
    session.commit()

    try:
        pipeline_links = await fetch_pipeline_links(pipelines_client, org=org, project=project, pat=pat)
        release_defs = await fetch_release_definitions(release_client, org=org, project=project, pat=pat)

        # environment_gates reflects the project's dev/qa/uat/prod ADO Environments and
        # their approval-check configuration -- project-global data, not per-repo. Fetch
        # it once here rather than once per matched repo inside the loop below.
        environment_gates_by_project = await fetch_environment_checks(
            pipelines_client, org=org, project=project, pat=pat,
            environment_names=_GATE_ENVIRONMENT_NAMES,
        )

        for repo in session.query(Repo).all():
            normalized_repo_url = _normalize_repo_url(repo.github_url)
            link_match = next(
                (p for p in pipeline_links if _normalize_repo_url(p.repository_url) == normalized_repo_url),
                None,
            )
            has_classic = any(repo.name.lower() in rd.name.lower() for rd in release_defs)

            if link_match is not None:
                link_row = session.query(PipelineLink).filter_by(repo_id=repo.id).one_or_none()
                if link_row is None:
                    link_row = PipelineLink(repo_id=repo.id)
                    session.add(link_row)
                link_row.ado_pipeline_id = link_match.pipeline_id
                link_row.ado_pipeline_name = link_match.pipeline_name
                link_row.is_yaml = link_match.is_yaml
                link_row.last_synced_at = now
                session.flush()

                environment_gates = environment_gates_by_project
            else:
                environment_gates = {}

            for check in compute_pipeline_readiness_checks(
                repo_id=repo.id,
                has_pipeline_link=link_match is not None,
                is_yaml=link_match.is_yaml if link_match else None,
                has_classic_release_def=has_classic,
                environment_gates=environment_gates,
                now=now,
            ):
                upsert_readiness_check(session, check)

        sync_run.status = "success"
        sync_run.finished_at = now
        session.commit()
    except Exception as exc:  # noqa: BLE001 - deliberately broad: record any failure on the SyncRun
        session.rollback()
        sync_run.status = "failed"
        sync_run.error = str(exc)
        sync_run.finished_at = now
        session.add(sync_run)
        session.commit()

    return sync_run


async def run_test_plans_sync(
    session: Session, client: httpx.AsyncClient, org: str, project: str, pat: str, now: datetime
) -> SyncRun:
    sync_run = SyncRun(connector="test_plans", started_at=now, status="running")
    session.add(sync_run)
    session.commit()

    try:
        for repo in session.query(Repo).all():
            latest_run = None
            if repo.e2e_test_plan_id is not None:
                latest_run = await fetch_test_plan_latest_run(
                    client, org=org, project=project, pat=pat, test_plan_id=repo.e2e_test_plan_id,
                )

            for check in compute_e2e_readiness_checks(repo.id, repo.e2e_test_plan_id, latest_run, now):
                upsert_readiness_check(session, check)

        sync_run.status = "success"
        sync_run.finished_at = now
        session.commit()
    except Exception as exc:  # noqa: BLE001 - deliberately broad: record any failure on the SyncRun
        session.rollback()
        sync_run.status = "failed"
        sync_run.error = str(exc)
        sync_run.finished_at = now
        session.add(sync_run)
        session.commit()

    return sync_run
