from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str):
    if database_url in ("sqlite:///:memory:", "sqlite://"):
        engine = create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        # Add event listener to ensure timezone-aware datetimes for all models
        from app.models import Repo, ReadinessCheck, AdoRepoSnapshot, OnboardingLog, SyncRun

        @event.listens_for(Repo, "load", propagate=True)
        @event.listens_for(ReadinessCheck, "load", propagate=True)
        @event.listens_for(AdoRepoSnapshot, "load", propagate=True)
        @event.listens_for(OnboardingLog, "load", propagate=True)
        @event.listens_for(SyncRun, "load", propagate=True)
        def ensure_timezone_aware(target, context):
            for column in target.__class__.__table__.columns:
                if hasattr(column.type, "timezone") and column.type.timezone:
                    value = getattr(target, column.name, None)
                    if isinstance(value, datetime) and value.tzinfo is None:
                        setattr(target, column.name, value.replace(tzinfo=timezone.utc))

        return engine
    return create_engine(database_url, future=True)


def get_sessionmaker(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
