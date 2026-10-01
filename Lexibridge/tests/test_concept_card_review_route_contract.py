import json
import uuid
from urllib.parse import quote

from test_concept_card_review import bearer, create_card, grant_review_access, unique_text, with_expected_version
from test_course_review_policy import create_policy, get_user, grant_permission
from test_openapi_route_parity import REQUIRED_ROUTE_METHODS, actual_api_routes


TARGET_ROUTES = {
    "/api/concept-cards/review-queue": {
        "endpoint": "concept_card_review_queue_api",
        "methods": {"GET"},
    },
    "/api/concept-cards/<card_uid>/reviews": {
        "endpoint": "concept_card_reviews_api",
        "methods": {"GET"},
    },
    "/api/concept-cards/<card_uid>/review": {
        "endpoint": "concept_card_review_action_api",
        "methods": {"POST"},
    },
    "/api/concept-cards/<card_uid>/assign-reviewer": {
        "endpoint": "concept_card_assign_reviewer_api",
        "methods": {"POST"},
    },
}


def target_rules(app_module):
    return [rule for rule in app_module.app.url_map.iter_rules() if rule.rule in TARGET_ROUTES]


def _route_methods(rule):
    return {method for method in rule.methods if method not in {"HEAD", "OPTIONS"}}


def test_concept_card_review_route_map_contract(app_module):
    rules = target_rules(app_module)
    assert len(rules) == 4
    seen = {}
    for rule in rules:
        methods = _route_methods(rule)
        seen.setdefault((rule.rule, tuple(sorted(methods))), []).append(rule.endpoint)
        assert rule.endpoint == TARGET_ROUTES[rule.rule]["endpoint"]
        assert methods == TARGET_ROUTES[rule.rule]["methods"]
    assert all(len(endpoints) == 1 for endpoints in seen.values())


def test_concept_card_review_openapi_contract_matches_route_map(app_module):
    actual = actual_api_routes(app_module)
    expected = {
        "/api/concept-cards/review-queue": {"get"},
        "/api/concept-cards/{card_uid}/reviews": {"get"},
        "/api/concept-cards/{card_uid}/review": {"post"},
        "/api/concept-cards/{card_uid}/assign-reviewer": {"post"},
    }
    for path, methods in expected.items():
        assert path in REQUIRED_ROUTE_METHODS
        assert REQUIRED_ROUTE_METHODS[path] == methods
        assert actual[path] == methods


def test_review_queue_history_auth_and_visibility_contract(client, app_module, teacher_token, student_token, admin_token):
    allowed_course = unique_text("Review Contract Course")
    hidden_course = unique_text("Review Hidden Course")
    with app_module.app.app_context():
        grant_review_access(app_module, course=allowed_course, permission_level="admin")
        allowed = create_card(
            app_module,
            course=allowed_course,
            english_term=unique_text("Contract Queue Allowed"),
            risk_labels=["bilingual_alignment_not_verified"],
        )
        hidden = create_card(app_module, course=hidden_course, english_term=unique_text("Contract Queue Hidden"))
        allowed_uid = allowed.card_uid
        hidden_uid = hidden.card_uid

    unauth = client.get(
        f"/api/concept-cards/review-queue?course={quote(allowed_course)}",
        headers={"X-Request-ID": "review-contract-unauth"},
    )
    assert unauth.status_code in {401, 403}
    assert unauth.get_json()["request_id"] == "review-contract-unauth"

    student_queue = client.get(
        f"/api/concept-cards/review-queue?course={quote(allowed_course)}",
        headers={**bearer(student_token), "X-Request-ID": "review-contract-student-queue"},
    )
    student_history = client.get(
        f"/api/concept-cards/{allowed_uid}/reviews",
        headers={**bearer(student_token), "X-Request-ID": "review-contract-student-history"},
    )
    assert student_queue.status_code == 403
    assert student_history.status_code == 403

    queue = client.get(
        f"/api/concept-cards/review-queue?course={quote(allowed_course)}&per_page=20",
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-queue"},
    )
    assert queue.status_code == 200, queue.get_data(as_text=True)
    payload = queue.get_json()
    assert set(payload) >= {"status", "message", "data", "request_id"}
    assert payload["request_id"] == "review-contract-queue"
    assert set(payload["data"]) == {"items", "pagination"}
    item = next(entry for entry in payload["data"]["items"] if entry["card_uid"] == allowed_uid)
    assert {"card_uid", "english_term", "chinese_term", "course", "chapter", "status", "risk_labels"} <= set(item)
    assert {"evidence_summary", "latest_review_summary", "assignment_summary", "verification_summary"} <= set(item)

    hidden_queue = client.get(
        f"/api/concept-cards/review-queue?course={quote(hidden_course)}",
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-hidden-queue"},
    )
    assert hidden_queue.status_code == 200
    assert all(entry["card_uid"] != hidden_uid for entry in hidden_queue.get_json()["data"]["items"])

    history = client.get(
        f"/api/concept-cards/{allowed_uid}/reviews",
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-history"},
    )
    assert history.status_code == 200, history.get_data(as_text=True)
    assert history.get_json()["request_id"] == "review-contract-history"
    assert set(history.get_json()["data"]) == {"items", "pagination"}

    hidden_history = client.get(
        f"/api/concept-cards/{hidden_uid}/reviews",
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-hidden-history"},
    )
    assert hidden_history.status_code == 403
    hidden_payload = hidden_history.get_json()
    assert hidden_payload["request_id"] == "review-contract-hidden-history"
    assert hidden_payload["details"]["audit_error_code"] == "course_review_permission_missing"

    admin_history = client.get(
        f"/api/concept-cards/{hidden_uid}/reviews",
        headers={**bearer(admin_token), "X-Request-ID": "review-contract-admin-history"},
    )
    assert admin_history.status_code == 200


def test_review_action_status_audit_and_block_contract(client, app_module, teacher_token, admin_token):
    course = unique_text("Review Action Contract Course")
    with app_module.app.app_context():
        grant_review_access(app_module, course=course, permission_level="admin")
        approve_card = create_card(app_module, course=course)
        reject_card = create_card(app_module, course=course)
        revision_card = create_card(app_module, course=course)
        more_evidence_card = create_card(app_module, course=course)
        reopen_card = create_card(app_module, course=course)
        deprecate_card = create_card(app_module, course=course)
        risky = create_card(app_module, course=course, risk_labels=["bilingual_alignment_not_verified"])
        reopen_card.status = "approved"
        deprecate_card.status = "approved"
        app_module.db.session.commit()
        ids = {
            "approve": approve_card.card_uid,
            "reject": reject_card.card_uid,
            "revision": revision_card.card_uid,
            "more": more_evidence_card.card_uid,
            "reopen": reopen_card.card_uid,
            "deprecate": deprecate_card.card_uid,
            "risky": risky.card_uid,
        }

    blocked = client.post(
        f"/api/concept-cards/{ids['risky']}/review",
        json=with_expected_version(app_module, ids["risky"], {"action": "approve", "reason_code": "teacher_verified", "review_comment": "Risk remains."}),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-risk-block"},
    )
    assert blocked.status_code == 400
    assert blocked.get_json()["request_id"] == "review-contract-risk-block"
    assert blocked.get_json()["details"]["audit_error_code"] == "concept_card_review_validation_error"

    approve = client.post(
        f"/api/concept-cards/{ids['approve']}/review",
        json=with_expected_version(app_module, ids["approve"], {"action": "approve", "reason_code": "teacher_verified", "review_comment": "Approved."}),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-approve"},
    )
    reject = client.post(
        f"/api/concept-cards/{ids['reject']}/review",
        json=with_expected_version(app_module, ids["reject"], {"action": "reject", "reason_code": "chinese_term_wrong", "review_comment": "Wrong term."}),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-reject"},
    )
    revision = client.post(
        f"/api/concept-cards/{ids['revision']}/review",
        json=with_expected_version(app_module, ids["revision"], {"action": "request_revision", "required_changes": ["Add source evidence."]}),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-revision"},
    )
    more = client.post(
        f"/api/concept-cards/{ids['more']}/review",
        json=with_expected_version(app_module, ids["more"], {"action": "mark_needs_more_evidence", "reason_code": "evidence_insufficient", "review_comment": "Need source."}),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-more"},
    )
    reopen = client.post(
        f"/api/concept-cards/{ids['reopen']}/review",
        json=with_expected_version(app_module, ids["reopen"], {"action": "reopen", "reason_code": "course_context_mismatch", "review_comment": "Recheck."}),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-reopen"},
    )
    deprecate = client.post(
        f"/api/concept-cards/{ids['deprecate']}/review",
        json=with_expected_version(app_module, ids["deprecate"], {"action": "deprecate", "reason_code": "duplicate_card", "review_comment": "Superseded."}),
        headers={**bearer(admin_token), "X-Request-ID": "review-contract-deprecate"},
    )

    assert approve.status_code == 200, approve.get_data(as_text=True)
    assert approve.get_json()["data"]["card"]["status"] == "approved"
    assert reject.status_code == 200
    assert reject.get_json()["data"]["card"]["status"] == "rejected"
    assert revision.status_code == 200
    assert revision.get_json()["data"]["review"]["required_changes"] == ["Add source evidence."]
    assert more.status_code == 200
    assert "insufficient_evidence" in more.get_json()["data"]["card"]["risk_labels"]
    assert reopen.status_code == 200
    assert reopen.get_json()["data"]["card"]["status"] == "needs_review"
    assert deprecate.status_code == 200
    assert deprecate.get_json()["data"]["card"]["status"] == "deprecated"

    with app_module.app.app_context():
        risky = app_module.ConceptAlignmentCard.query.filter_by(card_uid=ids["risky"]).first()
        assert risky.status == "needs_review"
        expected_events = {
            "review-contract-risk-block": "concept_card_review_blocked_by_course_policy",
            "review-contract-approve": "concept_card_approved",
            "review-contract-reject": "concept_card_rejected",
            "review-contract-revision": "concept_card_revision_requested",
            "review-contract-more": "concept_card_more_evidence_requested",
            "review-contract-reopen": "concept_card_reopened",
            "review-contract-deprecate": "concept_card_deprecated",
        }
        for request_id, event_type in expected_events.items():
            record = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type=event_type).first()
            assert record is not None
            dump = json.dumps(record.input_payload or "", ensure_ascii=False)
            assert "Authorization" not in dump
            assert "Cookie" not in dump
        for request_id in expected_events:
            review_record = app_module.ConceptCardReviewRecord.query.filter_by(request_id=request_id).first()
            if request_id != "review-contract-risk-block":
                assert review_record is not None


def test_assign_reviewer_permission_contract(client, app_module, teacher_token):
    admin_course = unique_text("Assign Admin Contract Course")
    review_only_course = unique_text("Assign Review Contract Course")
    with app_module.app.app_context():
        grant_review_access(app_module, course=admin_course, permission_level="admin")
        grant_review_access(app_module, course=review_only_course, permission_level="review")
        assign_card = create_card(app_module, course=admin_course)
        blocked_card = create_card(app_module, course=review_only_course)
        assign_uid = assign_card.card_uid
        blocked_uid = blocked_card.card_uid

    assigned = client.post(
        f"/api/concept-cards/{assign_uid}/assign-reviewer",
        json={"assigned_to": "teacher_001", "due_at": "2026-07-20T00:00:00"},
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-assign"},
    )
    blocked = client.post(
        f"/api/concept-cards/{blocked_uid}/assign-reviewer",
        json={"assigned_to": "teacher_002"},
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-assign-block"},
    )

    assert assigned.status_code == 200, assigned.get_data(as_text=True)
    assert assigned.get_json()["data"]["assignment"]["assigned_to"] == "teacher_001"
    assert assigned.get_json()["data"]["review"]["action"] == "assign_reviewer"
    assert blocked.status_code == 400
    assert blocked.get_json()["request_id"] == "review-contract-assign-block"

    with app_module.app.app_context():
        assert app_module.ConceptCardReviewAssignment.query.filter_by(card_uid=assign_uid).first() is not None
        assert app_module.ConceptCardReviewAssignment.query.filter_by(card_uid=blocked_uid).first() is None
        assignment_audit = app_module.AuditRecord.query.filter_by(
            request_id="review-contract-assign",
            event_type="concept_card_reviewer_assigned",
        ).first()
        permission_block = app_module.AuditRecord.query.filter_by(
            request_id="review-contract-assign-block",
            event_type="concept_card_review_blocked_by_permission",
        ).first()
        assert assignment_audit is not None
        assert permission_block is not None


def test_two_step_and_override_contract(client, app_module, teacher_token, admin_token):
    two_step_course = unique_text("Two Step Contract Course")
    override_course = unique_text("Override Contract Course")
    with app_module.app.app_context():
        teacher = get_user(app_module, "teacher")
        create_policy(
            app_module,
            course=two_step_course,
            require_two_step_review=True,
            required_evidence_sides="either",
            min_required_evidence_count=1,
            allow_approve_with_missing_chinese_evidence=True,
        )
        grant_permission(app_module, teacher, course=two_step_course, permission_level="approve")
        two_step = create_card(app_module, course=two_step_course)

        create_policy(
            app_module,
            course=override_course,
            required_evidence_sides="either",
            min_required_evidence_count=1,
            allow_approve_with_missing_chinese_evidence=True,
            allow_approve_with_unverified_alignment=True,
            allow_teacher_override=True,
            require_admin_for_override=False,
            blocking_risk_labels=["parse_failed"],
            override_allowed_risk_labels=[],
            override_forbidden_risk_labels=["parse_failed"],
        )
        grant_permission(app_module, teacher, course=override_course, permission_level="override")
        forbidden = create_card(app_module, course=override_course, risk_labels=["parse_failed"])
        missing_reason = create_card(app_module, course=override_course, risk_labels=["parse_failed"])
        ids = {
            "two_step": two_step.card_uid,
            "forbidden": forbidden.card_uid,
            "missing_reason": missing_reason.card_uid,
        }

    first = client.post(
        f"/api/concept-cards/{ids['two_step']}/review",
        json=with_expected_version(app_module, ids["two_step"], {"action": "approve", "reason_code": "teacher_verified", "review_comment": "Teacher review."}),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-two-step-teacher"},
    )
    assert first.status_code == 200, first.get_data(as_text=True)
    assert first.get_json()["data"]["card"]["status"] == "needs_review"
    assert first.get_json()["data"]["review"]["decision"] == "ready_for_admin_review"

    second = client.post(
        f"/api/concept-cards/{ids['two_step']}/review",
        json=with_expected_version(app_module, ids["two_step"], {"action": "approve", "reason_code": "teacher_verified", "review_comment": "Admin second review."}),
        headers={**bearer(admin_token), "X-Request-ID": "review-contract-two-step-admin"},
    )
    assert second.status_code == 200, second.get_data(as_text=True)
    assert second.get_json()["data"]["card"]["status"] == "approved"

    missing_override_reason = client.post(
        f"/api/concept-cards/{ids['missing_reason']}/review",
        json=with_expected_version(app_module, ids["missing_reason"], {"action": "approve", "reason_code": "teacher_verified", "allow_risk_override": True}),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-missing-override-reason"},
    )
    forbidden_override = client.post(
        f"/api/concept-cards/{ids['forbidden']}/review",
        json=with_expected_version(app_module, ids["forbidden"], {
            "action": "approve",
            "reason_code": "teacher_verified",
            "review_comment": "Trying forbidden override.",
            "allow_risk_override": True,
            "override_reason": "Forbidden by course policy.",
        }),
        headers={**bearer(teacher_token), "X-Request-ID": "review-contract-forbidden-override"},
    )
    assert missing_override_reason.status_code == 400
    assert forbidden_override.status_code == 400

    with app_module.app.app_context():
        missing = app_module.ConceptAlignmentCard.query.filter_by(card_uid=ids["missing_reason"]).first()
        forbidden = app_module.ConceptAlignmentCard.query.filter_by(card_uid=ids["forbidden"]).first()
        assert missing.status == "needs_review"
        assert forbidden.status == "needs_review"
        two_step_record = app_module.ConceptCardReviewRecord.query.filter_by(
            request_id="review-contract-two-step-teacher",
        ).first()
        assert two_step_record is not None
        assert app_module.ConceptCardReviewRecord.query.filter_by(
            request_id="review-contract-two-step-admin",
        ).first() is not None
        assert app_module.AuditRecord.query.filter_by(
            request_id="review-contract-forbidden-override",
            event_type="concept_card_risk_override_blocked_by_policy",
        ).first() is not None
