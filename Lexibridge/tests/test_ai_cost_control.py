def set_default_mock(app_module):
    app_module.AIProviderConfig.query.update({"is_default": False})
    app_module.db.session.add(app_module.AIProviderConfig(
        provider_name="mock",
        provider_mode="mock",
        default_model="mock",
        is_enabled=True,
        is_default=True,
        created_at=app_module.current_time_text(),
    ))
    app_module.db.session.commit()


def test_ai_usage_and_estimated_cost_recorded(app_module):
    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        set_default_mock(app_module)
        result = app_module.call_ai_task(
            "term_alignment",
            {"english_term": "Convolution", "translation_candidate_hint": "卷积"},
            "term_alignment",
            "v1",
            user_id=user.id,
        )
        assert result["status"] == "success"
        assert result["usage"]["input_tokens"] > 0
        assert result["usage"]["output_tokens"] > 0
        assert app_module.UsageRecord.query.filter_by(user_id=user.id, action_type="ai_alignment_call").count() >= 1


def test_ai_daily_quota_exceeded(app_module):
    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email="student.test@lexibridge.local").first()
        set_default_mock(app_module)
        old_limit = app_module.AI_DAILY_CALL_LIMIT_PER_USER
        app_module.AI_DAILY_CALL_LIMIT_PER_USER = 0
        try:
            result = app_module.call_ai_task(
                "term_alignment",
                {"english_term": "Wavelength", "translation_candidate_hint": "波长"},
                "term_alignment",
                "v1",
                user_id=user.id,
            )
        finally:
            app_module.AI_DAILY_CALL_LIMIT_PER_USER = old_limit
        assert result["status"] == "error"
        assert result["error_code"] == "QUOTA_EXCEEDED"


def test_admin_ai_usage_summary_endpoint(app_module, client, admin_token):
    response = client.get("/api/admin/ai/usage", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert "summary" in payload
    assert "total_calls" in payload["summary"]
