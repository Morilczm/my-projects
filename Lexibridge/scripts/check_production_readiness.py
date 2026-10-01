#!/usr/bin/env python3
"""Report production readiness blockers without pretending the Local MVP is production-ready."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_DOCS = [
    "docs/openapi.yaml",
    "docs/demo-test-report.md",
    "docs/production-risk-boundary.md",
    "docs/backup-and-recovery.md",
    "docs/cost-control.md",
    "docs/deployment-readiness.md",
    "docs/environment-config.md",
    "docs/logging-and-monitoring.md",
    "docs/database-migration-plan.md",
    "docs/object-storage-design.md",
    "docs/storage-migration-plan.md",
    "docs/production-data-readiness.md",
    "docs/ai-provider-governance.md",
    "docs/prompt-versioning.md",
    "docs/model-registry.md",
    "docs/ai-cost-control.md",
    "docs/ai-failure-and-fallback.md",
]


def run_check_env(env_file=None):
    cmd = [sys.executable, str(ROOT / "scripts/check_env.py"), "--env", "production"]
    if env_file:
        cmd += ["--file", str(env_file)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return result


def run_check_storage(env_file=None):
    cmd = [sys.executable, str(ROOT / "scripts/check_storage_config.py"), "--env", "production"]
    if env_file:
        cmd += ["--file", str(env_file)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return result


def run_check_ai(env_file=None):
    cmd = [sys.executable, str(ROOT / "scripts/check_ai_config.py"), "--env", "production"]
    if env_file:
        cmd += ["--file", str(env_file)]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    return result


def readiness_report(skip_tests=False, env_file=None):
    blockers = []
    warnings = []
    env_result = run_check_env(env_file)
    storage_result = run_check_storage(env_file)
    ai_result = run_check_ai(env_file)
    if env_result.returncode != 0:
        blockers.append("Production environment validation failed.")
        blockers.extend(line for line in env_result.stdout.splitlines() if line.startswith("- "))
    if storage_result.returncode != 0:
        blockers.append("Production storage validation failed.")
        blockers.extend(line for line in storage_result.stdout.splitlines() if line.startswith("- error:"))
    if ai_result.returncode != 0:
        blockers.append("Production AI provider validation failed.")
        blockers.extend(line for line in ai_result.stdout.splitlines() if line.startswith("- "))
    for rel in REQUIRED_DOCS:
        if not (ROOT / rel).exists():
            blockers.append(f"Required document missing: {rel}")
    if not (ROOT / ".env.production.example").exists():
        blockers.append(".env.production.example is missing.")
    if "Deployment Readiness" not in (ROOT / "README.md").read_text(encoding="utf-8", errors="ignore"):
        blockers.append("README is missing Deployment Readiness guidance.")
    if skip_tests:
        warnings.append("pytest was skipped for this readiness report.")
    status = "READY" if not blockers else "NOT READY"
    combined_output = env_result.stdout
    if storage_result.stdout:
        combined_output += "\n" + storage_result.stdout
    if ai_result.stdout:
        combined_output += "\n" + ai_result.stdout
    return status, blockers, warnings, combined_output


def main():
    parser = argparse.ArgumentParser(description="Check LexiBridge AI production readiness.")
    parser.add_argument("--env-file")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Return non-zero when status is NOT READY.")
    args = parser.parse_args()
    status, blockers, warnings, env_output = readiness_report(args.skip_tests, args.env_file)
    print(f"Production readiness: {status}")
    if env_output.strip():
        print("\nEnvironment check:")
        print(env_output.strip())
    if blockers:
        print("\nRequired before production:")
        for blocker in blockers:
            print(f"- {blocker.lstrip('- ').strip()}")
    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"- {warning}")
    return 1 if args.strict and status != "READY" else 0


if __name__ == "__main__":
    raise SystemExit(main())
