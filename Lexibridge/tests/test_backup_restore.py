import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backup_and_restore_roundtrip(tmp_path):
    db_path = tmp_path / "lexibridge.db"
    db_path.write_text("sqlite placeholder", encoding="utf-8")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "sample.txt").write_text("upload", encoding="utf-8")
    backup = tmp_path / "backup.zip"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/backup_local_data.py"),
            "--output",
            str(backup),
            "--database",
            str(db_path),
            "--uploads",
            str(uploads),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert backup.exists()
    with zipfile.ZipFile(backup) as archive:
        names = set(archive.namelist())
        assert "backup_manifest.json" in names
        assert ".env" not in names
        assert any(name.startswith("uploads/") for name in names)
        manifest = json.loads(archive.read("backup_manifest.json").decode("utf-8"))
        assert manifest["included_env"] is False

    target = tmp_path / "restore"
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/restore_local_data.py"), "--backup", str(backup), "--target", str(target)],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    assert (target / "backup_manifest.json").exists()
    assert list((target / "database").glob("*"))
    assert (target / "uploads" / "sample.txt").exists()

    failed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/restore_local_data.py"), "--backup", str(backup), "--target", str(target)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert failed.returncode != 0

    subprocess.run(
        [sys.executable, str(ROOT / "scripts/restore_local_data.py"), "--backup", str(backup), "--target", str(target), "--force"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
