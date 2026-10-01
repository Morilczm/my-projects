from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
BROWSER = (ROOT / "scripts" / "run_browser_e2e.py").read_text(encoding="utf-8")


def test_personal_workspace_has_optional_consent_first_pilot_panel():
    assert 'data-testid="student-pilot-panel"' in HTML
    assert 'data-testid="student-pilot-consent"' in HTML
    assert 'data-testid="student-pilot-withdraw"' in HTML
    assert "参与与否不影响正常使用" in HTML
    assert "/api/student/pilot" in HTML


def test_frontend_does_not_expose_pilot_to_instructor_or_reviewer_navigation():
    assert '["studentPilot"' not in HTML
    assert "Student pilot" not in HTML.split("const rolePages =", 1)[1].split("};", 1)[0]


def test_browser_e2e_labels_synthetic_pilot_validation_without_claiming_real_users():
    assert 'app_module.app.config["STUDENT_REAL_PILOT_ENABLED"] = True' in BROWSER
    assert 'env["LEXIBRIDGE_SKIP_ENV_FILE"] = "true"' in BROWSER
    assert 'env["DEEPSEEK_API_KEY"] = ""' in BROWSER
    assert "synthetic pilot contract" in BROWSER.lower()
    assert "real student pilot completed" not in BROWSER.lower()
