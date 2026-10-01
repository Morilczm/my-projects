import uuid

from test_concept_card_review import bearer, grant_review_access
from test_student_concept_cards import grant_student_course_access


def _unique(prefix):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def _source_and_chunk(app_module, *, course, language, status="active", page_number=2):
    role = "english_course_material" if language == "en" else "chinese_reference_material"
    source = app_module.KnowledgeSource(
        source_uid=f"source-{language}-{uuid.uuid4().hex}",
        title=f"{language.upper()} Publication Integrity Source",
        name=f"{language.upper()} Publication Integrity Source",
        source_title=f"{language.upper()} Publication Integrity Source",
        course=course,
        chapter="Integrity",
        language=language,
        source_role=role,
        trust_level="teacher_verified",
        quality_status="native_text_ok",
        status=status,
        allow_derivative_cards=True,
        authorization_status="allowed_for_course_use",
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    chunk = app_module.KnowledgeChunk(
        chunk_uid=f"chunk-{language}-{uuid.uuid4().hex}",
        source_uid=source.source_uid,
        document_id=0,
        source_id=source.id,
        knowledge_source_id=source.id,
        parse_uid=f"parse-{language}-{uuid.uuid4().hex}",
        parse_block_uid=f"block-{language}-{uuid.uuid4().hex}",
        course=course,
        chapter="Integrity",
        title=source.title,
        language=language,
        content=(
            "Momentum is the product of mass and velocity."
            if language == "en"
            else "动量是物体质量与速度的乘积。"
        ),
        normalized_text=(
            "Momentum is the product of mass and velocity."
            if language == "en"
            else "动量是物体质量与速度的乘积。"
        ),
        source_locator=f"page:{page_number};paragraph:1",
        page_number=page_number,
        block_type="paragraph",
        quality_status="native_text_ok",
        quality_flags='["native_text_ok"]',
        trust_level="teacher_verified",
        status="active",
        is_active=True,
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(chunk)
    app_module.db.session.flush()
    return source, chunk


def _evidence(source, chunk, *, language):
    return [{
        "chunk_uid": chunk.chunk_uid,
        "source_uid": source.source_uid,
        "source_title": source.title,
        "course": source.course,
        "chapter": source.chapter,
        "language": language,
        "source_role": source.source_role,
        "trust_level": source.trust_level,
        "quality_status": chunk.quality_status,
        "source_locator": chunk.source_locator,
        "snippet": chunk.content,
        "score": 0.91,
        "parse_uid": chunk.parse_uid,
        "parse_block_uid": chunk.parse_block_uid,
    }]


def _card(app_module, *, course, status="needs_review", en_source=None, en_chunk=None, zh_source=None, zh_chunk=None):
    if en_source is None or en_chunk is None:
        en_source, en_chunk = _source_and_chunk(app_module, course=course, language="en")
    if zh_source is None or zh_chunk is None:
        zh_source, zh_chunk = _source_and_chunk(app_module, course=course, language="zh")
    card = app_module.ConceptAlignmentCard(
        card_uid=f"card-{uuid.uuid4().hex}",
        english_term="Momentum",
        chinese_term="动量",
        course=course,
        chapter="Integrity",
        english_explanation="Momentum explanation for publication integrity.",
        chinese_explanation="动量发布一致性说明。",
        english_evidence=_evidence(en_source, en_chunk, language="en"),
        chinese_evidence=_evidence(zh_source, zh_chunk, language="zh"),
        risk_labels=[],
        status=status,
        reviewed_by=1 if status == "approved" else None,
        reviewed_at=app_module.current_time_text() if status == "approved" else "",
        confidence_score=0.88,
        retrieval_version="local-test-v1",
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def test_stale_review_token_blocks_lost_update(client, app_module, teacher_token):
    course = _unique("11D Stale Course")
    with app_module.app.app_context():
        grant_review_access(app_module, course=course, permission_level="admin")
        card = _card(app_module, course=course)
        card_uid = card.card_uid
        stale_version = card.version

    patch = client.patch(
        f"/api/concept-cards/{card_uid}",
        json={
            "expected_version": stale_version,
            "english_explanation": "Teacher B updated this card first.",
        },
        headers={**bearer(teacher_token), "X-Request-ID": "11d-stale-patch"},
    )
    assert patch.status_code == 200, patch.get_data(as_text=True)
    fresh_version = patch.get_json()["data"]["card"]["version"]
    assert fresh_version == stale_version + 1

    stale_approve = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json={
            "action": "approve",
            "expected_version": stale_version,
            "reason_code": "teacher_verified",
            "review_comment": "Old page should not approve.",
        },
        headers={**bearer(teacher_token), "X-Request-ID": "11d-stale-approve"},
    )
    assert stale_approve.status_code == 409, stale_approve.get_data(as_text=True)
    assert stale_approve.get_json()["error_code"] == "CONCEPT_CARD_STALE_REVIEW"

    with app_module.app.app_context():
        stored = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card_uid).one()
        assert stored.status == "needs_review"
        assert stored.version == fresh_version
        assert stored.english_explanation == "Teacher B updated this card first."


def test_review_requires_concurrency_token(client, app_module, teacher_token):
    course = _unique("11D Missing Token Course")
    with app_module.app.app_context():
        grant_review_access(app_module, course=course, permission_level="admin")
        card = _card(app_module, course=course)
        card_uid = card.card_uid

    response = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json={
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Missing expected_version must fail closed.",
        },
        headers={**bearer(teacher_token), "X-Request-ID": "11d-missing-token"},
    )
    assert response.status_code == 409
    assert response.get_json()["error_code"] == "CONCEPT_CARD_STALE_REVIEW"


def test_withdrawn_source_hides_approved_card_and_blocks_feedback(client, app_module, student_token):
    course = _unique("11D Withdraw Published Course")
    with app_module.app.app_context():
        en_source, en_chunk = _source_and_chunk(app_module, course=course, language="en")
        zh_source, zh_chunk = _source_and_chunk(app_module, course=course, language="zh")
        card = _card(
            app_module,
            course=course,
            status="approved",
            en_source=en_source,
            en_chunk=en_chunk,
            zh_source=zh_source,
            zh_chunk=zh_chunk,
        )
        student = app_module.User.query.filter_by(role="student").first()
        grant_student_course_access(app_module, course, user=student)
        card_uid = card.card_uid
        zh_source_uid = zh_source.source_uid

    before = client.get(f"/api/student/concept-cards?course={course}", headers=bearer(student_token))
    assert before.status_code == 200
    assert [item["card_uid"] for item in before.get_json()["data"]["items"]] == [card_uid]

    with app_module.app.app_context():
        source = app_module.KnowledgeSource.query.filter_by(source_uid=zh_source_uid).one()
        source.status = "deprecated"
        source.updated_at = app_module.current_time_text()
        app_module.db.session.commit()

    after = client.get(f"/api/student/concept-cards?course={course}", headers=bearer(student_token))
    assert after.status_code == 200
    assert after.get_json()["data"]["items"] == []

    detail = client.get(f"/api/student/concept-cards/{card_uid}", headers=bearer(student_token))
    assert detail.status_code == 404
    assert detail.get_json()["details"]["audit_error_code"] == "concept_card_source_unavailable"

    feedback = client.post(
        f"/api/student/concept-cards/{card_uid}/feedback",
        json={"feedback_type": "other", "message": "Hidden cards cannot accept feedback."},
        headers=bearer(student_token),
    )
    assert feedback.status_code == 404


def test_withdrawn_source_blocks_approval(client, app_module, teacher_token):
    course = _unique("11D Withdraw Review Course")
    with app_module.app.app_context():
        grant_review_access(app_module, course=course, permission_level="admin")
        en_source, en_chunk = _source_and_chunk(app_module, course=course, language="en")
        zh_source, zh_chunk = _source_and_chunk(app_module, course=course, language="zh", status="deprecated")
        card = _card(app_module, course=course, en_source=en_source, en_chunk=en_chunk, zh_source=zh_source, zh_chunk=zh_chunk)
        card_uid = card.card_uid
        version = card.version

    response = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json={
            "action": "approve",
            "expected_version": version,
            "reason_code": "teacher_verified",
            "review_comment": "Withdrawn Chinese source must block approval.",
        },
        headers={**bearer(teacher_token), "X-Request-ID": "11d-withdraw-approve"},
    )
    assert response.status_code == 422, response.get_data(as_text=True)
    assert response.get_json()["error_code"] == "CONCEPT_CARD_SOURCE_UNAVAILABLE"

    with app_module.app.app_context():
        stored = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card_uid).one()
        assert stored.status == "needs_review"
