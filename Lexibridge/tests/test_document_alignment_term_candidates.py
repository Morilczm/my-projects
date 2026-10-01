import inspect
from dataclasses import FrozenInstanceError

import pytest

from services.document_alignment_term_candidates import (
    ERROR_ITEM_LIMIT_EXCEEDED,
    ERROR_TERM_SCOPE_LIMIT_EXCEEDED,
    EXTRACTION_OUTCOME_EXTRACTED,
    EXTRACTION_OUTCOME_EXTRACTION_FAILED,
    EXTRACTION_OUTCOME_INVALID_CHUNK_SCOPE,
    EXTRACTION_OUTCOME_ITEM_LIMIT_EXCEEDED,
    EXTRACTION_OUTCOME_NO_CANDIDATES,
    EXTRACTION_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED,
    FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS,
    FORMAL_DOCUMENT_TERM_EXTRACTION_VERSION,
    FORMAL_TERM_MAX_CHUNK_REFS_PER_CANDIDATE,
    MULTI_CONTEXT_TERM_CANDIDATE,
    ChunkScopedTermCandidate,
    ChunkScopedTermCandidateExtractionResult,
    GovernedSourceChunkSnapshot,
    extract_chunk_scoped_term_candidates,
)


def _chunk(uid, index, text, **overrides):
    values = {
        "chunk_uid": uid,
        "source_uid": "source-9c5a",
        "parse_uid": "parse-9c5a",
        "source_version": "7",
        "chunk_index": index,
        "text": text,
        "language": "en",
    }
    values.update(overrides)
    return GovernedSourceChunkSnapshot(**values)


def _extract(chunks, extractor, **overrides):
    values = {
        "expected_source_uid": "source-9c5a",
        "expected_parse_uid": "parse-9c5a",
        "expected_source_version": "7",
    }
    values.update(overrides)
    return extract_chunk_scoped_term_candidates(chunks, extractor, **values)


def test_candidate_dtos_are_frozen_safe_and_module_has_no_runtime_dependencies():
    snapshot = _chunk("chunk-a", 0, "LEXIBRIDGE_SENTINEL_SECRET_9C5A")
    candidate = ChunkScopedTermCandidate(
        candidate_term="Fourier Transform",
        normalized_term="fourier transform",
        source_chunk_uids=("chunk-a",),
        occurrence_count=1,
        first_chunk_index=0,
        extraction_method=FORMAL_DOCUMENT_TERM_EXTRACTION_VERSION,
        risk_labels=(),
    )
    result = ChunkScopedTermCandidateExtractionResult(
        outcome=EXTRACTION_OUTCOME_EXTRACTED,
        candidates=(candidate,),
        source_chunk_count=1,
        raw_occurrence_count=1,
        canonical_candidate_count=1,
        warning_count=0,
    )
    for value in (snapshot, candidate, result):
        with pytest.raises(FrozenInstanceError):
            value.outcome = "changed" if hasattr(value, "outcome") else "changed"
    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5A" not in repr(snapshot)
    assert "LEXIBRIDGE_SENTINEL_SECRET_9C5A" not in repr(result)

    import services.document_alignment_term_candidates as module

    source = inspect.getsource(module).lower()
    for forbidden in ("flask", "backend.app", "urllib", "requests", "httpx", "socket", "credential", "provider"):
        assert forbidden not in source
    assert "sqlalchemy" not in source


def test_extraction_is_per_chunk_and_never_concatenates_document_text():
    calls = []

    def extractor(text):
        calls.append(text)
        return [{"english_term": text}]

    result = _extract(
        [_chunk("chunk-b", 1, "Laplace Transform"), _chunk("chunk-a", 0, "Fourier Transform")],
        extractor,
    )

    assert calls == ["Fourier Transform", "Laplace Transform"]
    assert [item.candidate_term for item in result.candidates] == ["Fourier Transform", "Laplace Transform"]
    assert [item.source_chunk_uids for item in result.candidates] == [("chunk-a",), ("chunk-b",)]
    assert result.source_chunk_count == 2


def test_normalization_grouping_occurrences_and_provenance_are_stable():
    chunks = [
        _chunk("chunk-c", 4, "third"),
        _chunk("chunk-a", 0, "first"),
        _chunk("chunk-b", 1, "second"),
    ]

    def extractor(text):
        if text == "first":
            return [{"english_term": "  Ｆｏｕｒｉｅｒ   Transform  "}, {"english_term": "Fourier Transform"}]
        return [{"english_term": "FOURIER TRANSFORM"}]

    result = _extract(chunks, extractor)
    candidate = result.candidates[0]

    assert result.outcome == EXTRACTION_OUTCOME_EXTRACTED
    assert candidate.candidate_term == "Fourier Transform"
    assert candidate.normalized_term == "fourier transform"
    assert candidate.source_chunk_uids == ("chunk-a", "chunk-b", "chunk-c")
    assert candidate.occurrence_count == 4
    assert candidate.first_chunk_index == 0
    assert candidate.risk_labels == (MULTI_CONTEXT_TERM_CANDIDATE,)
    assert result.raw_occurrence_count == 4
    assert result.warning_count == 1
    assert result == _extract(list(reversed(chunks)), extractor)


def test_empty_text_is_skipped_and_no_candidates_is_explicit():
    calls = []
    result = _extract(
        [_chunk("chunk-a", 0, ""), _chunk("chunk-b", 1, "   ")],
        lambda text: calls.append(text) or [],
    )
    assert calls == []
    assert result.outcome == EXTRACTION_OUTCOME_NO_CANDIDATES
    assert result.candidates == ()
    assert result.canonical_candidate_count == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_uid": "other-source"},
        {"parse_uid": "other-parse"},
        {"source_version": "8"},
        {"chunk_uid": ""},
    ],
)
def test_invalid_governed_chunk_membership_is_rejected(overrides):
    if overrides.get("chunk_uid") == "":
        with pytest.raises(ValueError):
            _chunk("", 0, "Fourier")
        return
    result = _extract([_chunk("chunk-a", 0, "Fourier", **overrides)], lambda text: [{"english_term": text}])
    assert result.outcome == EXTRACTION_OUTCOME_INVALID_CHUNK_SCOPE
    assert result.candidates == ()


@pytest.mark.parametrize("term", ["", "   ", "bad\x00term", "x" * 221])
def test_invalid_candidate_term_fails_without_silent_truncation(term):
    result = _extract([_chunk("chunk-a", 0, "content")], lambda text: [{"english_term": term}])
    assert result.outcome == EXTRACTION_OUTCOME_EXTRACTION_FAILED
    assert result.candidates == ()


def test_single_chunk_extractor_failure_fails_the_whole_result_without_text_leak():
    sentinel = "LEXIBRIDGE_SENTINEL_SECRET_9C5A"

    def extractor(text):
        if text == "second":
            raise RuntimeError(sentinel)
        return [{"english_term": "Fourier"}]

    result = _extract([_chunk("chunk-a", 0, "first"), _chunk("chunk-b", 1, "second")], extractor)
    assert result.outcome == EXTRACTION_OUTCOME_EXTRACTION_FAILED
    assert result.candidates == ()
    assert sentinel not in result.error_message
    assert sentinel not in repr(result)


def test_more_than_fifty_candidates_are_bounded_with_explicit_overflow():
    terms = [{"english_term": f"Term Candidate {index:02d}"} for index in range(FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS + 1)]
    result = _extract([_chunk("chunk-a", 0, "content")], lambda text: terms)
    assert result.outcome == EXTRACTION_OUTCOME_EXTRACTED
    assert len(result.candidates) == FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS
    assert len(result.overflow_candidates) == 1
    assert result.canonical_candidate_count == FORMAL_DOCUMENT_ALIGNMENT_MAX_ITEMS + 1


def test_term_scope_limit_is_blocked_without_provenance_truncation():
    chunks = [
        _chunk(f"chunk-{index:03d}", index, "content")
        for index in range(FORMAL_TERM_MAX_CHUNK_REFS_PER_CANDIDATE + 1)
    ]
    result = _extract(chunks, lambda text: [{"english_term": "Fourier Transform"}])
    assert result.outcome == EXTRACTION_OUTCOME_TERM_SCOPE_LIMIT_EXCEEDED
    assert result.error_code == ERROR_TERM_SCOPE_LIMIT_EXCEEDED
    assert result.candidates == ()
    assert result.raw_occurrence_count == FORMAL_TERM_MAX_CHUNK_REFS_PER_CANDIDATE + 1
