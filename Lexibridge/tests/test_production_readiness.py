import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_check_production_readiness_reports_not_ready(tmp_path):
    env_file = tmp_path / "unsafe-prod.env"
    upload = tmp_path / "uploads"
    upload.mkdir()
    env_file.write_text(
        "\n".join([
            "APP_ENV=development",
            "DEBUG=true",
            "SECRET_KEY=change-me-in-local-dev",
            "DATABASE_URL=sqlite:///local.db",
            f"UPLOAD_DIR={upload}",
            "CORS_ALLOW_ORIGINS=*",
            "AI_PROVIDER=none",
            "ALLOW_MOCK_AI=true",
            "ENABLE_MOCK_PAYMENT=true",
            "ENABLE_MOCK_EMAIL=true",
            "OCR_PROVIDER=none",
            "FORMULA_OCR_PROVIDER=none",
            "LOG_REDACT_SECRETS=true",
        ]),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_production_readiness.py"), "--env-file", str(env_file), "--skip-tests"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert "Production readiness: NOT READY" in result.stdout
    assert "Required before production" in result.stdout


def test_required_pr9_docs_exist():
    for rel in [
        "docs/deployment-readiness.md",
        "docs/environment-config.md",
        "docs/logging-and-monitoring.md",
        "docs/backup-and-recovery.md",
        "docs/cost-control.md",
        "docs/production-risk-boundary.md",
        "docs/production-readiness-checklist.md",
        ".env.development.example",
        ".env.production.example",
    ]:
        assert (ROOT / rel).exists(), rel
