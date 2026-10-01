import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_release_safety.py"


def run_checker(*paths):
    return subprocess.run(
        [sys.executable, str(CHECKER), *[str(path) for path in paths]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_safety_accepts_safe_directory(tmp_path):
    (tmp_path / "README.md").write_text("LexiBridge AI release\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text(
        "DEEPSEEK_API_KEY=YOUR_DEEPSEEK_API_KEY_HERE\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_release_safety_rejects_env_file_database_and_uploads(tmp_path):
    (tmp_path / ".env").write_text("SECRET_KEY=not-for-release\n", encoding="utf-8")
    (tmp_path / "lexibridge.db").write_bytes(b"SQLite format 3\x00")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "student.pdf").write_bytes(b"%PDF-1.4")

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "forbidden env file" in result.stderr
    assert "lexibridge.db" in result.stderr
    assert "uploads" in result.stderr


def test_release_safety_rejects_secret_like_values_and_local_paths(tmp_path):
    (tmp_path / "config.txt").write_text(
        "DEEPSEEK_API_KEY=" + "sk-" + "abcdefghijklmnopqrstuvwxyz123456\n"
        "LOCAL_NOTE=/" + "Users/example/Desktop/LexiBridge-AI/backend/app.py\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "API key" in result.stderr
    assert "local absolute path" in result.stderr


def test_release_safety_rejects_nested_archive_in_zip(tmp_path):
    release_zip = tmp_path / "release.zip"
    with zipfile.ZipFile(release_zip, "w") as archive:
        archive.writestr("project/README.md", "safe")
        archive.writestr("project/dist/old_release.zip", "nested")

    result = run_checker(release_zip)

    assert result.returncode == 1
    assert "nested archive" in result.stderr


def test_release_safety_rejects_migration_caller_without_apply(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "unsafe.py").write_text(
        "import subprocess\n"
        "subprocess.run(['python', 'scripts/migrate_db.py'], check=True)\n",
        encoding="utf-8",
    )

    result = run_checker(tmp_path)

    assert result.returncode == 1
    assert "migration CLI call missing explicit --apply" in result.stderr
