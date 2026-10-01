import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PILOT_DIR = ROOT / "pilot_package"

REQUIRED_FILES = [
    "README.md",
    "pilot_runbook.md",
    "teacher_manual.md",
    "student_manual.md",
    "admin_manual.md",
    "data_authorization_guide.md",
    "privacy_and_risk_notice.md",
    "pilot_metrics.md",
    "pre_pilot_checklist.md",
    "during_pilot_log_template.md",
    "post_pilot_report_template.md",
    "consent_notice_template.md",
    "course_material_inventory_template.md",
    "teacher_feedback_form.md",
    "student_feedback_form.md",
    "known_limitations.md",
    "demo_vs_real_pilot.md",
    "final_presentation_materials_index.md",
]


def read_package_file(name: str) -> str:
    return (PILOT_DIR / name).read_text(encoding="utf-8")


def test_pilot_package_directory_and_files_exist():
    assert PILOT_DIR.exists()
    for filename in REQUIRED_FILES:
        path = PILOT_DIR / filename
        assert path.exists(), filename
        assert path.read_text(encoding="utf-8").strip(), filename


def test_teacher_manual_contains_key_workflows():
    content = read_package_file("teacher_manual.md").lower()
    assert "upload" in content
    assert "qc" in content
    assert "feedback" in content
    assert "knowledgebaseversion" in content


def test_student_manual_contains_key_workflows():
    content = read_package_file("student_manual.md").lower()
    assert "search" in content
    assert "evidence" in content
    assert "favorite" in content
    assert "feedback" in content


def test_admin_manual_contains_key_workflows():
    content = read_package_file("admin_manual.md")
    assert "EvaluationRun" in content
    assert "KnowledgeBaseVersion" in content
    assert "Production Readiness" in content


def test_authorization_privacy_and_metrics_content():
    assert "restricted_no_derivative" in read_package_file("data_authorization_guide.md")
    privacy = read_package_file("privacy_and_risk_notice.md")
    assert "AI" in privacy
    assert "OCR" in privacy
    assert "系统输出不应被视为不可更改的标准答案" in privacy
    assert "no_evidence_forced_alignment_rate" in read_package_file("pilot_metrics.md")


def test_check_pilot_package_script_runs():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_pilot_package.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pilot Package Check: PASS" in result.stdout
