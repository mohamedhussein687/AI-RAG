from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.config import Settings


@dataclass
class IngestionJobRecord:
    id: str
    document_id: str
    status: str
    error: str | None = None


jobs: dict[str, IngestionJobRecord] = {}


class IngestionService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    async def run_indexing_job(self, job_id: str, document_id: str, work: Callable[[], Awaitable[int]]) -> int:
        jobs[job_id] = IngestionJobRecord(id=job_id, document_id=document_id, status="processing")
        try:
            chunks_indexed = await work()
        except Exception as exc:
            jobs[job_id] = IngestionJobRecord(id=job_id, document_id=document_id, status="failed", error=type(exc).__name__)
            raise
        jobs[job_id] = IngestionJobRecord(id=job_id, document_id=document_id, status="indexed")
        return chunks_indexed
