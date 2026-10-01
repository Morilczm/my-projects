from types import SimpleNamespace

from services import audit_context
from services import audit_records
from services import concept_alignment_cards as concept_cards


def test_build_audit_context_from_request_extracts_safe_context(app_module):
    with app_module.app.test_request_context(
        "/api/concept-cards",
        headers={
            "X-Request-ID": "ctx-safe-request-id",
            "Authorization": "Bearer should-not-be-copied",
            "Cookie": "session=should-not-be-copied",
            "User-Agent": "LexiBridge Test Client/1.0",
        },
        environ_base={"REMOTE_ADDR": "203.0.113.9"},
    ):
        from flask import request

        actor = SimpleNamespace(id=78, role="teacher", username="ctx_safe_teacher")
        context = audit_context.build_audit_context_from_request(request, actor)

    assert context["request_id"] == "ctx-safe-request-id"
    assert context["actor_id"] == 78
    assert context["actor_role"] == "teacher"
    assert context["actor_name"] == "ctx_safe_teacher"
    assert context["source"] == "api"
    assert len(context["ip_hash"]) == 16
    assert "LexiBridge Test Client" in context["user_agent_summary"]
    assert "Authorization" not in context
    assert "Cookie" not in context


def test_audit_context_generates_request_id_when_missing(app_module):
    with app_module.app.test_request_context("/api/concept-cards"):
        from flask import request

        context = audit_context.build_audit_context_from_request(request)

    assert context["request_id"]
    assert len(context["request_id"]) >= 32


def test_service_records_audit_context_and_still_works_without_context(app_module):
    with app_module.app.app_context():
        actor = SimpleNamespace(id=79, role="teacher", username="ctx_service_teacher")
        context = {
            "request_id": "ctx-service-request-id",
            "actor_id": actor.id,
            "actor_role": actor.role,
            "actor_name": actor.username,
            "source": "api",
        }
        card = concept_cards.create_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            {
                "english_term": "Context Service Term",
                "course": "Audit Context Course",
                "status": "draft",
            },
            audit_model=app_module.AuditRecord,
            audit_context=context,
            now_fn=app_module.current_time_text,
        )
        result = audit_records.list_audit_records(
            app_module.db.session,
            app_module.AuditRecord,
            {"target_uid": card.card_uid, "request_id": "ctx-service-request-id"},
        )

        assert result.total == 1
        serialized = audit_records.serialize_audit_record(result.items[0])
        assert serialized["request_id"] == "ctx-service-request-id"
        assert serialized["actor_id"] == 79
        assert serialized["source"] == "api"

        plain_card = concept_cards.create_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            {
                "english_term": "Context Without Audit Context",
                "course": "Audit Context Course",
                "status": "draft",
            },
            now_fn=app_module.current_time_text,
        )
        assert plain_card.card_uid
