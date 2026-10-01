"""Alignment verification schemas, run persistence, and safe card attachment."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from services import alignment_providers
from services import concept_alignment_cards
from services import parse_quality_risk


SENSITIVE_KEY_PARTS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
}
MAX_EVIDENCE_ITEMS = 20
MAX_SNIPPET_CHARS = 300


class AlignmentVerificationError(ValueError):
    """Raised for controlled alignment verification failures."""


class AlignmentVerificationProviderError(AlignmentVerificationError):
    """Raised when provider selection or execution fails."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _loads_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _labels(value: Any) -> list[str]:
    return parse_quality_risk.normalize_labels(value)


def _merge_labels(*groups: Any) -> list[str]:
    merged: list[str] = []
    for labels in groups:
        merged = parse_quality_risk.merge_risk_labels(merged, labels)
    return merged


def _is_sensitive_key(key: Any) -> bool:
    lowered = str(key or "").lower()
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def _redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                result[str(key)] = "[REDACTED]"
            else:
                result[str(key)] = _redact_sensitive(item)
        return result
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


def _bounded_text(value: Any, max_chars: int = MAX_SNIPPET_CHARS) -> str:
    text = _text(value)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def _normalize_evidence_item(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"snippet": _bounded_text(item)}
    safe = _redact_sensitive(item)
    return {
        "chunk_uid": _text(safe.get("chunk_uid")),
        "source_uid": _text(safe.get("source_uid")),
        "source_title": _bounded_text(safe.get("source_title"), 120),
        "course": _text(safe.get("course")),
        "chapter": _text(safe.get("chapter")),
        "language": _text(safe.get("language")),
        "source_role": _text(safe.get("source_role")),
        "trust_level": _text(safe.get("trust_level")),
        "quality_status": _text(safe.get("quality_status")),
        "quality_flags": _labels(safe.get("quality_flags", [])),
        "source_locator": _text(safe.get("source_locator")),
        "snippet": _bounded_text(safe.get("snippet") or safe.get("evidence_snippet") or safe.get("text")),
        "score": safe.get("score"),
        "retrieval_reason": _bounded_text(safe.get("retrieval_reason"), 200),
        "risk_labels": _labels(safe.get("risk_labels", [])),
        "parse_uid": _text(safe.get("parse_uid")),
        "parse_block_uid": _text(safe.get("parse_block_uid")),
        "evidence_type": _text(safe.get("evidence_type")),
        "selected_chinese_candidate": _redact_sensitive(safe.get("selected_chinese_candidate", {})),
    }


def _normalize_evidence(value: Any) -> list[dict[str, Any]]:
    evidence = _loads_json(value, [])
    if isinstance(evidence, dict):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []
    return [_normalize_evidence_item(item) for item in evidence[:MAX_EVIDENCE_ITEMS]]


def _normalize_candidate_info(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe = _redact_sensitive(value)
    return {
        "candidate_uid": _text(safe.get("candidate_uid")),
        "chinese_term": _text(safe.get("chinese_term")),
        "source_type": _text(safe.get("source_type")),
        "source_uid": _text(safe.get("source_uid")),
        "chunk_uid": _text(safe.get("chunk_uid")),
        "card_uid": _text(safe.get("card_uid")),
        "term_id": _text(safe.get("term_id")),
        "score": safe.get("score"),
        "risk_labels": _labels(safe.get("risk_labels", [])),
    }


def _extract_candidate_info(payload: dict[str, Any], chinese_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    candidate = payload.get("candidate_info") or payload.get("selected_chinese_candidate") or {}
    if not candidate:
        for item in chinese_evidence:
            selected = item.get("selected_chinese_candidate")
            if isinstance(selected, dict) and selected:
                candidate = selected
                break
    return _normalize_candidate_info(candidate)


def _extract_candidate_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = payload.get("chinese_term_candidates") or []
    if not isinstance(candidates, list):
        return []
    return [_normalize_candidate_info(candidate) for candidate in candidates[:MAX_EVIDENCE_ITEMS]]


def _score_summary(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    scores = []
    for item in evidence:
        try:
            scores.append(float(item.get("score")))
        except (TypeError, ValueError):
            continue
    if not scores:
        return {"count": len(evidence), "scores": []}
    return {
        "count": len(evidence),
        "max": round(max(scores), 4),
        "min": round(min(scores), 4),
        "avg": round(sum(scores) / len(scores), 4),
        "scores": [round(score, 4) for score in scores[:5]],
    }


def _candidate_score_summary(candidate_info: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    scores = []
    if candidate_info.get("score") is not None:
        scores.append(candidate_info.get("score"))
    for candidate in candidates:
        if candidate.get("score") is not None:
            scores.append(candidate.get("score"))
    numeric = []
    for score in scores:
        try:
            numeric.append(float(score))
        except (TypeError, ValueError):
            continue
    return {
        "selected_candidate_score": numeric[0] if numeric else None,
        "candidate_count": len(candidates),
        "scores": [round(score, 4) for score in numeric[:5]],
    }


def _source_trust_summary(english_evidence: list[dict[str, Any]], chinese_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    trust_levels = {}
    quality_statuses = {}
    for item in [*english_evidence, *chinese_evidence]:
        trust = _text(item.get("trust_level")) or "unknown"
        quality = _text(item.get("quality_status")) or "unknown"
        trust_levels[trust] = trust_levels.get(trust, 0) + 1
        quality_statuses[quality] = quality_statuses.get(quality, 0) + 1
    return {"trust_levels": trust_levels, "quality_statuses": quality_statuses}


def build_alignment_verification_input_from_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    data = _redact_sensitive(dict(payload or {}))
    raw_provider_options = data.get("provider_options") if isinstance(data.get("provider_options"), dict) else {}
    english_evidence = _normalize_evidence(data.get("english_evidence", []))
    chinese_evidence = _normalize_evidence(data.get("chinese_evidence", []))
    candidate_info = _extract_candidate_info(data, chinese_evidence)
    candidates = _extract_candidate_list(data)
    risk_labels = _merge_labels(
        data.get("risk_labels", []),
        candidate_info.get("risk_labels", []),
        *(item.get("risk_labels", []) for item in [*english_evidence, *chinese_evidence]),
    )
    return {
        "card_uid": _text(data.get("card_uid")),
        "english_term": _text(data.get("english_term")),
        "chinese_term": _text(data.get("chinese_term")),
        "course": _text(data.get("course")),
        "chapter": _text(data.get("chapter")),
        "english_evidence": english_evidence,
        "chinese_evidence": chinese_evidence,
        "candidate_info": candidate_info,
        "chinese_term_candidates": candidates,
        "retrieval_version": _text(data.get("retrieval_version")),
        "provider_options": {
            "fake_response_type": _text(data.get("fake_response_type") or raw_provider_options.get("fake_response_type")),
            "replay_response_type": _text(data.get("replay_response_type") or raw_provider_options.get("replay_response_type")),
            "prompt_version": _text(data.get("prompt_version") or raw_provider_options.get("prompt_version")),
            "max_prompt_chars": data.get("max_prompt_chars") or raw_provider_options.get("max_prompt_chars"),
            "max_output_chars": data.get("max_output_chars") or raw_provider_options.get("max_output_chars"),
            "max_estimated_cost": data.get("max_estimated_cost") or raw_provider_options.get("max_estimated_cost"),
            "timeout_seconds": data.get("timeout_seconds") or raw_provider_options.get("timeout_seconds"),
            "max_retries": data.get("max_retries") or raw_provider_options.get("max_retries"),
        },
        "risk_labels": risk_labels,
        "parse_quality_risks": _labels(data.get("parse_quality_risks") or data.get("input_risk_labels", [])),
        "source_trust_summary": data.get("source_trust_summary") or _source_trust_summary(english_evidence, chinese_evidence),
        "retrieval_score_summary": _score_summary([*english_evidence, *chinese_evidence]),
        "candidate_score_summary": _candidate_score_summary(candidate_info, candidates),
    }


def build_alignment_verification_input_from_card(card: Any) -> dict[str, Any]:
    payload = {
        "card_uid": getattr(card, "card_uid", ""),
        "english_term": getattr(card, "english_term", ""),
        "chinese_term": getattr(card, "chinese_term", ""),
        "course": getattr(card, "course", ""),
        "chapter": getattr(card, "chapter", ""),
        "english_evidence": _loads_json(getattr(card, "english_evidence", "[]"), []),
        "chinese_evidence": _loads_json(getattr(card, "chinese_evidence", "[]"), []),
        "retrieval_version": getattr(card, "retrieval_version", ""),
        "risk_labels": _loads_json(getattr(card, "risk_labels", "[]"), []),
        "parse_quality_risks": _loads_json(getattr(card, "input_risk_labels", "[]"), []),
    }
    return build_alignment_verification_input_from_payload(payload)


def validate_alignment_verification_input(input_data: dict[str, Any]) -> dict[str, Any]:
    data = build_alignment_verification_input_from_payload(input_data)
    if not data["english_term"]:
        raise AlignmentVerificationError("english_term is required.")
    risks = data["risk_labels"]
    if not data["chinese_term"]:
        risks = _merge_labels(risks, ["missing_chinese_term"])
    if not data["english_evidence"]:
        risks = _merge_labels(risks, ["no_english_evidence"])
    if not data["chinese_evidence"]:
        risks = _merge_labels(risks, ["no_chinese_evidence"])
    data["risk_labels"] = risks
    return data


def _top_chunk_uids(evidence: list[dict[str, Any]]) -> list[str]:
    return [_text(item.get("chunk_uid")) for item in evidence[:5] if _text(item.get("chunk_uid"))]


def _verification_status(output_data: dict[str, Any]) -> str:
    status = _text(output_data.get("verification_status"))
    provider_type = _text(output_data.get("provider_type"))
    if provider_type == "mock":
        return status if status in {"mock_only", "needs_review", "failed"} else "mock_only"
    if provider_type == "fake_llm":
        return status if status in {"needs_review", "completed", "failed"} else "needs_review"
    if provider_type in {"external_llm", "replay_llm"}:
        return status if status in {"needs_review", "completed", "failed"} else "needs_review"
    return status or "completed"


def create_alignment_verification_run(
    session: Any,
    run_model: Any,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
    *,
    card_uid: str = "",
    latency_ms: int | None = None,
    now_fn=None,
    commit: bool = True,
) -> Any:
    confidence = output_data.get("alignment_confidence")
    if confidence in ("", None):
        confidence = None
    else:
        confidence = float(confidence)
        if confidence < 0 or confidence > 1:
            raise AlignmentVerificationError("alignment_confidence must be between 0 and 1.")
    run = run_model(
        card_uid=card_uid or input_data.get("card_uid", ""),
        english_term=input_data.get("english_term", ""),
        chinese_term=input_data.get("chinese_term", ""),
        course=input_data.get("course", ""),
        chapter=input_data.get("chapter", ""),
        provider_name=output_data.get("provider_name", ""),
        provider_type=output_data.get("provider_type", ""),
        provider_version=output_data.get("provider_version", ""),
        input_payload=_dumps_json(input_data),
        output_payload=_dumps_json(output_data),
        english_evidence_count=len(input_data.get("english_evidence", [])),
        chinese_evidence_count=len(input_data.get("chinese_evidence", [])),
        top_english_chunk_uids=_dumps_json(_top_chunk_uids(input_data.get("english_evidence", []))),
        top_chinese_chunk_uids=_dumps_json(_top_chunk_uids(input_data.get("chinese_evidence", []))),
        retrieval_score_summary=_dumps_json(input_data.get("retrieval_score_summary", {})),
        candidate_score_summary=_dumps_json(input_data.get("candidate_score_summary", {})),
        alignment_confidence=confidence,
        verification_status=_verification_status(output_data),
        recommendation=output_data.get("recommendation", "needs_review"),
        risk_labels=_dumps_json(output_data.get("risk_labels", [])),
        prompt_version=output_data.get("prompt_version", ""),
        prompt_summary=_dumps_json(output_data.get("prompt_summary", {})),
        raw_output_summary=_dumps_json(output_data.get("raw_output_summary", {})),
        parser_version=output_data.get("parser_version", ""),
        output_schema_version=output_data.get("output_schema_version", ""),
        provider_response_status=output_data.get("provider_response_status", ""),
        error_code=output_data.get("error_code", ""),
        error_message=output_data.get("error_message", ""),
        latency_ms=latency_ms,
        created_at=now_fn() if now_fn else "",
    )
    session.add(run)
    if commit:
        session.commit()
    else:
        session.flush()
    return run


def _safe_reference_ids(evidence: list[dict[str, Any]]) -> list[str]:
    return sorted({
        _text(item.get("chunk_uid"))
        for item in evidence
        if isinstance(item, dict) and _text(item.get("chunk_uid"))
    })


def _safe_provider_error(value: Any) -> str:
    return _safe_provider_text(value, fallback="Formal alignment verification failed.", max_length=500)


def _safe_provider_text(value: Any, *, fallback: str = "", max_length: int = 160) -> str:
    text = _text(value)
    forbidden = ("LEXIBRIDGE_SENTINEL_SECRET", "Authorization:", "Cookie:", "Bearer ", "sk-")
    if any(marker in text for marker in forbidden):
        return fallback
    return text[:max_length]


def _safe_provider_labels(value: Any) -> list[str]:
    return [
        safe
        for label in _labels(value)
        if (safe := _safe_provider_text(label, max_length=120))
    ]


def _safe_non_negative_number(value: Any, *, integer: bool = False) -> int | float:
    try:
        number = int(value) if integer else float(value)
    except (TypeError, ValueError):
        return 0 if integer else 0.0
    if number < 0:
        return 0 if integer else 0.0
    return number


def _safe_estimated_cost(value: Any) -> dict[str, int | float]:
    source = value if isinstance(value, dict) else {}
    return {
        "estimated_input_tokens": _safe_non_negative_number(
            source.get("estimated_input_tokens"), integer=True
        ),
        "estimated_output_tokens": _safe_non_negative_number(
            source.get("estimated_output_tokens"), integer=True
        ),
        "estimated_cost": _safe_non_negative_number(source.get("estimated_cost")),
    }


def build_safe_alignment_verification_persistence(
    input_data: dict[str, Any],
    output_data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return reference-only input and bounded parsed output summaries."""

    normalized = validate_alignment_verification_input(input_data)
    english_refs = _safe_reference_ids(normalized.get("english_evidence", []))
    chinese_refs = _safe_reference_ids(normalized.get("chinese_evidence", []))
    candidate_info = normalized.get("candidate_info") or {}
    candidate_refs = sorted({
        _text(value)
        for value in (
            candidate_info.get("candidate_uid"),
            candidate_info.get("source_uid"),
            candidate_info.get("chunk_uid"),
            candidate_info.get("card_uid"),
            candidate_info.get("term_id"),
        )
        if _text(value)
    })
    safe_input = {
        "card_uid": _text(normalized.get("card_uid")),
        "english_term": _text(normalized.get("english_term")),
        "chinese_term": _text(normalized.get("chinese_term")),
        "course": _text(normalized.get("course")),
        "chapter": _text(normalized.get("chapter")),
        "english_evidence_refs": english_refs,
        "chinese_evidence_refs": chinese_refs,
        "chinese_candidate_provenance_refs": candidate_refs,
        "retrieval_version": _text(normalized.get("retrieval_version")),
        "risk_labels": _labels(normalized.get("risk_labels", [])),
    }
    raw_summary = output_data.get("raw_output_summary")
    raw_summary = raw_summary if isinstance(raw_summary, dict) else {}
    prompt_summary = output_data.get("prompt_summary")
    prompt_summary = prompt_summary if isinstance(prompt_summary, dict) else {}
    explanation = _safe_provider_text(output_data.get("explanation"), max_length=2000)
    if not explanation and _text(output_data.get("verification_status")) != "failed":
        raise AlignmentVerificationError(
            "formal verification explanation must be nonempty before persistence."
        )
    safe_output = {
        "provider_name": _safe_provider_text(output_data.get("provider_name"), max_length=120),
        "provider_type": _safe_provider_text(output_data.get("provider_type"), max_length=80),
        "provider_version": _safe_provider_text(output_data.get("provider_version"), max_length=120),
        "alignment_decision": _safe_provider_text(output_data.get("alignment_decision"), max_length=80),
        "alignment_confidence": output_data.get("alignment_confidence"),
        "explanation": explanation,
        "recommendation": _safe_provider_text(
            output_data.get("recommendation"), fallback="needs_review", max_length=80
        ) or "needs_review",
        "risk_labels": _safe_provider_labels(output_data.get("risk_labels", [])),
        "verification_status": _safe_provider_text(output_data.get("verification_status"), max_length=80),
        "provider_response_status": _safe_provider_text(
            output_data.get("provider_response_status"), max_length=80
        ),
        "prompt_version": _safe_provider_text(output_data.get("prompt_version"), max_length=80),
        "prompt_summary": {
            "prompt_version": _safe_provider_text(prompt_summary.get("prompt_version"), max_length=80),
            "prompt_chars": _safe_non_negative_number(prompt_summary.get("prompt_chars"), integer=True),
            "english_evidence_count": _safe_non_negative_number(
                prompt_summary.get("english_evidence_count"), integer=True
            ),
            "chinese_evidence_count": _safe_non_negative_number(
                prompt_summary.get("chinese_evidence_count"), integer=True
            ),
            "stores_full_prompt": False,
        },
        "raw_output_summary": {
            "raw_output_chars": _safe_non_negative_number(
                raw_summary.get("raw_output_chars"), integer=True
            ),
            "truncated": bool(raw_summary.get("truncated", False)),
            "content_present": bool(raw_summary.get("content_present", False)),
            "content_length_bucket": _safe_provider_text(
                raw_summary.get("content_length_bucket"), max_length=40
            ),
            "first_non_whitespace_character_class": _safe_provider_text(
                raw_summary.get("first_non_whitespace_character_class"), max_length=40
            ),
            "looks_like_json_object": bool(
                raw_summary.get("looks_like_json_object", False)
            ),
            "outer_code_fence_present": bool(
                raw_summary.get("outer_code_fence_present", False)
            ),
            "finish_reason": _safe_provider_text(
                raw_summary.get("finish_reason"), max_length=80
            ),
            "response_model": _safe_provider_text(
                raw_summary.get("response_model"), max_length=120
            ),
            "response_hash": _safe_provider_text(
                raw_summary.get("response_hash"), max_length=80
            ),
            "schema_validation_stage": _safe_provider_text(
                raw_summary.get("schema_validation_stage"), max_length=80
            ),
            "stable_parser_reason": _safe_provider_text(
                raw_summary.get("stable_parser_reason"), max_length=120
            ),
            "stores_full_raw_output": False,
        },
        "parser_version": _safe_provider_text(output_data.get("parser_version"), max_length=80),
        "output_schema_version": _safe_provider_text(
            output_data.get("output_schema_version"), max_length=80
        ),
        "is_production_result": False,
        "can_auto_approve": False,
        "estimated_cost": _safe_estimated_cost(output_data.get("estimated_cost")),
        "retry_count": _safe_non_negative_number(output_data.get("retry_count"), integer=True),
        "error_code": _safe_provider_text(output_data.get("error_code"), max_length=120),
        "error_message": _safe_provider_error(output_data.get("error_message")),
    }
    return safe_input, safe_output


def create_safe_alignment_verification_run(
    session: Any,
    run_model: Any,
    input_data: dict[str, Any],
    output_data: dict[str, Any],
    *,
    execution_key: str,
    card_uid: str = "",
    latency_ms: int | None = None,
    now_fn=None,
) -> Any:
    """Persist a formal run without owning commit/rollback or storing evidence bodies."""

    safe_input, safe_output = build_safe_alignment_verification_persistence(input_data, output_data)
    confidence = safe_output.get("alignment_confidence")
    if confidence in (None, ""):
        confidence = None
    else:
        confidence = float(confidence)
        if confidence < 0 or confidence > 1:
            raise AlignmentVerificationError("alignment_confidence must be between 0 and 1.")
    run = run_model(
        execution_key=_text(execution_key),
        card_uid=_text(card_uid or safe_input.get("card_uid")),
        english_term=safe_input.get("english_term", ""),
        chinese_term=safe_input.get("chinese_term", ""),
        course=safe_input.get("course", ""),
        chapter=safe_input.get("chapter", ""),
        provider_name=safe_output.get("provider_name", ""),
        provider_type=safe_output.get("provider_type", ""),
        provider_version=safe_output.get("provider_version", ""),
        input_payload=_dumps_json(safe_input),
        output_payload=_dumps_json(safe_output),
        english_evidence_count=len(safe_input.get("english_evidence_refs", [])),
        chinese_evidence_count=len(safe_input.get("chinese_evidence_refs", [])),
        top_english_chunk_uids=_dumps_json(safe_input.get("english_evidence_refs", [])[:5]),
        top_chinese_chunk_uids=_dumps_json(safe_input.get("chinese_evidence_refs", [])[:5]),
        retrieval_score_summary=_dumps_json({
            "english_count": len(safe_input.get("english_evidence_refs", [])),
            "chinese_count": len(safe_input.get("chinese_evidence_refs", [])),
        }),
        candidate_score_summary=_dumps_json({
            "provenance_count": len(safe_input.get("chinese_candidate_provenance_refs", [])),
        }),
        alignment_confidence=confidence,
        verification_status=_verification_status(safe_output),
        recommendation=safe_output.get("recommendation", "needs_review"),
        risk_labels=_dumps_json(safe_output.get("risk_labels", [])),
        prompt_version=safe_output.get("prompt_version", ""),
        prompt_summary=_dumps_json(safe_output.get("prompt_summary", {})),
        raw_output_summary=_dumps_json(safe_output.get("raw_output_summary", {})),
        parser_version=safe_output.get("parser_version", ""),
        output_schema_version=safe_output.get("output_schema_version", ""),
        provider_response_status=safe_output.get("provider_response_status", ""),
        error_code=safe_output.get("error_code", ""),
        error_message=safe_output.get("error_message", ""),
        latency_ms=latency_ms,
        created_at=now_fn() if now_fn else "",
    )
    session.add(run)
    session.flush()
    return run


def verify_alignment(
    session: Any,
    run_model: Any,
    input_data: dict[str, Any],
    *,
    provider_name: str = alignment_providers.MOCK_PROVIDER_NAME,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    commit: bool = True,
) -> tuple[Any, dict[str, Any]]:
    del audit_context
    started = time.perf_counter()
    normalized_input = validate_alignment_verification_input(input_data)
    try:
        provider = alignment_providers.get_alignment_provider(provider_name)
        output = provider.verify_alignment(normalized_input)
    except alignment_providers.AlignmentProviderError as exc:
        raise AlignmentVerificationProviderError(str(exc)) from exc
    output["risk_labels"] = _merge_labels(normalized_input.get("risk_labels", []), output.get("risk_labels", []))
    output["can_auto_approve"] = False
    if output.get("provider_type") in {"mock", "fake_llm", "external_llm", "replay_llm"}:
        output["is_production_result"] = False
        output["verification_status"] = _verification_status(output)
    latency_ms = int((time.perf_counter() - started) * 1000)
    run = create_alignment_verification_run(
        session,
        run_model,
        normalized_input,
        output,
        card_uid=normalized_input.get("card_uid", ""),
        latency_ms=latency_ms,
        now_fn=now_fn,
        commit=commit,
    )
    return run, output


def verify_concept_card(
    session: Any,
    card_model: Any,
    run_model: Any,
    card_uid: str,
    *,
    provider_name: str = alignment_providers.MOCK_PROVIDER_NAME,
    provider_options: dict[str, Any] | None = None,
    audit_context: dict[str, Any] | None = None,
    now_fn=None,
    commit: bool = True,
) -> tuple[Any, dict[str, Any], Any]:
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    input_data = build_alignment_verification_input_from_card(card)
    if provider_options:
        input_data["provider_options"] = provider_options
    run, output = verify_alignment(
        session,
        run_model,
        input_data,
        provider_name=provider_name,
        audit_context=audit_context,
        now_fn=now_fn,
        commit=commit,
    )
    return run, output, card


def apply_verification_result_to_card(
    session: Any,
    card_model: Any,
    run: Any,
    *,
    mode: str = "attach_only",
    commit: bool = True,
) -> Any | None:
    if mode != "attach_only":
        raise AlignmentVerificationError("Only attach_only verification result application is supported.")
    card_uid = _text(getattr(run, "card_uid", ""))
    if not card_uid:
        return None
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    existing_labels = _loads_json(getattr(card, "risk_labels", "[]"), [])
    run_labels = _loads_json(getattr(run, "risk_labels", "[]"), [])
    extra_labels = ["alignment_verification_attached"]
    if getattr(run, "provider_type", "") == "mock":
        extra_labels.append("alignment_verification_mock_only")
    if getattr(run, "provider_type", "") == "fake_llm":
        extra_labels.append("alignment_verification_fake_only")
    if getattr(run, "provider_type", "") == "external_llm":
        extra_labels.append("alignment_verification_external_llm")
    if getattr(run, "provider_type", "") == "replay_llm":
        extra_labels.append("alignment_verification_replay_only")
    merged = _merge_labels(existing_labels, run_labels, extra_labels)
    card.risk_labels = _dumps_json(merged)
    if getattr(card, "status", "") == "draft":
        card.status = "needs_review"
    # Never write mock or verification confidence into ConceptAlignmentCard.confidence_score.
    if commit:
        session.commit()
    else:
        session.flush()
    return card


@dataclass(frozen=True)
class ProtectedVerificationAttachResult:
    outcome: str
    card: Any | None


def apply_verification_result_to_card_protected(
    session: Any,
    card_model: Any,
    run: Any,
    *,
    mode: str = "attach_only",
    now_fn=None,
) -> ProtectedVerificationAttachResult:
    """Attach through an approved-card conditional update without owning commit."""

    if mode != "attach_only":
        raise AlignmentVerificationError("Only attach_only verification result application is supported.")
    card_uid = _text(getattr(run, "card_uid", ""))
    if not card_uid:
        return ProtectedVerificationAttachResult(outcome="missing_card", card=None)
    session.expire_all()
    card = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    if _text(getattr(card, "status", "")) == "approved":
        return ProtectedVerificationAttachResult(outcome="approved_protected", card=card)
    existing_labels = _loads_json(getattr(card, "risk_labels", "[]"), [])
    run_labels = _loads_json(getattr(run, "risk_labels", "[]"), [])
    extra_labels = ["alignment_verification_attached"]
    provider_type = getattr(run, "provider_type", "")
    if provider_type == "mock":
        extra_labels.append("alignment_verification_mock_only")
    if provider_type == "fake_llm":
        extra_labels.append("alignment_verification_fake_only")
    if provider_type == "external_llm":
        extra_labels.append("alignment_verification_external_llm")
    if provider_type == "replay_llm":
        extra_labels.append("alignment_verification_replay_only")
    values = {"risk_labels": _dumps_json(_merge_labels(existing_labels, run_labels, extra_labels))}
    if getattr(card, "status", "") == "draft":
        values["status"] = "needs_review"
    if now_fn is not None:
        values["updated_at"] = now_fn()
    affected = (
        session.query(card_model)
        .filter(card_model.card_uid == card_uid, card_model.status != "approved")
        .update(values, synchronize_session=False)
    )
    session.flush()
    session.expire_all()
    persisted = concept_alignment_cards.get_concept_card(session, card_model, card_uid)
    if affected != 1:
        outcome = "approved_protected" if persisted.status == "approved" else "conflict"
        return ProtectedVerificationAttachResult(outcome=outcome, card=persisted)
    return ProtectedVerificationAttachResult(outcome="attached", card=persisted)


def serialize_alignment_verification_run(run: Any) -> dict[str, Any]:
    output_payload = _loads_json(getattr(run, "output_payload", "{}"), {})
    return {
        "id": getattr(run, "id", None),
        "run_uid": getattr(run, "run_uid", ""),
        "card_uid": getattr(run, "card_uid", ""),
        "english_term": getattr(run, "english_term", ""),
        "chinese_term": getattr(run, "chinese_term", ""),
        "course": getattr(run, "course", ""),
        "chapter": getattr(run, "chapter", ""),
        "provider_name": getattr(run, "provider_name", ""),
        "provider_type": getattr(run, "provider_type", ""),
        "provider_version": getattr(run, "provider_version", ""),
        "input_payload": _loads_json(getattr(run, "input_payload", "{}"), {}),
        "output_payload": output_payload,
        "english_evidence_count": getattr(run, "english_evidence_count", 0),
        "chinese_evidence_count": getattr(run, "chinese_evidence_count", 0),
        "top_english_chunk_uids": _loads_json(getattr(run, "top_english_chunk_uids", "[]"), []),
        "top_chinese_chunk_uids": _loads_json(getattr(run, "top_chinese_chunk_uids", "[]"), []),
        "retrieval_score_summary": _loads_json(getattr(run, "retrieval_score_summary", "{}"), {}),
        "candidate_score_summary": _loads_json(getattr(run, "candidate_score_summary", "{}"), {}),
        "alignment_confidence": getattr(run, "alignment_confidence", None),
        "verification_status": getattr(run, "verification_status", ""),
        "alignment_decision": output_payload.get("alignment_decision", ""),
        "explanation": output_payload.get("explanation", ""),
        "recommendation": getattr(run, "recommendation", ""),
        "risk_labels": _loads_json(getattr(run, "risk_labels", "[]"), []),
        "prompt_version": getattr(run, "prompt_version", ""),
        "prompt_summary": _loads_json(getattr(run, "prompt_summary", "{}"), {}),
        "raw_output_summary": _loads_json(getattr(run, "raw_output_summary", "{}"), {}),
        "parser_version": getattr(run, "parser_version", ""),
        "output_schema_version": getattr(run, "output_schema_version", ""),
        "provider_response_status": getattr(run, "provider_response_status", ""),
        "estimated_cost": output_payload.get("estimated_cost", {}),
        "retry_count": output_payload.get("retry_count", 0),
        "error_code": getattr(run, "error_code", ""),
        "error_message": getattr(run, "error_message", ""),
        "latency_ms": getattr(run, "latency_ms", None),
        "created_at": getattr(run, "created_at", ""),
    }
