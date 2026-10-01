from dataclasses import dataclass


@dataclass
class SchemaIssue:
    severity: str
    table: str
    message: str
    recommendation: str

    def as_dict(self):
        return {
            "severity": self.severity,
            "table": self.table,
            "message": self.message,
            "recommendation": self.recommendation,
        }


def audit_schema(models: dict, table_columns: dict) -> dict:
    issues = []
    checked = len(table_columns)

    for table_name, columns in table_columns.items():
        colset = set(columns)
        if "id" not in colset:
            issues.append(SchemaIssue("warn", table_name, "Missing explicit id primary key in reflected columns.", "Confirm primary key before PostgreSQL migration."))
        if table_name in {"document", "formula_block"}:
            legacy_fields = {"saved_filename", "image_path"} & colset
            if legacy_fields:
                issues.append(SchemaIssue("warn", table_name, f"Legacy local path fields remain: {', '.join(sorted(legacy_fields))}.", "Prefer storage_key + StorageObject; keep legacy fields read-only for compatibility."))
        if table_name in {"document", "terminology_card", "feedback", "knowledge_chunk"}:
            if "owner_user_id" not in colset and table_name in {"document", "terminology_card"}:
                issues.append(SchemaIssue("warn", table_name, "Owner column missing or weak for privacy scope.", "Add owner_user_id index and enforce access in API."))
            if "course_id" not in colset and table_name != "feedback":
                issues.append(SchemaIssue("info", table_name, "No course_id column found.", "Confirm whether the table is global-only."))
        if table_name in {"background_job", "terminology_card"}:
            issues.append(SchemaIssue("warn", table_name, "Missing explicit composite index recommendations in Local MVP schema.", "Add Alembic indexes for status/priority and course_id+normalized_english_term."))
        if table_name in {"auth_token"} and "token" in colset:
            issues.append(SchemaIssue("warn", table_name, "Legacy token column exists.", "Keep token_hash for production and avoid exporting raw token values."))
        if not ({"created_at"} & colset):
            issues.append(SchemaIssue("info", table_name, "created_at not present.", "Add created_at in future Alembic migration if lifecycle tracking is needed."))

    storage_ready = "storage_object" in table_columns
    if not storage_ready:
        issues.append(SchemaIssue("warn", "storage_object", "StorageObject table is missing.", "Create StorageObject before object storage migration."))

    severity_order = {"error": 3, "warn": 2, "info": 1}
    max_severity = max((severity_order.get(issue.severity, 0) for issue in issues), default=0)
    status = "PASS" if max_severity <= 1 else "WARN"
    return {
        "status": status,
        "tables_checked": checked,
        "issues": [issue.as_dict() for issue in issues],
        "recommendations": [
            "Introduce Flask-Migrate/Alembic before staging PostgreSQL.",
            "Add composite indexes for course/term lookup and job queues.",
            "Keep SQLite compatibility for local pilot usage.",
            "Migrate file_path/saved_filename/image_path to storage_key-backed records.",
        ],
    }
