#!/usr/bin/env python3
"""Validate the PR-15 pilot package and final presentation materials."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PILOT_FILES = [
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

PROJECT_MATERIALS = [
    "docs/final-project-summary.md",
    "docs/course-report-materials.md",
    "docs/poster-content-outline.md",
    "docs/presentation-script-outline.md",
]

DISALLOWED_TERMS = ("TODO", "FIXME", "placeholder", "your-name-here")
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


def _contains_all(content: str, required: list[str]) -> bool:
    lower = content.lower()
    return all(item.lower() in lower for item in required)


def validate() -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    warnings: list[str] = []
    files_checked = 0

    package_dir = ROOT / "pilot_package"
    if not package_dir.exists():
        errors.append("pilot_package directory is missing.")
        return errors, warnings, files_checked

    paths = [package_dir / name for name in PILOT_FILES]
    paths += [ROOT / name for name in PROJECT_MATERIALS]

    for path in paths:
        files_checked += 1
        if not path.exists():
            errors.append(f"Missing required file: {path.relative_to(ROOT)}")
            continue
        content = _read(path)
        if not content.strip():
            errors.append(f"Required file is empty: {path.relative_to(ROOT)}")
            continue
        lowered = content.lower()
        for term in DISALLOWED_TERMS:
            if term.lower() in lowered:
                errors.append(f"Disallowed term '{term}' found in {path.relative_to(ROOT)}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                errors.append(f"Secret-like value found in {path.relative_to(ROOT)}")
        for email in EMAIL_PATTERN.findall(content):
            if not email.endswith(ALLOWED_EMAIL_SUFFIXES):
                errors.append(f"Non-demo email found in {path.relative_to(ROOT)}: {email}")

    checks = {
        "pilot_package/teacher_manual.md": ["upload", "qc", "feedback"],
        "pilot_package/student_manual.md": ["search", "evidence", "favorite", "feedback"],
        "pilot_package/admin_manual.md": ["EvaluationRun", "KnowledgeBaseVersion", "Production Readiness"],
        "pilot_package/data_authorization_guide.md": ["restricted_no_derivative", "authorization_status"],
        "pilot_package/privacy_and_risk_notice.md": ["AI", "OCR", "风险"],
        "pilot_package/pilot_metrics.md": ["no_evidence_forced_alignment_rate"],
        "pilot_package/final_presentation_materials_index.md": ["Computational Thinking", "Design Thinking"],
        "docs/course-report-materials.md": ["Computational Thinking", "Design Thinking"],
        "docs/presentation-script-outline.md": ["翻译网站", "课程知识对齐平台"],
    }

    for rel_path, required in checks.items():
        path = ROOT / rel_path
        if path.exists() and not _contains_all(_read(path), required):
            errors.append(f"{rel_path} is missing required content: {', '.join(required)}")

    return errors, warnings, files_checked


def main() -> int:
    errors, warnings, files_checked = validate()
    if errors:
        print("Pilot Package Check: FAIL")
        print(f"Files checked: {files_checked}")
        for error in errors:
            print(f"- {error}")
        if warnings:
            print("Warnings:")
            for warning in warnings:
                print(f"- {warning}")
        return 1

    print("Pilot Package Check: PASS")
    print(f"Files checked: {files_checked}")
    print(f"Warnings: {len(warnings)}")
    for warning in warnings:
        print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
