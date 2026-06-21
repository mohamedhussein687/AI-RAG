import hashlib
import math
from collections.abc import Sequence

import httpx

from app.config import Settings


class EmbeddingClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.size = settings.embedding_dimension if not settings.fake_embeddings else 32

    async def embed(self, text: str) -> list[float]:
        return (await self.embed_batch([text]))[0]

    async def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        if self.settings.fake_embeddings:
            return [self._fake_embed(text) for text in texts]
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds) as client:
            response = await client.post(
                f"{self.settings.embedding_base_url.rstrip('/')}/embed",
                json={"inputs": list(texts), "model": self.settings.embedding_model},
            )
            response.raise_for_status()
            data = response.json()
        vectors = data.get("data", data) if isinstance(data, dict) else data
        if isinstance(vectors, dict) and "embeddings" in vectors:
            vectors = vectors["embeddings"]
        if vectors and isinstance(vectors[0], dict):
            vectors = [item.get("embedding") for item in vectors]
        if len(vectors) != len(texts):
            raise RuntimeError("embedding service returned unexpected vector count")
        return [self._normalize([float(v) for v in vector]) for vector in vectors]

    async def health(self) -> str:
        if self.settings.fake_embeddings:
            return "disabled"
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                response = await client.get(f"{self.settings.embedding_base_url.rstrip('/')}/health")
            return "ok" if response.status_code < 500 else "error"
        except Exception:
            return "error"

    def _fake_embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = [((digest[i % len(digest)] / 255.0) * 2) - 1 for i in range(32)]
        return self._normalize(values)

    def _normalize(self, values: list[float]) -> list[float]:
        norm = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / norm for v in values]
