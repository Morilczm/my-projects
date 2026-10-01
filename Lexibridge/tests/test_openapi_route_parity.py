from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "docs" / "openapi.yaml"


REQUIRED_ROUTE_METHODS = {
    "/api/document-alignment-runs": {"post"},
    "/api/document-alignment-runs/{run_uid}": {"get"},
    "/api/document-alignment-runs/{run_uid}/items": {"get"},
    "/api/documents/upload": {"post"},
    "/api/knowledge/search": {"get"},
    "/api/evidence/search": {"post"},
    "/api/evidence/bilingual": {"post"},
    "/api/terms/chinese-candidates": {"post"},
    "/api/concept-cards": {"get", "post"},
    "/api/concept-cards/draft-from-evidence": {"post"},
    "/api/concept-cards/review-queue": {"get"},
    "/api/concept-cards/{card_uid}": {"get"},
    "/api/concept-cards/{card_uid}/reviews": {"get"},
    "/api/concept-cards/{card_uid}/review": {"post"},
    "/api/concept-cards/{card_uid}/assign-reviewer": {"post"},
    "/api/alignment/verify": {"post"},
    "/api/alignment/providers": {"get"},
    "/api/alignment/providers/{provider_name}/policy": {"get", "post"},
    "/api/alignment/providers/{provider_name}/usage": {"get"},
    "/api/alignment/providers/{provider_name}/preflight": {"get", "post"},
    "/api/alignment/providers/preflight/{preflight_uid}": {"get"},
    "/api/review-policies": {"get", "post"},
    "/api/review-policies/{policy_uid}": {"get"},
    "/api/review-permissions": {"get", "post"},
    "/api/review-permissions/{permission_uid}/revoke": {"post"},
    "/api/student/courses": {"get"},
    "/api/student/course-memberships": {"get", "post"},
    "/api/student/course-memberships/{membership_uid}/revoke": {"post"},
    "/api/course-student-visibility-policies": {"get", "post"},
    "/api/student/concept-cards": {"get"},
    "/api/student/concept-cards/{card_uid}": {"get"},
    "/api/student/concept-cards/{card_uid}/state": {"post"},
    "/api/student/concept-cards/{card_uid}/feedback": {"post"},
    "/api/student/concept-cards/export": {"get"},
    "/api/student/progress": {"get"},
    "/api/concept-cards/student-feedback-queue": {"get"},
    "/api/concept-cards/{card_uid}/student-feedback": {"get"},
    "/api/concept-cards/student-feedback/{feedback_uid}/triage": {"post"},
    "/api/teacher/learning-analytics": {"get"},
    "/api/teacher/learning-analytics/cards": {"get"},
    "/api/teacher/learning-analytics/export": {"get"},
}


def load_openapi_paths():
    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    return contract["paths"]


def normalize_flask_rule(rule: str) -> str:
    normalized = rule
    replacements = {
        "<int:course_id>": "{course_id}",
        "<int:document_id>": "{document_id}",
        "<int:job_id>": "{job_id}",
        "<int:run_id>": "{run_id}",
        "<int:version_id>": "{version_id}",
        "<int:card_id>": "{card_id}",
        "<int:feedback_id>": "{feedback_id}",
        "<path:provider_name>": "{provider_name}",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    while "<" in normalized and ">" in normalized:
        start = normalized.index("<")
        end = normalized.index(">", start)
        name = normalized[start + 1:end]
        if ":" in name:
            name = name.split(":", 1)[1]
        normalized = normalized[:start] + "{" + name + "}" + normalized[end + 1:]
    return normalized


def actual_api_routes(app_module):
    routes = {}
    for rule in app_module.app.url_map.iter_rules():
        path = normalize_flask_rule(str(rule))
        if not path.startswith("/api/"):
            continue
        methods = {method.lower() for method in rule.methods if method not in {"HEAD", "OPTIONS"}}
        routes.setdefault(path, set()).update(methods)
    return routes


def test_main_chain_openapi_routes_match_flask_routes(app_module):
    openapi_paths = load_openapi_paths()
    actual_routes = actual_api_routes(app_module)

    missing_in_flask = []
    missing_in_openapi = []
    method_mismatches = []

    for path, methods in REQUIRED_ROUTE_METHODS.items():
        if path not in actual_routes:
            missing_in_flask.append(path)
            continue
        if path not in openapi_paths:
            missing_in_openapi.append(path)
            continue
        documented = {method for method in openapi_paths[path] if method in {"get", "post", "put", "patch", "delete"}}
        missing_methods = methods - actual_routes[path]
        undocumented_methods = methods - documented
        if missing_methods or undocumented_methods:
            method_mismatches.append({
                "path": path,
                "required": sorted(methods),
                "actual": sorted(actual_routes.get(path, set())),
                "documented": sorted(documented),
            })

    assert missing_in_flask == []
    assert missing_in_openapi == []
    assert method_mismatches == []


def test_openapi_main_chain_paths_point_to_real_routes(app_module):
    actual_routes = actual_api_routes(app_module)
    openapi_paths = load_openapi_paths()
    for path in REQUIRED_ROUTE_METHODS:
        assert path in actual_routes
        assert path in openapi_paths
