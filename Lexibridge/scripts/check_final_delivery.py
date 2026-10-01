#!/usr/bin/env python3
"""Validate final delivery materials for the course handoff."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FINAL_FILES = [
    "README.md",
    "final_delivery_checklist.md",
    "final_acceptance_report.md",
    "final_test_report.md",
    "final_demo_script.md",
    "final_screenshot_checklist.md",
    "final_course_report_materials.md",
    "final_presentation_outline.md",
    "final_poster_copy.md",
    "final_project_summary.md",
    "final_known_limitations.md",
    "final_next_steps.md",
    "final_release_manifest.json",
    "final_artifact_index.md",
]

DOC_FILES = [
    "docs/final-delivery-guide.md",
    "docs/final-acceptance-report.md",
    "docs/final-demo-script.md",
    "docs/final-screenshot-checklist.md",
    "docs/final-course-report-materials.md",
    "docs/final-presentation-outline.md",
    "docs/final-poster-copy.md",
    "docs/final-project-summary.md",
    "docs/final-known-limitations.md",
    "docs/final-next-steps.md",
]

DISALLOWED = ("TODO", "FIXME", "placeholder", "your-name-here")
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b", re.IGNORECASE),
    re.compile(r"\b(?:access_)?token\s*[:=]\s*[A-Za-z0-9._-]{20,}\b", re.IGNORECASE),
    re.compile(r"\b[A-Za-z0-9_]*API[_-]?KEY\s*[:=]\s*['\"]?[A-Za-z0-9._-]{12,}", re.IGNORECASE),
]
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ALLOWED_EMAIL_SUFFIXES = ("@lexibridge.local",)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _has_all(path: Path, terms: list[str]) -> bool:
    text = _read(path).lower()
    return all(term.lower() in text for term in terms)


def validate() -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    final_dir = ROOT / "final_delivery"

    if not final_dir.exists():
        errors.append("final_delivery directory is missing.")
        return errors, warnings, checked
    if not (ROOT / "pilot_package").exists():
        errors.append("pilot_package directory is missing.")
    if not (ROOT / "README.md").exists():
        errors.append("README.md is missing.")
    if not (ROOT / "docs" / "openapi.yaml").exists():
        errors.append("docs/openapi.yaml is missing.")
    if not (ROOT / "docs" / "demo-test-report.md").exists():
        errors.append("docs/demo-test-report.md is missing.")

    paths = [final_dir / name for name in FINAL_FILES]
    paths += [ROOT / name for name in DOC_FILES]
    for path in paths:
        checked += 1
        if not path.exists():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")
            continue
        text = _read(path)
        if not text.strip():
            errors.append(f"Required file is empty: {path.relative_to(ROOT)}")
            continue
        lowered = text.lower()
        for marker in DISALLOWED:
            if marker.lower() in lowered:
                errors.append(f"Disallowed marker '{marker}' found in {path.relative_to(ROOT)}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"Secret-like value found in {path.relative_to(ROOT)}")
        for email in EMAIL_PATTERN.findall(text):
            if not email.endswith(ALLOWED_EMAIL_SUFFIXES):
                errors.append(f"Non-demo email found in {path.relative_to(ROOT)}: {email}")

    content_checks = {
        "final_delivery/final_known_limitations.md": ["production-ready", "not"],
        "final_delivery/final_course_report_materials.md": ["computational thinking", "design thinking", "knowledge alignment"],
        "final_delivery/final_presentation_outline.md": ["translation website", "knowledge alignment"],
        "final_delivery/final_poster_copy.md": ["evaluation"],
        "final_delivery/final_acceptance_report.md": ["local pilot-ready", "production-ready"],
    }
    for rel_path, terms in content_checks.items():
        path = ROOT / rel_path
        if path.exists() and not _has_all(path, terms):
            errors.append(f"{rel_path} is missing required content: {', '.join(terms)}")

    return errors, warnings, checked


def main() -> int:
    errors, warnings, checked = validate()
    if errors:
        print("Final Delivery Check: FAIL")
        print(f"Files checked: {checked}")
        for error in errors:
            print(f"- {error}")
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"- {warning}")
        return 1
    print("Final Delivery Check: PASS")
    print(f"Files checked: {checked}")
    print(f"Warnings: {len(warnings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
