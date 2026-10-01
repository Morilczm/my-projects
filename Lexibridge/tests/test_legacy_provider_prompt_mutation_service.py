import ast
import importlib
import json
import os
import socket
import urllib.request
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

import pytest

from services.legacy_provider_prompt_mutation import (
    LEGACY_PROMPT_MUTATION_POLICY,
    LegacyPromptMutationDependencies,
    LegacyPromptMutationRequest,
    LegacyPromptMutationResult,
    execute_legacy_prompt_mutation,
)
from services.legacy_provider_registry_seed import (
    LegacyProviderRegistrySeedModels,
    ensure_legacy_provider_registry_seed,
)


ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "backend" / "services" / "legacy_provider_prompt_mutation.py"
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4Q"


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


def prompt_counts(app_module, prompt_key, prompt_version="v1"):
    return app_module.PromptTemplate.query.filter_by(
        prompt_key=prompt_key,
        prompt_version=prompt_version,
    ).count()


def side_effect_counts(app_module):
    return {
        "audit_records": app_module.AuditRecord.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_calls": app_module.AICallLog.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
    }


def make_dependencies(app_module):
    seed_models = LegacyProviderRegistrySeedModels(
        AIProviderConfig=app_module.AIProviderConfig,
        AIModelRegistry=app_module.AIModelRegistry,
        PromptTemplate=app_module.PromptTemplate,
    )

    def seed_registry(owner_user_id):
        return ensure_legacy_provider_registry_seed(
            db=app_module.db,
            models=seed_models,
            selection=app_module.env_provider_selection(os.environ),
            default_prompts=app_module.DEFAULT_PROMPTS,
            current_time_text=app_module.current_time_text,
            model_version=os.environ.get("MODEL_VERSION", "local-mvp-v1"),
            owner_user_id=owner_user_id,
        )

    return LegacyPromptMutationDependencies(
        db=app_module.db,
        PromptTemplate=app_module.PromptTemplate,
        current_time_text=app_module.current_time_text,
        safe_json_loads=app_module.safe_json_loads,
        seed_registry=seed_registry,
    )


def request_from(payload, *, actor_user_id=1):
    return LegacyPromptMutationRequest.from_payload(payload, actor_user_id=actor_user_id)


def fetch_prompt(app_module, prompt_key, prompt_version="v1"):
    return app_module.PromptTemplate.query.filter_by(
        prompt_key=prompt_key,
        prompt_version=prompt_version,
    ).one()


def test_prompt_mutation_service_static_boundary_and_dtos_are_frozen():
    imports = set(imports_for(SERVICE_PATH))
    assert "flask" not in imports
    assert "backend.app" not in imports
    assert "backend.routes" not in imports
    assert "os" not in imports
    assert not any("transport" in item for item in imports)

    source = SERVICE_PATH.read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "api_key" not in source
    assert "Authorization" not in source
    assert "AuditRecord" not in source
    assert "healthcheck_provider" not in source
    assert "provider_from_selection" not in source

    request = LegacyPromptMutationRequest.from_payload(
        {"prompt_key": "immutable", "prompt_version": "v1"},
        actor_user_id=7,
    )
    with pytest.raises(FrozenInstanceError):
        request.prompt_key = "changed"

    result = LegacyPromptMutationResult.validation_error("VALIDATION_ERROR", "safe")
    with pytest.raises(FrozenInstanceError):
        result.message = "changed"

    assert LEGACY_PROMPT_MUTATION_POLICY == "LEGACY_PROMPT_MUTABLE_REVISION_V1"


def test_prompt_mutation_service_create_update_repeat_and_last_commit_wins(
    app_module,
    monkeypatch,
):
    no_network(monkeypatch)
    prompt_key = f"legacy_admin_9c4q_service_{uuid4().hex}"
    deps = make_dependencies(app_module)

    with app_module.app.app_context():
        app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).delete()
        app_module.db.session.commit()
        before = side_effect_counts(app_module)
        original_commit = app_module.db.session.commit
        commit_calls = []

        def tracked_commit():
            commit_calls.append("commit")
            return original_commit()

        monkeypatch.setattr(app_module.db.session, "commit", tracked_commit)

        create = execute_legacy_prompt_mutation(
            request=request_from(
                {
                    "prompt_key": prompt_key,
                    "prompt_version": "opaque-client-version",
                    "task_type": "term_alignment",
                    "language": "bilingual",
                    "template_text": "Use {term} and return JSON.",
                    "json_schema": {"type": "object", "properties": {"term": {"type": "string"}}},
                    "is_active": True,
                    "is_default": False,
                    "notes": "created",
                    "credential_metadata": {"api_key": SENTINEL},
                },
                actor_user_id=13,
            ),
            dependencies=deps,
        )
        assert create.outcome == "created"
        assert create.created is True
        assert create.prompt is not None
        assert commit_calls == ["commit"]
        prompt_id = create.prompt.id
        assert prompt_counts(app_module, prompt_key, "opaque-client-version") == 1
        prompt = fetch_prompt(app_module, prompt_key, "opaque-client-version")
        assert prompt.template_text == "Use {term} and return JSON."
        assert prompt.created_by == 13
        assert SENTINEL not in json.dumps(
            {
                "template_text": prompt.template_text,
                "json_schema": prompt.json_schema,
                "notes": prompt.notes,
            },
            ensure_ascii=False,
        )

        identical = execute_legacy_prompt_mutation(
            request=request_from(
                {
                    "prompt_key": prompt_key,
                    "prompt_version": "opaque-client-version",
                    "task_type": "term_alignment",
                    "language": "bilingual",
                    "template_text": "Use {term} and return JSON.",
                    "json_schema": {"type": "object", "properties": {"term": {"type": "string"}}},
                    "is_active": True,
                    "is_default": False,
                    "notes": "created",
                },
                actor_user_id=13,
            ),
            dependencies=deps,
        )
        assert identical.outcome == "updated"
        assert prompt_counts(app_module, prompt_key, "opaque-client-version") == 1

        first_write = execute_legacy_prompt_mutation(
            request=request_from(
                {
                    "prompt_key": prompt_key,
                    "prompt_version": "opaque-client-version",
                    "template_text": "first admin write",
                },
                actor_user_id=13,
            ),
            dependencies=deps,
        )
        second_write = execute_legacy_prompt_mutation(
            request=request_from(
                {
                    "prompt_key": prompt_key,
                    "prompt_version": "opaque-client-version",
                    "template_text": "second admin write",
                },
                actor_user_id=13,
            ),
            dependencies=deps,
        )
        assert first_write.outcome == "updated"
        assert second_write.outcome == "updated"
        prompt = fetch_prompt(app_module, prompt_key, "opaque-client-version")
        assert prompt.id == prompt_id
        assert prompt.template_text == "second admin write"
        assert prompt_counts(app_module, prompt_key, "opaque-client-version") == 1

        different_version = execute_legacy_prompt_mutation(
            request=request_from(
                {
                    "prompt_key": prompt_key,
                    "prompt_version": "v2",
                    "template_text": "new mutable revision label",
                    "is_active": False,
                    "is_default": True,
                },
                actor_user_id=13,
            ),
            dependencies=deps,
        )
        assert different_version.outcome == "created"
        assert app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).count() == 2
        v2 = fetch_prompt(app_module, prompt_key, "v2")
        assert v2.is_active is False
        assert v2.is_default is True

        after = side_effect_counts(app_module)
        assert after == before


def test_prompt_mutation_service_validation_seed_and_commit_failures_rollback(
    app_module,
    monkeypatch,
):
    no_network(monkeypatch)
    deps = make_dependencies(app_module)
    prompt_key = f"legacy_admin_9c4q_rollback_{uuid4().hex}"

    with app_module.app.app_context():
        original_rollback = app_module.db.session.rollback
        rollback_calls = []

        def tracked_rollback():
            rollback_calls.append("rollback")
            return original_rollback()

        monkeypatch.setattr(app_module.db.session, "rollback", tracked_rollback)

        validation = execute_legacy_prompt_mutation(
            request=request_from({"prompt_version": "v1"}),
            dependencies=deps,
        )
        assert validation.outcome == "validation_error"
        assert validation.error_code == "VALIDATION_ERROR"
        assert rollback_calls == ["rollback"]
        assert prompt_counts(app_module, "", "v1") == 0

        def fail_seed(owner_user_id):
            raise RuntimeError("controlled seed failure")

        seed_failure = execute_legacy_prompt_mutation(
            request=request_from({"prompt_key": prompt_key, "prompt_version": "v1"}),
            dependencies=LegacyPromptMutationDependencies(
                db=app_module.db,
                PromptTemplate=app_module.PromptTemplate,
                current_time_text=app_module.current_time_text,
                safe_json_loads=app_module.safe_json_loads,
                seed_registry=fail_seed,
            ),
        )
        assert seed_failure.outcome == "persistence_error"
        assert rollback_calls[-1] == "rollback"
        assert app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).first() is None

        original_commit = app_module.db.session.commit

        def fail_commit():
            raise RuntimeError("controlled commit failure")

        monkeypatch.setattr(app_module.db.session, "commit", fail_commit)
        commit_failure = execute_legacy_prompt_mutation(
            request=request_from({"prompt_key": prompt_key, "prompt_version": "v1"}),
            dependencies=deps,
        )
        assert commit_failure.outcome == "persistence_error"
        assert rollback_calls[-1] == "rollback"
        assert app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).first() is None

        monkeypatch.setattr(app_module.db.session, "commit", original_commit)
        recovery = execute_legacy_prompt_mutation(
            request=request_from({"prompt_key": f"{prompt_key}_recovery", "prompt_version": "v1"}),
            dependencies=deps,
        )
        assert recovery.outcome == "created"


def test_prompt_mutation_service_preserves_duplicate_first_row_behavior(app_module):
    prompt_key = f"legacy_admin_9c4q_duplicate_{uuid4().hex}"
    deps = make_dependencies(app_module)
    with app_module.app.app_context():
        app_module.PromptTemplate.query.filter_by(prompt_key=prompt_key).delete()
        now = app_module.current_time_text()
        first = app_module.PromptTemplate(
            prompt_key=prompt_key,
            prompt_version="v1",
            task_type="first",
            template_text="first row",
            created_at=now,
            updated_at=now,
        )
        second = app_module.PromptTemplate(
            prompt_key=prompt_key,
            prompt_version="v1",
            task_type="second",
            template_text="second row",
            created_at=now,
            updated_at=now,
        )
        app_module.db.session.add_all([first, second])
        app_module.db.session.commit()
        first_id = first.id
        second_id = second.id

        result = execute_legacy_prompt_mutation(
            request=request_from(
                {
                    "prompt_key": prompt_key,
                    "prompt_version": "v1",
                    "template_text": "updated first logical match",
                }
            ),
            dependencies=deps,
        )
        assert result.outcome == "updated"
        rows = app_module.PromptTemplate.query.filter_by(
            prompt_key=prompt_key,
            prompt_version="v1",
        ).order_by(app_module.PromptTemplate.id.asc()).all()
        assert [row.id for row in rows] == [first_id, second_id]
        assert rows[0].template_text == "updated first logical match"
        assert rows[1].template_text == "second row"
