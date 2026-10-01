from types import SimpleNamespace

import pytest

from services import audit_records
from services import concept_alignment_cards as concept_cards


def service_actor():
    return SimpleNamespace(id=321, role="teacher", username="audit_service_teacher")


def audit_evidence():
    return [{
        "source": "Audit Notes",
        "page": 4,
        "text": "The impulse response characterizes a linear time-invariant system.",
        "chunk_id": 404,
        "score": 0.91,
    }]


def create_audited_card(app_module, **overrides):
    data = {
        "english_term": "Impulse Response",
        "chinese_term": "冲激响应",
        "course": "Audit Signal Processing",
        "chapter": "Systems",
        "status": "needs_review",
        "confidence_score": 0.81,
        "risk_labels": ["teacher_review"],
        "english_evidence": audit_evidence(),
    }
    data.update(overrides)
    return concept_cards.create_concept_card(
        app_module.db.session,
        app_module.ConceptAlignmentCard,
        data,
        audit_model=app_module.AuditRecord,
        actor=service_actor(),
        now_fn=app_module.current_time_text,
    )


def test_service_create_audit_record_stores_json_fields(app_module):
    with app_module.app.app_context():
        record = audit_records.create_audit_record(
            app_module.db.session,
            app_module.AuditRecord,
            {
                "event_type": "concept_card_updated",
                "target_type": "concept_alignment_card",
                "target_uid": "card-json-test",
                "before_snapshot": {"status": "draft"},
                "after_snapshot": {"status": "needs_review"},
                "input_payload": {"status": "needs_review", "api_key": "should-not-leak"},
                "output_payload": {"ok": True},
                "changed_fields": ["status"],
                "result": "success",
            },
            now_fn=app_module.current_time_text,
        )

        serialized = audit_records.serialize_audit_record(record)
        assert serialized["audit_uid"]
        assert serialized["before_snapshot"] == {"status": "draft"}
        assert serialized["after_snapshot"] == {"status": "needs_review"}
        assert serialized["input_payload"]["api_key"] == "[REDACTED]"
        assert serialized["changed_fields"] == ["status"]


def test_create_concept_card_writes_created_audit_record(app_module):
    with app_module.app.app_context():
        card = create_audited_card(app_module, english_term="Audit Create Term")

        result = audit_records.list_audit_records(
            app_module.db.session,
            app_module.AuditRecord,
            {
                "target_uid": card.card_uid,
                "event_type": "concept_card_created",
                "result": "success",
            },
        )

        assert result.total == 1
        record = audit_records.serialize_audit_record(result.items[0])
        assert record["after_snapshot"]["english_term"] == "Audit Create Term"
        assert record["after_snapshot"]["status"] == "needs_review"
        assert record["actor_id"] == 321
        assert record["input_payload"]["english_evidence"][0]["chunk_id"] == 404
        assert "text" not in record["input_payload"]["english_evidence"][0]


def test_update_concept_card_writes_changed_fields_and_snapshots(app_module):
    with app_module.app.app_context():
        card = create_audited_card(app_module, english_term="Audit Update Original")
        updated = concept_cards.update_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            card.card_uid,
            {
                "chinese_term": "更新后的术语",
                "confidence_score": 0.88,
                "risk_labels": ["reviewed"],
            },
            audit_model=app_module.AuditRecord,
            actor=service_actor(),
            now_fn=app_module.current_time_text,
        )

        result = audit_records.list_audit_records(
            app_module.db.session,
            app_module.AuditRecord,
            {
                "target_uid": updated.card_uid,
                "event_type": "concept_card_updated",
                "result": "success",
            },
        )

        assert result.total == 1
        record = audit_records.serialize_audit_record(result.items[0])
        assert {"chinese_term", "confidence_score", "risk_labels"} <= set(record["changed_fields"])
        assert record["before_snapshot"]["chinese_term"] == "冲激响应"
        assert record["after_snapshot"]["chinese_term"] == "更新后的术语"
        assert record["after_snapshot"]["risk_labels"] == ["reviewed"]


def test_change_status_writes_status_changed_audit_record(app_module):
    with app_module.app.app_context():
        card = create_audited_card(app_module, english_term="Audit Status Term")
        changed = concept_cards.change_concept_card_status(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            card.card_uid,
            "approved",
            reviewer=service_actor(),
            audit_model=app_module.AuditRecord,
            actor=service_actor(),
            now_fn=app_module.current_time_text,
        )

        result = audit_records.list_audit_records(
            app_module.db.session,
            app_module.AuditRecord,
            {
                "target_uid": changed.card_uid,
                "event_type": "concept_card_status_changed",
                "result": "success",
            },
        )

        assert result.total == 1
        record = audit_records.serialize_audit_record(result.items[0])
        assert {"status", "reviewed_by", "reviewed_at"} <= set(record["changed_fields"])
        assert record["before_snapshot"]["status"] == "needs_review"
        assert record["after_snapshot"]["status"] == "approved"
        assert record["after_snapshot"]["reviewed_by"] == 321


def test_approved_without_evidence_failure_can_write_error_audit(app_module):
    with app_module.app.app_context():
        card = create_audited_card(
            app_module,
            english_term="Audit No Evidence Term",
            english_evidence=[],
            chinese_evidence=[],
            status="draft",
        )

        with pytest.raises(concept_cards.ConceptCardError, match="requires English or Chinese evidence"):
            concept_cards.change_concept_card_status(
                app_module.db.session,
                app_module.ConceptAlignmentCard,
                card.card_uid,
                "approved",
                audit_model=app_module.AuditRecord,
                actor=service_actor(),
                now_fn=app_module.current_time_text,
            )

        result = audit_records.list_audit_records(
            app_module.db.session,
            app_module.AuditRecord,
            {
                "target_uid": card.card_uid,
                "event_type": "concept_card_operation_failed",
                "result": "error",
            },
        )

        assert result.total == 1
        record = audit_records.serialize_audit_record(result.items[0])
        assert "requires English or Chinese evidence" in record["error_message"]
        assert record["input_payload"]["status"] == "approved"


def test_list_audit_records_filters_target_event_and_result(app_module):
    with app_module.app.app_context():
        card = create_audited_card(app_module, english_term="Audit Filter Term")
        concept_cards.update_concept_card(
            app_module.db.session,
            app_module.ConceptAlignmentCard,
            card.card_uid,
            {"english_term": "Audit Filter Term Updated"},
            audit_model=app_module.AuditRecord,
            actor=service_actor(),
            now_fn=app_module.current_time_text,
        )

        by_target = audit_records.list_audit_records(
            app_module.db.session,
            app_module.AuditRecord,
            {"target_uid": card.card_uid, "per_page": 20},
        )
        by_event = audit_records.list_audit_records(
            app_module.db.session,
            app_module.AuditRecord,
            {"target_uid": card.card_uid, "event_type": "concept_card_updated", "result": "success"},
        )

        assert by_target.total == 2
        assert by_event.total == 1
        assert by_event.items[0].event_type == "concept_card_updated"
