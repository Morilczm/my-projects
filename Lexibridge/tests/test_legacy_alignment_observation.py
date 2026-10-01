import json
import logging
import subprocess
import sys


LOGGER_NAME = "lexibridge"
SENTINEL = "LEXIBRIDGE_SENTINEL_SECRET_9C5O"


def _observation_records(caplog):
    records = []
    for record in caplog.records:
        try:
            payload = json.loads(record.getMessage())
        except (TypeError, ValueError):
            continue
        if payload.get("module") == "legacy_alignment_observation":
            records.append(payload)
    return records


def _delete_legacy_job(app_module, job_id, run_id):
    app_module.BackgroundJobEvent.query.filter_by(job_id=job_id).delete(synchronize_session=False)
    app_module.BackgroundJob.query.filter_by(id=job_id).delete(synchronize_session=False)
    app_module.AlignmentRun.query.filter_by(id=run_id).delete(synchronize_session=False)
    app_module.db.session.commit()


def test_legacy_post_logs_safe_caller_result_and_creation_counts(
    app_module,
    client,
    teacher_token,
    test_course,
    caplog,
):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    response = client.post(
        "/api/alignment/run",
        headers={
            "Authorization": f"Bearer {teacher_token}",
            "X-Request-ID": "legacy-observation-request",
        },
        json={
            "english_term": SENTINEL,
            "course_id": test_course.id,
            "scope_type": "course",
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    job_id = body["data"]["job_id"]
    run_id = body["data"]["alignment_run_id"]
    try:
        event = _observation_records(caplog)[-1]
        assert event["event"] == "legacy_alignment_request"
        assert event["route"] == "/api/alignment/run"
        assert event["request_mode"] == "async"
        assert event["caller_role"] == "teacher"
        assert event["result"] == "success"
        assert event["alignment_run_creations"] == 1
        assert event["background_job_creations"] == 1
        rendered = json.dumps(event, sort_keys=True)
        assert SENTINEL not in rendered
        assert "Authorization" not in rendered
        assert "Cookie" not in rendered
    finally:
        with app_module.app.app_context():
            _delete_legacy_job(app_module, job_id, run_id)


def test_freeze_and_history_get_emit_observation_without_domain_writes(
    app_module,
    client,
    teacher_token,
    test_course,
    caplog,
    monkeypatch,
):
    service = app_module.legacy_alignment_freeze_service
    monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_RUNTIME_STATE", service.RUNTIME_STATE_FREEZE)
    monkeypatch.setattr(app_module, "LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED", False)
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    with app_module.app.app_context():
        before = {
            "runs": app_module.AlignmentRun.query.count(),
            "jobs": app_module.BackgroundJob.query.filter_by(
                job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE
            ).count(),
        }

    blocked = client.post(
        "/api/alignment/run",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"english_term": SENTINEL, "course_id": test_course.id},
    )
    history = client.get(
        "/api/alignment/runs?page=1&page_size=5",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert blocked.status_code == 503
    assert history.status_code == 200
    events = _observation_records(caplog)
    blocked_event = next(event for event in events if event["route"] == "/api/alignment/run")
    history_event = next(event for event in events if event["route"] == "/api/alignment/runs")
    assert blocked_event["result"] == "admission_blocked"
    assert blocked_event["alignment_run_creations"] == 0
    assert blocked_event["background_job_creations"] == 0
    assert history_event["request_mode"] == "read"
    with app_module.app.app_context():
        assert before == {
            "runs": app_module.AlignmentRun.query.count(),
            "jobs": app_module.BackgroundJob.query.filter_by(
                job_type=app_module.LEGACY_ALIGNMENT_JOB_TYPE
            ).count(),
        }


def test_internal_creation_signal_and_log_summary_are_conservative(app_module, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER_NAME)
    with app_module.app.app_context():
        job = app_module.create_background_job(
            app_module.LEGACY_ALIGNMENT_JOB_TYPE,
            1,
            input_data={"english_term": SENTINEL},
        )
        job_id = job.id
        app_module.db.session.rollback()
    events = _observation_records(caplog)
    internal = next(event for event in events if event["event"] == "legacy_alignment_internal_creation")
    assert internal["entity"] == "background_job"
    assert internal["result"] == "created_in_transaction"
    assert SENTINEL not in json.dumps(internal, sort_keys=True)

    summary = app_module.legacy_alignment_observation_service.summarize_events(
        json.dumps(event, sort_keys=True) for event in events
    )
    assert summary["internal_creation_signal_count"] == 1
    assert summary["legacy_creation_signal_count"] == 1
    with app_module.app.app_context():
        assert app_module.db.session.get(app_module.BackgroundJob, job_id) is None


def test_observation_service_and_cli_do_not_import_flask_or_models():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    service_source = (root / "backend" / "services" / "legacy_alignment_observation.py").read_text(
        encoding="utf-8"
    )
    cli_source = (root / "scripts" / "legacy_alignment_observation_report.py").read_text(
        encoding="utf-8"
    )
    assert "from flask" not in service_source
    assert "backend.app" not in service_source
    assert "db.session" not in service_source
    assert "request.get_json" not in service_source
    assert "credential" not in service_source.lower()
    assert "input_payload" not in service_source
    assert "backend.app" not in cli_source


def test_observation_report_keeps_short_or_unknown_window_pending(tmp_path):
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    log_path = tmp_path / "legacy-observation.log"
    output = tmp_path / "report.json"
    log_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-22T00:00:00Z",
                "module": "legacy_alignment_observation",
                "event": "legacy_alignment_request",
                "method": "GET",
                "route": "/api/alignment/runs",
                "result": "success",
                "caller_role": "teacher",
                "caller_id": 7,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/legacy_alignment_observation_report.py",
            "--log",
            str(log_path),
            "--environment",
            "pilot-test",
            "--database",
            "isolated-test",
            "--window-start",
            "2026-07-22T00:00:00Z",
            "--window-end",
            "2026-08-03T23:59:59Z",
            "--active-days",
            "5",
            "--json-output",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == "OBSERVATION_WINDOW_PENDING"
    assert payload["duration_days"] < 14
    assert payload["gates"]["five_active_days"] is True
    assert payload["gates"]["fourteen_continuous_days"] is False
    assert payload["gates"]["external_consumer_boundary_supported"] is False
