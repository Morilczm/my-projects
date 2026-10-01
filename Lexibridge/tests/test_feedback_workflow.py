from test_pilot_feedback import auth_header, create_visible_card


def submit_feedback(client, token, card_id, feedback_type="translation_error", severity="medium", expected="傅里叶变换"):
    response = client.post(
        f"/api/terminology/cards/{card_id}/feedback",
        json={
            "feedback_type": feedback_type,
            "severity": severity,
            "reported_issue": "Pilot feedback issue",
            "expected_result": expected,
        },
        headers=auth_header(token),
    )
    assert response.status_code == 200
    return response.get_json()["data"]["feedback_id"]


def test_feedback_status_flow_and_resolve_requires_note(client, app_module, student_token, teacher_token):
    with app_module.app.app_context():
        card = create_visible_card(app_module)
        card_id = card.id

    feedback_id = submit_feedback(client, student_token, card_id)

    triaged = client.post(
        f"/api/feedback/{feedback_id}/triage",
        json={"status": "triaged"},
        headers=auth_header(teacher_token),
    )
    assert triaged.status_code == 200
    assert triaged.get_json()["feedback"]["status"] == "triaged"

    in_review = client.post(
        f"/api/feedback/{feedback_id}/triage",
        json={"status": "in_review"},
        headers=auth_header(teacher_token),
    )
    assert in_review.status_code == 200

    missing_note = client.post(
        f"/api/feedback/{feedback_id}/resolve",
        json={"resolution_action": "no_action_needed"},
        headers=auth_header(teacher_token),
    )
    assert missing_note.status_code == 400
    assert missing_note.get_json()["error_code"] == "VALIDATION_ERROR"

    resolved = client.post(
        f"/api/feedback/{feedback_id}/resolve",
        json={"resolution_action": "card_updated", "resolution_note": "Teacher corrected the explanation."},
        headers=auth_header(teacher_token),
    )
    assert resolved.status_code == 200
    payload = resolved.get_json()["feedback"]
    assert payload["status"] == "resolved"
    assert payload["resolved_by"]
    assert payload["resolved_at"]


def test_rejected_feedback_does_not_change_approved_card(client, app_module, student_token, teacher_token):
    with app_module.app.app_context():
        card = create_visible_card(app_module, status="approved")
        card_id = card.id

    feedback_id = submit_feedback(client, student_token, card_id, feedback_type="ui_confusion", severity="low")
    rejected = client.post(
        f"/api/feedback/{feedback_id}/reject",
        json={"resolution_note": "Not a terminology issue."},
        headers=auth_header(teacher_token),
    )
    assert rejected.status_code == 200
    assert rejected.get_json()["feedback"]["status"] == "rejected"
    with app_module.app.app_context():
        card = app_module.db.session.get(app_module.TerminologyCard, card_id)
        assert card.status == "approved"


def test_convert_feedback_to_evaluation_item_once(client, app_module, student_token, teacher_token):
    with app_module.app.app_context():
        card = create_visible_card(app_module)
        teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        evaluation_set = app_module.EvaluationSet(
            name="pilot_feedback_eval",
            course_id=card.course_id,
            discipline="signal_processing",
            description="Pilot feedback regression set",
            created_by=teacher.id,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        app_module.db.session.add(evaluation_set)
        app_module.db.session.commit()
        card_id = card.id
        set_id = evaluation_set.id

    feedback_id = submit_feedback(client, student_token, card_id, expected="傅里叶变换")
    first = client.post(
        f"/api/feedback/{feedback_id}/convert-to-evaluation",
        json={"evaluation_set_id": set_id},
        headers=auth_header(teacher_token),
    )
    second = client.post(
        f"/api/feedback/{feedback_id}/convert-to-evaluation",
        json={"evaluation_set_id": set_id},
        headers=auth_header(teacher_token),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()["data"]["evaluation_item_id"] == second.get_json()["data"]["evaluation_item_id"]
    with app_module.app.app_context():
        item = app_module.db.session.get(app_module.EvaluationItem, first.get_json()["data"]["evaluation_item_id"])
        tags = app_module.safe_json_loads(item.tags_json, [])
        assert "pilot_feedback" in tags
