import re
import unicodedata
from dataclasses import dataclass

from app.schemas import RagChunk, Source

CITATION_RE = re.compile(r"\[(S\d{1,3})\]")
RANGE_RE = re.compile(r"\[S\d{1,3}\s*[-–—]\s*S\d{1,3}\]")
CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)


@dataclass(frozen=True)
class CitationValidationResult:
    answer: str
    sources: list[Source]
    valid: bool
    invalid_markers: list[str]


def build_source_map(chunks: list[RagChunk]) -> dict[str, RagChunk]:
    return {f"S{idx}": chunk for idx, chunk in enumerate(chunks, start=1)}


def answer_with_citations(prefix: str, chunks: list[RagChunk]) -> str:
    if not chunks:
        return prefix.rstrip()
    markers = " ".join(f"[S{idx}]" for idx, _ in enumerate(chunks, start=1))
    return f"{prefix.rstrip()} {chunks[0].text} {markers}".strip()


def validate_answer(answer: str, chunks: list[RagChunk]) -> CitationValidationResult:
    normalized = unicodedata.normalize("NFKC", answer or "")
    source_map = build_source_map(chunks)
    invalid: list[str] = []
    if RANGE_RE.search(normalized):
        invalid.extend(RANGE_RE.findall(normalized))
        normalized = RANGE_RE.sub("", normalized)

    code_blocks = CODE_BLOCK_RE.findall(normalized)
    for block in code_blocks:
        invalid.extend(CITATION_RE.findall(block))
    normalized = CODE_BLOCK_RE.sub(lambda m: CITATION_RE.sub("", m.group(0)), normalized)

    seen: list[str] = []
    for marker in CITATION_RE.findall(normalized):
        if marker not in source_map:
            invalid.append(marker)
        elif marker not in seen:
            seen.append(marker)
    for marker in sorted(set(invalid), key=str):
        normalized = normalized.replace(f"[{marker}]", "")
    sources = [source_map[marker].source() for marker in seen if marker in source_map]
    return CitationValidationResult(answer=" ".join(normalized.split()), sources=sources, valid=not invalid, invalid_markers=invalid)
