import os
import sqlite3
from pathlib import Path


CORE_TABLES = [
    "user",
    "course",
    "document",
    "document_chunk",
    "formula_block",
    "knowledge_chunk",
    "terminology_card",
    "feedback",
    "background_job",
    "evaluation_run",
    "storage_object",
]


def sqlite_path_from_url(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "", 1)
    return ""


def inspect_sqlite_database(database_url: str) -> dict:
    db_path = sqlite_path_from_url(database_url)
    result = {
        "database_engine": "sqlite" if db_path else "unknown",
        "database_path": db_path,
        "connectable": False,
        "tables": {},
        "warnings": [],
        "errors": [],
        "orphan_records": {},
        "duplicate_cards": 0,
        "missing_personal_owner_records": 0,
    }
    if not db_path:
        result["warnings"].append("Only SQLite readiness introspection is implemented in Local MVP.")
        return result
    if not os.path.exists(db_path):
        result["errors"].append(f"SQLite database not found: {db_path}")
        return result
    result["size_bytes"] = Path(db_path).stat().st_size
    with sqlite3.connect(db_path) as conn:
        result["connectable"] = True
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        for table in CORE_TABLES:
            if table in tables:
                result["tables"][table] = conn.execute(f"select count(*) from {table}").fetchone()[0]
            else:
                result["warnings"].append(f"Missing core table: {table}")
        if {"document_chunk", "document"} <= tables:
            result["orphan_records"]["document_chunks"] = conn.execute(
                "select count(*) from document_chunk dc left join document d on dc.document_id=d.id where d.id is null"
            ).fetchone()[0]
        if {"formula_block", "document"} <= tables:
            result["orphan_records"]["formula_blocks"] = conn.execute(
                "select count(*) from formula_block fb left join document d on fb.document_id=d.id where d.id is null"
            ).fetchone()[0]
        if {"terminology_card", "course"} <= tables:
            result["orphan_records"]["terminology_cards"] = conn.execute(
                "select count(*) from terminology_card tc left join course c on tc.course_id=c.id where tc.course_id is not null and c.id is null"
            ).fetchone()[0]
            result["duplicate_cards"] = conn.execute(
                "select count(*) from (select course_id, normalized_english_term, final_chinese_term, count(*) c from terminology_card group by course_id, normalized_english_term, final_chinese_term having c > 1)"
            ).fetchone()[0]
            result["missing_personal_owner_records"] = conn.execute(
                "select count(*) from terminology_card where scope_type='personal' and (owner_user_id is null or owner_user_id=0)"
            ).fetchone()[0]
        if "document" in tables:
            result["missing_personal_owner_records"] += conn.execute(
                "select count(*) from document where scope_type='personal' and (owner_user_id is null or owner_user_id=0)"
            ).fetchone()[0]
    if any(result["orphan_records"].values()):
        result["warnings"].append("Orphan records detected.")
    if result["duplicate_cards"]:
        result["warnings"].append("Duplicate terminology cards detected.")
    if result["missing_personal_owner_records"]:
        result["warnings"].append("Personal scope records without owner_user_id detected.")
    return result
