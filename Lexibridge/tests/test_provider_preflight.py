import json
import uuid

from services import audit_records
from services import provider_governance
from services import provider_preflight


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_provider(prefix="preflight-provider"):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def upsert_policy(app_module, provider_name, **overrides):
    policy, created = provider_governance.create_or_update_provider_policy(
        app_module.db.session,
        app_module.AlignmentProviderPolicy,
        provider_name,
        overrides,
        now_fn=app_module.current_time_text,
        commit=True,
    )
    return policy, created


def safe_replay_policy():
    return {
        "provider_type": "replay_llm",
        "enabled": True,
        "status": "active",
        "replay_only": True,
        "allow_external_calls": False,
        "allow_attach_to_card": False,
        "allow_production_result": False,
        "allow_auto_approve": False,
        "require_human_review": True,
        "allowed_courses": ["Preflight Course"],
        "blocked_courses": ["Blocked Preflight Course"],
        "allowed_roles": ["teacher", "admin"],
        "max_calls_per_day": 10,
        "max_calls_per_month": 100,
        "max_estimated_cost_per_call": 0.25,
        "max_estimated_cost_per_day": 1.0,
        "max_prompt_chars": 8000,
        "max_output_chars": 4000,
        "timeout_seconds": 30,
        "max_retries": 0,
    }


def test_preflight_model_and_serialization_do_not_store_api_key(app_module, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "TEST_KEY_VALUE_DO_NOT_RETURN")
    with app_module.app.app_context():
        config_check = provider_preflight.check_provider_config("deepseek-alignment-v1-disabled")
        run = app_module.AlignmentProviderPreflightRun(
            provider_name="deepseek-alignment-v1-disabled",
            provider_type="external_llm",
            check_status="failed",
            api_key_present=config_check["api_key_present"],
            api_key_env_name=config_check["api_key_env_name"],
            check_results={"api_key_present": config_check["api_key_present"]},
            blocking_reasons=["provider_policy_missing"],
            warnings=[],
        )
        app_module.db.session.add(run)
        app_module.db.session.commit()
        serialized = provider_preflight.serialize_preflight_run(run)
        payload = json.dumps(serialized, ensure_ascii=False)

        assert serialized["preflight_uid"]
        assert serialized["api_key_present"] is True
        assert serialized["api_key_env_name"] == "DEEPSEEK_API_KEY"
        assert "TEST_KEY_VALUE_DO_NOT_RETURN" not in payload


def test_preflight_service_detects_missing_policy_and_unsafe_policy_shapes(app_module):
    with app_module.app.app_context():
        run, report = provider_preflight.run_provider_preflight(
            app_module.db.session,
            app_module.AlignmentProviderPreflightRun,
            app_module.AlignmentProviderPolicy,
            "deepseek-alignment-v1-disabled",
            course="Preflight Course",
            now_fn=app_module.current_time_text,
            commit=True,
        )
        auto_approve = provider_preflight.check_policy_readiness({
            "provider_name": "unsafe",
            "provider_type": "external_llm",
            "allow_auto_approve": True,
            "require_human_review": True,
            "allow_production_result": False,
            "allowed_courses": ["Preflight Course"],
            "max_calls_per_day": 1,
            "max_calls_per_month": 1,
            "max_estimated_cost_per_call": 1.0,
            "max_estimated_cost_per_day": 1.0,
        }, course="Preflight Course")
        no_human = provider_preflight.check_policy_readiness({
            "provider_name": "unsafe",
            "provider_type": "external_llm",
            "allow_auto_approve": False,
            "require_human_review": False,
            "allow_production_result": False,
            "allowed_courses": ["Preflight Course"],
            "max_calls_per_day": 1,
            "max_calls_per_month": 1,
            "max_estimated_cost_per_call": 1.0,
            "max_estimated_cost_per_day": 1.0,
        }, course="Preflight Course")
        production = provider_preflight.check_policy_readiness({
            "provider_name": "unsafe",
            "provider_type": "external_llm",
            "allow_production_result": True,
            "require_human_review": True,
            "allowed_courses": ["Preflight Course"],
            "max_calls_per_day": 1,
            "max_calls_per_month": 1,
            "max_estimated_cost_per_call": 1.0,
            "max_estimated_cost_per_day": 1.0,
        }, course="Preflight Course")

        assert run.preflight_uid
        assert report["overall_ready"] is False
        assert "provider_policy_missing" in report["blocking_reasons"]
        assert "provider_auto_approve_forbidden" in auto_approve["blocking_reasons"]
        assert "provider_human_review_required" in no_human["blocking_reasons"]
        assert "provider_production_result_forbidden" in production["blocking_reasons"]


def test_preflight_course_budget_and_replay_dry_run_rules(app_module):
    provider = "external-llm-replay-v1"
    with app_module.app.app_context():
        upsert_policy(app_module, provider, **safe_replay_policy())

        ready_run, ready = provider_preflight.run_provider_preflight(
            app_module.db.session,
            app_module.AlignmentProviderPreflightRun,
            app_module.AlignmentProviderPolicy,
            provider,
            course="Preflight Course",
            now_fn=app_module.current_time_text,
            commit=True,
        )
        not_allowed_run, not_allowed = provider_preflight.run_provider_preflight(
            app_module.db.session,
            app_module.AlignmentProviderPreflightRun,
            app_module.AlignmentProviderPolicy,
            provider,
            course="Other Course",
            now_fn=app_module.current_time_text,
            commit=True,
        )
        blocked_run, blocked = provider_preflight.run_provider_preflight(
            app_module.db.session,
            app_module.AlignmentProviderPreflightRun,
            app_module.AlignmentProviderPolicy,
            provider,
            course="Blocked Preflight Course",
            now_fn=app_module.current_time_text,
            commit=True,
        )
        failed_dry_run, dry_failed = provider_preflight.run_provider_preflight(
            app_module.db.session,
            app_module.AlignmentProviderPreflightRun,
            app_module.AlignmentProviderPolicy,
            provider,
            course="Preflight Course",
            replay_response_type="non_json",
            now_fn=app_module.current_time_text,
            commit=True,
        )
        policy = provider_governance.get_provider_policy(app_module.db.session, app_module.AlignmentProviderPolicy, provider)

        assert ready_run.preflight_uid
        assert ready["overall_ready"] is True
        assert ready["check_status"] == "passed"
        assert ready["replay_dry_run_status"] == "passed"
        assert ready["external_calls_enabled"] is False
        assert not_allowed_run.preflight_uid and "course_not_allowed" in not_allowed["blocking_reasons"]
        assert blocked_run.preflight_uid and "course_blocked" in blocked["blocking_reasons"]
        assert failed_dry_run.preflight_uid and dry_failed["overall_ready"] is False
        assert dry_failed["replay_dry_run_status"] == "failed"
        assert "provider_replay_dry_run_failed" in dry_failed["blocking_reasons"]
        assert policy.enabled is True
        assert policy.allow_external_calls is False


def test_preflight_missing_budget_and_scope_are_not_ready(app_module):
    provider = unique_provider()
    with app_module.app.app_context():
        upsert_policy(
            app_module,
            provider,
            provider_type="replay_llm",
            enabled=True,
            status="active",
            replay_only=True,
            max_calls_per_day=0,
            max_calls_per_month=0,
            max_estimated_cost_per_call=None,
            max_estimated_cost_per_day=None,
        )
        run, report = provider_preflight.run_provider_preflight(
            app_module.db.session,
            app_module.AlignmentProviderPreflightRun,
            app_module.AlignmentProviderPolicy,
            provider,
            course="Preflight Course",
            now_fn=app_module.current_time_text,
            commit=True,
        )

        assert run.preflight_uid
        assert report["overall_ready"] is False
        assert "course_scope_missing" in report["blocking_reasons"]
        assert "provider_usage_limit_missing" in report["blocking_reasons"]
        assert "provider_cost_limit_missing" in report["blocking_reasons"]


def test_provider_preflight_apis_and_audit(client, app_module, admin_token, teacher_token, monkeypatch):
    provider = "external-llm-replay-v1"
    request_id = f"preflight-api-{uuid.uuid4().hex[:6]}"
    monkeypatch.setenv("DEEPSEEK_API_KEY", "TEST_KEY_VALUE_DO_NOT_RETURN")
    policy_response = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json=safe_replay_policy(),
        headers={**bearer(admin_token), "X-Request-ID": f"{request_id}-policy"},
    )
    response = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Course", "include_replay_dry_run": True},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert policy_response.status_code == 200, policy_response.get_data(as_text=True)
    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_json()
    data = body["data"]
    serialized_response = json.dumps(body, ensure_ascii=False)
    assert body["request_id"] == request_id
    assert data["preflight_uid"]
    assert data["overall_ready"] is True
    assert data["replay_dry_run_status"] == "passed"
    assert "TEST_KEY_VALUE_DO_NOT_RETURN" not in serialized_response

    history = client.get(
        f"/api/alignment/providers/{provider}/preflight",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-history"},
    )
    detail = client.get(
        f"/api/alignment/providers/preflight/{data['preflight_uid']}",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-detail"},
    )
    missing_provider = client.post(
        f"/api/alignment/providers/{unique_provider('missing-provider')}/preflight",
        json={"course": "Preflight Course"},
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-missing"},
    )

    assert history.status_code == 200
    assert history.get_json()["data"]["total"] >= 1
    assert detail.status_code == 200
    assert detail.get_json()["data"]["preflight"]["preflight_uid"] == data["preflight_uid"]
    assert missing_provider.status_code == 200
    assert missing_provider.get_json()["data"]["overall_ready"] is False

    with app_module.app.app_context():
        requested = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="provider_preflight_requested",
        ).first()
        completed = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="provider_preflight_completed",
        ).first()
        failed = app_module.AuditRecord.query.filter_by(
            request_id=f"{request_id}-missing",
            event_type="provider_preflight_failed",
        ).first()
        assert requested is not None
        assert completed is not None
        assert failed is not None
        audit_dump = json.dumps(audit_records.serialize_audit_record(completed), ensure_ascii=False)
        assert "TEST_KEY_VALUE_DO_NOT_RETURN" not in audit_dump
        assert "Authorization" not in audit_dump
        assert "Cookie" not in audit_dump


def test_preflight_does_not_bypass_governance_gate(client, app_module, admin_token, teacher_token):
    provider = "external-llm-replay-v1"
    request_id = f"preflight-gate-{uuid.uuid4().hex[:6]}"
    client.post(
        f"/api/alignment/providers/{provider}/policy",
        json={**safe_replay_policy(), "allowed_courses": ["Preflight Course"], "allow_attach_to_card": True},
        headers={**bearer(admin_token), "X-Request-ID": f"{request_id}-policy"},
    )
    preflight = client.post(
        f"/api/alignment/providers/{provider}/preflight",
        json={"course": "Preflight Course", "include_replay_dry_run": True},
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-preflight"},
    )
    verify = client.post(
        "/api/alignment/verify",
        json={
            "provider": provider,
            "replay_response_type": "valid",
            "english_term": "preflight term",
            "chinese_term": "预检术语",
            "course": "Other Course",
            "chapter": "Preflight",
            "english_evidence": [],
            "chinese_evidence": [],
            "risk_labels": ["bilingual_alignment_not_verified"],
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert preflight.status_code == 200
    assert preflight.get_json()["data"]["overall_ready"] is True
    assert verify.status_code == 200, verify.get_data(as_text=True)
    verify_data = verify.get_json()["data"]
    assert verify_data["verification_status"] == "failed"
    assert verify_data["provider_response_status"] == "course_not_allowed"
