import pytest

from app.rag.qdrant_service import InMemoryQdrantService
from app.schemas import RagFilters, UserContext


@pytest.mark.asyncio
async def test_search_filters_tenant_project_and_active_payloads():
    store = InMemoryQdrantService()
    await store.upsert("active", [1.0, 0.0], {"tenant_id": "orbit", "project_id": "default", "source_type": "projects", "is_active": True})
    await store.upsert("inactive", [1.0, 0.0], {"tenant_id": "orbit", "project_id": "default", "source_type": "projects", "is_active": False})
    await store.upsert("other", [1.0, 0.0], {"tenant_id": "other", "project_id": "default", "source_type": "projects", "is_active": True})

    results = await store.search(
        [1.0, 0.0],
        UserContext(id="u", tenant_id="orbit", project_ids=["default"], permissions=[]),
        RagFilters(project_id="default"),
        10,
    )

    assert len(results) == 1
    assert results[0][0]["tenant_id"] == "orbit"
    assert results[0][0]["is_active"] is True
