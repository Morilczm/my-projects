import ast
import dataclasses
from pathlib import Path

from routes.shared import RouteCoreDependencies


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "backend" / "routes" / "document_alignment_workflow_routes.py"


def test_route_module_is_thin_and_uses_add_url_rule():
    source = MODULE.read_text(encoding="utf-8")
    tree = ast.parse(source)

    assert "app.add_url_rule" in source
    assert "@app.route" not in source
    assert "Blueprint" not in source
    assert "db.session" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "BackgroundJob" not in source
    assert "processing_orchestrator" not in source
    assert "alignment_providers" not in source
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and "backend.app" in ast.unparse(node)
        for node in ast.walk(tree)
    )


def test_route_dependencies_are_frozen_and_route_core_remains_nine_fields():
    from routes.document_alignment_workflow_routes import (
        DocumentAlignmentWorkflowRouteDependencies,
    )

    assert len(dataclasses.fields(RouteCoreDependencies)) == 9
    assert [field.name for field in dataclasses.fields(DocumentAlignmentWorkflowRouteDependencies)] == [
        "admission_dependencies_factory",
        "query_dependencies_factory",
        "start_service",
        "get_run_service",
        "list_items_service",
    ]
    assert DocumentAlignmentWorkflowRouteDependencies.__dataclass_params__.frozen is True


def test_runtime_routes_are_registered_once_with_expected_endpoints(app_module):
    expected = {
        ("/api/document-alignment-runs", "POST", "create_document_alignment_run"),
        ("/api/document-alignment-runs/<run_uid>", "GET", "get_document_alignment_run"),
        ("/api/document-alignment-runs/<run_uid>/items", "GET", "list_document_alignment_run_items"),
    }
    actual = set()
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            actual.add((rule.rule, method, rule.endpoint))
    assert expected <= actual
    for path, method, endpoint in expected:
        assert sum(1 for item in actual if item == (path, method, endpoint)) == 1


def test_route_import_does_not_execute_services(monkeypatch):
    import importlib
    import routes.document_alignment_workflow_routes as module

    calls = []
    monkeypatch.setattr(module, "start_document_alignment_workflow", lambda *args: calls.append(args))
    importlib.reload(module)
    assert calls == []


def test_idempotency_key_rejects_control_characters():
    from routes.document_alignment_workflow_routes import _validate_idempotency_key

    for value in ("contains\ttab", "contains\nnewline", "contains\x7fdelete"):
        try:
            _validate_idempotency_key(value)
        except ValueError:
            pass
        else:
            raise AssertionError("control character was accepted")
