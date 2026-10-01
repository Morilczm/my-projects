#!/usr/bin/env python3
"""Run the local LexiBridge AI pre-release gate."""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


@dataclass(frozen=True)
class CheckStep:
    name: str
    command: list[str]


def sqlite_url(path: Path) -> str:
    return "sqlite:///" + path.resolve().as_posix()


def build_check_env(temp_root: Path) -> dict[str, str]:
    env = dict(os.environ)
    upload_dir = temp_root / "uploads"
    derived_dir = upload_dir / "derived"
    env.update({
        "APP_ENV": "development",
        "FLASK_ENV": "development",
        "DEBUG": "false",
        "FLASK_DEBUG": "false",
        "DATABASE_ENGINE": "sqlite",
        "DATABASE_URL": sqlite_url(temp_root / "lexibridge_dev_check.db"),
        "UPLOAD_DIR": str(upload_dir),
        "UPLOAD_FOLDER": str(upload_dir),
        "DERIVED_UPLOAD_DIR": str(derived_dir),
        "STORAGE_BACKEND": "local",
        "LOCAL_STORAGE_ROOT": str(upload_dir),
        "PYTHONPYCACHEPREFIX": str(temp_root / "pycache"),
        "AI_PROVIDER": "none",
        "AI_PROVIDER_MODE": "none",
        "AI_MODEL": "",
        "DEEPSEEK_API_KEY": "",
        "OPENAI_API_KEY": "",
        "MATHPIX_APP_ID": "",
        "MATHPIX_APP_KEY": "",
        "ALLOW_MOCK_AI": "true",
        "ALLOW_LOCAL_HEURISTIC_AI": "true",
        "AI_PROVIDER_HEALTHCHECK_ENABLED": "false",
        "OCR_PROVIDER": "none",
        "FORMULA_OCR_PROVIDER": "none",
        "AUTH_REQUIRED": "true",
        "ENABLE_MOCK_PAYMENT": "true",
        "ENABLE_MOCK_EMAIL": "true",
        "MOCK_PAYMENT_ENABLED": "true",
        "MOCK_EMAIL_ENABLED": "true",
        "LOG_REDACT_SECRETS": "true",
    })
    return env


def build_steps(python: str) -> list[CheckStep]:
    return [
        CheckStep("release safety check", [python, "scripts/check_release_safety.py"]),
        CheckStep("pytest", [python, "-m", "pytest"]),
        CheckStep("database initialization", [python, "scripts/migrate_db.py", "--apply"]),
        CheckStep("backend import/API smoke", [python, "scripts/dev_check.py", "--backend-smoke-child"]),
    ]


def run_step(step: CheckStep, env: dict[str, str]) -> int:
    print(f"\n== {step.name} ==", flush=True)
    print("$ " + " ".join(step.command), flush=True)
    result = subprocess.run(step.command, cwd=ROOT, env=env, check=False)
    if result.returncode != 0:
        print(f"FAILED: {step.name} exited with {result.returncode}", file=sys.stderr, flush=True)
    return result.returncode


def backend_smoke() -> int:
    sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("lexibridge_dev_check_app", BACKEND / "app.py")
    if spec is None or spec.loader is None:
        print("FAILED: could not load backend/app.py", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    client = module.app.test_client()
    response = client.get("/api/test")
    if response.status_code != 200:
        print(f"FAILED: /api/test returned HTTP {response.status_code}", file=sys.stderr)
        return 1
    payload = response.get_json(silent=True) or {}
    if payload.get("status") != "success":
        print(f"FAILED: /api/test returned unexpected payload: {payload}", file=sys.stderr)
        return 1
    print("Backend smoke check passed: /api/test returned success.")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-smoke-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.backend_smoke_child:
        return backend_smoke()

    print("LexiBridge AI local pre-release gate")
    print("No real API keys are required; SQLite/uploads/pycache use a temporary directory.")
    with tempfile.TemporaryDirectory(prefix="lexibridge-dev-check-") as temp_dir:
        temp_root = Path(temp_dir)
        env = build_check_env(temp_root)
        print(f"temp_dir={temp_root}")
        for step in build_steps(sys.executable):
            code = run_step(step, env)
            if code != 0:
                return code
    print("\nAll local pre-release checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
