"""Prompt construction for alignment verification providers.

The prompt helpers define the contract future LLM providers must follow. They
do not call any external model and they keep prompt inputs bounded and redacted.
"""

from __future__ import annotations

import json
from typing import Any


LEGACY_PROMPT_VERSION = "alignment-v1"
STRUCTURED_PROMPT_VERSION = "alignment-json-v2"
PROMPT_VERSION = LEGACY_PROMPT_VERSION
MAX_PROMPT_EVIDENCE_ITEMS = 5
MAX_PROMPT_SNIPPET_CHARS = 300
SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
}


class AlignmentPromptError(ValueError):
    """Raised when an alignment prompt cannot be built."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key or "").lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _truncate(value: Any, max_chars: int) -> str:
    text = _text(value)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def sanitize_prompt_input(input_data: dict[str, Any] | None) -> dict[str, Any]:
    """Redact sensitive keys and keep only bounded prompt-safe content."""
    if not isinstance(input_data, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in input_data.items():
        if _is_sensitive_key(key):
            continue
        elif key in {"english_evidence", "chinese_evidence"}:
            sanitized[key] = summarize_evidence_for_prompt(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_prompt_input(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_prompt_input(item) if isinstance(item, dict) else _truncate(item, MAX_PROMPT_SNIPPET_CHARS)
                for item in value[:MAX_PROMPT_EVIDENCE_ITEMS]
            ]
        elif key in {"english_term", "chinese_term", "course", "chapter", "retrieval_version"}:
            sanitized[key] = _truncate(value, 240)
        elif key in {"risk_labels", "parse_quality_risks"}:
            sanitized[key] = value if isinstance(value, list) else []
        elif key in {"retrieval_score_summary", "candidate_score_summary", "source_trust_summary", "candidate_info"}:
            sanitized[key] = value
    return sanitized


def summarize_evidence_for_prompt(
    evidence: Any,
    *,
    max_items: int = MAX_PROMPT_EVIDENCE_ITEMS,
    max_snippet_chars: int = MAX_PROMPT_SNIPPET_CHARS,
) -> list[dict[str, Any]]:
    if isinstance(evidence, dict):
        evidence = [evidence]
    if not isinstance(evidence, list):
        return []
    summaries: list[dict[str, Any]] = []
    for item in evidence[:max_items]:
        if not isinstance(item, dict):
            summaries.append({"snippet": _truncate(item, max_snippet_chars)})
            continue
        summaries.append({
            "chunk_uid": _truncate(item.get("chunk_uid"), 120),
            "source_uid": _truncate(item.get("source_uid"), 120),
            "source_title": _truncate(item.get("source_title"), 160),
            "course": _truncate(item.get("course"), 160),
            "chapter": _truncate(item.get("chapter"), 160),
            "language": _truncate(item.get("language"), 20),
            "source_role": _truncate(item.get("source_role"), 80),
            "trust_level": _truncate(item.get("trust_level"), 80),
            "quality_status": _truncate(item.get("quality_status"), 80),
            "quality_flags": item.get("quality_flags") if isinstance(item.get("quality_flags"), list) else [],
            "source_locator": _truncate(item.get("source_locator"), 120),
            "snippet": _truncate(item.get("snippet") or item.get("evidence_snippet") or item.get("text"), max_snippet_chars),
            "retrieval_score": item.get("score"),
            "risk_labels": item.get("risk_labels") if isinstance(item.get("risk_labels"), list) else [],
            "parse_uid": _truncate(item.get("parse_uid"), 120),
            "parse_block_uid": _truncate(item.get("parse_block_uid"), 120),
        })
    return summaries


def list_prompt_versions() -> list[str]:
    return [LEGACY_PROMPT_VERSION, STRUCTURED_PROMPT_VERSION]


def get_prompt_template(prompt_version: str = PROMPT_VERSION) -> str:
    version = _text(prompt_version) or PROMPT_VERSION
    if version not in list_prompt_versions():
        raise AlignmentPromptError(f"Unknown alignment prompt version: {version}")
    semantic_contract = (
        "You are verifying whether an English technical term and a Chinese candidate term may refer to the same "
        "course concept. Use only the provided evidence summaries. Do not invent evidence, translations, page "
        "numbers, sources, or confidence. If evidence is missing or weak, return insufficient_evidence or "
        "needs_review. Distinguish retrieval_score, candidate_score, and alignment_confidence: retrieval_score ranks "
        "evidence retrieval results, candidate_score ranks Chinese term candidates, and alignment_confidence is your "
        "bounded verification score. Do not auto approve."
    )
    if version == LEGACY_PROMPT_VERSION:
        return f"{semantic_contract} Output JSON only, with no markdown or prose outside JSON."
    return (
        f"{semantic_contract} Return exactly one single JSON object matching the required schema. "
        "Output JSON only. The response must contain JSON only: do not add explanations before or after the JSON, "
        "and do not use a Markdown code fence."
    )


def build_alignment_prompt(input_data: dict[str, Any], prompt_version: str = PROMPT_VERSION) -> str:
    template = get_prompt_template(prompt_version)
    safe_input = sanitize_prompt_input(input_data)
    schema = {
        "alignment_decision": "aligned | likely_aligned | uncertain | not_aligned | insufficient_evidence",
        "alignment_confidence": "number from 0 to 1",
        "recommendation": "needs_review | reject | insufficient_evidence | candidate_ambiguous | ready_for_human_review",
        "risk_labels": [],
        "evidence_assessment": {
            "english_evidence_supported": "boolean",
            "chinese_evidence_supported": "boolean",
            "cross_language_support": "strong | moderate | weak | missing",
            "evidence_limitations": [],
        },
        "term_assessment": {
            "english_term_ok": "boolean",
            "chinese_term_ok": "boolean",
            "candidate_ambiguity": "none | low | medium | high",
            "notes": "",
        },
        "course_context_assessment": {
            "course_match": "boolean or null",
            "chapter_match": "boolean or null",
            "notes": "",
        },
        "explanation": "short evidence-bounded explanation",
        "limitations": [],
    }
    if prompt_version == STRUCTURED_PROMPT_VERSION:
        schema["evidence_citations"] = {
            "english": [
                {
                    "source_uid": "an English source_uid from Input summary",
                    "chunk_uid": "its English chunk_uid from Input summary",
                }
            ],
            "chinese": [
                {
                    "source_uid": "a Chinese source_uid from Input summary",
                    "chunk_uid": "its Chinese chunk_uid from Input summary",
                }
            ],
        }
    return "\n\n".join([
        f"Prompt version: {prompt_version}",
        template,
        "Required JSON schema:",
        json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2),
        "Input summary:",
        json.dumps(safe_input, ensure_ascii=False, sort_keys=True, indent=2),
    ])
