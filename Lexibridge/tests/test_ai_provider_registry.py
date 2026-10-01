from services.ai_registry import can_default_provider, is_placeholder_secret, validate_ai_config


def test_provider_registry_seed_and_default_uniqueness(app_module):
    with app_module.app.app_context():
        app_module.ensure_ai_registry_seed()
        default_count = app_module.AIProviderConfig.query.filter_by(is_default=True).count()
        assert default_count == 1

        mock = app_module.AIProviderConfig(
            provider_name="mock",
            provider_mode="mock",
            default_model="mock",
            is_enabled=True,
            is_default=False,
            created_at=app_module.current_time_text(),
        )
        local = app_module.AIProviderConfig(
            provider_name="local_heuristic",
            provider_mode="local_heuristic",
            default_model="local_heuristic",
            is_enabled=True,
            is_default=False,
            created_at=app_module.current_time_text(),
        )
        deepseek = app_module.AIProviderConfig(
            provider_name="deepseek",
            provider_mode="live",
            default_model="deepseek-chat",
            is_enabled=True,
            is_default=False,
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add_all([mock, local, deepseek])
        app_module.db.session.commit()

        assert app_module.AIProviderConfig.query.filter_by(provider_name="mock").first()
        assert app_module.AIProviderConfig.query.filter_by(provider_name="local_heuristic").first()
        assert app_module.AIProviderConfig.query.filter_by(provider_name="deepseek").first()


def test_production_forbids_mock_default_and_placeholder_keys():
    allowed, reasons = can_default_provider("mock", "mock", app_env="production")
    assert allowed is False
    assert reasons
    assert is_placeholder_secret("your-deepseek-api-key-here")
    errors, _ = validate_ai_config("production", {
        "AI_PROVIDER": "deepseek",
        "AI_PROVIDER_MODE": "live",
        "DEEPSEEK_API_KEY": "your-api-key-here",
        "ALLOW_MOCK_AI": "false",
        "ALLOW_LOCAL_HEURISTIC_AI": "false",
        "AI_LOG_PROMPT_FULL": "false",
        "AI_LOG_RESPONSE_FULL": "false",
        "AI_LOG_REDACT_SECRETS": "true",
        "AI_DAILY_CALL_LIMIT_PER_USER": "10",
        "AI_MONTHLY_CALL_LIMIT_PER_USER": "100",
        "AI_DAILY_COST_LIMIT_PER_USER": "1.00",
        "AI_PROVIDER_HEALTHCHECK_ENABLED": "true",
    })
    assert any("placeholder" in error.lower() for error in errors)


def test_provider_health_status_can_update(app_module):
    with app_module.app.app_context():
        app_module.ensure_ai_registry_seed()
        config = app_module.AIProviderConfig.query.first()
        config.health_status = "degraded"
        app_module.db.session.commit()
        assert app_module.AIProviderConfig.query.get(config.id).health_status == "degraded"
