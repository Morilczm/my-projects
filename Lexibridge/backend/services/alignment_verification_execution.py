"""Application service for alignment verification execution orchestration.

This module deliberately stays below the Flask layer. It accepts normalized
HTTP input, actor metadata, safe audit context, and explicit domain
dependencies, then returns a data result for the route adapter to wrap.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class AlignmentVerificationExecutionRequest:
    """Normalized request fields for one alignment verification execution."""

    payload: Mapping[str, Any]
    provider_name: str = "mock-rule-v1"
    card_uid: str = ""
    attach_to_card: bool = False

    def payload_dict(self) -> dict[str, Any]:
        return dict(self.payload or {})


@dataclass(frozen=True)
class AlignmentVerificationActor:
    """Safe actor identity required by the verification application service."""

    user_id: Any
    email: str = ""
    role: str = ""
    display_name: str = ""


@dataclass(frozen=True)
class AlignmentVerificationExecutionContext:
    """Safe request context used for audit summaries and request tracing."""

    request_id: str
    actor_id: Any = None
    actor_role: str = ""
    actor_name: str = ""
    source: str = "api"
    ip_hash: str = ""
    user_agent_summary: str = ""
    route: str = "/api/alignment/verify"
    occurred_at: str | None = None

    def to_audit_context(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "actor_name": self.actor_name,
            "source": self.source or "api",
            "ip_hash": self.ip_hash,
            "user_agent_summary": self.user_agent_summary,
        }


@dataclass(frozen=True)
class AlignmentVerificationExecutionModels:
    """Minimal model classes touched directly by the execution service."""

    concept_alignment_card: Any
    provider_policy: Any
    provider_usage_record: Any
    verification_run: Any


@dataclass(frozen=True)
class AlignmentVerificationExecutionDependencies:
    """Domain dependencies for alignment verification execution.

    This is intentionally scoped to the verification domain. It is not shared
    route infrastructure and must not be added to RouteCoreDependencies.
    """

    db: Any
    models: AlignmentVerificationExecutionModels
    provider_registry_service: Any
    provider_governance_service: Any
    verification_service: Any
    concept_card_service: Any
    current_time_text: Callable[[], str]
    record_alignment_verification_audit: Callable[..., Any]
    record_alignment_provider_usage: Callable[..., Any]


@dataclass(frozen=True)
class AlignmentVerificationExecutionResult:
    """Service result for the Flask route to map to the existing API envelope."""

    outcome: str
    status_code: int
    payload: dict[str, Any]
    message: str
    error_code: str = ""
    audit_error_code: str = ""
    verification_run_uid: str = ""
    attached_card_uid: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status_code < 400 and not self.error_code


def _provider_options(data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fake_response_type": str(data.get("fake_response_type") or "").strip(),
        "replay_response_type": str(data.get("replay_response_type") or "").strip(),
        "prompt_version": str(data.get("prompt_version") or "").strip(),
        "max_prompt_chars": data.get("max_prompt_chars"),
        "max_output_chars": data.get("max_output_chars"),
        "max_estimated_cost": data.get("max_estimated_cost"),
        "timeout_seconds": data.get("timeout_seconds"),
        "max_retries": data.get("max_retries"),
    }


def _provider_type_for(deps: AlignmentVerificationExecutionDependencies, provider_name: str) -> str:
    return deps.provider_governance_service.provider_type_for(provider_name)


def _error_result(
    *,
    outcome: str,
    status_code: int,
    error_code: str,
    message: str,
    audit_error_code: str,
) -> AlignmentVerificationExecutionResult:
    return AlignmentVerificationExecutionResult(
        outcome=outcome,
        status_code=status_code,
        payload={},
        message=message,
        error_code=error_code,
        audit_error_code=audit_error_code,
    )


def execute_alignment_verification(
    request: AlignmentVerificationExecutionRequest,
    actor: AlignmentVerificationActor,
    context: AlignmentVerificationExecutionContext,
    dependencies: AlignmentVerificationExecutionDependencies,
) -> AlignmentVerificationExecutionResult:
    """Execute one alignment verification using the existing domain services."""

    deps = dependencies
    session = deps.db.session
    data = request.payload_dict()
    provider_name = request.provider_name
    card_uid = request.card_uid
    attach_to_card = request.attach_to_card
    audit_context = context.to_audit_context()
    started_at = datetime.now()

    deps.record_alignment_verification_audit(
        "alignment_verification_requested",
        input_data=data,
        card_uid=card_uid,
        audit_context=audit_context,
        commit=True,
    )

    provider = None
    run = None
    output: dict[str, Any] = {}
    card = None
    attached_card = None
    attach_blocked_reason = ""

    concept_not_found_error = deps.concept_card_service.ConceptCardNotFoundError
    provider_error = deps.provider_registry_service.AlignmentProviderError
    verification_provider_error = deps.verification_service.AlignmentVerificationProviderError
    verification_error = deps.verification_service.AlignmentVerificationError

    try:
        provider = deps.provider_registry_service.get_alignment_provider(provider_name)
        options = _provider_options(data)
        started_at = datetime.now()
        if card_uid:
            card = deps.concept_card_service.get_concept_card(
                session,
                deps.models.concept_alignment_card,
                card_uid,
            )
            verification_input = deps.verification_service.build_alignment_verification_input_from_card(card)
            verification_input["provider_options"] = options
        else:
            verification_input = deps.verification_service.validate_alignment_verification_input(data)

        gate_result = deps.provider_governance_service.evaluate_provider_request(
            session,
            deps.models.provider_policy,
            deps.models.provider_usage_record,
            provider_name,
            verification_input,
            actor_role=actor.role,
            audit_context=audit_context,
            now_fn=deps.current_time_text,
        )

        if not gate_result.get("allowed"):
            output = deps.provider_governance_service.provider_blocked_output(
                provider_name,
                _provider_type_for(deps, provider_name),
                gate_result,
            )
            run = deps.verification_service.create_alignment_verification_run(
                session,
                deps.models.verification_run,
                verification_input,
                output,
                card_uid=verification_input.get("card_uid", ""),
                now_fn=deps.current_time_text,
                commit=False,
            )
            deps.record_alignment_verification_audit(
                "alignment_verification_blocked_by_policy",
                run=run,
                input_data=data,
                output_data=output,
                card_uid=card_uid,
                audit_context=audit_context,
                error_code=gate_result.get("reason", "provider_policy_invalid"),
                error_message=gate_result.get("reason", "provider_policy_invalid"),
                commit=False,
            )
            deps.record_alignment_provider_usage(
                provider_name,
                run=run,
                input_data=verification_input,
                output_data=output,
                audit_context=audit_context,
                commit=False,
            )
            session.commit()
        else:
            run, output = deps.verification_service.verify_alignment(
                session,
                deps.models.verification_run,
                verification_input,
                provider_name=provider_name,
                audit_context=audit_context,
                now_fn=deps.current_time_text,
                commit=False,
            )
            deps.record_alignment_provider_usage(
                provider_name,
                run=run,
                input_data=verification_input,
                output_data=output,
                audit_context=audit_context,
                commit=False,
            )
            if attach_to_card and getattr(run, "card_uid", ""):
                if deps.provider_governance_service.can_attach_verification_to_card(
                    run,
                    gate_result.get("policy", {}),
                ):
                    attached_card = deps.verification_service.apply_verification_result_to_card(
                        session,
                        deps.models.concept_alignment_card,
                        run,
                        mode="attach_only",
                        commit=False,
                    )
                else:
                    attach_blocked_reason = "provider_attach_not_allowed"
                    deps.record_alignment_verification_audit(
                        "alignment_verification_blocked_by_policy",
                        run=run,
                        input_data=data,
                        output_data=output,
                        card_uid=card_uid,
                        audit_context=audit_context,
                        error_code=attach_blocked_reason,
                        error_message=attach_blocked_reason,
                        commit=False,
                    )
            session.commit()
    except concept_not_found_error as exc:
        session.rollback()
        latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        deps.record_alignment_verification_audit(
            "alignment_verification_failed",
            input_data=data,
            card_uid=card_uid,
            audit_context=audit_context,
            error_code="concept_card_not_found",
            error_message=str(exc),
            latency_ms=latency_ms,
        )
        return _error_result(
            outcome="concept_card_not_found",
            status_code=404,
            error_code="RESOURCE_NOT_FOUND",
            message=str(exc),
            audit_error_code="concept_card_not_found",
        )
    except provider_error as exc:
        session.rollback()
        latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        deps.record_alignment_verification_audit(
            "alignment_verification_failed",
            input_data=data,
            card_uid=card_uid,
            audit_context=audit_context,
            error_code="unknown_provider",
            error_message=str(exc),
            latency_ms=latency_ms,
        )
        return _error_result(
            outcome="unknown_provider",
            status_code=400,
            error_code="VALIDATION_ERROR",
            message=str(exc),
            audit_error_code="unknown_provider",
        )
    except verification_provider_error as exc:
        session.rollback()
        latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        deps.record_alignment_verification_audit(
            "alignment_verification_failed",
            input_data=data,
            card_uid=card_uid,
            audit_context=audit_context,
            error_code="unknown_provider",
            error_message=str(exc),
            latency_ms=latency_ms,
        )
        return _error_result(
            outcome="unknown_provider",
            status_code=400,
            error_code="VALIDATION_ERROR",
            message=str(exc),
            audit_error_code="unknown_provider",
        )
    except verification_error as exc:
        session.rollback()
        latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        deps.record_alignment_verification_audit(
            "alignment_verification_failed",
            input_data=data,
            card_uid=card_uid,
            audit_context=audit_context,
            error_code="alignment_verification_validation_error",
            error_message=str(exc),
            latency_ms=latency_ms,
        )
        return _error_result(
            outcome="validation_error",
            status_code=400,
            error_code="VALIDATION_ERROR",
            message=str(exc),
            audit_error_code="alignment_verification_validation_error",
        )
    except Exception as exc:
        session.rollback()
        latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        deps.record_alignment_verification_audit(
            "alignment_verification_failed",
            input_data=data,
            card_uid=card_uid,
            audit_context=audit_context,
            error_code="alignment_verification_failed",
            error_message=str(exc),
            latency_ms=latency_ms,
        )
        return _error_result(
            outcome="execution_failed",
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="Alignment verification failed.",
            audit_error_code="alignment_verification_failed",
        )

    latency_ms = int((datetime.now() - started_at).total_seconds() * 1000)
    completion_event_type = (
        "alignment_verification_failed"
        if getattr(run, "verification_status", "") == "failed"
        else "alignment_verification_completed"
    )
    deps.record_alignment_verification_audit(
        completion_event_type,
        run=run,
        input_data=data,
        output_data=output,
        card_uid=card_uid,
        audit_context=audit_context,
        error_code=getattr(run, "error_code", "") if completion_event_type == "alignment_verification_failed" else "",
        error_message=getattr(run, "error_message", "") if completion_event_type == "alignment_verification_failed" else "",
        latency_ms=latency_ms,
    )

    if attached_card is not None:
        deps.record_alignment_verification_audit(
            "alignment_verification_attached_to_card",
            run=run,
            input_data=data,
            output_data=output,
            card_uid=getattr(attached_card, "card_uid", ""),
            audit_context=audit_context,
            latency_ms=latency_ms,
        )

    serialized_run = deps.verification_service.serialize_alignment_verification_run(run)
    response_data = {
        "run_uid": getattr(run, "run_uid", ""),
        "provider_name": getattr(run, "provider_name", ""),
        "provider_type": getattr(run, "provider_type", ""),
        "provider_version": getattr(run, "provider_version", ""),
        "prompt_version": getattr(run, "prompt_version", ""),
        "output_schema_version": getattr(run, "output_schema_version", ""),
        "parser_version": getattr(run, "parser_version", ""),
        "provider_response_status": getattr(run, "provider_response_status", ""),
        "verification_status": getattr(run, "verification_status", ""),
        "alignment_decision": output.get("alignment_decision", "") if isinstance(output, dict) else "",
        "alignment_confidence": getattr(run, "alignment_confidence", None),
        "recommendation": getattr(run, "recommendation", ""),
        "risk_labels": serialized_run.get("risk_labels", []),
        "estimated_cost": output.get("estimated_cost", {}) if isinstance(output, dict) else {},
        "retry_count": output.get("retry_count", 0) if isinstance(output, dict) else 0,
        "can_auto_approve": bool(output.get("can_auto_approve")) if isinstance(output, dict) else False,
        "is_production_result": bool(output.get("is_production_result")) if isinstance(output, dict) else False,
        "run": serialized_run,
    }
    if attach_blocked_reason:
        response_data["attach_blocked_reason"] = attach_blocked_reason
    if card is not None:
        response_data["card"] = deps.concept_card_service.serialize_concept_card(attached_card or card)

    return AlignmentVerificationExecutionResult(
        outcome="success",
        status_code=200,
        payload=response_data,
        message="Alignment verification completed.",
        verification_run_uid=getattr(run, "run_uid", ""),
        attached_card_uid=getattr(attached_card, "card_uid", "") if attached_card is not None else "",
    )
