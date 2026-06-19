from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.config import settings


logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def normalize_database_url(raw_url: str) -> str:
    url = make_url(raw_url)

    if url.get_backend_name() != "sqlite":
        return raw_url

    database = url.database
    if not database or database == ":memory:":
        return raw_url

    db_path = Path(database)
    if not db_path.is_absolute():
        db_path = (Path(__file__).resolve().parent.parent / db_path).resolve()

    return str(URL.create("sqlite", database=str(db_path)))


DATABASE_URL = normalize_database_url(settings.database_url)
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_database_directory() -> None:
    url = make_url(DATABASE_URL)

    if url.get_backend_name() != "sqlite":
        return

    database = url.database
    if not database or database == ":memory:":
        return

    db_path = Path(database)
    if not db_path.is_absolute():
        db_path = Path(__file__).resolve().parent.parent / db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Ensured database directory exists: %s", db_path.parent)


def init_db() -> None:
    from src import models  # noqa: F401

    ensure_database_directory()
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized.")


def get_session() -> Session:
    return SessionLocal()
