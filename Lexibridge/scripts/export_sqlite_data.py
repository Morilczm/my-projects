#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path


DEFAULT_TABLES = {
    "user": "users.jsonl",
    "course": "courses.jsonl",
    "course_member": "course_members.jsonl",
    "document": "documents.jsonl",
    "document_chunk": "document_chunks.jsonl",
    "knowledge_base_version": "knowledge_base_versions.jsonl",
    "knowledge_source": "knowledge_sources.jsonl",
    "knowledge_chunk": "knowledge_chunks.jsonl",
    "retrieval_run": "retrieval_runs.jsonl",
    "retrieval_experiment_run": "retrieval_experiment_runs.jsonl",
    "formula_block": "formula_blocks.jsonl",
    "terminology_card": "terminology_cards.jsonl",
    "alignment_run": "alignment_runs.jsonl",
    "evaluation_set": "evaluation_sets.jsonl",
    "evaluation_item": "evaluation_items.jsonl",
    "evaluation_run": "evaluation_runs.jsonl",
    "background_job": "background_jobs.jsonl",
    "feedback": "feedback.jsonl",
    "iteration_backlog_item": "iteration_backlog.jsonl",
    "usage_record": "usage_records.jsonl",
    "system_log": "system_logs.jsonl",
    "storage_object": "storage_objects.jsonl",
    "ai_provider_config": "ai_provider_configs.jsonl",
    "ai_model_registry": "ai_model_registry.jsonl",
    "prompt_template": "prompt_templates.jsonl",
    "ai_call_log": "ai_call_logs.jsonl",
}
SENSITIVE_COLUMNS = {"password_hash", "token", "token_hash", "reset_token", "verification_token"}


def row_to_dict(cursor, row):
    return {cursor.description[index][0]: row[index] for index in range(len(row))}


def redact_record(record):
    return {key: ("[REDACTED]" if key in SENSITIVE_COLUMNS else value) for key, value in record.items()}


def table_exists(conn, table):
    return conn.execute("select name from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None


def export_table(conn, table, output_path, exclude_personal=False, demo_only=False):
    if not table_exists(conn, table):
        return 0, f"missing table {table}"
    cursor = conn.execute(f"select * from {table}")
    count = 0
    with output_path.open("w", encoding="utf-8") as handle:
        for row in cursor:
            record = redact_record(row_to_dict(cursor, row))
            if exclude_personal and record.get("scope_type") == "personal":
                continue
            if demo_only and not (
                str(record.get("source_type", "")).startswith("demo")
                or str(record.get("course_code", "")).startswith(("DS101", "SP101", "MATH101"))
                or "demo" in str(record.get("name", "")).lower()
            ):
                continue
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1
    return count, ""


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="backend/lexibridge.db")
    parser.add_argument("--output", default="")
    parser.add_argument("--demo-only", action="store_true")
    parser.add_argument("--exclude-personal", action="store_true")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        raise SystemExit(f"SQLite database not found: {db_path}")
    output_dir = Path(args.output or f"exports/sqlite_export_{datetime.utcnow():%Y%m%d_%H%M%S}")
    output_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    counts = {}
    with sqlite3.connect(db_path) as conn:
        for table, filename in DEFAULT_TABLES.items():
            count, warning = export_table(conn, table, output_dir / filename, args.exclude_personal, args.demo_only)
            counts[table] = count
            if warning:
                warnings.append(warning)
    metadata = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "database_engine": "sqlite",
        "database_path": str(db_path),
        "table_counts": counts,
        "warnings": warnings,
        "app_version": "local-mvp-v0.8",
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SQLite export written: {output_dir}")
    print(json.dumps({"table_counts": counts, "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
