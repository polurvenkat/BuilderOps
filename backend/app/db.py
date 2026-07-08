from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str):
    if database_url in ("sqlite:///:memory:", "sqlite://"):
        return create_engine(
            database_url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(database_url, future=True)


def get_sessionmaker(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
