import ast
import importlib.util
import inspect
import sys
from pathlib import Path

from flask import Flask

from routes.shared import RouteCoreDependencies


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "backend" / "routes" / "admin_alignment_runs.py"


class DummyQuery:
    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return []


class DummyAlignmentRun:
    id = object()
    query = DummyQuery()


class DummyDb:
    session = object()


def load_module():
    module_name = "admin_alignment_runs_route_module_test"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous
    return module


def dummy_core():
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


def imports_for_module():
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return set(imports)


def test_admin_alignment_runs_module_import_boundary():
    module = load_module()
    assert hasattr(module, "register_admin_alignment_run_routes")
    imports = imports_for_module()
    assert "backend.app" not in imports
    assert "app" not in imports
    assert "os" not in imports
    assert not any(name.startswith("services") for name in imports)


def test_admin_alignment_runs_static_boundary_has_no_writes_or_provider_execution():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "AlignmentVerificationRun" not in imported_names | imported_from_names
    assert "AlignmentProviderUsageRecord" not in imported_names | imported_from_names
    assert "AlignmentProviderPolicy" not in imported_names | imported_from_names
    assert "AlignmentProviderPreflightRun" not in imported_names | imported_from_names
    assert "ConceptAlignmentCard" not in imported_names | imported_from_names
    assert "commit" not in source
    assert "rollback" not in source
    assert "transport" not in source
    assert "provider.call" not in source
    assert "os.environ" not in source


def test_admin_alignment_runs_register_signature_and_route_contract():
    module = load_module()
    signature = inspect.signature(module.register_admin_alignment_run_routes)
    assert "core" in signature.parameters
    assert "models" in signature.parameters
    assert "serialize_alignment_run" in signature.parameters
    assert "provider_transport" not in signature.parameters
    assert "run_query_service" not in signature.parameters

    app = Flask("admin-alignment-runs-route-module-test")
    module.register_admin_alignment_run_routes(
        app,
        core=dummy_core(),
        models=module.AdminAlignmentRunModels(AlignmentRun=DummyAlignmentRun),
        serialize_alignment_run=lambda run: {},
    )
    routes = {
        (rule.rule, method): rule.endpoint
        for rule in app.url_map.iter_rules()
        for method in rule.methods - {"HEAD", "OPTIONS"}
        if rule.rule == "/api/admin/alignment-runs"
    }
    assert routes == {("/api/admin/alignment-runs", "GET"): "admin_alignment_runs"}

    module.register_admin_alignment_run_routes(
        app,
        core=dummy_core(),
        models=module.AdminAlignmentRunModels(AlignmentRun=DummyAlignmentRun),
        serialize_alignment_run=lambda run: {},
    )
    assert sum(
        1
        for rule in app.url_map.iter_rules()
        if rule.rule == "/api/admin/alignment-runs" and "GET" in rule.methods
    ) == 1


def test_existing_app_has_single_admin_alignment_runs_route(app_module):
    routes = {
        (rule.rule, method): rule.endpoint
        for rule in app_module.app.url_map.iter_rules()
        for method in rule.methods - {"HEAD", "OPTIONS"}
        if rule.rule == "/api/admin/alignment-runs"
    }
    assert routes == {("/api/admin/alignment-runs", "GET"): "admin_alignment_runs"}
    assert sum(
        1
        for rule in app_module.app.url_map.iter_rules()
        if rule.rule == "/api/admin/alignment-runs" and "GET" in rule.methods
    ) == 1
