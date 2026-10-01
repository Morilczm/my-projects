import pytest

from document_alignment_workflow_route_support import bearer, cleanup, create_governed_source
from routes.document_alignment_workflow_routes import (
    ADMISSION_OUTCOME_HTTP_STATUS,
    QUERY_OUTCOME_HTTP_STATUS,
)


@pytest.fixture(autouse=True)
def clean_formal_route_state(app_module):
    with app_module.app.app_context():
        cleanup(app_module)
    yield
    with app_module.app.app_context():
        cleanup(app_module)


@pytest.mark.parametrize(
    "source_overrides,expected_status,expected_code",
    [
        ({"trust_level": "untrusted"}, 422, "DOCUMENT_ALIGNMENT_SOURCE_NOT_GOVERNED"),
        ({"parse_status": "failed"}, 422, "DOCUMENT_ALIGNMENT_PARSE_BLOCKED"),
        ({"quality_status": "parse_failed"}, 422, "DOCUMENT_ALIGNMENT_PARSE_BLOCKED"),
        ({"source_status": "disabled"}, 404, "DOCUMENT_ALIGNMENT_SOURCE_NOT_AVAILABLE"),
    ],
)
def test_admission_outcome_http_mapping(
    client, app_module, teacher_token, source_overrides, expected_status, expected_code
):
    with app_module.app.app_context():
        source = create_governed_source(app_module, **source_overrides)
    response = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": source.source_uid},
        headers={
            **bearer(teacher_token),
            "Idempotency-Key": f"mapping-{expected_code}",
            "X-Request-ID": "mapping-request-9c5f",
        },
    )
    assert response.status_code == expected_status
    assert response.get_json()["error_code"] == expected_code
    assert response.get_json()["request_id"] == "mapping-request-9c5f"


def test_malformed_json_and_missing_source_have_safe_400(client, teacher_token):
    headers = {
        **bearer(teacher_token),
        "Idempotency-Key": "mapping-invalid-json",
        "X-Request-ID": "mapping-invalid-request",
    }
    malformed = client.post(
        "/api/document-alignment-runs",
        data="{not-json",
        content_type="application/json",
        headers=headers,
    )
    missing = client.post("/api/document-alignment-runs", json={}, headers=headers)
    assert malformed.status_code == missing.status_code == 400
    assert malformed.get_json()["error_code"] == "DOCUMENT_ALIGNMENT_INVALID_REQUEST"
    assert "traceback" not in str(malformed.get_json()).casefold()


def test_all_typed_service_outcomes_have_explicit_http_mapping():
    assert ADMISSION_OUTCOME_HTTP_STATUS == {
        "invalid_request": 400,
        "source_not_available": 404,
        "source_not_governed": 422,
        "parse_blocked": 422,
        "no_usable_chunks": 422,
        "idempotency_conflict": 409,
        "persistence_error": 500,
    }
    assert QUERY_OUTCOME_HTTP_STATUS == {
        "not_found": 404,
        "forbidden": 404,
        "invalid_request": 400,
        "persistence_error": 500,
    }
