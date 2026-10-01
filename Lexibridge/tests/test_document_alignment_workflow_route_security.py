from pathlib import Path

import pytest

from document_alignment_workflow_query_support import cleanup as cleanup_query, create_scenario
from document_alignment_workflow_route_support import bearer, token_for_user


ROOT = Path(__file__).resolve().parents[1]
ROUTE = ROOT / "backend" / "routes" / "document_alignment_workflow_routes.py"
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C5F"


def test_route_has_no_actor_spoofing_cors_or_debug_bypass():
    source = ROUTE.read_text(encoding="utf-8")
    lowered = source.casefold()
    assert "access-control-allow-origin" not in lowered
    assert "debug_admin" not in lowered
    assert "?role=" not in lowered
    assert "actor_uid\")" not in source
    assert "provider transport" not in lowered


def test_query_responses_redact_hidden_sentinel_and_paths(client, app_module):
    with app_module.app.app_context():
        cleanup_query(app_module)
        scenario = create_scenario(
            app_module,
            item_count=1,
            source_filename=f"/private/internal/{SENTINEL}/source.pdf",
        )
        run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=scenario["run_uid"]).one()
        with pytest.raises(ValueError):
            run.error_message = f"Traceback Authorization: Bearer {SENTINEL}"
        run.error_message = "Safe root error summary."
        item = app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).one()
        with pytest.raises(ValueError):
            item.error_message = f"provider output secret={SENTINEL}"
        item.error_message = "Safe item error summary."
        app_module.db.session.commit()
        token = token_for_user(app_module, scenario["requester_id"])
    run_response = client.get(
        f"/api/document-alignment-runs/{scenario['run_uid']}", headers=bearer(token)
    )
    item_response = client.get(
        f"/api/document-alignment-runs/{scenario['run_uid']}/items", headers=bearer(token)
    )
    combined = str(run_response.get_json()) + str(item_response.get_json())
    assert SENTINEL not in combined
    assert "/private/internal" not in combined
    with app_module.app.app_context():
        cleanup_query(app_module)


def test_body_cannot_spoof_actor(client, teacher_token):
    response = client.post(
        "/api/document-alignment-runs",
        json={"source_uid": "source", "actor_uid": "1", "role": "admin"},
        headers={**bearer(teacher_token), "Idempotency-Key": "spoof-actor-9c5f"},
    )
    assert response.status_code == 400
    assert SENTINEL not in str(response.get_json())
