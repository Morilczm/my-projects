import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend" / ".venv-macos" / "bin" / "python"
PYTHON_CMD = str(PYTHON if PYTHON.exists() else sys.executable)

EXECUTION_TABLE = "document_alignment_item_verification_executions"
IDENTITY_COLUMNS = {
    "alignment_verification_run": "execution_key",
    "alignment_provider_preflight_run": "execution_key",
    "alignment_provider_usage_record": "execution_key",
    "audit_record": "event_identity",
}
IDENTITY_INDEXES = {
    "alignment_verification_run": "uq_alignment_verification_run_execution_key",
    "alignment_provider_preflight_run": "uq_alignment_provider_preflight_execution_key",
    "alignment_provider_usage_record": "uq_alignment_provider_usage_execution_key",
    "audit_record": "uq_audit_record_event_identity",
}


def _migrate(db_path):
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{db_path}",
            "UPLOAD_FOLDER": str(db_path.parent / "uploads"),
            "AUTH_REQUIRED": "True",
            "AI_PROVIDER": "none",
            "ALLOW_MOCK_AI": "True",
            "OCR_PROVIDER": "none",
            "FORMULA_OCR_PROVIDER": "none",
        }
    )
    return subprocess.run(
        [PYTHON_CMD, "scripts/migrate_db.py", "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _tables(connection):
    return {
        row[0]
        for row in connection.execute("select name from sqlite_master where type='table'")
    }


def _columns(connection, table):
    return {row[1] for row in connection.execute(f"pragma table_info({table})")}


def _indexes(connection, table):
    return {row[1]: bool(row[2]) for row in connection.execute(f"pragma index_list({table})")}


def _create_legacy_identity_tables(db_path):
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "create table document_alignment_workflow_runs ("
            "id integer primary key, run_uid varchar(64), source_uid varchar(64), "
            "parse_uid varchar(64), requested_by varchar(120), "
            "idempotency_key varchar(160), idempotency_fingerprint varchar(128), "
            "workflow_version varchar(80))"
        )
        connection.execute(
            "insert into document_alignment_workflow_runs "
            "(id, run_uid, source_uid, parse_uid, requested_by, idempotency_key, "
            "idempotency_fingerprint, workflow_version) values "
            "(9, 'legacy-workflow-run', 'legacy-source', 'legacy-parse', "
            "'legacy-teacher', 'legacy-idempotency', 'legacy-fingerprint', "
            "'formal-document-alignment-v1')"
        )
        connection.execute(
            "create table document_alignment_workflow_items ("
            "id integer primary key, item_uid varchar(64), workflow_run_id integer, "
            "item_key varchar(220), candidate_term varchar(220), normalized_term varchar(220))"
        )
        connection.execute(
            "insert into document_alignment_workflow_items "
            "(id, item_uid, workflow_run_id, item_key, candidate_term, normalized_term) "
            "values (10, 'legacy-workflow-item', 9, 'legacy-item-key', "
            "'Legacy term', 'legacy term')"
        )
        connection.execute(
            "create table alignment_verification_run ("
            "id integer primary key, run_uid varchar(64), english_term varchar(220))"
        )
        connection.execute(
            "insert into alignment_verification_run (id, run_uid, english_term) "
            "values (11, 'legacy-verification', 'Legacy term')"
        )
        connection.execute(
            "create table alignment_provider_preflight_run ("
            "id integer primary key, preflight_uid varchar(64), provider_name varchar(120))"
        )
        connection.execute(
            "insert into alignment_provider_preflight_run "
            "(id, preflight_uid, provider_name) values (12, 'legacy-preflight', 'none')"
        )
        connection.execute(
            "create table alignment_provider_usage_record ("
            "id integer primary key, usage_uid varchar(64), provider_name varchar(120))"
        )
        connection.execute(
            "insert into alignment_provider_usage_record "
            "(id, usage_uid, provider_name) values (13, 'legacy-usage', 'none')"
        )
        connection.execute(
            "create table audit_record ("
            "id integer primary key, audit_uid varchar(64), event_type varchar(120), "
            "target_type varchar(120))"
        )
        connection.execute(
            "insert into audit_record "
            "(id, audit_uid, event_type, target_type) "
            "values (14, 'legacy-audit', 'legacy_event', 'legacy_target')"
        )
        connection.commit()


def test_fresh_database_and_repeated_migration_create_execution_identity_schema(tmp_path):
    database = tmp_path / "fresh-formal-item-execution.db"
    first = _migrate(database)
    second = _migrate(database)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    with sqlite3.connect(database) as connection:
        assert EXECUTION_TABLE in _tables(connection)
        execution_columns = _columns(connection, EXECUTION_TABLE)
        assert {
            "execution_key",
            "workflow_run_uid",
            "workflow_item_uid",
            "preflight_run_uid",
            "verification_run_uid",
            "safe_input_fingerprint",
            "execution_status",
            "safe_error_code",
            "safe_error_message",
        } <= execution_columns
        execution_indexes = _indexes(connection, EXECUTION_TABLE)
        assert execution_indexes["uq_document_alignment_item_verification_execution_key"]
        assert execution_indexes["uq_document_alignment_item_verification_preflight_uid"]
        assert execution_indexes["uq_document_alignment_item_verification_run_uid"]
        for table, column in IDENTITY_COLUMNS.items():
            assert column in _columns(connection, table)
            assert _indexes(connection, table)[IDENTITY_INDEXES[table]]


def test_old_sqlite_upgrade_is_additive_idempotent_preserves_rows_and_does_not_backfill(tmp_path):
    database = tmp_path / "legacy-formal-item-execution.db"
    _create_legacy_identity_tables(database)

    first = _migrate(database)
    second = _migrate(database)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    with sqlite3.connect(database) as connection:
        assert EXECUTION_TABLE in _tables(connection)
        assert connection.execute(
            "select item_uid, workflow_run_id, item_key from "
            "document_alignment_workflow_items where id=10"
        ).fetchone() == ("legacy-workflow-item", 9, "legacy-item-key")
        expected_rows = {
            "alignment_verification_run": (11, "legacy-verification", None),
            "alignment_provider_preflight_run": (12, "legacy-preflight", None),
            "alignment_provider_usage_record": (13, "legacy-usage", None),
            "audit_record": (14, "legacy-audit", None),
        }
        uid_columns = {
            "alignment_verification_run": "run_uid",
            "alignment_provider_preflight_run": "preflight_uid",
            "alignment_provider_usage_record": "usage_uid",
            "audit_record": "audit_uid",
        }
        for table, identity_column in IDENTITY_COLUMNS.items():
            assert identity_column in _columns(connection, table)
            assert _indexes(connection, table)[IDENTITY_INDEXES[table]]
            row = connection.execute(
                f"select id, {uid_columns[table]}, {identity_column} from {table} "
                "where id in (11, 12, 13, 14)"
            ).fetchone()
            assert row == expected_rows[table]


def test_upgraded_nullable_unique_indexes_accept_legacy_nulls_and_reject_duplicate_identity(
    tmp_path,
):
    database = tmp_path / "legacy-null-compatibility.db"
    _create_legacy_identity_tables(database)
    result = _migrate(database)
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(database) as connection:
        for table, identity_column in IDENTITY_COLUMNS.items():
            connection.execute(
                f"insert into {table} ({identity_column}) values (null)"
            )
            connection.execute(
                f"insert into {table} ({identity_column}) values (?)",
                (f"identity-{table}",),
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"insert into {table} ({identity_column}) values (?)",
                    (f"identity-{table}",),
                )
            connection.rollback()


def test_partial_upgrade_with_conflicting_non_null_identity_fails_without_deleting_rows(tmp_path):
    database = tmp_path / "conflicting-formal-item-identity.db"
    _create_legacy_identity_tables(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "alter table alignment_verification_run add column execution_key varchar(128)"
        )
        connection.execute(
            "insert into alignment_verification_run "
            "(id, run_uid, english_term, execution_key) "
            "values (21, 'conflict-a', 'Term A', 'duplicate-execution')"
        )
        connection.execute(
            "insert into alignment_verification_run "
            "(id, run_uid, english_term, execution_key) "
            "values (22, 'conflict-b', 'Term B', 'duplicate-execution')"
        )
        connection.commit()

    result = _migrate(database)
    assert result.returncode != 0
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "select run_uid, execution_key from alignment_verification_run "
            "where id in (21, 22) order by id"
        ).fetchall()
    assert rows == [
        ("conflict-a", "duplicate-execution"),
        ("conflict-b", "duplicate-execution"),
    ]
