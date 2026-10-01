import ast
import dataclasses
import inspect
import json
import socket
import uuid

import pytest

from routes.shared import RouteCoreDependencies
from services import alignment_verification_execution as execution_service
from services import audit_records
from services import provider_governance


def unique_token(prefix="ExecutionService"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def evidence_item(term, *, language="en", course="Execution Service Course", score=0.72):
    return {
        "chunk_uid": f"chunk-{uuid.uuid4().hex}",
        "source_uid": f"src-{uuid.uuid4().hex}",
        "source_title": f"{term} Source",
        "course": course,
        "chapter": "Service Boundary",
        "language": language,
        "source_role": "english_course_material" if language == "en" else "chinese_reference_material",
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "quality_flags": ["native_text_ok"],
        "source_locator": "page:11",
        "snippet": f"{term} bounded evidence snippet.",
        "score": score,
        "retrieval_reason": "execution service boundary",
        "risk_labels": [],
        "parse_uid": f"parse-{uuid.uuid4().hex}",
        "parse_block_uid": f"block-{uuid.uuid4().hex}",
    }


def valid_payload(**overrides):
    course = overrides.pop("course", "Execution Service Course")
    english_term = overrides.pop("english_term", unique_token("Fourier"))
    chinese_term = overrides.pop("chinese_term", f"傅里叶{uuid.uuid4().hex[:6]}")
    payload = {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": course,
        "chapter": "Service Boundary",
        "english_evidence": [evidence_item(english_term, language="en", course=course)],
        "chinese_evidence": [evidence_item(chinese_term, language="zh", course=course, score=0.68)],
        "candidate_info": {
            "candidate_uid": f"cand-{uuid.uuid4().hex}",
            "chinese_term": chinese_term,
            "score": 0.82,
            "risk_labels": ["candidate_not_alignment_verified"],
        },
        "risk_labels": ["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
        "retrieval_version": "lexical-v1",
    }
    payload.update(overrides)
    return payload


def create_card(app_module, payload=None, **overrides):
    payload = payload or valid_payload()
    card = app_module.ConceptAlignmentCard(
        english_term=payload["english_term"],
        chinese_term=payload.get("chinese_term", ""),
        course=payload.get("course", "Execution Service Course"),
        chapter=payload.get("chapter", "Service Boundary"),
        english_evidence=payload.get("english_evidence", []),
        chinese_evidence=payload.get("chinese_evidence", []),
        risk_labels=payload.get("risk_labels", []),
        status=overrides.get("status", "draft"),
        confidence_score=overrides.get("confidence_score"),
        retrieval_version=payload.get("retrieval_version", "lexical-v1"),
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def upsert_replay_policy(app_module, *, allow_attach=False):
    return provider_governance.create_or_update_provider_policy(
        app_module.db.session,
        app_module.AlignmentProviderPolicy,
        "external-llm-replay-v1",
        {
            "provider_type": "replay_llm",
            "enabled": True,
            "status": "active",
            "replay_only": True,
            "allow_external_calls": False,
            "allow_attach_to_card": allow_attach,
            "allow_production_result": False,
            "allow_auto_approve": False,
            "require_human_review": True,
            "allowed_courses": ["Execution Service Course"],
            "allowed_roles": ["teacher", "admin"],
        },
        now_fn=app_module.current_time_text,
        commit=True,
    )[0]


def side_effect_counts(app_module):
    return {
        "runs": app_module.AlignmentVerificationRun.query.count(),
        "usage": app_module.AlignmentProviderUsageRecord.query.count(),
        "audits": app_module.AuditRecord.query.count(),
        "cards": app_module.ConceptAlignmentCard.query.count(),
        "policies": app_module.AlignmentProviderPolicy.query.count(),
    }


def service_dependencies(app_module, **overrides):
    deps = execution_service.AlignmentVerificationExecutionDependencies(
        db=app_module.db,
        models=execution_service.AlignmentVerificationExecutionModels(
            concept_alignment_card=app_module.ConceptAlignmentCard,
            provider_policy=app_module.AlignmentProviderPolicy,
            provider_usage_record=app_module.AlignmentProviderUsageRecord,
            verification_run=app_module.AlignmentVerificationRun,
        ),
        provider_registry_service=app_module.alignment_provider_service,
        provider_governance_service=app_module.provider_governance_service,
        verification_service=app_module.alignment_verification_service,
        concept_card_service=app_module.concept_card_service,
        current_time_text=app_module.current_time_text,
        record_alignment_verification_audit=app_module.record_alignment_verification_audit,
        record_alignment_provider_usage=app_module.record_alignment_provider_usage,
    )
    return dataclasses.replace(deps, **overrides)


def teacher_actor_and_context(app_module, request_id):
    teacher = app_module.User.query.filter_by(email="teacher.test@lexibridge.local").one()
    return (
        execution_service.AlignmentVerificationActor(
            user_id=teacher.id,
            email=teacher.email,
            role=teacher.role,
            display_name=teacher.username,
        ),
        execution_service.AlignmentVerificationExecutionContext(
            request_id=request_id,
            actor_id=teacher.id,
            actor_role=teacher.role,
            actor_name=teacher.username,
            source="api",
            route="/api/alignment/verify",
            occurred_at=app_module.current_time_text(),
        ),
    )


def execute(app_module, payload, request_id, **request_overrides):
    actor, context = teacher_actor_and_context(app_module, request_id)
    provider_name = str(payload.get("provider") or payload.get("provider_name") or "mock-rule-v1").strip()
    card_uid = str(payload.get("card_uid") or "").strip()
    attach_to_card = payload.get("attach_to_card", False)
    if isinstance(attach_to_card, str):
        attach_to_card = attach_to_card.strip().lower() in {"1", "true", "yes", "on"}
    else:
        attach_to_card = bool(attach_to_card)
    request = execution_service.AlignmentVerificationExecutionRequest(
        payload=payload,
        provider_name=provider_name,
        card_uid=card_uid,
        attach_to_card=attach_to_card,
    )
    if request_overrides:
        request = dataclasses.replace(request, **request_overrides)
    return execution_service.execute_alignment_verification(
        request,
        actor,
        context,
        service_dependencies(app_module),
    )


def assert_no_secret_values(payload):
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in [
        "LEXIBRIDGE_SENTINEL_SECRET_9C4D1",
        "Bearer sentinel",
        "Authorization",
        "Cookie",
        "private key",
        "password",
        "api_key",
    ]:
        assert forbidden not in serialized


def test_execution_service_boundary_and_immutable_dtos(app_module):
    source = inspect.getsource(execution_service)
    tree = ast.parse(source)
    imported_roots = {
        node.module.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_roots.update(
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert "flask" not in imported_roots
    assert "backend" not in imported_roots
    assert "routes" not in imported_roots
    assert "os" not in imported_roots

    request = execution_service.AlignmentVerificationExecutionRequest(payload={"english_term": "Boundary"})
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.provider_name = "fake-llm-v1"
    actor = execution_service.AlignmentVerificationActor(user_id=1, role="teacher")
    with pytest.raises(dataclasses.FrozenInstanceError):
        actor.role = "admin"
    context = execution_service.AlignmentVerificationExecutionContext(request_id="immutable-context")
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.request_id = "changed"

    assert len(dataclasses.fields(RouteCoreDependencies)) == 9
    core_field_names = {field.name for field in dataclasses.fields(RouteCoreDependencies)}
    assert "alignment_verification_execution_service" not in core_field_names
    assert "provider_execution_service" not in core_field_names

    route_source = inspect.getsource(app_module.app.view_functions["verify_alignment_api"])
    assert "AlignmentVerificationRun" not in route_source
    assert "AlignmentProviderUsageRecord" not in route_source
    assert "record_alignment_provider_usage" not in route_source
    assert "verify_alignment(" not in route_source
    assert "apply_verification_result_to_card" not in route_source
    assert "execute_fn(" in route_source


def test_execution_service_provider_modes_and_usage_write_set(app_module):
    with app_module.app.app_context():
        upsert_replay_policy(app_module, allow_attach=False)
        before = side_effect_counts(app_module)
        cases = [
            ("svc-mode-mock", {**valid_payload(), "provider": "mock-rule-v1"}, "mock", "mock_only"),
            (
                "svc-mode-fake-valid",
                {**valid_payload(), "provider": "fake-llm-v1", "fake_response_type": "valid"},
                "fake_llm",
                "needs_review",
            ),
            (
                "svc-mode-replay",
                {**valid_payload(), "provider": "external-llm-replay-v1", "replay_response_type": "valid"},
                "replay_llm",
                "needs_review",
            ),
            (
                "svc-mode-disabled-external",
                {**valid_payload(), "provider": "deepseek-alignment-v1-disabled"},
                "external_llm",
                "failed",
            ),
        ]
        for request_id, payload, provider_type, verification_status in cases:
            result = execute(app_module, payload, request_id)
            assert result.succeeded
            assert result.payload["provider_type"] == provider_type
            assert result.payload["verification_status"] == verification_status
            assert result.payload["can_auto_approve"] is False
            assert result.payload["is_production_result"] is False

        after = side_effect_counts(app_module)
        assert after["runs"] == before["runs"] + len(cases)
        assert after["usage"] == before["usage"] + len(cases)
        assert after["cards"] == before["cards"]
        assert app_module.AuditRecord.query.filter_by(
            request_id="svc-mode-disabled-external",
            event_type="alignment_verification_blocked_by_policy",
        ).one()


def test_execution_service_attach_gate_blocks_and_allows(app_module):
    with app_module.app.app_context():
        upsert_replay_policy(app_module, allow_attach=False)
        blocked_card = create_card(app_module)
        blocked = execute(
            app_module,
            {
                "card_uid": blocked_card.card_uid,
                "provider": "external-llm-replay-v1",
                "replay_response_type": "valid",
                "attach_to_card": True,
            },
            "svc-attach-blocked",
        )
        assert blocked.succeeded
        assert blocked.payload["attach_blocked_reason"] == "provider_attach_not_allowed"
        assert blocked.payload["card"]["status"] == "draft"
        app_module.db.session.refresh(blocked_card)
        assert blocked_card.status == "draft"

        upsert_replay_policy(app_module, allow_attach=True)
        allowed_card = create_card(app_module)
        allowed = execute(
            app_module,
            {
                "card_uid": allowed_card.card_uid,
                "provider": "external-llm-replay-v1",
                "replay_response_type": "valid",
                "attach_to_card": "yes",
            },
            "svc-attach-allowed",
        )
        assert allowed.succeeded
        assert allowed.payload["card"]["status"] == "needs_review"
        assert allowed.payload["card"]["status"] != "approved"
        app_module.db.session.refresh(allowed_card)
        assert allowed_card.status == "needs_review"
        assert app_module.AuditRecord.query.filter_by(
            request_id="svc-attach-allowed",
            event_type="alignment_verification_attached_to_card",
        ).one()


def test_execution_service_validation_errors_and_rollback(app_module):
    with app_module.app.app_context():
        before = side_effect_counts(app_module)
        missing_provider = execute(
            app_module,
            {**valid_payload(), "provider": "provider-not-enabled"},
            "svc-unknown-provider",
        )
        assert missing_provider.status_code == 400
        assert missing_provider.error_code == "VALIDATION_ERROR"
        assert missing_provider.audit_error_code == "unknown_provider"

        empty = execute(app_module, {}, "svc-empty-body")
        assert empty.status_code == 400
        assert empty.audit_error_code == "alignment_verification_validation_error"

        def fail_usage(*args, **kwargs):
            raise RuntimeError("forced service usage failure")

        deps = service_dependencies(app_module, record_alignment_provider_usage=fail_usage)
        actor, context = teacher_actor_and_context(app_module, "svc-usage-rollback")
        rollback = execution_service.execute_alignment_verification(
            execution_service.AlignmentVerificationExecutionRequest(
                payload={**valid_payload(), "provider": "mock-rule-v1"},
                provider_name="mock-rule-v1",
            ),
            actor,
            context,
            deps,
        )
        assert rollback.status_code == 500
        assert rollback.audit_error_code == "alignment_verification_failed"
        after = side_effect_counts(app_module)
        assert after["runs"] == before["runs"]
        assert after["usage"] == before["usage"]


def test_execution_service_secret_redaction_and_no_network(app_module, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "LEXIBRIDGE_SENTINEL_SECRET_9C4D1")

    def blocked_connect(*args, **kwargs):
        raise AssertionError("alignment execution service attempted external network access")

    monkeypatch.setattr(socket.socket, "connect", blocked_connect)
    payload = valid_payload(
        provider="fake-llm-v1",
        fake_response_type="valid",
        api_key="LEXIBRIDGE_SENTINEL_SECRET_9C4D1",
        secret="LEXIBRIDGE_SENTINEL_SECRET_9C4D1",
        token="LEXIBRIDGE_SENTINEL_SECRET_9C4D1",
        password="password",
        private_key="private key",
    )
    payload["english_evidence"][0]["Authorization"] = "Bearer sentinel"
    payload["english_evidence"][0]["Cookie"] = "Cookie: sentinel"

    with app_module.app.app_context():
        result = execute(app_module, payload, "svc-secret-no-network")
        assert result.succeeded
        assert_no_secret_values(result.payload)
        run = app_module.AlignmentVerificationRun.query.filter_by(
            run_uid=result.payload["run_uid"],
        ).one()
        audits = app_module.AuditRecord.query.filter_by(request_id="svc-secret-no-network").all()
        usage = app_module.AlignmentProviderUsageRecord.query.filter_by(run_uid=run.run_uid).one()
        assert_no_secret_values({
            "input_payload": run.input_payload,
            "output_payload": run.output_payload,
            "usage": {
                "error_code": usage.error_code,
                "error_message": usage.error_message,
                "provider_response_status": usage.provider_response_status,
            },
            "audits": [audit_records.serialize_audit_record(item) for item in audits],
        })
