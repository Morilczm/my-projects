import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_check_database_readiness_script_runs(tmp_path):
    db_path = tmp_path / "ready.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    subprocess.run([sys.executable, str(ROOT / "scripts/migrate_db.py"), "--apply"], cwd=ROOT, env=env, check=True)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_database_readiness.py")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Database Readiness:" in result.stdout
    assert '"connectable": true' in result.stdout


def test_database_readiness_detects_orphan_document_chunk(tmp_path):
    db_path = tmp_path / "orphan.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table document (id integer primary key, scope_type text, owner_user_id integer)")
        conn.execute("create table document_chunk (id integer primary key, document_id integer)")
        conn.execute("create table formula_block (id integer primary key, document_id integer)")
        conn.execute("create table terminology_card (id integer primary key, course_id integer, scope_type text, owner_user_id integer, normalized_english_term text, final_chinese_term text)")
        conn.execute("create table course (id integer primary key)")
        conn.execute("insert into document_chunk (id, document_id) values (1, 999)")
        conn.commit()
    from services.database_health import inspect_sqlite_database
    result = inspect_sqlite_database(f"sqlite:///{db_path}")
    assert result["orphan_records"]["document_chunks"] == 1
    assert "Orphan records detected." in result["warnings"]
