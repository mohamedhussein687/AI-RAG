import re

import httpx

from app.config import Settings
from app.schemas import RagChunk


def terms(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[\w؀-ۿ]+", text) if len(t) > 1}


class RerankerClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def rerank(self, query: str, chunks: list[RagChunk], top_k: int) -> list[RagChunk]:
        if not chunks:
            return []
        if self.settings.fake_reranker:
            return self._fake_rerank(query, chunks, top_k)
        pairs = [[query, chunk.text] for chunk in chunks]
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.reranker_base_url.rstrip('/')}/rerank",
                json={"query": query, "texts": [chunk.text for chunk in chunks], "raw_scores": False, "return_text": False},
            )
            if response.status_code == 404:
                response = await client.post(
                    f"{self.settings.reranker_base_url.rstrip('/')}/rerank",
                    json={"inputs": pairs, "model": self.settings.reranker_model},
                )
            response.raise_for_status()
            data = response.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        scored: list[tuple[int, float]] = []
        for position, item in enumerate(items):
            if isinstance(item, dict):
                index = int(item.get("index", position))
                score = float(item.get("score", item.get("relevance_score", 0)))
            else:
                index = position
                score = float(item)
            scored.append((index, score))
        ranked = []
        for index, score in sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]:
            chunk = chunks[index].model_copy(update={"score": score})
            ranked.append(chunk)
        return ranked

    async def health(self) -> str:
        if self.settings.fake_reranker:
            return "disabled"
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.settings.reranker_base_url.rstrip('/')}/health")
            return "ok" if response.status_code < 500 else "error"
        except Exception:
            return "error"

    def _fake_rerank(self, query: str, chunks: list[RagChunk], top_k: int) -> list[RagChunk]:
        q = terms(query)
        def score(chunk: RagChunk) -> float:
            lexical = len(q & terms(chunk.text))
            return lexical + float(chunk.score or 0)
        return sorted(chunks, key=score, reverse=True)[:top_k]
