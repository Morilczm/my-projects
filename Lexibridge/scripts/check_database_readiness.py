#!/usr/bin/env python3
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from services.database_health import inspect_sqlite_database


spec = importlib.util.spec_from_file_location("lexibridge_db_ready_app", BACKEND / "app.py")
appmod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(appmod)


def main():
    with appmod.app.app_context():
        database_url = appmod.app.config["SQLALCHEMY_DATABASE_URI"]
        result = inspect_sqlite_database(database_url)
    status = "FAIL" if result["errors"] else "WARN" if result["warnings"] else "PASS"
    result["status"] = status
    print(f"Database Readiness: {status}")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
