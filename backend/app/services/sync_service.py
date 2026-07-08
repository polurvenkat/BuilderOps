from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.connectors.ado_connector import fetch_ado_repos
from app.connectors.github_connector import fetch_repos
from app.models import AdoRepoSnapshot, Repo, SyncRun
from app.services.readiness import compute_readiness_checks
from app.services.readiness_store import upsert_readiness_check


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

            for check in compute_readiness_checks(github_repo, ado_repo_names, repo.id, now):
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
