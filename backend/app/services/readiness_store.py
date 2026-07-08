from sqlalchemy.orm import Session

from app.models import ReadinessCheck


def upsert_readiness_check(session: Session, check: ReadinessCheck) -> None:
    existing = session.get(ReadinessCheck, (check.repo_id, check.stage_key))
    if existing is None or existing.status != check.status:
        check.status_changed_at = check.updated_at
    else:
        check.status_changed_at = existing.status_changed_at
    session.merge(check)
