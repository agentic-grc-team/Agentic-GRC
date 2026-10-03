from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    try:
        url = get_settings().sqlalchemy_url
    except ValueError as exc:
        raise RuntimeError(
            "PostgreSQL is not configured. Set DB_HOST and DB_USER in backend/.env."
        ) from exc
    return create_engine(url, pool_pre_ping=True)


def get_db_session() -> Generator[Session, None, None]:
    with Session(get_engine()) as session:
        yield session
