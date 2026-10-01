import ast
import importlib
import json
import socket
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from services.legacy_provider_registry_seed import (
    LegacyProviderRegistrySeedModels,
    ensure_legacy_provider_registry_seed,
)


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "backend" / "services" / "legacy_provider_registry_seed.py"
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4J"


def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError(f"network access attempted: args={args!r}")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(urllib.request, "urlopen", blocked)
    for module_name in ("requests", "httpx"):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        if hasattr(module, "request"):
            monkeypatch.setattr(module, "request", blocked)


def imports_for(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return imports


def models_for(app_module):
    return LegacyProviderRegistrySeedModels(
        AIProviderConfig=app_module.AIProviderConfig,
        AIModelRegistry=app_module.AIModelRegistry,
        PromptTemplate=app_module.PromptTemplate,
    )


def selection(**overrides):
    data = {
        "provider_name": "mock",
        "provider_mode": "mock",
        "model_name": "mock-rule-v1",
        "base_url": "",
        "api_key": SENTINEL,
        "timeout_seconds": 45,
        "max_retries": 2,
        "cost_per_1k_input_tokens": 0.0,
        "cost_per_1k_output_tokens": 0.0,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def seed_counts(app_module):
    return {
        "providers": app_module.AIProviderConfig.query.count(),
        "models": app_module.AIModelRegistry.query.count(),
        "prompts": app_module.PromptTemplate.query.count(),
    }


def reset_seed_tables(app_module):
    app_module.PromptTemplate.query.delete()
    app_module.AIModelRegistry.query.delete()
    app_module.AIProviderConfig.query.delete()
    app_module.db.session.commit()


def call_service(app_module, **overrides):
    return ensure_legacy_provider_registry_seed(
        db=app_module.db,
        models=models_for(app_module),
        selection=selection(**overrides),
        default_prompts=app_module.DEFAULT_PROMPTS,
        current_time_text=app_module.current_time_text,
        model_version="local-mvp-v1",
        owner_user_id=42,
    )


def test_seed_service_static_boundary():
    imports = set(imports_for(SERVICE_PATH))
    assert "flask" not in imports
    assert "backend.app" not in imports
    assert "backend.routes" not in imports
    assert "os" not in imports
    assert not any("transport" in item for item in imports)

    source = SERVICE_PATH.read_text(encoding="utf-8")
    assert "db.session.commit" not in source
    assert "db.session.rollback" not in source
    assert "os.environ" not in source
    assert "api_key" not in source
    assert "healthcheck_provider" not in source
    assert "provider_from_selection" not in source


def test_seed_service_first_and_repeated_call_are_idempotent_without_commit_or_rollback(
    app_module,
    monkeypatch,
):
    no_network(monkeypatch)
    with app_module.app.app_context():
        reset_seed_tables(app_module)
        with monkeypatch.context() as patch:
            patch.setattr(app_module.db.session, "commit", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("commit called")))
            patch.setattr(app_module.db.session, "rollback", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("rollback called")))
            first = call_service(app_module)
            assert first.created_provider is True
            assert first.created_model is True
            assert first.created_prompt_count == len(app_module.DEFAULT_PROMPTS)
            assert seed_counts(app_module) == {
                "providers": 1,
                "models": 1,
                "prompts": len(app_module.DEFAULT_PROMPTS),
            }
            second = call_service(app_module)
            assert second.created_provider is False
            assert second.created_model is False
            assert second.created_prompt_count == 0
            assert seed_counts(app_module) == {
                "providers": 1,
                "models": 1,
                "prompts": len(app_module.DEFAULT_PROMPTS),
            }
        app_module.db.session.rollback()


def test_seed_service_caller_rollback_and_commit_own_persistence(app_module):
    with app_module.app.app_context():
        reset_seed_tables(app_module)
        call_service(app_module)
        assert seed_counts(app_module)["providers"] == 1
        app_module.db.session.rollback()
        assert seed_counts(app_module) == {"providers": 0, "models": 0, "prompts": 0}

        result = call_service(app_module)
        app_module.db.session.commit()
        assert result.provider_config.id is not None
        assert seed_counts(app_module) == {
            "providers": 1,
            "models": 1,
            "prompts": len(app_module.DEFAULT_PROMPTS),
        }

        call_service(app_module)
        app_module.db.session.commit()
        assert seed_counts(app_module) == {
            "providers": 1,
            "models": 1,
            "prompts": len(app_module.DEFAULT_PROMPTS),
        }


def test_seed_service_handles_partial_existing_records_without_duplicates(app_module):
    with app_module.app.app_context():
        reset_seed_tables(app_module)
        provider = app_module.AIProviderConfig(
            provider_name="mock",
            provider_mode="mock",
            default_model="mock-rule-v1",
            is_enabled=True,
            is_default=True,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        prompt_default = app_module.DEFAULT_PROMPTS[0]
        prompt = app_module.PromptTemplate(
            prompt_key=prompt_default["prompt_key"],
            prompt_version=prompt_default["prompt_version"],
            task_type=prompt_default["task_type"],
            language=prompt_default["language"],
            template_text=prompt_default["template_text"],
            json_schema=json.dumps(prompt_default["json_schema"], ensure_ascii=False),
            is_active=True,
            is_default=True,
            created_by=99,
            created_at=app_module.current_time_text(),
            updated_at=app_module.current_time_text(),
        )
        app_module.db.session.add_all([provider, prompt])
        app_module.db.session.commit()

        result = call_service(app_module)
        assert result.created_provider is False
        assert result.created_model is True
        assert result.created_prompt_count == len(app_module.DEFAULT_PROMPTS) - 1
        app_module.db.session.commit()

        assert app_module.AIProviderConfig.query.filter_by(provider_name="mock").count() == 1
        assert app_module.AIModelRegistry.query.filter_by(
            provider_name="mock",
            model_name="mock-rule-v1",
        ).count() == 1
        for item in app_module.DEFAULT_PROMPTS:
            assert app_module.PromptTemplate.query.filter_by(
                prompt_key=item["prompt_key"],
                prompt_version=item["prompt_version"],
            ).count() == 1


def test_seed_service_flush_exception_is_left_to_caller_transaction(app_module, monkeypatch):
    with app_module.app.app_context():
        reset_seed_tables(app_module)
        original_flush = app_module.db.session.flush
        calls = {"count": 0}

        def failing_flush(*args, **kwargs):
            calls["count"] += 1
            raise RuntimeError("flush failed for seed service test")

        monkeypatch.setattr(app_module.db.session, "flush", failing_flush)
        try:
            try:
                call_service(app_module)
            except RuntimeError as exc:
                assert "flush failed" in str(exc)
            else:
                raise AssertionError("seed service did not propagate flush failure")
            assert calls["count"] == 1
        finally:
            monkeypatch.setattr(app_module.db.session, "flush", original_flush)
            app_module.db.session.rollback()

        assert seed_counts(app_module) == {"providers": 0, "models": 0, "prompts": 0}


def test_seed_service_does_not_persist_sentinel_credential(app_module, monkeypatch):
    no_network(monkeypatch)
    with app_module.app.app_context():
        reset_seed_tables(app_module)
        call_service(app_module)
        app_module.db.session.commit()
        rows = {
            "providers": [
                {
                    "provider_name": item.provider_name,
                    "provider_mode": item.provider_mode,
                    "base_url": item.base_url,
                    "default_model": item.default_model,
                }
                for item in app_module.AIProviderConfig.query.all()
            ],
            "models": [
                {
                    "provider_name": item.provider_name,
                    "model_name": item.model_name,
                    "known_risks_json": item.known_risks_json,
                }
                for item in app_module.AIModelRegistry.query.all()
            ],
            "prompts": [
                {
                    "prompt_key": item.prompt_key,
                    "prompt_version": item.prompt_version,
                    "notes": item.notes,
                }
                for item in app_module.PromptTemplate.query.all()
            ],
        }
        assert SENTINEL not in json.dumps(rows, ensure_ascii=False)
