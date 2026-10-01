import threading
import uuid

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker


def _uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _execution(app_module, execution_key):
    return app_module.DocumentAlignmentItemVerificationExecution(
        execution_key=execution_key,
        workflow_run_uid=_uid("workflow-run"),
        workflow_item_uid=_uid("workflow-item"),
        workflow_item_key=_uid("item-key-v1"),
        execution_version="item-verification-execution-v1",
        workflow_version="formal-document-alignment-v1",
        provider_name="replay-llm-v1",
        model_identity="replay-model-v1",
        retrieval_version="retrieval-v1",
        prompt_version="prompt-v1",
        parser_version="parser-v1",
        output_schema_version="alignment-output-v1",
        safe_input_fingerprint="a" * 64,
    )


def _verification(app_module, execution_key=None):
    return app_module.AlignmentVerificationRun(
        run_uid=_uid("verification"),
        english_term="Fourier transform",
        execution_key=execution_key,
    )


def _preflight(app_module, execution_key=None):
    return app_module.AlignmentProviderPreflightRun(
        preflight_uid=_uid("preflight"),
        provider_name="replay-llm-v1",
        execution_key=execution_key,
    )


def _usage(app_module, execution_key=None):
    return app_module.AlignmentProviderUsageRecord(
        usage_uid=_uid("usage"),
        provider_name="replay-llm-v1",
        execution_key=execution_key,
    )


def _audit(app_module, event_identity=None):
    return app_module.AuditRecord(
        audit_uid=_uid("audit"),
        event_type="item_verification_requested",
        target_type="document_alignment_workflow_item",
        target_uid=_uid("workflow-item"),
        event_identity=event_identity,
    )


@pytest.fixture()
def clean_idempotency_records(app_module):
    models = (
        app_module.DocumentAlignmentItemVerificationExecution,
        app_module.AlignmentVerificationRun,
        app_module.AlignmentProviderPreflightRun,
        app_module.AlignmentProviderUsageRecord,
        app_module.AuditRecord,
    )
    with app_module.app.app_context():
        app_module.db.session.rollback()
        for model in models:
            model.query.delete()
        app_module.db.session.commit()
        app_module.db.session.remove()
    yield
    with app_module.app.app_context():
        app_module.db.session.rollback()
        for model in models:
            model.query.delete()
        app_module.db.session.commit()
        app_module.db.session.remove()


def test_existing_formal_models_expose_nullable_named_unique_identities(app_module):
    expected = {
        app_module.AlignmentVerificationRun: (
            "execution_key",
            "uq_alignment_verification_run_execution_key",
        ),
        app_module.AlignmentProviderPreflightRun: (
            "execution_key",
            "uq_alignment_provider_preflight_execution_key",
        ),
        app_module.AlignmentProviderUsageRecord: (
            "execution_key",
            "uq_alignment_provider_usage_execution_key",
        ),
        app_module.AuditRecord: (
            "event_identity",
            "uq_audit_record_event_identity",
        ),
    }
    for model, (column_name, index_name) in expected.items():
        column = model.__table__.columns[column_name]
        assert column.nullable is True
        indexes = {index.name: index for index in model.__table__.indexes}
        assert indexes[index_name].unique is True
        assert tuple(item.name for item in indexes[index_name].columns) == (column_name,)


@pytest.mark.parametrize(
    ("factory_name", "identity_field"),
    [
        ("verification", "execution_key"),
        ("preflight", "execution_key"),
        ("usage", "execution_key"),
        ("audit", "event_identity"),
    ],
)
def test_non_null_identity_is_unique_while_multiple_legacy_nulls_remain_valid(
    app_module,
    clean_idempotency_records,
    factory_name,
    identity_field,
):
    factories = {
        "verification": _verification,
        "preflight": _preflight,
        "usage": _usage,
        "audit": _audit,
    }
    factory = factories[factory_name]
    identity = f"identity-{factory_name}-{uuid.uuid4().hex}"

    with app_module.app.app_context():
        app_module.db.session.add(factory(app_module, identity))
        app_module.db.session.commit()
        app_module.db.session.add(factory(app_module, identity))
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()

        app_module.db.session.add_all([factory(app_module), factory(app_module)])
        app_module.db.session.commit()
        model = {
            "verification": app_module.AlignmentVerificationRun,
            "preflight": app_module.AlignmentProviderPreflightRun,
            "usage": app_module.AlignmentProviderUsageRecord,
            "audit": app_module.AuditRecord,
        }[factory_name]
        assert model.query.filter(getattr(model, identity_field).is_(None)).count() == 2


def test_mapping_unique_conflict_rolls_back_and_session_remains_usable(
    app_module,
    clean_idempotency_records,
):
    execution_key = "item-verification-execution-v1:" + "c" * 64
    with app_module.app.app_context():
        app_module.db.session.add(_execution(app_module, execution_key))
        app_module.db.session.commit()
        app_module.db.session.add(_execution(app_module, execution_key))
        with pytest.raises(IntegrityError):
            app_module.db.session.commit()
        app_module.db.session.rollback()

        recovery_key = "item-verification-execution-v1:" + "d" * 64
        app_module.db.session.add(_execution(app_module, recovery_key))
        app_module.db.session.commit()
        assert (
            app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
                execution_key=recovery_key
            ).count()
            == 1
        )


def test_execution_mapping_insert_has_no_business_or_legacy_dual_write(
    app_module,
    clean_idempotency_records,
):
    with app_module.app.app_context():
        legacy_before = {
            "alignment_run": app_module.AlignmentRun.query.count(),
            "terminology_card": app_module.TerminologyCard.query.count(),
            "legacy_usage": app_module.UsageRecord.query.count(),
            "ai_call_log": app_module.AICallLog.query.count(),
        }
        execution_key = "item-verification-execution-v1:" + "9" * 64
        app_module.db.session.add(_execution(app_module, execution_key))
        app_module.db.session.commit()

        assert app_module.AlignmentVerificationRun.query.count() == 0
        assert app_module.AlignmentProviderPreflightRun.query.count() == 0
        assert app_module.AlignmentProviderUsageRecord.query.count() == 0
        assert app_module.AuditRecord.query.count() == 0
        assert app_module.ConceptAlignmentCard.query.filter_by(
            card_uid="LEXIBRIDGE_SENTINEL_SECRET_9C5B1"
        ).count() == 0
        assert {
            "alignment_run": app_module.AlignmentRun.query.count(),
            "terminology_card": app_module.TerminologyCard.query.count(),
            "legacy_usage": app_module.UsageRecord.query.count(),
            "ai_call_log": app_module.AICallLog.query.count(),
        } == legacy_before


def test_concurrent_duplicate_mapping_insert_has_one_winner_and_no_database_lock_residue(
    app_module,
    clean_idempotency_records,
):
    with app_module.app.app_context():
        engine = app_module.db.engine
        app_module.db.session.remove()
        independent_session = sessionmaker(bind=engine, expire_on_commit=False)
        results = []
        result_lock = threading.Lock()
        barrier = threading.Barrier(2)

        def insert(execution_key):
            session = independent_session()
            try:
                session.add(_execution(app_module, execution_key))
                barrier.wait(timeout=5)
                session.commit()
            except IntegrityError:
                session.rollback()
                outcome = "conflict"
            except OperationalError as exc:
                session.rollback()
                outcome = f"database-error:{exc}"
            else:
                outcome = "winner"
            finally:
                session.close()
            with result_lock:
                results.append(outcome)

        execution_key = "item-verification-execution-v1:" + "e" * 64
        threads = [threading.Thread(target=insert, args=(execution_key,)) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert all(not thread.is_alive() for thread in threads)
        assert sorted(results) == ["conflict", "winner"]
        assert (
            app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
                execution_key=execution_key
            ).count()
            == 1
        )

        residue_key = "item-verification-execution-v1:" + "f" * 64
        app_module.db.session.add(_execution(app_module, residue_key))
        app_module.db.session.commit()
