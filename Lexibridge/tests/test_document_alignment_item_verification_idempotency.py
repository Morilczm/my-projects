import threading

from sqlalchemy.orm import sessionmaker

from services import alignment_providers
from services import document_alignment_item_verification_adapter as adapter
from services.formal_item_verification_identity import (
    build_formal_item_audit_event_identity,
)
from test_document_alignment_item_verification_adapter_integration import (
    _cleanup,
    _command,
    _dependencies,
    _setup,
)


def _logical_counts(app_module, execution_key):
    audit_identities = [
        build_formal_item_audit_event_identity(execution_key, event_type)
        for event_type in (
            "item_verification_requested",
            "item_verification_provider_completed",
            "item_verification_attached",
            "item_verification_failed",
        )
    ]
    return {
        "mapping": app_module.DocumentAlignmentItemVerificationExecution.query.filter_by(
            execution_key=execution_key
        ).count(),
        "preflight": app_module.AlignmentProviderPreflightRun.query.filter_by(
            execution_key=execution_key
        ).count(),
        "verification": app_module.AlignmentVerificationRun.query.filter_by(
            execution_key=execution_key
        ).count(),
        "usage": app_module.AlignmentProviderUsageRecord.query.filter_by(
            execution_key=execution_key
        ).count(),
        "audit": app_module.AuditRecord.query.filter(
            app_module.AuditRecord.event_identity.in_(audit_identities)
        ).count(),
    }


def test_completed_execution_reuse_keeps_all_logical_identity_counts_stable(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "stable-counts")
        command = _command(run, item, lease, "stable-counts")
        dependencies = _dependencies(app_module)

        first = adapter.execute_document_alignment_item_verification(command, dependencies)
        before = _logical_counts(app_module, first.execution_key)
        second = adapter.execute_document_alignment_item_verification(command, dependencies)
        after = _logical_counts(app_module, first.execution_key)

        assert first.outcome == "needs_review"
        assert second.outcome == "reused_completed_result"
        assert before == after
        assert before["mapping"] == 1
        assert before["preflight"] == 1
        assert before["verification"] == 1
        assert before["usage"] == 1
        assert before["audit"] == 3
        _cleanup(app_module)


def test_two_independent_sessions_may_replay_deterministic_provider_but_keep_one_logical_write_set(app_module):
    with app_module.app.app_context():
        run, item, lease = _setup(app_module, "concurrent")
        command = _command(run, item, lease, "concurrent")
        Session = sessionmaker(bind=app_module.db.engine, expire_on_commit=False)
        barrier = threading.Barrier(2, timeout=10)
        lock = threading.Lock()
        provider_calls = 0
        results = []
        errors = []

        def resolver(provider_name):
            nonlocal provider_calls
            with lock:
                provider_calls += 1
            barrier.wait()
            return alignment_providers.get_alignment_provider(provider_name)

        def worker():
            session = Session()
            try:
                with app_module.app.app_context():
                    dependencies = _dependencies(app_module, provider_resolver=resolver)
                    dependencies = type(dependencies)(
                        session=session,
                        models=dependencies.models,
                        draft=dependencies.draft,
                        governance=dependencies.governance,
                        verification=dependencies.verification,
                        recording=dependencies.recording,
                        fence_active_lease=dependencies.fence_active_lease,
                        current_time_factory=dependencies.current_time_factory,
                        lease_seconds=dependencies.lease_seconds,
                        actor_role=dependencies.actor_role,
                    )
                    results.append(adapter.execute_document_alignment_item_verification(command, dependencies))
            except Exception as exc:
                errors.append(exc)
            finally:
                session.rollback()
                session.close()

        threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert len(results) == 2
        assert provider_calls == 2
        app_module.db.session.expire_all()
        execution_key = next(result.execution_key for result in results if result.execution_key)
        counts = _logical_counts(app_module, execution_key)
        assert counts["mapping"] == 1
        assert counts["preflight"] == 1
        assert counts["verification"] == 1
        assert counts["usage"] == 1
        assert counts["audit"] == 3
        persisted_item = app_module.DocumentAlignmentWorkflowItem.query.filter_by(
            item_uid=item.item_uid
        ).one()
        assert persisted_item.status == "needs_review", [
            (result.outcome, result.execution_status, result.item_status, result.error_message)
            for result in results
        ]
        _cleanup(app_module)
