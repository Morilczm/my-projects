from test_pilot_feedback import auth_header, create_visible_card


def make_feedback(client, app_module, student_token, feedback_type, severity):
    with app_module.app.app_context():
        card = create_visible_card(app_module)
        card_id = card.id
    response = client.post(
        f"/api/terminology/cards/{card_id}/feedback",
        json={"feedback_type": feedback_type, "severity": severity, "reported_issue": f"{feedback_type} issue"},
        headers=auth_header(student_token),
    )
    assert response.status_code == 200
    return response.get_json()["data"]["feedback_id"]


def convert_to_backlog(client, teacher_token, feedback_id):
    response = client.post(
        f"/api/feedback/{feedback_id}/convert-to-backlog",
        json={},
        headers=auth_header(teacher_token),
    )
    assert response.status_code == 200
    return response.get_json()["backlog_item"]


def test_feedback_to_backlog_priority_mapping(client, app_module, student_token, teacher_token):
    formula_feedback = make_feedback(client, app_module, student_token, "formula_ocr_error", "high")
    permission_feedback = make_feedback(client, app_module, student_token, "permission_issue", "critical")
    ui_feedback = make_feedback(client, app_module, student_token, "ui_confusion", "low")

    formula_item = convert_to_backlog(client, teacher_token, formula_feedback)
    permission_item = convert_to_backlog(client, teacher_token, permission_feedback)
    ui_item = convert_to_backlog(client, teacher_token, ui_feedback)

    assert formula_item["priority"] == "P1"
    assert formula_item["category"] == "formula_ocr"
    assert permission_item["priority"] == "P0"
    assert permission_item["category"] == "security_privacy"
    assert ui_item["priority"] == "P3"
    assert ui_item["category"] == "frontend_ux"
    assert formula_item["acceptance_criteria"]


def test_backlog_status_updates(client, app_module, student_token, teacher_token):
    feedback_id = make_feedback(client, app_module, student_token, "evidence_error", "high")
    item = convert_to_backlog(client, teacher_token, feedback_id)

    for status in ["planned", "in_progress", "done"]:
        response = client.post(
            f"/api/backlog/{item['id']}/update-status",
            json={"status": status},
            headers=auth_header(teacher_token),
        )
        assert response.status_code == 200
        item = response.get_json()["backlog_item"]
        assert item["status"] == status
    assert item["closed_at"]

    list_response = client.get("/api/backlog", headers=auth_header(teacher_token))
    assert list_response.status_code == 200
    assert any(entry["id"] == item["id"] for entry in list_response.get_json()["data"]["items"])
