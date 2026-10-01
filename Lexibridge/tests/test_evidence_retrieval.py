import uuid

import pytest

from services import audit_records
from services import evidence_retrieval


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_token(prefix="Evidence"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def create_governed_chunk(app_module, *, token=None, text=None, **overrides):
    token = token or unique_token()
    source_uid = overrides.get("source_uid") or f"src-{uuid.uuid4().hex}"
    course = overrides.get("course", f"Evidence Course {uuid.uuid4().hex[:6]}")
    chapter = overrides.get("chapter", "Retrieval")
    language = overrides.get("language", "en")
    quality_status = overrides.get("quality_status", "native_text_ok")
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        title=overrides.get("title", f"{token} Source"),
        name=overrides.get("title", f"{token} Source"),
        source_title=overrides.get("title", f"{token} Source"),
        course=course,
        chapter=chapter,
        language=language,
        source_type=overrides.get("source_type", "teacher_upload"),
        source_role=overrides.get("source_role", "english_course_material" if language == "en" else "chinese_reference_material"),
        scope_type=overrides.get("scope_type"),
        visibility=overrides.get("visibility", "course"),
        trust_level=overrides.get("source_trust_level", overrides.get("trust_level", "teacher_verified")),
        quality_status=overrides.get("source_quality_status", quality_status),
        quality_flags=overrides.get("source_quality_flags", [quality_status] if quality_status else []),
        status=overrides.get("source_status", "active"),
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    chunk_text = text or f"{token} describes Fourier transform evidence for governed retrieval."
    chunk = app_module.KnowledgeChunk(
        chunk_uid=overrides.get("chunk_uid", f"chunk-{uuid.uuid4().hex}"),
        source_uid=source.source_uid,
        knowledge_source_id=source.id,
        document_id=0,
        scope_type=overrides.get("scope_type"),
        course=course,
        chapter=chapter,
        language=language,
        content=chunk_text,
        normalized_text=" ".join(chunk_text.split()),
        source_locator=overrides.get("source_locator", "page:4"),
        page_number=overrides.get("page_number", 4),
        slide_number=overrides.get("slide_number"),
        block_type=overrides.get("block_type", "text"),
        quality_status=quality_status,
        quality_flags=overrides.get("quality_flags", [quality_status] if quality_status else []),
        trust_level=overrides.get("trust_level", "teacher_verified"),
        visibility=overrides.get("visibility", "course"),
        status=overrides.get("chunk_status", "active"),
        parse_uid=overrides.get("parse_uid", f"parse-{uuid.uuid4().hex}"),
        parse_block_uid=overrides.get("parse_block_uid", f"block-{uuid.uuid4().hex}"),
        formula_block_ids_json=overrides.get("formula_block_ids_json", "[]"),
    )
    app_module.db.session.add(chunk)
    app_module.db.session.commit()
    return source, chunk, token


def test_search_evidence_returns_structured_governed_candidate(app_module):
    with app_module.app.app_context():
        long_tail = " ".join(["context"] * 80)
        query_token = unique_token("Needle")
        source, chunk, token = create_governed_chunk(
            app_module,
            text=f"Intro text. {long_tail} {query_token} {long_tail}",
        )

        result = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            query_token,
            filters={"course": chunk.course, "language": "en"},
            limit=5,
        )

        assert result.total == 1
        candidate = result.candidates[0]
        assert candidate["chunk_uid"] == chunk.chunk_uid
        assert candidate["source_uid"] == source.source_uid
        assert candidate["source_locator"] == "page:4"
        assert candidate["trust_level"] == "teacher_verified"
        assert candidate["quality_status"] == "native_text_ok"
        assert 0 <= candidate["score"] <= 1
        assert len(candidate["snippet"]) <= evidence_retrieval.DEFAULT_SNIPPET_CHARS + 6
        assert "content" not in candidate
        assert query_token in candidate["matched_terms"]


def test_stale_formula_flags_are_suppressed_only_for_explicitly_formula_free_prose(
    app_module,
):
    with app_module.app.app_context():
        token = unique_token("ChargeUnit")
        _, clean_chunk, _ = create_governed_chunk(
            app_module,
            token=token,
            text=f"{token}: electric charge is measured in coulombs (C).",
            source_quality_flags=[
                "native_text_ok",
                "formula_detected",
                "formula_ocr_required",
            ],
            quality_flags=[
                "native_text_ok",
                "formula_detected",
                "formula_ocr_required",
            ],
            formula_block_ids_json="[]",
            scope_type="personal",
        )
        _, formula_chunk, _ = create_governed_chunk(
            app_module,
            token=token,
            text=f"{token}: V = U / q.",
            source_quality_flags=[
                "native_text_ok",
                "formula_detected",
                "formula_ocr_required",
            ],
            quality_flags=[
                "native_text_ok",
                "formula_detected",
                "formula_ocr_required",
            ],
            formula_block_ids_json="[]",
            scope_type="personal",
        )

        clean = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            token,
            filters={"source_uid": clean_chunk.source_uid},
        )
        formula = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            token,
            filters={
                "source_uid": formula_chunk.source_uid,
                "include_needs_review": True,
            },
        )

        assert clean.total == 1
        assert "formula_context_risk" not in clean.candidates[0]["risk_labels"]
        assert formula.total == 1
        assert "formula_context_risk" in formula.candidates[0]["risk_labels"]


def test_search_evidence_rejects_empty_query(app_module):
    with app_module.app.app_context():
        with pytest.raises(evidence_retrieval.EvidenceRetrievalError):
            evidence_retrieval.search_evidence(
                app_module.db.session,
                app_module.KnowledgeChunk,
                app_module.KnowledgeSource,
                "",
            )


def test_search_evidence_excludes_anonymous_chunks_without_source_uid(app_module):
    with app_module.app.app_context():
        token = unique_token("AnonymousToken")
        chunk = app_module.KnowledgeChunk(
            chunk_uid=f"chunk-{uuid.uuid4().hex}",
            source_uid="",
            document_id=0,
            course="Anonymous Evidence Course",
            chapter="Anonymous",
            language="en",
            content=f"{token} should not be returned without a governed source.",
            normalized_text=f"{token} should not be returned without a governed source.",
            quality_status="native_text_ok",
            quality_flags=["native_text_ok"],
            trust_level="teacher_verified",
            status="active",
        )
        app_module.db.session.add(chunk)
        app_module.db.session.commit()

        result = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            token,
            limit=5,
        )

        assert result.candidates == []


def test_search_evidence_filters_course_chapter_language_trust_and_source_role(app_module):
    with app_module.app.app_context():
        token = unique_token("FilterToken")
        _, expected, _ = create_governed_chunk(
            app_module,
            token=token,
            course="Evidence Filter Course",
            chapter="Expected Chapter",
            language="zh",
            source_role="chinese_reference_material",
            trust_level="reference_material",
            source_trust_level="reference_material",
            text=f"{token} appears in the expected governed Chinese reference chunk.",
        )
        create_governed_chunk(
            app_module,
            token=token,
            course="Other Evidence Course",
            chapter="Other Chapter",
            language="en",
            source_role="english_course_material",
            trust_level="teacher_verified",
            text=f"{token} appears in a different governed chunk.",
        )

        result = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            token,
            filters={
                "course": "Evidence Filter Course",
                "chapter": "Expected Chapter",
                "language": "zh",
                "source_role": "chinese_reference_material",
                "trust_level": "reference_material",
            },
            limit=10,
        )

        assert [candidate["chunk_uid"] for candidate in result.candidates] == [expected.chunk_uid]


def test_search_evidence_excludes_blocked_deprecated_and_low_quality_by_default(app_module):
    with app_module.app.app_context():
        token = unique_token("GateToken")
        _, good, _ = create_governed_chunk(app_module, token=token, text=f"{token} good governed evidence.")
        _, low_quality, _ = create_governed_chunk(
            app_module,
            token=token,
            trust_level="low_quality",
            source_trust_level="low_quality",
            text=f"{token} low quality governed evidence.",
        )
        create_governed_chunk(app_module, token=token, chunk_status="blocked", text=f"{token} blocked chunk.")
        create_governed_chunk(app_module, token=token, chunk_status="deprecated", text=f"{token} deprecated chunk.")
        create_governed_chunk(app_module, token=token, source_status="deprecated", text=f"{token} deprecated source.")
        create_governed_chunk(app_module, token=token, quality_status="parse_failed", text=f"{token} failed parse.")
        create_governed_chunk(app_module, token=token, quality_status="ocr_unavailable", text=f"{token} ocr unavailable.")

        default_result = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            token,
            limit=20,
        )
        include_low_quality = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            token,
            filters={"include_low_quality": True},
            limit=20,
        )

        default_uids = {candidate["chunk_uid"] for candidate in default_result.candidates}
        included_uids = {candidate["chunk_uid"] for candidate in include_low_quality.candidates}
        assert default_uids == {good.chunk_uid}
        assert low_quality.chunk_uid not in default_uids
        assert low_quality.chunk_uid in included_uids


def test_search_evidence_includes_partial_needs_review_only_when_requested(app_module):
    with app_module.app.app_context():
        token = unique_token("PartialToken")
        _, partial_chunk, _ = create_governed_chunk(
            app_module,
            token=token,
            quality_status="partial_text",
            chunk_status="needs_review",
            trust_level="teacher_verified",
            source_trust_level="teacher_verified",
            text=f"{token} partial governed evidence.",
        )

        default_result = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            token,
            limit=5,
        )
        review_result = evidence_retrieval.search_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            token,
            filters={"include_needs_review": True},
            limit=5,
        )

        assert default_result.candidates == []
        assert review_result.candidates[0]["chunk_uid"] == partial_chunk.chunk_uid
        assert "input_partial_text" in review_result.candidates[0]["risk_labels"]
        assert "needs_review_evidence" in review_result.candidates[0]["risk_labels"]


def test_attach_evidence_candidates_to_card_payload_does_not_approve_or_invent_confidence():
    candidate = {"chunk_uid": "chunk-1", "snippet": "short evidence", "score": 0.5}
    payload = evidence_retrieval.attach_evidence_candidates_to_card_payload(
        {"english_term": "Fourier Transform", "course": "Signals"},
        english_candidates=[candidate],
    )

    assert payload["status"] == "needs_review"
    assert payload["english_evidence"] == [candidate]
    assert "confidence_score" not in payload
    assert "alignment_reason" not in payload


def test_evidence_search_api_returns_candidates_and_completion_audit(client, app_module, teacher_token):
    request_id = "evidence-api-success"
    with app_module.app.app_context():
        source, chunk, token = create_governed_chunk(
            app_module,
            course="Evidence API Course",
            chapter="Search",
            language="en",
            text="Sensitive full chunk text must stay out of audit. ApiEvidenceToken appears here.",
            token="ApiEvidenceToken",
        )
        source_uid = source.source_uid
        chunk_uid = chunk.chunk_uid

    response = client.post(
        "/api/evidence/search",
        json={"query": "ApiEvidenceToken", "course": "Evidence API Course", "language": "en", "limit": 5},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["request_id"] == request_id
    assert payload["data"]["total"] == 1
    candidate = payload["data"]["candidates"][0]
    assert candidate["chunk_uid"] == chunk_uid
    assert candidate["source_uid"] == source_uid
    with app_module.app.app_context():
        audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="evidence_retrieval_completed",
        ).first()
        serialized = audit_records.serialize_audit_record(audit)
        assert serialized["output_payload"]["result_count"] == 1
        assert chunk_uid in serialized["output_payload"]["top_chunk_uids"]
        assert "Sensitive full chunk text" not in str(serialized["output_payload"])


def test_evidence_search_api_missing_query_returns_json_and_failure_audit(client, app_module, teacher_token):
    request_id = "evidence-api-missing-query"
    response = client.post(
        "/api/evidence/search",
        json={"course": "Evidence API Course"},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["request_id"] == request_id
    assert payload["audit_error_code"] == "missing_query"
    with app_module.app.app_context():
        audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="evidence_retrieval_failed",
        ).first()
        assert audit is not None
        serialized = audit_records.serialize_audit_record(audit)
        assert serialized["error_code"] == "missing_query"
        assert "Authorization" not in str(serialized["input_payload"])


def test_evidence_search_api_caps_limit_and_returns_empty_candidates(client, teacher_token):
    response = client.post(
        "/api/evidence/search",
        json={"query": "NoSuchEvidenceTokenForLexiBridge", "limit": 999},
        headers=bearer(teacher_token),
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["request_id"]
    assert payload["data"]["filters"]["limit"] == evidence_retrieval.MAX_LIMIT
    assert payload["data"]["total"] == 0
    assert payload["data"]["candidates"] == []
