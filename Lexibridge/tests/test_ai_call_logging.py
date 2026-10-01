def set_default_provider(app_module, provider_name="mock", provider_mode="mock", model_name="mock"):
    app_module.AIProviderConfig.query.update({"is_default": False})
    config = app_module.AIProviderConfig(
        provider_name=provider_name,
        provider_mode=provider_mode,
        default_model=model_name,
        is_enabled=True,
        is_default=True,
        created_at=app_module.current_time_text(),
    )
    app_module.db.session.add(config)
    app_module.db.session.commit()
    return config


def test_successful_ai_call_writes_redacted_log(app_module):
    with app_module.app.app_context():
        user = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").first()
        set_default_provider(app_module, "mock", "mock", "mock")
        before = app_module.AICallLog.query.count()
        result = app_module.call_ai_task(
            task_type="term_alignment",
            prompt_key="term_alignment",
            prompt_version="v1",
            input_payload={
                "english_term": "Fourier Transform",
                "translation_candidate_hint": "傅里叶变换",
                "password": "Secret1234",
                "api_key": "sk-thismustnotappear",
            },
            user_id=user.id,
        )
        assert result["status"] == "success"
        assert app_module.AICallLog.query.count() == before + 1
        log = app_module.AICallLog.query.order_by(app_module.AICallLog.id.desc()).first()
        assert log.status == "success"
        assert log.request_hash
        assert log.response_hash
        assert "Secret1234" not in log.redacted_prompt_preview
        assert "sk-thismustnotappear" not in log.redacted_prompt_preview
        assert len(log.redacted_prompt_preview) <= 340
        assert len(log.redacted_response_preview) <= 360


def test_failed_ai_call_writes_error_log(app_module):
    with app_module.app.app_context():
        set_default_provider(app_module, "none", "none", "none")
        result = app_module.call_ai_task(
            task_type="term_alignment",
            prompt_key="term_alignment",
            prompt_version="v1",
            input_payload={"english_term": "Hash Table"},
        )
        assert result["status"] == "error"
        log = app_module.AICallLog.query.order_by(app_module.AICallLog.id.desc()).first()
        assert log.status == "error"
        assert log.error_code == "AI_PROVIDER_NOT_CONFIGURED"
