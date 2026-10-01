import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_env(path, **values):
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    return path


def run_check(env_name, path):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_env.py"), "--env", env_name, "--file", str(path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )


def base_env(tmp_path):
    upload = tmp_path / "uploads"
    upload.mkdir()
    return {
        "APP_ENV": "development",
        "DEBUG": "true",
        "SECRET_KEY": "change-me-in-local-dev",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'dev.db'}",
        "UPLOAD_DIR": str(upload),
        "CORS_ALLOW_ORIGINS": "http://localhost:5000",
        "AI_PROVIDER": "none",
        "OCR_PROVIDER": "none",
        "FORMULA_OCR_PROVIDER": "none",
        "ALLOW_MOCK_AI": "true",
        "ENABLE_MOCK_PAYMENT": "true",
        "ENABLE_MOCK_EMAIL": "true",
        "LOG_REDACT_SECRETS": "true",
    }


def test_development_config_passes_with_warnings(tmp_path):
    path = write_env(tmp_path / "dev.env", **base_env(tmp_path))
    result = run_check("development", path)
    assert result.returncode == 0
    assert "Development environment check: PASS" in result.stdout


def test_production_rejects_debug_mock_sqlite_and_wildcard(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "APP_ENV": "production",
        "DEBUG": "true",
        "SECRET_KEY": "replace-with-strong-secret",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'prod.db'}",
        "CORS_ALLOW_ORIGINS": "*",
        "AI_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "your-api-key-here",
        "ALLOW_MOCK_AI": "true",
    })
    path = write_env(tmp_path / "prod.env", **env)
    result = run_check("production", path)
    assert result.returncode == 1
    assert "DEBUG must be false" in result.stdout
    assert "ALLOW_MOCK_AI must be false" in result.stdout
    assert "DATABASE_URL must not use SQLite" in result.stdout
    assert "CORS allowlist must not contain *" in result.stdout


def test_production_rejects_default_secret_and_placeholder_key(tmp_path):
    env = base_env(tmp_path)
    env.update({
        "APP_ENV": "production",
        "DEBUG": "false",
        "SECRET_KEY": "change-me-in-local-dev",
        "DATABASE_URL": "postgresql://user:password@localhost:5432/lexibridge",
        "AI_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "sk-xxx",
        "ALLOW_MOCK_AI": "false",
        "ENABLE_MOCK_PAYMENT": "false",
        "ENABLE_MOCK_EMAIL": "false",
    })
    path = write_env(tmp_path / "prod-placeholder.env", **env)
    result = run_check("production", path)
    assert result.returncode == 1
    assert "SECRET_KEY must be a strong" in result.stdout
    assert "DEEPSEEK_API_KEY must be configured" in result.stdout
