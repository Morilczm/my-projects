import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
)


ROOT = Path(__file__).resolve().parents[1]
WORKER_SCRIPT = ROOT / "scripts" / "run_worker.py"


def _job(app_module, job_type, priority):
    now = app_module.current_time_text()
    return app_module.BackgroundJob(
        job_type=job_type,
        status="queued",
        priority=priority,
        created_by=1,
        input_json="{}",
        result_json="{}",
        attempt_count=0,
        max_attempts=3,
        created_at=now,
        updated_at=now,
    )


def _delete_jobs(app_module, job_ids):
    app_module.BackgroundJobEvent.query.filter(
        app_module.BackgroundJobEvent.job_id.in_(job_ids)
    ).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter(app_module.BackgroundJob.id.in_(job_ids)).delete(
        synchronize_session=False
    )
    app_module.db.session.commit()


def _load_worker_cycle():
    tree = ast.parse(WORKER_SCRIPT.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_worker_cycle"
    )
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(WORKER_SCRIPT), "exec"), namespace)
    return namespace["run_worker_cycle"], namespace


def test_database_claim_helpers_isolate_legacy_generic_and_formal_jobs(app_module):
    with app_module.app.app_context():
        formal = _job(app_module, FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE, 1)
        legacy = _job(app_module, app_module.LEGACY_ALIGNMENT_JOB_TYPE, 2)
        ingestion = _job(app_module, "document_ingestion", 3)
        evaluation = _job(app_module, "evaluation_run", 4)
        app_module.db.session.add_all([formal, legacy, ingestion, evaluation])
        app_module.db.session.commit()
        job_ids = [formal.id, legacy.id, ingestion.id, evaluation.id]

        try:
            claimed_generic = app_module.claim_next_generic_background_job("generic-isolation-worker")
            assert claimed_generic.id == ingestion.id
            assert claimed_generic.job_type == "document_ingestion"

            claimed_legacy = app_module.claim_next_legacy_alignment_job("legacy-isolation-worker")
            assert claimed_legacy.id == legacy.id
            assert claimed_legacy.job_type == "alignment_run"

            app_module.db.session.expire_all()
            assert app_module.db.session.get(app_module.BackgroundJob, formal.id).status == "queued"
            assert app_module.db.session.get(app_module.BackgroundJob, evaluation.id).status == "queued"
            assert app_module.db.session.get(app_module.BackgroundJob, legacy.id).locked_by == (
                "legacy-isolation-worker"
            )
        finally:
            _delete_jobs(app_module, job_ids)


def test_filtered_claim_rejects_unsupported_job_types(app_module):
    with app_module.app.app_context():
        with pytest.raises(ValueError, match="Unsupported background job types"):
            app_module.claim_next_background_job("invalid-worker", job_types={"unknown"})


def test_worker_modes_call_only_their_owned_dispatchers():
    run_worker_cycle, namespace = _load_worker_cycle()
    calls = []

    def formal(worker_id):
        calls.append(("formal", worker_id))
        return SimpleNamespace(outcome="no_job_available")

    def generic(worker_id):
        calls.append(("generic", worker_id))
        return None

    def legacy(worker_id):
        calls.append(("legacy", worker_id))
        return None

    namespace["app_module"] = SimpleNamespace(
        run_formal_worker_once=formal,
        run_generic_background_worker_once=generic,
        run_legacy_alignment_worker_once=legacy,
    )

    run_worker_cycle("standard", "standard-worker", True)
    assert calls == [("formal", "standard-worker"), ("generic", "standard-worker")]

    calls.clear()
    run_worker_cycle("formal", "formal-worker")
    assert calls == [("formal", "formal-worker")]

    calls.clear()
    run_worker_cycle("generic", "generic-worker")
    assert calls == [("generic", "generic-worker")]

    calls.clear()
    run_worker_cycle("legacy-alignment", "legacy-worker")
    assert calls == [("legacy", "legacy-worker")]


def test_worker_script_defaults_to_standard_and_requires_explicit_legacy_mode():
    source = WORKER_SCRIPT.read_text(encoding="utf-8")
    assert 'default=os.environ.get("JOB_WORKER_QUEUE_MODE", "standard")' in source
    assert 'elif mode == "legacy-alignment"' in source
    assert "run_legacy_alignment_worker_once" in source
    assert "app_module.run_worker_once" not in source
