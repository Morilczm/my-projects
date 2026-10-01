import json
from urllib.parse import quote

from test_openapi_route_parity import REQUIRED_ROUTE_METHODS, actual_api_routes
from test_student_concept_cards import bearer, create_concept_card, grant_student_course_access, unique_text


TARGET_ROUTES = {
    "/api/student/concept-cards": {
        "endpoint": "list_student_concept_cards_api",
        "methods": {"GET"},
    },
    "/api/student/concept-cards/export": {
        "endpoint": "export_student_concept_cards_api",
        "methods": {"GET"},
    },
    "/api/student/concept-cards/<card_uid>": {
        "endpoint": "get_student_concept_card_api",
        "methods": {"GET"},
    },
    "/api/student/concept-cards/<card_uid>/state": {
        "endpoint": "update_student_concept_card_state_api",
        "methods": {"POST"},
    },
    "/api/student/concept-cards/<card_uid>/feedback": {
        "endpoint": "student_concept_card_feedback_api",
        "methods": {"POST"},
    },
}

CSV_HEADER = (
    "english_term,chinese_term,course,chapter,concept_scope,english_explanation,"
    "chinese_explanation,source_summary,mastered,favorited"
)


def target_rules(app_module):
    return [rule for rule in app_module.app.url_map.iter_rules() if rule.rule in TARGET_ROUTES]


def _create_hidden_course(app_module, course):
    admin = app_module.User.query.filter_by(role="admin").first()
    app_module.student_course_access_service.create_or_update_course_student_visibility_policy(
        app_module.db.session,
        app_module.CourseStudentVisibilityPolicy,
        course,
        {
            "visibility": "enrolled_only",
            "status": "active",
            "allow_teacher_preview": True,
        },
        actor=admin,
        now_fn=app_module.current_time_text,
    )
    app_module.db.session.commit()


def test_student_concept_card_route_map_contract(app_module):
    rules = target_rules(app_module)
    assert len(rules) == 5
    seen = {}
    for rule in rules:
        methods = {method for method in rule.methods if method not in {"HEAD", "OPTIONS"}}
        seen.setdefault((rule.rule, tuple(sorted(methods))), []).append(rule.endpoint)
        assert rule.endpoint == TARGET_ROUTES[rule.rule]["endpoint"]
        assert methods == TARGET_ROUTES[rule.rule]["methods"]
    assert all(len(endpoints) == 1 for endpoints in seen.values())


def test_student_concept_card_openapi_contract_matches_route_map(app_module):
    actual = actual_api_routes(app_module)
    for path in {
        "/api/student/concept-cards",
        "/api/student/concept-cards/{card_uid}",
        "/api/student/concept-cards/{card_uid}/state",
        "/api/student/concept-cards/{card_uid}/feedback",
        "/api/student/concept-cards/export",
    }:
        assert path in REQUIRED_ROUTE_METHODS
        assert actual[path] == REQUIRED_ROUTE_METHODS[path]


def test_student_concept_card_list_detail_auth_and_visibility_contract(
    client,
    app_module,
    student_token,
    teacher_token,
    admin_token,
):
    visible_course = unique_text("Contract Visible Course")
    hidden_course = unique_text("Contract Hidden Course")
    with app_module.app.app_context():
        approved = create_concept_card(app_module, course=visible_course, english_term="Contract Approved Fourier")
        hidden = create_concept_card(app_module, course=hidden_course, english_term="Contract Hidden Fourier")
        needs_review = create_concept_card(
            app_module,
            status="needs_review",
            course=visible_course,
            english_term="Contract Needs Review Fourier",
        )
        approved_uid = approved.card_uid
        hidden_uid = hidden.card_uid
        needs_review_uid = needs_review.card_uid
        grant_student_course_access(app_module, visible_course)
        _create_hidden_course(app_module, hidden_course)

    unauth = client.get(
        f"/api/student/concept-cards?course={quote(visible_course)}",
        headers={"X-Request-ID": "student-contract-unauth"},
    )
    assert unauth.status_code in {401, 403}
    assert unauth.get_json()["request_id"] == "student-contract-unauth"

    visible = client.get(
        f"/api/student/concept-cards?course={quote(visible_course)}&q=Approved",
        headers={**bearer(student_token), "X-Request-ID": "student-contract-list"},
    )
    assert visible.status_code == 200, visible.get_data(as_text=True)
    payload = visible.get_json()
    assert set(payload) >= {"status", "message", "data", "request_id"}
    assert payload["request_id"] == "student-contract-list"
    assert set(payload["data"]) == {"items", "pagination", "approved_only"}
    assert payload["data"]["approved_only"] is True
    assert [item["card_uid"] for item in payload["data"]["items"]] == [approved_uid]
    item = payload["data"]["items"][0]
    assert item["status"] == "approved"
    assert item["source_summary"]
    assert "Teacher reviewed" in item["public_badges"]

    hidden_list = client.get(
        f"/api/student/concept-cards?course={quote(hidden_course)}",
        headers={**bearer(student_token), "X-Request-ID": "student-contract-hidden-list"},
    )
    assert hidden_list.status_code == 200
    assert hidden_list.get_json()["data"]["items"] == []

    teacher_view = client.get(
        f"/api/student/concept-cards?course={quote(visible_course)}",
        headers={**bearer(teacher_token), "X-Request-ID": "student-contract-teacher-view"},
    )
    assert teacher_view.status_code == 200
    assert teacher_view.get_json()["data"]["items"]

    admin_view = client.get(
        f"/api/student/concept-cards?course={quote(visible_course)}",
        headers={**bearer(admin_token), "X-Request-ID": "student-contract-admin-view"},
    )
    assert admin_view.status_code == 200
    assert admin_view.get_json()["data"]["items"]

    detail = client.get(
        f"/api/student/concept-cards/{approved_uid}",
        headers={**bearer(student_token), "X-Request-ID": "student-contract-detail"},
    )
    assert detail.status_code == 200, detail.get_data(as_text=True)
    detail_payload = detail.get_json()
    assert detail_payload["request_id"] == "student-contract-detail"
    assert set(detail_payload["data"]) == {"card", "approved_only"}
    card_data = detail_payload["data"]["card"]
    assert card_data["card_uid"] == approved_uid
    assert card_data["english_evidence"]
    assert card_data["chinese_evidence"]
    assert card_data["student_state"]["view_count"] == 1
    detail_dump = json.dumps(detail_payload, ensure_ascii=False)
    assert "AuditRecord" not in detail_dump
    assert "Authorization" not in detail_dump
    assert "Cookie" not in detail_dump
    assert "override_reason" not in detail_dump
    assert "provider_raw" not in detail_dump

    blocked_hidden = client.get(
        f"/api/student/concept-cards/{hidden_uid}",
        headers={**bearer(student_token), "X-Request-ID": "student-contract-hidden-detail"},
    )
    assert blocked_hidden.status_code == 404
    hidden_payload = blocked_hidden.get_json()
    assert hidden_payload["request_id"] == "student-contract-hidden-detail"
    assert hidden_payload["details"]["audit_error_code"] == "student_concept_card_access_denied"

    blocked_needs_review = client.get(
        f"/api/student/concept-cards/{needs_review_uid}",
        headers={**bearer(student_token), "X-Request-ID": "student-contract-needs-review-detail"},
    )
    assert blocked_needs_review.status_code == 404
    assert blocked_needs_review.get_json()["details"]["audit_error_code"] == "concept_card_not_available"


def test_student_concept_card_state_feedback_audit_and_export_contract(client, app_module, student_token):
    visible_course = unique_text("Contract State Export Course")
    hidden_course = unique_text("Contract Hidden Write Course")
    with app_module.app.app_context():
        visible = create_concept_card(app_module, course=visible_course, english_term="Contract Export Term")
        hidden = create_concept_card(app_module, course=hidden_course, english_term="Contract Hidden Write Term")
        visible_uid = visible.card_uid
        hidden_uid = hidden.card_uid
        grant_student_course_access(app_module, visible_course)
        _create_hidden_course(app_module, hidden_course)

    state = client.post(
        f"/api/student/concept-cards/{visible_uid}/state",
        json={"favorited": True, "mastered": False, "personal_note": "Route contract note."},
        headers={**bearer(student_token), "X-Request-ID": "student-contract-state"},
    )
    assert state.status_code == 200, state.get_data(as_text=True)
    state_payload = state.get_json()
    assert state_payload["request_id"] == "student-contract-state"
    assert set(state_payload["data"]) == {"state", "card", "approved_only"}
    assert state_payload["data"]["state"]["favorited"] is True
    assert state_payload["data"]["state"]["mastered"] is False

    feedback = client.post(
        f"/api/student/concept-cards/{visible_uid}/feedback",
        json={
            "feedback_type": "explanation_unclear",
            "message": "The explanation needs one more student-facing example.",
            "suggested_chinese_term": "合同建议术语",
        },
        headers={**bearer(student_token), "X-Request-ID": "student-contract-feedback"},
    )
    assert feedback.status_code == 200, feedback.get_data(as_text=True)
    feedback_payload = feedback.get_json()
    assert feedback_payload["request_id"] == "student-contract-feedback"
    assert set(feedback_payload["data"]) == {"feedback", "approved_only"}
    assert feedback_payload["data"]["feedback"]["card_uid"] == visible_uid
    assert feedback_payload["data"]["feedback"]["feedback_source"] == "student_concept_card"

    hidden_state = client.post(
        f"/api/student/concept-cards/{hidden_uid}/state",
        json={"favorited": True},
        headers={**bearer(student_token), "X-Request-ID": "student-contract-hidden-state"},
    )
    hidden_feedback = client.post(
        f"/api/student/concept-cards/{hidden_uid}/feedback",
        json={"feedback_type": "other", "message": "Hidden feedback should be blocked."},
        headers={**bearer(student_token), "X-Request-ID": "student-contract-hidden-feedback"},
    )
    assert hidden_state.status_code == 404
    assert hidden_feedback.status_code == 404

    export_json = client.get(
        f"/api/student/concept-cards/export?course={quote(visible_course)}&format=json",
        headers={**bearer(student_token), "X-Request-ID": "student-contract-export-json"},
    )
    assert export_json.status_code == 200, export_json.get_data(as_text=True)
    export_payload = export_json.get_json()
    assert export_payload["request_id"] == "student-contract-export-json"
    assert set(export_payload["data"]) == {"items", "count", "approved_only"}
    assert export_payload["data"]["count"] == 1
    assert export_payload["data"]["items"][0]["english_term"] == "Contract Export Term"
    export_dump = json.dumps(export_payload, ensure_ascii=False)
    assert "AuditRecord" not in export_dump
    assert "Authorization" not in export_dump
    assert "Cookie" not in export_dump
    assert "override_reason" not in export_dump

    export_favorited = client.get(
        f"/api/student/concept-cards/export?course={quote(visible_course)}&scope=favorited&format=json",
        headers=bearer(student_token),
    )
    assert export_favorited.get_json()["data"]["count"] == 1

    export_unmastered = client.get(
        f"/api/student/concept-cards/export?course={quote(visible_course)}&scope=unmastered&format=json",
        headers=bearer(student_token),
    )
    assert export_unmastered.get_json()["data"]["count"] == 1

    export_csv = client.get(
        f"/api/student/concept-cards/export?course={quote(visible_course)}&format=csv",
        headers={**bearer(student_token), "X-Request-ID": "student-contract-export-csv"},
    )
    assert export_csv.status_code == 200, export_csv.get_data(as_text=True)
    assert export_csv.headers["X-Request-ID"] == "student-contract-export-csv"
    assert export_csv.headers["Content-Type"].startswith("text/csv")
    assert "attachment; filename=student_concept_cards.csv" in export_csv.headers["Content-Disposition"]
    csv_text = export_csv.get_data(as_text=True)
    assert csv_text.startswith(CSV_HEADER)
    assert len(csv_text.strip().splitlines()) > 1
    assert "Contract Hidden Write Term" not in csv_text
    assert "Authorization" not in csv_text
    assert "Cookie" not in csv_text
    assert "AuditRecord" not in csv_text

    with app_module.app.app_context():
        persisted = app_module.ConceptAlignmentCard.query.filter_by(card_uid=visible_uid).first()
        assert persisted.status == "approved"
        hidden_state_row = app_module.StudentConceptCardState.query.filter_by(card_uid=hidden_uid).first()
        assert hidden_state_row is None
        hidden_feedback_row = app_module.Feedback.query.filter_by(actual_result=hidden_uid).first()
        assert hidden_feedback_row is None
        expected = {
            "student-contract-state": "student_concept_card_state_updated",
            "student-contract-feedback": "student_concept_card_feedback_submitted",
            "student-contract-hidden-state": "student_concept_card_access_denied",
            "student-contract-hidden-feedback": "student_concept_card_access_denied",
        }
        for request_id, event_type in expected.items():
            record = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type=event_type).first()
            assert record is not None
            assert "Authorization" not in (record.input_payload or "")
            assert "Cookie" not in (record.input_payload or "")
