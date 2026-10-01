import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

from flask import Flask, jsonify

from routes import alignment_verification
from routes.shared import RouteCoreDependencies
from services.alignment_verification_execution import (
    AlignmentVerificationExecutionDependencies,
    AlignmentVerificationExecutionResult,
)


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "backend" / "routes" / "alignment_verification.py"


class DummyDb:
    session = object()


def _dummy_core(user=None):
    user = user or SimpleNamespace(
        id=7,
        email="teacher.route-module@example.test",
        role="teacher",
        username="Route Module Teacher",
    )

    def success(data=None, message="", audit_context=None):
        audit_context = audit_context or {}
        return jsonify(
            {
                "status": "success",
                "message": message,
                "data": data,
                "request_id": audit_context.get("request_id", ""),
            }
        )

    def error(error_code, message, http_status=None, audit_context=None, details=None):
        audit_context = audit_context or {}
        payload = {
            "status": "error",
            "error_code": error_code,
            "message": message,
            "request_id": audit_context.get("request_id", ""),
        }
        payload.update(details or {})
        return jsonify(payload), http_status or 400

    return RouteCoreDependencies(
        db=DummyDb(),
        audit_record_model=object,
        audit_record_service=object(),
        current_time_text=lambda: "2026-07-15T00:00:00Z",
        require_current_user=lambda roles: (user, None),
        get_route_audit_context=lambda current_user=None: {
            "request_id": "route-module-request",
            "actor_id": getattr(current_user, "id", None),
            "actor_role": getattr(current_user, "role", ""),
            "actor_name": getattr(current_user, "username", ""),
            "source": "api",
            "ip_hash": "hash",
            "user_agent_summary": "pytest",
        },
        attach_request_id_to_response=lambda response, audit_context: response,
        api_success_with_audit_context=success,
        api_error_with_audit_context=error,
    )


def _module_ast():
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def _imported_modules():
    imports = []
    for node in ast.walk(_module_ast()):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return set(imports)


def test_alignment_verification_route_module_import_boundary():
    imports = _imported_modules()
    assert "backend.app" not in imports
    assert "app" not in imports
    assert hasattr(alignment_verification, "register_alignment_verification_routes")
    assert hasattr(alignment_verification, "RouteCoreDependencies")
    assert hasattr(alignment_verification, "AlignmentVerificationExecutionDependencies")


def test_alignment_verification_route_module_avoids_domain_state_machine_dependencies():
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "AlignmentVerificationRun" not in source
    assert "AlignmentProviderUsageRecord" not in source
    assert "AlignmentProviderPolicy" not in source
    assert "ProviderPolicy" not in source
    assert "provider_transport" not in source
    assert "os.environ" not in source

    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"commit", "rollback"}


def test_alignment_verification_adapter_stays_thin():
    tree = _module_ast()
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "verify_alignment_api"
    ]
    assert len(functions) == 1
    handler = functions[0]
    assert handler.end_lineno - handler.lineno + 1 <= 80

    source = inspect.getsource(alignment_verification.register_alignment_verification_routes)
    assert "AlignmentVerificationRun" not in source
    assert "AlignmentProviderUsageRecord" not in source
    assert "record_alignment_provider_usage" not in source
    assert "verify_alignment(" not in source
    assert "apply_verification_result_to_card" not in source
    assert "execute_fn(" in source


def test_register_alignment_verification_route_and_adapter_payload_mapping():
    app = Flask("alignment-verification-route-module-test")
    calls = {}
    dependencies = object()

    def execute_fn(request, actor, context, deps):
        calls["request"] = request
        calls["actor"] = actor
        calls["context"] = context
        calls["deps"] = deps
        return AlignmentVerificationExecutionResult(
            outcome="success",
            status_code=200,
            payload={"provider_name": request.provider_name, "attach_to_card": request.attach_to_card},
            message="Verification complete.",
        )

    alignment_verification.register_alignment_verification_routes(
        app,
        core=_dummy_core(),
        execution_dependencies=lambda: dependencies,
        execute_fn=execute_fn,
    )

    first_rules = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.rule == "/api/alignment/verify" and "POST" in rule.methods
    ]
    assert len(first_rules) == 1
    assert first_rules[0].endpoint == "verify_alignment_api"

    alignment_verification.register_alignment_verification_routes(
        app,
        core=_dummy_core(),
        execution_dependencies=lambda: dependencies,
        execute_fn=execute_fn,
    )
    second_rules = [
        rule
        for rule in app.url_map.iter_rules()
        if rule.rule == "/api/alignment/verify" and "POST" in rule.methods
    ]
    assert len(second_rules) == 1

    response = app.test_client().post(
        "/api/alignment/verify",
        json={"provider_name": "fake-llm-v1", "card_uid": "card-1", "attach_to_card": "yes"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert body["request_id"] == "route-module-request"
    assert body["data"] == {"provider_name": "fake-llm-v1", "attach_to_card": True}

    assert calls["request"].provider_name == "fake-llm-v1"
    assert calls["request"].card_uid == "card-1"
    assert calls["request"].attach_to_card is True
    assert calls["actor"].role == "teacher"
    assert calls["context"].request_id == "route-module-request"
    assert calls["deps"] is dependencies


def test_existing_app_alignment_verification_endpoint_is_unique(app_module):
    rules = [
        rule
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/alignment/verify" and "POST" in rule.methods
    ]
    assert len(rules) == 1
    assert rules[0].endpoint == "verify_alignment_api"
    assert app_module.app.view_functions["verify_alignment_api"].__name__ == "verify_alignment_api"
