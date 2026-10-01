"""Prompt template registry defaults and validation helpers."""

from __future__ import annotations

import json


ALIGNMENT_STATUS_ENUM = [
    "exact_match",
    "accepted_translation",
    "partial_match",
    "broader_than_source",
    "narrower_than_source",
    "ambiguous_candidate",
    "multi_translation_conflict",
    "no_en_evidence",
    "no_zh_evidence",
    "domain_mismatch",
    "unverified_translation",
]


TERM_ALIGNMENT_SCHEMA = {
    "type": "object",
    "required": [
        "alignment_status",
        "candidate_chinese_term",
        "concept_explanation",
        "alignment_reason",
        "ai_confidence",
        "risk_flags",
        "requires_human_review",
    ],
    "properties": {
        "alignment_status": {"type": "string", "enum": ALIGNMENT_STATUS_ENUM},
        "candidate_chinese_term": {"type": "string"},
        "concept_explanation": {"type": "string"},
        "alignment_reason": {"type": "string"},
        "ai_confidence": {"type": "number"},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "requires_human_review": {"type": "boolean"},
    },
}


TERM_EXTRACTION_SCHEMA = {
    "type": "object",
    "required": ["terms"],
    "properties": {
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["english_term", "context_sentence", "reason", "confidence"],
                "properties": {
                    "english_term": {"type": "string"},
                    "context_sentence": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number"},
                },
            },
        }
    },
}


FEEDBACK_CLASSIFICATION_SCHEMA = {
    "type": "object",
    "required": ["classification", "root_cause", "severity", "summary"],
    "properties": {
        "classification": {"type": "string"},
        "root_cause": {"type": "string"},
        "severity": {"type": "string"},
        "summary": {"type": "string"},
    },
}


DEFAULT_PROMPTS = [
    {
        "prompt_key": "term_extraction",
        "prompt_version": "v1",
        "task_type": "term_extraction",
        "language": "en",
        "json_schema": TERM_EXTRACTION_SCHEMA,
        "notes": "Extract English academic terms only; no full sentences or OCR placeholders.",
        "template_text": """
You are LexiBridge AI's term extraction component.
Input contains parsed DocumentChunk text only. Extract professional English course terms.
Do not output complete sentences, verb phrases, OCR placeholders, formula fragments, or unsupported guesses.
Return JSON matching the schema exactly.
""".strip(),
    },
    {
        "prompt_key": "term_alignment",
        "prompt_version": "v1",
        "task_type": "term_alignment",
        "language": "bilingual",
        "json_schema": TERM_ALIGNMENT_SCHEMA,
        "notes": "Evidence-bound bilingual terminology alignment.",
        "template_text": """
You are LexiBridge AI's bilingual course knowledge alignment component.
Use only the provided English evidence and Chinese evidence.
Do not invent evidence. If either evidence side is missing, output no_en_evidence or no_zh_evidence.
Do not mark mock/local results as verified. Do not bypass retrieval gates.
Return JSON matching the schema exactly.
""".strip(),
    },
    {
        "prompt_key": "feedback_classification",
        "prompt_version": "v1",
        "task_type": "feedback_classification",
        "language": "bilingual",
        "json_schema": FEEDBACK_CLASSIFICATION_SCHEMA,
        "notes": "Pilot feedback triage helper.",
        "template_text": """
Classify pilot feedback into the provided taxonomy using only the submitted issue text and linked card metadata.
Return concise JSON. Do not include student private content beyond a short sanitized summary.
""".strip(),
    },
]


def default_prompt_lookup(prompt_key, prompt_version=None, task_type=None):
    prompt_key = str(prompt_key or "").strip()
    prompt_version = str(prompt_version or "").strip()
    task_type = str(task_type or "").strip()
    for prompt in DEFAULT_PROMPTS:
        if prompt["prompt_key"] != prompt_key:
            continue
        if prompt_version and prompt["prompt_version"] != prompt_version:
            continue
        if task_type and prompt["task_type"] != task_type:
            continue
        return dict(prompt)
    return None


def validate_prompt_schema(schema):
    if isinstance(schema, str):
        schema = json.loads(schema)
    if not isinstance(schema, dict) or schema.get("type") != "object":
        return False
    return "properties" in schema


def validate_ai_json(task_type, result):
    """Return (ok, reason) for a minimal JSON-schema validation."""
    if not isinstance(result, dict):
        return False, "AI result is not an object."
    if task_type == "term_alignment":
        status = result.get("alignment_status")
        if status not in ALIGNMENT_STATUS_ENUM:
            return False, f"Unsupported alignment_status: {status}"
        for field in ["candidate_chinese_term", "concept_explanation", "alignment_reason"]:
            if field not in result:
                return False, f"Missing field: {field}"
        if "risk_flags" in result and not isinstance(result["risk_flags"], list):
            return False, "risk_flags must be an array."
    elif task_type == "term_extraction":
        if not isinstance(result.get("terms"), list):
            return False, "terms must be an array."
    return True, ""
