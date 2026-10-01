import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORE_COUNT_TABLES = [
    "concept_alignment_card",
    "concept_card_review_record",
    "student_concept_card_state",
    "audit_record",
]


def run_cmd(args, env, *, expect_success=True):
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if expect_success and result.returncode != 0:
        raise AssertionError(f"command failed: {args}\nstdout={result.stdout}\nstderr={result.stderr}")
    if not expect_success and result.returncode == 0:
        raise AssertionError(f"command unexpectedly succeeded: {args}\nstdout={result.stdout}")
    return result


def build_env(tmp_path):
    database = tmp_path / "pilot.db"
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database}"
    env["UPLOAD_FOLDER"] = str(uploads)
    env["AUTH_REQUIRED"] = "True"
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    env["OCR_PROVIDER"] = "none"
    env["FORMULA_OCR_PROVIDER"] = "none"
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("OPENAI_API_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    return env, database, uploads


def table_counts(database):
    with sqlite3.connect(database) as conn:
        return {
            table: int(conn.execute(f'select count(*) from "{table}"').fetchone()[0])
            for table in CORE_COUNT_TABLES
        }


def upload_hashes(root):
    import hashlib

    hashes = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        hashes[path.relative_to(root).as_posix()] = digest
    return hashes


def prepare_demo_database(tmp_path):
    env, database, uploads = build_env(tmp_path)
    (uploads / "demo").mkdir()
    (uploads / "demo" / "course-note.txt").write_text("local upload fixture", encoding="utf-8")
    run_cmd(["scripts/migrate_db.py", "--apply"], env)
    run_cmd(["scripts/seed_review_demo.py", "--reset-demo"], env)
    return env, database, uploads


def parse_last_json(stdout):
    lines = [line for line in stdout.splitlines() if line.strip()]
    return json.loads(lines[-1])


def test_pilot_backup_restore_round_trip_and_tamper_rejection(tmp_path):
    env, database, uploads = prepare_demo_database(tmp_path)
    before_counts = table_counts(database)
    before_upload_hashes = upload_hashes(uploads)

    backup_dir = tmp_path / "backup"
    backup_result = run_cmd(
        [
            "scripts/pilot_backup.py",
            "--database",
            str(database),
            "--uploads",
            str(uploads),
            "--output",
            str(backup_dir),
        ],
        env,
    )
    backup_payload = parse_last_json(backup_result.stdout)
    manifest_path = Path(backup_payload["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_text = json.dumps(manifest, ensure_ascii=False).lower()
    assert "api_key" not in manifest_text
    assert "authorization" not in manifest_text
    assert "cookie" not in manifest_text

    verify_result = run_cmd(["scripts/verify_pilot_backup.py", "--backup", str(backup_dir)], env)
    verify_payload = parse_last_json(verify_result.stdout)
    assert verify_payload["sqlite_integrity"] == "ok"

    restored_db = tmp_path / "restore" / "restored.db"
    restored_uploads = tmp_path / "restore" / "uploads"
    run_cmd(
        [
            "scripts/pilot_restore.py",
            "--backup",
            str(backup_dir),
            "--database-target",
            str(restored_db),
            "--uploads-target",
            str(restored_uploads),
        ],
        env,
    )
    assert table_counts(restored_db) == before_counts
    assert upload_hashes(restored_uploads) == before_upload_hashes
    with sqlite3.connect(restored_db) as conn:
        assert conn.execute("pragma integrity_check").fetchone()[0] == "ok"

    run_cmd(
        [
            "scripts/pilot_restore.py",
            "--backup",
            str(backup_dir),
            "--database-target",
            str(restored_db),
            "--uploads-target",
            str(restored_uploads),
        ],
        env,
        expect_success=False,
    )
    run_cmd(
        [
            "scripts/pilot_restore.py",
            "--backup",
            str(backup_dir),
            "--database-target",
            str(restored_db),
            "--uploads-target",
            str(restored_uploads),
            "--force",
        ],
        env,
    )

    tampered_backup = tmp_path / "tampered-backup"
    run_cmd(
        [
            "scripts/pilot_backup.py",
            "--database",
            str(database),
            "--uploads",
            str(uploads),
            "--output",
            str(tampered_backup),
        ],
        env,
    )
    (tampered_backup / "database.sqlite").write_bytes((tampered_backup / "database.sqlite").read_bytes() + b"tamper")
    run_cmd(["scripts/verify_pilot_backup.py", "--backup", str(tampered_backup)], env, expect_success=False)

    after_counts = table_counts(database)
    assert after_counts == before_counts


def test_repeated_backup_does_not_modify_source_data(tmp_path):
    env, database, uploads = prepare_demo_database(tmp_path)
    before_counts = table_counts(database)
    backup_parent = tmp_path / "repeated"
    run_cmd(["scripts/pilot_backup.py", "--database", str(database), "--uploads", str(uploads), "--output", str(backup_parent)], env)
    run_cmd(["scripts/pilot_backup.py", "--database", str(database), "--uploads", str(uploads), "--output", str(backup_parent)], env)
    assert table_counts(database) == before_counts
    assert len(list(backup_parent.rglob("backup_manifest.json"))) == 2
