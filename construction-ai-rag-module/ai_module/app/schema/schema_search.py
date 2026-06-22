from __future__ import annotations

import re

from app.schema.schema_ingestion import SchemaChunk


def search_schema_chunks(
    chunks: list[SchemaChunk],
    *,
    query: str,
    source_name: str | None = None,
    table_name: str | None = None,
    top_k: int = 6,
) -> list[SchemaChunk]:
    query_terms = _terms(query)
    candidates = []
    for chunk in chunks:
        if source_name and chunk.source_name != source_name:
            continue
        if table_name and chunk.table_name != table_name:
            continue
        content_terms = _terms(chunk.content)
        score = len(query_terms & content_terms)
        if query.lower() in chunk.content.lower():
            score += 10
        if score > 0:
            candidates.append((score, chunk))
    return [chunk for _, chunk in sorted(candidates, key=lambda item: item[0], reverse=True)[:top_k]]


def _terms(text: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[\w؀-ۿ]+", text) if len(item) > 1}
