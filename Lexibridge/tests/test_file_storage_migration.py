from pathlib import Path
import os
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_document_upload_creates_storage_object(client, app_module, teacher_token, test_course):
    from io import BytesIO
    response = client.post(
        "/api/documents/upload?sync=true",
        data={
            "file": (BytesIO(b"Fourier Transform converts a time-domain signal."), "notes.txt"),
            "scope_type": "course",
            "course_id": str(test_course.id),
            "language": "en",
        },
        content_type="multipart/form-data",
        headers={"Authorization": f"Bearer {teacher_token}"},
    )
    assert response.status_code == 200
    with app_module.app.app_context():
        document = app_module.Document.query.order_by(app_module.Document.id.desc()).first()
        assert document.storage_key
        assert document.storage_object_id
        assert app_module.StorageObject.query.filter_by(id=document.storage_object_id).first() is not None


def test_local_file_migration_dry_run_and_apply(app_module, tmp_path):
    db_path = tmp_path / "file-migration.db"
    uploads = tmp_path / "uploads"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["UPLOAD_FOLDER"] = str(uploads)
    env["LOCAL_STORAGE_ROOT"] = str(uploads)
    subprocess.run([sys.executable, str(ROOT / "scripts/migrate_db.py"), "--apply"], cwd=ROOT, env=env, check=True)
    legacy_file = uploads / "legacy.txt"
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.write_text("legacy content", encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "insert into document (owner_user_id, scope_type, filename, saved_filename, file_type, upload_time) values (1, 'personal', 'legacy.txt', 'legacy.txt', 'txt', 'now')"
        )
        conn.commit()
    dry = subprocess.run(
        [sys.executable, str(ROOT / "scripts/migrate_local_files_to_storage.py"), "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "dry-run" in dry.stdout
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select storage_key from document where saved_filename='legacy.txt'").fetchone()[0] in (None, "")
    apply = subprocess.run(
        [sys.executable, str(ROOT / "scripts/migrate_local_files_to_storage.py"), "--apply"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "migrated" in apply.stdout
    with sqlite3.connect(db_path) as conn:
        storage_key = conn.execute("select storage_key from document where saved_filename='legacy.txt'").fetchone()[0]
        assert storage_key
        assert conn.execute("select count(*) from storage_object").fetchone()[0] == 1
    assert legacy_file.exists()
