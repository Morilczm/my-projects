import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from services.document_alignment_workflow_contract import FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE


ROOT = Path(__file__).resolve().parents[1]
PYTHON_CMD = sys.executable

LEASE_COLUMNS = {
    "job_uid",
    "execution_attempt",
    "lease_token",
    "heartbeat_at",
    "lease_expires_at",
}


def _migrate(db_path):
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{db_path}",
        "UPLOAD_FOLDER": str(db_path.parent / "uploads"),
        "AUTH_REQUIRED": "True",
        "AI_PROVIDER": "none",
        "OCR_PROVIDER": "none",
        "FORMULA_OCR_PROVIDER": "none",
    })
    return subprocess.run(
        [PYTHON_CMD, "scripts/migrate_db.py", "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _columns(db_path):
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute("pragma table_info(background_job)")}


def _indexes(db_path):
    with sqlite3.connect(db_path) as connection:
        return {row[1] for row in connection.execute("pragma index_list(background_job)")}


def test_migration_subprocess_uses_active_test_interpreter(monkeypatch, tmp_path):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    _migrate(tmp_path / "interpreter-contract.db")

    assert captured["command"] == [sys.executable, "scripts/migrate_db.py", "--apply"]
    assert captured["kwargs"]["cwd"] == ROOT
    assert captured["kwargs"]["env"]["DATABASE_URL"].endswith("/interpreter-contract.db")
    assert captured["kwargs"]["check"] is False


def test_fresh_and_repeated_migration_create_formal_lease_schema(tmp_path):
    database = tmp_path / "fresh-lease.db"
    first = _migrate(database)
    second = _migrate(database)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert LEASE_COLUMNS <= _columns(database)
    assert {
        "ix_background_job_job_uid",
        "ix_background_job_formal_claim",
        "ix_background_job_formal_stale_lease",
    } <= _indexes(database)


def test_existing_background_job_upgrade_is_additive_and_preserves_legacy_row(tmp_path):
    database = tmp_path / "legacy-background-job.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "create table background_job ("
            "id integer primary key, job_type varchar(80), status varchar(40), "
            "priority integer, attempt_count integer, max_attempts integer, "
            "locked_by varchar(120), locked_at varchar(40))"
        )
        connection.execute(
            "insert into background_job "
            "(id, job_type, status, priority, attempt_count, max_attempts, locked_by, locked_at) "
            "values (17, 'document_ingestion', 'queued', 100, 0, 3, '', '')"
        )
        connection.commit()

    result = _migrate(database)
    repeated = _migrate(database)
    assert result.returncode == 0, result.stderr
    assert repeated.returncode == 0, repeated.stderr
    assert LEASE_COLUMNS <= _columns(database)
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "select id, job_type, status, attempt_count from background_job where id=17"
        ).fetchone()
    assert row == (17, "document_ingestion", "queued", 0)


def test_formal_admission_job_gets_stable_uid_without_changing_minimal_payload(app_module):
    from services.document_alignment_workflow_application import _build_background_job

    class Source:
        visibility = "course"

    class Run:
        run_uid = "workflow-run-schema-9c4z"
        workflow_version = "formal-document-alignment-v1"

    class Command:
        requested_by = "1"

    class Dependencies:
        current_time_factory = staticmethod(lambda: "2026-07-18 10:00:00")
        background_job_model = app_module.BackgroundJob

    with app_module.app.app_context():
        job = _build_background_job(Dependencies(), Command(), Source(), Run())
        app_module.db.session.add(job)
        app_module.db.session.flush()
        assert job.job_type == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE
        assert job.job_uid
        assert job.execution_attempt == 0
        assert job.lease_token in {None, ""}
        assert job.input_json == '{"workflow_run_uid": "workflow-run-schema-9c4z", "workflow_version": "formal-document-alignment-v1"}'
        app_module.db.session.rollback()
