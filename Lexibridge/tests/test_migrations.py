import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "backend" / ".venv-macos" / "bin" / "python"
PYTHON_CMD = str(PYTHON if PYTHON.exists() else sys.executable)


def table_names(db_path):
    with sqlite3.connect(db_path) as conn:
        return {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}


def column_names(db_path, table):
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute(f"pragma table_info({table})")}


def run_migration(db_path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["UPLOAD_FOLDER"] = str(db_path.parent / "uploads")
    return subprocess.run(
        [PYTHON_CMD, "scripts/migrate_db.py", "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_empty_database_migration_creates_core_tables(tmp_path):
    db_path = tmp_path / "empty.db"
    result = run_migration(db_path)

    assert result.returncode == 0, result.stderr
    tables = table_names(db_path)
    assert {
        "formula_block",
        "alignment_run",
        "evaluation_set",
        "evaluation_item",
        "evaluation_run",
        "personal_access_audit",
        "audit_record",
        "alignment_verification_run",
        "alignment_provider_policy",
        "alignment_provider_usage_record",
        "alignment_provider_preflight_run",
        "terminology_card",
        "concept_alignment_card",
        "concept_card_review_record",
        "concept_card_review_assignment",
        "course_review_policy",
        "course_review_permission",
        "document_parse_record",
        "document_parse_block",
        "knowledge_source",
        "knowledge_chunk",
        "knowledge_version",
        "knowledge_permission",
        "background_job",
        "background_job_event",
        "iteration_backlog_item",
        "student_pilot_enrollment",
        "student_pilot_session",
        "student_pilot_survey",
    } <= tables


def test_old_schema_database_migration_is_idempotent_and_preserves_data(tmp_path):
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table user (id integer primary key, username varchar(80), email varchar(160), password_hash text, role varchar(30))")
        conn.execute("insert into user (id, username, email, password_hash, role) values (99, 'legacy', 'legacy@example.test', 'hash', 'student')")
        conn.commit()

    first = run_migration(db_path)
    second = run_migration(db_path)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    user_columns = column_names(db_path, "user")
    assert {"is_verified", "verification_token", "reset_token", "created_at", "last_login_at"} <= user_columns
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("select username from user where id=99").fetchone()
    assert row == ("legacy",)


def test_migration_adds_pr5_required_fields(app_module):
    with app_module.app.app_context():
        before_users = app_module.User.query.count()
        before_courses = app_module.Course.query.count()
        app_module.ensure_schema_columns()
        app_module.ensure_schema_columns()
        after_users = app_module.User.query.count()
        after_courses = app_module.Course.query.count()

    db_path = app_module.app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    assert before_users == after_users
    assert before_courses == after_courses
    assert "status" in column_names(db_path, "formula_block")
    assert {
        "formula_region_uid",
        "source_uid",
        "document_uid",
        "detection_method",
        "detection_confidence",
        "surrounding_text_refs_json",
        "source_page_ref",
        "recognizer_provider",
        "recognizer_model",
        "recognition_confidence",
        "latex_candidate",
        "mathml_candidate",
        "abstention_reason",
        "provenance_json",
    } <= column_names(db_path, "formula_block")
    assert "auto_approved_count" in column_names(db_path, "alignment_run")
    assert "report_markdown" in column_names(db_path, "evaluation_run")
    assert "source_alignment_run_id" in column_names(db_path, "terminology_card")
    assert {
        "card_uid",
        "english_term",
        "course",
        "english_evidence",
        "chinese_evidence",
        "confidence_score",
        "risk_labels",
        "parse_uid",
        "parse_quality_status",
        "parse_quality_flags",
        "input_risk_labels",
        "status",
        "version",
    } <= column_names(db_path, "concept_alignment_card")
    assert {
        "review_uid",
        "card_uid",
        "reviewer_id",
        "reviewer_role",
        "reviewer_name",
        "action",
        "previous_status",
        "new_status",
        "decision",
        "reason_code",
        "review_comment",
        "evidence_assessment",
        "term_assessment",
        "risk_assessment",
        "required_changes",
        "resolved_risk_labels",
        "remaining_risk_labels",
        "verification_run_uid",
        "request_id",
    } <= column_names(db_path, "concept_card_review_record")
    assert {
        "assignment_uid",
        "card_uid",
        "assigned_to",
        "assigned_by",
        "assignment_status",
        "due_at",
        "created_at",
        "updated_at",
    } <= column_names(db_path, "concept_card_review_assignment")
    assert {
        "policy_uid",
        "course",
        "chapter",
        "require_human_review",
        "require_two_step_review",
        "require_admin_for_override",
        "allow_teacher_override",
        "allow_approve_with_unverified_alignment",
        "allow_approve_with_partial_text",
        "allow_approve_with_missing_chinese_evidence",
        "allow_approve_with_missing_english_evidence",
        "blocking_risk_labels",
        "override_allowed_risk_labels",
        "override_forbidden_risk_labels",
        "required_evidence_sides",
        "min_required_evidence_count",
        "status",
        "created_by",
        "updated_by",
    } <= column_names(db_path, "course_review_policy")
    assert {
        "permission_uid",
        "course",
        "chapter",
        "reviewer_id",
        "reviewer_role",
        "permission_level",
        "can_review",
        "can_approve",
        "can_override_risk",
        "can_assign_reviewer",
        "status",
        "granted_by",
        "granted_at",
        "revoked_by",
        "revoked_at",
    } <= column_names(db_path, "course_review_permission")
    assert {
        "audit_uid",
        "event_type",
        "target_type",
        "target_uid",
        "before_snapshot",
        "after_snapshot",
        "input_payload",
        "output_payload",
        "changed_fields",
        "result",
        "model_name",
        "prompt_version",
        "retrieval_version",
    } <= column_names(db_path, "audit_record")
    assert {
        "run_uid",
        "card_uid",
        "english_term",
        "chinese_term",
        "provider_name",
        "provider_type",
        "input_payload",
        "output_payload",
        "retrieval_score_summary",
        "candidate_score_summary",
        "alignment_confidence",
        "verification_status",
        "recommendation",
        "risk_labels",
        "prompt_version",
        "prompt_summary",
        "raw_output_summary",
        "parser_version",
        "output_schema_version",
        "provider_response_status",
    } <= column_names(db_path, "alignment_verification_run")
    assert {
        "policy_uid",
        "provider_name",
        "provider_type",
        "enabled",
        "replay_only",
        "allow_external_calls",
        "allow_attach_to_card",
        "allow_production_result",
        "allow_auto_approve",
        "require_human_review",
        "allowed_courses",
        "blocked_courses",
        "allowed_roles",
        "max_calls_per_day",
        "max_calls_per_month",
        "max_estimated_cost_per_call",
        "max_estimated_cost_per_day",
        "max_prompt_chars",
        "max_output_chars",
        "timeout_seconds",
        "max_retries",
        "status",
    } <= column_names(db_path, "alignment_provider_policy")
    assert {
        "usage_uid",
        "provider_name",
        "provider_type",
        "run_uid",
        "card_uid",
        "course",
        "chapter",
        "request_id",
        "estimated_input_tokens",
        "estimated_output_tokens",
        "estimated_cost",
        "actual_cost",
        "provider_response_status",
        "error_code",
        "error_message",
    } <= column_names(db_path, "alignment_provider_usage_record")
    assert {
        "preflight_uid",
        "provider_name",
        "provider_type",
        "policy_uid",
        "course",
        "requested_by",
        "check_status",
        "overall_ready",
        "external_calls_enabled",
        "replay_only",
        "api_key_present",
        "api_key_env_name",
        "policy_summary",
        "check_results",
        "blocking_reasons",
        "warnings",
        "replay_dry_run_status",
        "estimated_cost_per_call",
        "max_estimated_cost_per_call",
        "max_calls_per_day",
        "max_calls_per_month",
        "require_human_review",
        "allow_auto_approve",
        "allow_production_result",
    } <= column_names(db_path, "alignment_provider_preflight_run")
    assert {
        "feedback_source",
        "reported_issue",
        "expected_result",
        "classification",
        "root_cause",
        "converted_to_evaluation_item_id",
        "linked_backlog_item_id",
    } <= column_names(db_path, "feedback")
    assert {
        "parse_uid",
        "source_filename",
        "file_type",
        "parse_status",
        "quality_status",
        "quality_flags",
        "ocr_required",
        "ocr_available",
        "formula_detected",
        "warnings",
    } <= column_names(db_path, "document_parse_record")
    assert {
        "block_uid",
        "parse_uid",
        "block_index",
        "block_type",
        "text",
        "confidence",
        "parser_type",
        "source_locator",
        "quality_flags",
    } <= column_names(db_path, "document_parse_block")
    assert {"parse_uid"} <= column_names(db_path, "knowledge_document")
    assert {
        "chunk_uid",
        "source_uid",
        "parse_uid",
        "parse_block_uid",
        "source_locator",
        "block_type",
        "token_count",
        "char_count",
        "quality_status",
        "quality_flags",
        "trust_level",
        "status",
        "embedding_status",
    } <= column_names(db_path, "knowledge_chunk")
    assert {
        "source_uid",
        "title",
        "course",
        "chapter",
        "source_role",
        "owner_type",
        "owner_id",
        "visibility",
        "trust_level",
        "parse_uid",
        "source_filename",
        "file_type",
        "content_hash",
        "version",
        "license_note",
        "quality_status",
        "quality_flags",
    } <= column_names(db_path, "knowledge_source")
    assert {
        "version_uid",
        "source_uid",
        "version_number",
        "change_type",
        "previous_content_hash",
        "new_content_hash",
        "parse_uid",
        "changed_by",
        "change_note",
    } <= column_names(db_path, "knowledge_version")
    assert {
        "permission_uid",
        "source_uid",
        "principal_type",
        "principal_id",
        "access_level",
    } <= column_names(db_path, "knowledge_permission")
    assert {"parse_uid"} <= column_names(db_path, "courseware_upload")
    assert {"parse_uid"} <= column_names(db_path, "document")
    assert {"parse_uid", "parse_block_uid"} <= column_names(db_path, "document_chunk")
    assert {"parse_uid", "parse_quality_status", "parse_quality_flags", "input_risk_labels", "source_uid", "chunk_uid"} <= column_names(db_path, "term")
    assert {"parse_uid", "parse_quality_status", "parse_quality_flags", "input_risk_labels"} <= column_names(db_path, "terminology_card")
    assert {
        "source_feedback_id",
        "priority",
        "category",
        "acceptance_criteria",
        "closed_at",
    } <= column_names(db_path, "iteration_backlog_item")
    assert {"job_type", "status", "progress_current", "error_code", "locked_by"} <= column_names(db_path, "background_job")
    assert {"job_id", "event_type", "metadata_json"} <= column_names(db_path, "background_job_event")
