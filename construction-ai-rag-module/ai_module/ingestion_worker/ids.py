from __future__ import annotations

import uuid


POINT_NAMESPACE = uuid.UUID("4b7f6d14-5a9d-4a55-98d0-6f57a7f2aa91")


def source_key(tenant_id: str, project_id: str, source_table: str, source_id: str) -> str:
    return f"{tenant_id}:{project_id}:{source_table}:{source_id}"


def deterministic_point_id(tenant_id: str, project_id: str, source_table: str, source_id: str) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, source_key(tenant_id, project_id, source_table, source_id)))
