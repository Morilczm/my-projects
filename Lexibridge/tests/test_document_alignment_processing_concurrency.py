import threading

import pytest
from sqlalchemy.orm import sessionmaker

from services import document_alignment_processing_orchestrator as orchestrator
from test_document_alignment_processing_orchestrator_integration import (
    _cleanup,
    _formal_counts_for_run,
    _orchestrator_dependencies,
    _setup_governed_workflow,
)


@pytest.fixture(autouse=True)
def _app_context(app_module):
    with app_module.app.app_context():
        yield


@pytest.mark.parametrize("iteration", range(5))
def test_same_lease_duplicate_invocations_converge_without_duplicate_business_rows(app_module, iteration):
    run_uid, lease = _setup_governed_workflow(
        app_module,
        f"concurrent-{iteration}",
        bootstrap=False,
    )
    command = orchestrator.ProcessDocumentAlignmentWorkflowCommand(
        workflow_run_uid=run_uid,
        job_uid=lease.job_uid,
        worker_id=lease.worker_id,
        execution_attempt=lease.execution_attempt,
        lease_token=lease.lease_token,
    )
    Session = sessionmaker(bind=app_module.db.engine)
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def invoke(worker_suffix):
        with app_module.app.app_context():
            session = Session()
            try:
                dependencies = _orchestrator_dependencies(
                    app_module,
                    session,
                    lease,
                    f"concurrent-{iteration}-{worker_suffix}",
                )
                barrier.wait(timeout=5)
                results.append(orchestrator.process_document_alignment_workflow(command, dependencies))
            except Exception as exc:
                errors.append(exc)
            finally:
                session.close()

    threads = [threading.Thread(target=invoke, args=(suffix,)) for suffix in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 2
    assert {result.outcome for result in results} <= {
        "ready_for_review",
        "already_terminal",
        "retryable_interruption",
    }
    app_module.db.session.expire_all()
    run = app_module.DocumentAlignmentWorkflowRun.query.filter_by(run_uid=run_uid).one()
    item_states = [
        (item.item_uid, item.status, item.stage, item.error_code)
        for item in app_module.DocumentAlignmentWorkflowItem.query.order_by(
            app_module.DocumentAlignmentWorkflowItem.id
        ).all()
    ]
    assert run.status == "ready_for_review", {
        "results": [result.__dict__ for result in results],
        "items": item_states,
        "formal_counts": _formal_counts_for_run(app_module, run_uid),
    }
    assert run.total_items == 1
    assert run.ready_for_review_items == 1
    assert app_module.DocumentAlignmentWorkflowItem.query.filter_by(workflow_run_id=run.id).count() == 1
    assert _formal_counts_for_run(app_module, run_uid) == {
        "mappings": 1,
        "cards": 1,
        "preflights": 1,
        "verifications": 1,
        "usage": 1,
    }
    root_events = app_module.AuditRecord.query.filter_by(target_uid=run_uid).all()
    assert len({event.event_identity for event in root_events}) == len(root_events)
    app_module.db.session.commit()
    _cleanup(app_module)
