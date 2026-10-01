#!/usr/bin/env python3
"""Generate a safe final release manifest."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _rel_files(directory: str, pattern: str = "*") -> list[str]:
    base = ROOT / directory
    if not base.exists():
        return []
    return sorted(str(path.relative_to(ROOT)) for path in base.rglob(pattern) if path.is_file())


def _git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return "unknown"


def _production_readiness() -> dict:
    script = ROOT / "scripts" / "check_production_readiness.py"
    if not script.exists():
        return {"status": "UNKNOWN", "blockers": ["check_production_readiness.py missing"]}
    result = subprocess.run([_python(), str(script)], cwd=ROOT, capture_output=True, text=True, check=False)
    output = result.stdout + result.stderr
    status = "NOT_READY" if "NOT READY" in output else ("READY" if "READY" in output else "UNKNOWN")
    blockers = [
        line[2:].strip().replace("non-placeholder", "non-default")
        for line in output.splitlines()
        if line.startswith("- ")
    ]
    return {"status": status, "blockers": blockers[:50]}


def _python() -> str:
    candidate = ROOT / "backend" / ".venv-macos" / "bin" / "python"
    return str(candidate) if candidate.exists() else "python3"


def _release_check(zip_path: Path) -> dict:
    if not zip_path.exists():
        return {"passed": False, "findings": [f"release zip not found: {zip_path.relative_to(ROOT)}"]}
    result = subprocess.run(
        [_python(), str(ROOT / "scripts" / "check_release_package.py"), str(zip_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    findings = []
    if result.returncode != 0:
        findings = [line.strip() for line in (result.stdout + result.stderr).splitlines() if line.strip()]
    return {"passed": result.returncode == 0, "findings": findings}


def build_manifest(release_zip: str | None = None) -> dict:
    zip_path = Path(release_zip) if release_zip else ROOT / "dist" / f"LexiBridge-AI-Local-MVP-v0.8-{datetime.now().strftime('%Y%m%d')}.zip"
    if not zip_path.is_absolute():
        zip_path = ROOT / zip_path
    return {
        "project_name": "LexiBridge AI",
        "version": "pilot-v1.0-candidate",
        "release_name": "LexiBridge AI Pilot v1.0 Candidate",
        "release_classification": "Controlled Academic Pilot Release",
        "candidate_scope": "source branch and commit",
        "readiness_verdict": "READY_WITH_CONDITIONS",
        "source_baseline_commit": "8ba533ab43fc36e952268c5ea385397778b6fbd5",
        "release_branch": "release/pilot-v1-candidate",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "python_version": platform.python_version(),
        "core_modules": [
            "OCR",
            "Evidence Retrieval",
            "Alignment State Machine",
            "Evaluation Harness",
            "Async Jobs",
            "AI Provider Governance",
            "Formal Document Alignment Workflow",
            "Teacher Formal Workflow",
            "Audit Trail",
            "Review Preparation",
            "KnowledgeBaseVersion",
            "RetrievalBackend",
            "PilotFeedback",
        ],
        "scripts": _rel_files("scripts", "*.py"),
        "docs": _rel_files("docs", "*.md"),
        "pilot_package_files": _rel_files("pilot_package", "*.md"),
        "final_delivery_files": _rel_files("final_delivery"),
        "tests": _rel_files("tests", "test_*.py"),
        "known_limitations": [
            "Controlled Academic Pilot Release only; not production-ready",
            "PostgreSQL and Alembic migration proof are not implemented",
            "LocalStorageBackend is not production object storage",
            "local worker is not a supervised production queue or worker runtime",
            "HTTPS deployment is not implemented",
            "live provider operation is disabled and not production-validated",
            "production monitoring and alerting are not implemented",
            "mock payment and mock email are not production capabilities",
            "real course materials require teacher authorization and review",
        ],
        "release_artifact_role": "historical package safety evidence; the source branch is the candidate",
        "release_zip": str(zip_path.relative_to(ROOT)) if zip_path.exists() else str(zip_path),
        "sensitive_file_check": _release_check(zip_path),
        "production_readiness": _production_readiness(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--release-zip")
    args = parser.parse_args()
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_manifest(args.release_zip), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Final release manifest written: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
