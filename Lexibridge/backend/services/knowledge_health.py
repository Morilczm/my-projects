"""Knowledge-base health checks for local pilot deployments."""

from __future__ import annotations


def summarize_health(version, chunks, sources) -> dict:
    issues = []
    warnings = []
    if version is None:
        issues.append("No published KB version found.")
        return {"status": "FAIL", "issues": issues, "warnings": warnings, "metrics": {}}
    active_chunks = [chunk for chunk in chunks if bool(getattr(chunk, "is_active", True))]
    duplicate_chunks = [chunk for chunk in chunks if bool(getattr(chunk, "is_duplicate", False))]
    if not active_chunks:
        issues.append("Published version has zero active chunks.")
    if str(getattr(version, "scope_type", "") or getattr(version, "kb_scope", "")) == "course":
        leaked = [chunk for chunk in active_chunks if str(getattr(chunk, "scope_type", "course")) == "personal" or getattr(chunk, "visibility", "") == "private"]
        if leaked:
            issues.append("Personal chunks found in course KB.")
    removed_active = []
    unknown_auth = []
    source_by_id = {getattr(source, "id", None): source for source in sources}
    for chunk in active_chunks:
        source = source_by_id.get(getattr(chunk, "knowledge_source_id", None) or getattr(chunk, "source_id", None))
        if source is None:
            continue
        if getattr(source, "status", "") == "removed":
            removed_active.append(chunk)
        if getattr(source, "authorization_status", "unknown") == "unknown":
            unknown_auth.append(source)
    if removed_active:
        issues.append("Removed sources are active in index.")
    duplicate_ratio = len(duplicate_chunks) / max(1, len(chunks))
    if duplicate_ratio > 0.30:
        warnings.append(f"duplicate ratio is high: {duplicate_ratio:.2f}")
    unknown_ratio = len({getattr(source, "id", None) for source in unknown_auth}) / max(1, len(sources))
    if unknown_ratio > 0.25:
        warnings.append(f"unknown authorization ratio is high: {unknown_ratio:.2f}")
    status = "FAIL" if issues else "WARN" if warnings else "PASS"
    return {
        "status": status,
        "issues": issues,
        "warnings": warnings,
        "metrics": {
            "active_chunk_count": len(active_chunks),
            "chunk_count": len(chunks),
            "duplicate_count": len(duplicate_chunks),
            "duplicate_ratio": round(duplicate_ratio, 4),
            "source_count": len(sources),
            "unknown_authorization_count": len({getattr(source, "id", None) for source in unknown_auth}),
        },
    }
