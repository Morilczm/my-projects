import ast
import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path

from flask import Flask

from routes.shared import RouteCoreDependencies


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "backend" / "routes" / "legacy_provider_admin_configuration.py"
APP_PATH = ROOT / "backend" / "app.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "legacy_provider_admin_configuration_routes",
        MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
    return module


def imports_for(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return imports


class DummyQuery:
    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return []


class DummyAIProviderConfig:
    id = object()
    is_default = object()
    query = DummyQuery()


class DummyAIModelRegistry:
    provider_name = object()
    id = object()
    query = DummyQuery()


class DummyPromptTemplate:
    prompt_key = object()
    id = object()
    query = DummyQuery()


class DummyDb:
    session = object()


@dataclass(frozen=True)
class DummyMutationDependencies:
    marker: str = "mutation-dependencies"


def dummy_core_dependencies():
    return RouteCoreDependencies(
        db=DummyDb(),
        audit_record_model=object,
        audit_record_service=object(),
        current_time_text=lambda: "",
        require_current_user=lambda roles: (None, None),
        get_route_audit_context=lambda user=None: {"request_id": "dummy"},
        attach_request_id_to_response=lambda response, audit_context: response,
        api_success_with_audit_context=lambda data=None, message="", audit_context=None: data,
        api_error_with_audit_context=lambda *args, **kwargs: ({"status": "error"}, 400),
    )


def dummy_serializers(module):
    return module.LegacyProviderAdminConfigurationSerializers(
        api_success=lambda data=None, message="Operation completed.": {
            "status": "success",
            "message": message,
            "data": data or {},
        },
        api_error=lambda error_code, message, status_code: ({"status": "error", "error_code": error_code}, status_code),
        serialize_ai_provider_config=lambda provider: {},
        serialize_ai_model_registry=lambda model: {},
        serialize_prompt_template=lambda prompt: {},
        current_provider_metadata=lambda: {},
    )


def dummy_models(module):
    return module.LegacyProviderAdminConfigurationModels(
        AIProviderConfig=DummyAIProviderConfig,
        AIModelRegistry=DummyAIModelRegistry,
        PromptTemplate=DummyPromptTemplate,
    )


def target_route_summary(app):
    return {
        rule.rule: {
            "endpoint": rule.endpoint,
            "methods": {method for method in rule.methods if method not in {"HEAD", "OPTIONS"}},
        }
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/admin/ai/")
    }


def test_prompt_mutation_route_module_boundary_and_signature():
    imports = set(imports_for(MODULE_PATH))
    assert "backend.app" not in imports
    assert "app" not in imports
    assert "os" not in imports
    assert "socket" not in imports
    assert "urllib.request" not in imports
    assert "requests" not in imports
    assert "httpx" not in imports
    assert not any("transport" in name for name in imports)
    assert not any("adapter" in name for name in imports)

    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "prompt_post_handler" not in source
    assert "db.session.commit" not in source
    assert "db.session.rollback" not in source
    assert "PromptTemplate(" not in source
    assert "models.PromptTemplate.query.filter_by" not in source
    assert "prompt_mutation_service(" in source
    assert "LegacyPromptMutationRequest.from_payload" in source

    app_source = APP_PATH.read_text(encoding="utf-8")
    assert "def admin_ai_prompts_post_handler" not in app_source
    assert "prompt_post_handler" not in app_source

    module = load_module()
    signature = inspect.signature(module.register_legacy_provider_admin_configuration_routes)
    assert "core" in signature.parameters
    assert "models" in signature.parameters
    assert "serializers" in signature.parameters
    assert "registry_seed_service" in signature.parameters
    assert "prompt_mutation_service" in signature.parameters
    assert "prompt_mutation_dependencies" in signature.parameters
    assert "prompt_post_handler" not in signature.parameters

    from routes.shared import RouteCoreDependencies as ImportedCoreDependencies

    assert len(ImportedCoreDependencies.__dataclass_fields__) == 9


def test_prompt_mutation_route_module_registers_shared_get_post_rule_without_callback():
    module = load_module()
    app = Flask("legacy-prompt-mutation-route-module-test")
    mutation_calls = []

    def mutation_service(*, request, dependencies):
        mutation_calls.append((request, dependencies))
        return type(
            "Result",
            (),
            {
                "outcome": "created",
                "prompt": object(),
                "message": "Prompt saved.",
                "error_code": None,
            },
        )()

    module.register_legacy_provider_admin_configuration_routes(
        app,
        core=dummy_core_dependencies(),
        models=dummy_models(module),
        serializers=dummy_serializers(module),
        registry_seed_service=lambda **kwargs: None,
        seed_models=object(),
        provider_selection_factory=lambda: object(),
        default_prompts=[],
        model_version_factory=lambda: "local-mvp-v1",
        prompt_mutation_service=mutation_service,
        prompt_mutation_dependencies=DummyMutationDependencies(),
    )
    first = target_route_summary(app)
    assert first == {
        "/api/admin/ai/providers": {"endpoint": "admin_ai_providers", "methods": {"GET"}},
        "/api/admin/ai/models": {"endpoint": "admin_ai_models", "methods": {"GET"}},
        "/api/admin/ai/prompts": {"endpoint": "admin_ai_prompts", "methods": {"GET", "POST"}},
    }

    module.register_legacy_provider_admin_configuration_routes(
        app,
        core=dummy_core_dependencies(),
        models=dummy_models(module),
        serializers=dummy_serializers(module),
        registry_seed_service=lambda **kwargs: None,
        seed_models=object(),
        provider_selection_factory=lambda: object(),
        default_prompts=[],
        model_version_factory=lambda: "local-mvp-v1",
        prompt_mutation_service=mutation_service,
        prompt_mutation_dependencies=DummyMutationDependencies(),
    )
    assert target_route_summary(app) == first
