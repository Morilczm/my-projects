"""Alignment verification provider abstractions.

Only non-production providers are registered in this repository. The fake LLM
provider simulates raw JSON responses for parser and failure-path tests without
calling external APIs.
"""

from __future__ import annotations

import json
from typing import Any

from services import alignment_output_parser
from services import alignment_prompting
from services import llm_provider_config
from services import llm_transport
from services import parse_quality_risk


MOCK_PROVIDER_NAME = "mock-rule-v1"
MOCK_PROVIDER_VERSION = "v1"
FAKE_LLM_PROVIDER_NAME = "fake-llm-v1"
FAKE_LLM_PROVIDER_VERSION = "v1"
DISABLED_EXTERNAL_PROVIDER_NAME = llm_provider_config.DISABLED_EXTERNAL_PROVIDER_NAME
DEEPSEEK_EXTERNAL_PROVIDER_NAME = llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
REPLAY_EXTERNAL_PROVIDER_NAME = llm_provider_config.REPLAY_EXTERNAL_PROVIDER_NAME
EXTERNAL_PROVIDER_VERSION = "v1"
LOW_EVIDENCE_SCORE_THRESHOLD = 0.35
CLOSE_CANDIDATE_SCORE_DELTA = 0.08

PARSER_ERROR_CODE_MAP = {
    "provider_output_not_json": "provider_non_json_output",
    "missing_alignment_output_fields": "provider_schema_invalid",
    "invalid_alignment_output_schema": "provider_schema_invalid",
    "invalid_alignment_output_provenance": "provider_schema_invalid",
    "invalid_alignment_confidence": "provider_confidence_out_of_range",
}


class AlignmentProviderError(ValueError):
    """Raised when an alignment verification provider cannot run."""


class BaseAlignmentProvider:
    """Base interface for alignment verification providers."""

    provider_name = ""
    provider_type = ""
    provider_version = ""
    is_production_provider = False
    supports_external_calls = False

    def verify_alignment(self, input_data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


def _text(value: Any) -> str:
    return str(value or "").strip()


def _labels(value: Any) -> list[str]:
    return parse_quality_risk.normalize_labels(value)


def _merge_labels(*groups: Any) -> list[str]:
    merged: list[str] = []
    for labels in groups:
        merged = parse_quality_risk.merge_risk_labels(merged, labels)
    return merged


def _score(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _evidence_list(input_data: dict[str, Any], field: str) -> list[dict[str, Any]]:
    values = input_data.get(field) or []
    return values if isinstance(values, list) else []


def _candidate_list(input_data: dict[str, Any]) -> list[dict[str, Any]]:
    values = input_data.get("chinese_term_candidates") or []
    return values if isinstance(values, list) else []


def _evidence_provenance(input_data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for language, field in (
        ("english", "english_evidence"),
        ("chinese", "chinese_evidence"),
    ):
        result[language] = [
            {
                "source_uid": _text(item.get("source_uid")),
                "chunk_uid": _text(item.get("chunk_uid")),
            }
            for item in _evidence_list(input_data, field)
            if _text(item.get("source_uid")) and _text(item.get("chunk_uid"))
        ]
    return result


def _allowed_evidence_provenance(
    input_data: dict[str, Any],
) -> dict[str, set[tuple[str, str]]]:
    values = _evidence_provenance(input_data)
    return {
        language: {
            (_text(item.get("source_uid")), _text(item.get("chunk_uid")))
            for item in items
        }
        for language, items in values.items()
    }


def _has_review_evidence(evidence: list[dict[str, Any]]) -> bool:
    for item in evidence:
        status = _text(item.get("status"))
        quality_status = _text(item.get("quality_status"))
        risk_labels = set(_labels(item.get("risk_labels", [])))
        quality_flags = set(_labels(item.get("quality_flags", [])))
        if (
            status == "needs_review"
            or quality_status in {"partial_text", "mixed_quality", "ocr_low_confidence"}
            or bool(quality_flags & {"partial_text", "mixed_quality", "ocr_low_confidence"})
            or "needs_review_evidence" in risk_labels
        ):
            return True
    return False


def _has_partial_text(evidence: list[dict[str, Any]]) -> bool:
    for item in evidence:
        quality_status = _text(item.get("quality_status"))
        risk_labels = set(_labels(item.get("risk_labels", [])))
        quality_flags = set(_labels(item.get("quality_flags", [])))
        if quality_status == "partial_text" or "partial_text" in quality_flags or "input_partial_text" in risk_labels:
            return True
    return False


def _has_low_trust(evidence: list[dict[str, Any]]) -> bool:
    return any(_text(item.get("trust_level")) in {"low_quality", "unknown", "student_uploaded"} for item in evidence)


def _has_course_mismatch(evidence: list[dict[str, Any]], course: str, chapter: str) -> bool:
    for item in evidence:
        item_course = _text(item.get("course"))
        item_chapter = _text(item.get("chapter"))
        if course and item_course and item_course != course:
            return True
        if chapter and item_chapter and item_chapter != chapter:
            return True
    return False


def _ambiguous_candidates(input_data: dict[str, Any]) -> bool:
    candidates = _candidate_list(input_data)
    if len(candidates) < 2:
        return False
    top = sorted((_score(item.get("score")) for item in candidates), reverse=True)
    return top[0] - top[1] <= CLOSE_CANDIDATE_SCORE_DELTA


class MockAlignmentProvider(BaseAlignmentProvider):
    """Deterministic rule provider for schema and workflow testing only."""

    provider_name = MOCK_PROVIDER_NAME
    provider_type = "mock"
    provider_version = MOCK_PROVIDER_VERSION
    is_production_provider = False
    supports_external_calls = False

    def verify_alignment(self, input_data: dict[str, Any]) -> dict[str, Any]:
        english_term = _text(input_data.get("english_term"))
        chinese_term = _text(input_data.get("chinese_term"))
        course = _text(input_data.get("course"))
        chapter = _text(input_data.get("chapter"))
        english_evidence = _evidence_list(input_data, "english_evidence")
        chinese_evidence = _evidence_list(input_data, "chinese_evidence")

        risk_labels = _merge_labels(input_data.get("risk_labels", []))
        if not chinese_term:
            risk_labels = _merge_labels(risk_labels, ["missing_chinese_term"])
        if not english_evidence:
            risk_labels = _merge_labels(risk_labels, ["no_english_evidence"])
        if not chinese_evidence:
            risk_labels = _merge_labels(risk_labels, ["no_chinese_evidence"])
        if _ambiguous_candidates(input_data):
            risk_labels = _merge_labels(risk_labels, ["ambiguous_chinese_candidates"])
        all_evidence = [*english_evidence, *chinese_evidence]
        if _has_partial_text(all_evidence):
            risk_labels = _merge_labels(risk_labels, ["evidence_from_partial_text"])
        if _has_review_evidence(all_evidence):
            risk_labels = _merge_labels(risk_labels, ["evidence_from_needs_review_source"])
        if _has_low_trust(all_evidence):
            risk_labels = _merge_labels(risk_labels, ["evidence_from_low_trust_source"])
        if _has_course_mismatch(all_evidence, course, chapter):
            risk_labels = _merge_labels(risk_labels, ["course_mismatch"])

        confidence = 0.2
        if english_term:
            confidence += 0.08
        if chinese_term:
            confidence += 0.10
        if english_evidence:
            confidence += 0.18
        if chinese_evidence:
            confidence += 0.18
        if english_evidence and chinese_evidence and chinese_term:
            confidence += 0.10
        if "ambiguous_chinese_candidates" in risk_labels:
            confidence -= 0.12
        if "course_mismatch" in risk_labels:
            confidence -= 0.10
        if "evidence_from_partial_text" in risk_labels:
            confidence -= 0.08
        if "evidence_from_low_trust_source" in risk_labels:
            confidence -= 0.08
        if "no_english_evidence" in risk_labels or "no_chinese_evidence" in risk_labels:
            confidence = min(confidence, 0.42)
        if "missing_chinese_term" in risk_labels:
            confidence = min(confidence, 0.35)
        confidence = round(max(0.0, min(confidence, 0.78)), 4)

        if "no_english_evidence" in risk_labels or "no_chinese_evidence" in risk_labels:
            recommendation = "insufficient_evidence"
        elif "missing_chinese_term" in risk_labels:
            recommendation = "needs_review"
        elif "ambiguous_chinese_candidates" in risk_labels:
            recommendation = "candidate_ambiguous"
        elif "course_mismatch" in risk_labels:
            recommendation = "needs_review"
        else:
            recommendation = "ready_for_human_review"

        return {
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "provider_version": self.provider_version,
            "alignment_confidence": confidence,
            "recommendation": recommendation,
            "risk_labels": risk_labels,
            "evidence_assessment": {
                "english_evidence_count": len(english_evidence),
                "chinese_evidence_count": len(chinese_evidence),
                "english_evidence_present": bool(english_evidence),
                "chinese_evidence_present": bool(chinese_evidence),
                "uses_mock_rules": True,
            },
            "term_assessment": {
                "english_term_present": bool(english_term),
                "chinese_term_present": bool(chinese_term),
                "candidate_count": len(_candidate_list(input_data)),
            },
            "course_context_assessment": {
                "course": course,
                "chapter": chapter,
                "course_mismatch": "course_mismatch" in risk_labels,
            },
            "explanation": (
                "Mock rule-based alignment verification for schema, API, and audit testing only. "
                "This is not a production LLM judgment and must not auto-approve a Concept Card."
            ),
            "limitations": [
                "mock_provider_only",
                "no_real_llm_called",
                "no_semantic_alignment_judgment",
                "requires_teacher_or_future_provider_review",
            ],
            "is_production_result": False,
            "can_auto_approve": False,
            "verification_status": "mock_only",
        }


class FakeLLMAlignmentProvider(BaseAlignmentProvider):
    """Fake LLM provider for prompt, parser, and failure-path tests only."""

    provider_name = FAKE_LLM_PROVIDER_NAME
    provider_type = "fake_llm"
    provider_version = FAKE_LLM_PROVIDER_VERSION
    is_production_provider = False
    supports_external_calls = False

    def verify_alignment(self, input_data: dict[str, Any]) -> dict[str, Any]:
        provider_options = input_data.get("provider_options") if isinstance(input_data.get("provider_options"), dict) else {}
        prompt_version = (
            _text(provider_options.get("prompt_version"))
            or alignment_prompting.PROMPT_VERSION
        )
        fake_response_type = _text(provider_options.get("fake_response_type")) or "valid"
        try:
            prompt = alignment_prompting.build_alignment_prompt(input_data, prompt_version=prompt_version)
        except alignment_prompting.AlignmentPromptError as exc:
            return self._failed_output(
                "alignment_prompt_error",
                str(exc),
                prompt_version=prompt_version,
                raw_output="",
            )

        raw_output = self._build_raw_output(fake_response_type, input_data)
        raw_output_summary = self._raw_output_summary(raw_output)
        prompt_summary = self._prompt_summary(prompt, input_data, prompt_version)
        try:
            parsed = alignment_output_parser.parse_alignment_provider_output(raw_output)
        except alignment_output_parser.AlignmentOutputParserError as exc:
            failed = self._failed_output(
                exc.error_code,
                str(exc),
                prompt_version=prompt_version,
                raw_output=raw_output,
                prompt_summary=prompt_summary,
                raw_output_summary=raw_output_summary,
            )
            return failed

        parsed.update({
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "provider_version": self.provider_version,
            "prompt_version": prompt_version,
            "prompt_summary": prompt_summary,
            "raw_output_summary": raw_output_summary,
            "parser_version": (
                alignment_output_parser.STRUCTURED_PARSER_VERSION
                if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION
                else alignment_output_parser.PARSER_VERSION
            ),
            "output_schema_version": (
                alignment_output_parser.STRUCTURED_OUTPUT_SCHEMA_VERSION
                if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION
                else alignment_output_parser.OUTPUT_SCHEMA_VERSION
            ),
            "provider_response_status": "parsed",
            "verification_status": "needs_review",
            "is_production_result": False,
            "can_auto_approve": False,
        })
        return parsed

    def _prompt_summary(self, prompt: str, input_data: dict[str, Any], prompt_version: str) -> dict[str, Any]:
        return {
            "prompt_version": prompt_version,
            "prompt_chars": len(prompt),
            "english_evidence_count": len(_evidence_list(input_data, "english_evidence")),
            "chinese_evidence_count": len(_evidence_list(input_data, "chinese_evidence")),
            "stores_full_prompt": False,
        }

    def _raw_output_summary(self, raw_output: str) -> dict[str, Any]:
        text = _text(raw_output)
        preview = f"{text[:240]}..." if len(text) > 240 else "[omitted_short_provider_output]"
        return {
            "raw_output_chars": len(text),
            "raw_output_preview": preview,
            "truncated": len(text) > 240,
            "stores_full_raw_output": False,
        }

    def _failed_output(
        self,
        error_code: str,
        error_message: str,
        *,
        prompt_version: str,
        raw_output: str,
        prompt_summary: dict[str, Any] | None = None,
        raw_output_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        failed = alignment_output_parser.build_failed_alignment_output(error_code, error_message)
        failed.update({
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "provider_version": self.provider_version,
            "prompt_version": prompt_version,
            "prompt_summary": prompt_summary or {
                "prompt_version": prompt_version,
                "stores_full_prompt": False,
            },
            "raw_output_summary": raw_output_summary or self._raw_output_summary(raw_output),
            "parser_version": (
                alignment_output_parser.STRUCTURED_PARSER_VERSION
                if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION
                else alignment_output_parser.PARSER_VERSION
            ),
            "output_schema_version": (
                alignment_output_parser.STRUCTURED_OUTPUT_SCHEMA_VERSION
                if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION
                else alignment_output_parser.OUTPUT_SCHEMA_VERSION
            ),
            "provider_response_status": "parse_failed",
            "is_production_result": False,
            "can_auto_approve": False,
        })
        return failed

    def _base_response(self, input_data: dict[str, Any]) -> dict[str, Any]:
        risk_labels = _merge_labels(
            input_data.get("risk_labels", []),
            ["bilingual_alignment_not_verified", "candidate_not_alignment_verified"],
        )
        english_evidence = _evidence_list(input_data, "english_evidence")
        chinese_evidence = _evidence_list(input_data, "chinese_evidence")
        return {
            "alignment_decision": "likely_aligned",
            "alignment_confidence": 0.72,
            "recommendation": "ready_for_human_review",
            "risk_labels": risk_labels,
            "evidence_assessment": {
                "english_evidence_supported": bool(english_evidence),
                "chinese_evidence_supported": bool(chinese_evidence),
                "cross_language_support": "moderate" if english_evidence and chinese_evidence else "missing",
                "evidence_limitations": [
                    "fake_llm_fixture_only",
                    "not_a_production_llm_judgment",
                ],
            },
            "term_assessment": {
                "english_term_ok": bool(_text(input_data.get("english_term"))),
                "chinese_term_ok": bool(_text(input_data.get("chinese_term"))),
                "candidate_ambiguity": "none",
                "notes": "Fake fixture response for parser and safety gate tests.",
            },
            "course_context_assessment": {
                "course_match": True,
                "chapter_match": True,
                "notes": "Course and chapter are treated as fixture-matched unless a failure fixture is selected.",
            },
            "explanation": (
                "Fake LLM-style JSON response for validating schema, parser, audit, and safety gates. "
                "This is not a production model judgment."
            ),
            "limitations": [
                "fake_provider_only",
                "no_external_model_called",
                "requires_human_review",
            ],
            "evidence_citations": _evidence_provenance(input_data),
            "auto_approve": True,
        }

    def _build_raw_output(self, fake_response_type: str, input_data: dict[str, Any]) -> str:
        if fake_response_type == "non_json":
            return "This is not JSON and must fail parser validation."
        response = self._base_response(input_data)
        if fake_response_type == "missing_fields":
            response.pop("recommendation", None)
        elif fake_response_type == "confidence_out_of_range":
            response["alignment_confidence"] = 1.4
        elif fake_response_type == "insufficient_evidence":
            response.update({
                "alignment_decision": "insufficient_evidence",
                "alignment_confidence": 0.24,
                "recommendation": "insufficient_evidence",
                "risk_labels": _merge_labels(response.get("risk_labels", []), ["no_english_evidence", "no_chinese_evidence"]),
            })
            response["evidence_assessment"]["english_evidence_supported"] = False
            response["evidence_assessment"]["chinese_evidence_supported"] = False
            response["evidence_assessment"]["cross_language_support"] = "missing"
            response["evidence_assessment"]["evidence_limitations"].append("insufficient_evidence_fixture")
        elif fake_response_type == "ambiguous_candidate":
            response.update({
                "alignment_decision": "uncertain",
                "alignment_confidence": 0.45,
                "recommendation": "candidate_ambiguous",
                "risk_labels": _merge_labels(response.get("risk_labels", []), ["ambiguous_chinese_candidates"]),
            })
            response["term_assessment"]["candidate_ambiguity"] = "high"
            response["term_assessment"]["notes"] = "Multiple Chinese candidates are close in fake fixture score."
        elif fake_response_type != "valid":
            response.update({
                "alignment_decision": "uncertain",
                "alignment_confidence": 0.4,
                "recommendation": "needs_review",
                "risk_labels": _merge_labels(response.get("risk_labels", []), ["unknown_fake_response_type"]),
            })
        return json.dumps(response, ensure_ascii=False, sort_keys=True)


class GuardedLLMAlignmentProvider(BaseAlignmentProvider):
    """Guarded external provider adapter with explicit transport gates."""

    provider_name = DISABLED_EXTERNAL_PROVIDER_NAME
    provider_type = "external_llm"
    provider_version = EXTERNAL_PROVIDER_VERSION
    is_production_provider = True
    supports_external_calls = True

    def __init__(self, provider_name: str = DISABLED_EXTERNAL_PROVIDER_NAME, transport: llm_transport.BaseLLMTransport | None = None):
        self.provider_name = provider_name
        self.config = llm_provider_config.get_llm_provider_config(provider_name)
        self.provider_type = self.config.get("provider_type", "external_llm")
        self.is_production_provider = self.provider_type == "external_llm"
        self.supports_external_calls = self.provider_type == "external_llm"
        if transport is not None:
            self.transport = transport
        elif self.config.get("replay_mode"):
            self.transport = llm_transport.ReplayLLMTransport()
        elif self.provider_name == DEEPSEEK_EXTERNAL_PROVIDER_NAME and self.config.get("executable"):
            self.transport = llm_transport.DeepSeekHTTPTransport()
        else:
            self.transport = llm_transport.DisabledLLMTransport()

    def verify_alignment(self, input_data: dict[str, Any]) -> dict[str, Any]:
        provider_options = input_data.get("provider_options") if isinstance(input_data.get("provider_options"), dict) else {}
        prompt_version = (
            alignment_prompting.STRUCTURED_PROMPT_VERSION
            if self.provider_name == DEEPSEEK_EXTERNAL_PROVIDER_NAME
            else _text(provider_options.get("prompt_version"))
            or alignment_prompting.PROMPT_VERSION
        )
        config = self._config_with_safe_options(provider_options)
        try:
            prompt = alignment_prompting.build_alignment_prompt(input_data, prompt_version=prompt_version)
        except alignment_prompting.AlignmentPromptError as exc:
            return self._failed_output(
                "alignment_prompt_error",
                str(exc),
                prompt_version=prompt_version,
                prompt_summary={"prompt_version": prompt_version, "stores_full_prompt": False},
            )

        prompt_truncated = False
        max_prompt_chars = int(config.get("max_prompt_chars") or llm_provider_config.DEFAULT_MAX_PROMPT_CHARS)
        if len(prompt) > max_prompt_chars:
            prompt = prompt[:max_prompt_chars]
            prompt_truncated = True
        prompt_summary = self._prompt_summary(prompt, input_data, prompt_version, prompt_truncated)
        estimated_cost = llm_provider_config.estimate_alignment_call_cost(
            {"prompt_chars": len(prompt), "expected_output_chars": config.get("max_output_chars")},
            self.provider_name,
            config=config,
        )
        if (
            self.provider_name == DEEPSEEK_EXTERNAL_PROVIDER_NAME
            and not estimated_cost.get("pricing_available")
        ):
            return self._failed_output(
                "provider_pricing_unavailable",
                "Provider pricing is unavailable for the fixed model identity.",
                prompt_version=prompt_version,
                prompt_summary=prompt_summary,
                estimated_cost=estimated_cost,
            )
        if estimated_cost.get("exceeds_limit"):
            return self._failed_output(
                "provider_cost_limit_exceeded",
                "Estimated alignment provider cost exceeds configured limit.",
                prompt_version=prompt_version,
                prompt_summary=prompt_summary,
                estimated_cost=estimated_cost,
            )

        if not config.get("replay_mode"):
            try:
                llm_provider_config.require_external_llm_enabled(self.provider_name, config=config)
            except llm_provider_config.LLMProviderConfigError as exc:
                return self._failed_output(
                    exc.error_code,
                    str(exc),
                    prompt_version=prompt_version,
                    prompt_summary=prompt_summary,
                    estimated_cost=estimated_cost,
                )

        transport_result = self.transport.generate(
            prompt,
            llm_provider_config.sanitize_provider_config(config),
            {
                "replay_response_type": _text(provider_options.get("replay_response_type")) or "valid",
                "fake_response_type": _text(provider_options.get("fake_response_type")) or "valid",
                "evidence_citations": _evidence_provenance(input_data),
            },
        )
        if transport_result.status != "success":
            return self._failed_output(
                transport_result.error_code or "provider_bad_response",
                transport_result.error_message or "Alignment provider transport failed.",
                prompt_version=prompt_version,
                prompt_summary=prompt_summary,
                raw_output=transport_result.raw_output,
                estimated_cost=estimated_cost,
                retry_count=transport_result.retry_count,
                latency_ms=transport_result.latency_ms,
            )

        raw_output = transport_result.raw_output or ""
        raw_output_summary = self._raw_output_summary(
            raw_output,
            finish_reason=transport_result.metadata.get("finish_reason", ""),
            response_model=transport_result.metadata.get("resolved_model", ""),
            validation_stage="content_received",
        )
        max_output_chars = int(config.get("max_output_chars") or llm_provider_config.DEFAULT_MAX_OUTPUT_CHARS)
        if len(raw_output) > max_output_chars:
            return self._failed_output(
                "provider_output_too_long",
                "Alignment provider output exceeded configured max_output_chars.",
                prompt_version=prompt_version,
                prompt_summary=prompt_summary,
                raw_output=raw_output,
                raw_output_summary=raw_output_summary,
                estimated_cost=estimated_cost,
                retry_count=transport_result.retry_count,
                latency_ms=transport_result.latency_ms,
            )
        try:
            if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION:
                parsed = alignment_output_parser.parse_structured_alignment_provider_output(
                    raw_output,
                    allowed_provenance=_allowed_evidence_provenance(input_data),
                )
            else:
                parsed = alignment_output_parser.parse_alignment_provider_output(
                    raw_output
                )
        except alignment_output_parser.AlignmentOutputParserError as exc:
            raw_output_summary = self._raw_output_summary(
                raw_output,
                finish_reason=transport_result.metadata.get("finish_reason", ""),
                response_model=transport_result.metadata.get("resolved_model", ""),
                validation_stage="schema_validation",
                parser_reason=PARSER_ERROR_CODE_MAP.get(
                    exc.error_code, "provider_bad_response"
                ),
            )
            return self._failed_output(
                PARSER_ERROR_CODE_MAP.get(exc.error_code, "provider_bad_response"),
                str(exc),
                prompt_version=prompt_version,
                prompt_summary=prompt_summary,
                raw_output=raw_output,
                raw_output_summary=raw_output_summary,
                estimated_cost=estimated_cost,
                retry_count=transport_result.retry_count,
                latency_ms=transport_result.latency_ms,
            )
        raw_output_summary = self._raw_output_summary(
            raw_output,
            finish_reason=transport_result.metadata.get("finish_reason", ""),
            response_model=transport_result.metadata.get("resolved_model", ""),
            validation_stage="validated",
            parser_reason="",
        )

        provider_response_status = "replayed" if config.get("replay_mode") else "parsed"
        risk_labels = _merge_labels(parsed.get("risk_labels", []))
        if prompt_truncated:
            risk_labels = _merge_labels(risk_labels, ["prompt_truncated"])
        parsed.update({
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "provider_version": self.provider_version,
            "prompt_version": prompt_version,
            "prompt_summary": prompt_summary,
            "raw_output_summary": raw_output_summary,
            "parser_version": (
                alignment_output_parser.STRUCTURED_PARSER_VERSION
                if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION
                else alignment_output_parser.PARSER_VERSION
            ),
            "output_schema_version": (
                alignment_output_parser.STRUCTURED_OUTPUT_SCHEMA_VERSION
                if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION
                else alignment_output_parser.OUTPUT_SCHEMA_VERSION
            ),
            "provider_response_status": provider_response_status,
            "estimated_cost": estimated_cost,
            "retry_count": transport_result.retry_count,
            "verification_status": "needs_review",
            "risk_labels": risk_labels,
            "is_production_result": False,
            "can_auto_approve": False,
        })
        return parsed

    def _config_with_safe_options(self, provider_options: dict[str, Any]) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        for key in {"timeout_seconds", "max_retries", "max_prompt_chars", "max_output_chars"}:
            if provider_options.get(key) not in ("", None):
                overrides[key] = provider_options.get(key)
        if provider_options.get("max_estimated_cost") not in ("", None):
            overrides["max_estimated_cost"] = provider_options.get("max_estimated_cost")
        return llm_provider_config.get_llm_provider_config(self.provider_name, overrides=overrides)

    def _prompt_summary(
        self,
        prompt: str,
        input_data: dict[str, Any],
        prompt_version: str,
        prompt_truncated: bool,
    ) -> dict[str, Any]:
        return {
            "prompt_version": prompt_version,
            "prompt_chars": len(prompt),
            "english_evidence_count": len(_evidence_list(input_data, "english_evidence")),
            "chinese_evidence_count": len(_evidence_list(input_data, "chinese_evidence")),
            "prompt_truncated": prompt_truncated,
            "stores_full_prompt": False,
        }

    def _raw_output_summary(
        self,
        raw_output: str,
        *,
        finish_reason: str = "",
        response_model: str = "",
        validation_stage: str = "",
        parser_reason: str = "",
    ) -> dict[str, Any]:
        diagnostics = alignment_output_parser.build_sanitized_output_diagnostics(
            raw_output,
            finish_reason=finish_reason,
            response_model=response_model,
            validation_stage=validation_stage,
            parser_reason=parser_reason,
        )
        diagnostics.update({
            "raw_output_chars": len(raw_output or ""),
            "truncated": False,
        })
        return diagnostics

    def _failed_output(
        self,
        error_code: str,
        error_message: str,
        *,
        prompt_version: str,
        prompt_summary: dict[str, Any],
        raw_output: str = "",
        raw_output_summary: dict[str, Any] | None = None,
        estimated_cost: dict[str, Any] | None = None,
        retry_count: int = 0,
        latency_ms: int = 0,
    ) -> dict[str, Any]:
        failed = alignment_output_parser.build_failed_alignment_output(error_code, error_message)
        failed.update({
            "provider_name": self.provider_name,
            "provider_type": self.provider_type,
            "provider_version": self.provider_version,
            "prompt_version": prompt_version,
            "prompt_summary": prompt_summary,
            "raw_output_summary": raw_output_summary or self._raw_output_summary(raw_output),
            "parser_version": (
                alignment_output_parser.STRUCTURED_PARSER_VERSION
                if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION
                else alignment_output_parser.PARSER_VERSION
            ),
            "output_schema_version": (
                alignment_output_parser.STRUCTURED_OUTPUT_SCHEMA_VERSION
                if prompt_version == alignment_prompting.STRUCTURED_PROMPT_VERSION
                else alignment_output_parser.OUTPUT_SCHEMA_VERSION
            ),
            "provider_response_status": error_code,
            "estimated_cost": estimated_cost or {},
            "retry_count": retry_count,
            "transport_latency_ms": latency_ms,
            "risk_labels": _merge_labels([error_code], failed.get("risk_labels", [])),
            "is_production_result": False,
            "can_auto_approve": False,
        })
        return failed


def get_alignment_provider(provider_name: str | None = None):
    provider = _text(provider_name) or MOCK_PROVIDER_NAME
    if provider == MOCK_PROVIDER_NAME:
        return MockAlignmentProvider()
    if provider == FAKE_LLM_PROVIDER_NAME:
        return FakeLLMAlignmentProvider()
    if provider in {DISABLED_EXTERNAL_PROVIDER_NAME, DEEPSEEK_EXTERNAL_PROVIDER_NAME, REPLAY_EXTERNAL_PROVIDER_NAME}:
        return GuardedLLMAlignmentProvider(provider)
    raise AlignmentProviderError(f"Unknown alignment verification provider: {provider}")


def list_alignment_providers() -> list[dict[str, Any]]:
    return [
        {
            "provider_name": MOCK_PROVIDER_NAME,
            "provider_type": "mock",
            "provider_version": MOCK_PROVIDER_VERSION,
            "is_production_provider": False,
            "supports_external_calls": False,
        },
        {
            "provider_name": FAKE_LLM_PROVIDER_NAME,
            "provider_type": "fake_llm",
            "provider_version": FAKE_LLM_PROVIDER_VERSION,
            "is_production_provider": False,
            "supports_external_calls": False,
        },
        {
            "provider_name": DISABLED_EXTERNAL_PROVIDER_NAME,
            "provider_type": "external_llm",
            "provider_version": EXTERNAL_PROVIDER_VERSION,
            "is_production_provider": True,
            "supports_external_calls": True,
            "enabled": False,
        },
        {
            "provider_name": DEEPSEEK_EXTERNAL_PROVIDER_NAME,
            "provider_type": "external_llm",
            "provider_version": EXTERNAL_PROVIDER_VERSION,
            "is_production_provider": True,
            "supports_external_calls": True,
            "enabled": llm_provider_config.get_llm_provider_config(DEEPSEEK_EXTERNAL_PROVIDER_NAME).get("enabled"),
            "feature_enabled": llm_provider_config.get_llm_provider_config(DEEPSEEK_EXTERNAL_PROVIDER_NAME).get("feature_enabled"),
            "executable": llm_provider_config.get_llm_provider_config(DEEPSEEK_EXTERNAL_PROVIDER_NAME).get("executable"),
        },
        {
            "provider_name": REPLAY_EXTERNAL_PROVIDER_NAME,
            "provider_type": "replay_llm",
            "provider_version": EXTERNAL_PROVIDER_VERSION,
            "is_production_provider": False,
            "supports_external_calls": False,
            "enabled": False,
            "replay_mode": True,
        },
    ]
