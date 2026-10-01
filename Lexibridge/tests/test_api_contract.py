from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


CORE_PATHS = {
    "/api/auth/register": ["post"],
    "/api/auth/login": ["post"],
    "/api/auth/logout": ["post"],
    "/api/auth/me": ["get"],
    "/api/courses": ["get", "post"],
    "/api/courses/mine": ["get"],
    "/api/courses/{course_id}/join": ["post"],
    "/api/documents/upload": ["post"],
    "/api/documents": ["get"],
    "/api/documents/{document_id}/chunks": ["get"],
    "/api/knowledge/search": ["get"],
    "/api/alignment/run": ["post"],
    "/api/alignment/runs": ["get"],
    "/api/alignment/runs/{run_id}": ["get"],
    "/api/jobs": ["get"],
    "/api/jobs/{job_id}": ["get"],
    "/api/jobs/{job_id}/events": ["get"],
    "/api/jobs/{job_id}/cancel": ["post"],
    "/api/jobs/{job_id}/retry": ["post"],
    "/api/terminology/cards": ["get"],
    "/api/terminology/cards/{card_id}": ["get"],
    "/api/terminology/cards/{card_id}/favorite": ["post"],
    "/api/terminology/cards/{card_id}/mastered": ["post"],
    "/api/terminology/cards/{card_id}/feedback": ["post"],
    "/api/terminology/cards/export": ["get"],
    "/api/quality-control": ["get"],
    "/api/quality-control/{card_id}/approve": ["post"],
    "/api/quality-control/{card_id}/reject": ["post"],
    "/api/quality-control/{card_id}/edit": ["post"],
    "/api/quality-control/{card_id}/needs-more-evidence": ["post"],
    "/api/feedback": ["get", "post"],
    "/api/feedback/{feedback_id}": ["get"],
    "/api/feedback/{feedback_id}/triage": ["post"],
    "/api/feedback/{feedback_id}/resolve": ["post"],
    "/api/feedback/{feedback_id}/reject": ["post"],
    "/api/feedback/{feedback_id}/convert-to-evaluation": ["post"],
    "/api/feedback/{feedback_id}/convert-to-backlog": ["post"],
    "/api/backlog": ["get"],
    "/api/backlog/{item_id}": ["get"],
    "/api/backlog/{item_id}/update-status": ["post"],
    "/api/pilot/report": ["get"],
    "/api/evaluation/sets": ["get", "post"],
    "/api/evaluation/items/import": ["post"],
    "/api/evaluation/items": ["get"],
    "/api/evaluation/run": ["post"],
    "/api/evaluation/runs": ["get"],
    "/api/evaluation/runs/{run_id}": ["get"],
    "/api/admin/users": ["get"],
    "/api/admin/usage": ["get"],
    "/api/admin/billing": ["get"],
    "/api/admin/logs": ["get"],
    "/api/admin/ingestion-jobs": ["get"],
    "/api/admin/ai/providers": ["get"],
    "/api/admin/ai/models": ["get"],
    "/api/admin/ai/prompts": ["get", "post"],
    "/api/admin/ai/calls": ["get"],
    "/api/admin/ai/usage": ["get"],
    "/api/admin/ai/health": ["get"],
    "/api/admin/ai/healthcheck": ["post"],
}


def load_contract():
    path = ROOT / "docs" / "openapi.yaml"
    assert path.exists()
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def test_openapi_paths_and_operation_contracts(app_module):
    contract = load_contract()
    assert contract["openapi"] == "3.0.3"
    paths = contract["paths"]
    root_security = contract.get("security")
    for path, methods in CORE_PATHS.items():
        assert path in paths
        for method in methods:
            operation = paths[path].get(method)
            assert operation, f"{method.upper()} {path} missing"
            assert operation.get("summary")
            assert operation.get("security", root_security) is not None
            if method in {"post", "put", "patch"} and path not in {"/api/auth/logout", "/api/courses/{course_id}/join"}:
                assert "requestBody" in operation or "parameters" in operation
            if "{" in path:
                assert operation.get("parameters")
            assert "200" in operation["responses"]
            assert any(code in operation["responses"] for code in ["400", "401", "403", "404", "413", "415", "422"])

    enum_codes = set(contract["components"]["schemas"]["ApiError"]["properties"]["error_code"]["enum"])
    assert enum_codes == set(app_module.ERROR_CODES.keys())


def test_openapi_upload_export_and_alignment_evaluation_shapes():
    contract = load_contract()
    upload = contract["paths"]["/api/documents/upload"]["post"]["requestBody"]["content"]
    assert "multipart/form-data" in upload
    assert upload["multipart/form-data"]["schema"]["properties"]["file"]["format"] == "binary"

    export = contract["paths"]["/api/terminology/cards/export"]["get"]["responses"]["200"]["content"]
    assert "application/pdf" in export

    alignment_run = contract["paths"]["/api/alignment/run"]["post"]
    assert "requestBody" in alignment_run
    assert "200" in alignment_run["responses"]

    evaluation_run = contract["paths"]["/api/evaluation/run"]["post"]
    assert "requestBody" in evaluation_run
    assert "200" in evaluation_run["responses"]


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def assert_error_code(response, status_code, error_code):
    assert response.status_code == status_code
    payload = response.get_json()
    assert payload["status"] == "error"
    assert payload["error_code"] == error_code
    assert "message" in payload
    assert "details" in payload


def test_core_api_error_envelopes(client, student_token, teacher_token):
    assert_error_code(
        client.post("/api/auth/register", json={"username": "ab", "email": "bad", "password": "x"}),
        400,
        "VALIDATION_ERROR",
    )
    assert_error_code(
        client.get("/api/knowledge/search", headers=bearer(student_token)),
        400,
        "VALIDATION_ERROR",
    )
    assert_error_code(
        client.post("/api/alignment/run", json={"scope_type": "course"}, headers=bearer(teacher_token)),
        403,
        "PERMISSION_DENIED",
    )
    assert_error_code(
        client.get("/api/alignment/runs/999999", headers=bearer(teacher_token)),
        404,
        "RESOURCE_NOT_FOUND",
    )
    assert_error_code(
        client.post("/api/evaluation/run", json={"evaluation_set_id": 999999}, headers=bearer(teacher_token)),
        404,
        "RESOURCE_NOT_FOUND",
    )
    assert_error_code(
        client.get("/api/does-not-exist", headers=bearer(student_token)),
        404,
        "RESOURCE_NOT_FOUND",
    )
