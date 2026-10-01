import json
import uuid
from urllib.parse import quote

from test_openapi_route_parity import REQUIRED_ROUTE_METHODS, actual_api_routes
from test_student_learning_progress_feedback import (
    bearer,
    create_card,
    create_feedback,
    grant_teacher_review_access,
    unique_text,
)


TARGET_ROUTES = {
    "/api/concept-cards/student-feedback-queue": {
        "endpoint": "concept_card_student_feedback_queue_api",
        "methods": {"GET"},
    },
    "/api/concept-cards/<card_uid>/student-feedback": {
        "endpoint": "concept_card_student_feedback_for_card_api",
        "methods": {"GET"},
    },
    "/api/concept-cards/student-feedback/<feedback_uid>/triage": {
        "endpoint": "triage_concept_card_student_feedback_api",
        "methods": {"POST"},
    },
}


def target_rules(app_module):
    return [rule for rule in app_module.app.url_map.iter_rules() if rule.rule in TARGET_ROUTES]


def _route_methods(rule):
    return {method for method in rule.methods if method not in {"HEAD", "OPTIONS"}}


def _course(prefix):
    return unique_text(prefix)


def test_concept_card_feedback_route_map_contract(app_module):
    rules = target_rules(app_module)
    assert len(rules) == 3
    seen = {}
    for rule in rules:
        methods = _route_methods(rule)
        seen.setdefault((rule.rule, tuple(sorted(methods))), []).append(rule.endpoint)
        assert rule.endpoint == TARGET_ROUTES[rule.rule]["endpoint"]
        assert methods == TARGET_ROUTES[rule.rule]["methods"]
    assert all(len(endpoints) == 1 for endpoints in seen.values())


def test_concept_card_feedback_openapi_contract_matches_route_map(app_module):
    actual = actual_api_routes(app_module)
    expected = {
        "/api/concept-cards/student-feedback-queue": {"get"},
        "/api/concept-cards/{card_uid}/student-feedback": {"get"},
        "/api/concept-cards/student-feedback/{feedback_uid}/triage": {"post"},
    }
    for path, methods in expected.items():
        assert path in REQUIRED_ROUTE_METHODS
        assert REQUIRED_ROUTE_METHODS[path] == methods
        assert actual[path] == methods


def test_feedback_queue_and_card_feedback_contract(client, app_module, teacher_token, admin_token, student_token):
    course = _course("Feedback Contract Course")
    hidden_course = _course("Feedback Contract Hidden")
    with app_module.app.app_context():
        visible_card = create_card(app_module, course, english_term="Feedback Queue Visible")
        hidden_card = create_card(app_module, hidden_course, english_term="Feedback Queue Hidden")
        visible_feedback = create_feedback(app_module, visible_card, message="Visible feedback message for queue.")
        hidden_feedback = create_feedback(app_module, hidden_card, message="Hidden feedback message for queue.")
        grant_teacher_review_access(app_module, course)
        visible_feedback_uid = visible_feedback.feedback_uid
        hidden_feedback_uid = hidden_feedback.feedback_uid
        visible_card_uid = visible_card.card_uid
        hidden_card_uid = hidden_card.card_uid

    unauth = client.get(
        f"/api/concept-cards/student-feedback-queue?course={quote(course)}",
        headers={"X-Request-ID": "feedback-contract-unauth"},
    )
    assert unauth.status_code in {401, 403}
    assert unauth.get_json()["request_id"] == "feedback-contract-unauth"

    student_queue = client.get(
        f"/api/concept-cards/student-feedback-queue?course={quote(course)}",
        headers={**bearer(student_token), "X-Request-ID": "feedback-contract-student-queue"},
    )
    student_detail = client.get(
        f"/api/concept-cards/{visible_card_uid}/student-feedback",
        headers={**bearer(student_token), "X-Request-ID": "feedback-contract-student-detail"},
    )
    assert student_queue.status_code == 403
    assert student_detail.status_code == 403

    queue = client.get(
        f"/api/concept-cards/student-feedback-queue?course={quote(course)}&status=submitted&page=1&per_page=20",
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-contract-queue"},
    )
    assert queue.status_code == 200, queue.get_data(as_text=True)
    payload = queue.get_json()
    assert set(payload) >= {"status", "message", "data", "request_id"}
    assert payload["request_id"] == "feedback-contract-queue"
    assert set(payload["data"]) == {"items", "pagination"}
    item = next(entry for entry in payload["data"]["items"] if entry["feedback_uid"] == visible_feedback_uid)
    assert {
        "feedback_uid",
        "card_uid",
        "english_term",
        "chinese_term",
        "course",
        "chapter",
        "feedback_type",
        "message",
        "message_snippet",
        "suggested_chinese_term",
        "submitted_by",
        "status",
        "priority",
        "card_status",
        "card_risk_labels",
        "latest_review_summary",
    } <= set(item)
    assert item["card_uid"] == visible_card_uid
    assert hidden_feedback_uid not in {entry["feedback_uid"] for entry in payload["data"]["items"]}

    detail = client.get(
        f"/api/concept-cards/{visible_card_uid}/student-feedback",
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-contract-detail"},
    )
    assert detail.status_code == 200
    detail_payload = detail.get_json()
    assert detail_payload["request_id"] == "feedback-contract-detail"
    assert set(detail_payload["data"]) == {"items", "count"}
    assert detail_payload["data"]["items"][0]["feedback_uid"] == visible_feedback_uid

    hidden_detail = client.get(
        f"/api/concept-cards/{hidden_card_uid}/student-feedback",
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-contract-hidden-detail"},
    )
    assert hidden_detail.status_code == 403
    assert hidden_detail.get_json()["details"]["audit_error_code"] == "course_review_permission_missing"

    admin_queue = client.get(
        f"/api/concept-cards/student-feedback-queue?course={quote(hidden_course)}",
        headers={**bearer(admin_token), "X-Request-ID": "feedback-contract-admin-queue"},
    )
    assert admin_queue.status_code == 200
    assert hidden_feedback_uid in {entry["feedback_uid"] for entry in admin_queue.get_json()["data"]["items"]}

    with app_module.app.app_context():
        audit = app_module.AuditRecord.query.filter_by(
            event_type="concept_card_feedback_queue_viewed",
            request_id="feedback-contract-queue",
        ).first()
        assert audit is not None
        assert "Authorization" not in (audit.input_payload or "")
        assert "Cookie" not in (audit.input_payload or "")


def test_feedback_triage_action_contract(client, app_module, teacher_token):
    course = _course("Feedback Triage Contract")
    with app_module.app.app_context():
        grant_teacher_review_access(app_module, course)
        cards = {
            "ack": create_card(app_module, course, english_term="Feedback Ack Term"),
            "resolve": create_card(app_module, course, english_term="Feedback Resolve Term"),
            "duplicate": create_card(app_module, course, english_term="Feedback Duplicate Term"),
            "reject": create_card(app_module, course, english_term="Feedback Reject Term"),
            "note": create_card(app_module, course, english_term="Feedback Note Term"),
            "link": create_card(app_module, course, english_term="Feedback Link Term"),
            "revision": create_card(app_module, course, english_term="Feedback Revision Term"),
            "reopen": create_card(app_module, course, english_term="Feedback Reopen Term"),
        }
        feedbacks = {key: create_feedback(app_module, card) for key, card in cards.items()}
        feedback_uids = {key: feedback.feedback_uid for key, feedback in feedbacks.items()}
        card_uids = {key: card.card_uid for key, card in cards.items()}

    actions = {
        "ack": (
            {"action": "acknowledge", "teacher_note": "Acknowledged."},
            "triaged",
            None,
            "concept_card_feedback_triaged",
        ),
        "resolve": (
            {"action": "mark_resolved", "teacher_note": "Resolved."},
            "resolved",
            None,
            "concept_card_feedback_resolved",
        ),
        "duplicate": (
            {"action": "mark_duplicate", "teacher_note": "Duplicate."},
            "duplicate",
            None,
            "concept_card_feedback_triaged",
        ),
        "reject": (
            {"action": "reject_feedback", "teacher_note": "Not actionable."},
            "rejected",
            None,
            "concept_card_feedback_triaged",
        ),
        "note": (
            {"action": "add_teacher_note", "teacher_note": "Teacher note only."},
            "submitted",
            None,
            "concept_card_feedback_triaged",
        ),
        "link": (
            {"action": "link_to_existing_review", "linked_review_uid": "existing-review-contract"},
            "linked_to_review",
            None,
            "concept_card_feedback_linked_to_review",
        ),
        "revision": (
            {
                "action": "request_card_revision",
                "reason_code": "evidence_insufficient",
                "teacher_note": "Student feedback requires revision.",
                "required_changes": ["Clarify student-facing explanation."],
            },
            "linked_to_review",
            "request_revision",
            "concept_card_feedback_linked_to_review",
        ),
        "reopen": (
            {
                "action": "reopen_card_for_review",
                "reason_code": "evidence_insufficient",
                "teacher_note": "Approved card needs another review.",
            },
            "linked_to_review",
            "reopen",
            "concept_card_reopened_from_student_feedback",
        ),
    }

    for key, (payload, expected_status, expected_review_action, expected_event) in actions.items():
        request_id = f"feedback-contract-{key}"
        response = client.post(
            f"/api/concept-cards/student-feedback/{feedback_uids[key]}/triage",
            json=payload,
            headers={**bearer(teacher_token), "X-Request-ID": request_id},
        )
        assert response.status_code == 200, response.get_data(as_text=True)
        body = response.get_json()
        assert body["request_id"] == request_id
        assert set(body["data"]) == {"feedback", "triage", "review", "card"}
        assert body["data"]["feedback"]["status"] == expected_status
        assert body["data"]["triage"]["action"] == payload["action"]
        assert body["data"]["triage"]["previous_status"] == "submitted"
        assert body["data"]["triage"]["new_status"] == expected_status
        if expected_review_action:
            assert body["data"]["review"]["action"] == expected_review_action
        else:
            assert body["data"]["review"] is None
        if key == "link":
            assert body["data"]["feedback"]["linked_review_uid"] == "existing-review-contract"

        with app_module.app.app_context():
            assert app_module.ConceptCardFeedbackTriageRecord.query.filter_by(
                feedback_uid=feedback_uids[key],
                action=payload["action"],
            ).first() is not None
            audit = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type=expected_event).first()
            assert audit is not None
            audit_dump = json.dumps([audit.input_payload, audit.output_payload], ensure_ascii=False)
            assert "Authorization" not in audit_dump
            assert "Cookie" not in audit_dump
            feedback = app_module.Feedback.query.filter_by(feedback_uid=feedback_uids[key]).first()
            assert feedback.status == expected_status
            if expected_review_action:
                review = app_module.ConceptCardReviewRecord.query.filter_by(
                    card_uid=card_uids[key],
                    action=expected_review_action,
                ).first()
                assert review is not None

    with app_module.app.app_context():
        revision_card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card_uids["revision"]).first()
        reopen_card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card_uids["reopen"]).first()
        assert revision_card.status == "needs_review"
        assert reopen_card.status == "needs_review"


def test_feedback_triage_error_and_block_contract(client, app_module, teacher_token, student_token):
    course = _course("Feedback Error Contract")
    hidden_course = _course("Feedback Error Hidden")
    with app_module.app.app_context():
        grant_teacher_review_access(app_module, course)
        visible_card = create_card(app_module, course, english_term="Feedback Error Visible")
        hidden_card = create_card(app_module, hidden_course, english_term="Feedback Error Hidden")
        invalid_feedback = create_feedback(app_module, visible_card)
        missing_note_feedback = create_feedback(app_module, visible_card)
        missing_reason_feedback = create_feedback(app_module, visible_card)
        hidden_feedback = create_feedback(app_module, hidden_card)
        ids = {
            "visible_card": visible_card.card_uid,
            "hidden_card": hidden_card.card_uid,
            "invalid": invalid_feedback.feedback_uid,
            "missing_note": missing_note_feedback.feedback_uid,
            "missing_reason": missing_reason_feedback.feedback_uid,
            "hidden": hidden_feedback.feedback_uid,
        }

    student = client.post(
        f"/api/concept-cards/student-feedback/{ids['invalid']}/triage",
        json={"action": "acknowledge", "teacher_note": "Student cannot triage."},
        headers={**bearer(student_token), "X-Request-ID": "feedback-contract-student-triage"},
    )
    assert student.status_code == 403

    invalid = client.post(
        f"/api/concept-cards/student-feedback/{ids['invalid']}/triage",
        json={"action": "not_real"},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-contract-invalid"},
    )
    missing_note = client.post(
        f"/api/concept-cards/student-feedback/{ids['missing_note']}/triage",
        json={"action": "reject_feedback"},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-contract-missing-note"},
    )
    missing_reason = client.post(
        f"/api/concept-cards/student-feedback/{ids['missing_reason']}/triage",
        json={"action": "request_card_revision", "teacher_note": "Needs reason."},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-contract-missing-reason"},
    )
    unauthorized = client.post(
        f"/api/concept-cards/student-feedback/{ids['hidden']}/triage",
        json={"action": "acknowledge", "teacher_note": "No course permission."},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-contract-unauthorized"},
    )
    missing = client.post(
        f"/api/concept-cards/student-feedback/missing-{uuid.uuid4().hex}/triage",
        json={"action": "acknowledge", "teacher_note": "Missing feedback."},
        headers={**bearer(teacher_token), "X-Request-ID": "feedback-contract-missing"},
    )

    assert invalid.status_code == 400
    assert invalid.get_json()["details"]["audit_error_code"] == "invalid_action"
    assert missing_note.status_code == 400
    assert missing_note.get_json()["details"]["audit_error_code"] == "missing_teacher_note"
    assert missing_reason.status_code == 400
    assert missing_reason.get_json()["details"]["audit_error_code"] == "missing_reason_code"
    assert unauthorized.status_code == 403
    assert unauthorized.get_json()["details"]["audit_error_code"] == "course_review_permission_missing"
    assert missing.status_code == 404
    assert missing.get_json()["details"]["audit_error_code"] == "feedback_not_found"

    with app_module.app.app_context():
        hidden_feedback = app_module.Feedback.query.filter_by(feedback_uid=ids["hidden"]).first()
        hidden_card = app_module.ConceptAlignmentCard.query.filter_by(card_uid=ids["hidden_card"]).first()
        assert hidden_feedback.status == "submitted"
        assert hidden_card.status == "approved"
        assert app_module.ConceptCardFeedbackTriageRecord.query.filter_by(feedback_uid=ids["hidden"]).first() is None
