from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.main import get_db
from app.models import SyncRun
from app.schemas import SyncRunOut
from app.services.sync_service import run_ado_sync, run_github_sync

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status")
def sync_status(session: Session = Depends(get_db)):
    result = {}
    for connector in ("github", "ado"):
        latest = (
            session.query(SyncRun)
            .filter_by(connector=connector)
            .order_by(SyncRun.started_at.desc())
            .first()
        )
        result[connector] = SyncRunOut.model_validate(latest).model_dump() if latest else None
    return result


# Runs synchronously within the request (deliberate v1 simplification - no background-task
# infrastructure yet). Revisit with a background task if org size makes this slow enough to
# risk a gateway timeout.
@router.post("/github", response_model=SyncRunOut, status_code=200)
async def trigger_github_sync(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    async with httpx.AsyncClient(base_url="https://api.github.com") as client:
        return await run_github_sync(
            session, client, org=settings.github_org, token=settings.github_token, now=datetime.now(timezone.utc)
        )


# Runs synchronously within the request (deliberate v1 simplification - no background-task
# infrastructure yet). Revisit with a background task if org size makes this slow enough to
# risk a gateway timeout.
@router.post("/ado", response_model=SyncRunOut, status_code=200)
async def trigger_ado_sync(request: Request, session: Session = Depends(get_db)):
    settings = request.app.state.settings
    async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}") as client:
        return await run_ado_sync(
            session, client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
            now=datetime.now(timezone.utc),
        )
