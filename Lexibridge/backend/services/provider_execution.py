"""Governed, bounded Provider execution with an injectable transport.

Task 12I-A qualifies only deterministic fake execution.  This module does not
load credentials, select a real transport, or make a network request.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from typing import Any

from services import alignment_output_parser, prompt_registry


POLICY_ID = "governed-provider-execution"
POLICY_VERSION = "1.0.0"
ACTIVE_READINESS_POLICY = "governed-provider-readiness@1.0.0"
ACTIVE_QUALIFICATION_POLICY = "governed-bilingual-evidence-qualification@1.1.0"

SUCCEEDED = "SUCCEEDED"
BLOCKED = "BLOCKED"
FAILED = "FAILED"
REUSED = "REUSED"

PROVIDER_EXECUTION_NOT_READY = "PROVIDER_EXECUTION_NOT_READY"
PROVIDER_EXECUTION_REVIEW_REQUIRED = "PROVIDER_EXECUTION_REVIEW_REQUIRED"
PROVIDER_EXECUTION_ADMISSION_DENIED = "PROVIDER_EXECUTION_ADMISSION_DENIED"
PROVIDER_EXECUTION_PROMPT_VERSION_INVALID = (
    "PROVIDER_EXECUTION_PROMPT_VERSION_INVALID"
)
PROVIDER_EXECUTION_PROVIDER_NOT_ALLOWED = "PROVIDER_EXECUTION_PROVIDER_NOT_ALLOWED"
PROVIDER_EXECUTION_BUDGET_EXCEEDED = "PROVIDER_EXECUTION_BUDGET_EXCEEDED"
PROVIDER_EXECUTION_PRIVACY_GATE_FAILED = "PROVIDER_EXECUTION_PRIVACY_GATE_FAILED"
PROVIDER_EXECUTION_IDEMPOTENCY_CONFLICT = (
    "PROVIDER_EXECUTION_IDEMPOTENCY_CONFLICT"
)
PROVIDER_EXECUTION_TIMEOUT = "PROVIDER_EXECUTION_TIMEOUT"
PROVIDER_EXECUTION_RETRY_EXHAUSTED = "PROVIDER_EXECUTION_RETRY_EXHAUSTED"
PROVIDER_EXECUTION_RESPONSE_INVALID = "PROVIDER_EXECUTION_RESPONSE_INVALID"
PROVIDER_EXECUTION_PARSE_FAILED = "PROVIDER_EXECUTION_PARSE_FAILED"
PROVIDER_EXECUTION_FAILED = "PROVIDER_EXECUTION_FAILED"

MAX_TERM_CHARS = 160
MAX_CONTEXT_CHARS = 800
MAX_EVIDENCE_REFS = 8
MAX_EVIDENCE_REF_CHARS = 240
MAX_TOKEN_CEILING = 32_000
MAX_COST_CEILING = 25.0
MAX_TIMEOUT_SECONDS = 120
MAX_RETRY_BUDGET = 3
ALLOWED_FAKE_PROVIDER = ("fake-llm-v1", "fake-llm-v1:v1")
APPROVED_PROMPTS = {
    ("term_alignment", "v1"),
    ("formal_alignment", "alignment-v1"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bounded(value: Any, limit: int) -> str:
    text = " ".join(_text(value).split())
    if not text:
        raise ValueError("bounded text is required.")
    if len(text) > limit:
        raise ValueError("bounded text exceeds execution contract.")
    return text


def _refs(values: Any) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("evidence references must be a collection.")
    refs = tuple(
        sorted(
            {
                _bounded(value, MAX_EVIDENCE_REF_CHARS)
                for value in (values or ())
                if _text(value)
            }
        )
    )
    if not refs or len(refs) > MAX_EVIDENCE_REFS:
        raise ValueError("bounded evidence provenance is required.")
    return refs


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProviderExecutionRequest:
    readiness_decision: str
    readiness_policy: str
    readiness_result_id: str
    qualification_decision: str
    qualification_policy: str
    qualification_result_id: str
    execution_admission: bool
    privacy_gate_passed: bool
    provenance_gate_passed: bool
    budget_gate_passed: bool
    provider_id: str
    model_id: str
    prompt_registry_id: str
    prompt_version: str
    english_term: str
    english_context: str
    english_evidence: tuple[str, ...]
    chinese_term: str
    chinese_context: str
    chinese_evidence: tuple[str, ...]
    request_token_ceiling: int
    cost_ceiling: float
    timeout_seconds: int
    retry_budget: int
    idempotency_key: str
    audit_correlation_id: str

    def __post_init__(self):
        for name, limit in (
            ("readiness_decision", 40),
            ("readiness_policy", 160),
            ("readiness_result_id", 160),
            ("qualification_decision", 40),
            ("qualification_policy", 160),
            ("qualification_result_id", 160),
            ("provider_id", 120),
            ("model_id", 160),
            ("prompt_registry_id", 80),
            ("prompt_version", 80),
            ("english_term", MAX_TERM_CHARS),
            ("english_context", MAX_CONTEXT_CHARS),
            ("chinese_term", MAX_TERM_CHARS),
            ("chinese_context", MAX_CONTEXT_CHARS),
            ("idempotency_key", 160),
            ("audit_correlation_id", 160),
        ):
            object.__setattr__(self, name, _bounded(getattr(self, name), limit))
        object.__setattr__(self, "english_evidence", _refs(self.english_evidence))
        object.__setattr__(self, "chinese_evidence", _refs(self.chinese_evidence))


@dataclass(frozen=True)
class ProviderExecutionResult:
    status: str
    provider_id: str
    model_id: str
    prompt_registry_id: str
    prompt_version: str
    qualification_result_id: str
    readiness_result_id: str
    idempotency_key_hash: str
    request_hash: str
    response_hash: str
    parse_status: str
    estimated_input_tokens: int
    fake_output_tokens: int
    estimated_cost: float
    retry_count: int
    request_count: int
    reason_codes: tuple[str, ...]
    audit_correlation_id: str
    english_provenance: tuple[str, ...]
    chinese_provenance: tuple[str, ...]
    execution_id: str
    created_by_policy: str = f"{POLICY_ID}@{POLICY_VERSION}"
    network_called: bool = False
    credential_value_read: bool = False
    real_provider_requests: int = 0


class FakeTransportTimeout(TimeoutError):
    pass


class FakeTransportRetryableError(RuntimeError):
    pass


class FakeTransportNonRetryableError(RuntimeError):
    pass


class DeterministicFakeProviderTransport:
    """Test transport that returns raw Provider-shaped output without I/O."""

    def __init__(self, mode: str = "valid"):
        self.mode = _text(mode) or "valid"
        self.call_count = 0
        self.network_calls = 0
        self.credential_reads = 0

    def execute(self, payload: dict[str, Any], *, timeout_seconds: int) -> str:
        self.call_count += 1
        if self.mode == "timeout":
            raise FakeTransportTimeout("deterministic fake timeout")
        if self.mode == "retryable_error":
            raise FakeTransportRetryableError("deterministic fake retryable error")
        if self.mode == "non_retryable_error":
            raise FakeTransportNonRetryableError("deterministic fake failure")
        if self.mode in {"malformed_json", "natural_language"}:
            return "not structured provider json"
        if payload["prompt_registry_id"] == "term_alignment":
            response = {
                "alignment_status": "accepted_translation",
                "candidate_chinese_term": payload["chinese_term"],
                "concept_explanation": "Fake bounded concept explanation.",
                "alignment_reason": "Fake deterministic evidence-bound alignment.",
                "ai_confidence": 0.8,
                "risk_flags": ["requires_human_review"],
                "requires_human_review": True,
            }
            if self.mode == "missing_fields":
                response.pop("alignment_reason")
            return json.dumps(response, ensure_ascii=False, sort_keys=True)
        response = {
            "alignment_decision": "likely_aligned",
            "alignment_confidence": 0.8,
            "recommendation": "needs_review",
            "risk_labels": ["requires_human_review"],
            "evidence_assessment": {
                "english_evidence_supported": True,
                "chinese_evidence_supported": True,
                "cross_language_support": "moderate",
                "evidence_limitations": [],
            },
            "term_assessment": {
                "english_term_ok": True,
                "chinese_term_ok": True,
                "candidate_ambiguity": "low",
            },
            "course_context_assessment": {
                "course_match": True,
                "chapter_match": True,
            },
            "explanation": "Fake deterministic alignment.",
            "limitations": [],
        }
        if self.mode == "missing_fields":
            response.pop("recommendation")
        return json.dumps(response, ensure_ascii=False, sort_keys=True)


class InMemoryExecutionLedger:
    def __init__(self):
        self._items: dict[str, tuple[str, ProviderExecutionResult]] = {}

    def get(self, key: str):
        return self._items.get(key)

    def store(
        self, key: str, request_hash: str, result: ProviderExecutionResult
    ) -> None:
        self._items[key] = (request_hash, result)


def _request_payload(value: ProviderExecutionRequest) -> dict[str, Any]:
    return {
        "provider_id": value.provider_id,
        "model_id": value.model_id,
        "prompt_registry_id": value.prompt_registry_id,
        "prompt_version": value.prompt_version,
        "english_term": value.english_term,
        "english_context": value.english_context,
        "english_evidence": list(value.english_evidence),
        "chinese_term": value.chinese_term,
        "chinese_context": value.chinese_context,
        "chinese_evidence": list(value.chinese_evidence),
        "qualification_result_id": value.qualification_result_id,
        "readiness_result_id": value.readiness_result_id,
        "readiness_policy": value.readiness_policy,
        "qualification_policy": value.qualification_policy,
        "request_token_ceiling": value.request_token_ceiling,
        "cost_ceiling": value.cost_ceiling,
        "timeout_seconds": value.timeout_seconds,
        "retry_budget": value.retry_budget,
        "idempotency_key_hash": _hash_text(value.idempotency_key),
        "audit_correlation_id": value.audit_correlation_id,
    }


def _estimated_tokens(payload: dict[str, Any]) -> int:
    bounded_content = " ".join(
        (
            payload["english_term"],
            payload["english_context"],
            payload["chinese_term"],
            payload["chinese_context"],
            *payload["english_evidence"],
            *payload["chinese_evidence"],
        )
    )
    return max(1, (len(bounded_content) + 3) // 4)


def _result(
    value: ProviderExecutionRequest,
    *,
    status: str,
    request_hash: str,
    response_hash: str = "",
    parse_status: str = "not_run",
    estimated_input_tokens: int = 0,
    fake_output_tokens: int = 0,
    retry_count: int = 0,
    request_count: int = 0,
    reason_codes: tuple[str, ...] = (),
) -> ProviderExecutionResult:
    identity = _hash_json(
        {
            "request_hash": request_hash,
            "response_hash": response_hash,
            "status": status,
            "reasons": reason_codes,
            "policy": f"{POLICY_ID}@{POLICY_VERSION}",
        }
    )
    return ProviderExecutionResult(
        status=status,
        provider_id=value.provider_id,
        model_id=value.model_id,
        prompt_registry_id=value.prompt_registry_id,
        prompt_version=value.prompt_version,
        qualification_result_id=value.qualification_result_id,
        readiness_result_id=value.readiness_result_id,
        idempotency_key_hash=_hash_text(value.idempotency_key),
        request_hash=request_hash,
        response_hash=response_hash,
        parse_status=parse_status,
        estimated_input_tokens=estimated_input_tokens,
        fake_output_tokens=fake_output_tokens,
        estimated_cost=0.0,
        retry_count=retry_count,
        request_count=request_count,
        reason_codes=tuple(sorted(set(reason_codes))),
        audit_correlation_id=value.audit_correlation_id,
        english_provenance=value.english_evidence,
        chinese_provenance=value.chinese_evidence,
        execution_id=f"provider-execution:{identity}",
    )


def _admission_reasons(value: ProviderExecutionRequest) -> tuple[str, ...]:
    reasons = []
    if value.readiness_decision == "REVIEW_REQUIRED":
        reasons.append(PROVIDER_EXECUTION_REVIEW_REQUIRED)
    elif value.readiness_decision != "READY":
        reasons.append(PROVIDER_EXECUTION_NOT_READY)
    if (
        value.readiness_policy != ACTIVE_READINESS_POLICY
        or value.qualification_decision != "QUALIFIED"
        or value.qualification_policy != ACTIVE_QUALIFICATION_POLICY
        or not value.execution_admission
        or not value.provenance_gate_passed
    ):
        reasons.append(PROVIDER_EXECUTION_ADMISSION_DENIED)
    if not value.privacy_gate_passed:
        reasons.append(PROVIDER_EXECUTION_PRIVACY_GATE_FAILED)
    if not value.budget_gate_passed:
        reasons.append(PROVIDER_EXECUTION_BUDGET_EXCEEDED)
    if (value.provider_id, value.model_id) != ALLOWED_FAKE_PROVIDER:
        reasons.append(PROVIDER_EXECUTION_PROVIDER_NOT_ALLOWED)
    if (value.prompt_registry_id, value.prompt_version) not in APPROVED_PROMPTS:
        reasons.append(PROVIDER_EXECUTION_PROMPT_VERSION_INVALID)
    return tuple(sorted(set(reasons)))


def _validate_term_alignment_response(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("response is not JSON") from exc
    required = set(prompt_registry.TERM_ALIGNMENT_SCHEMA["required"])
    if not isinstance(parsed, dict) or required - set(parsed):
        raise ValueError("response schema is incomplete")
    ok, reason = prompt_registry.validate_ai_json("term_alignment", parsed)
    if not ok:
        raise ValueError(reason)
    if not isinstance(parsed.get("risk_flags"), list) or not isinstance(
        parsed.get("requires_human_review"), bool
    ):
        raise ValueError("response schema has invalid field types")
    return parsed


def _parse_response(value: ProviderExecutionRequest, raw: str) -> dict[str, Any]:
    if value.prompt_registry_id == "term_alignment":
        return _validate_term_alignment_response(raw)
    return alignment_output_parser.parse_alignment_provider_output(raw)


def execute_provider_request(
    value: ProviderExecutionRequest,
    *,
    transport: DeterministicFakeProviderTransport,
    ledger: InMemoryExecutionLedger | None = None,
) -> ProviderExecutionResult:
    if not isinstance(value, ProviderExecutionRequest):
        raise TypeError("value must be ProviderExecutionRequest.")
    if not isinstance(transport, DeterministicFakeProviderTransport):
        raise TypeError("Task 12I-A permits only DeterministicFakeProviderTransport.")
    payload = _request_payload(value)
    request_hash = _hash_json(payload)
    reasons = _admission_reasons(value)
    if reasons:
        return _result(
            value, status=BLOCKED, request_hash=request_hash, reason_codes=reasons
        )

    tokens = _estimated_tokens(payload)
    budget_valid = all(
        (
            tokens <= int(value.request_token_ceiling) <= MAX_TOKEN_CEILING,
            0 <= float(value.cost_ceiling) <= MAX_COST_CEILING,
            0 < int(value.timeout_seconds) <= MAX_TIMEOUT_SECONDS,
            0 <= int(value.retry_budget) <= MAX_RETRY_BUDGET,
        )
    )
    if not budget_valid:
        return _result(
            value,
            status=BLOCKED,
            request_hash=request_hash,
            estimated_input_tokens=tokens,
            reason_codes=(PROVIDER_EXECUTION_BUDGET_EXCEEDED,),
        )

    active_ledger = ledger or InMemoryExecutionLedger()
    existing = active_ledger.get(value.idempotency_key)
    if existing is not None:
        existing_hash, existing_result = existing
        if existing_hash != request_hash:
            return _result(
                value,
                status=BLOCKED,
                request_hash=request_hash,
                estimated_input_tokens=tokens,
                reason_codes=(PROVIDER_EXECUTION_IDEMPOTENCY_CONFLICT,),
            )
        return replace(existing_result, status=REUSED, request_count=0)

    raw = ""
    retry_count = 0
    request_count = 0
    while True:
        try:
            request_count += 1
            raw = transport.execute(payload, timeout_seconds=value.timeout_seconds)
            break
        except FakeTransportTimeout:
            if retry_count >= value.retry_budget:
                result = _result(
                    value,
                    status=FAILED,
                    request_hash=request_hash,
                    estimated_input_tokens=tokens,
                    retry_count=retry_count,
                    request_count=request_count,
                    reason_codes=(
                        PROVIDER_EXECUTION_TIMEOUT,
                        PROVIDER_EXECUTION_RETRY_EXHAUSTED,
                    ),
                )
                active_ledger.store(value.idempotency_key, request_hash, result)
                return result
            retry_count += 1
        except FakeTransportRetryableError:
            if retry_count >= value.retry_budget:
                result = _result(
                    value,
                    status=FAILED,
                    request_hash=request_hash,
                    estimated_input_tokens=tokens,
                    retry_count=retry_count,
                    request_count=request_count,
                    reason_codes=(PROVIDER_EXECUTION_RETRY_EXHAUSTED,),
                )
                active_ledger.store(value.idempotency_key, request_hash, result)
                return result
            retry_count += 1
        except FakeTransportNonRetryableError:
            result = _result(
                value,
                status=FAILED,
                request_hash=request_hash,
                estimated_input_tokens=tokens,
                retry_count=retry_count,
                request_count=request_count,
                reason_codes=(PROVIDER_EXECUTION_FAILED,),
            )
            active_ledger.store(value.idempotency_key, request_hash, result)
            return result

    response_hash = _hash_text(raw)
    try:
        _parse_response(value, raw)
    except (ValueError, alignment_output_parser.AlignmentOutputParserError):
        result = _result(
            value,
            status=FAILED,
            request_hash=request_hash,
            response_hash=response_hash,
            parse_status="failed",
            estimated_input_tokens=tokens,
            fake_output_tokens=max(1, (len(raw) + 3) // 4),
            retry_count=retry_count,
            request_count=request_count,
            reason_codes=(
                PROVIDER_EXECUTION_RESPONSE_INVALID,
                PROVIDER_EXECUTION_PARSE_FAILED,
            ),
        )
        active_ledger.store(value.idempotency_key, request_hash, result)
        return result

    result = _result(
        value,
        status=SUCCEEDED,
        request_hash=request_hash,
        response_hash=response_hash,
        parse_status="parsed",
        estimated_input_tokens=tokens,
        fake_output_tokens=max(1, (len(raw) + 3) // 4),
        retry_count=retry_count,
        request_count=request_count,
    )
    active_ledger.store(value.idempotency_key, request_hash, result)
    return result


def serialize_execution_result(result: ProviderExecutionResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["reason_codes"] = list(result.reason_codes)
    payload["english_provenance"] = list(result.english_provenance)
    payload["chinese_provenance"] = list(result.chinese_provenance)
    return payload


def policy_manifest() -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "active_readiness_policy": ACTIVE_READINESS_POLICY,
        "active_qualification_policy": ACTIVE_QUALIFICATION_POLICY,
        "allowed_provider": {
            "provider_id": ALLOWED_FAKE_PROVIDER[0],
            "model_id": ALLOWED_FAKE_PROVIDER[1],
        },
        "approved_prompts": [
            {"prompt_registry_id": item[0], "prompt_version": item[1]}
            for item in sorted(APPROVED_PROMPTS)
        ],
        "max_token_ceiling": MAX_TOKEN_CEILING,
        "max_cost_ceiling": MAX_COST_CEILING,
        "max_timeout_seconds": MAX_TIMEOUT_SECONDS,
        "max_retry_budget": MAX_RETRY_BUDGET,
        "external_network_requests": 0,
        "real_provider_requests": 0,
        "real_credentials_read": False,
    }
