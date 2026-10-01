import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend" / ".venv-macos" / "bin" / "python"
PYTHON_CMD = str(PYTHON if PYTHON.exists() else sys.executable)


PILOT_TABLES = {
    "document_parse_record",
    "document_parse_block",
    "knowledge_source",
    "knowledge_chunk",
    "concept_alignment_card",
    "alignment_verification_run",
    "alignment_provider_policy",
    "alignment_provider_usage_record",
    "alignment_provider_preflight_run",
    "concept_card_review_record",
    "concept_card_review_assignment",
    "course_review_policy",
    "course_review_permission",
    "student_course_membership",
    "course_student_visibility_policy",
    "student_concept_card_state",
    "concept_card_feedback_triage_record",
    "feedback",
    "audit_record",
}


def run_migration(db_path: Path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["UPLOAD_FOLDER"] = str(db_path.parent / "uploads")
    env["AUTH_REQUIRED"] = "True"
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    env["OCR_PROVIDER"] = "none"
    env["FORMULA_OCR_PROVIDER"] = "none"
    return subprocess.run(
        [PYTHON_CMD, "scripts/migrate_db.py", "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def run_seed(db_path: Path, *args: str):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["UPLOAD_FOLDER"] = str(db_path.parent / "uploads")
    env["AUTH_REQUIRED"] = "True"
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    env["OCR_PROVIDER"] = "none"
    env["FORMULA_OCR_PROVIDER"] = "none"
    return subprocess.run(
        [PYTHON_CMD, "scripts/seed_review_demo.py", *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}


def column_names(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute(f"pragma table_info({table})")}


def test_fresh_database_initialization_is_idempotent(tmp_path):
    db_path = tmp_path / "fresh-pilot.db"
    first = run_migration(db_path)
    second = run_migration(db_path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert PILOT_TABLES <= table_names(db_path)


def test_existing_database_upgrade_adds_pilot_tables_and_preserves_rows(tmp_path):
    db_path = tmp_path / "legacy-upgrade.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "create table user (id integer primary key, username varchar(80), email varchar(160), password_hash text, role varchar(30))"
        )
        conn.execute(
            "insert into user (id, username, email, password_hash, role) values (7, 'legacy_student', 'legacy.student@example.test', 'hash', 'student')"
        )
        conn.execute(
            "create table concept_alignment_card (id integer primary key, card_uid varchar(64), english_term varchar(220), course varchar(160), status varchar(40))"
        )
        conn.execute(
            "insert into concept_alignment_card (id, card_uid, english_term, course, status) values (3, 'legacy-card', 'Legacy term', 'Legacy Course', 'needs_review')"
        )
        conn.execute("create table feedback (id integer primary key, term_id integer, user_id integer, feedback_content text)")
        conn.execute("insert into feedback (id, term_id, user_id, feedback_content) values (5, 0, 7, 'legacy feedback')")
        conn.commit()

    result = run_migration(db_path)
    assert result.returncode == 0, result.stderr
    assert PILOT_TABLES <= table_names(db_path)
    assert {
        "chinese_term",
        "english_evidence",
        "chinese_evidence",
        "confidence_score",
        "risk_labels",
        "reviewed_at",
    } <= column_names(db_path, "concept_alignment_card")
    assert {
        "feedback_uid",
        "card_uid",
        "feedback_source",
        "message",
        "status",
        "linked_review_uid",
    } <= column_names(db_path, "feedback")
    with sqlite3.connect(db_path) as conn:
        user_row = conn.execute("select username from user where id=7").fetchone()
        card_row = conn.execute("select english_term from concept_alignment_card where id=3").fetchone()
        feedback_row = conn.execute("select feedback_content from feedback where id=5").fetchone()
    assert user_row == ("legacy_student",)
    assert card_row == ("Legacy term",)
    assert feedback_row == ("legacy feedback",)


def test_seed_runs_on_upgraded_database_and_is_idempotent(tmp_path):
    db_path = tmp_path / "seed-upgrade.db"
    migration = run_migration(db_path)
    assert migration.returncode == 0, migration.stderr

    first = run_seed(db_path, "--reset-demo")
    second = run_seed(db_path)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    with sqlite3.connect(db_path) as conn:
        course_count = conn.execute("select count(*) from course where name='DEMO Signals and Systems'").fetchone()[0]
        hidden_count = conn.execute("select count(*) from course where name='DEMO Hidden Course'").fetchone()[0]
        approved_count = conn.execute(
            "select count(*) from concept_alignment_card where course='DEMO Signals and Systems' and status='approved'"
        ).fetchone()[0]
        state_count = conn.execute("select count(*) from student_concept_card_state").fetchone()[0]
        feedback_count = conn.execute("select count(*) from feedback where feedback_source='student_concept_card'").fetchone()[0]
    assert course_count == 1
    assert hidden_count == 1
    assert approved_count >= 3
    assert state_count >= 4
    assert feedback_count >= 4
    assert not (ROOT / "pilot_readiness_check.db").exists()


def test_migration_failure_returns_nonzero_for_unwritable_database_path(tmp_path):
    db_path = Path("/dev/null") / "cannot-open.db"
    result = run_migration(db_path)
    assert result.returncode != 0
