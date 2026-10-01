import csv
import os
import subprocess
import sys
from pathlib import Path

from test_pilot_feedback import auth_header, create_visible_card


ROOT = Path(__file__).resolve().parents[1]


def test_pilot_report_api_is_redacted(client, app_module, student_token, admin_token):
    with app_module.app.app_context():
        card = create_visible_card(app_module)
        card_id = card.id
        course_id = card.course_id
    feedback_response = client.post(
        f"/api/terminology/cards/{card_id}/feedback",
        json={"feedback_type": "evidence_error", "severity": "high", "reported_issue": "Wrong evidence"},
        headers=auth_header(student_token),
    )
    assert feedback_response.status_code == 200

    response = client.get(f"/api/pilot/report?course_id={course_id}", headers=auth_header(admin_token))

    assert response.status_code == 200
    report = response.get_json()["data"]["report_markdown"]
    assert "Feedback Summary" in report
    assert "Terminology Quality" in report
    assert "student.test@lexibridge.local" not in report
    assert "Bearer " not in report
    assert "sk-" not in report


def test_generate_pilot_report_script_runs(tmp_path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'pilot-report.db'}"
    env["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    env["AI_PROVIDER"] = "none"
    env["ALLOW_MOCK_AI"] = "True"
    subprocess.run([sys.executable, str(ROOT / "scripts/migrate_db.py"), "--apply"], cwd=ROOT, env=env, check=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/seed_demo_data.py")], cwd=ROOT, env=env, check=True)
    output = tmp_path / "pilot_report.md"

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/generate_pilot_report.py"), "--output", str(output)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert output.exists()
    text = output.read_text(encoding="utf-8")
    assert "LexiBridge AI Pilot Report" in text
    assert "student@lexibridge.local" not in text
    assert "token" not in text.lower()
    assert "Pilot report generated" in result.stdout


def test_export_feedback_summary_script_redacts_student_email(tmp_path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'feedback-summary.db'}"
    env["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    subprocess.run([sys.executable, str(ROOT / "scripts/migrate_db.py"), "--apply"], cwd=ROOT, env=env, check=True)
    output = tmp_path / "feedback_summary.csv"

    subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_feedback_summary.py"), "--output", str(output)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    assert output.exists()
    with output.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [] or "student_email" not in rows[0]
