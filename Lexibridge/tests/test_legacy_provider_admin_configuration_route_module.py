import ast
import importlib.util
import inspect
import sys
from pathlib import Path

from flask import Flask

from routes.shared import RouteCoreDependencies


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "backend" / "routes" / "legacy_provider_admin_configuration.py"


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


def dummy_seed_service(**kwargs):
    return object()


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


def test_configuration_module_import_boundary_and_signature():
    assert MODULE_PATH.exists()
    imports = set(imports_for(MODULE_PATH))
    assert "backend.app" not in imports
    assert "app" not in imports
    assert "os" not in imports
    assert "socket" not in imports
    assert "urllib.request" not in imports
    assert "requests" not in imports
    assert "httpx" not in imports
    assert not any("transport" in name for name in imports)
    assert not any("ai_health" in name for name in imports)
    assert not any("alignment_verification" in name for name in imports)

    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "ensure_ai_registry_seed" not in source
    assert "db.session.commit" not in source
    assert "db.session.rollback" not in source
    assert "healthcheck_provider" not in source
    assert "provider_from_selection" not in source
    assert "AlignmentVerificationRun" not in source
    assert "AlignmentProviderUsageRecord" not in source
    assert "os.environ" not in source

    module = load_module()
    assert hasattr(module, "register_legacy_provider_admin_configuration_routes")
    assert hasattr(module, "LegacyProviderAdminConfigurationModels")
    assert hasattr(module, "LegacyProviderAdminConfigurationSerializers")

    signature = inspect.signature(module.register_legacy_provider_admin_configuration_routes)
    assert "core" in signature.parameters
    assert "models" in signature.parameters
    assert "serializers" in signature.parameters
    assert "registry_seed_service" in signature.parameters
    assert "prompt_mutation_service" in signature.parameters
    assert "prompt_mutation_dependencies" in signature.parameters
    assert "prompt_post_handler" not in signature.parameters


def test_configuration_register_function_registers_expected_routes_and_is_idempotent():
    module = load_module()
    app = Flask("legacy-provider-admin-configuration-route-test")
    models = module.LegacyProviderAdminConfigurationModels(
        AIProviderConfig=DummyAIProviderConfig,
        AIModelRegistry=DummyAIModelRegistry,
        PromptTemplate=DummyPromptTemplate,
    )
    serializers = module.LegacyProviderAdminConfigurationSerializers(
        api_success=lambda data=None, message="Operation completed.": {
            "status": "success",
            "message": message,
            "data": data or {},
        },
        api_error=lambda error_code, message, status_code: ({"status": "error"}, status_code),
        serialize_ai_provider_config=lambda provider: {},
        serialize_ai_model_registry=lambda model: {},
        serialize_prompt_template=lambda prompt: {},
        current_provider_metadata=lambda: {},
    )

    module.register_legacy_provider_admin_configuration_routes(
        app,
        core=dummy_core_dependencies(),
        models=models,
        serializers=serializers,
        registry_seed_service=dummy_seed_service,
        seed_models=object(),
        provider_selection_factory=lambda: object(),
        default_prompts=[],
        model_version_factory=lambda: "local-mvp-v1",
        prompt_mutation_service=lambda **kwargs: type(
            "Result",
            (),
            {
                "outcome": "created",
                "prompt": object(),
                "message": "Prompt saved.",
                "error_code": None,
            },
        )(),
        prompt_mutation_dependencies=object(),
    )
    first = {
        rule.rule: {
            "endpoint": rule.endpoint,
            "methods": {method for method in rule.methods if method not in {"HEAD", "OPTIONS"}},
        }
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/admin/ai/")
    }
    assert first == {
        "/api/admin/ai/providers": {"endpoint": "admin_ai_providers", "methods": {"GET"}},
        "/api/admin/ai/models": {"endpoint": "admin_ai_models", "methods": {"GET"}},
        "/api/admin/ai/prompts": {"endpoint": "admin_ai_prompts", "methods": {"GET", "POST"}},
    }

    module.register_legacy_provider_admin_configuration_routes(
        app,
        core=dummy_core_dependencies(),
        models=models,
        serializers=serializers,
        registry_seed_service=dummy_seed_service,
        seed_models=object(),
        provider_selection_factory=lambda: object(),
        default_prompts=[],
        model_version_factory=lambda: "local-mvp-v1",
        prompt_mutation_service=lambda **kwargs: type(
            "Result",
            (),
            {
                "outcome": "created",
                "prompt": object(),
                "message": "Prompt saved.",
                "error_code": None,
            },
        )(),
        prompt_mutation_dependencies=object(),
    )
    second = {
        rule.rule: {
            "endpoint": rule.endpoint,
            "methods": {method for method in rule.methods if method not in {"HEAD", "OPTIONS"}},
        }
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/admin/ai/")
    }
    assert second == first
