import uuid

from services import audit_records
from services import chinese_term_candidates
from services import concept_alignment_cards
from services import concept_card_drafts
from services import bilingual_evidence_workflow


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_token(prefix="ChineseCandidate"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def unique_chinese(prefix="候选"):
    return f"{prefix}{uuid.uuid4().hex[:6]}"


def create_governed_chunk(app_module, *, english_term, text, **overrides):
    source_uid = overrides.get("source_uid") or f"src-{uuid.uuid4().hex}"
    course = overrides.get("course", "Candidate Course")
    chapter = overrides.get("chapter", "Candidate Chapter")
    language = overrides.get("language", "mixed")
    quality_status = overrides.get("quality_status", "native_text_ok")
    source = app_module.KnowledgeSource(
        source_uid=source_uid,
        title=overrides.get("title", f"{english_term} bilingual source"),
        name=overrides.get("title", f"{english_term} bilingual source"),
        source_title=overrides.get("title", f"{english_term} bilingual source"),
        course=course,
        chapter=chapter,
        language=language,
        source_type=overrides.get("source_type", "reference"),
        source_role=overrides.get("source_role", "bilingual_reference"),
        visibility=overrides.get("visibility", "course"),
        trust_level=overrides.get("source_trust_level", overrides.get("trust_level", "reference_material")),
        quality_status=overrides.get("source_quality_status", quality_status),
        quality_flags=overrides.get("source_quality_flags", [quality_status] if quality_status else []),
        status=overrides.get("source_status", "active"),
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    chunk = app_module.KnowledgeChunk(
        chunk_uid=overrides.get("chunk_uid", f"chunk-{uuid.uuid4().hex}"),
        source_uid=source.source_uid,
        knowledge_source_id=source.id,
        document_id=0,
        course=course,
        chapter=chapter,
        language=language,
        content=text,
        normalized_text=" ".join(text.split()),
        source_locator=overrides.get("source_locator", "page:9"),
        page_number=overrides.get("page_number", 9),
        block_type=overrides.get("block_type", "text"),
        quality_status=quality_status,
        quality_flags=overrides.get("quality_flags", [quality_status] if quality_status else []),
        trust_level=overrides.get("trust_level", "reference_material"),
        visibility=overrides.get("visibility", "course"),
        status=overrides.get("chunk_status", "active"),
        parse_uid=overrides.get("parse_uid", f"parse-{uuid.uuid4().hex}"),
        parse_block_uid=overrides.get("parse_block_uid", f"block-{uuid.uuid4().hex}"),
    )
    app_module.db.session.add(chunk)
    app_module.db.session.commit()
    return source, chunk


def generate_candidates(app_module, english_term, **kwargs):
    return chinese_term_candidates.generate_chinese_term_candidates(
        app_module.db.session,
        concept_card_model=app_module.ConceptAlignmentCard,
        term_model=app_module.Term,
        terminology_card_model=app_module.TerminologyCard,
        chunk_model=app_module.KnowledgeChunk,
        source_model=app_module.KnowledgeSource,
        english_term=english_term,
        **kwargs,
    )


def test_candidate_service_finds_approved_concept_card(app_module):
    with app_module.app.app_context():
        english_term = unique_token("ApprovedCard")
        chinese_term = unique_chinese("已审卡")
        card = app_module.ConceptAlignmentCard(
            english_term=english_term,
            chinese_term=chinese_term,
            course="Candidate Approved Course",
            chapter="Approved",
            status="approved",
            english_evidence=[{"source": "fixture", "snippet": english_term}],
            risk_labels=[],
        )
        app_module.db.session.add(card)
        app_module.db.session.commit()

        result = generate_candidates(
            app_module,
            english_term,
            course="Candidate Approved Course",
            chapter="Approved",
        )

        assert result.total == 1
        candidate = result.candidates[0]
        assert candidate["chinese_term"] == chinese_term
        assert candidate["source_type"] == "concept_card"
        assert candidate["card_uid"] == card.card_uid
        assert "existing_approved_card_match" in candidate["risk_labels"]
        assert "candidate_not_alignment_verified" in candidate["risk_labels"]
        assert 0 <= candidate["score"] <= 1


def test_candidate_service_finds_legacy_term_and_marks_unverified(app_module):
    with app_module.app.app_context():
        english_term = unique_token("LegacyTerm")
        chinese_term = unique_chinese("旧术语")
        legacy = app_module.Term(
            english_term=english_term,
            chinese_term=chinese_term,
            course="Legacy Candidate Course",
            chapter="Legacy Chapter",
            status="pending",
            courseware_sentence=f"{english_term} appears in an old glossary row.",
        )
        app_module.db.session.add(legacy)
        app_module.db.session.commit()

        result = generate_candidates(
            app_module,
            english_term,
            course="Legacy Candidate Course",
            chapter="Legacy Chapter",
        )

        candidate = result.candidates[0]
        assert candidate["source_type"] == "legacy_term"
        assert candidate["term_id"] == str(legacy.id)
        assert candidate["chinese_term"] == chinese_term
        assert "legacy_unverified_source" in candidate["risk_labels"]
        assert "candidate_not_alignment_verified" in result.risk_labels


def test_candidate_service_extracts_bilingual_chunk_patterns(app_module):
    with app_module.app.app_context():
        english_one = unique_token("PatternOne")
        chinese_one = unique_chinese("括号前")
        english_two = unique_token("PatternTwo")
        chinese_two = unique_chinese("括号后")
        _, chunk_one = create_governed_chunk(
            app_module,
            english_term=english_one,
            course="Pattern Course",
            chapter="Patterns",
            text=f"{chinese_one}（{english_one}）用于描述课程材料中的双语概念。",
        )
        _, chunk_two = create_governed_chunk(
            app_module,
            english_term=english_two,
            course="Pattern Course",
            chapter="Patterns",
            text=f"{english_two}（{chinese_two}）出现在受治理双语知识块中。",
        )

        first = generate_candidates(app_module, english_one, course="Pattern Course", chapter="Patterns")
        second = generate_candidates(app_module, english_two, course="Pattern Course", chapter="Patterns")

        assert first.candidates[0]["chinese_term"] == chinese_one
        assert first.candidates[0]["chunk_uid"] == chunk_one.chunk_uid
        assert "bilingual_pattern_extracted" in first.candidates[0]["risk_labels"]
        assert second.candidates[0]["chinese_term"] == chinese_two
        assert second.candidates[0]["chunk_uid"] == chunk_two.chunk_uid
        assert "bilingual_pattern_extracted" in second.candidates[0]["risk_labels"]


def test_candidate_service_excludes_low_quality_and_failed_parse_chunks(app_module):
    with app_module.app.app_context():
        english_term = unique_token("ExcludedSource")
        create_governed_chunk(
            app_module,
            english_term=english_term,
            text=f"{unique_chinese('低质')}（{english_term}）不应作为候选。",
            trust_level="low_quality",
            source_trust_level="low_quality",
        )
        create_governed_chunk(
            app_module,
            english_term=english_term,
            text=f"{unique_chinese('失败解析')}（{english_term}）不应作为候选。",
            quality_status="parse_failed",
        )
        create_governed_chunk(
            app_module,
            english_term=english_term,
            text=f"{unique_chinese('未配置OCR')}（{english_term}）不应作为候选。",
            quality_status="ocr_unavailable",
        )

        result = generate_candidates(app_module, english_term)

        assert result.candidates == []
        assert "no_chinese_candidate_found" in result.risk_labels


def test_candidate_service_course_chapter_priority_merge_and_ambiguous_risk(app_module):
    with app_module.app.app_context():
        english_term = unique_token("MergeCandidate")
        chinese_shared = unique_chinese("合并候选")
        chinese_other = unique_chinese("歧义候选")
        app_module.db.session.add(app_module.Term(
            english_term=english_term,
            chinese_term=chinese_shared,
            course="Merge Course",
            chapter="Merge Chapter",
            status="pending",
        ))
        create_governed_chunk(
            app_module,
            english_term=english_term,
            course="Merge Course",
            chapter="Merge Chapter",
            text=f"{chinese_shared}（{english_term}）在第二个来源中重复出现。",
        )
        create_governed_chunk(
            app_module,
            english_term=english_term,
            course="Merge Course",
            chapter="Merge Chapter",
            text=f"{chinese_other}（{english_term}）来自同课程的另一个候选。",
        )
        app_module.db.session.commit()

        result = generate_candidates(app_module, english_term, course="Merge Course", chapter="Merge Chapter")

        assert result.total == 2
        shared = next(candidate for candidate in result.candidates if candidate["chinese_term"] == chinese_shared)
        assert shared["source_count"] >= 2
        assert shared["score_breakdown"]["duplicate_sources"] > 0
        assert "ambiguous_chinese_candidates" in result.risk_labels


def test_chinese_candidates_api_success_missing_and_empty_results(client, app_module, teacher_token):
    request_id = f"candidate-api-{uuid.uuid4().hex[:6]}"
    with app_module.app.app_context():
        english_term = unique_token("ApiCandidate")
        chinese_term = unique_chinese("接口候选")
        create_governed_chunk(
            app_module,
            english_term=english_term,
            course="Candidate API Course",
            chapter="Candidate API Chapter",
            text=f"{chinese_term}（{english_term}）来自 API 测试知识块，完整内容不应进入审计。",
        )

    response = client.post(
        "/api/terms/chinese-candidates",
        json={
            "english_term": english_term,
            "course": "Candidate API Course",
            "chapter": "Candidate API Chapter",
            "limit": 99,
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )
    missing = client.post(
        "/api/terms/chinese-candidates",
        json={"course": "Candidate API Course"},
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-missing"},
    )
    empty = client.post(
        "/api/terms/chinese-candidates",
        json={"english_term": unique_token("NoCandidate")},
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-empty"},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    assert payload["request_id"] == request_id
    assert payload["data"]["total"] == 1
    assert payload["data"]["candidates"][0]["chinese_term"] == chinese_term
    assert missing.status_code == 400
    assert missing.get_json()["request_id"] == f"{request_id}-missing"
    assert empty.status_code == 200
    assert empty.get_json()["data"]["candidates"] == []
    assert "no_chinese_candidate_found" in empty.get_json()["data"]["risk_labels"]
    with app_module.app.app_context():
        generated = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="chinese_term_candidates_generated",
        ).first()
        not_found = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-empty",
            event_type="chinese_term_candidates_not_found",
        ).first()
        assert generated is not None
        assert not_found is not None
        serialized = audit_records.serialize_audit_record(generated)
        assert serialized["output_payload"]["candidate_count"] == 1
        assert "完整内容不应进入审计" not in str(serialized["output_payload"])
        assert "Authorization" not in str(serialized["input_payload"])


def test_bilingual_workflow_auto_generates_candidate_and_uses_it_for_chinese_evidence(app_module):
    with app_module.app.app_context():
        english_term = unique_token("AutoWorkflow")
        chinese_term = unique_chinese("自动工作流")
        create_governed_chunk(
            app_module,
            english_term=english_term,
            course="Auto Workflow Course",
            chapter="Auto Chapter",
            language="en",
            source_role="english_course_material",
            source_type="course_material",
            text=f"{english_term} appears as English evidence.",
        )
        create_governed_chunk(
            app_module,
            english_term=english_term,
            course="Auto Workflow Course",
            chapter="Auto Chapter",
            language="mixed",
            source_role="bilingual_reference",
            source_type="reference",
            text=f"{chinese_term}（{english_term}）同时提供候选和中文证据。",
        )

        result = bilingual_evidence_workflow.retrieve_bilingual_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            english_term,
            course="Auto Workflow Course",
            chapter="Auto Chapter",
            auto_generate_chinese_candidates=True,
            concept_card_model=app_module.ConceptAlignmentCard,
            term_model=app_module.Term,
            terminology_card_model=app_module.TerminologyCard,
        )

        assert result.chinese_term == chinese_term
        assert result.selected_chinese_candidate["chinese_term"] == chinese_term
        assert result.chinese_evidence_candidates
        assert result.draft_payload["selected_chinese_candidate"]["chinese_term"] == chinese_term
        assert "candidate_not_alignment_verified" in result.risk_labels
        assert result.draft_payload["confidence_score"] is None
        assert result.draft_payload["alignment_reason"] == ""


def test_bilingual_workflow_auto_candidate_not_found_keeps_missing_chinese_term(app_module):
    with app_module.app.app_context():
        english_term = unique_token("NoAutoCandidate")

        result = bilingual_evidence_workflow.retrieve_bilingual_evidence(
            app_module.db.session,
            app_module.KnowledgeChunk,
            app_module.KnowledgeSource,
            english_term,
            course="No Candidate Course",
            auto_generate_chinese_candidates=True,
            concept_card_model=app_module.ConceptAlignmentCard,
            term_model=app_module.Term,
            terminology_card_model=app_module.TerminologyCard,
        )

        assert result.chinese_term == ""
        assert result.chinese_term_candidates == []
        assert "missing_chinese_term" in result.risk_labels
        assert "no_chinese_candidate_found" in result.risk_labels


def test_draft_from_evidence_auto_candidate_creates_needs_review_card_and_audit(client, app_module, teacher_token):
    request_id = f"draft-auto-candidate-{uuid.uuid4().hex[:6]}"
    with app_module.app.app_context():
        english_term = unique_token("AutoDraft")
        chinese_term = unique_chinese("自动草稿")
        create_governed_chunk(
            app_module,
            english_term=english_term,
            course="Auto Draft Course",
            chapter="Auto Draft Chapter",
            language="en",
            source_role="english_course_material",
            source_type="course_material",
            text=f"{english_term} is the English evidence for auto draft.",
        )
        create_governed_chunk(
            app_module,
            english_term=english_term,
            course="Auto Draft Course",
            chapter="Auto Draft Chapter",
            language="mixed",
            source_role="bilingual_reference",
            source_type="reference",
            text=f"{chinese_term}（{english_term}）是自动候选来源。",
        )

    response = client.post(
        "/api/concept-cards/draft-from-evidence",
        json={
            "english_term": english_term,
            "course": "Auto Draft Course",
            "chapter": "Auto Draft Chapter",
            "auto_generate_chinese_candidates": True,
            "create": True,
            "status": "approved",
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    card = data["card"]
    assert card["chinese_term"] == chinese_term
    assert card["status"] == "needs_review"
    assert card["status"] != "approved"
    assert card["confidence_score"] is None
    assert card["model_name"] in ("", None)
    assert card["prompt_version"] in ("", None)
    assert "candidate_not_alignment_verified" in card["risk_labels"]
    assert data["selected_chinese_candidate"]["chinese_term"] == chinese_term
    assert data["draft_payload"]["selected_chinese_candidate"]["chinese_term"] == chinese_term
    assert data["draft_payload"]["chinese_evidence"][0]["evidence_type"] == "selected_chinese_candidate"
    with app_module.app.app_context():
        stored = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card["card_uid"]).first()
        serialized = concept_alignment_cards.serialize_concept_card(stored)
        assert serialized["chinese_evidence"][0]["evidence_type"] == "selected_chinese_candidate"
        selected_audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="chinese_candidate_selected_for_draft",
        ).first()
        created_audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="concept_card_draft_created",
        ).first()
        assert selected_audit is not None
        assert created_audit is not None


def test_draft_service_auto_candidate_with_force_create_still_not_approved(app_module):
    with app_module.app.app_context():
        english_term = unique_token("ServiceAutoDraft")
        chinese_term = unique_chinese("服务自动")
        create_governed_chunk(
            app_module,
            english_term=english_term,
            course="Service Auto Course",
            language="mixed",
            text=f"{english_term}（{chinese_term}）用于服务层自动候选。",
        )

        result = concept_card_drafts.create_concept_card_draft_from_evidence(
            app_module.db.session,
            card_model=app_module.ConceptAlignmentCard,
            chunk_model=app_module.KnowledgeChunk,
            source_model=app_module.KnowledgeSource,
            term_model=app_module.Term,
            terminology_card_model=app_module.TerminologyCard,
            input_data={
                "english_term": english_term,
                "course": "Service Auto Course",
                "auto_generate_chinese_candidates": True,
                "status": "approved",
            },
            audit_model=app_module.AuditRecord,
            now_fn=app_module.current_time_text,
        )
        serialized = concept_alignment_cards.serialize_concept_card(result.card)

        assert serialized["status"] == "needs_review"
        assert serialized["confidence_score"] is None
        assert serialized["chinese_term"] == chinese_term
        assert result.bilingual_result.selected_chinese_candidate["chinese_term"] == chinese_term
