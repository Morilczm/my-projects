"""Governed evidence and Chinese-candidate preparation for one workflow item."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from services import alignment_providers
from services.alignment_output_parser import OUTPUT_SCHEMA_VERSION, PARSER_VERSION
from services.bilingual_evidence_workflow import BILINGUAL_RETRIEVAL_VERSION, BilingualEvidenceResult
from services.document_alignment_item_verification_adapter import (
    PreparedEvidenceSnippet,
    PreparedFormalItemVerificationInput,
)
from services.formal_document_alignment_provider_selection import (
    FORMAL_DEFAULT_PROVIDER_NAME,
    FormalDocumentAlignmentProviderSelectionError,
    validate_formal_document_alignment_provider_selection,
)


PREPARATION_OUTCOME_PREPARED = "prepared"
PREPARATION_OUTCOME_EVIDENCE_INSUFFICIENT = "evidence_insufficient"
PREPARATION_OUTCOME_EVIDENCE_QUALIFICATION_REQUIRED = "evidence_qualification_required"
PREPARATION_OUTCOME_CHINESE_CANDIDATE_UNAVAILABLE = "chinese_candidate_unavailable"
PREPARATION_OUTCOME_SOURCE_CHANGED = "source_changed"
PREPARATION_OUTCOME_CHUNK_NOT_AVAILABLE = "chunk_not_available"
PREPARATION_OUTCOME_PROVIDER_SELECTION_MISSING = "provider_selection_missing"
PREPARATION_OUTCOME_PROVIDER_SELECTION_INVALID = "provider_selection_invalid"
PREPARATION_OUTCOME_FAILED = "preparation_failed"

_SAFE_MARKERS = (
    "LEXIBRIDGE_SENTINEL_SECRET",
    "Authorization:",
    "Cookie:",
    "Bearer ",
    "sk-",
)


def _required_text(value: Any, field_name: str, max_length: int = 500) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} is too long.")
    return text


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    if any(marker in text for marker in _SAFE_MARKERS):
        return ""
    return text


@dataclass(frozen=True)
class PrepareDocumentAlignmentItemCommand:
    workflow_run_uid: str
    workflow_item_uid: str

    def __post_init__(self):
        object.__setattr__(
            self,
            "workflow_run_uid",
            _required_text(self.workflow_run_uid, "workflow_run_uid", 64),
        )
        object.__setattr__(
            self,
            "workflow_item_uid",
            _required_text(self.workflow_item_uid, "workflow_item_uid", 64),
        )


@dataclass(frozen=True)
class PrepareDocumentAlignmentItemResult:
    outcome: str
    workflow_run_uid: str
    workflow_item_uid: str
    prepared_input: PreparedFormalItemVerificationInput | None = field(default=None, repr=False)
    english_evidence_refs: tuple[str, ...] = ()
    chinese_evidence_refs: tuple[str, ...] = ()
    chinese_candidate_values: tuple[str, ...] = ()
    chinese_candidate_provenance_refs: tuple[str, ...] = ()
    risk_labels: tuple[str, ...] = ()
    candidate_count: int = 0
    retryable: bool = False
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self):
        object.__setattr__(self, "outcome", _required_text(self.outcome, "outcome", 80))
        object.__setattr__(
            self,
            "workflow_run_uid",
            _required_text(self.workflow_run_uid, "workflow_run_uid", 64),
        )
        object.__setattr__(
            self,
            "workflow_item_uid",
            _required_text(self.workflow_item_uid, "workflow_item_uid", 64),
        )
        count = int(self.candidate_count or 0)
        if count < 0:
            raise ValueError("candidate_count must be non-negative.")
        object.__setattr__(self, "candidate_count", count)
        object.__setattr__(self, "error_code", str(self.error_code or "")[:120])
        message = _safe_text(self.error_message)
        object.__setattr__(
            self,
            "error_message",
            message[:500] if message else ("Item preparation failed safely." if self.error_message else ""),
        )


@dataclass(frozen=True)
class DocumentAlignmentItemPreparationModels:
    workflow_run: Any
    workflow_item: Any
    source: Any
    chunk: Any
    concept_card: Any


@dataclass(frozen=True)
class DocumentAlignmentItemPreparationDependencies:
    session: Any
    models: DocumentAlignmentItemPreparationModels
    candidate_generator: Callable[..., Any]
    evidence_retriever: Callable[..., BilingualEvidenceResult]
    retrieval_version: str = ""
    parser_version: str = PARSER_VERSION
    output_schema_version: str = OUTPUT_SCHEMA_VERSION
    evidence_limit: int = 5
    candidate_limit: int = 10
    evaluation_context: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        for name in (
            "parser_version",
            "output_schema_version",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name, 160))
        for name in ("evidence_limit", "candidate_limit"):
            value = int(getattr(self, name) or 0)
            if value <= 0:
                raise ValueError(f"{name} must be positive.")
            object.__setattr__(self, name, value)


def select_primary_chinese_candidate(candidates: list[dict[str, Any]] | tuple[dict[str, Any], ...]):
    safe_candidates = []
    for candidate in candidates or ():
        value = _safe_text(candidate.get("chinese_term"))
        reference = _safe_text(candidate.get("candidate_uid"))
        if not value or not reference:
            continue
        item = dict(candidate)
        item["chinese_term"] = value
        item["candidate_uid"] = reference
        safe_candidates.append(item)
    if not safe_candidates:
        return None
    return sorted(
        safe_candidates,
        key=lambda item: (
            -float(item.get("score") or 0.0),
            str(item.get("candidate_uid") or ""),
            str(item.get("chinese_term") or "").casefold(),
        ),
    )[0]


def _loads_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, (tuple, list)):
        loaded = value
    else:
        try:
            loaded = json.loads(value or "[]")
        except (TypeError, ValueError):
            loaded = []
    if not isinstance(loaded, list):
        return ()
    return tuple(sorted({str(item or "").strip() for item in loaded if str(item or "").strip()}))


def _labels(*groups: Any) -> tuple[str, ...]:
    values = set()
    for group in groups:
        if isinstance(group, str):
            group = _loads_list(group)
        for value in group or ():
            text = str(value or "").strip()
            if text and not any(marker in text for marker in _SAFE_MARKERS):
                values.add(text)
    return tuple(sorted(values))


def _candidate_ref(candidate: dict[str, Any]) -> str:
    return _safe_text(candidate.get("candidate_uid"))


def _evidence_ref(candidate: dict[str, Any]) -> str:
    return _safe_text(candidate.get("chunk_uid") or candidate.get("evidence_uid"))


def _bounded_snippets(candidates: list[dict[str, Any]]) -> tuple[PreparedEvidenceSnippet, ...]:
    snippets = []
    seen = set()
    for candidate in candidates:
        reference = _evidence_ref(candidate)
        text = str(candidate.get("snippet") or candidate.get("evidence_snippet") or "").strip()
        if not reference or not text or reference in seen:
            continue
        snippets.append(PreparedEvidenceSnippet(reference, text[:500]))
        seen.add(reference)
    return tuple(snippets)


def _result(command: PrepareDocumentAlignmentItemCommand, outcome: str, **values):
    return PrepareDocumentAlignmentItemResult(
        outcome=outcome,
        workflow_run_uid=command.workflow_run_uid,
        workflow_item_uid=command.workflow_item_uid,
        **values,
    )


def _load_scope(command, dependencies):
    session = dependencies.session
    models = dependencies.models
    run = session.query(models.workflow_run).filter_by(run_uid=command.workflow_run_uid).one_or_none()
    item = session.query(models.workflow_item).filter_by(item_uid=command.workflow_item_uid).one_or_none()
    if run is None or item is None or item.workflow_run_id != getattr(run, "id", None):
        return None
    source = session.query(models.source).filter_by(source_uid=run.source_uid).one_or_none()
    if not all((
        source is not None,
        str(getattr(source, "parse_uid", "") or "") == str(run.parse_uid),
        str(getattr(source, "version", "") or "") == str(run.source_version or ""),
        str(getattr(source, "status", "") or "") == "active",
        str(getattr(source, "quality_status", "") or "")
        in {"ready", "native_text_ok", "ocr_text_ok", "partial_text"},
    )):
        return (run, item, None, ())
    refs = _loads_list(item.source_chunk_refs)
    chunks = (
        session.query(models.chunk)
        .filter(models.chunk.chunk_uid.in_(refs))
        .order_by(models.chunk.chunk_index, models.chunk.chunk_uid)
        .all()
        if refs else []
    )
    valid = len(chunks) == len(refs) and all(
        str(chunk.source_uid or "") == str(run.source_uid)
        and str(chunk.parse_uid or "") == str(run.parse_uid)
        and str(chunk.status or "") == "active"
        and bool(chunk.is_active)
        for chunk in chunks
    )
    return (run, item, source, tuple(chunks) if valid else ())


def _persisted_provider_selection(run: Any, evaluation_context: Any = None) -> tuple[str, str, str]:
    provider_name = str(getattr(run, "provider_preference", "") or "").strip()
    model_identity = str(getattr(run, "model_preference", "") or "").strip()
    prompt_version = str(getattr(run, "prompt_version", "") or "").strip()
    if not all((provider_name, model_identity, prompt_version)):
        raise LookupError("Formal workflow provider selection is missing.")
    try:
        provider = alignment_providers.get_alignment_provider(provider_name)
    except alignment_providers.AlignmentProviderError as exc:
        raise ValueError("Formal workflow provider selection is invalid.") from exc
    if (
        provider.provider_type in {"mock", "fake_llm", "replay_llm"}
        and not bool(getattr(provider, "supports_external_calls", False))
    ):
        if provider_name == FORMAL_DEFAULT_PROVIDER_NAME:
            try:
                validate_formal_document_alignment_provider_selection(
                    provider_name=provider_name,
                    model_identity=model_identity,
                    prompt_version=prompt_version,
                )
            except FormalDocumentAlignmentProviderSelectionError as exc:
                raise ValueError("Formal workflow provider selection is invalid.") from exc
    else:
        try:
            validate_formal_document_alignment_provider_selection(
                provider_name=provider_name,
                model_identity=model_identity,
                prompt_version=prompt_version,
                evaluation_context=evaluation_context,
            )
        except FormalDocumentAlignmentProviderSelectionError as exc:
            raise ValueError("Formal workflow provider selection is invalid.") from exc
    return provider_name, model_identity, prompt_version


def validate_document_alignment_prepared_scope(
    command: PrepareDocumentAlignmentItemCommand,
    dependencies: DocumentAlignmentItemPreparationDependencies,
    prepared: PreparedFormalItemVerificationInput,
) -> bool:
    loaded = _load_scope(command, dependencies)
    if loaded is None:
        return False
    run, item, source, chunks = loaded
    return bool(
        source
        and chunks
        and prepared.workflow_run_uid == str(run.run_uid)
        and prepared.workflow_item_uid == str(item.item_uid)
        and prepared.workflow_item_key == str(item.item_key)
        and prepared.english_term == str(item.candidate_term)
        and prepared.source_uid == str(run.source_uid)
        and prepared.source_version == str(run.source_version or "")
        and prepared.workflow_version == str(run.workflow_version)
        and set(_loads_list(item.source_chunk_refs)) == {str(chunk.chunk_uid) for chunk in chunks}
    )


def prepare_document_alignment_item(
    command: PrepareDocumentAlignmentItemCommand,
    dependencies: DocumentAlignmentItemPreparationDependencies,
) -> PrepareDocumentAlignmentItemResult:
    session = dependencies.session
    try:
        loaded = _load_scope(command, dependencies)
        if loaded is None:
            session.rollback()
            return _result(
                command,
                PREPARATION_OUTCOME_SOURCE_CHANGED,
                error_code="DOCUMENT_ALIGNMENT_RUN_NOT_FOUND",
                error_message="Formal workflow run or item is not available.",
            )
        run, item, source, chunks = loaded
        if source is None:
            session.rollback()
            return _result(
                command,
                PREPARATION_OUTCOME_SOURCE_CHANGED,
                error_code="DOCUMENT_ALIGNMENT_SOURCE_CHANGED",
                error_message="Governed source identity changed.",
            )
        if not chunks:
            session.rollback()
            return _result(
                command,
                PREPARATION_OUTCOME_CHUNK_NOT_AVAILABLE,
                error_code="DOCUMENT_ALIGNMENT_CHUNK_NOT_AVAILABLE",
                error_message="Governed source chunk scope is not available.",
            )

        try:
            provider_name, model_identity, prompt_version = _persisted_provider_selection(
                run,
                dependencies.evaluation_context,
            )
        except LookupError:
            session.rollback()
            return _result(
                command,
                PREPARATION_OUTCOME_PROVIDER_SELECTION_MISSING,
                error_code="DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_MISSING",
                error_message="Formal workflow provider selection is missing.",
            )
        except ValueError:
            session.rollback()
            return _result(
                command,
                PREPARATION_OUTCOME_PROVIDER_SELECTION_INVALID,
                error_code="DOCUMENT_ALIGNMENT_PROVIDER_SELECTION_INVALID",
                error_message="Formal workflow provider selection is invalid.",
            )

        candidate_result = dependencies.candidate_generator(
            session,
            concept_card_model=dependencies.models.concept_card,
            term_model=None,
            terminology_card_model=None,
            chunk_model=dependencies.models.chunk,
            source_model=dependencies.models.source,
            english_term=item.candidate_term,
            course=run.course,
            chapter=run.chapter,
            limit=dependencies.candidate_limit,
            filters={"include_low_quality": False, "include_needs_review": False},
        )
        candidate_values = list(candidate_result.candidates)
        candidate_risk_labels = list(candidate_result.risk_labels)
        selected = select_primary_chinese_candidate(candidate_values)
        evidence = None
        if selected is None:
            english_context = " ".join(
                _safe_text(getattr(chunk, "content", ""))
                for chunk in chunks
            )[:800]
            evidence = dependencies.evidence_retriever(
                session,
                dependencies.models.chunk,
                dependencies.models.source,
                item.candidate_term,
                chinese_term="",
                course=run.course,
                chapter=run.chapter,
                limit=dependencies.evidence_limit,
                filters={"include_low_quality": False, "include_needs_review": False},
                concept_scope=item.normalized_term,
                auto_generate_chinese_candidates=False,
                candidate_limit=dependencies.candidate_limit,
                english_candidate_uid=str(item.item_uid),
                normalized_english_term=str(item.normalized_term or ""),
                english_context=english_context,
                discipline=str(getattr(source, "discipline", "") or ""),
            )
            candidate_values = list(evidence.chinese_term_candidates)
            candidate_risk_labels = list(
                _labels(candidate_risk_labels, evidence.risk_labels)
            )
            top_pair = next(iter(evidence.bilingual_pair_candidates), None)
            paired_uid = str(
                (top_pair or {}).get("chinese_candidate_uid") or ""
            )
            selected = next(
                (
                    candidate for candidate in candidate_values
                    if str(candidate.get("candidate_uid") or "") == paired_uid
                ),
                None,
            )
        if selected is None:
            session.rollback()
            return _result(
                command,
                PREPARATION_OUTCOME_CHINESE_CANDIDATE_UNAVAILABLE,
                candidate_count=len(candidate_values),
                risk_labels=_labels(item.risk_labels, candidate_risk_labels),
                error_code="DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE",
                error_message="No governed Chinese candidate is available.",
            )

        if evidence is None:
            evidence = dependencies.evidence_retriever(
                session,
                dependencies.models.chunk,
                dependencies.models.source,
                item.candidate_term,
                chinese_term=selected["chinese_term"],
                course=run.course,
                chapter=run.chapter,
                limit=dependencies.evidence_limit,
                filters={"include_low_quality": False, "include_needs_review": False},
                concept_scope=item.normalized_term,
                auto_generate_chinese_candidates=False,
            )
        source_refs = set(_loads_list(item.source_chunk_refs))
        english_candidates = [
            candidate
            for candidate in evidence.english_evidence_candidates
            if _evidence_ref(candidate) in source_refs
        ]
        chinese_candidates = list(evidence.chinese_evidence_candidates)
        english_refs = tuple(sorted({_evidence_ref(candidate) for candidate in english_candidates if _evidence_ref(candidate)}))
        chinese_refs = tuple(sorted({_evidence_ref(candidate) for candidate in chinese_candidates if _evidence_ref(candidate)}))
        candidate_ref = _candidate_ref(selected)
        risk_labels = _labels(item.risk_labels, candidate_risk_labels, evidence.risk_labels)
        qualification = getattr(evidence, "evidence_qualification", None)
        if evidence.bilingual_pair_candidates and (
            not isinstance(qualification, dict)
            or qualification.get("decision") != "QUALIFIED"
        ):
            session.rollback()
            reasons = (
                qualification.get("reason_codes", [])
                if isinstance(qualification, dict)
                else ["EVIDENCE_QUALIFICATION_INPUT_INCOMPLETE"]
            )
            return _result(
                command,
                PREPARATION_OUTCOME_EVIDENCE_QUALIFICATION_REQUIRED,
                english_evidence_refs=english_refs,
                chinese_evidence_refs=chinese_refs,
                chinese_candidate_values=(selected["chinese_term"],),
                chinese_candidate_provenance_refs=(candidate_ref,),
                risk_labels=_labels(risk_labels, reasons),
                candidate_count=len(candidate_values),
                error_code="DOCUMENT_ALIGNMENT_EVIDENCE_QUALIFICATION_REQUIRED",
                error_message="Governed bilingual evidence qualification is required.",
            )
        if not english_refs or not chinese_refs:
            session.rollback()
            return _result(
                command,
                PREPARATION_OUTCOME_EVIDENCE_INSUFFICIENT,
                english_evidence_refs=english_refs,
                chinese_evidence_refs=chinese_refs,
                chinese_candidate_values=(selected["chinese_term"],),
                chinese_candidate_provenance_refs=(candidate_ref,),
                risk_labels=risk_labels,
                candidate_count=len(candidate_values),
                error_code="DOCUMENT_ALIGNMENT_EVIDENCE_INSUFFICIENT",
                error_message="Governed bilingual evidence is insufficient.",
            )

        prepared = PreparedFormalItemVerificationInput(
            workflow_run_uid=str(run.run_uid),
            workflow_item_uid=str(item.item_uid),
            workflow_item_key=str(item.item_key),
            english_term=str(item.candidate_term),
            chinese_candidate_values=(selected["chinese_term"],),
            chinese_candidate_provenance_refs=(candidate_ref,),
            english_evidence_refs=english_refs,
            chinese_evidence_refs=chinese_refs,
            english_snippets=_bounded_snippets(english_candidates),
            chinese_snippets=_bounded_snippets(chinese_candidates),
            source_uid=str(run.source_uid),
            source_version=str(run.source_version or ""),
            course=str(run.course or ""),
            chapter=str(run.chapter or ""),
            workflow_version=str(run.workflow_version),
            retrieval_version=str(
                run.retrieval_version
                or dependencies.retrieval_version
                or BILINGUAL_RETRIEVAL_VERSION
            ),
            provider_name=provider_name,
            model_identity=model_identity,
            prompt_version=prompt_version,
            parser_version=dependencies.parser_version,
            output_schema_version=dependencies.output_schema_version,
            risk_labels=risk_labels,
            evidence_qualification_result_id=str(
                (qualification or {}).get("result_id") or ""
            ),
            evidence_qualification_decision=str(
                (qualification or {}).get("decision") or ""
            ),
            evidence_qualification_policy=(
                f"{(qualification or {}).get('policy_id')}@"
                f"{(qualification or {}).get('policy_version')}"
                if qualification
                else ""
            ),
        )
        session.rollback()
        return _result(
            command,
            PREPARATION_OUTCOME_PREPARED,
            prepared_input=prepared,
            english_evidence_refs=english_refs,
            chinese_evidence_refs=chinese_refs,
            chinese_candidate_values=prepared.chinese_candidate_values,
            chinese_candidate_provenance_refs=prepared.chinese_candidate_provenance_refs,
            risk_labels=risk_labels,
            candidate_count=len(candidate_values),
        )
    except Exception:
        session.rollback()
        return _result(
            command,
            PREPARATION_OUTCOME_FAILED,
            retryable=True,
            error_code="DOCUMENT_ALIGNMENT_INTERNAL_PROCESSING_FAILED",
            error_message="Governed item preparation failed.",
        )
