import ast
import importlib.util
import inspect
import sys
from pathlib import Path

from flask import Flask

from routes.shared import RouteCoreDependencies


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "backend" / "routes" / "legacy_provider_admin_healthcheck.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "legacy_provider_admin_healthcheck_routes",
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


class DummySession:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1


class DummyDb:
    session = DummySession()


class DummyQuery:
    def filter_by(self, **kwargs):
        return self

    def all(self):
        return []


class DummyAIProviderConfig:
    query = DummyQuery()


def dummy_core_dependencies():
    return RouteCoreDependencies(
        db=DummyDb(),
        audit_record_model=object,
        audit_record_service=object(),
        current_time_text=lambda: "2026-07-16T00:00:00Z",
        require_current_user=lambda roles: (type("User", (), {"id": 1})(), None),
        get_route_audit_context=lambda user=None: {"request_id": "dummy"},
        attach_request_id_to_response=lambda response, audit_context: response,
        api_success_with_audit_context=lambda data=None, message="", audit_context=None: data,
        api_error_with_audit_context=lambda *args, **kwargs: ({"status": "error"}, 400),
    )


def test_healthcheck_module_import_boundary_and_signature():
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
    assert not any("ai_provider" in name for name in imports)
    assert not any("alignment_verification" in name for name in imports)

    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "ensure_ai_registry_seed" not in source
    assert "healthcheck_provider" not in source
    assert "provider_from_selection" not in source
    assert "os.environ" not in source
    assert "api_key" not in source
    assert "Authorization" not in source
    assert "Cookie" not in source
    assert "AICallLog" not in source
    assert "AlignmentProviderUsageRecord" not in source
    assert "AlignmentVerificationRun" not in source
    assert "AlignmentProviderPreflightRun" not in source
    assert "ConceptAlignmentCard" not in source
    assert "AuditRecord" not in source
    assert ".commit()" in source
    assert ".rollback()" not in source

    module = load_module()
    assert hasattr(module, "register_legacy_provider_admin_healthcheck_routes")
    assert hasattr(module, "LegacyProviderAdminHealthcheckModels")
    assert hasattr(module, "LegacyProviderAdminHealthcheckSerializers")

    signature = inspect.signature(module.register_legacy_provider_admin_healthcheck_routes)
    assert "core" in signature.parameters
    assert "models" in signature.parameters
    assert "serializers" in signature.parameters
    assert "registry_seed_service" in signature.parameters
    assert "seed_models" in signature.parameters
    assert "provider_selection_factory" in signature.parameters
    assert "default_prompts" in signature.parameters
    assert "model_version_factory" in signature.parameters
    assert "local_readiness_service" in signature.parameters
    assert "credential_presence_resolver" in signature.parameters
    assert "healthcheck_provider" not in signature.parameters
    assert "provider_transport" not in signature.parameters


def test_healthcheck_register_function_registers_expected_route_and_is_idempotent():
    module = load_module()
    app = Flask("legacy-provider-healthcheck-route-test")

    module.register_legacy_provider_admin_healthcheck_routes(
        app,
        core=dummy_core_dependencies(),
        models=module.LegacyProviderAdminHealthcheckModels(
            AIProviderConfig=DummyAIProviderConfig,
        ),
        serializers=module.LegacyProviderAdminHealthcheckSerializers(
            api_success=lambda data=None, message="Operation completed.": {
                "status": "success",
                "message": message,
                "data": data or {},
            },
        ),
        registry_seed_service=lambda **kwargs: None,
        seed_models=object(),
        provider_selection_factory=lambda: object(),
        default_prompts=[],
        model_version_factory=lambda: "local-mvp-v1",
        local_readiness_service=lambda **kwargs: type(
            "Result",
            (),
            {
                "health_updates": {"health_status": "healthy"},
                "to_payload": lambda self: {"provider_name": "mock", "health_status": "healthy"},
            },
        )(),
        credential_presence_resolver=lambda config: False,
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
        "/api/admin/ai/healthcheck": {
            "endpoint": "admin_ai_healthcheck",
            "methods": {"POST"},
        },
    }

    module.register_legacy_provider_admin_healthcheck_routes(
        app,
        core=dummy_core_dependencies(),
        models=module.LegacyProviderAdminHealthcheckModels(
            AIProviderConfig=DummyAIProviderConfig,
        ),
        serializers=module.LegacyProviderAdminHealthcheckSerializers(
            api_success=lambda data=None, message="Operation completed.": data,
        ),
        registry_seed_service=lambda **kwargs: None,
        seed_models=object(),
        provider_selection_factory=lambda: object(),
        default_prompts=[],
        model_version_factory=lambda: "local-mvp-v1",
        local_readiness_service=lambda **kwargs: object(),
        credential_presence_resolver=lambda config: False,
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
