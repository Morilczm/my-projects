from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
from services.formal_background_job_execution import (
    CLAIM_OUTCOME_CLAIMED,
    FORMAL_JOB_DEFAULT_LEASE_SECONDS,
    LEASE_OUTCOME_LEASE_EXPIRED,
    LEASE_OUTCOME_STALE_ATTEMPT,
    FormalBackgroundJobExecutionDependencies,
    claim_next_formal_background_job,
    complete_formal_background_job,
)


NOW = datetime(2026, 7, 18, 9, 0, 0)


def _database(app_module, tmp_path):
    path = tmp_path / "formal-job-concurrency.db"
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    app_module.BackgroundJob.__table__.create(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _job(app_module, **overrides):
    values = {
        "job_type": FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        "status": "queued",
        "priority": 100,
        "created_by": 1,
        "input_json": "{}",
        "result_json": "{}",
        "attempt_count": 0,
        "max_attempts": 3,
        "created_at": "2026-07-18 08:59:00",
        "updated_at": "2026-07-18 08:59:00",
    }
    values.update(overrides)
    return app_module.BackgroundJob(**values)


def _deps(session, model, worker_time, token):
    return FormalBackgroundJobExecutionDependencies(
        session=session,
        job_model=model,
        current_time_factory=lambda: worker_time,
        lease_token_factory=lambda: token,
    )


def test_two_sessions_claim_one_formal_job_exactly_once_over_twenty_races(monkeypatch, app_module, tmp_path):
    import services.formal_background_job_execution as service

    engine, sessions = _database(app_module, tmp_path)
    original_candidates = service._candidate_rows

    try:
        for iteration in range(20):
            setup = sessions()
            setup.add(_job(app_module, priority=iteration))
            setup.commit()
            setup.close()

            barrier = Barrier(2)

            def synchronized_candidates(*args, **kwargs):
                rows = original_candidates(*args, **kwargs)
                barrier.wait(timeout=5)
                return rows

            monkeypatch.setattr(service, "_candidate_rows", synchronized_candidates)

            def compete(worker_id):
                session = sessions()
                try:
                    return claim_next_formal_background_job(
                        worker_id,
                        _deps(session, app_module.BackgroundJob, NOW, f"token-{iteration}-{worker_id}"),
                    )
                finally:
                    session.close()

            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(compete, ("worker-a", "worker-b")))

            assert sum(result.outcome == CLAIM_OUTCOME_CLAIMED for result in results) == 1
            verify = sessions()
            rows = verify.query(app_module.BackgroundJob).all()
            assert len(rows) == iteration + 1
            assert sum(row.status == "running" for row in rows) == iteration + 1
            assert rows[-1].execution_attempt == 1
            verify.close()
    finally:
        engine.dispose()


def test_two_sessions_reclaim_one_stale_job_once_and_old_owner_is_fenced(monkeypatch, app_module, tmp_path):
    import services.formal_background_job_execution as service

    engine, sessions = _database(app_module, tmp_path)
    setup = sessions()
    setup.add(_job(app_module))
    setup.commit()
    first = claim_next_formal_background_job(
        "worker-old",
        _deps(setup, app_module.BackgroundJob, NOW, "old-token"),
    ).lease
    setup.close()

    reclaim_time = NOW + timedelta(seconds=FORMAL_JOB_DEFAULT_LEASE_SECONDS)
    original_candidates = service._candidate_rows
    barrier = Barrier(2)

    def synchronized_candidates(*args, **kwargs):
        rows = original_candidates(*args, **kwargs)
        barrier.wait(timeout=5)
        return rows

    monkeypatch.setattr(service, "_candidate_rows", synchronized_candidates)

    def reclaim(worker_id):
        session = sessions()
        try:
            return claim_next_formal_background_job(
                worker_id,
                _deps(session, app_module.BackgroundJob, reclaim_time, f"new-token-{worker_id}"),
            )
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reclaim, ("worker-b", "worker-c")))
        winners = [result for result in results if result.outcome == CLAIM_OUTCOME_CLAIMED]
        assert len(winners) == 1
        assert winners[0].lease.execution_attempt == 2

        old_session = sessions()
        old_result = complete_formal_background_job(
            first,
            _deps(old_session, app_module.BackgroundJob, reclaim_time + timedelta(seconds=1), "unused"),
        )
        old_session.close()
        assert old_result.outcome == LEASE_OUTCOME_STALE_ATTEMPT

        verify = sessions()
        stored = verify.query(app_module.BackgroundJob).one()
        assert stored.status == "running"
        assert stored.execution_attempt == 2
        verify.close()
    finally:
        engine.dispose()


def test_expiry_boundary_prevents_old_finalize_and_terminal_prevents_reclaim(app_module, tmp_path):
    engine, sessions = _database(app_module, tmp_path)
    setup = sessions()
    setup.add(_job(app_module))
    setup.commit()
    lease = claim_next_formal_background_job("worker-a", _deps(setup, app_module.BackgroundJob, NOW, "token-a")).lease
    setup.close()

    expiry = NOW + timedelta(seconds=FORMAL_JOB_DEFAULT_LEASE_SECONDS)
    try:
        old = sessions()
        rejected = complete_formal_background_job(lease, _deps(old, app_module.BackgroundJob, expiry, "unused"))
        old.close()
        assert rejected.outcome == LEASE_OUTCOME_LEASE_EXPIRED

        reclaim = sessions()
        current = claim_next_formal_background_job("worker-b", _deps(reclaim, app_module.BackgroundJob, expiry, "token-b")).lease
        reclaim.close()

        finisher = sessions()
        completed = complete_formal_background_job(
            current,
            _deps(finisher, app_module.BackgroundJob, expiry + timedelta(seconds=1), "unused"),
        )
        finisher.close()
        assert completed.status == "completed"

        late = sessions()
        no_reclaim = claim_next_formal_background_job(
            "worker-c",
            _deps(late, app_module.BackgroundJob, expiry + timedelta(minutes=10), "token-c"),
        )
        late.close()
        assert no_reclaim.lease is None
    finally:
        engine.dispose()
