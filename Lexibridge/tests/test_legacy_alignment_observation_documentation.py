from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_observation_report_records_active_but_unfinished_window():
    report = (ROOT / "docs" / "legacy_alignment_observation_report.md").read_text(
        encoding="utf-8"
    )
    for expected in (
        "LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE",
        "pilot-internal-local",
        "2026-07-22T15:13:47Z",
        "2026-08-05T15:13:47Z",
        "Actual target-environment active days: `0`",
        "UNKNOWN_EXTERNAL_LEGACY_CONSUMER",
        "FORMAL_ONLY_RUNTIME_CONFIRMED",
        "LOG_RETENTION_LIMITED",
        "LEGACY_ALIGNMENT_410_NOT_AUTHORIZED",
    ):
        assert expected in report
    assert "LEGACY_ALIGNMENT_DEPRECATION_OBSERVATION_COMPLETE" not in report
    assert "LEGACY_ALIGNMENT_410_READY" not in report


def test_rollback_procedure_names_owner_and_restarts_window():
    procedure = (ROOT / "docs" / "legacy_alignment_rollback_procedure.md").read_text(
        encoding="utf-8"
    )
    for expected in (
        "pilot-internal-local",
        "Rollback owner: Project Maintainer",
        "LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE",
        "ROLLBACK_READY_FREEZE_NOT_EXECUTED",
        "LEGACY_ALIGNMENT_RUNTIME_STATE=freeze",
        "LEGACY_ALIGNMENT_RUNTIME_STATE=active",
        "LEGACY_ALIGNMENT_ROUTE_ADMISSION_ENABLED=true",
        "restart the full observation window",
        "LEGACY_ALIGNMENT_ROLLBACK_REHEARSAL_PASS",
    ):
        assert expected in procedure


def test_pilot_environment_declares_active_runtime_evidence():
    declaration = (ROOT / "docs" / "pilot_environment_declaration.md").read_text(
        encoding="utf-8"
    )
    for expected in (
        "pilot-internal-local",
        "f04c32c38423192a3088bf32151ae51127eb3b3f",
        "ff86db830c53cd96466e6da080206eab2d383f74",
        "project-root/backend/lexibridge.db",
        "pilot-internal-formal-1",
        "pilot-internal-legacy-1",
        "127.0.0.1:5100",
        "Observation owner | Project Maintainer",
        "Gateway/reverse-proxy logs | none | `NOT_AVAILABLE`",
        "## Metric Availability Matrix",
        "EXTERNAL_CONSUMER_VISIBILITY_LIMITED",
        "LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE",
        "LOG_RETENTION_LIMITED",
    ):
        assert expected in declaration
    assert "LEGACY_ALIGNMENT_410_READY" not in declaration


def test_snapshot_procedure_covers_legacy_and_formal_state_without_live_restore():
    procedure = (ROOT / "docs" / "pilot_database_snapshot_procedure.md").read_text(
        encoding="utf-8"
    )
    for expected in (
        "alignment_run",
        "background_job",
        "background_job_event",
        "document_alignment_workflow_runs",
        "scripts/pilot_backup.py",
        "scripts/verify_pilot_backup.py",
        "scripts/pilot_restore.py",
        "Never use `--force` against the declared live source",
    ):
        assert expected in procedure


def test_migration_notice_records_controlled_distribution_but_not_retirement():
    notice = (ROOT / "docs" / "legacy_alignment_migration_notice.md").read_text(
        encoding="utf-8"
    )
    for expected in (
        "Publication status: `DISTRIBUTED`",
        "2026-07-22T15:17:39Z",
        "pilot-internal-local",
        "Project Maintainer",
        "LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE",
        "external client-owner list exists",
    ):
        assert expected in notice
    assert "does not announce retirement" in notice
    assert "LEGACY_ALIGNMENT_410_READY" not in notice


def test_day0_snapshot_records_database_process_queue_and_metric_baseline():
    day0 = (ROOT / "docs" / "legacy_alignment_observation_day0.md").read_text(
        encoding="utf-8"
    )
    for expected in (
        "LEGACY_ALIGNMENT_OBSERVATION_WINDOW_ACTIVE",
        "2026-07-22T15:13:47Z",
        "ff86db830c53cd96466e6da080206eab2d383f74",
        "42a195ab9033124f44f0441dc61c7c1effb5591a6b07db704429c226b5ebcaf0",
        "pilot-backup-54608165f43e4c1493b2248a816b7146",
        "pilot-internal-formal-1",
        "pilot-internal-legacy-1",
        "STOPPED_BY_POLICY",
        "Legacy queued jobs | 0",
        "Legacy POST requests | 0",
        "LOG_RETENTION_LIMITED",
        "Day 0 activation baseline; not an operating day",
    ):
        assert expected in day0
    assert "LEGACY_ALIGNMENT_DEPRECATION_OBSERVATION_COMPLETE" not in day0
    assert "LEGACY_ALIGNMENT_410_READY" not in day0


def test_daily_checklist_requires_traffic_queue_formal_and_owner_evidence():
    checklist = (
        ROOT / "docs" / "legacy_alignment_observation_daily_checklist.md"
    ).read_text(encoding="utf-8")
    for expected in (
        "POST /api/alignment/run",
        "GET /api/alignment/runs",
        "Legacy BackgroundJob creation",
        "Formal worker execution",
        "legacy_alignment_requests=0",
        "External-consumer status remains evidence-based",
        "at least 14 continuous calendar days and five",
    ):
        assert expected in checklist


def test_openapi_keeps_deprecated_legacy_operation_and_pending_window_note():
    text = (ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8")
    operation = text.split("  /api/alignment/run:", 1)[1].split(
        "\n  /api/alignment/runs:", 1
    )[0]
    assert "deprecated: true" in operation
    assert "14 continuous days" in operation
    assert "five operating days" in operation
    assert '"410"' not in operation
