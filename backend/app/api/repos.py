from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.main import get_db
from app.models import OnboardingLog, ReadinessCheck, Repo
from app.schemas import OnboardingLogIn, OnboardingLogOut, RepoOut, RepoPatchIn

router = APIRouter(prefix="/repos", tags=["repos"])


def _to_repo_out(repo: Repo, session: Session) -> RepoOut:
    checks = session.query(ReadinessCheck).filter_by(repo_id=repo.id).all()
    return RepoOut(
        id=repo.id,
        name=repo.name,
        domain=repo.domain,
        migration_wave=repo.migration_wave,
        stages={c.stage_key: c.status for c in checks},
    )


@router.get("", response_model=list[RepoOut])
def list_repos(session: Session = Depends(get_db)):
    repos = session.query(Repo).all()
    return [_to_repo_out(r, session) for r in repos]


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
