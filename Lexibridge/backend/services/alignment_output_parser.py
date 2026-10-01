"""Parser and schema checks for alignment provider JSON output."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from services import parse_quality_risk


PARSER_VERSION = "alignment-parser-v1"
OUTPUT_SCHEMA_VERSION = "alignment-output-v1"
STRUCTURED_PARSER_VERSION = "alignment-parser-json-v2"
STRUCTURED_OUTPUT_SCHEMA_VERSION = "alignment-output-json-v2"
MAX_EXPLANATION_CHARS = 1000
MAX_LIMITATION_CHARS = 240
REQUIRED_OUTPUT_FIELDS = frozenset({
    "alignment_decision",
    "alignment_confidence",
    "recommendation",
    "risk_labels",
    "evidence_assessment",
    "term_assessment",
    "course_context_assessment",
    "explanation",
    "limitations",
})
STRUCTURED_OUTPUT_FIELDS = REQUIRED_OUTPUT_FIELDS | {"evidence_citations"}

ALLOWED_DECISIONS = {
    "aligned",
    "likely_aligned",
    "uncertain",
    "not_aligned",
    "insufficient_evidence",
}
ALLOWED_RECOMMENDATIONS = {
    "needs_review",
    "reject",
    "insufficient_evidence",
    "candidate_ambiguous",
    "ready_for_human_review",
}
ALLOWED_CROSS_LANGUAGE_SUPPORT = {"strong", "moderate", "weak", "missing"}
ALLOWED_CANDIDATE_AMBIGUITY = {"none", "low", "medium", "high"}


class AlignmentOutputParserError(ValueError):
    """Raised when provider output fails schema parsing."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def _text(value: Any) -> str:
    return str(value or "").strip()


def _require_dict(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AlignmentOutputParserError("invalid_alignment_output_schema", f"{field} must be an object.")
    return value


def _require_bool_or_null(value: Any, field: str) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise AlignmentOutputParserError("invalid_alignment_output_schema", f"{field} must be boolean or null.")


def _require_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise AlignmentOutputParserError("invalid_alignment_output_schema", f"{field} must be boolean.")


def _require_enum(value: Any, allowed: set[str], field: str) -> str:
    text = _text(value)
    if text not in allowed:
        raise AlignmentOutputParserError("invalid_alignment_output_schema", f"{field} has invalid value: {text}")
    return text


def _require_confidence(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise AlignmentOutputParserError("invalid_alignment_confidence", "alignment_confidence must be numeric.") from exc
    if score < 0 or score > 1:
        raise AlignmentOutputParserError("invalid_alignment_confidence", "alignment_confidence must be between 0 and 1.")
    return round(score, 4)


def truncate_alignment_explanation(text: Any, max_chars: int = MAX_EXPLANATION_CHARS) -> str:
    value = _text(text)
    if len(value) <= max_chars:
        return value
    return f"{value[:max_chars]}..."


def _normalize_string_list(values: Any, max_item_chars: int = MAX_LIMITATION_CHARS) -> list[str]:
    if not isinstance(values, list):
        raise AlignmentOutputParserError("invalid_alignment_output_schema", "Expected list field.")
    result = []
    for item in values:
        text = _text(item)
        if text:
            result.append(truncate_alignment_explanation(text, max_item_chars))
    return result


def validate_alignment_output_schema(parsed: dict[str, Any]) -> bool:
    missing = sorted(REQUIRED_OUTPUT_FIELDS - set(parsed.keys()))
    if missing:
        raise AlignmentOutputParserError("missing_alignment_output_fields", f"Missing provider output fields: {', '.join(missing)}")

    _require_enum(parsed.get("alignment_decision"), ALLOWED_DECISIONS, "alignment_decision")
    _require_confidence(parsed.get("alignment_confidence"))
    _require_enum(parsed.get("recommendation"), ALLOWED_RECOMMENDATIONS, "recommendation")
    if not isinstance(parsed.get("risk_labels"), list):
        raise AlignmentOutputParserError("invalid_alignment_output_schema", "risk_labels must be a list.")

    evidence = _require_dict(parsed.get("evidence_assessment"), "evidence_assessment")
    _require_bool(evidence.get("english_evidence_supported"), "evidence_assessment.english_evidence_supported")
    _require_bool(evidence.get("chinese_evidence_supported"), "evidence_assessment.chinese_evidence_supported")
    _require_enum(evidence.get("cross_language_support"), ALLOWED_CROSS_LANGUAGE_SUPPORT, "evidence_assessment.cross_language_support")
    _normalize_string_list(evidence.get("evidence_limitations", []))

    term = _require_dict(parsed.get("term_assessment"), "term_assessment")
    _require_bool(term.get("english_term_ok"), "term_assessment.english_term_ok")
    _require_bool(term.get("chinese_term_ok"), "term_assessment.chinese_term_ok")
    _require_enum(term.get("candidate_ambiguity"), ALLOWED_CANDIDATE_AMBIGUITY, "term_assessment.candidate_ambiguity")

    course = _require_dict(parsed.get("course_context_assessment"), "course_context_assessment")
    _require_bool_or_null(course.get("course_match"), "course_context_assessment.course_match")
    _require_bool_or_null(course.get("chapter_match"), "course_context_assessment.chapter_match")
    _normalize_string_list(parsed.get("limitations", []))
    return True


def normalize_alignment_output(parsed: dict[str, Any]) -> dict[str, Any]:
    validate_alignment_output_schema(parsed)
    evidence = parsed["evidence_assessment"]
    term = parsed["term_assessment"]
    course = parsed["course_context_assessment"]
    return {
        "alignment_decision": _require_enum(parsed.get("alignment_decision"), ALLOWED_DECISIONS, "alignment_decision"),
        "alignment_confidence": _require_confidence(parsed.get("alignment_confidence")),
        "recommendation": _require_enum(parsed.get("recommendation"), ALLOWED_RECOMMENDATIONS, "recommendation"),
        "risk_labels": parse_quality_risk.normalize_labels(parsed.get("risk_labels", [])),
        "evidence_assessment": {
            "english_evidence_supported": _require_bool(evidence.get("english_evidence_supported"), "evidence_assessment.english_evidence_supported"),
            "chinese_evidence_supported": _require_bool(evidence.get("chinese_evidence_supported"), "evidence_assessment.chinese_evidence_supported"),
            "cross_language_support": _require_enum(evidence.get("cross_language_support"), ALLOWED_CROSS_LANGUAGE_SUPPORT, "evidence_assessment.cross_language_support"),
            "evidence_limitations": _normalize_string_list(evidence.get("evidence_limitations", [])),
        },
        "term_assessment": {
            "english_term_ok": _require_bool(term.get("english_term_ok"), "term_assessment.english_term_ok"),
            "chinese_term_ok": _require_bool(term.get("chinese_term_ok"), "term_assessment.chinese_term_ok"),
            "candidate_ambiguity": _require_enum(term.get("candidate_ambiguity"), ALLOWED_CANDIDATE_AMBIGUITY, "term_assessment.candidate_ambiguity"),
            "notes": truncate_alignment_explanation(term.get("notes", ""), 500),
        },
        "course_context_assessment": {
            "course_match": _require_bool_or_null(course.get("course_match"), "course_context_assessment.course_match"),
            "chapter_match": _require_bool_or_null(course.get("chapter_match"), "course_context_assessment.chapter_match"),
            "notes": truncate_alignment_explanation(course.get("notes", ""), 500),
        },
        "explanation": truncate_alignment_explanation(parsed.get("explanation", "")),
        "limitations": _normalize_string_list(parsed.get("limitations", [])),
        "is_production_result": False,
        "can_auto_approve": False,
    }


def parse_alignment_provider_output(raw_output: Any) -> dict[str, Any]:
    if isinstance(raw_output, dict):
        parsed = raw_output
    elif isinstance(raw_output, str):
        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise AlignmentOutputParserError("provider_output_not_json", "Provider output is not valid JSON.") from exc
    else:
        raise AlignmentOutputParserError("provider_output_not_json", "Provider output must be a JSON object or JSON string.")
    if not isinstance(parsed, dict):
        raise AlignmentOutputParserError("invalid_alignment_output_schema", "Provider output must be a JSON object.")
    return normalize_alignment_output(parsed)


def validate_alignment_output_provenance(
    parsed: dict[str, Any],
    allowed_provenance: dict[str, set[tuple[str, str]]],
) -> dict[str, list[dict[str, str]]]:
    citations = _require_dict(parsed.get("evidence_citations"), "evidence_citations")
    normalized: dict[str, list[dict[str, str]]] = {}
    for language in ("english", "chinese"):
        values = citations.get(language)
        if not isinstance(values, list) or not values:
            raise AlignmentOutputParserError(
                "missing_alignment_output_fields",
                f"evidence_citations.{language} must be a non-empty list.",
            )
        allowed = allowed_provenance.get(language, set())
        normalized[language] = []
        for value in values:
            item = _require_dict(value, f"evidence_citations.{language}")
            unknown = sorted(set(item) - {"source_uid", "chunk_uid"})
            if unknown:
                raise AlignmentOutputParserError(
                    "invalid_alignment_output_schema",
                    f"evidence_citations.{language} contains unknown fields.",
                )
            source_uid = _text(item.get("source_uid"))
            chunk_uid = _text(item.get("chunk_uid"))
            if not source_uid or not chunk_uid or (source_uid, chunk_uid) not in allowed:
                raise AlignmentOutputParserError(
                    "invalid_alignment_output_provenance",
                    f"evidence_citations.{language} contains unknown provenance.",
                )
            normalized[language].append({
                "source_uid": source_uid,
                "chunk_uid": chunk_uid,
            })
    return normalized


def parse_structured_alignment_provider_output(
    raw_output: Any,
    *,
    allowed_provenance: dict[str, set[tuple[str, str]]],
) -> dict[str, Any]:
    if not isinstance(raw_output, (dict, str)):
        raise AlignmentOutputParserError(
            "provider_output_not_json",
            "Provider output must be a JSON object or JSON string.",
        )
    try:
        parsed = raw_output if isinstance(raw_output, dict) else json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise AlignmentOutputParserError(
            "provider_output_not_json", "Provider output is not valid JSON."
        ) from exc
    if not isinstance(parsed, dict):
        raise AlignmentOutputParserError(
            "invalid_alignment_output_schema",
            "Provider output must be a JSON object.",
        )
    unknown_root = sorted(set(parsed) - STRUCTURED_OUTPUT_FIELDS)
    if unknown_root:
        raise AlignmentOutputParserError(
            "invalid_alignment_output_schema",
            "Provider output contains unknown top-level fields.",
        )
    for field, allowed_fields in (
        (
            "evidence_assessment",
            {
                "english_evidence_supported",
                "chinese_evidence_supported",
                "cross_language_support",
                "evidence_limitations",
            },
        ),
        (
            "term_assessment",
            {
                "english_term_ok",
                "chinese_term_ok",
                "candidate_ambiguity",
                "notes",
            },
        ),
        (
            "course_context_assessment",
            {"course_match", "chapter_match", "notes"},
        ),
    ):
        value = _require_dict(parsed.get(field), field)
        if set(value) - allowed_fields:
            raise AlignmentOutputParserError(
                "invalid_alignment_output_schema",
                f"{field} contains unknown fields.",
            )
    citations = validate_alignment_output_provenance(parsed, allowed_provenance)
    normalized = normalize_alignment_output(parsed)
    normalized["evidence_citations"] = citations
    return normalized


def build_sanitized_output_diagnostics(
    raw_output: Any,
    *,
    finish_reason: str = "",
    response_model: str = "",
    validation_stage: str = "",
    parser_reason: str = "",
) -> dict[str, Any]:
    """Describe provider output shape without retaining recoverable content."""
    text = raw_output if isinstance(raw_output, str) else ""
    stripped = text.strip()
    length = len(text)
    if length == 0:
        length_bucket = "empty"
    elif length <= 255:
        length_bucket = "1-255"
    elif length <= 1023:
        length_bucket = "256-1023"
    elif length <= 4095:
        length_bucket = "1024-4095"
    else:
        length_bucket = "4096+"

    if not stripped:
        first_class = "none"
    elif stripped.startswith("```"):
        first_class = "markdown_fence"
    elif stripped[0] == "{":
        first_class = "object_open"
    elif stripped[0] == "[":
        first_class = "array_open"
    elif stripped[0].isalpha():
        first_class = "alphabetic"
    else:
        first_class = "other"

    return {
        "content_present": bool(stripped),
        "content_length_bucket": length_bucket,
        "first_non_whitespace_character_class": first_class,
        "looks_like_json_object": bool(
            stripped.startswith("{") and stripped.endswith("}")
        ),
        "outer_code_fence_present": bool(
            stripped.startswith("```") and stripped.endswith("```")
        ),
        "finish_reason": str(finish_reason or ""),
        "response_model": str(response_model or ""),
        "response_hash": hashlib.sha256(text.encode("utf-8")).hexdigest() if text else "",
        "schema_validation_stage": str(validation_stage or ""),
        "stable_parser_reason": str(parser_reason or ""),
        "stores_full_raw_output": False,
    }


def build_failed_alignment_output(error_code: str, error_message: str) -> dict[str, Any]:
    return {
        "alignment_decision": "uncertain",
        "alignment_confidence": None,
        "recommendation": "needs_review",
        "risk_labels": ["alignment_provider_output_invalid"],
        "evidence_assessment": {
            "english_evidence_supported": False,
            "chinese_evidence_supported": False,
            "cross_language_support": "missing",
            "evidence_limitations": [truncate_alignment_explanation(error_message, 240)],
        },
        "term_assessment": {
            "english_term_ok": False,
            "chinese_term_ok": False,
            "candidate_ambiguity": "high",
            "notes": "Provider output could not be parsed into the required schema.",
        },
        "course_context_assessment": {
            "course_match": None,
            "chapter_match": None,
            "notes": "",
        },
        "explanation": "Alignment provider output failed schema parsing. This result is not production trustworthy.",
        "limitations": ["provider_output_parse_failed"],
        "is_production_result": False,
        "can_auto_approve": False,
        "verification_status": "failed",
        "error_code": error_code,
        "error_message": error_message,
    }
