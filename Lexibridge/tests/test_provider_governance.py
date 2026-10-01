import json
import uuid

from services import audit_records
from services import concept_alignment_cards
from services import provider_governance


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def unique_token(prefix="Gov"):
    return f"{prefix}{uuid.uuid4().hex[:10]}"


def evidence_item(term, *, language="en", score=0.7):
    return {
        "chunk_uid": f"chunk-{uuid.uuid4().hex}",
        "source_uid": f"src-{uuid.uuid4().hex}",
        "source_title": f"{term} Source",
        "course": "Governance Course",
        "chapter": "Provider Policy",
        "language": language,
        "source_role": "english_course_material" if language == "en" else "chinese_reference_material",
        "trust_level": "teacher_verified",
        "quality_status": "native_text_ok",
        "quality_flags": ["native_text_ok"],
        "source_locator": "page:4",
        "snippet": f"{term} bounded evidence snippet.",
        "score": score,
        "retrieval_reason": "test lexical evidence",
        "risk_labels": [],
        "parse_uid": f"parse-{uuid.uuid4().hex}",
        "parse_block_uid": f"block-{uuid.uuid4().hex}",
    }


def valid_payload(course="Governance Course"):
    english_term = unique_token("Fourier")
    chinese_term = f"傅里叶{uuid.uuid4().hex[:6]}"
    return {
        "english_term": english_term,
        "chinese_term": chinese_term,
        "course": course,
        "chapter": "Provider Policy",
        "english_evidence": [evidence_item(english_term, language="en")],
        "chinese_evidence": [evidence_item(chinese_term, language="zh", score=0.68)],
        "candidate_info": {
            "candidate_uid": f"cand-{uuid.uuid4().hex}",
            "chinese_term": chinese_term,
            "score": 0.82,
            "risk_labels": ["candidate_not_alignment_verified"],
        },
        "risk_labels": ["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
        "retrieval_version": "lexical-v1",
    }


def create_card(app_module, payload=None):
    payload = payload or valid_payload()
    card = app_module.ConceptAlignmentCard(
        english_term=payload["english_term"],
        chinese_term=payload["chinese_term"],
        course=payload["course"],
        chapter=payload["chapter"],
        english_evidence=payload["english_evidence"],
        chinese_evidence=payload["chinese_evidence"],
        risk_labels=payload["risk_labels"],
        status="draft",
        retrieval_version="lexical-v1",
    )
    app_module.db.session.add(card)
    app_module.db.session.commit()
    return card


def upsert_policy(app_module, provider_name, **overrides):
    with app_module.app.app_context():
        policy, _ = provider_governance.create_or_update_provider_policy(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            provider_name,
            overrides,
            now_fn=app_module.current_time_text,
            commit=True,
        )
        return policy.policy_uid


def test_provider_policy_and_usage_models_are_conservative_by_default(app_module):
    with app_module.app.app_context():
        policy, created = provider_governance.create_or_update_provider_policy(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            f"custom-disabled-{uuid.uuid4().hex}",
            {},
            now_fn=app_module.current_time_text,
            commit=True,
        )
        usage = provider_governance.record_provider_usage(
            app_module.db.session,
            app_module.AlignmentProviderUsageRecord,
            policy.provider_name,
            input_summary={"course": "Governance Course"},
            result_summary={"provider_response_status": "provider_disabled", "estimated_cost": {"estimated_cost": 0.0}},
            audit_context={"request_id": "model-usage"},
            now_fn=app_module.current_time_text,
            commit=True,
        )
        serialized = provider_governance.serialize_provider_policy(policy)
        usage_data = provider_governance.serialize_provider_usage_record(usage)

        assert created is True
        assert serialized["enabled"] is False
        assert serialized["allow_external_calls"] is False
        assert serialized["allow_auto_approve"] is False
        assert serialized["require_human_review"] is True
        assert usage_data["usage_uid"]
        assert usage_data["provider_response_status"] == "provider_disabled"


def test_provider_governance_service_gate_rules(app_module):
    with app_module.app.app_context():
        missing = provider_governance.evaluate_provider_request(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            app_module.AlignmentProviderUsageRecord,
            f"missing-policy-{uuid.uuid4().hex}",
            valid_payload(),
            now_fn=app_module.current_time_text,
        )
        disabled_policy, _ = provider_governance.create_or_update_provider_policy(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            f"disabled-{uuid.uuid4().hex}",
            {"enabled": False, "status": "disabled"},
            now_fn=app_module.current_time_text,
            commit=True,
        )
        disabled = provider_governance.evaluate_provider_request(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            app_module.AlignmentProviderUsageRecord,
            disabled_policy.provider_name,
            valid_payload(),
            now_fn=app_module.current_time_text,
        )
        replay_provider = f"replay-policy-{uuid.uuid4().hex}"
        provider_governance.create_or_update_provider_policy(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            replay_provider,
            {
                "provider_type": "replay_llm",
                "enabled": True,
                "status": "active",
                "replay_only": True,
                "allowed_courses": ["Allowed Course"],
                "blocked_courses": ["Blocked Course"],
                "max_estimated_cost_per_call": 0.00000001,
            },
            now_fn=app_module.current_time_text,
            commit=True,
        )
        course_not_allowed = provider_governance.evaluate_provider_request(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            app_module.AlignmentProviderUsageRecord,
            replay_provider,
            valid_payload(course="Other Course"),
            now_fn=app_module.current_time_text,
        )
        course_blocked = provider_governance.evaluate_provider_request(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            app_module.AlignmentProviderUsageRecord,
            replay_provider,
            valid_payload(course="Blocked Course"),
            now_fn=app_module.current_time_text,
        )
        cost_blocked = provider_governance.evaluate_provider_request(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            app_module.AlignmentProviderUsageRecord,
            replay_provider,
            valid_payload(course="Allowed Course"),
            now_fn=app_module.current_time_text,
        )
        external_provider = f"external-policy-{uuid.uuid4().hex}"
        provider_governance.create_or_update_provider_policy(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            external_provider,
            {
                "provider_type": "external_llm",
                "enabled": True,
                "status": "active",
                "replay_only": False,
                "allow_external_calls": False,
            },
            now_fn=app_module.current_time_text,
            commit=True,
        )
        external_blocked = provider_governance.evaluate_provider_request(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            app_module.AlignmentProviderUsageRecord,
            external_provider,
            valid_payload(),
            now_fn=app_module.current_time_text,
        )

        assert missing["reason"] == "provider_policy_missing"
        assert disabled["reason"] == "provider_disabled_by_policy"
        assert course_not_allowed["reason"] == "course_not_allowed"
        assert course_blocked["reason"] == "course_blocked"
        assert cost_blocked["reason"] == "provider_cost_limit_exceeded"
        assert external_blocked["reason"] == "provider_external_calls_not_allowed"
        assert provider_governance.can_auto_approve_alignment({}, {}) is False
        assert provider_governance.requires_human_review_for_verification({}, {}) is True


def test_usage_limit_and_attach_policy_helpers(app_module):
    provider_name = f"usage-limit-{uuid.uuid4().hex}"
    with app_module.app.app_context():
        policy, _ = provider_governance.create_or_update_provider_policy(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            provider_name,
            {
                "provider_type": "replay_llm",
                "enabled": True,
                "status": "active",
                "replay_only": True,
                "allow_attach_to_card": False,
                "max_calls_per_day": 1,
            },
            now_fn=app_module.current_time_text,
            commit=True,
        )
        first = provider_governance.evaluate_provider_request(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            app_module.AlignmentProviderUsageRecord,
            provider_name,
            valid_payload(),
            now_fn=app_module.current_time_text,
        )
        provider_governance.record_provider_usage(
            app_module.db.session,
            app_module.AlignmentProviderUsageRecord,
            provider_name,
            input_summary={"course": "Governance Course"},
            result_summary={"provider_response_status": "replayed", "estimated_cost": {"estimated_cost": 0.0}},
            now_fn=app_module.current_time_text,
            commit=True,
        )
        second = provider_governance.evaluate_provider_request(
            app_module.db.session,
            app_module.AlignmentProviderPolicy,
            app_module.AlignmentProviderUsageRecord,
            provider_name,
            valid_payload(),
            now_fn=app_module.current_time_text,
        )

        assert first["allowed"] is True
        assert second["reason"] == "provider_usage_limit_exceeded"
        assert provider_governance.can_attach_verification_to_card({}, policy) is False
        policy.allow_attach_to_card = True
        assert provider_governance.can_attach_verification_to_card({}, policy) is True


def test_provider_governance_apis_and_policy_audit(client, app_module, admin_token, teacher_token):
    provider = f"governance-api-{uuid.uuid4().hex}"
    request_id = f"policy-api-{uuid.uuid4().hex[:6]}"
    providers = client.get(
        "/api/alignment/providers",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-list"},
    )
    created = client.post(
        f"/api/alignment/providers/{provider}/policy",
        json={
            "provider_type": "replay_llm",
            "enabled": True,
            "status": "active",
            "replay_only": True,
            "allow_attach_to_card": False,
            "allowed_courses": ["Governance Course"],
            "allowed_roles": ["teacher", "admin"],
        },
        headers={**bearer(admin_token), "X-Request-ID": request_id},
    )
    fetched = client.get(
        f"/api/alignment/providers/{provider}/policy",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-get"},
    )
    usage = client.get(
        f"/api/alignment/providers/{provider}/usage",
        headers={**bearer(teacher_token), "X-Request-ID": f"{request_id}-usage"},
    )

    assert providers.status_code == 200
    assert created.status_code == 200, created.get_data(as_text=True)
    assert created.get_json()["data"]["policy"]["allow_auto_approve"] is False
    assert fetched.status_code == 200
    assert fetched.get_json()["data"]["policy"]["enabled"] is True
    assert usage.status_code == 200
    with app_module.app.app_context():
        audit = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="provider_policy_created",
        ).first()
        assert audit is not None


def test_alignment_verify_policy_blocked_and_usage_audit(client, app_module, teacher_token):
    request_id = f"policy-block-{uuid.uuid4().hex[:6]}"
    response = client.post(
        "/api/alignment/verify",
        json={**valid_payload(), "provider": "deepseek-alignment-v1-disabled"},
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["verification_status"] == "failed"
    assert data["provider_response_status"] == "provider_policy_missing"
    assert data["can_auto_approve"] is False
    with app_module.app.app_context():
        blocked = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="alignment_verification_blocked_by_policy",
        ).first()
        usage = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="provider_usage_recorded",
        ).first()
        assert blocked is not None
        assert usage is not None
        serialized = json.dumps(audit_records.serialize_audit_record(blocked), ensure_ascii=False)
        assert "Authorization" not in serialized
        assert "DEEPSEEK_API_KEY" not in serialized
        assert "english_evidence" not in serialized


def test_alignment_verify_replay_policy_allows_run_but_blocks_attach(client, app_module, admin_token, teacher_token):
    provider = "external-llm-replay-v1"
    request_id = f"policy-replay-{uuid.uuid4().hex[:6]}"
    client.post(
        f"/api/alignment/providers/{provider}/policy",
        json={
            "provider_type": "replay_llm",
            "enabled": True,
            "status": "active",
            "replay_only": True,
            "allow_attach_to_card": False,
            "allowed_courses": ["Governance Course"],
            "allowed_roles": ["teacher", "admin"],
        },
        headers={**bearer(admin_token), "X-Request-ID": f"{request_id}-policy"},
    )
    with app_module.app.app_context():
        card = create_card(app_module)
        card_uid = card.card_uid

    response = client.post(
        "/api/alignment/verify",
        json={
            "card_uid": card_uid,
            "provider": provider,
            "replay_response_type": "valid",
            "attach_to_card": True,
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["provider_response_status"] == "replayed"
    assert data["attach_blocked_reason"] == "provider_attach_not_allowed"
    assert "card" in data
    assert data["card"]["status"] == "draft"
    assert data["card"]["confidence_score"] is None
    with app_module.app.app_context():
        refreshed = app_module.ConceptAlignmentCard.query.filter_by(card_uid=card_uid).first()
        serialized_card = concept_alignment_cards.serialize_concept_card(refreshed)
        blocked = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="alignment_verification_blocked_by_policy",
        ).first()
        usage_records = app_module.AlignmentProviderUsageRecord.query.filter_by(provider_name=provider).all()
        assert serialized_card["status"] == "draft"
        assert blocked is not None
        assert usage_records


def test_alignment_verify_replay_policy_allows_attach_but_never_approves(client, app_module, admin_token, teacher_token):
    provider = "external-llm-replay-v1"
    request_id = f"policy-attach-{uuid.uuid4().hex[:6]}"
    client.post(
        f"/api/alignment/providers/{provider}/policy",
        json={
            "provider_type": "replay_llm",
            "enabled": True,
            "status": "active",
            "replay_only": True,
            "allow_attach_to_card": True,
            "allowed_courses": ["Governance Course"],
            "allowed_roles": ["teacher", "admin"],
        },
        headers={**bearer(admin_token), "X-Request-ID": f"{request_id}-policy"},
    )
    with app_module.app.app_context():
        card = create_card(app_module)
        card_uid = card.card_uid

    response = client.post(
        "/api/alignment/verify",
        json={
            "card_uid": card_uid,
            "provider": provider,
            "replay_response_type": "valid",
            "attach_to_card": True,
        },
        headers={**bearer(teacher_token), "X-Request-ID": request_id},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    data = response.get_json()["data"]
    assert data["card"]["status"] == "needs_review"
    assert data["card"]["status"] != "approved"
    assert data["card"]["confidence_score"] is None
    assert data["can_auto_approve"] is False
    with app_module.app.app_context():
        attached = app_module.AuditRecord.query.filter_by(
            request_id=request_id,
            event_type="alignment_verification_attached_to_card",
        ).first()
        assert attached is not None
