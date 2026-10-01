"""Deterministic, network-free Provider readiness admission policy.

The policy consumes a governed evidence-qualification result and sanitized
local configuration metadata.  It never loads credentials and never calls a
Provider.  Execution remains a separate, downstream concern.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


POLICY_ID = "governed-provider-readiness"
POLICY_VERSION = "1.0.0"
ACTIVE_QUALIFICATION_POLICY = "governed-bilingual-evidence-qualification@1.1.0"

READY = "READY"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
NOT_READY = "NOT_READY"

PROVIDER_READINESS_QUALIFICATION_NOT_APPROVED = (
    "PROVIDER_READINESS_QUALIFICATION_NOT_APPROVED"
)
PROVIDER_READINESS_REVIEW_REQUIRED = "PROVIDER_READINESS_REVIEW_REQUIRED"
PROVIDER_READINESS_EVIDENCE_INCOMPLETE = "PROVIDER_READINESS_EVIDENCE_INCOMPLETE"
PROVIDER_READINESS_PROVENANCE_INCOMPLETE = "PROVIDER_READINESS_PROVENANCE_INCOMPLETE"
PROVIDER_READINESS_SOURCE_NOT_ELIGIBLE = "PROVIDER_READINESS_SOURCE_NOT_ELIGIBLE"
PROVIDER_READINESS_PRIVACY_GATE_FAILED = "PROVIDER_READINESS_PRIVACY_GATE_FAILED"
PROVIDER_READINESS_PROMPT_NOT_APPROVED = "PROVIDER_READINESS_PROMPT_NOT_APPROVED"
PROVIDER_READINESS_PROVIDER_NOT_ALLOWED = "PROVIDER_READINESS_PROVIDER_NOT_ALLOWED"
PROVIDER_READINESS_PROVIDER_CONFIG_INCOMPLETE = (
    "PROVIDER_READINESS_PROVIDER_CONFIG_INCOMPLETE"
)
PROVIDER_READINESS_BUDGET_INVALID = "PROVIDER_READINESS_BUDGET_INVALID"
PROVIDER_READINESS_AUDIT_CONTEXT_INCOMPLETE = (
    "PROVIDER_READINESS_AUDIT_CONTEXT_INCOMPLETE"
)
PROVIDER_READINESS_POLICY_UNAVAILABLE = "PROVIDER_READINESS_POLICY_UNAVAILABLE"
PROVIDER_READINESS_EVALUATION_FAILED = "PROVIDER_READINESS_EVALUATION_FAILED"

MAX_REQUEST_TOKEN_BUDGET = 32_000
MAX_COST_CEILING = 25.0
MAX_RETRY_BUDGET = 3
MAX_TIMEOUT_SECONDS = 120
ALLOWED_PRIVACY_CLASSIFICATIONS = frozenset(
    {"PUBLIC", "SYNTHETIC", "AUTHORIZED_EXTERNAL", "LOCAL_ONLY_PRIVATE"}
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _texts(values: Any) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        values = (values,)
    return tuple(sorted({_text(value) for value in (values or ()) if _text(value)}))


@dataclass(frozen=True)
class ProviderReadinessInput:
    qualification_decision: str
    qualification_policy: str
    qualification_result_id: str
    qualification_score: float
    qualification_reason_codes: tuple[str, ...]
    qualification_risk_labels: tuple[str, ...]
    english_term: str
    chinese_term: str
    english_evidence_refs: tuple[str, ...]
    chinese_evidence_refs: tuple[str, ...]
    pair_rank: int
    pair_score: float
    pair_model_metadata_complete: bool
    provider_id: str
    provider_policy_id: str
    provider_allowed: bool
    provider_config_complete: bool
    credential_reference_configured: bool
    prompt_registry_id: str
    prompt_version: str
    prompt_approved: bool
    privacy_classification: str
    privacy_gate_passed: bool
    provenance_gate_passed: bool
    source_governance_passed: bool
    request_token_budget: int
    cost_ceiling: float
    retry_budget: int
    timeout_seconds: int
    idempotency_key: str
    audit_context: str
    upstream_fatal_reasons: tuple[str, ...] = ()

    def __post_init__(self):
        for name in (
            "qualification_reason_codes",
            "qualification_risk_labels",
            "english_evidence_refs",
            "chinese_evidence_refs",
            "upstream_fatal_reasons",
        ):
            object.__setattr__(self, name, _texts(getattr(self, name)))
        object.__setattr__(
            self, "privacy_classification", _text(self.privacy_classification).upper()
        )


@dataclass(frozen=True)
class ProviderReadinessResult:
    decision: str
    readiness_score: float
    reason_codes: tuple[str, ...]
    qualification_policy: str
    provider_policy: str
    prompt_registry_id: str
    prompt_version: str
    privacy_result: str
    provenance_result: str
    budget_result: str
    provider_configuration_result: str
    execution_admission: bool
    readiness_id: str
    policy_id: str = POLICY_ID
    policy_version: str = POLICY_VERSION
    network_called: bool = False
    credential_value_read: bool = False
    score_is_probability: bool = False


def _stable_id(value: ProviderReadinessInput, decision: str, reasons: tuple[str, ...]) -> str:
    payload = {
        "qualification_result_id": value.qualification_result_id,
        "provider_id": value.provider_id,
        "provider_policy_id": value.provider_policy_id,
        "prompt_registry_id": value.prompt_registry_id,
        "prompt_version": value.prompt_version,
        "idempotency_key": value.idempotency_key,
        "decision": decision,
        "reasons": reasons,
        "policy": f"{POLICY_ID}@{POLICY_VERSION}",
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"provider-readiness:{digest}"


def evaluate_provider_readiness(value: ProviderReadinessInput) -> ProviderReadinessResult:
    if not isinstance(value, ProviderReadinessInput):
        raise TypeError("value must be ProviderReadinessInput.")
    reasons: list[str] = []

    qualification = _text(value.qualification_decision).upper()
    if qualification == REVIEW_REQUIRED:
        reasons.append(PROVIDER_READINESS_REVIEW_REQUIRED)
    elif qualification != "QUALIFIED":
        reasons.append(PROVIDER_READINESS_QUALIFICATION_NOT_APPROVED)
    if value.qualification_policy != ACTIVE_QUALIFICATION_POLICY:
        reasons.append(PROVIDER_READINESS_POLICY_UNAVAILABLE)
    if value.upstream_fatal_reasons or value.pair_rank != 1:
        reasons.append(PROVIDER_READINESS_QUALIFICATION_NOT_APPROVED)
    if not all((_text(value.english_term), _text(value.chinese_term))):
        reasons.append(PROVIDER_READINESS_EVIDENCE_INCOMPLETE)
    if not value.english_evidence_refs or not value.chinese_evidence_refs:
        reasons.append(PROVIDER_READINESS_EVIDENCE_INCOMPLETE)
    if not value.provenance_gate_passed or not value.pair_model_metadata_complete:
        reasons.append(PROVIDER_READINESS_PROVENANCE_INCOMPLETE)
    if not value.source_governance_passed:
        reasons.append(PROVIDER_READINESS_SOURCE_NOT_ELIGIBLE)
    privacy_ok = (
        value.privacy_gate_passed
        and value.privacy_classification in ALLOWED_PRIVACY_CLASSIFICATIONS
    )
    if not privacy_ok:
        reasons.append(PROVIDER_READINESS_PRIVACY_GATE_FAILED)
    if not value.prompt_approved or not all(
        (_text(value.prompt_registry_id), _text(value.prompt_version))
    ):
        reasons.append(PROVIDER_READINESS_PROMPT_NOT_APPROVED)
    if not value.provider_allowed or not _text(value.provider_policy_id):
        reasons.append(PROVIDER_READINESS_PROVIDER_NOT_ALLOWED)
    if not value.provider_config_complete or not value.credential_reference_configured:
        reasons.append(PROVIDER_READINESS_PROVIDER_CONFIG_INCOMPLETE)
    budget_ok = all(
        (
            0 < int(value.request_token_budget) <= MAX_REQUEST_TOKEN_BUDGET,
            0 <= float(value.cost_ceiling) <= MAX_COST_CEILING,
            0 <= int(value.retry_budget) <= MAX_RETRY_BUDGET,
            0 < int(value.timeout_seconds) <= MAX_TIMEOUT_SECONDS,
        )
    )
    if not budget_ok:
        reasons.append(PROVIDER_READINESS_BUDGET_INVALID)
    if not all((_text(value.idempotency_key), _text(value.audit_context))):
        reasons.append(PROVIDER_READINESS_AUDIT_CONTEXT_INCOMPLETE)

    reason_codes = tuple(sorted(set(reasons)))
    if not reason_codes:
        decision = READY
    elif qualification == REVIEW_REQUIRED and set(reason_codes) == {
        PROVIDER_READINESS_REVIEW_REQUIRED
    }:
        decision = REVIEW_REQUIRED
    elif qualification == REVIEW_REQUIRED:
        decision = REVIEW_REQUIRED
    else:
        decision = NOT_READY

    gates = (
        qualification == "QUALIFIED",
        value.qualification_policy == ACTIVE_QUALIFICATION_POLICY,
        bool(value.english_evidence_refs and value.chinese_evidence_refs),
        value.provenance_gate_passed,
        value.source_governance_passed,
        privacy_ok,
        value.prompt_approved,
        value.provider_allowed,
        value.provider_config_complete and value.credential_reference_configured,
        budget_ok,
        bool(_text(value.idempotency_key) and _text(value.audit_context)),
    )
    score = round(sum(bool(gate) for gate in gates) / len(gates), 6)
    return ProviderReadinessResult(
        decision=decision,
        readiness_score=score,
        reason_codes=reason_codes,
        qualification_policy=value.qualification_policy,
        provider_policy=value.provider_policy_id,
        prompt_registry_id=value.prompt_registry_id,
        prompt_version=value.prompt_version,
        privacy_result="passed" if privacy_ok else "failed",
        provenance_result=(
            "passed"
            if value.provenance_gate_passed and value.pair_model_metadata_complete
            else "failed"
        ),
        budget_result="passed" if budget_ok else "failed",
        provider_configuration_result=(
            "passed"
            if value.provider_allowed
            and value.provider_config_complete
            and value.credential_reference_configured
            else "failed"
        ),
        execution_admission=decision == READY,
        readiness_id=_stable_id(value, decision, reason_codes),
    )


def serialize_provider_readiness_result(
    result: ProviderReadinessResult,
) -> dict[str, Any]:
    if not isinstance(result, ProviderReadinessResult):
        raise TypeError("result must be ProviderReadinessResult.")
    payload = asdict(result)
    payload["reason_codes"] = list(result.reason_codes)
    return payload


def policy_manifest() -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "policy_version": POLICY_VERSION,
        "active_qualification_policy": ACTIVE_QUALIFICATION_POLICY,
        "decisions": [READY, REVIEW_REQUIRED, NOT_READY],
        "hard_gates": [
            "qualification",
            "evidence",
            "provenance",
            "source_governance",
            "privacy",
            "prompt_registry",
            "provider_policy",
            "provider_local_configuration",
            "bounded_budget",
            "idempotency_and_audit",
        ],
        "network_calls": 0,
        "credential_value_reads": 0,
        "score_is_probability": False,
    }


def evaluate_formal_prepared_readiness(
    prepared: Any,
    *,
    session: Any,
    policy_model: Any,
    execution_key: str,
) -> ProviderReadinessResult:
    """Adapt a server-created Formal input without reading credential values."""

    from services import alignment_prompting, llm_provider_config, provider_governance

    policy = provider_governance.get_effective_provider_policy(
        session, policy_model, prepared.provider_name
    )
    policy_data = provider_governance.serialize_provider_policy(policy)
    config = dict(
        llm_provider_config.DEFAULT_PROVIDER_CONFIGS.get(prepared.provider_name, {})
    )
    allowed_courses = provider_governance.normalize_list(
        policy_data.get("allowed_courses", [])
    )
    blocked_courses = provider_governance.normalize_list(
        policy_data.get("blocked_courses", [])
    )
    provider_allowed = bool(
        policy_data
        and policy_data.get("enabled")
        and policy_data.get("status") == "active"
        and prepared.course not in blocked_courses
        and ("*" in allowed_courses or prepared.course in allowed_courses)
    )
    try:
        alignment_prompting.get_prompt_template(prepared.prompt_version)
        prompt_approved = True
    except Exception:
        prompt_approved = False
    requires_credentials = bool(config.get("requires_credentials"))
    credential_reference_configured = bool(
        not requires_credentials or _text(config.get("api_key_env_name"))
    )
    config_complete = bool(
        config
        and config.get("enabled")
        and int(config.get("timeout_seconds") or 0) > 0
        and int(config.get("max_prompt_chars") or 0) > 0
        and int(config.get("max_output_chars") or 0) > 0
        and (config.get("transport_mode") == "local" or config.get("replay_mode"))
    )
    max_cost = policy_data.get("max_estimated_cost_per_call")
    cost_ceiling = float(max_cost) if max_cost not in (None, "") else -1.0
    return evaluate_provider_readiness(
        ProviderReadinessInput(
            qualification_decision=prepared.evidence_qualification_decision,
            qualification_policy=prepared.evidence_qualification_policy,
            qualification_result_id=prepared.evidence_qualification_result_id,
            qualification_score=float(
                getattr(prepared, "evidence_qualification_score", 0.0) or 0.0
            ),
            qualification_reason_codes=tuple(
                getattr(prepared, "evidence_qualification_reason_codes", ()) or ()
            ),
            qualification_risk_labels=tuple(prepared.risk_labels or ()),
            english_term=prepared.english_term,
            chinese_term=prepared.chinese_candidate_values[0],
            english_evidence_refs=prepared.english_evidence_refs,
            chinese_evidence_refs=prepared.chinese_evidence_refs,
            pair_rank=1 if prepared.evidence_qualification_result_id else 0,
            pair_score=float(getattr(prepared, "selected_pair_score", 0.0) or 0.0),
            pair_model_metadata_complete=bool(
                prepared.evidence_qualification_result_id
                and prepared.model_identity
                and prepared.retrieval_version
            ),
            provider_id=prepared.provider_name,
            provider_policy_id=(
                _text(policy_data.get("policy_uid"))
                or f"{prepared.provider_name}-provider-policy"
            ),
            provider_allowed=provider_allowed,
            provider_config_complete=config_complete,
            credential_reference_configured=credential_reference_configured,
            prompt_registry_id="term_alignment",
            prompt_version=prepared.prompt_version,
            prompt_approved=prompt_approved,
            privacy_classification="LOCAL_ONLY_PRIVATE",
            privacy_gate_passed=bool(config.get("transport_mode") == "local"),
            provenance_gate_passed=bool(
                prepared.english_evidence_refs
                and prepared.chinese_evidence_refs
                and prepared.chinese_candidate_provenance_refs
            ),
            source_governance_passed=True,
            request_token_budget=int(policy_data.get("max_prompt_chars") or 0),
            cost_ceiling=cost_ceiling,
            retry_budget=int(policy_data.get("max_retries") or 0),
            timeout_seconds=int(policy_data.get("timeout_seconds") or 0),
            idempotency_key=execution_key,
            audit_context="formal_document_alignment",
        )
    )
