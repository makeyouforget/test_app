"""Конфигурация приложения.

Все настройки читаются ТОЛЬКО из переменных окружения.
Значений по умолчанию для секретов нет: если пароль или адрес БД не переданы,
приложение падает на старте с внятной ошибкой.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote_plus


class ConfigError(RuntimeError):
    """Не хватает обязательных переменных окружения."""


def _get(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    database_url: str
    app_name: str
    log_level: str
    # Сколько секунд приложение доживает после SIGTERM, дорабатывая запросы.
    shutdown_delay: int
    # Таймаут одной попытки подключения к БД на старте.
    db_connect_timeout: int

    @property
    def safe_database_url(self) -> str:
        """URL без пароля — для логов."""
        url = self.database_url
        if "@" not in url or "//" not in url:
            return url
        scheme, rest = url.split("//", 1)
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}//{user}:***@{host}"


def _build_database_url() -> str:
    """DATABASE_URL целиком либо собранный из POSTGRES_* переменных."""
    url = _get("DATABASE_URL")
    if url:
        return url

    missing = [
        name
        for name in ("POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD")
        if not _get(name)
    ]
    if missing:
        raise ConfigError(
            "Database is not configured. Set DATABASE_URL, or all of: "
            + ", ".join(missing)
        )

    host = _get("POSTGRES_HOST")
    port = _get("POSTGRES_PORT", "5432")
    db = _get("POSTGRES_DB")
    user = quote_plus(_get("POSTGRES_USER") or "")
    password = quote_plus(_get("POSTGRES_PASSWORD") or "")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def load_settings() -> Settings:
    return Settings(
        database_url=_build_database_url(),
        app_name=_get("APP_NAME", "notes") or "notes",
        log_level=(_get("LOG_LEVEL", "INFO") or "INFO").upper(),
        shutdown_delay=_get_int("SHUTDOWN_DELAY_SECONDS", 3),
        db_connect_timeout=_get_int("DB_CONNECT_TIMEOUT", 5),
    )
