import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_build_final_release_check_only_runs():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_final_release.py"), "--check-only"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Final release result:" in result.stdout


def test_release_manifest_json_is_parseable(tmp_path):
    output = tmp_path / "manifest.json"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_final_release_manifest.py"), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["project_name"] == "LexiBridge AI"
    assert manifest["known_limitations"]
    assert "production_readiness" in manifest


def test_release_package_checker_rejects_sensitive_files(tmp_path):
    bad_zip = tmp_path / "bad_release.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("project/.env", "SECRET_KEY=not-for-release")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_package.py"), str(bad_zip)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0


def test_release_package_checker_accepts_safe_zip(tmp_path):
    safe_zip = tmp_path / "safe_release.zip"
    with zipfile.ZipFile(safe_zip, "w") as zf:
        zf.writestr("project/README.md", "safe release")
        zf.writestr("project/final_delivery/README.md", "safe final delivery")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release_package.py"), str(safe_zip)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
