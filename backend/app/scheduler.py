import asyncio
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

from app.services.sync_service import run_ado_pipelines_sync, run_ado_sync, run_github_sync, run_test_plans_sync


def _run_github_sync_job(app: FastAPI):
    settings = app.state.settings
    session = app.state.sessionmaker()

    async def _go():
        async with httpx.AsyncClient(base_url="https://api.github.com", timeout=30.0) as client:
            await run_github_sync(
                session, client, org=settings.github_org, token=settings.github_token,
                now=datetime.now(timezone.utc),
            )

    try:
        asyncio.run(_go())
    finally:
        session.close()


def _run_ado_sync_job(app: FastAPI):
    settings = app.state.settings
    session = app.state.sessionmaker()

    async def _go():
        async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as client:
            await run_ado_sync(
                session, client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
                now=datetime.now(timezone.utc),
            )

    try:
        asyncio.run(_go())
    finally:
        session.close()


def _run_ado_pipelines_sync_job(app: FastAPI):
    settings = app.state.settings
    session = app.state.sessionmaker()

    async def _go():
        async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as pipelines_client, \
                httpx.AsyncClient(base_url=f"https://vsrm.dev.azure.com/{settings.ado_org}", timeout=30.0) as release_client:
            await run_ado_pipelines_sync(
                session, pipelines_client, release_client, org=settings.ado_org, project=settings.ado_project,
                pat=settings.ado_pat, now=datetime.now(timezone.utc),
            )

    try:
        asyncio.run(_go())
    finally:
        session.close()


def _run_test_plans_sync_job(app: FastAPI):
    settings = app.state.settings
    session = app.state.sessionmaker()

    async def _go():
        async with httpx.AsyncClient(base_url=f"https://dev.azure.com/{settings.ado_org}", timeout=30.0) as client:
            await run_test_plans_sync(
                session, client, org=settings.ado_org, project=settings.ado_project, pat=settings.ado_pat,
                now=datetime.now(timezone.utc),
            )

    try:
        asyncio.run(_go())
    finally:
        session.close()


def start_scheduler(app: FastAPI) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_github_sync_job, "interval", hours=4, args=[app], id="github_sync")
    scheduler.add_job(_run_ado_sync_job, "interval", days=1, args=[app], id="ado_sync")
    scheduler.add_job(_run_ado_pipelines_sync_job, "interval", hours=4, args=[app], id="ado_pipelines_sync")
    scheduler.add_job(_run_test_plans_sync_job, "interval", hours=4, args=[app], id="test_plans_sync")
    scheduler.start()
    app.state.scheduler = scheduler
    return scheduler
