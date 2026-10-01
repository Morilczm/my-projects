import json
import uuid

import pytest
from sqlalchemy.exc import IntegrityError


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_text(prefix="Student Concept"):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def evidence(term, language="en", score=0.87):
    return [{
        "chunk_uid": f"chunk-{uuid.uuid4().hex}",
        "source_uid": f"src-{uuid.uuid4().hex}",
        "source_title": f"{term} Source",
        "course": "Student Concept Course",
        "chapter": "Approved Cards",
        "language": language,
        "source_role": "english_course_material" if language == "en" else "chinese_reference_material",
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "source_locator": "page:8",
        "snippet": f"{term} evidence snippet for student learning.",
        "score": score,
        "retrieval_reason": "lexical_match",
        "risk_labels": [],
        "parse_uid": f"parse-{uuid.uuid4().hex}",
        "parse_block_uid": f"block-{uuid.uuid4().hex}",
    }]


def source_and_chunk(app_module, *, term, course, chapter="Approved Cards", language="en", score=0.87):
    role = "english_course_material" if language == "en" else "chinese_reference_material"
    source = app_module.KnowledgeSource(
        source_uid=f"src-{uuid.uuid4().hex}",
        title=f"{term} Source",
        name=f"{term} Source",
        source_title=f"{term} Source",
        course=course,
        chapter=chapter,
        language=language,
        source_role=role,
        trust_level="teacher_verified",
        quality_status="native_text_ok",
        status="active",
        allow_derivative_cards=True,
        authorization_status="allowed_for_course_use",
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(source)
    app_module.db.session.flush()
    chunk = app_module.KnowledgeChunk(
        chunk_uid=f"chunk-{uuid.uuid4().hex}",
        source_uid=source.source_uid,
        document_id=0,
        source_id=source.id,
        knowledge_source_id=source.id,
        parse_uid=f"parse-{uuid.uuid4().hex}",
        parse_block_uid=f"block-{uuid.uuid4().hex}",
        course=course,
        chapter=chapter,
        title=source.title,
        language=language,
        content=f"{term} evidence snippet for student learning.",
        normalized_text=f"{term} evidence snippet for student learning.",
        source_locator="page:8",
        page_number=8,
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
    return source, chunk, [{
        "chunk_uid": chunk.chunk_uid,
        "source_uid": source.source_uid,
        "source_title": source.title,
        "course": course,
        "chapter": chapter,
        "language": language,
        "source_role": role,
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "source_locator": chunk.source_locator,
        "snippet": chunk.content,
        "score": score,
        "retrieval_reason": "lexical_match",
        "risk_labels": [],
        "parse_uid": chunk.parse_uid,
        "parse_block_uid": chunk.parse_block_uid,
    }]


def create_concept_card(app_module, *, status="approved", course=None, chapter="Approved Cards", **overrides):
    english_term = overrides.pop("english_term", unique_text("Fourier"))
    chinese_term = overrides.pop("chinese_term", f"学生概念{uuid.uuid4().hex[:5]}")
    course = course or unique_text("Student Concept Course")
    if "english_evidence" in overrides:
        english_evidence = overrides.pop("english_evidence")
    else:
        _, _, english_evidence = source_and_chunk(app_module, term=english_term, course=course, chapter=chapter, language="en")
    if "chinese_evidence" in overrides:
        chinese_evidence = overrides.pop("chinese_evidence")
    else:
        _, _, chinese_evidence = source_and_chunk(app_module, term=chinese_term, course=course, chapter=chapter, language="zh")
    card = app_module.ConceptAlignmentCard(
        card_uid=overrides.pop("card_uid", f"card-{uuid.uuid4().hex}"),
        english_term=english_term,
        chinese_term=chinese_term,
        course=course,
        chapter=chapter,
        concept_scope=overrides.pop("concept_scope", "Student learning concept scope."),
        english_explanation=overrides.pop("english_explanation", f"{english_term} is explained for students."),
        chinese_explanation=overrides.pop("chinese_explanation", f"{chinese_term} 的学生端解释。"),
        english_evidence=english_evidence,
        chinese_evidence=chinese_evidence,
        risk_labels=overrides.pop("risk_labels", ["teacher_reviewed"]),
        status=status,
        reviewed_by=1,
        reviewed_at=app_module.current_time_text(),
        retrieval_version="lexical-v1",
    )
    for key, value in overrides.items():
        setattr(card, key, value)
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def grant_student_course_access(app_module, course, *, user=None, visibility="enrolled_only", role_in_course="student", status="active"):
    student = user or app_module.User.query.filter_by(role="student").first()
    admin = app_module.User.query.filter_by(role="admin").first()
    app_module.student_course_access_service.create_or_update_course_student_visibility_policy(
        app_module.db.session,
        app_module.CourseStudentVisibilityPolicy,
        course,
        {
            "visibility": visibility,
            "allow_teacher_preview": True,
            "allow_auditor_view": False,
            "allow_cross_course_search": False,
            "status": "active",
        },
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    if visibility != "public":
        app_module.student_course_access_service.add_student_course_membership(
            app_module.db.session,
            app_module.StudentCourseMembership,
            student.id,
            course,
            {
                "role_in_course": role_in_course,
                "status": status,
            },
            actor=admin,
            now_fn=app_module.current_time_text,
        )
    app_module.db.session.commit()


def test_student_concept_card_state_model_unique_constraint(app_module):
    with app_module.app.app_context():
        card = create_concept_card(app_module, course=unique_text("State Course"))
        student = app_module.User.query.filter_by(role="student").first()
        state = app_module.StudentConceptCardState(
            state_uid=f"state-{uuid.uuid4().hex}",
            user_id=student.id,
            card_uid=card.card_uid,
            course=card.course,
            favorited=True,
            mastered=False,
            personal_note="Review this later.",
        )
        app_module.db.session.add(state)
        app_module.db.session.commit()

        assert state.state_uid
        assert state.favorited is True

        duplicate = app_module.StudentConceptCardState(
            state_uid=f"state-{uuid.uuid4().hex}",
            user_id=student.id,
            card_uid=card.card_uid,
            course=card.course,
        )
        app_module.db.session.add(duplicate)
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()


def test_student_concept_cards_list_is_approved_only_and_filterable(app_module, client, student_token):
    course = unique_text("Approved Only Course")
    with app_module.app.app_context():
        approved = create_concept_card(app_module, course=course, english_term="Approved Fourier Transform")
        approved_uid = approved.card_uid
        for status in ["draft", "needs_review", "rejected", "deprecated"]:
            create_concept_card(app_module, status=status, course=course, english_term=f"{status} Hidden Term")
        grant_student_course_access(app_module, course)

    response = client.get(
        f"/api/student/concept-cards?course={course}&q=Fourier",
        headers=bearer(student_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    items = payload["data"]["items"]

    assert payload["request_id"]
    assert payload["data"]["approved_only"] is True
    assert [item["card_uid"] for item in items] == [approved_uid]
    assert items[0]["status"] == "approved"
    assert items[0]["source_summary"]


def test_student_concept_card_detail_blocks_unapproved_and_tracks_view(app_module, client, student_token):
    course = unique_text("Detail Course")
    with app_module.app.app_context():
        approved = create_concept_card(app_module, course=course)
        hidden = create_concept_card(app_module, status="needs_review", course=course)
        approved_uid = approved.card_uid
        hidden_uid = hidden.card_uid
        grant_student_course_access(app_module, course)

    ok_response = client.get(f"/api/student/concept-cards/{approved_uid}", headers=bearer(student_token))
    assert ok_response.status_code == 200
    detail = ok_response.get_json()["data"]["card"]

    assert detail["card_uid"] == approved_uid
    assert detail["status"] == "approved"
    assert detail["english_evidence"][0]["source_title"]
    assert detail["chinese_evidence"][0]["source_title"]
    assert detail["student_state"]["view_count"] == 1
    assert "Teacher reviewed" in detail["public_risk_labels"]

    blocked_response = client.get(f"/api/student/concept-cards/{hidden_uid}", headers=bearer(student_token))
    assert blocked_response.status_code == 404
    assert blocked_response.get_json()["request_id"]


def test_student_state_favorite_mastered_and_filters(app_module, client, student_token):
    course = unique_text("State Filter Course")
    with app_module.app.app_context():
        favorited = create_concept_card(app_module, course=course, english_term="Favorite State Term")
        other = create_concept_card(app_module, course=course, english_term="Other State Term")
        favorited_uid = favorited.card_uid
        other_uid = other.card_uid
        grant_student_course_access(app_module, course)

    state_response = client.post(
        f"/api/student/concept-cards/{favorited_uid}/state",
        json={"favorited": True, "mastered": True, "personal_note": "Need one final review."},
        headers=bearer(student_token),
    )
    assert state_response.status_code == 200
    state_payload = state_response.get_json()
    assert state_payload["request_id"]
    assert state_payload["data"]["state"]["favorited"] is True
    assert state_payload["data"]["state"]["mastered"] is True

    favorite_response = client.get(
        f"/api/student/concept-cards?course={course}&favorited=true",
        headers=bearer(student_token),
    )
    favorite_uids = {item["card_uid"] for item in favorite_response.get_json()["data"]["items"]}
    assert favorited_uid in favorite_uids
    assert other_uid not in favorite_uids

    mastered_response = client.get(
        f"/api/student/concept-cards?course={course}&mastered=true",
        headers=bearer(student_token),
    )
    mastered_uids = {item["card_uid"] for item in mastered_response.get_json()["data"]["items"]}
    assert mastered_uids == {favorited_uid}

    with app_module.app.app_context():
        persisted = app_module.ConceptAlignmentCard.query.filter_by(card_uid=favorited_uid).first()
        assert persisted.status == "approved"


def test_student_feedback_export_and_review_permission_boundaries(app_module, client, student_token):
    course = unique_text("Feedback Export Course")
    with app_module.app.app_context():
        card = create_concept_card(app_module, course=course, english_term="Feedback Export Term")
        card_uid = card.card_uid
        grant_student_course_access(app_module, course)

    feedback_response = client.post(
        f"/api/student/concept-cards/{card_uid}/feedback",
        json={
            "feedback_type": "explanation_unclear",
            "message": "The Chinese explanation needs a clearer course example.",
            "suggested_chinese_term": "反馈建议术语",
        },
        headers=bearer(student_token),
    )
    assert feedback_response.status_code == 200
    feedback_payload = feedback_response.get_json()
    assert feedback_payload["request_id"]
    assert feedback_payload["data"]["feedback"]["feedback_uid"]
    assert feedback_payload["data"]["feedback"]["card_uid"] == card_uid

    with app_module.app.app_context():
        feedback = app_module.Feedback.query.filter_by(
            feedback_source="student_concept_card",
            actual_result=card_uid,
        ).first()
        assert feedback is not None
        assert feedback.status == "submitted"
        assert feedback.card_uid == card_uid
        assert feedback.message == "The Chinese explanation needs a clearer course example."
        assert json.loads(feedback.evidence_comment)["card_uid"] == card_uid
        persisted = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card_uid).first()
        assert persisted.status == "approved"

    client.post(
        f"/api/student/concept-cards/{card_uid}/state",
        json={"favorited": True},
        headers=bearer(student_token),
    )
    export_all = client.get(
        f"/api/student/concept-cards/export?course={course}&format=json",
        headers=bearer(student_token),
    )
    assert export_all.status_code == 200
    assert export_all.get_json()["data"]["items"][0]["english_term"] == "Feedback Export Term"

    export_favorited = client.get(
        f"/api/student/concept-cards/export?course={course}&scope=favorited&format=json",
        headers=bearer(student_token),
    )
    assert len(export_favorited.get_json()["data"]["items"]) == 1

    export_unmastered = client.get(
        f"/api/student/concept-cards/export?course={course}&scope=unmastered&format=json",
        headers=bearer(student_token),
    )
    assert len(export_unmastered.get_json()["data"]["items"]) == 1

    review_response = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json={"action": "approve", "reason_code": "teacher_verified"},
        headers=bearer(student_token),
    )
    assert review_response.status_code == 403
    assert review_response.get_json()["request_id"]


def test_student_concept_card_visibility_blocks_unenrolled_course(app_module, client, student_token):
    visible_course = unique_text("Visible Membership Course")
    hidden_course = unique_text("Hidden Membership Course")
    with app_module.app.app_context():
        visible = create_concept_card(app_module, course=visible_course, english_term="Visible Approved Term")
        hidden = create_concept_card(app_module, course=hidden_course, english_term="Hidden Approved Term")
        grant_student_course_access(app_module, visible_course)
        app_module.student_course_access_service.create_or_update_course_student_visibility_policy(
            app_module.db.session,
            app_module.CourseStudentVisibilityPolicy,
            hidden_course,
            {
                "visibility": "enrolled_only",
                "status": "active",
            },
            actor=app_module.User.query.filter_by(role="admin").first(),
            now_fn=app_module.current_time_text,
        )
        app_module.db.session.commit()
        visible_uid = visible.card_uid
        hidden_uid = hidden.card_uid

    visible_response = client.get(
        f"/api/student/concept-cards?course={visible_course}",
        headers=bearer(student_token),
    )
    hidden_response = client.get(
        f"/api/student/concept-cards?course={hidden_course}",
        headers=bearer(student_token),
    )
    assert visible_response.status_code == 200
    assert [item["card_uid"] for item in visible_response.get_json()["data"]["items"]] == [visible_uid]
    assert hidden_response.status_code == 200
    assert hidden_response.get_json()["data"]["items"] == []

    detail = client.get(f"/api/student/concept-cards/{hidden_uid}", headers=bearer(student_token))
    assert detail.status_code == 404
    assert detail.get_json()["details"]["audit_error_code"] == "student_concept_card_access_denied"

    state = client.post(
        f"/api/student/concept-cards/{hidden_uid}/state",
        json={"favorited": True},
        headers=bearer(student_token),
    )
    feedback = client.post(
        f"/api/student/concept-cards/{hidden_uid}/feedback",
        json={"feedback_type": "other", "message": "Should not be accepted."},
        headers=bearer(student_token),
    )
    assert state.status_code == 404
    assert feedback.status_code == 404

    export_response = client.get("/api/student/concept-cards/export?format=json", headers=bearer(student_token))
    exported_terms = {item["english_term"] for item in export_response.get_json()["data"]["items"]}
    assert "Visible Approved Term" in exported_terms
    assert "Hidden Approved Term" not in exported_terms

    courses_response = client.get("/api/student/courses", headers=bearer(student_token))
    courses = {item["course"] for item in courses_response.get_json()["data"]["items"]}
    assert visible_course in courses
    assert hidden_course not in courses

    with app_module.app.app_context():
        denied_audit = app_module.AuditRecord.query.filter_by(
            event_type="student_concept_card_access_denied",
            target_uid=hidden_uid,
        ).first()
        assert denied_audit is not None
