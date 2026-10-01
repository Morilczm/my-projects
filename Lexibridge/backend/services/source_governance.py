"""Knowledge source authorization and quality rules."""

from __future__ import annotations


RESTRICTED_AUTH_STATUSES = {"restricted_no_derivative"}
REMOVED_STATUSES = {"removed", "archived"}
DEPRECATED_STATUSES = {"deprecated"}


def source_quality_from_governance(source) -> float:
    explicit = getattr(source, "source_quality", None)
    if explicit is not None:
        try:
            return max(0.0, min(float(explicit), 1.0))
        except (TypeError, ValueError):
            pass
    status = str(getattr(source, "status", "") or "active")
    authorization = str(getattr(source, "authorization_status", "") or "unknown")
    license_type = str(getattr(source, "license_type", "") or getattr(source, "license_status", "") or "unknown")
    source_type = str(getattr(source, "source_type", "") or "")
    if status in REMOVED_STATUSES:
        return 0.0
    if authorization in RESTRICTED_AUTH_STATUSES:
        return 0.0
    if status in DEPRECATED_STATUSES:
        return 0.35
    if authorization == "allowed_for_course_use":
        return 0.9
    if license_type in {"open_license", "public_domain", "open_licensed"}:
        return 0.75
    if license_type == "demo_synthetic" or source_type == "demo_seed":
        return 0.7
    if authorization == "allowed_for_private_use":
        return 0.6
    return 0.4


def can_source_generate_public_evidence(source) -> bool:
    authorization = str(getattr(source, "authorization_status", "") or "")
    status = str(getattr(source, "status", "") or "active")
    if status in REMOVED_STATUSES:
        return False
    if authorization in RESTRICTED_AUTH_STATUSES:
        return False
    if getattr(source, "allow_derivative_cards", True) is False:
        return False
    return True


def source_status_flags(source) -> list[str]:
    flags = []
    status = str(getattr(source, "status", "") or "active")
    authorization = str(getattr(source, "authorization_status", "") or "unknown")
    if status in DEPRECATED_STATUSES:
        flags.append("source_deprecated")
    if status in REMOVED_STATUSES:
        flags.append("source_removed")
    if authorization == "unknown":
        flags.append("source_authorization_unknown")
    if authorization in RESTRICTED_AUTH_STATUSES:
        flags.append("restricted_no_derivative")
    return flags
