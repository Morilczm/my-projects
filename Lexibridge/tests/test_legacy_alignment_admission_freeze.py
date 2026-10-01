from io import BytesIO

import pytest


def _counts(app_module):
    return {
        "documents": app_module.Document.query.count(),
        "alignment_runs": app_module.AlignmentRun.query.count(),
        "background_jobs": app_module.BackgroundJob.query.count(),
        "job_events": app_module.BackgroundJobEvent.query.count(),
        "cards": app_module.TerminologyCard.query.count(),
    }


def _freeze(monkeypatch, app_module):
    monkeypatch.setattr(
        app_module,
        "LEGACY_ALIGNMENT_RUNTIME_STATE",
        app_module.legacy_alignment_freeze_service.RUNTIME_STATE_FREEZE,
    )
    monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED", False)


@pytest.mark.parametrize("sync", [False, True])
def test_freeze_blocks_legacy_http_async_and_sync_with_zero_writes(
    app_module,
    client,
    teacher_token,
    test_course,
    monkeypatch,
    sync,
):
    _freeze(monkeypatch, app_module)
    with app_module.app.app_context():
        before = _counts(app_module)

    suffix = "?sync=true" if sync else ""
    response = client.post(
        f"/api/alignment/run{suffix}",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={
            "english_term": "Freeze Admission Term",
            "scope_type": "course",
            "course_id": test_course.id,
        },
    )

    assert response.status_code == 503
    assert response.get_json()["error_code"] == "LEGACY_ALIGNMENT_ADMISSION_DISABLED"
    with app_module.app.app_context():
        assert _counts(app_module) == before


def test_freeze_blocks_sync_upload_before_document_or_legacy_writes(
    app_module,
    client,
    teacher_token,
    test_course,
    monkeypatch,
):
    _freeze(monkeypatch, app_module)
    with app_module.app.app_context():
        before = _counts(app_module)

    response = client.post(
        "/api/documents/upload?sync=true",
        headers={"Authorization": f"Bearer {teacher_token}"},
        data={
            "scope_type": "course",
            "course_id": str(test_course.id),
            "language": "en",
            "file": (BytesIO(b"Fourier Transform freeze boundary."), "freeze-boundary.txt"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 503
    assert response.get_json()["error_code"] == "LEGACY_ALIGNMENT_ADMISSION_DISABLED"
    with app_module.app.app_context():
        assert _counts(app_module) == before


def test_freeze_blocks_internal_helper_and_legacy_job_factory(app_module, monkeypatch):
    _freeze(monkeypatch, app_module)
    error = app_module.legacy_alignment_freeze_service.LegacyAlignmentAdmissionError

    with app_module.app.app_context():
        before = _counts(app_module)
        with pytest.raises(error, match="LEGACY_ALIGNMENT_ADMISSION_DISABLED"):
            app_module.run_alignment_for_chunks([])
        with pytest.raises(error, match="LEGACY_ALIGNMENT_ADMISSION_DISABLED"):
            app_module.create_background_job(
                app_module.LEGACY_ALIGNMENT_JOB_TYPE,
                1,
                input_data={"english_term": "must not be queued"},
            )
        app_module.db.session.rollback()
        assert _counts(app_module) == before


def test_draining_worker_reuses_existing_run_without_new_alignment_run(app_module, monkeypatch):
    service = app_module.legacy_alignment_freeze_service
    monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_RUNTIME_STATE", service.RUNTIME_STATE_DRAINING)
    monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED", False)

    with app_module.app.app_context():
        run = app_module.AlignmentRun(
            triggered_by=1,
            provider="mock",
            model_name="mock",
            status="queued",
        )
        app_module.db.session.add(run)
        app_module.db.session.commit()
        run_id = run.id
        before = app_module.AlignmentRun.query.count()
        try:
            cards = app_module.run_alignment_for_chunks([], alignment_run=run)
            app_module.db.session.flush()
            assert cards == []
            assert app_module.AlignmentRun.query.count() == before
            assert app_module.db.session.get(app_module.AlignmentRun, run_id).id == run_id
        finally:
            app_module.db.session.delete(app_module.db.session.get(app_module.AlignmentRun, run_id))
            app_module.db.session.commit()
