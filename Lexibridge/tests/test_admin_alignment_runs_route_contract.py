import json
import socket
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C4G"


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError(f"network access attempted: args={args!r}")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)


def route_map(app_module):
    result = {}
    for rule in app_module.app.url_map.iter_rules():
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            result[(rule.rule, method)] = rule.endpoint
    return result


def side_effect_counts(app_module):
    return {
        "alignment_runs": app_module.AlignmentRun.query.count(),
        "verification_runs": app_module.AlignmentVerificationRun.query.count(),
        "provider_usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "provider_policy": app_module.AlignmentProviderPolicy.query.count(),
        "provider_preflight": app_module.AlignmentProviderPreflightRun.query.count(),
        "concept_cards": app_module.ConceptAlignmentCard.query.count(),
        "review_records": app_module.ConceptCardReviewRecord.query.count(),
        "audit_records": app_module.AuditRecord.query.count(),
    }


def assert_no_secret_like_data(payload):
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    forbidden = [
        SENTINEL,
        "Authorization",
        "Cookie",
        "private key",
        "api_key",
        "bearer ",
        "password",
        "secret",
    ]
    for item in forbidden:
        assert item.lower() not in serialized.lower()


def create_alignment_run(app_module, *, provider, status, term_count=1, error_message=""):
    run = app_module.AlignmentRun(
        triggered_by=0,
        provider=provider,
        model_name=f"{provider}-model",
        ai_provider=provider,
        ai_provider_mode="mock",
        ai_model=f"{provider}-model",
        prompt_key="term_alignment",
        prompt_version="v1",
        retrieval_version="test",
        term_count=term_count,
        status=status,
        metrics_json=json.dumps({"safe_summary": provider}, ensure_ascii=False),
        error_message=error_message,
        started_at=app_module.current_time_text(),
        finished_at=app_module.current_time_text(),
    )
    app_module.db.session.add(run)
    app_module.db.session.flush()
    return run


def create_unrelated_sensitive_provider_records(app_module):
    verification_run = app_module.AlignmentVerificationRun(
        english_term="sensitive source",
        chinese_term="敏感源",
        provider_name="fake-llm-v1",
        provider_type="fake",
        output_payload=json.dumps({"provider_output": SENTINEL}, ensure_ascii=False),
        raw_output_summary=json.dumps({"raw": SENTINEL}, ensure_ascii=False),
        prompt_summary=json.dumps({"prompt": SENTINEL}, ensure_ascii=False),
        error_message=SENTINEL,
    )
    usage = app_module.AlignmentProviderUsageRecord(
        provider_name="fake-llm-v1",
        provider_type="fake",
        request_id=SENTINEL,
        error_message=SENTINEL,
    )
    policy = app_module.AlignmentProviderPolicy(
        provider_name=f"sentinel-policy-{SENTINEL}",
        provider_type="fake",
        status="disabled",
        allowed_courses=json.dumps([SENTINEL], ensure_ascii=False),
        allowed_roles=json.dumps(["admin"], ensure_ascii=False),
    )
    preflight = app_module.AlignmentProviderPreflightRun(
        provider_name="fake-llm-v1",
        provider_type="fake",
        requested_by=SENTINEL,
        policy_summary=json.dumps({"policy": SENTINEL}, ensure_ascii=False),
        check_results=json.dumps({"environment": SENTINEL}, ensure_ascii=False),
    )
    app_module.db.session.add_all([verification_run, usage, policy, preflight])


def test_admin_alignment_runs_route_contract_and_permissions(
    app_module,
    client,
    admin_token,
    teacher_token,
    student_token,
):
    actual = route_map(app_module)
    assert actual[("/api/admin/alignment-runs", "GET")] == "admin_alignment_runs"
    assert ("/api/admin/alignment-runs", "POST") not in actual

    assert client.get("/api/admin/alignment-runs").status_code == 401
    assert client.get("/api/admin/alignment-runs", headers=bearer(student_token)).status_code == 403
    assert client.get("/api/admin/alignment-runs", headers=bearer(teacher_token)).status_code == 403

    with app_module.app.app_context():
        old = create_alignment_run(app_module, provider="old-provider", status="queued", term_count=1)
        middle = create_alignment_run(app_module, provider="middle-provider", status="failed", term_count=2)
        newest = create_alignment_run(app_module, provider="new-provider", status="completed", term_count=3)
        create_unrelated_sensitive_provider_records(app_module)
        app_module.db.session.commit()
        expected_ids = [newest.id, middle.id, old.id]
        before = side_effect_counts(app_module)

    response = client.get(
        "/api/admin/alignment-runs",
        headers={**bearer(admin_token), "X-Request-ID": "admin-alignment-runs-contract"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"status", "runs"}
    assert payload["status"] == "success"
    assert "request_id" not in payload
    assert "pagination" not in payload
    assert "data" not in payload
    assert [run["id"] for run in payload["runs"][:3]] == expected_ids
    assert len(payload["runs"]) <= 300
    first = payload["runs"][0]
    assert {
        "id",
        "document_id",
        "course_id",
        "triggered_by",
        "provider",
        "model_name",
        "ai_provider",
        "ai_provider_mode",
        "ai_model",
        "prompt_key",
        "prompt_version",
        "retrieval_version",
        "terms_extracted",
        "cards_created",
        "term_count",
        "card_created_count",
        "auto_approved_count",
        "qc_count",
        "needs_evidence_count",
        "conflict_count",
        "failed_count",
        "status",
        "metrics",
        "error_message",
        "started_at",
        "finished_at",
    } == set(first)
    assert first["provider"] == "new-provider"
    assert first["status"] == "completed"
    assert_no_secret_like_data(payload)

    with app_module.app.app_context():
        assert side_effect_counts(app_module) == before


def test_admin_alignment_runs_ignores_query_filters_and_remains_read_only(
    app_module,
    client,
    admin_token,
    monkeypatch,
):
    no_network(monkeypatch)
    with app_module.app.app_context():
        keep = create_alignment_run(app_module, provider="ignored-filter-provider", status="completed")
        app_module.db.session.commit()
        keep_id = keep.id
        before = side_effect_counts(app_module)

    response = client.get(
        "/api/admin/alignment-runs"
        "?provider=no-such-provider&status=failed&course=hidden&card_uid=missing"
        "&date_from=1900-01-01&date_to=1900-01-02&page=999&per_page=1",
        headers=bearer(admin_token),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) == {"status", "runs"}
    assert any(run["id"] == keep_id for run in payload["runs"])
    assert "pagination" not in payload
    assert_no_secret_like_data(payload)

    with app_module.app.app_context():
        assert side_effect_counts(app_module) == before


def test_admin_alignment_runs_openapi_contract_is_currently_absent():
    contract = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    assert "/api/admin/alignment-runs" not in contract["paths"]
