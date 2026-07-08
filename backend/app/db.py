from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def get_engine(database_url: str):
    return create_engine(database_url, future=True)


def get_sessionmaker(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
