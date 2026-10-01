import json
from urllib.parse import quote

from test_openapi_route_parity import REQUIRED_ROUTE_METHODS, actual_api_routes
from test_teacher_learning_analytics import bearer, build_analytics_fixture


TARGET_ROUTES = {
    "/api/teacher/learning-analytics": {
        "endpoint": "teacher_learning_analytics_api",
        "methods": {"GET"},
    },
    "/api/teacher/learning-analytics/cards": {
        "endpoint": "teacher_learning_analytics_cards_api",
        "methods": {"GET"},
    },
    "/api/teacher/learning-analytics/export": {
        "endpoint": "teacher_learning_analytics_export_api",
        "methods": {"GET"},
    },
}

CSV_HEADER = (
    "course,chapter,english_term,chinese_term,mastered_count,favorited_count,"
    "viewed_count,feedback_count,unresolved_feedback_count,priority_hint"
)


def target_rules(app_module):
    return [rule for rule in app_module.app.url_map.iter_rules() if rule.rule in TARGET_ROUTES]


def test_teacher_analytics_route_map_contract(app_module):
    rules = target_rules(app_module)
    assert len(rules) == 3
    seen = {}
    for rule in rules:
        methods = {method for method in rule.methods if method not in {"HEAD", "OPTIONS"}}
        seen.setdefault((rule.rule, tuple(sorted(methods))), []).append(rule.endpoint)
        assert rule.endpoint == TARGET_ROUTES[rule.rule]["endpoint"]
        assert methods == TARGET_ROUTES[rule.rule]["methods"]
    assert all(len(endpoints) == 1 for endpoints in seen.values())


def test_teacher_analytics_openapi_contract_matches_route_map(app_module):
    actual = actual_api_routes(app_module)
    for path in TARGET_ROUTES:
        assert path in REQUIRED_ROUTE_METHODS
        assert actual[path] == {"get"}


def test_teacher_analytics_success_error_auth_and_permission_contract(
    client,
    app_module,
    teacher_token,
    admin_token,
    student_token,
):
    with app_module.app.app_context():
        fixture = build_analytics_fixture(app_module)
        course = fixture["course"]
        hidden_course = fixture["hidden_course"]

    analytics = client.get(
        f"/api/teacher/learning-analytics?course={quote(course)}&include_feedback_hotspots=true",
        headers={**bearer(teacher_token), "X-Request-ID": "contract-analytics"},
    )
    assert analytics.status_code == 200, analytics.get_data(as_text=True)
    payload = analytics.get_json()
    assert set(payload) >= {"status", "message", "data", "request_id"}
    assert payload["status"] == "success"
    assert payload["request_id"] == "contract-analytics"
    assert set(payload["data"]) >= {
        "course_summary",
        "chapter_summaries",
        "low_mastery_cards",
        "feedback_hotspots",
        "unresolved_feedback",
    }

    cards = client.get(
        f"/api/teacher/learning-analytics/cards?course={quote(course)}&sort=feedback_count",
        headers={**bearer(teacher_token), "X-Request-ID": "contract-cards"},
    )
    assert cards.status_code == 200, cards.get_data(as_text=True)
    cards_payload = cards.get_json()
    assert cards_payload["request_id"] == "contract-cards"
    assert set(cards_payload["data"]) == {"items", "pagination"}
    assert cards_payload["data"]["items"]

    hidden = client.get(
        f"/api/teacher/learning-analytics?course={quote(hidden_course)}",
        headers={**bearer(teacher_token), "X-Request-ID": "contract-hidden"},
    )
    assert hidden.status_code == 200, hidden.get_data(as_text=True)
    assert hidden.get_json()["data"]["course_summary"]["approved_card_count"] == 0

    admin_hidden = client.get(
        f"/api/teacher/learning-analytics?course={quote(hidden_course)}",
        headers={**bearer(admin_token), "X-Request-ID": "contract-admin-hidden"},
    )
    assert admin_hidden.status_code == 200, admin_hidden.get_data(as_text=True)
    assert admin_hidden.get_json()["data"]["course_summary"]["approved_card_count"] == 1

    student_block = client.get(
        f"/api/teacher/learning-analytics?course={quote(course)}",
        headers={**bearer(student_token), "X-Request-ID": "contract-student-block"},
    )
    assert student_block.status_code == 403
    student_payload = student_block.get_json()
    assert set(student_payload) >= {"status", "error_code", "message", "details", "request_id"}
    assert student_payload["status"] == "error"
    assert student_payload["request_id"] == "contract-student-block"

    unauth = client.get(
        f"/api/teacher/learning-analytics?course={quote(course)}",
        headers={"X-Request-ID": "contract-unauth"},
    )
    assert unauth.status_code in {401, 403}
    unauth_payload = unauth.get_json()
    assert set(unauth_payload) >= {"status", "error_code", "message", "details", "request_id"}
    assert unauth_payload["request_id"] == "contract-unauth"


def test_teacher_analytics_audit_and_export_contract(client, app_module, teacher_token):
    with app_module.app.app_context():
        fixture = build_analytics_fixture(app_module)
        course = fixture["course"]

    client.get(
        f"/api/teacher/learning-analytics?course={quote(course)}",
        headers={**bearer(teacher_token), "X-Request-ID": "contract-audit-view"},
    )
    client.get(
        f"/api/teacher/learning-analytics/cards?course={quote(course)}",
        headers={**bearer(teacher_token), "X-Request-ID": "contract-audit-cards"},
    )
    export_json = client.get(
        f"/api/teacher/learning-analytics/export?course={quote(course)}&format=json",
        headers={**bearer(teacher_token), "X-Request-ID": "contract-audit-export-json"},
    )
    assert export_json.status_code == 200, export_json.get_data(as_text=True)
    export_payload = export_json.get_json()
    assert export_payload["request_id"] == "contract-audit-export-json"
    dump = json.dumps(export_payload, ensure_ascii=False)
    assert "AuditRecord" not in dump
    assert "Authorization" not in dump
    assert "Cookie" not in dump
    assert "submitted_by" not in dump

    export_csv = client.get(
        f"/api/teacher/learning-analytics/export?course={quote(course)}&format=csv",
        headers={**bearer(teacher_token), "X-Request-ID": "contract-audit-export-csv"},
    )
    assert export_csv.status_code == 200, export_csv.get_data(as_text=True)
    assert export_csv.headers["X-Request-ID"] == "contract-audit-export-csv"
    assert export_csv.headers["Content-Type"].startswith("text/csv")
    assert "attachment; filename=teacher_learning_analytics.csv" in export_csv.headers["Content-Disposition"]
    csv_text = export_csv.get_data(as_text=True)
    assert csv_text.startswith(CSV_HEADER)
    assert len(csv_text.strip().splitlines()) > 1
    assert "Authorization" not in csv_text
    assert "Cookie" not in csv_text
    assert "AuditRecord" not in csv_text

    with app_module.app.app_context():
        expected = {
            "contract-audit-view": "teacher_learning_analytics_viewed",
            "contract-audit-cards": "teacher_learning_analytics_cards_viewed",
            "contract-audit-export-json": "teacher_learning_report_exported",
            "contract-audit-export-csv": "teacher_learning_report_exported",
        }
        for request_id, event_type in expected.items():
            record = app_module.AuditRecord.query.filter_by(request_id=request_id, event_type=event_type).first()
            assert record is not None
            assert record.target_type == "teacher_learning_analytics"
            assert "Authorization" not in (record.input_payload or "")
            assert "Cookie" not in (record.input_payload or "")
            output_payload = json.loads(record.output_payload or "{}")
            assert "result_count" in output_payload
            if event_type == "teacher_learning_report_exported":
                assert output_payload["export_format"] in {"csv", "json"}
