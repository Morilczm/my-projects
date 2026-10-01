import json
import uuid

from services import course_review_policy


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_text(prefix):
    return f"{prefix} {uuid.uuid4().hex[:10]}"


def evidence(term, language="en"):
    return [{
        "chunk_uid": f"chunk-{uuid.uuid4().hex}",
        "source_uid": f"src-{uuid.uuid4().hex}",
        "source_title": f"{term} Source",
        "course": "Progress Course",
        "chapter": "Progress Chapter",
        "language": language,
        "source_role": "english_course_material" if language == "en" else "chinese_reference_material",
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "source_locator": "page:8",
        "snippet": f"{term} evidence.",
        "score": 0.88,
    }]


def student_user(app_module):
    return app_module.User.query.filter_by(role="student").first()


def teacher_user(app_module):
    return app_module.User.query.filter_by(role="teacher").first()


def admin_user(app_module):
    return app_module.User.query.filter_by(role="admin").first()


def create_card(app_module, course, *, status="approved", chapter="Progress Chapter", english_term=None):
    english_term = english_term or unique_text("Progress Term")
    chinese_term = f"进度术语{uuid.uuid4().hex[:4]}"
    card = app_module.ConceptAlignmentCard(
        card_uid=f"card-{uuid.uuid4().hex}",
        english_term=english_term,
        chinese_term=chinese_term,
        course=course,
        chapter=chapter,
        concept_scope="Progress and feedback test concept.",
        english_explanation=f"{english_term} explanation.",
        chinese_explanation=f"{chinese_term} 解释。",
        english_evidence=json.dumps(evidence(english_term, "en"), ensure_ascii=False),
        chinese_evidence=json.dumps(evidence(chinese_term, "zh"), ensure_ascii=False),
        risk_labels="[]",
        status=status,
        reviewed_by=1,
        reviewed_at=app_module.current_time_text() if status == "approved" else "",
        retrieval_version="lexical-v1",
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def grant_student_access(app_module, course, *, user=None, visibility="enrolled_only", membership_status="active"):
    student = user or student_user(app_module)
    admin = admin_user(app_module)
    app_module.student_course_access_service.create_or_update_course_student_visibility_policy(
        app_module.db.session,
        app_module.CourseStudentVisibilityPolicy,
        course,
        {"visibility": visibility, "status": "active", "allow_teacher_preview": True},
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    if visibility != "public":
        app_module.student_course_access_service.add_student_course_membership(
            app_module.db.session,
            app_module.StudentCourseMembership,
            student.id,
            course,
            {"role_in_course": "student", "status": membership_status},
            actor=admin,
            now_fn=app_module.current_time_text,
        )
    app_module.db.session.commit()


def grant_teacher_review_access(app_module, course):
    teacher = teacher_user(app_module)
    admin = admin_user(app_module)
    course_review_policy.create_or_update_course_review_policy(
        app_module.db.session,
        app_module.CourseReviewPolicy,
        course,
        {
            "required_evidence_sides": "either",
            "min_required_evidence_count": 1,
            "allow_approve_with_missing_chinese_evidence": True,
            "allow_approve_with_missing_english_evidence": True,
            "allow_approve_with_unverified_alignment": True,
            "allow_teacher_override": True,
            "require_admin_for_override": False,
            "override_allowed_risk_labels": ["bilingual_alignment_not_verified"],
            "override_forbidden_risk_labels": ["parse_failed"],
            "status": "active",
        },
        actor=admin,
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
            "permission_level": "approve",
            "status": "active",
        },
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    app_module.db.session.commit()


def create_state(app_module, card, *, mastered=False, favorited=False, view_count=0):
    student = student_user(app_module)
    state = app_module.StudentConceptCardState(
        state_uid=f"state-{uuid.uuid4().hex}",
        user_id=student.id,
        card_uid=card.card_uid,
        course=card.course,
        favorited=favorited,
        mastered=mastered,
        mastered_at=app_module.current_time_text() if mastered else "",
        last_viewed_at=app_module.current_time_text() if view_count else "",
        view_count=view_count,
    )
    app_module.db.session.add(state)
    app_module.db.session.commit()
    return state


def create_feedback(app_module, card, *, status="submitted", user=None, message="Student feedback message."):
    student = user or student_user(app_module)
    feedback = app_module.Feedback(
        feedback_uid=f"feedback-{uuid.uuid4().hex}",
        term_id=0,
        user_id=student.id,
        user_role=getattr(student, "role", "student"),
        course=card.course,
        chapter=card.chapter,
        card_uid=card.card_uid,
        english_term=card.english_term,
        chinese_term=card.chinese_term,
        feedback_type="concept_explanation_error",
        feedback_source="student_concept_card",
        priority="P2",
        message=message,
        feedback_content=message,
        reported_issue=message,
        actual_result=card.card_uid,
        evidence_comment=json.dumps({"card_uid": card.card_uid}, ensure_ascii=False),
        status=status,
        linked_card_uid=card.card_uid,
        created_at=app_module.current_time_text(),
        updated_at=app_module.current_time_text(),
    )
    app_module.db.session.add(feedback)
    app_module.db.session.commit()
    return feedback


def test_student_progress_counts_only_visible_approved_cards(app_module, client, student_token):
    visible_course = unique_text("Visible Progress")
    hidden_course = unique_text("Hidden Progress")
    with app_module.app.app_context():
        mastered = create_card(app_module, visible_course, english_term="Mastered Visible Term")
        unmastered = create_card(app_module, visible_course, english_term="Unmastered Visible Term")
        create_card(app_module, visible_course, status="needs_review", english_term="Needs Review Hidden")
        hidden = create_card(app_module, hidden_course, english_term="Hidden Approved Progress Term")
        grant_student_access(app_module, visible_course)
        app_module.student_course_access_service.create_or_update_course_student_visibility_policy(
            app_module.db.session,
            app_module.CourseStudentVisibilityPolicy,
            hidden_course,
            {"visibility": "enrolled_only", "status": "active"},
            actor=admin_user(app_module),
            now_fn=app_module.current_time_text,
        )
        create_state(app_module, mastered, mastered=True, favorited=True, view_count=2)
        create_state(app_module, unmastered, mastered=False, favorited=False, view_count=1)
        create_feedback(app_module, mastered)
        hidden_uid = hidden.card_uid

    response = client.get(
        f"/api/student/progress?course={visible_course}&include_recent=true",
        headers={**bearer(student_token), "X-Request-ID": "progress-visible"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.get_json()
    overall = payload["data"]["overall"]

    assert payload["request_id"] == "progress-visible"
    assert overall["visible_card_count"] == 2
    assert overall["mastered_count"] == 1
    assert overall["unmastered_count"] == 1
    assert overall["favorited_count"] == 1
    assert overall["viewed_count"] == 2
    assert overall["feedback_count"] == 1
    assert overall["mastery_rate"] == 0.5
    assert payload["data"]["courses"][0]["course"] == visible_course
    assert payload["data"]["chapters"][0]["chapter"] == "Progress Chapter"
    assert payload["data"]["recent_activity"]

    hidden_response = client.get(
        f"/api/student/progress?course={hidden_course}",
        headers=bearer(student_token),
    )
    assert hidden_response.status_code == 200
    assert hidden_response.get_json()["data"]["overall"]["visible_card_count"] == 0

    with app_module.app.app_context():
        hidden_card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=hidden_uid).first()
        assert hidden_card.status == "approved"


def test_student_progress_audit_recorded(app_module, client, student_token):
    course = unique_text("Progress Audit")
    with app_module.app.app_context():
        create_card(app_module, course)
        grant_student_access(app_module, course)

    response = client.get(
        f"/api/student/progress?course={course}",
        headers={**bearer(student_token), "X-Request-ID": "progress-audit"},
    )
    assert response.status_code == 200
    with app_module.app.app_context():
        audit = app_module.AuditRecord.query.filter_by(
            event_type="student_learning_progress_viewed",
            request_id="progress-audit",
        ).first()
        assert audit is not None
        assert "Authorization" not in json.dumps([audit.input_payload, audit.output_payload])


def test_teacher_feedback_queue_permissions_and_triage_actions(app_module, client, teacher_token, admin_token, student_token):
    course = unique_text("Feedback Queue Course")
    hidden_course = unique_text("Feedback Hidden Course")
    with app_module.app.app_context():
        acknowledge_card = create_card(app_module, course, english_term="Acknowledge Feedback Term")
        resolve_card = create_card(app_module, course, english_term="Resolve Feedback Term")
        revision_card = create_card(app_module, course, english_term="Revision Feedback Term")
        reopen_card = create_card(app_module, course, english_term="Reopen Feedback Term")
        reject_card = create_card(app_module, course, english_term="Reject Feedback Term")
        hidden_card = create_card(app_module, hidden_course, english_term="Unauthorized Feedback Term")
        grant_student_access(app_module, course)
        grant_student_access(app_module, hidden_course, user=student_user(app_module))
        grant_teacher_review_access(app_module, course)
        feedbacks = {
            "ack": create_feedback(app_module, acknowledge_card),
            "resolve": create_feedback(app_module, resolve_card),
            "revision": create_feedback(app_module, revision_card),
            "reopen": create_feedback(app_module, reopen_card),
            "reject": create_feedback(app_module, reject_card),
            "hidden": create_feedback(app_module, hidden_card),
        }
        feedback_uids = {key: feedback.feedback_uid for key, feedback in feedbacks.items()}
        revision_uid = revision_card.card_uid
        reopen_uid = reopen_card.card_uid

    queue = client.get(
        f"/api/concept-cards/student-feedback-queue?course={course}",
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-queue"},
    )
    assert queue.status_code == 200, queue.get_data(as_text=True)
    queue_payload = queue.get_json()
    queue_uids = {item["feedback_uid"] for item in queue_payload["data"]["items"]}
    assert feedback_uids["ack"] in queue_uids
    assert feedback_uids["hidden"] not in queue_uids
    assert queue_payload["request_id"] == "feedback-queue"

    admin_queue = client.get(
        "/api/concept-cards/student-feedback-queue",
        headers=bearer(admin_token),
    )
    admin_uids = {item["feedback_uid"] for item in admin_queue.get_json()["data"]["items"]}
    assert feedback_uids["hidden"] in admin_uids

    card_feedback = client.get(
        f"/api/concept-cards/{revision_uid}/student-feedback",
        headers=bearer(teacher_token),
    )
    assert card_feedback.status_code == 200
    assert card_feedback.get_json()["data"]["items"][0]["feedback_uid"] == feedback_uids["revision"]

    student_triage = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uids['ack']}/triage",
        json={"action": "acknowledge", "teacher_note": "Student should not triage."},
        headers=bearer(student_token),
    )
    assert student_triage.status_code == 403

    acknowledge = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uids['ack']}/triage",
        json={"action": "acknowledge", "teacher_note": "Acknowledged."},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-ack"},
    )
    assert acknowledge.status_code == 200, acknowledge.get_data(as_text=True)
    assert acknowledge.get_json()["data"]["feedback"]["status"] == "triaged"

    resolved = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uids['resolve']}/triage",
        json={"action": "mark_resolved", "teacher_note": "Resolved after review."},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.get_json()["data"]["feedback"]["status"] == "resolved"

    rejected = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uids['reject']}/triage",
        json={"action": "reject_feedback", "teacher_note": "Not actionable."},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.get_json()["data"]["feedback"]["status"] == "rejected"

    revision = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uids['revision']}/triage",
        json={
            "action": "request_card_revision",
            "reason_code": "evidence_insufficient",
            "teacher_note": "Student feedback requires clarification.",
            "required_changes": ["Clarify student-facing explanation."],
        },
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-revision"},
    )
    assert revision.status_code == 200, revision.get_data(as_text=True)
    assert revision.get_json()["data"]["feedback"]["status"] == "linked_to_review"
    assert revision.get_json()["data"]["review"]["action"] == "request_revision"

    reopen = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uids['reopen']}/triage",
        json={
            "action": "reopen_card_for_review",
            "reason_code": "evidence_insufficient",
            "teacher_note": "Approved card needs another review.",
        },
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-reopen"},
    )
    assert reopen.status_code == 200, reopen.get_data(as_text=True)
    assert reopen.get_json()["data"]["card"]["status"] == "needs_review"

    with app_module.app.app_context():
        revision_card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=revision_uid).first()
        reopen_card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=reopen_uid).first()
        assert revision_card.status == "needs_review"
        assert reopen_card.status == "needs_review"
        assert app_module.ConceptCardFeedbackTriageRecord.query.filter_by(feedback_uid=feedback_uids["ack"]).first() is not None
        assert app_module.ConceptCardReviewRecord.query.filter_by(card_uid=revision_uid, action="request_revision").first() is not None
        assert app_module.AuditRecord.query.filter_by(event_type="concept_card_feedback_triaged", request_id="feedback-ack").first() is not None
        assert app_module.AuditRecord.query.filter_by(event_type="concept_card_feedback_resolved", request_id="feedback-resolved").first() is not None
        assert app_module.AuditRecord.query.filter_by(event_type="concept_card_feedback_linked_to_review", request_id="feedback-revision").first() is not None
        assert app_module.AuditRecord.query.filter_by(event_type="concept_card_reopened_from_student_feedback", request_id="feedback-reopen").first() is not None


def test_feedback_queue_permission_block_and_stable_error(app_module, client, teacher_token):
    unauthorized_course = unique_text("Unauthorized Feedback")
    with app_module.app.app_context():
        card = create_card(app_module, unauthorized_course, english_term="Unauthorized Detail Feedback")
        feedback = create_feedback(app_module, card)
        card_uid = card.card_uid
        feedback_uid = feedback.feedback_uid

    detail = client.get(
        f"/api/concept-cards/{card_uid}/student-feedback",
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-permission-detail"},
    )
    assert detail.status_code == 403
    assert detail.get_json()["request_id"] == "feedback-permission-detail"

    triage = client.post(
        f"/api/concept-cards/student-feedback/{feedback_uid}/triage",
        json={"action": "acknowledge", "teacher_note": "No permission."},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-permission-triage"},
    )
    assert triage.status_code == 403
    assert triage.get_json()["request_id"] == "feedback-permission-triage"
