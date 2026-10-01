"""Lease-fenced formal verification for one document-alignment workflow item."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.exc import IntegrityError
from services.formal_real_provider_evaluation_policy import (
    is_trusted_formal_real_provider_evaluation_context,
)

from services.document_alignment_workflow_contract import (
    FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
    FORMAL_ITEM_VERIFICATION_EXECUTION_VERSION,
    ITEM_STAGE_DRAFT_CREATION,
    ITEM_STAGE_EVIDENCE_RETRIEVAL,
    ITEM_STAGE_TERMINAL,
    ITEM_STAGE_VERIFICATION,
    ITEM_STATUS_BLOCKED,
    ITEM_STATUS_DRAFT_CREATED,
    ITEM_STATUS_EVIDENCE_READY,
    ITEM_STATUS_FAILED,
    ITEM_STATUS_NEEDS_REVIEW,
    ITEM_STATUS_VERIFICATION_COMPLETED,
    ITEM_VERIFICATION_EXECUTION_STATUS_ATTACH_PENDING,
    ITEM_VERIFICATION_EXECUTION_STATUS_BLOCKED,
    ITEM_VERIFICATION_EXECUTION_STATUS_DRAFT_READY,
    ITEM_VERIFICATION_EXECUTION_STATUS_FAILED,
    ITEM_VERIFICATION_EXECUTION_STATUS_NEEDS_REVIEW,
    ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_BLOCKED,
    ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_PASSED,
    ITEM_VERIFICATION_EXECUTION_STATUS_PREPARED,
    ITEM_VERIFICATION_EXECUTION_STATUS_PROVIDER_COMPLETED,
    ITEM_VERIFICATION_EXECUTION_STATUS_PROVIDER_STARTED,
    ITEM_VERIFICATION_EXECUTION_STATUS_VERIFICATION_PERSISTED,
    ROOT_STATUS_PROCESSING,
)
from services.formal_background_job_execution import (
    LEASE_OUTCOME_ACCEPTED,
    LEASE_OUTCOME_INVALID_STATE,
    LEASE_OUTCOME_LEASE_EXPIRED,
    LEASE_OUTCOME_STALE_ATTEMPT,
    FormalBackgroundJobExecutionDependencies,
    FormalJobLeaseOperationResult,
    FormalJobExecutionFence,
)
from services.formal_item_verification_identity import (
    build_formal_item_audit_event_identity,
    build_formal_item_verification_execution_key,
    build_formal_item_verification_input_fingerprint,
)


MAX_EVIDENCE_SNIPPET_CHARS = 500


def _required_text(value: Any, field_name: str, max_length: int = 500) -> str:
    text = " ".join(unicodedata.normalize("NFKC", str(value or "")).split())
    if not text:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _normalized_values(values: Any, field_name: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be a collection.")
    normalized = tuple(sorted({_required_text(value, field_name) for value in (values or ())}))
    if not normalized and not allow_empty:
        raise ValueError(f"{field_name} is required.")
    return normalized


@dataclass(frozen=True)
class PreparedEvidenceSnippet:
    reference_id: str
    text: str = field(repr=False)

    def __post_init__(self):
        reference = _required_text(self.reference_id, "reference_id", 300)
        text = str(self.text or "").strip()
        if not text:
            raise ValueError("evidence snippet is required.")
        if len(text) > MAX_EVIDENCE_SNIPPET_CHARS:
            raise ValueError("evidence snippet must be bounded to 500 characters.")
        object.__setattr__(self, "reference_id", reference)
        object.__setattr__(self, "text", text)


@dataclass(frozen=True)
class PreparedFormalItemVerificationInput:
    workflow_run_uid: str
    workflow_item_uid: str
    workflow_item_key: str
    english_term: str
    chinese_candidate_values: tuple[str, ...]
    chinese_candidate_provenance_refs: tuple[str, ...]
    english_evidence_refs: tuple[str, ...]
    chinese_evidence_refs: tuple[str, ...]
    english_snippets: tuple[PreparedEvidenceSnippet, ...] = field(repr=False)
    chinese_snippets: tuple[PreparedEvidenceSnippet, ...] = field(repr=False)
    source_uid: str = ""
    source_version: str = ""
    course: str = ""
    chapter: str = ""
    workflow_version: str = ""
    retrieval_version: str = ""
    provider_name: str = ""
    model_identity: str = ""
    prompt_version: str = ""
    parser_version: str = ""
    output_schema_version: str = ""
    risk_labels: tuple[str, ...] = ()
    evidence_qualification_result_id: str = ""
    evidence_qualification_decision: str = ""
    evidence_qualification_policy: str = ""

    def __post_init__(self):
        required = (
            ("workflow_run_uid", 64),
            ("workflow_item_uid", 64),
            ("workflow_item_key", 220),
            ("english_term", 220),
            ("source_uid", 64),
            ("source_version", 80),
            ("course", 160),
            ("chapter", 160),
            ("workflow_version", 80),
            ("retrieval_version", 80),
            ("provider_name", 120),
            ("model_identity", 160),
            ("prompt_version", 80),
            ("parser_version", 80),
            ("output_schema_version", 80),
        )
        for name, limit in required:
            object.__setattr__(self, name, _required_text(getattr(self, name), name, limit))
        for name in (
            "chinese_candidate_values",
            "chinese_candidate_provenance_refs",
            "english_evidence_refs",
            "chinese_evidence_refs",
        ):
            object.__setattr__(self, name, _normalized_values(getattr(self, name), name))
        if len(self.chinese_candidate_values) != 1 or len(self.chinese_candidate_provenance_refs) != 1:
            raise ValueError("V1 requires one selected Chinese candidate and one provenance reference.")
        object.__setattr__(self, "risk_labels", _normalized_values(self.risk_labels, "risk_labels", allow_empty=True))
        if self.evidence_qualification_result_id:
            object.__setattr__(
                self,
                "evidence_qualification_result_id",
                _required_text(
                    self.evidence_qualification_result_id,
                    "evidence_qualification_result_id",
                    160,
                ),
            )
            if self.evidence_qualification_decision != "QUALIFIED":
                raise ValueError(
                    "Formal readiness requires a QUALIFIED evidence decision."
                )
            object.__setattr__(
                self,
                "evidence_qualification_policy",
                _required_text(
                    self.evidence_qualification_policy,
                    "evidence_qualification_policy",
                    160,
                ),
            )
        for name, refs_name in (
            ("english_snippets", "english_evidence_refs"),
            ("chinese_snippets", "chinese_evidence_refs"),
        ):
            snippets = tuple(getattr(self, name) or ())
            if any(not isinstance(snippet, PreparedEvidenceSnippet) for snippet in snippets):
                raise TypeError(f"{name} must contain PreparedEvidenceSnippet values.")
            allowed_refs = set(getattr(self, refs_name))
            if any(snippet.reference_id not in allowed_refs for snippet in snippets):
                raise ValueError(f"{name} must reference governed evidence IDs.")
            object.__setattr__(self, name, snippets)


@dataclass(frozen=True)
class ExecuteDocumentAlignmentItemVerificationCommand:
    workflow_run_uid: str
    workflow_item_uid: str
    job_uid: str
    worker_id: str
    execution_attempt: int
    lease_token: str = field(repr=False)
    prepared_input: PreparedFormalItemVerificationInput = field(repr=False)

    def __post_init__(self):
        for name, limit in (
            ("workflow_run_uid", 64),
            ("workflow_item_uid", 64),
            ("job_uid", 64),
            ("worker_id", 120),
            ("lease_token", 128),
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, limit))
        attempt = int(self.execution_attempt or 0)
        if attempt <= 0:
            raise ValueError("execution_attempt must be positive.")
        object.__setattr__(self, "execution_attempt", attempt)
        if not isinstance(self.prepared_input, PreparedFormalItemVerificationInput):
            raise TypeError("prepared_input must be PreparedFormalItemVerificationInput.")
        if self.workflow_run_uid != self.prepared_input.workflow_run_uid:
            raise ValueError("workflow_run_uid does not match prepared_input.")
        if self.workflow_item_uid != self.prepared_input.workflow_item_uid:
            raise ValueError("workflow_item_uid does not match prepared_input.")


@dataclass(frozen=True)
class ExecuteDocumentAlignmentItemVerificationResult:
    outcome: str
    workflow_run_uid: str
    workflow_item_uid: str
    execution_key: str = ""
    execution_status: str = ""
    item_status: str = ""
    item_stage: str = ""
    draft_card_uid: str = ""
    preflight_run_uid: str = ""
    verification_run_uid: str = ""
    reused_execution: bool = False
    reused_draft: bool = False
    reused_preflight: bool = False
    reused_verification: bool = False
    provider_executed: bool = False
    usage_recorded: bool = False
    audit_events_created: int = 0
    retryable: bool = False
    risk_labels: tuple[str, ...] = ()
    confidence_summary: dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""
    error_code: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class DocumentAlignmentItemVerificationModels:
    workflow_run: Any
    workflow_item: Any
    execution: Any
    concept_card: Any
    provider_policy: Any
    preflight_run: Any
    verification_run: Any
    provider_usage: Any
    audit_record: Any
    background_job: Any


@dataclass(frozen=True)
class DraftVerificationCollaborator:
    create_or_reuse: Callable[..., Any]


@dataclass(frozen=True)
class ProviderGovernanceCollaborator:
    provider_type_for: Callable[[str], str]
    evaluate_policy: Callable[..., dict[str, Any]]
    run_preflight: Callable[..., tuple[Any, dict[str, Any]]]
    can_attach: Callable[[Any, Any], bool]


@dataclass(frozen=True)
class VerificationCollaborator:
    resolve_provider: Callable[[str], Any]
    validate_input: Callable[[dict[str, Any]], dict[str, Any]]
    create_safe_run: Callable[..., Any]
    attach: Callable[..., Any]


@dataclass(frozen=True)
class RecordingCollaborator:
    record_usage: Callable[..., Any]
    create_audit: Callable[..., Any]


@dataclass(frozen=True)
class DocumentAlignmentItemVerificationDependencies:
    session: Any
    models: DocumentAlignmentItemVerificationModels
    draft: DraftVerificationCollaborator
    governance: ProviderGovernanceCollaborator
    verification: VerificationCollaborator
    recording: RecordingCollaborator
    fence_active_lease: Callable[..., Any]
    current_time_factory: Callable[[], datetime]
    lease_seconds: int = 30
    actor_role: str = "teacher"
    evaluation_context: Any = field(default=None, repr=False, compare=False)
    evaluate_provider_readiness: Callable[..., Any] | None = field(
        default=None, repr=False, compare=False
    )


_ALLOWED_PROVIDER_TYPES = frozenset({"mock", "fake_llm", "replay_llm", "local", "deterministic"})
_SAFE_ERROR_MARKERS = (
    "LEXIBRIDGE_SENTINEL_SECRET",
    "Authorization:",
    "Cookie:",
    "Bearer ",
    "sk-",
)


def _time_text(value: datetime) -> str:
    return value.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _safe_error(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip() or fallback
    if any(marker in text for marker in _SAFE_ERROR_MARKERS):
        return fallback
    return text[:500]


def _loads_json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _safe_output_fingerprint(output: dict[str, Any]) -> str:
    payload = {
        "provider_name": str(output.get("provider_name") or ""),
        "provider_type": str(output.get("provider_type") or ""),
        "provider_version": str(output.get("provider_version") or ""),
        "alignment_decision": str(output.get("alignment_decision") or ""),
        "alignment_confidence": output.get("alignment_confidence"),
        "recommendation": str(output.get("recommendation") or ""),
        "risk_labels": sorted({str(value) for value in output.get("risk_labels", []) or []}),
        "verification_status": str(output.get("verification_status") or ""),
        "provider_response_status": str(output.get("provider_response_status") or ""),
        "prompt_version": str(output.get("prompt_version") or ""),
        "parser_version": str(output.get("parser_version") or ""),
        "output_schema_version": str(output.get("output_schema_version") or ""),
        "error_code": str(output.get("error_code") or ""),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _execution_identity(prepared: PreparedFormalItemVerificationInput) -> tuple[str, str]:
    fingerprint = build_formal_item_verification_input_fingerprint(
        workflow_run_uid=prepared.workflow_run_uid,
        workflow_item_uid=prepared.workflow_item_uid,
        workflow_item_key=prepared.workflow_item_key,
        english_term=prepared.english_term,
        chinese_candidate_values=prepared.chinese_candidate_values,
        chinese_candidate_provenance_refs=prepared.chinese_candidate_provenance_refs,
        english_evidence_refs=prepared.english_evidence_refs,
        chinese_evidence_refs=prepared.chinese_evidence_refs,
        source_uid=prepared.source_uid,
        source_version=prepared.source_version,
        course=prepared.course,
        chapter=prepared.chapter,
        retrieval_version=prepared.retrieval_version,
        evidence_qualification_result_id=prepared.evidence_qualification_result_id,
        evidence_qualification_policy=prepared.evidence_qualification_policy,
    )
    execution_key = build_formal_item_verification_execution_key(
        workflow_run_uid=prepared.workflow_run_uid,
        workflow_item_uid=prepared.workflow_item_uid,
        workflow_item_key=prepared.workflow_item_key,
        workflow_version=prepared.workflow_version,
        safe_input_fingerprint=fingerprint,
        provider_name=prepared.provider_name,
        model_identity=prepared.model_identity,
        retrieval_version=prepared.retrieval_version,
        prompt_version=prepared.prompt_version,
        parser_version=prepared.parser_version,
        output_schema_version=prepared.output_schema_version,
    )
    return fingerprint, execution_key


def _lease_fence(
    command: ExecuteDocumentAlignmentItemVerificationCommand,
    dependencies: DocumentAlignmentItemVerificationDependencies,
):
    fence = FormalJobExecutionFence(
        job_uid=command.job_uid,
        worker_id=command.worker_id,
        execution_attempt=command.execution_attempt,
        lease_token=command.lease_token,
    )
    lease_dependencies = FormalBackgroundJobExecutionDependencies(
        session=dependencies.session,
        job_model=dependencies.models.background_job,
        current_time_factory=dependencies.current_time_factory,
        lease_seconds=dependencies.lease_seconds,
    )
    result = dependencies.fence_active_lease(fence, lease_dependencies)
    if result.outcome != LEASE_OUTCOME_ACCEPTED:
        return result
    scope_error = _persisted_scope_error(command, dependencies)
    if scope_error:
        return FormalJobLeaseOperationResult(
            outcome=LEASE_OUTCOME_INVALID_STATE,
            job_uid=command.job_uid,
            execution_attempt=command.execution_attempt,
            error_code=scope_error,
            error_message="Formal job, workflow run, and item scope do not match.",
        )
    return result


def _lease_rejection_result(command, lease_result):
    if lease_result.error_code in {
        "FORMAL_ITEM_VERIFICATION_JOB_MISMATCH",
        "FORMAL_ITEM_VERIFICATION_INPUT_MISMATCH",
    }:
        outcome = "execution_conflict"
    elif lease_result.outcome == LEASE_OUTCOME_STALE_ATTEMPT:
        outcome = "stale_attempt"
    elif lease_result.outcome == LEASE_OUTCOME_LEASE_EXPIRED:
        outcome = "lease_expired"
    else:
        outcome = "persistence_error"
    return ExecuteDocumentAlignmentItemVerificationResult(
        outcome=outcome,
        workflow_run_uid=command.workflow_run_uid,
        workflow_item_uid=command.workflow_item_uid,
        retryable=outcome == "persistence_error",
        error_code=lease_result.error_code or "FORMAL_JOB_LEASE_NOT_ACTIVE",
        error_message=_safe_error(
            lease_result.error_message,
            "Formal job lease is not active for item verification.",
        ),
    )


def _load_run_item(command, dependencies):
    models = dependencies.models
    session = dependencies.session
    run = session.query(models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one_or_none()
    item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one_or_none()
    if run is None or item is None or item.workflow_run_id != getattr(run, "id", None):
        raise ValueError("Formal workflow run or item is not available.")
    if not _run_item_scope_matches(run, item, command.prepared_input):
        raise ValueError("Formal item prepared input does not match persisted source identity.")
    return run, item


def _normalized_json_values(value: Any) -> tuple[str, ...]:
    loaded = _loads_json(value, [])
    if not isinstance(loaded, list):
        return ()
    return tuple(sorted({_required_text(item, "persisted_reference", 300) for item in loaded}))


def _persisted_candidate_summary(value: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    loaded = _loads_json(value, {})
    if not isinstance(loaded, dict):
        return (), ()
    values = _normalized_values(loaded.get("values", ()), "persisted_candidate_values", allow_empty=True)
    refs = _normalized_values(
        loaded.get("provenance_refs", ()),
        "persisted_candidate_provenance_refs",
        allow_empty=True,
    )
    return values, refs


def _run_item_scope_matches(run: Any, item: Any, prepared: PreparedFormalItemVerificationInput) -> bool:
    candidate_values, candidate_refs = _persisted_candidate_summary(
        getattr(item, "chinese_candidate_summary", "{}")
    )
    return all((
        getattr(run, "status", "") == ROOT_STATUS_PROCESSING,
        item.item_key == prepared.workflow_item_key,
        item.candidate_term == prepared.english_term,
        run.source_uid == prepared.source_uid,
        str(run.source_version or "") == prepared.source_version,
        run.workflow_version == prepared.workflow_version,
        not run.retrieval_version or run.retrieval_version == prepared.retrieval_version,
        not run.prompt_version or run.prompt_version == prepared.prompt_version,
        not run.provider_preference or run.provider_preference == prepared.provider_name,
        not run.model_preference or run.model_preference == prepared.model_identity,
        candidate_values == prepared.chinese_candidate_values,
        candidate_refs == prepared.chinese_candidate_provenance_refs,
        _normalized_json_values(item.english_evidence_refs) == prepared.english_evidence_refs,
        _normalized_json_values(item.chinese_evidence_refs) == prepared.chinese_evidence_refs,
    ))


def _persisted_scope_error(command, dependencies) -> str:
    models = dependencies.models
    session = dependencies.session
    job = session.query(models.background_job).filter_by(job_uid=command.job_uid).one_or_none()
    run = session.query(models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one_or_none()
    item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one_or_none()
    payload = _loads_json(getattr(job, "input_json", "{}"), {}) if job is not None else {}
    if not all((
        job is not None,
        getattr(job, "job_type", "") == FORMAL_DOCUMENT_ALIGNMENT_JOB_TYPE,
        isinstance(payload, dict),
        payload.get("workflow_run_uid") == command.workflow_run_uid,
        payload.get("workflow_version") == command.prepared_input.workflow_version,
    )):
        return "FORMAL_ITEM_VERIFICATION_JOB_MISMATCH"
    if not all((
        run is not None,
        item is not None,
        getattr(item, "workflow_run_id", None) == getattr(run, "id", None),
        run is not None and item is not None and _run_item_scope_matches(run, item, command.prepared_input),
    )):
        return "FORMAL_ITEM_VERIFICATION_INPUT_MISMATCH"
    return ""


def _integrity_error_matches(error: IntegrityError, *markers: str) -> bool:
    text = f"{error} {getattr(error, 'orig', '')}".lower()
    return any(marker.lower() in text for marker in markers)


def _mapping_matches(mapping: Any, prepared: PreparedFormalItemVerificationInput, fingerprint: str) -> bool:
    return all((
        mapping.workflow_run_uid == prepared.workflow_run_uid,
        mapping.workflow_item_uid == prepared.workflow_item_uid,
        mapping.workflow_item_key == prepared.workflow_item_key,
        mapping.workflow_version == prepared.workflow_version,
        mapping.provider_name == prepared.provider_name,
        mapping.model_identity == prepared.model_identity,
        mapping.retrieval_version == prepared.retrieval_version,
        mapping.prompt_version == prepared.prompt_version,
        mapping.parser_version == prepared.parser_version,
        mapping.output_schema_version == prepared.output_schema_version,
        mapping.safe_input_fingerprint == fingerprint,
    ))


def _audit_once(
    dependencies: DocumentAlignmentItemVerificationDependencies,
    *,
    execution_key: str,
    event_type: str,
    command: ExecuteDocumentAlignmentItemVerificationCommand,
    result: str = "success",
    error_code: str = "",
    error_message: str = "",
    output_payload: dict[str, Any] | None = None,
) -> bool:
    identity = build_formal_item_audit_event_identity(execution_key, event_type)
    model = dependencies.models.audit_record
    if dependencies.session.query(model).filter_by(event_identity=identity).first() is not None:
        return False
    prepared = command.prepared_input
    dependencies.recording.create_audit(
        dependencies.session,
        model,
        {
            "event_identity": identity,
            "event_type": event_type,
            "target_type": "document_alignment_workflow_item",
            "target_uid": command.workflow_item_uid,
            "source": "formal_worker",
            "input_payload": {
                "workflow_run_uid": command.workflow_run_uid,
                "workflow_item_uid": command.workflow_item_uid,
                "source_uid": prepared.source_uid,
                "english_evidence_refs": list(prepared.english_evidence_refs),
                "chinese_evidence_refs": list(prepared.chinese_evidence_refs),
            },
            "output_payload": output_payload or {},
            "changed_fields": [],
            "result": result,
            "error_code": error_code,
            "error_message": _safe_error(error_message, "Formal item verification failed.") if error_code else "",
            "model_name": prepared.model_identity,
            "prompt_version": prepared.prompt_version,
            "retrieval_version": prepared.retrieval_version,
        },
        audit_context={"source": "formal_worker"},
        now_fn=lambda: _time_text(dependencies.current_time_factory()),
        commit=False,
    )
    return True


def _in_memory_verification_input(prepared: PreparedFormalItemVerificationInput, card_uid: str) -> dict[str, Any]:
    english_snippets = {snippet.reference_id: snippet.text for snippet in prepared.english_snippets}
    chinese_snippets = {snippet.reference_id: snippet.text for snippet in prepared.chinese_snippets}

    def evidence(reference: str, language: str, snippets: dict[str, str]):
        return {
            "chunk_uid": reference,
            "source_uid": prepared.source_uid,
            "course": prepared.course,
            "chapter": prepared.chapter,
            "language": language,
            "trust_level": "governed",
            "quality_status": "governed",
            "snippet": snippets.get(reference, ""),
            "risk_labels": list(prepared.risk_labels),
        }

    chinese_term = prepared.chinese_candidate_values[0]
    return {
        "card_uid": card_uid,
        "english_term": prepared.english_term,
        "chinese_term": chinese_term,
        "course": prepared.course,
        "chapter": prepared.chapter,
        "english_evidence": [
            evidence(reference, "en", english_snippets)
            for reference in prepared.english_evidence_refs
        ],
        "chinese_evidence": [
            evidence(reference, "zh", chinese_snippets)
            for reference in prepared.chinese_evidence_refs
        ],
        "candidate_info": {
            "candidate_uid": prepared.chinese_candidate_provenance_refs[0],
            "chinese_term": chinese_term,
            "source_type": "governed_formal_workflow",
            "source_uid": prepared.source_uid,
            "risk_labels": list(prepared.risk_labels),
        },
        "chinese_term_candidates": [
            {
                "candidate_uid": reference,
                "chinese_term": value,
                "source_type": "governed_formal_workflow",
                "source_uid": prepared.source_uid,
            }
            for value, reference in zip(
                prepared.chinese_candidate_values,
                prepared.chinese_candidate_provenance_refs,
            )
        ],
        "retrieval_version": prepared.retrieval_version,
        "provider_options": {"prompt_version": prepared.prompt_version},
        "risk_labels": list(prepared.risk_labels),
        "evidence_qualification": {
            "result_id": prepared.evidence_qualification_result_id,
            "decision": prepared.evidence_qualification_decision,
            "policy": prepared.evidence_qualification_policy,
        } if prepared.evidence_qualification_result_id else None,
    }


def _result(
    command,
    *,
    outcome,
    mapping=None,
    item=None,
    provider_executed=False,
    usage_recorded=False,
    audit_events_created=0,
    reused_execution=False,
    reused_draft=False,
    reused_preflight=False,
    reused_verification=False,
    retryable=False,
    error_code="",
    error_message="",
    risk_labels=(),
    confidence_summary=None,
    recommendation="",
):
    return ExecuteDocumentAlignmentItemVerificationResult(
        outcome=outcome,
        workflow_run_uid=command.workflow_run_uid,
        workflow_item_uid=command.workflow_item_uid,
        execution_key=getattr(mapping, "execution_key", "") if mapping is not None else "",
        execution_status=getattr(mapping, "execution_status", "") if mapping is not None else "",
        item_status=getattr(item, "status", "") if item is not None else "",
        item_stage=getattr(item, "stage", "") if item is not None else "",
        draft_card_uid=getattr(mapping, "draft_card_uid", "") or "" if mapping is not None else "",
        preflight_run_uid=getattr(mapping, "preflight_run_uid", "") or "" if mapping is not None else "",
        verification_run_uid=getattr(mapping, "verification_run_uid", "") or "" if mapping is not None else "",
        reused_execution=reused_execution,
        reused_draft=reused_draft,
        reused_preflight=reused_preflight,
        reused_verification=reused_verification,
        provider_executed=provider_executed,
        usage_recorded=usage_recorded,
        audit_events_created=audit_events_created,
        retryable=retryable,
        risk_labels=tuple(risk_labels or ()),
        confidence_summary=confidence_summary or {},
        recommendation=recommendation,
        error_code=error_code,
        error_message=_safe_error(error_message, "Formal item verification failed.") if error_code else "",
    )


def _completed_result(command, dependencies, mapping, item):
    verification = dependencies.session.query(dependencies.models.verification_run).filter_by(
        execution_key=mapping.execution_key
    ).one_or_none()
    output = _loads_json(getattr(verification, "output_payload", "{}"), {}) if verification else {}
    usage_recorded = dependencies.session.query(dependencies.models.provider_usage).filter_by(
        execution_key=mapping.execution_key
    ).count() == 1
    return _result(
        command,
        outcome="reused_completed_result",
        mapping=mapping,
        item=item,
        reused_execution=True,
        reused_draft=bool(mapping.draft_card_uid),
        reused_preflight=bool(mapping.preflight_run_uid),
        reused_verification=bool(mapping.verification_run_uid),
        usage_recorded=usage_recorded,
        risk_labels=output.get("risk_labels", []),
        confidence_summary={
            "alignment_confidence": output.get("alignment_confidence"),
            "provider_name": mapping.provider_name,
            "model_identity": mapping.model_identity,
        },
        recommendation=str(output.get("recommendation") or "needs_review"),
    )


def _block_item(
    command,
    dependencies,
    mapping,
    item,
    *,
    outcome,
    error_code,
    execution_status=ITEM_VERIFICATION_EXECUTION_STATUS_BLOCKED,
    audit_event="item_verification_failed",
):
    mapping.execution_status = execution_status
    mapping.safe_error_code = error_code
    mapping.safe_error_message = error_code
    item.status = ITEM_STATUS_BLOCKED
    item.stage = ITEM_STAGE_TERMINAL
    item.error_code = error_code
    item.error_message = error_code
    audit_created = _audit_once(
        dependencies,
        execution_key=mapping.execution_key,
        event_type=audit_event,
        command=command,
        result="error",
        error_code=error_code,
        error_message=error_code,
    )
    dependencies.session.commit()
    return _result(
        command,
        outcome=outcome,
        mapping=mapping,
        item=item,
        audit_events_created=int(audit_created),
        error_code=error_code,
        error_message=error_code,
    )


def _hold_item_for_provider_readiness(
    command,
    dependencies,
    mapping,
    item,
):
    """Keep a non-ready item in governed review without executing a Provider."""

    error_code = "DOCUMENT_ALIGNMENT_PROVIDER_READINESS_NOT_APPROVED"
    mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_NEEDS_REVIEW
    mapping.safe_error_code = error_code
    mapping.safe_error_message = error_code
    item.status = ITEM_STATUS_NEEDS_REVIEW
    item.stage = ITEM_STAGE_TERMINAL
    item.error_code = error_code
    item.error_message = error_code
    audit_created = _audit_once(
        dependencies,
        execution_key=mapping.execution_key,
        event_type="item_provider_readiness_not_approved",
        command=command,
        result="success",
        error_code=error_code,
        error_message=error_code,
    )
    dependencies.session.commit()
    return _result(
        command,
        outcome="needs_review",
        mapping=mapping,
        item=item,
        audit_events_created=int(audit_created),
        recommendation="needs_review",
        error_code=error_code,
        error_message=error_code,
    )


def execute_document_alignment_item_verification(
    command: ExecuteDocumentAlignmentItemVerificationCommand,
    dependencies: DocumentAlignmentItemVerificationDependencies,
) -> ExecuteDocumentAlignmentItemVerificationResult:
    """Execute or recover one deterministic, lease-fenced formal item verification."""

    if not isinstance(command, ExecuteDocumentAlignmentItemVerificationCommand):
        raise TypeError("command must be ExecuteDocumentAlignmentItemVerificationCommand.")
    session = dependencies.session
    models = dependencies.models
    prepared = command.prepared_input
    fingerprint, execution_key = _execution_identity(prepared)
    reused_execution = False
    audit_count = 0

    lease_result = _lease_fence(command, dependencies)
    if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
        session.rollback()
        return _lease_rejection_result(command, lease_result)
    try:
        _, item = _load_run_item(command, dependencies)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one_or_none()
        if mapping is not None:
            reused_execution = True
            if not _mapping_matches(mapping, prepared, fingerprint):
                session.rollback()
                return _result(
                    command,
                    outcome="execution_conflict",
                    mapping=mapping,
                    item=item,
                    error_code="FORMAL_ITEM_VERIFICATION_EXECUTION_CONFLICT",
                    error_message="Formal item execution identity conflicts with persisted input.",
                )
        else:
            mapping = models.execution(
                execution_key=execution_key,
                workflow_run_uid=prepared.workflow_run_uid,
                workflow_item_uid=prepared.workflow_item_uid,
                workflow_item_key=prepared.workflow_item_key,
                execution_version=FORMAL_ITEM_VERIFICATION_EXECUTION_VERSION,
                workflow_version=prepared.workflow_version,
                provider_name=prepared.provider_name,
                model_identity=prepared.model_identity,
                retrieval_version=prepared.retrieval_version,
                prompt_version=prepared.prompt_version,
                parser_version=prepared.parser_version,
                output_schema_version=prepared.output_schema_version,
                safe_input_fingerprint=fingerprint,
                execution_status=ITEM_VERIFICATION_EXECUTION_STATUS_PREPARED,
                created_at=_time_text(dependencies.current_time_factory()),
                updated_at=_time_text(dependencies.current_time_factory()),
            )
            session.add(mapping)
            session.flush()
        if item.status == ITEM_STATUS_NEEDS_REVIEW and mapping.execution_status == ITEM_VERIFICATION_EXECUTION_STATUS_NEEDS_REVIEW:
            session.rollback()
            return _completed_result(command, dependencies, mapping, item)
        if item.status not in {
            ITEM_STATUS_EVIDENCE_READY,
            ITEM_STATUS_DRAFT_CREATED,
            ITEM_STATUS_VERIFICATION_COMPLETED,
        }:
            session.rollback()
            return _result(
                command,
                outcome="execution_conflict",
                mapping=mapping,
                item=item,
                error_code="FORMAL_ITEM_VERIFICATION_INVALID_ITEM_STATE",
                error_message="Workflow item is not in a processable verification state.",
            )
        audit_count += int(_audit_once(
            dependencies,
            execution_key=execution_key,
            event_type="item_verification_requested",
            command=command,
        ))
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if not _integrity_error_matches(
            exc,
            "document_alignment_item_verification_executions.execution_key",
            "uq_document_alignment_item_verification_execution_key",
            "audit_record.event_identity",
            "uq_audit_record_event_identity",
        ):
            return _result(
                command,
                outcome="persistence_error",
                retryable=True,
                error_code="FORMAL_ITEM_VERIFICATION_PERSISTENCE_FAILED",
                error_message="Formal item execution mapping could not be persisted.",
            )
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        _, item = _load_run_item(command, dependencies)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one_or_none()
        if mapping is None or not _mapping_matches(mapping, prepared, fingerprint):
            session.rollback()
            return _result(
                command,
                outcome="execution_conflict",
                mapping=mapping,
                item=item,
                error_code="FORMAL_ITEM_VERIFICATION_EXECUTION_CONFLICT",
                error_message="Formal item execution identity could not be recovered.",
            )
        session.commit()
        reused_execution = True
    except Exception as exc:
        session.rollback()
        return _result(
            command,
            outcome="persistence_error",
            error_code="FORMAL_ITEM_VERIFICATION_PERSISTENCE_FAILED",
            error_message=_safe_error(exc, "Formal item execution mapping could not be persisted."),
            retryable=True,
        )

    session.expire_all()
    mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
    item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
    if item.status == ITEM_STATUS_NEEDS_REVIEW and mapping.execution_status == ITEM_VERIFICATION_EXECUTION_STATUS_NEEDS_REVIEW:
        return _completed_result(command, dependencies, mapping, item)

    reused_draft = bool(mapping.draft_card_uid)
    if not mapping.draft_card_uid:
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        _, item = _load_run_item(command, dependencies)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        try:
            draft_result = dependencies.draft.create_or_reuse(
                session,
                models.concept_card,
                english_term=prepared.english_term,
                chinese_term=prepared.chinese_candidate_values[0],
                course=prepared.course,
                chapter=prepared.chapter,
                retrieval_version=prepared.retrieval_version,
                english_evidence_refs=prepared.english_evidence_refs,
                chinese_evidence_refs=prepared.chinese_evidence_refs,
                risk_labels=prepared.risk_labels,
                now_fn=lambda: _time_text(dependencies.current_time_factory()),
            )
        except Exception as exc:
            session.rollback()
            mapping = session.query(models.execution).filter_by(execution_key=execution_key).one_or_none()
            item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one_or_none()
            return _result(
                command,
                outcome="persistence_error",
                mapping=mapping,
                item=item,
                reused_execution=reused_execution,
                retryable=True,
                error_code="FORMAL_ITEM_VERIFICATION_PERSISTENCE_FAILED",
                error_message=_safe_error(exc, "Formal draft could not be persisted."),
            )
        if draft_result.outcome == "approved_protected":
            mapping.draft_card_uid = draft_result.card.card_uid
            item.draft_card_uid = draft_result.card.card_uid
            return _block_item(
                command,
                dependencies,
                mapping,
                item,
                outcome="approved_card_protected",
                error_code="DOCUMENT_ALIGNMENT_APPROVED_CARD_PROTECTED",
            )
        if draft_result.outcome == "conflict":
            return _block_item(
                command,
                dependencies,
                mapping,
                item,
                outcome="attach_blocked",
                error_code="DOCUMENT_ALIGNMENT_DRAFT_CONFLICT",
            )
        mapping.draft_card_uid = draft_result.card.card_uid
        mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_DRAFT_READY
        item.draft_card_uid = draft_result.card.card_uid
        item.status = ITEM_STATUS_DRAFT_CREATED
        item.stage = ITEM_STAGE_DRAFT_CREATION
        session.commit()
        reused_draft = draft_result.reused

    if dependencies.evaluate_provider_readiness is not None:
        readiness = dependencies.evaluate_provider_readiness(
            prepared,
            session=session,
            policy_model=models.provider_policy,
            execution_key=execution_key,
        )
        if not bool(getattr(readiness, "execution_admission", False)):
            lease_result = _lease_fence(command, dependencies)
            if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
                session.rollback()
                return _lease_rejection_result(command, lease_result)
            mapping = session.query(models.execution).filter_by(
                execution_key=execution_key
            ).one()
            item = session.query(models.workflow_item).filter_by(
                item_uid=command.workflow_item_uid
            ).one()
            return _hold_item_for_provider_readiness(
                command,
                dependencies,
                mapping,
                item,
            )

    verification_input = dependencies.verification.validate_input(
        _in_memory_verification_input(prepared, mapping.draft_card_uid)
    )
    provider_type = dependencies.governance.provider_type_for(prepared.provider_name)
    evaluation_external_allowed = (
        provider_type == "external_llm"
        and is_trusted_formal_real_provider_evaluation_context(
            dependencies.evaluation_context,
            provider_name=prepared.provider_name,
            model_identity=prepared.model_identity,
        )
    )
    if provider_type not in _ALLOWED_PROVIDER_TYPES and not evaluation_external_allowed:
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
        return _block_item(
            command,
            dependencies,
            mapping,
            item,
            outcome="provider_policy_blocked",
            error_code="DOCUMENT_ALIGNMENT_PROVIDER_POLICY_BLOCKED",
        )

    gate = dependencies.governance.evaluate_policy(
        session,
        models.provider_policy,
        models.provider_usage,
        prepared.provider_name,
        verification_input,
        actor_role=dependencies.actor_role,
        now_fn=lambda: _time_text(dependencies.current_time_factory()),
    )
    if not gate.get("allowed"):
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
        return _block_item(
            command,
            dependencies,
            mapping,
            item,
            outcome="provider_policy_blocked",
            error_code="DOCUMENT_ALIGNMENT_PROVIDER_POLICY_BLOCKED",
        )

    preflight = session.query(models.preflight_run).filter_by(execution_key=execution_key).one_or_none()
    reused_preflight = preflight is not None
    if preflight is None:
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
        try:
            preflight_kwargs = {
                "course": prepared.course,
                "include_replay_dry_run": True,
                "execution_key": execution_key,
                "now_fn": lambda: _time_text(dependencies.current_time_factory()),
                "commit": False,
            }
            if dependencies.evaluation_context is not None:
                preflight_kwargs["evaluation_context"] = dependencies.evaluation_context
            preflight, report = dependencies.governance.run_preflight(
                session,
                models.preflight_run,
                models.provider_policy,
                prepared.provider_name,
                **preflight_kwargs,
            )
            mapping.preflight_run_uid = preflight.preflight_uid
            if not report.get("overall_ready"):
                mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_BLOCKED
                return _block_item(
                    command,
                    dependencies,
                    mapping,
                    item,
                    outcome="provider_preflight_blocked",
                    error_code="DOCUMENT_ALIGNMENT_PROVIDER_PREFLIGHT_BLOCKED",
                    execution_status=ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_BLOCKED,
                    audit_event="item_verification_preflight_blocked",
                )
            mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_PASSED
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if not _integrity_error_matches(
                exc,
                "alignment_provider_preflight_run.execution_key",
                "uq_alignment_provider_preflight_execution_key",
            ):
                return _result(
                    command,
                    outcome="persistence_error",
                    mapping=mapping,
                    item=item,
                    retryable=True,
                    error_code="FORMAL_ITEM_VERIFICATION_PERSISTENCE_FAILED",
                    error_message="Formal preflight could not be persisted.",
                )
            lease_result = _lease_fence(command, dependencies)
            if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
                session.rollback()
                return _lease_rejection_result(command, lease_result)
            preflight = session.query(models.preflight_run).filter_by(execution_key=execution_key).one_or_none()
            mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
            item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
            if preflight is None:
                session.rollback()
                return _result(
                    command,
                    outcome="persistence_error",
                    mapping=mapping,
                    item=item,
                    retryable=True,
                    error_code="FORMAL_ITEM_VERIFICATION_PERSISTENCE_FAILED",
                    error_message="Formal preflight identity conflict could not be recovered.",
                )
            mapping.preflight_run_uid = preflight.preflight_uid
            if mapping.execution_status in {
                ITEM_VERIFICATION_EXECUTION_STATUS_PREPARED,
                ITEM_VERIFICATION_EXECUTION_STATUS_DRAFT_READY,
                ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_PASSED,
            }:
                mapping.execution_status = (
                    ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_PASSED
                    if preflight.overall_ready
                    else ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_BLOCKED
                )
            session.commit()
            reused_preflight = True
    elif not bool(preflight.overall_ready):
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
        return _block_item(
            command,
            dependencies,
            mapping,
            item,
            outcome="provider_preflight_blocked",
            error_code="DOCUMENT_ALIGNMENT_PROVIDER_PREFLIGHT_BLOCKED",
            execution_status=ITEM_VERIFICATION_EXECUTION_STATUS_PREFLIGHT_BLOCKED,
            audit_event="item_verification_preflight_blocked",
        )

    verification = session.query(models.verification_run).filter_by(execution_key=execution_key).one_or_none()
    provider_executed = False
    usage_recorded = session.query(models.provider_usage).filter_by(execution_key=execution_key).count() == 1
    reused_verification = verification is not None
    output = _loads_json(getattr(verification, "output_payload", "{}"), {}) if verification is not None else {}
    if verification is None:
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_PROVIDER_STARTED
        mapping.provider_started_at = _time_text(dependencies.current_time_factory())
        session.commit()

        try:
            provider = dependencies.verification.resolve_provider(prepared.provider_name)
            output = provider.verify_alignment(verification_input)
            provider_executed = True
        except Exception as exc:
            session.rollback()
            lease_result = _lease_fence(command, dependencies)
            if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
                session.rollback()
                return _lease_rejection_result(command, lease_result)
            mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
            item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
            mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_FAILED
            mapping.safe_error_code = "DOCUMENT_ALIGNMENT_VERIFICATION_FAILED"
            mapping.safe_error_message = _safe_error(exc, "Formal deterministic provider failed.")
            item.status = ITEM_STATUS_FAILED
            item.stage = ITEM_STAGE_TERMINAL
            item.error_code = "DOCUMENT_ALIGNMENT_VERIFICATION_FAILED"
            item.error_message = _safe_error(exc, "Formal deterministic provider failed.")
            audit_count += int(_audit_once(
                dependencies,
                execution_key=execution_key,
                event_type="item_verification_failed",
                command=command,
                result="error",
                error_code="DOCUMENT_ALIGNMENT_VERIFICATION_FAILED",
                error_message="Formal deterministic provider failed.",
            ))
            session.commit()
            return _result(
                command,
                outcome="verification_failed",
                mapping=mapping,
                item=item,
                provider_executed=provider_executed,
                audit_events_created=audit_count,
                retryable=False,
                error_code="DOCUMENT_ALIGNMENT_VERIFICATION_FAILED",
                error_message="Formal deterministic provider failed.",
            )

        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
        mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_PROVIDER_COMPLETED
        mapping.safe_output_fingerprint = _safe_output_fingerprint(output)
        mapping.provider_completed_at = _time_text(dependencies.current_time_factory())
        session.commit()

        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
        try:
            verification = dependencies.verification.create_safe_run(
                session,
                models.verification_run,
                verification_input,
                output,
                execution_key=execution_key,
                card_uid=mapping.draft_card_uid,
                now_fn=lambda: _time_text(dependencies.current_time_factory()),
            )
            persisted_output = _loads_json(getattr(verification, "output_payload", "{}"), {})
            usage = session.query(models.provider_usage).filter_by(execution_key=execution_key).one_or_none()
            if usage is None:
                usage = dependencies.recording.record_usage(
                    session,
                    models.provider_usage,
                    prepared.provider_name,
                    execution_key=execution_key,
                    run_uid=verification.run_uid,
                    input_summary={
                        "card_uid": mapping.draft_card_uid,
                        "course": prepared.course,
                        "chapter": prepared.chapter,
                        "estimated_cost": persisted_output.get("estimated_cost", {}),
                    },
                    result_summary={
                        "run_uid": verification.run_uid,
                        "card_uid": mapping.draft_card_uid,
                        "provider_type": verification.provider_type or provider_type,
                        "provider_response_status": verification.provider_response_status or "completed",
                        "estimated_cost": persisted_output.get("estimated_cost", {}),
                        "error_code": verification.error_code or "",
                        "error_message": verification.error_message or "",
                    },
                    audit_context={"source": "formal_worker"},
                    now_fn=lambda: _time_text(dependencies.current_time_factory()),
                    commit=False,
                )
                usage_recorded = True
            mapping.verification_run_uid = verification.run_uid
            mapping.safe_output_fingerprint = _safe_output_fingerprint(output)
            mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_VERIFICATION_PERSISTED
            item.verification_run_uid = verification.run_uid
            item.status = ITEM_STATUS_VERIFICATION_COMPLETED
            item.stage = ITEM_STAGE_VERIFICATION
            audit_count += int(_audit_once(
                dependencies,
                execution_key=execution_key,
                event_type="item_verification_provider_completed",
                command=command,
                output_payload={
                    "verification_run_uid": verification.run_uid,
                    "provider_name": prepared.provider_name,
                    "provider_response_status": verification.provider_response_status or "completed",
                },
            ))
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if not _integrity_error_matches(
                exc,
                "alignment_verification_run.execution_key",
                "uq_alignment_verification_run_execution_key",
                "alignment_provider_usage_record.execution_key",
                "uq_alignment_provider_usage_execution_key",
                "audit_record.event_identity",
                "uq_audit_record_event_identity",
            ):
                return _result(
                    command,
                    outcome="persistence_error",
                    mapping=mapping,
                    item=item,
                    provider_executed=provider_executed,
                    retryable=True,
                    error_code="FORMAL_ITEM_VERIFICATION_PERSISTENCE_FAILED",
                    error_message="Formal provider result could not be persisted.",
                )
            lease_result = _lease_fence(command, dependencies)
            if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
                session.rollback()
                return _lease_rejection_result(command, lease_result)
            mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
            item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
            verification = session.query(models.verification_run).filter_by(execution_key=execution_key).one_or_none()
            if verification is None:
                session.rollback()
                return _result(
                    command,
                    outcome="persistence_error",
                    mapping=mapping,
                    item=item,
                    provider_executed=provider_executed,
                    retryable=True,
                    error_code="FORMAL_ITEM_VERIFICATION_PERSISTENCE_FAILED",
                    error_message="Formal verification identity conflict could not be recovered.",
                )
            mapping.verification_run_uid = verification.run_uid
            item.verification_run_uid = verification.run_uid
            item.status = ITEM_STATUS_VERIFICATION_COMPLETED
            item.stage = ITEM_STAGE_VERIFICATION
            mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_VERIFICATION_PERSISTED
            session.commit()
            reused_verification = True
        except Exception as exc:
            session.rollback()
            mapping = session.query(models.execution).filter_by(execution_key=execution_key).one_or_none()
            item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one_or_none()
            return _result(
                command,
                outcome="persistence_error",
                mapping=mapping,
                item=item,
                provider_executed=provider_executed,
                retryable=True,
                error_code="FORMAL_ITEM_VERIFICATION_PERSISTENCE_FAILED",
                error_message=_safe_error(
                    exc,
                    "Formal provider result could not be persisted.",
                ),
            )

    verification = session.query(models.verification_run).filter_by(execution_key=execution_key).one()
    output = _loads_json(getattr(verification, "output_payload", "{}"), {})
    usage_recorded = session.query(models.provider_usage).filter_by(execution_key=execution_key).count() == 1
    if str(output.get("provider_response_status") or "") == "parse_failed" or str(output.get("error_code") or "").startswith("provider_"):
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
        mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_FAILED
        mapping.safe_error_code = "DOCUMENT_ALIGNMENT_VERIFICATION_PARSE_FAILED"
        mapping.safe_error_message = "Formal verification output could not be parsed."
        item.status = ITEM_STATUS_FAILED
        item.stage = ITEM_STAGE_TERMINAL
        item.error_code = "DOCUMENT_ALIGNMENT_VERIFICATION_PARSE_FAILED"
        item.error_message = "Formal verification output could not be parsed."
        audit_count += int(_audit_once(
            dependencies,
            execution_key=execution_key,
            event_type="item_verification_failed",
            command=command,
            result="error",
            error_code="DOCUMENT_ALIGNMENT_VERIFICATION_PARSE_FAILED",
            error_message="Formal verification output could not be parsed.",
        ))
        session.commit()
        return _result(
            command,
            outcome="parser_failed",
            mapping=mapping,
            item=item,
            provider_executed=provider_executed,
            usage_recorded=usage_recorded,
            audit_events_created=audit_count,
            error_code="DOCUMENT_ALIGNMENT_VERIFICATION_PARSE_FAILED",
            error_message="Formal verification output could not be parsed.",
        )

    lease_result = _lease_fence(command, dependencies)
    if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
        session.rollback()
        return _lease_rejection_result(command, lease_result)
    mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
    item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
    verification = session.query(models.verification_run).filter_by(execution_key=execution_key).one()
    card = session.query(models.concept_card).filter_by(card_uid=mapping.draft_card_uid).one()
    policy = session.query(models.provider_policy).filter_by(provider_name=prepared.provider_name).one_or_none()
    if getattr(card, "status", "") == "approved" or not dependencies.governance.can_attach(verification, policy):
        mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_ATTACH_PENDING
        item.status = ITEM_STATUS_VERIFICATION_COMPLETED
        item.stage = ITEM_STAGE_VERIFICATION
        audit_count += int(_audit_once(
            dependencies,
            execution_key=execution_key,
            event_type="item_verification_failed",
            command=command,
            result="error",
            error_code="DOCUMENT_ALIGNMENT_ATTACH_BLOCKED",
            error_message="Formal verification attach is blocked.",
        ))
        session.commit()
        return _result(
            command,
            outcome="attach_blocked",
            mapping=mapping,
            item=item,
            provider_executed=provider_executed,
            usage_recorded=usage_recorded,
            audit_events_created=audit_count,
            reused_execution=reused_execution,
            reused_draft=reused_draft,
            reused_preflight=reused_preflight,
            reused_verification=reused_verification,
            error_code="DOCUMENT_ALIGNMENT_ATTACH_BLOCKED",
            error_message="Formal verification attach is blocked.",
        )
    try:
        mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_ATTACH_PENDING
        attach_result = dependencies.verification.attach(
            session,
            models.concept_card,
            verification,
            mode="attach_only",
            now_fn=lambda: _time_text(dependencies.current_time_factory()),
        )
        if getattr(attach_result, "outcome", "") in {"approved_protected", "conflict"}:
            mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_ATTACH_PENDING
            item.status = ITEM_STATUS_VERIFICATION_COMPLETED
            item.stage = ITEM_STAGE_VERIFICATION
            audit_count += int(_audit_once(
                dependencies,
                execution_key=execution_key,
                event_type="item_verification_failed",
                command=command,
                result="error",
                error_code="DOCUMENT_ALIGNMENT_ATTACH_BLOCKED",
                error_message="Formal verification attach is blocked.",
            ))
            session.commit()
            return _result(
                command,
                outcome="attach_blocked",
                mapping=mapping,
                item=item,
                provider_executed=provider_executed,
                usage_recorded=usage_recorded,
                audit_events_created=audit_count,
                reused_execution=reused_execution,
                reused_draft=reused_draft,
                reused_preflight=reused_preflight,
                reused_verification=reused_verification,
                error_code="DOCUMENT_ALIGNMENT_ATTACH_BLOCKED",
                error_message="Formal verification attach is blocked.",
            )
        mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_NEEDS_REVIEW
        mapping.attached_at = _time_text(dependencies.current_time_factory())
        item.status = ITEM_STATUS_NEEDS_REVIEW
        item.stage = ITEM_STAGE_TERMINAL
        item.risk_labels = output.get("risk_labels", [])
        item.confidence_score = output.get("alignment_confidence")
        item.confidence_summary = {
            "alignment_confidence": output.get("alignment_confidence"),
            "provider_name": prepared.provider_name,
            "model_identity": prepared.model_identity,
        }
        item.recommendation = str(output.get("recommendation") or "needs_review")
        item.error_code = ""
        item.error_message = ""
        audit_count += int(_audit_once(
            dependencies,
            execution_key=execution_key,
            event_type="item_verification_attached",
            command=command,
            output_payload={
                "draft_card_uid": mapping.draft_card_uid,
                "verification_run_uid": mapping.verification_run_uid,
                "item_status": ITEM_STATUS_NEEDS_REVIEW,
            },
        ))
        session.commit()
    except Exception as exc:
        session.rollback()
        lease_result = _lease_fence(command, dependencies)
        if lease_result.outcome != LEASE_OUTCOME_ACCEPTED:
            session.rollback()
            return _lease_rejection_result(command, lease_result)
        mapping = session.query(models.execution).filter_by(execution_key=execution_key).one()
        item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one()
        mapping.execution_status = ITEM_VERIFICATION_EXECUTION_STATUS_ATTACH_PENDING
        mapping.safe_error_code = "DOCUMENT_ALIGNMENT_ATTACH_PENDING"
        mapping.safe_error_message = "Formal verification attach must be retried."
        item.status = ITEM_STATUS_VERIFICATION_COMPLETED
        item.stage = ITEM_STAGE_VERIFICATION
        audit_count += int(_audit_once(
            dependencies,
            execution_key=execution_key,
            event_type="item_verification_failed",
            command=command,
            result="error",
            error_code="DOCUMENT_ALIGNMENT_ATTACH_PENDING",
            error_message="Formal verification attach must be retried.",
        ))
        session.commit()
        return _result(
            command,
            outcome="attach_pending",
            mapping=mapping,
            item=item,
            provider_executed=provider_executed,
            usage_recorded=usage_recorded,
            audit_events_created=audit_count,
            reused_execution=reused_execution,
            reused_draft=reused_draft,
            reused_preflight=reused_preflight,
            reused_verification=reused_verification,
            retryable=True,
            error_code="DOCUMENT_ALIGNMENT_ATTACH_PENDING",
            error_message=_safe_error(exc, "Formal verification attach must be retried."),
        )
    return _result(
        command,
        outcome="needs_review",
        mapping=mapping,
        item=item,
        provider_executed=provider_executed,
        usage_recorded=usage_recorded,
        audit_events_created=audit_count,
        reused_execution=reused_execution,
        reused_draft=reused_draft,
        reused_preflight=reused_preflight,
        reused_verification=reused_verification,
        risk_labels=output.get("risk_labels", []),
        confidence_summary={
            "alignment_confidence": output.get("alignment_confidence"),
            "provider_name": prepared.provider_name,
            "model_identity": prepared.model_identity,
        },
        recommendation=str(output.get("recommendation") or "needs_review"),
    )
