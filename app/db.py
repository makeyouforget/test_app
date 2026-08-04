"""Подключение к PostgreSQL.

Важно: приложение НЕ ждёт базу самостоятельно. Если на старте БД недоступна,
процесс завершается с ошибкой. Ожидание готовности БД — задача инфраструктуры
(entrypoint / оркестратор).
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import Base

log = logging.getLogger("notes.db")

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def init_engine(settings: Settings) -> Engine:
    global _engine, _SessionFactory

    log.info("connecting to database: %s", settings.safe_database_url)
    _engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": settings.db_connect_timeout},
    )
    # Единственная попытка: не ретраим намеренно.
    with _engine.connect() as conn:
        conn.execute(text("SELECT 1"))

    Base.metadata.create_all(_engine)
    _SessionFactory = sessionmaker(bind=_engine, expire_on_commit=False)
    log.info("database is ready")
    return _engine


def dispose_engine() -> None:
    global _engine, _SessionFactory
    if _engine is not None:
        log.info("closing database connection pool")
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def ping() -> None:
    """Бросает исключение, если БД недоступна. Используется в /readyz."""
    if _engine is None:
        raise RuntimeError("engine is not initialized")
    with _engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def get_session() -> Session:
    """FastAPI-зависимость: сессия на запрос."""
    if _SessionFactory is None:
        raise RuntimeError("engine is not initialized")
    session = _SessionFactory()
    try:
        yield session
    finally:
        session.close()
