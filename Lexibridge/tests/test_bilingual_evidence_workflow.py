import uuid

from services import audit_records
from services import bilingual_evidence_workflow


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_token(prefix="Bilingual"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def create_governed_chunk(app_module, *, term, text=None, **overrides):
    source_uid = overrides.get("source_uid") or f"src-{uuid.uuid4().hex}"
    course = overrides.get("course", "Bilingual Evidence Course")
    chapter = overrides.get("chapter", "Evidence Chapter")
    language = overrides.get("language", "en")
    quality_status = overrides.get("quality_status", "native_text_ok")
    source_role = overrides.get(
        "source_role",
        "english_course_material" if language == "en" else "chinese_reference_material",
    )
    source_type = overrides.get("source_type", "course_material" if language == "en" else "textbook")
    trust_level = overrides.get("trust_level", "teacher_verified" if language == "en" else "reference_material")
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        title=overrides.get("title", f"{term} governed source"),
        name=overrides.get("title", f"{term} governed source"),
        source_title=overrides.get("title", f"{term} governed source"),
        course=course,
        chapter=chapter,
        language=language,
        source_type=source_type,
        source_role=source_role,
        visibility=overrides.get("visibility", "course"),
        trust_level=overrides.get("source_trust_level", trust_level),
        quality_status=overrides.get("source_quality_status", quality_status),
        quality_flags=overrides.get("source_quality_flags", [quality_status] if quality_status else []),
        status=overrides.get("source_status", "active"),
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    chunk_text = text or f"{term} is described in governed bilingual evidence."
    chunk = app_module.KnowledgeChunk(
        chunk_uid=overrides.get("chunk_uid", f"chunk-{uuid.uuid4().hex}"),
        source_uid=source.source_uid,
        knowledge_source_id=source.id,
        document_id=0,
        course=course,
        chapter=chapter,
        language=language,
        content=chunk_text,
        normalized_text=" ".join(chunk_text.split()),
        source_locator=overrides.get("source_locator", "page:2"),
        page_number=overrides.get("page_number", 2),
        quality_status=quality_status,
        quality_flags=overrides.get("quality_flags", [quality_status] if quality_status else []),
        trust_level=trust_level,
        visibility=overrides.get("visibility", "course"),
        status=overrides.get("chunk_status", "active"),
        parse_uid=overrides.get("parse_uid", f"parse-{uuid.uuid4().hex}"),
        parse_block_uid=overrides.get("parse_block_uid", f"block-{uuid.uuid4().hex}"),
    )
    app_module.db.session.add(chunk)
    app_module.db.session.commit()
    return source, chunk


def retrieve_workflow(app_module, english_term, chinese_term="", **kwargs):
    return bilingual_evidence_workflow.retrieve_bilingual_evidence(
        app_module.db.session,
        app_module.KnowledgeChunk,
        app_module.KnowledgeSource,
        english_term,
        chinese_term=chinese_term,
        **kwargs,
    )


def test_bilingual_workflow_retrieves_english_and_chinese_evidence(app_module):
    with app_module.app.app_context():
        english_term = unique_token("Fourier")
        chinese_term = f"傅里叶{uuid.uuid4().hex[:6]}"
        _, english_chunk = create_governed_chunk(
            app_module,
            term=english_term,
            course="Bilingual Signals",
            chapter="Frequency",
            language="en",
            source_role="english_course_material",
            source_type="course_material",
            text=f"{english_term} maps signals into frequency components.",
        )
        _, chinese_chunk = create_governed_chunk(
            app_module,
            term=chinese_term,
            course="Bilingual Signals",
            chapter="Frequency",
            language="zh",
            source_role="chinese_reference_material",
            source_type="textbook",
            text=f"{chinese_term} 用于描述信号的频域表示。",
        )

        result = retrieve_workflow(
            app_module,
            english_term,
            chinese_term,
            course="Bilingual Signals",
            chapter="Frequency",
            limit=5,
        )

        assert result.english_evidence_candidates[0]["chunk_uid"] == english_chunk.chunk_uid
        assert result.chinese_evidence_candidates[0]["chunk_uid"] == chinese_chunk.chunk_uid
        assert result.draft_payload["english_evidence"][0]["chunk_uid"] == english_chunk.chunk_uid
        assert result.draft_payload["chinese_evidence"][0]["chunk_uid"] == chinese_chunk.chunk_uid
        assert result.draft_payload["status"] == "needs_review"
        assert result.draft_payload["confidence_score"] is None
        assert result.draft_payload["alignment_reason"] == ""
        assert result.draft_payload["model_name"] is None
        assert result.draft_payload["prompt_version"] is None
        assert result.draft_payload["retrieval_version"] == bilingual_evidence_workflow.BILINGUAL_RETRIEVAL_VERSION
        assert "bilingual_alignment_not_verified" in result.risk_labels


def test_bilingual_workflow_course_and_chapter_filters_apply(app_module):
    with app_module.app.app_context():
        english_term = unique_token("CourseFilter")
        chinese_term = f"课程过滤{uuid.uuid4().hex[:6]}"
        _, expected_english = create_governed_chunk(
            app_module,
            term=english_term,
            course="Expected Course",
            chapter="Expected Chapter",
            language="en",
            text=f"{english_term} expected course evidence.",
        )
        _, expected_chinese = create_governed_chunk(
            app_module,
            term=chinese_term,
            course="Expected Course",
            chapter="Expected Chapter",
            language="zh",
            text=f"{chinese_term} 是目标章节证据。",
        )
        create_governed_chunk(app_module, term=english_term, course="Other Course", chapter="Expected Chapter", language="en")
        create_governed_chunk(app_module, term=chinese_term, course="Expected Course", chapter="Other Chapter", language="zh")

        result = retrieve_workflow(
            app_module,
            english_term,
            chinese_term,
            course="Expected Course",
            chapter="Expected Chapter",
            limit=10,
        )

        assert [item["chunk_uid"] for item in result.english_evidence_candidates] == [expected_english.chunk_uid]
        assert [item["chunk_uid"] for item in result.chinese_evidence_candidates] == [expected_chinese.chunk_uid]


def test_bilingual_workflow_missing_evidence_and_chinese_term_risks(app_module):
    with app_module.app.app_context():
        english_term = unique_token("MissingEnglish")

        result = retrieve_workflow(
            app_module,
            english_term,
            chinese_term="不存在中文证据",
            course="No Evidence Course",
            chapter="No Evidence Chapter",
            limit=5,
        )
        english_only = retrieve_workflow(
            app_module,
            english_term,
            chinese_term="",
            course="No Evidence Course",
            chapter="No Evidence Chapter",
            limit=5,
        )

        assert result.english_evidence_candidates == []
        assert result.chinese_evidence_candidates == []
        assert {"no_english_evidence", "no_chinese_evidence", "cross_language_evidence_missing"} <= set(result.risk_labels)
        assert english_only.chinese_term == ""
        assert "missing_chinese_term" in english_only.risk_labels
        assert "cross_language_evidence_missing" in english_only.risk_labels
        assert english_only.draft_payload["status"] == "needs_review"


def test_bilingual_workflow_low_quality_is_excluded_by_default(app_module):
    with app_module.app.app_context():
        english_term = unique_token("LowQuality")
        chinese_term = f"低质量{uuid.uuid4().hex[:6]}"
        create_governed_chunk(
            app_module,
            term=english_term,
            language="en",
            trust_level="low_quality",
            source_trust_level="low_quality",
            text=f"{english_term} low quality English evidence.",
        )
        create_governed_chunk(
            app_module,
            term=chinese_term,
            language="zh",
            trust_level="low_quality",
            source_trust_level="low_quality",
            text=f"{chinese_term} 低质量中文证据。",
        )

        result = retrieve_workflow(app_module, english_term, chinese_term, limit=5)

        assert result.english_evidence_candidates == []
        assert result.chinese_evidence_candidates == []
        assert "no_english_evidence" in result.risk_labels
        assert "no_chinese_evidence" in result.risk_labels


def test_bilingual_workflow_partial_text_requires_include_flag_and_adds_risks(app_module):
    with app_module.app.app_context():
        english_term = unique_token("PartialEvidence")
        chinese_term = f"部分文本{uuid.uuid4().hex[:6]}"
        _, english_chunk = create_governed_chunk(
            app_module,
            term=english_term,
            language="en",
            quality_status="partial_text",
            chunk_status="needs_review",
            source_status="needs_review",
            trust_level="teacher_verified",
            source_trust_level="teacher_verified",
            text=f"{english_term} partial English evidence.",
        )
        _, chinese_chunk = create_governed_chunk(
            app_module,
            term=chinese_term,
            language="zh",
            quality_status="partial_text",
            chunk_status="needs_review",
            source_status="needs_review",
            trust_level="reference_material",
            source_trust_level="reference_material",
            text=f"{chinese_term} 部分解析中文证据。",
        )

        default_result = retrieve_workflow(app_module, english_term, chinese_term, limit=5)
        review_result = retrieve_workflow(
            app_module,
            english_term,
            chinese_term,
            limit=5,
            filters={"include_needs_review": True},
        )

        assert default_result.english_evidence_candidates == []
        assert default_result.chinese_evidence_candidates == []
        assert review_result.english_evidence_candidates[0]["chunk_uid"] == english_chunk.chunk_uid
        assert review_result.chinese_evidence_candidates[0]["chunk_uid"] == chinese_chunk.chunk_uid
        assert "evidence_from_partial_text" in review_result.risk_labels
        assert "evidence_from_needs_review_source" in review_result.risk_labels


def test_bilingual_workflow_does_not_fabricate_alignment_fields(app_module):
    with app_module.app.app_context():
        english_term = unique_token("DraftSafety")
        create_governed_chunk(app_module, term=english_term, language="en")

        result = retrieve_workflow(app_module, english_term, chinese_term="", limit=5)
        draft = result.draft_payload

        assert draft["status"] != "approved"
        assert draft["confidence_score"] is None
        assert draft["alignment_reason"] == ""
        assert draft["model_name"] is None
        assert draft["prompt_version"] is None
        assert "bilingual_alignment_not_verified" in draft["risk_labels"]


def test_bilingual_evidence_api_success_and_audit(client, app_module, teacher_token):
    request_id = "bilingual-api-success"
    with app_module.app.app_context():
        english_term = unique_token("ApiEnglish")
        chinese_term = f"接口中文{uuid.uuid4().hex[:6]}"
        _, english_chunk = create_governed_chunk(
            app_module,
            term=english_term,
            course="API Bilingual Course",
            chapter="API Chapter",
            language="en",
            text=f"Sensitive English full chunk text should stay out of audit. {english_term}",
        )
        _, chinese_chunk = create_governed_chunk(
            app_module,
            term=chinese_term,
            course="API Bilingual Course",
            chapter="API Chapter",
            language="zh",
            text=f"敏感中文完整块内容不应进入审计。{chinese_term}",
        )
        english_uid = english_chunk.chunk_uid
        chinese_uid = chinese_chunk.chunk_uid

    response = client.post(
        "/api/evidence/bilingual",
        json={
            "english_term": english_term,
            "chinese_term": chinese_term,
            "course": "API Bilingual Course",
            "chapter": "API Chapter",
            "limit": 5,
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["request_id"] == request_id
    data = payload["data"]
    assert data["english_evidence_candidates"][0]["chunk_uid"] == english_uid
    assert data["chinese_evidence_candidates"][0]["chunk_uid"] == chinese_uid
    assert data["draft_payload"]["status"] == "needs_review"
    assert data["draft_payload"]["confidence_score"] is None
    with app_module.app.app_context():
        completed = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="bilingual_evidence_retrieval_completed",
        ).first()
        draft_audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="concept_card_draft_payload_created",
        ).first()
        assert completed is not None
        assert draft_audit is not None
        serialized = audit_records.serialize_audit_record(completed)
        assert serialized["output_payload"]["english_result_count"] == 1
        assert english_uid in serialized["output_payload"]["top_english_chunk_uids"]
        assert "Sensitive English full chunk text" not in str(serialized["output_payload"])
        assert "Authorization" not in str(serialized["input_payload"])


def test_bilingual_evidence_api_missing_english_term_returns_json_and_audit(client, app_module, teacher_token):
    request_id = "bilingual-api-missing-english"
    response = client.post(
        "/api/evidence/bilingual",
        json={"chinese_term": "缺少英文术语"},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["request_id"] == request_id
    assert payload["audit_error_code"] == "missing_english_term"
    with app_module.app.app_context():
        audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="bilingual_evidence_retrieval_failed",
        ).first()
        assert audit is not None
        serialized = audit_records.serialize_audit_record(audit)
        assert serialized["error_code"] == "missing_english_term"


def test_bilingual_evidence_api_allows_missing_chinese_term(client, app_module, teacher_token):
    request_id = "bilingual-api-english-only"
    with app_module.app.app_context():
        english_term = unique_token("EnglishOnly")
        _, chunk = create_governed_chunk(
            app_module,
            term=english_term,
            course="English Only Course",
            chapter="English Only Chapter",
            language="en",
        )
        chunk_uid = chunk.chunk_uid

    response = client.post(
        "/api/evidence/bilingual",
        json={
            "english_term": english_term,
            "course": "English Only Course",
            "chapter": "English Only Chapter",
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["english_evidence_candidates"][0]["chunk_uid"] == chunk_uid
    assert data["chinese_evidence_candidates"] == []
    assert "missing_chinese_term" in data["risk_labels"]
    assert data["draft_payload"]["chinese_term"] == ""


def test_bilingual_evidence_api_no_results_returns_empty_candidates(client, teacher_token):
    request_id = "bilingual-api-no-results"
    response = client.post(
        "/api/evidence/bilingual",
        json={
            "english_term": unique_token("NoResult"),
            "chinese_term": f"无结果{uuid.uuid4().hex[:6]}",
            "course": "No Result Course",
            "limit": 5,
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["english_evidence_candidates"] == []
    assert data["chinese_evidence_candidates"] == []
    assert {"no_english_evidence", "no_chinese_evidence"} <= set(data["risk_labels"])
