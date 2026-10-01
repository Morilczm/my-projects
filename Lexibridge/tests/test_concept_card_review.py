import json
import uuid
from types import SimpleNamespace

import pytest

from services import audit_records
from services import concept_alignment_cards as concept_cards
from services import concept_card_review
from services import course_review_policy


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_text(prefix="Review"):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def evidence(term="Review Term", score=0.84):
    return [{
        "chunk_uid": f"chunk-{uuid.uuid4().hex}",
        "source_uid": f"src-{uuid.uuid4().hex}",
        "source_title": "Teacher Reviewed Source",
        "course": "Review Workflow Course",
        "chapter": "Quality Control",
        "language": "en",
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "source_locator": "page:12",
        "snippet": f"{term} evidence for review workflow.",
        "score": score,
    }]


def create_source_and_chunk(app_module, *, term, course, chapter="Quality Control", language="en"):
    role = "english_course_material" if language == "en" else "chinese_reference_material"
    source = app_module.KnowledgeSource(
        source_uid=f"src-{uuid.uuid4().hex}",
        title=f"{term} {language.upper()} Source",
        name=f"{term} {language.upper()} Source",
        source_title=f"{term} {language.upper()} Source",
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
        content=f"{term} evidence for review workflow.",
        normalized_text=f"{term} evidence for review workflow.",
        source_locator="page:12",
        page_number=12,
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


def evidence_from_source(source, chunk, *, term, language="en", score=0.84):
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
        "snippet": f"{term} evidence for review workflow.",
        "score": score,
        "parse_uid": chunk.parse_uid,
        "parse_block_uid": chunk.parse_block_uid,
    }]


def reviewer(role="teacher", reviewer_id=42):
    return {"reviewer_id": reviewer_id, "reviewer_role": role, "reviewer_name": f"{role}-reviewer"}


def create_card(app_module, **overrides):
    course = overrides.pop("course", "Review Workflow Course")
    chapter = overrides.pop("chapter", "Quality Control")
    english_term = overrides.pop("english_term", unique_text("Review Term"))
    chinese_term = overrides.pop("chinese_term", f"审核术语{uuid.uuid4().hex[:5]}")
    if "english_evidence" in overrides:
        english_evidence = overrides.pop("english_evidence")
    else:
        en_source, en_chunk = create_source_and_chunk(app_module, term=english_term, course=course, chapter=chapter, language="en")
        english_evidence = evidence_from_source(en_source, en_chunk, term=english_term, language="en")
    if "chinese_evidence" in overrides:
        chinese_evidence = overrides.pop("chinese_evidence")
    else:
        zh_source, zh_chunk = create_source_and_chunk(app_module, term=chinese_term, course=course, chapter=chapter, language="zh")
        chinese_evidence = evidence_from_source(zh_source, zh_chunk, term=chinese_term, language="zh")
    data = {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": course,
        "chapter": chapter,
        "status": "needs_review",
        "risk_labels": [],
        "english_evidence": english_evidence,
        "chinese_evidence": chinese_evidence,
        "confidence_score": None,
    }
    data.update(overrides)
    return concept_cards.create_concept_card(
        app_module.db.session,
        app_module.ConceptAlignmentCard,
        data,
        now_fn=app_module.current_time_text,
    )


def grant_review_access(app_module, course="Review Workflow Course", permission_level="admin", policy_overrides=None):
    teacher = app_module.User.query.filter_by(role="teacher").first()
    policy_data = {
        "course": course,
        "required_evidence_sides": "either",
        "min_required_evidence_count": 1,
        "allow_approve_with_missing_chinese_evidence": True,
        "allow_approve_with_unverified_alignment": True,
        "allow_teacher_override": True,
        "require_admin_for_override": False,
        "override_allowed_risk_labels": [
            "bilingual_alignment_not_verified",
            "candidate_not_alignment_verified",
        ],
        "override_forbidden_risk_labels": ["parse_failed"],
    }
    policy_data.update(policy_overrides or {})
    course_review_policy.create_or_update_course_review_policy(
        app_module.db.session,
        app_module.CourseReviewPolicy,
        course,
        policy_data,
        actor=teacher,
        now_fn=app_module.current_time_text,
    )
    course_review_policy.grant_course_review_permission(
        app_module.db.session,
        app_module.CourseReviewPermission,
        course,
        teacher.id,
        {
            "reviewer_id": teacher.id,
            "reviewer_role": "teacher",
            "permission_level": permission_level,
        },
        actor=teacher,
        now_fn=app_module.current_time_text,
    )
    return teacher


def with_expected_version(app_module, card_uid, payload):
    with app_module.app.app_context():
        card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card_uid).one()
        return {**payload, "expected_version": card.version}


def test_review_record_model_and_json_fields(app_module):
    with app_module.app.app_context():
        card = create_card(app_module, risk_labels=["bilingual_alignment_not_verified"])
        record = concept_card_review.create_review_record(
            app_module.db.session,
            app_module.ConceptCardReviewRecord,
            card,
            "request_revision",
            reviewer(),
            {
                "reason_code": "evidence_insufficient",
                "required_changes": ["Add Chinese textbook evidence"],
                "resolved_risk_labels": ["bilingual_alignment_not_verified"],
                "request_id": "review-record-json",
            },
            previous_status="needs_review",
            new_status="needs_review",
            now_fn=app_module.current_time_text,
        )
        assignment = app_module.ConceptCardReviewAssignment(
            card_uid=card.card_uid,
            assigned_to="teacher_001",
            assigned_by=1,
            assignment_status="active",
        )
        app_module.db.session.add(assignment)
        app_module.db.session.commit()
        serialized = concept_card_review.serialize_review_record(record)

        assert serialized["review_uid"]
        assert serialized["required_changes"] == ["Add Chinese textbook evidence"]
        assert serialized["resolved_risk_labels"] == ["bilingual_alignment_not_verified"]
        assert assignment.assignment_uid


def test_review_queue_defaults_to_draft_and_needs_review(app_module):
    course = unique_text("Queue Course")
    with app_module.app.app_context():
        draft = create_card(app_module, course=course, status="draft")
        needs_review = create_card(app_module, course=course, status="needs_review")
        approved = create_card(app_module, course=course, status="needs_review")
        deprecated = create_card(app_module, course=course, status="needs_review")
        approved.status = "approved"
        approved.reviewed_by = 42
        deprecated.status = "deprecated"
        app_module.db.session.commit()

        result = concept_card_review.get_review_queue(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            {"course": course, "per_page": 20},
        )

        uids = {card.card_uid for card in result.items}
        assert draft.card_uid in uids
        assert needs_review.card_uid in uids
        assert approved.card_uid not in uids
        assert deprecated.card_uid not in uids


def test_approve_quality_gates_and_override(app_module):
    with app_module.app.app_context():
        no_chinese = create_card(app_module, chinese_term="")
        no_evidence = create_card(app_module, english_evidence=[], chinese_evidence=[])
        risky = create_card(
            app_module,
            risk_labels=["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
            confidence_score=None,
        )

        with pytest.raises(concept_card_review.ConceptCardReviewError, match="chinese_term"):
            concept_card_review.approve_concept_card(
                app_module.db.session,
                app_module.ConceptAlignmentCard,
                app_module.ConceptCardReviewRecord,
                no_chinese.card_uid,
                reviewer(),
                {"reason_code": "teacher_verified"},
            )
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="evidence"):
            concept_card_review.approve_concept_card(
                app_module.db.session,
                app_module.ConceptAlignmentCard,
                app_module.ConceptCardReviewRecord,
                no_evidence.card_uid,
                reviewer(),
                {"reason_code": "teacher_verified"},
            )
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="unresolved risk"):
            concept_card_review.approve_concept_card(
                app_module.db.session,
                app_module.ConceptAlignmentCard,
                app_module.ConceptCardReviewRecord,
                risky.card_uid,
                reviewer(),
                {"reason_code": "teacher_verified"},
            )

        card, review = concept_card_review.approve_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.ConceptCardReviewRecord,
            risky.card_uid,
            reviewer(),
            {
                "reason_code": "teacher_verified",
                "review_comment": "Teacher verified against course materials.",
                "allow_risk_override": True,
                "override_reason": "Teacher manually verified the bilingual concept.",
                "resolved_risk_labels": ["bilingual_alignment_not_verified"],
            },
            audit_model=app_module.AuditRecord,
            audit_context={"request_id": "approve-override", "source": "api"},
            now_fn=app_module.current_time_text,
        )
        serialized = concept_cards.serialize_concept_card(card)
        review_data = concept_card_review.serialize_review_record(review)

        assert serialized["status"] == "approved"
        assert serialized["confidence_score"] is None
        assert "bilingual_alignment_not_verified" in serialized["risk_labels"]
        assert review_data["risk_assessment"]["risk_override_used"] is True
        with app_module.app.app_context():
            override_audit = app_module.AuditRecord.query.filter_by(
                request_id="approve-override",
                event_type="concept_card_risk_override_used",
            ).first()
            assert override_audit is not None


def test_reject_revision_more_evidence_reopen_and_deprecate(app_module):
    with app_module.app.app_context():
        rejected_card = create_card(app_module)
        revised_card = create_card(app_module)
        evidence_card = create_card(app_module)
        approved_card = create_card(app_module)
        deprecated_card = create_card(app_module)

        rejected, reject_review = concept_card_review.reject_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.ConceptCardReviewRecord,
            rejected_card.card_uid,
            reviewer(),
            {"reason_code": "chinese_term_wrong", "review_comment": "Wrong Chinese term."},
            now_fn=app_module.current_time_text,
        )
        revised, revision_review = concept_card_review.request_card_revision(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.ConceptCardReviewRecord,
            revised_card.card_uid,
            reviewer(),
            {"reason_code": "evidence_insufficient", "required_changes": ["Add Chinese evidence"]},
            now_fn=app_module.current_time_text,
        )
        more_evidence, more_review = concept_card_review.mark_card_needs_more_evidence(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.ConceptCardReviewRecord,
            evidence_card.card_uid,
            reviewer(),
            {"reason_code": "evidence_insufficient", "review_comment": "More evidence required."},
            now_fn=app_module.current_time_text,
        )
        approved_card.status = "approved"
        approved_card.reviewed_by = 42
        deprecated_card.status = "deprecated"
        deprecated_card.reviewed_by = 42
        app_module.db.session.commit()
        reopened, reopen_review = concept_card_review.reopen_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.ConceptCardReviewRecord,
            approved_card.card_uid,
            reviewer(),
            {"reason_code": "course_context_mismatch", "review_comment": "Recheck course context."},
            now_fn=app_module.current_time_text,
        )

        assert rejected.status == "rejected"
        assert concept_card_review.serialize_review_record(reject_review)["decision"] == "rejected"
        assert revised.status == "needs_review"
        assert concept_card_review.serialize_review_record(revision_review)["required_changes"] == ["Add Chinese evidence"]
        assert more_evidence.status == "needs_review"
        assert "insufficient_evidence" in concept_cards.serialize_concept_card(more_evidence)["risk_labels"]
        assert concept_card_review.serialize_review_record(more_review)["decision"] == "insufficient_evidence"
        assert reopened.status == "needs_review"
        assert concept_card_review.serialize_review_record(reopen_review)["action"] == "reopen"
        with pytest.raises(concept_card_review.ConceptCardReviewError, match="deprecated"):
            concept_card_review.approve_concept_card(
                app_module.db.session,
                app_module.ConceptAlignmentCard,
                app_module.ConceptCardReviewRecord,
                deprecated_card.card_uid,
                reviewer(),
                {"reason_code": "teacher_verified"},
            )


def test_review_history_and_assignment_service(app_module):
    with app_module.app.app_context():
        card = create_card(app_module)
        assigned_card, record, assignment = concept_card_review.assign_card_reviewer(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            app_module.ConceptCardReviewRecord,
            app_module.ConceptCardReviewAssignment,
            card.card_uid,
            reviewer(),
            {"assigned_to": "teacher_001", "due_at": "2026-07-20T00:00:00"},
            audit_model=app_module.AuditRecord,
            audit_context={"request_id": "assign-reviewer", "source": "api"},
            now_fn=app_module.current_time_text,
        )
        history = concept_card_review.get_card_review_history(
            app_module.db.session,
            app_module.ConceptCardReviewRecord,
            card.card_uid,
            {"per_page": 10},
        )

        assert assigned_card.card_uid == card.card_uid
        assert concept_card_review.serialize_assignment(assignment)["assigned_to"] == "teacher_001"
        assert concept_card_review.serialize_review_record(record)["action"] == "assign_reviewer"
        assert history.total >= 1


def test_review_service_role_restrictions(app_module):
    with app_module.app.app_context():
        card = create_card(app_module)
        validated = concept_card_review.validate_review_action(
            card,
            "add_review_note",
            {"review_comment": "Reviewer role remains governed by course permission."},
            reviewer(role="reviewer"),
        )
        assert validated["reviewer_role"] == "reviewer"

        with pytest.raises(concept_card_review.ConceptCardReviewError, match="authorized reviewer"):
            concept_card_review.approve_concept_card(
                app_module.db.session,
                app_module.ConceptAlignmentCard,
                app_module.ConceptCardReviewRecord,
                card.card_uid,
                reviewer(role="student"),
                {"reason_code": "teacher_verified"},
            )


def test_review_api_queue_history_and_actions(client, app_module, teacher_token):
    request_id = f"review-api-{uuid.uuid4().hex[:6]}"
    with app_module.app.app_context():
        grant_review_access(app_module)
        card = create_card(
            app_module,
            risk_labels=["bilingual_alignment_not_verified"],
            english_term=unique_text("API Review"),
        )
        card_uid = card.card_uid

    queue = client.get(
        "/api/concept-cards/review-queue?course=Review%20Workflow%20Course&per_page=50",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-queue"},
    )
    blocked = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json=with_expected_version(app_module, card_uid, {"action": "approve", "reason_code": "teacher_verified"}),
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-blocked"},
    )
    approved = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json=with_expected_version(app_module, card_uid, {
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Teacher verified manually.",
            "allow_risk_override": True,
            "override_reason": "Teacher verified against course materials.",
            "resolved_risk_labels": ["bilingual_alignment_not_verified"],
        }),
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )
    history = client.get(
        f"/api/concept-cards/{card_uid}/reviews",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-history"},
    )

    assert queue.status_code == 200
    queue_item = next(item for item in queue.get_json()["data"]["items"] if item["card_uid"] == card_uid)
    assert {"card_uid", "english_term", "chinese_term", "course", "chapter", "status", "risk_labels"} <= set(queue_item)
    assert "evidence_summary" in queue_item
    assert "latest_review_summary" in queue_item
    assert "assignment_summary" in queue_item
    assert "verification_summary" in queue_item
    assert blocked.status_code == 400
    assert blocked.get_json()["request_id"] == f"{request_id}-blocked"
    assert approved.status_code == 200, approved.get_data(as_text=True)
    approved_data = approved.get_json()["data"]
    assert approved.get_json()["request_id"] == request_id
    assert approved_data["card"]["status"] == "approved"
    assert approved_data["card"]["confidence_score"] is None
    assert approved_data["review"]["action"] == "approve"
    assert history.status_code == 200
    assert history.get_json()["data"]["items"][0]["card_uid"] == card_uid
    with app_module.app.app_context():
        approved_audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="concept_card_approved",
        ).first()
        review_created = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="concept_card_review_record_created",
        ).first()
        assert approved_audit is not None
        assert review_created is not None
        dump = json.dumps(audit_records.serialize_audit_record(approved_audit), ensure_ascii=False)
        assert "Authorization" not in dump
        assert "Cookie" not in dump


def test_review_api_reject_revision_more_evidence_assign_and_errors(client, app_module, teacher_token):
    with app_module.app.app_context():
        grant_review_access(app_module)
        reject_card = create_card(app_module)
        revision_card = create_card(app_module)
        evidence_card = create_card(app_module)
        assign_card = create_card(app_module)
        reject_uid = reject_card.card_uid
        revision_uid = revision_card.card_uid
        evidence_uid = evidence_card.card_uid
        assign_uid = assign_card.card_uid
        missing_uid = f"missing-{uuid.uuid4().hex}"

    rejected = client.post(
        f"/api/concept-cards/{reject_uid}/review",
        json=with_expected_version(app_module, reject_uid, {"action": "reject", "reason_code": "chinese_term_wrong", "review_comment": "Wrong term."}),
        headers=bearer(teacher_token),
    )
    revision = client.post(
        f"/api/concept-cards/{revision_uid}/review",
        json=with_expected_version(app_module, revision_uid, {"action": "request_revision", "required_changes": ["Add Chinese evidence"]}),
        headers=bearer(teacher_token),
    )
    more_evidence = client.post(
        f"/api/concept-cards/{evidence_uid}/review",
        json=with_expected_version(app_module, evidence_uid, {"action": "mark_needs_more_evidence", "reason_code": "evidence_insufficient", "review_comment": "More evidence."}),
        headers=bearer(teacher_token),
    )
    assigned = client.post(
        f"/api/concept-cards/{assign_uid}/assign-reviewer",
        json={"assigned_to": "teacher_001"},
        headers=bearer(teacher_token),
    )
    missing = client.post(
        f"/api/concept-cards/{missing_uid}/review",
        json={"action": "reject", "reason_code": "other", "review_comment": "Missing."},
        headers=bearer(teacher_token),
    )
    invalid = client.post(
        f"/api/concept-cards/{assign_uid}/review",
        json=with_expected_version(app_module, assign_uid, {"action": "not_real"}),
        headers=bearer(teacher_token),
    )

    assert rejected.status_code == 200
    assert rejected.get_json()["data"]["card"]["status"] == "rejected"
    assert revision.status_code == 200
    assert revision.get_json()["data"]["review"]["required_changes"] == ["Add Chinese evidence"]
    assert more_evidence.status_code == 200
    assert "insufficient_evidence" in more_evidence.get_json()["data"]["card"]["risk_labels"]
    assert assigned.status_code == 200
    assert assigned.get_json()["data"]["assignment"]["assigned_to"] == "teacher_001"
    assert missing.status_code == 404
    assert invalid.status_code == 400


def test_review_api_permission_checks(client, app_module, teacher_token, student_token):
    with app_module.app.app_context():
        grant_review_access(app_module)
        card = create_card(app_module)
        card_uid = card.card_uid

    student = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json={"action": "approve", "reason_code": "teacher_verified"},
        headers=bearer(student_token),
    )
    student_queue = client.get(
        "/api/concept-cards/review-queue",
        headers=bearer(student_token),
    )
    student_history = client.get(
        f"/api/concept-cards/{card_uid}/reviews",
        headers=bearer(student_token),
    )
    anonymous = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json={"action": "approve", "reason_code": "teacher_verified"},
    )
    teacher = client.post(
        f"/api/concept-cards/{card_uid}/review",
        json=with_expected_version(app_module, card_uid, {"action": "approve", "reason_code": "teacher_verified", "review_comment": "Approved."}),
        headers=bearer(teacher_token),
    )

    assert student.status_code == 403
    assert student_queue.status_code == 403
    assert student_history.status_code == 403
    assert anonymous.status_code == 401
    assert teacher.status_code == 200, teacher.get_data(as_text=True)
