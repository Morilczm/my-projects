import os

from provider_admin_state_isolation import (
    SENTINEL_PREFIX,
    assert_provider_admin_state_clean,
    capture_provider_admin_state,
    restore_provider_admin_state,
)


SENTINEL = f"{SENTINEL_PREFIX}9C4O1"


def test_provider_admin_state_restore_clears_committed_sentinel_rows_and_globals(app_module):
    snapshot = capture_provider_admin_state(app_module)
    os.environ["DEEPSEEK_BASE_URL"] = f"https://example.invalid/{SENTINEL}"
    app_module.DEEPSEEK_BASE_URL = f"https://example.invalid/{SENTINEL}"
    with app_module.app.app_context():
        app_module.AIProviderConfig.query.filter(
            app_module.AIProviderConfig.base_url.contains(SENTINEL_PREFIX)
        ).delete(synchronize_session=False)
        provider = app_module.AIProviderConfig(
            provider_name="deepseek",
            provider_mode="live",
            base_url=f"https://example.invalid/{SENTINEL}",
            default_model="deepseek-chat",
            is_enabled=True,
            is_default=True,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        prompt = app_module.PromptTemplate(
            prompt_key=f"prompt-{SENTINEL}",
            prompt_version="v1",
            notes=f"secret-like metadata {SENTINEL}",
            created_at=app_module.current_time_text(),
        )
        app_module.db.session.add_all([provider, prompt])
        app_module.db.session.commit()
        assert app_module.AIProviderConfig.query.filter(
            app_module.AIProviderConfig.base_url.contains(SENTINEL)
        ).count() == 1

    restore_provider_admin_state(app_module, snapshot)

    assert os.environ.get("DEEPSEEK_BASE_URL") == snapshot.environ["DEEPSEEK_BASE_URL"]
    assert app_module.DEEPSEEK_BASE_URL == snapshot.module_globals["DEEPSEEK_BASE_URL"]
    assert_provider_admin_state_clean(app_module)


def test_provider_admin_state_restore_rolls_back_pending_sentinel_rows(app_module):
    snapshot = capture_provider_admin_state(app_module)
    with app_module.app.app_context():
        app_module.db.session.add(
            app_module.AIProviderConfig(
                provider_name=f"pending-{SENTINEL}",
                provider_mode="live",
                base_url=f"https://example.invalid/{SENTINEL}",
            )
        )
        assert app_module.db.session.new

    restore_provider_admin_state(app_module, snapshot)

    assert_provider_admin_state_clean(app_module)
