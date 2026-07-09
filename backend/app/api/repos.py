import statistics
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.connectors.ado_pipelines_connector import fetch_pipeline_detail, fetch_pipeline_run_status
from app.connectors.github_connector import rename_repo
from app.main import get_db
from app.models import OnboardingLog, PipelineLink, ReadinessCheck, Repo
from app.schemas import (
    OnboardingLogIn,
    OnboardingLogOut,
    OnboardingSummaryOut,
    PipelineStageStatusOut,
    PipelineStatusOut,
    RepoOut,
    RepoPatchIn,
    StageCheckOut,
)
from app.services.complexity import compute_complexity_buckets
from app.services.readiness_store import upsert_readiness_check
from app.services.stage import CheckStatus, derive_stage_info

router = APIRouter(prefix="/repos", tags=["repos"])


def _aware(dt):
    """Normalize datetime to timezone-aware UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _compute_complexity_map(session: Session) -> dict[int, str | None]:
    byte_counts = dict(session.query(Repo.id, Repo.total_code_bytes).all())
    return compute_complexity_buckets(byte_counts)


def _to_repo_out(
    repo: Repo, session: Session, checks: list[ReadinessCheck] | None = None, complexity: str | None = None,
) -> RepoOut:
    if checks is None:
        checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    stages = {
        c.stage_key: StageCheckOut(status=c.status, source=c.source, detail=c.detail, updated_at=c.updated_at)
        for c in checks
    }
    stage_checks = {
        c.stage_key: CheckStatus(status=c.status, status_changed_at=_aware(c.status_changed_at)) for c in checks
    }
    if "domain_assigned" not in stages:
        # No real ReadinessCheck row for domain_assigned exists (e.g. pre-existing data,
        # or a write path other than PATCH /repos/{id} that set repo.domain directly).
        # Synthesize a fallback so a repo with a real domain isn't misreported as stuck.
        domain_status = "pass" if repo.domain else "fail"
        stages["domain_assigned"] = StageCheckOut(
            status=domain_status, source="manual", detail=None, updated_at=None
        )
        stage_checks["domain_assigned"] = CheckStatus(
            status=domain_status, status_changed_at=_aware(repo.created_at)
        )
    stage_info = derive_stage_info(
        checks=stage_checks,
        team=repo.team,
        now=datetime.now(timezone.utc),
    )
    return RepoOut(
        id=repo.id,
        name=repo.name,
        domain=repo.domain,
        team=repo.team,
        migration_wave=repo.migration_wave,
        github_url=repo.github_url,
        last_synced_at=repo.last_synced_at,
        dockerize_eligible=repo.dockerize_eligible,
        e2e_test_plan_id=repo.e2e_test_plan_id,
        app_count=repo.app_count,
        primary_language=repo.primary_language,
        complexity=complexity,
        stages=stages,
        current_stage=stage_info.current_stage,
        is_stuck=stage_info.is_stuck,
        dwell_days=stage_info.dwell_days,
        stuck_reason=stage_info.stuck_reason,
    )


@router.get("", response_model=list[RepoOut])
def list_repos(
    stage: str | None = None,
    domain: str | None = None,
    sort: str | None = None,
    session: Session = Depends(get_db),
):
    complexity_map = _compute_complexity_map(session)

    query = session.query(Repo)
    if domain is not None:
        query = query.filter(Repo.domain == domain)
    repo_rows = query.all()

    # Batch-fetch every repo's readiness checks in one query instead of one query per repo --
    # against a remote DB, N sequential round trips dominate response time (11s for 230 repos).
    checks_by_repo_id: dict[int, list[ReadinessCheck]] = defaultdict(list)
    repo_ids = [r.id for r in repo_rows]
    if repo_ids:
        for check in session.query(ReadinessCheck).filter(ReadinessCheck.repo_id.in_(repo_ids)).all():
            checks_by_repo_id[check.repo_id].append(check)

    repos = [
        _to_repo_out(r, session, checks_by_repo_id.get(r.id, []), complexity_map.get(r.id))
        for r in repo_rows
    ]

    if stage is not None:
        repos = [r for r in repos if r.current_stage == stage]

    if sort == "dwell_desc":
        repos.sort(key=lambda r: (not r.is_stuck, -(r.dwell_days or 0)))

    return repos


@router.get("/{repo_id}", response_model=RepoOut)
def get_repo(repo_id: int, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    complexity_map = _compute_complexity_map(session)
    return _to_repo_out(repo, session, complexity=complexity_map.get(repo_id))


@router.patch("/{repo_id}", response_model=RepoOut)
async def patch_repo(repo_id: int, body: RepoPatchIn, request: Request, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    if body.domain is not None:
        repo.domain = body.domain
        now = datetime.now(timezone.utc)
        upsert_readiness_check(session, ReadinessCheck(
            repo_id=repo_id,
            stage_key="domain_assigned",
            status="pass" if body.domain else "fail",
            source="manual",
            detail=None,
            updated_at=now,
        ))
    if body.team is not None:
        repo.team = body.team
    if body.migration_wave is not None:
        repo.migration_wave = body.migration_wave
    if body.dockerize_eligible is not None:
        repo.dockerize_eligible = body.dockerize_eligible
    if body.e2e_test_plan_id is not None:
        repo.e2e_test_plan_id = body.e2e_test_plan_id
    if body.app_count is not None:
        repo.app_count = body.app_count
    if body.ado_pipeline_id is not None:
        settings = request.app.state.settings
        try:
            async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as client:
                detail = await fetch_pipeline_detail(
                    client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
                    pipeline_id=body.ado_pipeline_id,
                )
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="Couldn't reach Azure DevOps")

        link = session.query(PipelineLink).filter_by(repo_id=repo_id).one_or_none()
        if link is None:
            link = PipelineLink(repo_id=repo_id)
            session.add(link)
        link.ado_pipeline_id = detail.pipeline_id
        link.ado_pipeline_name = detail.pipeline_name
        link.is_yaml = detail.is_yaml
        link.source = "manual"
        now = datetime.now(timezone.utc)
        link.last_synced_at = now
        upsert_readiness_check(session, ReadinessCheck(
            repo_id=repo_id, stage_key="pipeline_linked", status="pass",
            source="manual", detail=None, updated_at=now,
        ))
        upsert_readiness_check(session, ReadinessCheck(
            repo_id=repo_id, stage_key="pipeline_is_yaml", status="pass" if detail.is_yaml else "fail",
            source="manual", detail=None, updated_at=now,
        ))
    if body.new_name is not None:
        settings = request.app.state.settings
        try:
            async with httpx.AsyncClient(base_url="https://api.github.com", timeout=30.0) as client:
                renamed = await rename_repo(
                    client, org=settings.github_org, token=settings.github_token,
                    current_name=repo.name, new_name=body.new_name,
                )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if 400 <= status < 500:
                try:
                    message = exc.response.json().get("message", "GitHub rejected the rename")
                except Exception:
                    message = "GitHub rejected the rename"
                raise HTTPException(status_code=status, detail=message)
            raise HTTPException(status_code=502, detail="Couldn't reach GitHub")
        except httpx.HTTPError:
            raise HTTPException(status_code=502, detail="Couldn't reach GitHub")

        # Update the SAME row GitHub just renamed -- run_github_sync matches incoming repos by
        # Repo.name, so if this doesn't land on the existing row, the next sync creates a
        # duplicate Repo and orphans every readiness check/onboarding log/domain/team tied to
        # the old row's id.
        repo.name = renamed.name
        repo.github_url = renamed.url
    session.commit()
    complexity_map = _compute_complexity_map(session)
    return _to_repo_out(repo, session, complexity=complexity_map.get(repo_id))


@router.post("/{repo_id}/onboarding-log", response_model=OnboardingLogOut, status_code=201)
def post_onboarding_log(repo_id: int, body: OnboardingLogIn, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    entry = OnboardingLog(
        repo_id=repo_id,
        engineer_name=body.engineer_name,
        hours=body.hours,
        logged_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    session.commit()
    return entry


@router.get("/{repo_id}/onboarding-log", response_model=OnboardingSummaryOut)
def get_onboarding_log(repo_id: int, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    entries = session.query(OnboardingLog).filter_by(repo_id=repo_id).order_by(OnboardingLog.logged_at).all()
    hours = [e.hours for e in entries]
    median_hours = statistics.median(hours) if hours else None
    return OnboardingSummaryOut(entries=entries, median_hours=median_hours)


@router.get("/{repo_id}/pipeline-status", response_model=PipelineStatusOut)
async def get_pipeline_status(repo_id: int, request: Request, session: Session = Depends(get_db)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    link = session.query(PipelineLink).filter_by(repo_id=repo_id).one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="Repo has no linked pipeline")

    settings = request.app.state.settings
    try:
        async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as client:
            stages = await fetch_pipeline_run_status(
                client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
                pipeline_id=link.ado_pipeline_id,
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Couldn't reach Azure DevOps")

    return PipelineStatusOut(stages=[
        PipelineStageStatusOut(
            name=s.name, status=s.status, pending_approval_description=s.pending_approval_description,
        )
        for s in stages
    ])
