import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sqlite_export_writes_jsonl_and_redacts_password_hash(tmp_path):
    db_path = tmp_path / "export.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    subprocess.run([sys.executable, str(ROOT / "scripts/migrate_db.py"), "--apply"], cwd=ROOT, env=env, check=True)
    output = tmp_path / "export"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_sqlite_data.py"), "--db", str(db_path), "--output", str(output), "--exclude-personal"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "SQLite export written" in result.stdout
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["database_engine"] == "sqlite"
    users = (output / "users.jsonl").read_text(encoding="utf-8")
    assert "password_hash" in users
    assert "[REDACTED]" in users
