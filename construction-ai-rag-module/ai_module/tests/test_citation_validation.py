from app.agent.citation_validator import validate_answer
from app.schemas import RagChunk


def chunk(idx: int) -> RagChunk:
    return RagChunk(chunk_id=f"chk_{idx}", document_id=f"doc_{idx}", title=f"Doc {idx}", source_type="policy", project_id="p1", chunk_index=idx, text="evidence")


def test_unknown_and_range_citations_are_removed():
    result = validate_answer("Answer [S1] [S99] [S1-S99]", [chunk(1)])
    assert result.answer == "Answer [S1]"
    assert len(result.sources) == 1
    assert not result.valid


def test_citations_inside_code_blocks_are_not_returned_as_sources():
    result = validate_answer("Use this ```[S1]``` and evidence [S1]", [chunk(1)])
    assert len(result.sources) == 1
    assert "``` ```" in result.answer or "```" in result.answer


def test_unicode_lookalike_marker_is_normalized():
    result = validate_answer("دليل ［S1］", [chunk(1)])
    assert result.sources[0].chunk_id == "chk_1"
