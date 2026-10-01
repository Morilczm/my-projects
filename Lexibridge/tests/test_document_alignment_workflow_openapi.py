from pathlib import Path

import yaml

from services.document_alignment_workflow_contract import DOCUMENT_ALIGNMENT_ITEM_STATUSES


ROOT = Path(__file__).resolve().parents[1]
OPENAPI = ROOT / "docs" / "openapi.yaml"


def test_formal_workflow_openapi_is_structured_and_matches_runtime(app_module):
    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    paths = contract["paths"]
    expected = {
        "/api/document-alignment-runs": "post",
        "/api/document-alignment-runs/{run_uid}": "get",
        "/api/document-alignment-runs/{run_uid}/items": "get",
    }
    actual = {
        str(rule).replace("<run_uid>", "{run_uid}"): {
            method.lower() for method in rule.methods - {"HEAD", "OPTIONS"}
        }
        for rule in app_module.app.url_map.iter_rules()
    }
    for path, method in expected.items():
        assert method in paths[path]
        assert method in actual[path]

    post = paths["/api/document-alignment-runs"]["post"]
    assert post["operationId"] == "create_document_alignment_run"
    idempotency = next(parameter for parameter in post["parameters"] if parameter["name"] == "Idempotency-Key")
    assert idempotency["required"] is True
    assert idempotency["schema"]["maxLength"] == 128
    assert "202" in post["responses"]
    assert "Location" in post["responses"]["202"]["headers"]

    items = paths["/api/document-alignment-runs/{run_uid}/items"]["get"]
    assert paths["/api/document-alignment-runs/{run_uid}"]["get"]["operationId"] == "get_document_alignment_run"
    assert items["operationId"] == "list_document_alignment_run_items"
    params = {parameter["name"]: parameter for parameter in items["parameters"]}
    assert params["page_size"]["schema"]["maximum"] == 100
    assert set(params["status"]["schema"]["enum"]) == set(DOCUMENT_ALIGNMENT_ITEM_STATUSES)
    assert {"400", "401", "403", "404", "409", "415", "422", "500"} <= set(post["responses"])


def test_openapi_does_not_expose_transport_or_execution_internals():
    contract = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    formal = {
        key: value
        for key, value in contract["paths"].items()
        if key.startswith("/api/document-alignment-runs")
    }
    text = str(formal).casefold()
    for forbidden in (
        "lease_token",
        "worker_id",
        "execution_attempt",
        "execution_key",
        "input_fingerprint",
        "job_uid",
        "backgroundjob",
        "raw evidence",
        "raw output",
        "credential",
    ):
        assert forbidden not in text
