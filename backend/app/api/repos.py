from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.main import get_db
from app.models import OnboardingLog, ReadinessCheck, Repo
from app.schemas import OnboardingLogIn, OnboardingLogOut, RepoOut, RepoPatchIn, StageCheckOut
from app.services.readiness_store import upsert_readiness_check
from app.services.stage import CheckStatus, derive_stage_info

router = APIRouter(prefix="/repos", tags=["repos"])


def _aware(dt):
    """Normalize datetime to timezone-aware UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _to_repo_out(repo: Repo, session: Session) -> RepoOut:
    checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    stages = {
        c.stage_key: StageCheckOut(status=c.status, source=c.source, detail=c.detail, updated_at=c.updated_at)
        for c in checks
    }
    stage_info = derive_stage_info(
        checks={c.stage_key: CheckStatus(status=c.status, status_changed_at=_aware(c.status_changed_at)) for c in checks},
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
    query = session.query(Repo)
    if domain is not None:
        query = query.filter(Repo.domain == domain)
    repos = [_to_repo_out(r, session) for r in query.all()]

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
    return _to_repo_out(repo, session)


@router.patch("/{repo_id}", response_model=RepoOut)
def patch_repo(repo_id: int, body: RepoPatchIn, session: Session = Depends(get_db)):
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
    session.commit()
    return _to_repo_out(repo, session)


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
