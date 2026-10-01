import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FINAL_DIR = ROOT / "final_delivery"


def test_final_delivery_core_files_exist():
    required = [
        "README.md",
        "final_delivery_checklist.md",
        "final_acceptance_report.md",
        "final_test_report.md",
        "final_demo_script.md",
        "final_known_limitations.md",
        "final_next_steps.md",
    ]
    assert FINAL_DIR.exists()
    for filename in required:
        path = FINAL_DIR / filename
        assert path.exists(), filename
        assert path.read_text(encoding="utf-8").strip(), filename


def test_check_final_delivery_script_runs():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_final_delivery.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Final Delivery Check: PASS" in result.stdout


def test_final_release_manifest_can_be_generated(tmp_path):
    output = tmp_path / "manifest.json"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "generate_final_release_manifest.py"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["project_name"] == "LexiBridge AI"
    assert manifest["known_limitations"]
    assert manifest["production_readiness"]["status"] in {"NOT_READY", "READY", "UNKNOWN"}


def test_final_delivery_docs_do_not_contain_unresolved_markers():
    disallowed = ["TODO", "FIXME", "placeholder", "your-name-here"]
    for path in FINAL_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8").lower()
        for marker in disallowed:
            assert marker.lower() not in content, f"{marker} in {path}"
