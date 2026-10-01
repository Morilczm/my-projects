import ast
import importlib.util
import inspect
import sys
from pathlib import Path

from flask import Flask

from routes.shared import RouteCoreDependencies


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "backend" / "routes" / "legacy_provider_admin_observability.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "legacy_provider_admin_observability_routes",
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

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return []


class DummyAICallLog:
    id = object()
    query = DummyQuery()


class DummyAIProviderConfig:
    id = object()
    query = DummyQuery()


class DummyDb:
    session = object()


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


def test_observability_module_import_boundary_and_signature():
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
    assert "db.session.commit" not in source
    assert "db.session.rollback" not in source
    assert "healthcheck_provider" not in source
    assert "provider_from_selection" not in source
    assert "AlignmentVerificationRun" not in source
    assert "AlignmentProviderUsageRecord" not in source
    assert "os.environ" not in source

    module = load_module()
    assert hasattr(module, "register_legacy_provider_admin_observability_routes")
    assert hasattr(module, "LegacyProviderAdminObservabilityModels")
    assert hasattr(module, "LegacyProviderAdminObservabilitySerializers")

    signature = inspect.signature(module.register_legacy_provider_admin_observability_routes)
    assert "core" in signature.parameters
    assert "models" in signature.parameters
    assert "serializers" in signature.parameters
    assert "registry_seed_service" in signature.parameters


def test_observability_register_function_registers_expected_routes_and_is_idempotent():
    module = load_module()
    app = Flask("legacy-provider-admin-observability-route-test")
    models = module.LegacyProviderAdminObservabilityModels(
        AICallLog=DummyAICallLog,
        AIProviderConfig=DummyAIProviderConfig,
    )
    serializers = module.LegacyProviderAdminObservabilitySerializers(
        api_success=lambda data=None, message="Operation completed.": {"status": "success", "message": message, "data": data or {}},
        serialize_ai_call_log=lambda log: {},
        serialize_ai_provider_config=lambda config: {},
        summarize_ai_calls=lambda logs: {"total_calls": len(logs)},
    )

    module.register_legacy_provider_admin_observability_routes(
        app,
        core=dummy_core_dependencies(),
        models=models,
        serializers=serializers,
        registry_seed_service=lambda owner_user_id=0: None,
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
        "/api/admin/ai/calls": {"endpoint": "admin_ai_calls", "methods": {"GET"}},
        "/api/admin/ai/usage": {"endpoint": "admin_ai_usage", "methods": {"GET"}},
        "/api/admin/ai/health": {"endpoint": "admin_ai_health", "methods": {"GET"}},
    }

    module.register_legacy_provider_admin_observability_routes(
        app,
        core=dummy_core_dependencies(),
        models=models,
        serializers=serializers,
        registry_seed_service=lambda owner_user_id=0: None,
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
