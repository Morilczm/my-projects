#!/usr/bin/env python3
import importlib.util
import sys
from pathlib import Path
from sqlalchemy import inspect


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services.schema_audit import audit_schema


spec = importlib.util.spec_from_file_location("lexibridge_schema_audit_app", BACKEND / "app.py")
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)


def main():
    with appmod.app.app_context():
        appmod.db.create_all()
        appmod.ensure_schema_columns()
        inspector = inspect(appmod.db.engine)
        table_columns = {
            table: [column["name"] for column in inspector.get_columns(table)]
            for table in inspector.get_table_names()
        }
        result = audit_schema({}, table_columns)
    report = ROOT / "docs" / "schema-audit-report.md"
    lines = [
        "# Schema Audit Report",
        "",
        f"Schema Audit Result: {result['status']}",
        f"Tables checked: {result['tables_checked']}",
        "",
        "## Issues",
    ]
    for issue in result["issues"]:
        lines.append(f"- [{issue['severity']}] `{issue['table']}`: {issue['message']} Recommendation: {issue['recommendation']}")
    lines.extend(["", "## Recommendations"])
    for item in result["recommendations"]:
        lines.append(f"- {item}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Schema Audit Result: {result['status']}")
    print(f"Tables checked: {result['tables_checked']}")
    print(f"Issues: {len(result['issues'])}")
    print(f"Report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
