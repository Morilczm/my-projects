#!/usr/bin/env python3
"""Validate LexiBridge AI environment files for development or production."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
VALID_AI = {"none", "deepseek", "openai", "gemini", "claude", "mock", "local_heuristic"}
VALID_AI_MODES = {"none", "mock", "local_heuristic", "live"}
VALID_OCR = {"none", "auto", "tesseract", "paddle", "mock"}
VALID_FORMULA = {"none", "mock", "mathpix", "local_latex", "local"}
PLACEHOLDERS = {
    "your-api-key",
    "your-api-key-here",
    "your_deepseek_api_key_here",
    "your-deepseek-api-key-here",
    "your_openai_api_key_here",
    "your_mathpix_app_id_here",
    "your_mathpix_app_key_here",
    "sk-xxx",
    "placeholder",
    "change-me",
    "change-me-in-local-dev",
    "replace-with-strong-secret",
    "lexibridge-local-demo-secret",
    "lexibridge-local-dev-secret",
}


def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def load_env_file(path):
    data = {}
    path = Path(path)
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def merged_env(path=None):
    data = dict(os.environ)
    if path:
        data.update(load_env_file(path))
    elif (ROOT / ".env").exists():
        data.update(load_env_file(ROOT / ".env"))
    return data


def value(env, *names, default=""):
    for name in names:
        if env.get(name) not in (None, ""):
            return str(env.get(name)).strip()
    return default


def is_placeholder(text):
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return lowered in PLACEHOLDERS or any(token in lowered for token in PLACEHOLDERS)


def validate_env(target_env, env):
    errors = []
    warnings = []

    app_env = value(env, "APP_ENV", "FLASK_ENV", default="development").lower()
    debug = parse_bool(value(env, "DEBUG", "FLASK_DEBUG", default="false"))
    secret_key = value(env, "SECRET_KEY", default="")
    database_url = value(env, "DATABASE_URL", default="")
    database_engine = value(
        env,
        "DATABASE_ENGINE",
        default=("sqlite" if database_url.startswith("sqlite") else "postgresql" if database_url.startswith("postgresql") else "")
    ).lower()
    upload_dir = value(env, "UPLOAD_DIR", "UPLOAD_FOLDER", default=str(ROOT / "backend" / "uploads"))
    cors = value(env, "CORS_ALLOW_ORIGINS", "FRONTEND_ORIGIN", default="")
    ai_provider = value(env, "AI_PROVIDER", default="none").lower()
    ai_provider_mode = value(env, "AI_PROVIDER_MODE", default="none").lower()
    ocr_provider = value(env, "OCR_PROVIDER", default="none").lower()
    formula_provider = value(env, "FORMULA_OCR_PROVIDER", default="none").lower()
    deepseek_key = value(env, "DEEPSEEK_API_KEY", default="")
    allow_mock_ai = parse_bool(value(env, "ALLOW_MOCK_AI", default="false"))
    allow_local_ai = parse_bool(value(env, "ALLOW_LOCAL_HEURISTIC_AI", default="false"))
    mock_payment = parse_bool(value(env, "ENABLE_MOCK_PAYMENT", "MOCK_PAYMENT_ENABLED", default="false"))
    mock_email = parse_bool(value(env, "ENABLE_MOCK_EMAIL", "MOCK_EMAIL_ENABLED", default="false"))
    redact = parse_bool(value(env, "LOG_REDACT_SECRETS", default="true"), default=True)

    if ai_provider not in VALID_AI:
        errors.append(f"AI_PROVIDER is invalid: {ai_provider}")
    if ai_provider_mode not in VALID_AI_MODES:
        errors.append(f"AI_PROVIDER_MODE is invalid: {ai_provider_mode}")
    if ocr_provider not in VALID_OCR:
        errors.append(f"OCR_PROVIDER is invalid: {ocr_provider}")
    if formula_provider not in VALID_FORMULA:
        errors.append(f"FORMULA_OCR_PROVIDER is invalid: {formula_provider}")
    if database_url:
        parsed = urlparse(database_url)
        if not parsed.scheme:
            errors.append("DATABASE_URL is not parseable.")
    else:
        warnings.append("DATABASE_URL is empty; backend default SQLite path will be used.")
    if database_engine not in {"sqlite", "postgresql", ""}:
        errors.append("DATABASE_ENGINE must be sqlite or postgresql.")
    if database_engine == "postgresql" and not database_url.startswith("postgresql"):
        errors.append("DATABASE_ENGINE=postgresql requires a postgresql:// DATABASE_URL.")
    if database_engine == "sqlite" and database_url and not database_url.startswith("sqlite"):
        errors.append("DATABASE_ENGINE=sqlite requires a sqlite:/// DATABASE_URL.")

    try:
        Path(upload_dir).expanduser().mkdir(parents=True, exist_ok=True)
        test_file = Path(upload_dir).expanduser() / ".write-test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
    except Exception as exc:
        errors.append(f"UPLOAD_DIR/UPLOAD_FOLDER is not writable: {upload_dir} ({exc})")

    if deepseek_key and is_placeholder(deepseek_key):
        warnings.append("DEEPSEEK_API_KEY is a placeholder and will not enable live AI.")

    if target_env == "production":
        if app_env != "production":
            errors.append("APP_ENV must be production.")
        if debug:
            errors.append("DEBUG must be false in production.")
        if not secret_key or is_placeholder(secret_key) or len(secret_key) < 32:
            errors.append("SECRET_KEY must be a strong non-placeholder value of at least 32 characters.")
        if allow_mock_ai:
            errors.append("ALLOW_MOCK_AI must be false in production.")
        if allow_local_ai:
            errors.append("ALLOW_LOCAL_HEURISTIC_AI must be false in production.")
        if ai_provider_mode != "live":
            errors.append("AI_PROVIDER_MODE must be live in production.")
        if mock_payment:
            errors.append("ENABLE_MOCK_PAYMENT/MOCK_PAYMENT_ENABLED must be false in production.")
        if mock_email:
            errors.append("ENABLE_MOCK_EMAIL/MOCK_EMAIL_ENABLED must be false in production.")
        if database_url.startswith("sqlite:") or database_engine == "sqlite" or not database_url:
            errors.append("DATABASE_URL must not use SQLite in production.")
        if cors == "*" or "*" in [part.strip() for part in cors.split(",")]:
            errors.append("CORS allowlist must not contain * in production.")
        if ai_provider == "deepseek" and (not deepseek_key or is_placeholder(deepseek_key)):
            errors.append("DEEPSEEK_API_KEY must be configured with a non-placeholder value for production DeepSeek.")
        if not redact:
            errors.append("LOG_REDACT_SECRETS must be true in production.")
    else:
        if is_placeholder(secret_key) or len(secret_key) < 16:
            warnings.append("SECRET_KEY is weak or placeholder; acceptable only for local development.")

    return errors, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate LexiBridge AI environment configuration.")
    parser.add_argument("--env", choices=["development", "staging", "production"], default="development")
    parser.add_argument("--file", help="Optional env file to validate.")
    args = parser.parse_args(argv)
    env = merged_env(args.file)
    errors, warnings = validate_env(args.env, env)
    label = "Production" if args.env == "production" else args.env.capitalize()
    status = "FAIL" if errors else "PASS"
    print(f"{label} environment check: {status}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"- {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
