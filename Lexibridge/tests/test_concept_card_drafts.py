import uuid

from services import audit_records
from services import concept_alignment_cards
from services import concept_card_drafts


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_token(prefix="Draft"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def create_governed_chunk(app_module, *, term, text=None, **overrides):
    source_uid = overrides.get("source_uid") or f"src-{uuid.uuid4().hex}"
    course = overrides.get("course", "Draft Evidence Course")
    chapter = overrides.get("chapter", "Draft Chapter")
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
        title=overrides.get("title", f"{term} source"),
        name=overrides.get("title", f"{term} source"),
        source_title=overrides.get("title", f"{term} source"),
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
    chunk_text = text or f"{term} governed source evidence."
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
        source_locator=overrides.get("source_locator", "page:7"),
        page_number=overrides.get("page_number", 7),
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


def create_draft(app_module, input_data, **kwargs):
    return concept_card_drafts.create_concept_card_draft_from_evidence(
        app_module.db.session,
        card_model=app_module.ConceptAlignmentCard,
        chunk_model=app_module.KnowledgeChunk,
        source_model=app_module.KnowledgeSource,
        input_data=input_data,
        audit_model=app_module.AuditRecord,
        now_fn=app_module.current_time_text,
        **kwargs,
    )


def test_service_creates_concept_card_draft_from_bilingual_evidence(app_module):
    with app_module.app.app_context():
        english_term = unique_token("ServiceEnglish")
        chinese_term = f"服务草稿{uuid.uuid4().hex[:6]}"
        _, english_chunk = create_governed_chunk(
            app_module,
            term=english_term,
            course="Draft Service Course",
            chapter="Draft Service Chapter",
            language="en",
            text=f"{english_term} service English evidence.",
        )
        _, chinese_chunk = create_governed_chunk(
            app_module,
            term=chinese_term,
            course="Draft Service Course",
            chapter="Draft Service Chapter",
            language="zh",
            text=f"{chinese_term} 服务中文证据。",
        )

        result = create_draft(
            app_module,
            {
                "english_term": english_term,
                "chinese_term": chinese_term,
                "course": "Draft Service Course",
                "chapter": "Draft Service Chapter",
                "limit": 5,
            },
        )
        serialized = concept_alignment_cards.serialize_concept_card(result.card)

        assert result.created is True
        assert result.reused is False
        assert serialized["status"] == "needs_review"
        assert serialized["status"] != "approved"
        assert serialized["confidence_score"] is None
        assert serialized["model_name"] in ("", None)
        assert serialized["prompt_version"] in ("", None)
        assert serialized["retrieval_version"] == "lexical-v1"
        assert serialized["english_evidence"][0]["chunk_uid"] == english_chunk.chunk_uid
        assert serialized["chinese_evidence"][0]["chunk_uid"] == chinese_chunk.chunk_uid
        assert "snippet" in serialized["english_evidence"][0]
        assert len(serialized["english_evidence"][0]["snippet"]) <= 306
        assert "bilingual_alignment_not_verified" in serialized["risk_labels"]


def test_service_missing_chinese_evidence_and_term_create_needs_review(app_module):
    with app_module.app.app_context():
        english_term = unique_token("EnglishOnlyDraft")
        create_governed_chunk(
            app_module,
            term=english_term,
            course="English Only Draft Course",
            chapter="English Only Draft Chapter",
            language="en",
        )

        result = create_draft(
            app_module,
            {
                "english_term": english_term,
                "course": "English Only Draft Course",
                "chapter": "English Only Draft Chapter",
                "limit": 5,
            },
        )
        serialized = concept_alignment_cards.serialize_concept_card(result.card)

        assert serialized["status"] == "needs_review"
        assert serialized["chinese_term"] == ""
        assert "missing_chinese_term" in serialized["risk_labels"]
        assert "cross_language_evidence_missing" in serialized["risk_labels"]


def test_service_requested_approved_is_downgraded(app_module):
    with app_module.app.app_context():
        english_term = unique_token("ApprovedRequest")
        create_governed_chunk(app_module, term=english_term, course="Downgrade Course", language="en")

        result = create_draft(
            app_module,
            {
                "english_term": english_term,
                "course": "Downgrade Course",
                "status": "approved",
                "limit": 5,
            },
        )
        serialized = concept_alignment_cards.serialize_concept_card(result.card)

        assert serialized["status"] == "needs_review"
        assert "requested_approved_downgraded" in serialized["risk_labels"]
        assert serialized["confidence_score"] is None


def test_service_reuses_existing_draft_by_default_and_force_create_makes_new_draft(app_module):
    with app_module.app.app_context():
        english_term = unique_token("ReuseDraft")
        chinese_term = f"复用草稿{uuid.uuid4().hex[:6]}"
        create_governed_chunk(app_module, term=english_term, course="Reuse Draft Course", language="en")
        create_governed_chunk(app_module, term=chinese_term, course="Reuse Draft Course", language="zh")
        payload = {
            "english_term": english_term,
            "chinese_term": chinese_term,
            "course": "Reuse Draft Course",
            "limit": 5,
        }

        first = create_draft(app_module, payload)
        reused = create_draft(app_module, payload)
        forced = create_draft(app_module, {**payload, "force_create": True}, force_create=True)

        assert first.created is True
        assert reused.created is False
        assert reused.reused is True
        assert reused.card.card_uid == first.card.card_uid
        assert forced.created is True
        assert forced.card.card_uid != first.card.card_uid
        assert forced.card.status != "approved"


def test_service_missing_english_term_records_failure_audit(app_module):
    with app_module.app.app_context():
        before = app_module.ConceptAlignmentCard.query.count()

        try:
            create_draft(app_module, {"course": "Failure Course"})
        except Exception:
            pass

        assert app_module.ConceptAlignmentCard.query.count() == before
        audit = app_module.AuditRecord.query.filter_by(event_type="concept_card_draft_creation_failed").order_by(app_module.AuditRecord.id.desc()).first()
        assert audit is not None
        serialized = audit_records.serialize_audit_record(audit)
        assert serialized["error_code"] == "concept_card_draft_creation_failed"


def test_api_create_true_creates_card_and_audit(client, app_module, teacher_token):
    request_id = "draft-api-create"
    with app_module.app.app_context():
        english_term = unique_token("ApiDraftEnglish")
        chinese_term = f"接口草稿{uuid.uuid4().hex[:6]}"
        _, english_chunk = create_governed_chunk(
            app_module,
            term=english_term,
            course="API Draft Course",
            chapter="API Draft Chapter",
            language="en",
            text=f"Sensitive draft English text must not enter audit. {english_term}",
        )
        _, chinese_chunk = create_governed_chunk(
            app_module,
            term=chinese_term,
            course="API Draft Course",
            chapter="API Draft Chapter",
            language="zh",
            text=f"敏感草稿中文文本不应进入审计。{chinese_term}",
        )
        english_uid = english_chunk.chunk_uid
        chinese_uid = chinese_chunk.chunk_uid

    response = client.post(
        "/api/concept-cards/draft-from-evidence",
        json={
            "english_term": english_term,
            "chinese_term": chinese_term,
            "course": "API Draft Course",
            "chapter": "API Draft Chapter",
            "limit": 5,
            "create": True,
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert response.get_json()["request_id"] == request_id
    assert data["created"] is True
    assert data["card"]["card_uid"]
    assert data["card"]["status"] == "needs_review"
    assert data["card"]["confidence_score"] is None
    assert data["card"]["english_evidence"][0]["chunk_uid"] == english_uid
    assert data["card"]["chinese_evidence"][0]["chunk_uid"] == chinese_uid
    with app_module.app.app_context():
        audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="concept_card_draft_created",
        ).first()
        payload_audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="concept_card_draft_payload_created",
        ).first()
        assert audit is not None
        assert payload_audit is not None
        serialized = audit_records.serialize_audit_record(audit)
        assert serialized["output_payload"]["created"] is True
        assert english_uid in serialized["output_payload"]["top_english_chunk_uids"]
        assert "Sensitive draft English text" not in str(serialized["output_payload"])
        assert "Authorization" not in str(serialized["input_payload"])


def test_api_create_false_only_returns_payload(client, app_module, teacher_token):
    request_id = "draft-api-create-false"
    with app_module.app.app_context():
        english_term = unique_token("PayloadOnly")
        create_governed_chunk(
            app_module,
            term=english_term,
            course="Payload Only Course",
            language="en",
        )
        before = app_module.ConceptAlignmentCard.query.count()

    response = client.post(
        "/api/concept-cards/draft-from-evidence",
        json={"english_term": english_term, "course": "Payload Only Course", "create": False},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["created"] is False
    assert data["card"] is None
    assert data["draft_payload"]["status"] == "needs_review"
    with app_module.app.app_context():
        assert app_module.ConceptAlignmentCard.query.count() == before
        audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="concept_card_draft_payload_created",
        ).first()
        assert audit is not None


def test_api_missing_english_term_returns_json_error_and_audit(client, app_module, teacher_token):
    request_id = "draft-api-missing-english"
    response = client.post(
        "/api/concept-cards/draft-from-evidence",
        json={"course": "Missing English Course"},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["request_id"] == request_id
    with app_module.app.app_context():
        audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="concept_card_draft_creation_failed",
        ).first()
        assert audit is not None


def test_api_missing_chinese_term_can_create_needs_review_draft(client, teacher_token):
    response = client.post(
        "/api/concept-cards/draft-from-evidence",
        json={
            "english_term": unique_token("NoChineseApi"),
            "course": "No Chinese API Course",
            "create": True,
        },
        headers=bearer(teacher_token),
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    card = response.get_json()["data"]["card"]
    assert card["status"] == "needs_review"
    assert "missing_chinese_term" in card["risk_labels"]
    assert card["confidence_score"] is None


def test_api_requested_approved_does_not_create_approved(client, app_module, teacher_token):
    with app_module.app.app_context():
        english_term = unique_token("ApiApproved")
        create_governed_chunk(app_module, term=english_term, course="API Downgrade Course", language="en")

    response = client.post(
        "/api/concept-cards/draft-from-evidence",
        json={
            "english_term": english_term,
            "course": "API Downgrade Course",
            "status": "approved",
        },
        headers=bearer(teacher_token),
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    card = response.get_json()["data"]["card"]
    assert card["status"] == "needs_review"
    assert card["status"] != "approved"
    assert "requested_approved_downgraded" in card["risk_labels"]


def test_api_duplicate_reuses_existing_draft_and_force_create_creates_new(client, app_module, teacher_token):
    with app_module.app.app_context():
        english_term = unique_token("ApiReuse")
        chinese_term = f"接口复用{uuid.uuid4().hex[:6]}"
        create_governed_chunk(app_module, term=english_term, course="API Reuse Course", language="en")
        create_governed_chunk(app_module, term=chinese_term, course="API Reuse Course", language="zh")
    payload = {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": "API Reuse Course",
    }

    first = client.post("/api/concept-cards/draft-from-evidence", json=payload, headers=bearer(teacher_token))
    second = client.post("/api/concept-cards/draft-from-evidence", json=payload, headers=bearer(teacher_token))
    forced = client.post(
        "/api/concept-cards/draft-from-evidence",
        json={**payload, "force_create": True},
        headers=bearer(teacher_token),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert forced.status_code == 200
    first_card = first.get_json()["data"]["card"]
    second_data = second.get_json()["data"]
    forced_card = forced.get_json()["data"]["card"]
    assert second_data["created"] is False
    assert second_data["reused"] is True
    assert second_data["card"]["card_uid"] == first_card["card_uid"]
    assert forced.get_json()["data"]["created"] is True
    assert forced_card["card_uid"] != first_card["card_uid"]
    assert forced_card["status"] != "approved"
