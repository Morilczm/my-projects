from services import legacy_alignment_freeze as freeze_service


def _job(app_module, status="queued"):
    now = app_module.current_time_text()
    return app_module.BackgroundJob(
        job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE,
        status=status,
        priority=-10000,
        created_by=1,
        input_json="{}",
        result_json="{}",
        attempt_count=0,
        max_attempts=3,
        created_at=now,
        updated_at=now,
    )


def test_freeze_state_machine_admission_and_worker_policy():
    expected = {
        "active": (True, True),
        "freeze": (False, False),
        "draining": (False, True),
        "disabled": (False, False),
    }
    for state, (creation, worker) in expected.items():
        assert freeze_service.creation_is_allowed(state, True) is creation
        assert freeze_service.worker_claim_is_allowed(state) is worker
    assert freeze_service.creation_is_allowed("active", False) is False


def test_freeze_pauses_claim_and_draining_claims_only_existing_legacy_job(app_module, monkeypatch):
    with app_module.app.app_context():
        job = _job(app_module)
        app_module.db.session.add(job)
        app_module.db.session.commit()
        job_id = job.id
        try:
            monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_RUNTIME_STATE", "freeze")
            assert app_module.claim_next_legacy_alignment_job("freeze-worker") is None
            app_module.db.session.expire_all()
            assert app_module.db.session.get(app_module.BackgroundJob, job_id).status == "queued"

            monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_RUNTIME_STATE", "draining")
            claimed = app_module.claim_next_legacy_alignment_job("drain-worker")
            assert claimed.id == job_id
            assert claimed.status == "running"
            assert claimed.locked_by == "drain-worker"
        finally:
            app_module.BackgroundJobEvent.query.filter_by(job_id=job_id).delete(
                synchronize_session=False
            )
            app_module.BackgroundJob.query.filter_by(id=job_id).delete(synchronize_session=False)
            app_module.db.session.commit()


def test_formal_contract_constants_are_unchanged_by_freeze_boundary(app_module):
    assert app_module.WORKFLOW_VERSION_V1 == "formal-document-alignment-v1"
    assert app_module.FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE == (
        "formal_document_alignment_workflow_v1"
    )
