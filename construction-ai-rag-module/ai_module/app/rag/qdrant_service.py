import math
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient, models

from app.config import Settings, get_settings
from app.schemas import RagFilters, UserContext
from .permission_filter import is_authorized_payload


@dataclass
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any]


class InMemoryQdrantService:
    def __init__(self):
        self.points: dict[str, VectorPoint] = {}

    async def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self.points[point_id] = VectorPoint(point_id, vector, payload)

    async def upsert_many(self, points: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        for point_id, vector, payload in points:
            await self.upsert(point_id, vector, payload)

    async def delete(self, point_ids: list[str]) -> None:
        for point_id in point_ids:
            self.points.pop(point_id, None)

    async def search(self, query_vector: list[float], user_context: UserContext, filters: RagFilters, limit: int) -> list[tuple[dict[str, Any], float]]:
        scored: list[tuple[dict[str, Any], float]] = []
        for point in self.points.values():
            payload = point.payload
            if not is_authorized_payload(payload, user_context):
                continue
            if filters.project_id and str(payload.get("project_id")) != filters.project_id:
                continue
            if filters.document_types and payload.get("source_type") not in filters.document_types:
                continue
            scored.append((payload, cosine(query_vector, point.vector)))
        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]

    async def health(self) -> str:
        return "ok"


class QdrantService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = AsyncQdrantClient(url=settings.qdrant_url, timeout=settings.http_timeout_seconds)
        self.collection = settings.qdrant_collection

    async def ensure_collection(self) -> None:
        exists = await self.client.collection_exists(self.collection)
        if not exists:
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(size=self.settings.embedding_dimension, distance=models.Distance.COSINE),
            )
        for field in ("tenant_id", "project_id", "document_id", "document_version", "source_type", "status", "index_version"):
            try:
                await self.client.create_payload_index(self.collection, field_name=field, field_schema=models.PayloadSchemaType.KEYWORD)
            except Exception:
                pass
            
    async def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        await self.upsert_many([(point_id, vector, payload)])

    async def upsert_many(self, points: list[tuple[str, list[float], dict[str, Any]]]) -> None:
        await self.ensure_collection()
        await self.client.upsert(
            collection_name=self.collection,
            points=[models.PointStruct(id=qdrant_point_id(point_id), vector=vector, payload=payload) for point_id, vector, payload in points],
            wait=True,
        )

    async def delete(self, point_ids: list[str]) -> None:
        await self.client.delete(self.collection, points_selector=models.PointIdsList(points=[qdrant_point_id(point_id) for point_id in point_ids]), wait=True)

    async def search(self, query_vector: list[float], user_context: UserContext, filters: RagFilters, limit: int) -> list[tuple[dict[str, Any], float]]:
        await self.ensure_collection()
        must = [models.FieldCondition(key="tenant_id", match=models.MatchValue(value=user_context.tenant_id))]
        if filters.project_id:
            must.append(models.FieldCondition(key="project_id", match=models.MatchValue(value=filters.project_id)))
        if filters.document_types:
            must.append(models.FieldCondition(key="source_type", match=models.MatchAny(any=filters.document_types)))
        must.append(models.FieldCondition(key="status", match=models.MatchValue(value="indexed")))
        must.append(models.FieldCondition(key="index_version", match=models.MatchValue(value=self.settings.index_version)))
        qfilter = models.Filter(must=must)
        response = await self.client.query_points(collection_name=self.collection, query=query_vector, query_filter=qfilter, limit=limit, with_payload=True)
        authorized: list[tuple[dict[str, Any], float]] = []
        for result in response.points:
            payload = dict(result.payload or {})
            if is_authorized_payload(payload, user_context):
                authorized.append((payload, float(result.score)))
        return authorized

    async def health(self) -> str:
        try:
            await self.client.get_collections()
            return "ok"
        except Exception:
            return "error"


def qdrant_point_id(point_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, point_id))

def cosine(a: list[float], b: list[float]) -> float:
    denom = (math.sqrt(sum(x*x for x in a)) or 1.0) * (math.sqrt(sum(x*x for x in b)) or 1.0)
    return sum(x*y for x, y in zip(a, b)) / denom


def get_qdrant_service(settings: Settings | None = None):
    settings = settings or get_settings()
    if settings.fake_embeddings and not settings.production_mode:
        return qdrant
    return QdrantService(settings)


qdrant = InMemoryQdrantService()
