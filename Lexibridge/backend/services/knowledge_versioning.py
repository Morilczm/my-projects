"""Knowledge-base version lifecycle helpers."""

from __future__ import annotations


def next_version_number(existing_versions) -> int:
    numbers = []
    for version in existing_versions:
        try:
            numbers.append(int(getattr(version, "version_number", 0) or 0))
        except (TypeError, ValueError):
            continue
    return (max(numbers) if numbers else 0) + 1


def default_version_name(scope_type: str, version_number: int, course_id=None, owner_user_id=None) -> str:
    if scope_type == "personal":
        return f"personal-{owner_user_id}-kb-v{version_number}"
    if scope_type == "global":
        return f"global-kb-v{version_number}"
    return f"course-{course_id}-kb-v{version_number}"


def can_publish_version(version) -> tuple[bool, list[str]]:
    reasons = []
    if str(getattr(version, "status", "") or "") != "ready":
        reasons.append("version status must be ready")
    if int(getattr(version, "chunk_count", 0) or 0) <= 0:
        reasons.append("chunk_count must be greater than 0")
    if str(getattr(version, "quality_gate_status", "") or "").lower() == "fail":
        reasons.append("quality gate failed")
    return not reasons, reasons
