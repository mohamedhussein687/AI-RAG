from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiomysql

from app.config import Settings, get_settings
from app.db.sql_executor import redact_database_error


class MySqlConnectionError(RuntimeError):
    pass


@asynccontextmanager
async def readonly_mysql_connection(settings: Settings | None = None) -> AsyncIterator[aiomysql.Connection]:
    settings = settings or get_settings()
    _validate_mysql_settings(settings)
    connection = None
    try:
        connection = await aiomysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_username,
            password=settings.mysql_password,
            db=settings.mysql_database,
            autocommit=True,
            connect_timeout=settings.mysql_connect_timeout_seconds,
            cursorclass=aiomysql.DictCursor,
        )
        yield connection
    except Exception as exc:
        raise MySqlConnectionError(redact_database_error(str(exc))) from exc
    finally:
        if connection is not None:
            connection.close()
            await connection.ensure_closed()


def _validate_mysql_settings(settings: Settings) -> None:
    missing = [
        name
        for name, value in {
            "MYSQL_HOST": settings.mysql_host,
            "MYSQL_DATABASE": settings.mysql_database,
            "MYSQL_USER": settings.mysql_username,
        }.items()
        if not value
    ]
    if missing:
        raise MySqlConnectionError("MySQL configuration is incomplete: " + ", ".join(missing))
