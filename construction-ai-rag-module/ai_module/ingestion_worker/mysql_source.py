from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

import aiomysql

from app.config import Settings
from ingestion_worker.config import TableConfig


class MySqlSource:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def __aenter__(self) -> "MySqlSource":
        if not all([self.settings.mysql_host, self.settings.mysql_database, self.settings.mysql_username]):
            raise RuntimeError("MySQL source configuration is incomplete")
        self.connection = await aiomysql.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_username,
            password=self.settings.mysql_password,
            db=self.settings.mysql_database,
            autocommit=True,
            connect_timeout=self.settings.mysql_connect_timeout_seconds,
            cursorclass=aiomysql.DictCursor,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.connection.close()
        await self.connection.ensure_closed()

    async def iter_rows(self, table: TableConfig, *, since: datetime | None, batch_size: int = 500) -> AsyncIterator[list[dict[str, Any]]]:
        offset = 0
        while True:
            rows = await self._fetch_batch(table, since=since, limit=batch_size, offset=offset)
            if not rows:
                break
            yield rows
            offset += len(rows)

    async def _fetch_batch(self, table: TableConfig, *, since: datetime | None, limit: int, offset: int) -> list[dict[str, Any]]:
        columns = await self._columns(table.name)
        if table.primary_key not in columns:
            raise RuntimeError(f"source table {table.name} is missing primary key column {table.primary_key}")
        if table.updated_at_column not in columns:
            raise RuntimeError(f"source table {table.name} is missing updated_at column {table.updated_at_column}")
        selected = ", ".join(_ident(column) for column in columns)
        where = ""
        params: list[Any] = []
        if since is not None:
            where = f" where {_ident(table.updated_at_column)} > %s"
            params.append(since)
        sql = f"select {selected} from {_ident(table.name)}{where} order by {_ident(table.updated_at_column)} asc, {_ident(table.primary_key)} asc limit %s offset %s"
        params.extend([limit, offset])
        async with self.connection.cursor() as cursor:
            await cursor.execute(sql, params)
            return list(await cursor.fetchall())

    async def _columns(self, table_name: str) -> list[str]:
        sql = """
            select column_name
            from information_schema.columns
            where table_schema = database() and table_name = %s
            order by ordinal_position
        """
        async with self.connection.cursor() as cursor:
            await cursor.execute(sql, [table_name])
            rows = await cursor.fetchall()
        return [row["column_name"] for row in rows]


def _ident(value: str) -> str:
    if not value.replace("_", "").isalnum():
        raise ValueError(f"unsafe identifier: {value}")
    return f"`{value}`"
