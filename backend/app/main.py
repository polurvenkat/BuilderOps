from fastapi import FastAPI, Request
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import Base, get_engine, get_sessionmaker


def get_db(request: Request):
    sessionmaker_ = request.app.state.sessionmaker
    db: Session = sessionmaker_()
    try:
        yield db
    finally:
        db.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="BuilderOps API")

    engine = get_engine(settings.database_url)
    Base.metadata.create_all(engine)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = get_sessionmaker(engine)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
