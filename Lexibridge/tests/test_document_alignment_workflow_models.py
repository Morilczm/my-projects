import json
import uuid

import pytest
from sqlalchemy.exc import IntegrityError


def _uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _make_run(app_module, **overrides):
    values = {
        "run_uid": _uid("workflow-run"),
        "source_uid": _uid("source"),
        "parse_uid": _uid("parse"),
        "source_version": "v1",
        "course": "Formal Workflow Course",
        "chapter": "Boundary Chapter",
        "requested_by": _uid("teacher"),
        "request_id": _uid("request"),
        "idempotency_key": _uid("idem"),
        "idempotency_fingerprint": _uid("fingerprint"),
        "workflow_version": "formal-document-alignment-v1",
    }
    values.update(overrides)
    return app_module.DocumentAlignmentWorkflowRun(**values)


def _make_item(app_module, run, **overrides):
    values = {
        "item_uid": _uid("workflow-item"),
        "workflow_run": run,
        "item_key": _uid("item-key"),
        "candidate_term": "Laplace Transform",
        "normalized_term": "laplace transform",
        "source_chunk_refs": json.dumps(["chunk-a", "chunk-b"]),
        "english_evidence_refs": json.dumps(["evidence-en"]),
        "chinese_evidence_refs": json.dumps(["evidence-zh"]),
    }
    values.update(overrides)
    return app_module.DocumentAlignmentWorkflowItem(**values)


@pytest.fixture()
def clean_workflow_tables(app_module):
    with app_module.app.app_context():
        if hasattr(app_module, "DocumentAlignmentWorkflowItem"):
            app_module.DocumentAlignmentWorkflowItem.query.delete()
        if hasattr(app_module, "DocumentAlignmentWorkflowRun"):
            app_module.DocumentAlignmentWorkflowRun.query.delete()
        app_module.db.session.commit()
    yield
    with app_module.app.app_context():
        app_module.db.session.rollback()
        if hasattr(app_module, "DocumentAlignmentWorkflowItem"):
            app_module.DocumentAlignmentWorkflowItem.query.delete()
        if hasattr(app_module, "DocumentAlignmentWorkflowRun"):
            app_module.DocumentAlignmentWorkflowRun.query.delete()
        app_module.db.session.commit()


def test_model_classes_table_names_and_defaults(app_module, clean_workflow_tables):
    with app_module.app.app_context():
        assert app_module.DocumentAlignmentWorkflowRun.__tablename__ == "document_alignment_workflow_runs"
        assert app_module.DocumentAlignmentWorkflowItem.__tablename__ == "document_alignment_workflow_items"

        run = _make_run(app_module)
        item = _make_item(app_module, run)
        app_module.db.session.add(run)
        app_module.db.session.add(item)
        app_module.db.session.commit()

        assert run.run_uid
        assert run.status == "queued"
        assert run.stage == "queued"
        assert run.total_items == 0
        assert run.successful_items == 0
        assert run.ready_for_review_items == 0
        assert run.blocked_items == 0
        assert run.failed_items == 0
        assert run.warning_count == 0
        assert run.created_at
        assert run.updated_at
        assert item.item_uid
        assert item.status == "candidate"
        assert item.stage == "candidate"
        assert item.retry_count == 0
        assert item.warning_count == 0
        assert item.workflow_run_id == run.id
        assert run.items.count() == 1
        assert run.items.first().item_uid == item.item_uid


def test_uid_and_idempotency_constraints(app_module, clean_workflow_tables):
    with app_module.app.app_context():
        run_uid = _uid("same-run")
        run_a = _make_run(app_module, run_uid=run_uid)
        run_b = _make_run(app_module, run_uid=run_uid)
        app_module.db.session.add(run_a)
        app_module.db.session.commit()
        app_module.db.session.add(run_b)
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()

        requested_by = _uid("teacher")
        source_uid = _uid("source")
        workflow_version = "formal-document-alignment-v1"
        idempotency_key = _uid("idem")
        scoped_a = _make_run(
            app_module,
            requested_by=requested_by,
            source_uid=source_uid,
            workflow_version=workflow_version,
            idempotency_key=idempotency_key,
        )
        scoped_b = _make_run(
            app_module,
            requested_by=requested_by,
            source_uid=source_uid,
            workflow_version=workflow_version,
            idempotency_key=idempotency_key,
        )
        app_module.db.session.add(scoped_a)
        app_module.db.session.commit()
        app_module.db.session.add(scoped_b)
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()

        same_request_id_a = _make_run(app_module, request_id="same-request-id")
        same_request_id_b = _make_run(app_module, request_id="same-request-id")
        app_module.db.session.add_all([same_request_id_a, same_request_id_b])
        app_module.db.session.commit()
        assert app_module.DocumentAlignmentWorkflowRun.query.filter_by(request_id="same-request-id").count() == 2

        different_source = _make_run(
            app_module,
            requested_by=requested_by,
            source_uid=_uid("source-other"),
            workflow_version=workflow_version,
            idempotency_key=idempotency_key,
        )
        different_version = _make_run(
            app_module,
            requested_by=requested_by,
            source_uid=source_uid,
            workflow_version="formal-document-alignment-v2",
            idempotency_key=idempotency_key,
        )
        app_module.db.session.add_all([different_source, different_version])
        app_module.db.session.commit()


def test_item_constraints_relationship_and_reusable_terms(app_module, clean_workflow_tables):
    with app_module.app.app_context():
        run_a = _make_run(app_module)
        run_b = _make_run(app_module)
        app_module.db.session.add_all([run_a, run_b])
        app_module.db.session.flush()

        item_key = "laplace-transform:chunk-a"
        item_a = _make_item(app_module, run_a, item_key=item_key, normalized_term="laplace transform")
        app_module.db.session.add(item_a)
        app_module.db.session.commit()
        duplicate_item = _make_item(app_module, run_a, item_key=item_key, normalized_term="laplace transform")
        app_module.db.session.add(duplicate_item)
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()
        other_run_item = _make_item(app_module, run_b, item_key=item_key, normalized_term="laplace transform")
        app_module.db.session.add(other_run_item)
        app_module.db.session.commit()

        assert run_a.items.count() == 1
        assert run_b.items.count() == 1
        assert run_a.items.first().normalized_term == other_run_item.normalized_term


def test_validated_status_stage_progress_retry_and_required_fields(app_module, clean_workflow_tables):
    with app_module.app.app_context():
        for kwargs in [
            {"status": "approved"},
            {"stage": "student_visible"},
            {"blocked_items": -1},
            {"idempotency_key": ""},
        ]:
            with pytest.raises(ValueError):
                _make_run(app_module, **kwargs)

        valid_run = _make_run(app_module)
        for kwargs in [
            {"status": "published"},
            {"retry_count": -1},
            {"candidate_term": ""},
        ]:
            with pytest.raises(ValueError):
                _make_item(app_module, valid_run, **kwargs)

        valid = _make_run(app_module)
        app_module.db.session.add(valid)
        app_module.db.session.commit()
        assert valid.total_items == 0


def test_safe_reference_fields_and_no_sensitive_columns(app_module, clean_workflow_tables):
    forbidden_names = {
        "credential",
        "api_key",
        "raw_exception",
        "traceback",
        "raw_document",
        "document_text",
        "raw_prompt",
        "prompt_text",
        "raw_provider_output",
        "raw_response",
        "raw_evidence",
    }
    run_columns = {column.name for column in app_module.DocumentAlignmentWorkflowRun.__table__.columns}
    item_columns = {column.name for column in app_module.DocumentAlignmentWorkflowItem.__table__.columns}

    assert forbidden_names.isdisjoint(run_columns)
    assert forbidden_names.isdisjoint(item_columns)
    assert {"source_uid", "parse_uid", "source_version"} <= run_columns
    assert {"source_chunk_refs", "english_evidence_refs", "chinese_evidence_refs"} <= item_columns
    assert {"draft_card_uid", "verification_run_uid"} <= item_columns
    assert "alignment_run_id" not in item_columns
    assert "terminology_card_id" not in item_columns
    assert "usage_record_id" not in item_columns
    assert "ai_call_log_id" not in item_columns

    with app_module.app.app_context():
        run = _make_run(app_module, error_code="DOCUMENT_ALIGNMENT_PROVIDER_POLICY_BLOCKED", error_message="Safe summary")
        item = _make_item(
            app_module,
            run,
            draft_card_uid="formal-card-uid",
            verification_run_uid="formal-verification-run-uid",
            chinese_candidate_summary=json.dumps({"candidate": "拉普拉斯变换"}),
            risk_labels=json.dumps(["needs_teacher_review"]),
            confidence_summary=json.dumps({"label": "medium"}),
            recommendation="needs_review",
            error_code="DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT",
            error_message="Safe item summary",
        )
        app_module.db.session.add_all([run, item])
        app_module.db.session.commit()

        persisted = app_module.DocumentAlignmentWorkflowItem.query.filter_by(item_uid=item.item_uid).one()
        assert json.loads(persisted.source_chunk_refs) == ["chunk-a", "chunk-b"]
        assert json.loads(persisted.english_evidence_refs) == ["evidence-en"]
        assert json.loads(persisted.chinese_evidence_refs) == ["evidence-zh"]
        assert persisted.draft_card_uid == "formal-card-uid"
        assert persisted.verification_run_uid == "formal-verification-run-uid"


def test_no_legacy_formal_dual_write_and_session_recovers_after_rollback(app_module, clean_workflow_tables):
    with app_module.app.app_context():
        before_legacy_runs = app_module.AlignmentRun.query.count()
        before_legacy_cards = app_module.TerminologyCard.query.count()
        before_legacy_usage = app_module.UsageRecord.query.count()
        before_ai_logs = app_module.AICallLog.query.count()

        run = _make_run(app_module)
        item = _make_item(app_module, run)
        app_module.db.session.add_all([run, item])
        app_module.db.session.commit()

        assert app_module.AlignmentRun.query.count() == before_legacy_runs
        assert app_module.TerminologyCard.query.count() == before_legacy_cards
        assert app_module.UsageRecord.query.count() == before_legacy_usage
        assert app_module.AICallLog.query.count() == before_ai_logs

        legacy = app_module.AlignmentRun(document_id=0, status="completed", provider="none")
        app_module.db.session.add(legacy)
        app_module.db.session.commit()

        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 1
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == 1

        duplicate = _make_run(app_module, run_uid=run.run_uid)
        app_module.db.session.add(duplicate)
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()

        recovered = _make_run(app_module)
        app_module.db.session.add(recovered)
        app_module.db.session.commit()
        assert app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=recovered.run_uid).one()


def test_create_all_repeated_and_new_tables_queryable(app_module, clean_workflow_tables):
    with app_module.app.app_context():
        app_module.db.create_all()
        app_module.db.create_all()
        assert app_module.DocumentAlignmentWorkflowRun.query.count() == 0
        assert app_module.DocumentAlignmentWorkflowItem.query.count() == 0
