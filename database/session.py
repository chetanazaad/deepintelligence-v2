from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import models
from database.base import Base
from database.config import get_settings


settings = get_settings()

engine = create_engine(
    settings.sqlalchemy_database_uri,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


def create_tables() -> None:
    """Create all registered ORM tables."""
    # Force model imports so metadata includes every mapped table.
    _ = models
    Base.metadata.create_all(bind=engine)


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency-compatible DB session generator."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
