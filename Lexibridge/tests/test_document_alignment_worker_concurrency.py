from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.document_alignment_worker_handler import (
    OUTCOME_COMPLETED,
    RunFormalDocumentAlignmentJobResult,
)
from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
from services.formal_background_job_dispatch import (
    FormalBackgroundJobDispatchDependencies,
    run_one_formal_document_alignment_job,
)
from services.formal_background_job_execution import (
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
)


NOW = datetime(2026, 7, 19, 10, 30, 0)


def test_two_independent_dispatchers_have_one_execution_owner_over_ten_races(
    monkeypatch,
    app_module,
    tmp_path,
):
    import services.formal_background_job_execution as ownership_service

    engine = create_engine(
        f"sqlite:///{tmp_path / 'formal-worker-dispatch-races.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    app_module.BackgroundJob.__table__.create(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    original_candidates = ownership_service._candidate_rows
    handled_attempts = []

    try:
        for iteration in range(10):
            setup = sessions()
            setup.add(
                app_module.BackgroundJob(
                    job_type=FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
                    status="queued",
                    priority=iteration,
                    created_by=1,
                    input_json="{}",
                    result_json="{}",
                    attempt_count=0,
                    max_attempts=3,
                    created_at="2026-07-19 10:29:00",
                    updated_at="2026-07-19 10:29:00",
                )
            )
            setup.commit()
            setup.close()
            barrier = Barrier(2)

            def synchronized_candidates(*args, **kwargs):
                rows = original_candidates(*args, **kwargs)
                barrier.wait(timeout=5)
                return rows

            monkeypatch.setattr(ownership_service, "_candidate_rows", synchronized_candidates)

            def dispatch(worker_id):
                session = sessions()
                try:
                    dependencies = FormalBackgroundJobExecutionDependencies(
                        session=session,
                        job_model=app_module.BackgroundJob,
                        current_time_factory=lambda: NOW,
                        lease_token_factory=lambda: f"token-{iteration}-{worker_id}",
                    )
                    return run_one_formal_document_alignment_job(
                        worker_id,
                        FormalBackgroundJobDispatchDependencies(
                            claim=lambda active_worker: claim_next_formal_background_job(
                                active_worker, dependencies
                            ),
                            handle=lambda lease: handled_attempts.append(
                                (iteration, lease.worker_id, lease.execution_attempt)
                            )
                            or RunFormalDocumentAlignmentJobResult(
                                outcome=OUTCOME_COMPLETED,
                                job_uid=lease.job_uid,
                                workflow_run_uid=f"run-{iteration}",
                                job_status="running",
                                run_status="processing",
                                run_stage="verification",
                                execution_attempt=lease.execution_attempt,
                            ),
                        ),
                    )
                finally:
                    session.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(dispatch, (f"worker-a-{iteration}", f"worker-b-{iteration}")))

            assert sum(result.job_uid != "" for result in results) == 1
            assert sum(record[0] == iteration for record in handled_attempts) == 1
            verify = sessions()
            current = verify.query(app_module.BackgroundJob).order_by(app_module.BackgroundJob.id.desc()).first()
            assert current.status == "running"
            assert current.execution_attempt == 1
            assert current.attempt_count == 0
            verify.close()
    finally:
        engine.dispose()
