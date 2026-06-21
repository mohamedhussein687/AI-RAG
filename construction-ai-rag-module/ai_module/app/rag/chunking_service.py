import re


class ChunkingService:
    def __init__(self, max_chunk_chars: int = 1600, overlap_chars: int = 180):
        self.max_chunk_chars = max_chunk_chars
        self.overlap_chars = overlap_chars

    def clean_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()

    def split(self, text: str) -> list[str]:
        text = self.clean_text(text)
        if not text:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self.max_chunk_chars)
            if end < len(text):
                boundary = max(text.rfind(". ", start, end), text.rfind("؟ ", start, end), text.rfind("\n", start, end))
                if boundary > start + self.max_chunk_chars // 2:
                    end = boundary + 1
            chunks.append(text[start:end].strip())
            if end >= len(text):
                break
            start = max(0, end - self.overlap_chars)
        return [c for c in chunks if c]
