from app.config import Settings
from app.schemas import RagChunk, RagSearchRequest, RagSearchResponse
from .embedding_client import EmbeddingClient
from .qdrant_service import get_qdrant_service
from .reranker_client import RerankerClient


class RetrievalService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embedder = EmbeddingClient(settings)
        self.reranker = RerankerClient(settings)
        self.vector_store = get_qdrant_service(settings)

    async def search(self, request: RagSearchRequest) -> RagSearchResponse:
        vector = await self.embedder.embed(request.query)
        candidate_limit = min(max(request.top_k * 6, self.settings.max_retrieved_chunks, self.settings.candidate_count), 200)
        raw = await self.vector_store.search(vector, request.user_context, request.filters, candidate_limit)
        chunks = [RagChunk(chunk_id=p["chunk_id"], document_id=p["document_id"], title=p["title"], source_type=p["source_type"], project_id=p.get("project_id"), chunk_index=p["chunk_index"], page_number=p.get("page_number"), section_title=p.get("section_title"), text=p["text"][: self.settings.max_chunk_chars], score=s) for p, s in raw]
        if not chunks:
            return RagSearchResponse(results=[])
        ranked = await self.reranker.rerank(request.query, chunks, min(request.top_k, self.settings.max_retrieved_chunks))
        total = 0
        limited = []
        for chunk in ranked:
            if total + len(chunk.text) > self.settings.max_total_context_chars:
                break
            limited.append(chunk)
            total += len(chunk.text)
        return RagSearchResponse(results=limited)
