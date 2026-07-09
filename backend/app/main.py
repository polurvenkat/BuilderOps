from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import Base, get_engine, get_sessionmaker
from app.scheduler import start_scheduler
from app import models  # noqa: F401 - ensures all models are registered on Base.metadata before create_all


def get_db(request: Request):
    sessionmaker_ = request.app.state.sessionmaker
    db: Session = sessionmaker_()
    try:
        yield db
    finally:
        db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    from app.api.repos import router as repos_router
    from app.api.sync import router as sync_router

    settings = settings or get_settings()
    app = FastAPI(title="BuilderOps API")

    # No auth/cookies are sent by the frontend (plain fetch, no credentials) -- Phase 0 is
    # BuilderOps-internal only, so a wildcard origin is safe and avoids hardcoding the dev
    # server's port.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = get_sessionmaker(engine)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(repos_router)
    app.include_router(sync_router)

    if settings.database_url != "sqlite:///:memory:":
        start_scheduler(app)

    return app
