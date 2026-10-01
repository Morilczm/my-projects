"""Pure scoring helpers for Task 11E bilingual knowledge quality evaluation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


QUALITY_STATUSES = {
    "BILINGUAL_KNOWLEDGE_QUALITY_BASELINE_ESTABLISHED",
    "BILINGUAL_KNOWLEDGE_QUALITY_INSUFFICIENT",
    "BILINGUAL_KNOWLEDGE_QUALITY_VALIDATION_BLOCKED",
}

FAILURE_ATTRIBUTIONS = {
    "SOURCE_CONTENT_DEFECT",
    "INGESTION_OR_CHUNKING_DEFECT",
    "CANDIDATE_EXTRACTION_DEFECT",
    "CHINESE_CANDIDATE_DEFECT",
    "ENGLISH_RETRIEVAL_DEFECT",
    "CHINESE_RETRIEVAL_DEFECT",
    "TERM_ALIGNMENT_DEFECT",
    "EXPLANATION_GENERATION_DEFECT",
    "PROVENANCE_LOSS",
    "WORKFLOW_OR_PERSISTENCE_DEFECT",
    "PROVIDER_FAILURE",
    "EVALUATION_GOLD_AMBIGUITY",
    "UNRESOLVED_WITH_EVIDENCE",
}

QUALITY_THRESHOLDS = {
    "candidate_recall": 0.88,
    "chinese_term_top1_accuracy": 0.80,
    "chinese_term_top3_accuracy": 0.92,
    "english_hit_at_3": 0.90,
    "chinese_hit_at_3": 0.85,
    "bilingual_evidence_completeness": 0.80,
    "term_pair_accuracy": 0.80,
    "unsupported_claim_rate": 0.10,
    "critical_confusion_count": 0,
    "source_reference_completeness": 1.00,
    "chunk_reference_completeness": 1.00,
    "approve_proxy_rate": 0.60,
    "reject_proxy_rate": 0.15,
}

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
}
FULL_TEXT_KEYS = {"full_source_text", "source_text", "document_text", "raw_prompt", "raw_headers"}
SAFE_SENSITIVE_METRIC_KEYS = {"secret_exposure"}


@dataclass(frozen=True)
class GoldConcept:
    concept_id: str
    english_term: str
    accepted_chinese_terms: tuple[str, ...]
    rejected_confusions: tuple[str, ...]
    required_english_evidence_ids: tuple[str, ...]
    required_chinese_evidence_ids: tuple[str, ...]
    required_propositions: tuple[str, ...]
    forbidden_claims: tuple[str, ...]
    domain: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SystemConceptResult:
    concept_id: str
    english_term: str = ""
    chinese_term: str = ""
    chinese_candidates: tuple[str, ...] = ()
    english_evidence_ids: tuple[str, ...] = ()
    chinese_evidence_ids: tuple[str, ...] = ()
    explanation_score: int | None = None
    unsupported_claim_count: int = 0
    contradiction_count: int = 0
    source_reference_complete: bool = False
    chunk_reference_complete: bool = False
    parse_reference_complete_when_available: bool | None = None
    page_bbox_complete_when_available: bool | None = None
    provider_error: str = ""
    workflow_error: str = ""
    candidate_error: str = ""
    retrieval_error: str = ""
    provenance_error: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["raw"] = sanitize_artifact(payload.get("raw", {}))
        return payload


def normalize_term(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def chinese_term_matches(value: Any, accepted_terms: tuple[str, ...]) -> bool:
    normalized = normalize_term(value)
    return bool(normalized and normalized in {normalize_term(term) for term in accepted_terms})


def is_rejected_confusion(value: Any, rejected_confusions: tuple[str, ...]) -> bool:
    normalized = normalize_term(value)
    return bool(normalized and normalized in {normalize_term(term) for term in rejected_confusions})


def hit_at_k(retrieved_ids: tuple[str, ...] | list[str], required_ids: tuple[str, ...] | list[str], k: int) -> bool:
    if not required_ids:
        return False
    retrieved = [str(item or "").strip() for item in list(retrieved_ids or ())[: max(0, int(k))]]
    required = {str(item or "").strip() for item in required_ids if str(item or "").strip()}
    return bool(required and any(item in required for item in retrieved))


def recall_at_k(retrieved_ids: tuple[str, ...] | list[str], required_ids: tuple[str, ...] | list[str], k: int) -> float:
    required = {str(item or "").strip() for item in required_ids if str(item or "").strip()}
    if not required:
        return 0.0
    retrieved = {str(item or "").strip() for item in list(retrieved_ids or ())[: max(0, int(k))] if str(item or "").strip()}
    return len(required & retrieved) / len(required)


def score_concept(gold: GoldConcept, result: SystemConceptResult | None) -> dict[str, Any]:
    if result is None:
        return _missing_concept_result(gold)
    candidates = tuple(result.chinese_candidates or ())
    top1 = chinese_term_matches(result.chinese_term or (candidates[0] if candidates else ""), gold.accepted_chinese_terms)
    top3 = any(chinese_term_matches(candidate, gold.accepted_chinese_terms) for candidate in candidates[:3])
    candidate_surface = top3
    critical_confusion = (
        is_rejected_confusion(result.chinese_term, gold.rejected_confusions)
        or any(is_rejected_confusion(candidate, gold.rejected_confusions) for candidate in candidates[:3])
    )
    english_hit1 = hit_at_k(result.english_evidence_ids, gold.required_english_evidence_ids, 1)
    english_hit3 = hit_at_k(result.english_evidence_ids, gold.required_english_evidence_ids, 3)
    chinese_hit1 = hit_at_k(result.chinese_evidence_ids, gold.required_chinese_evidence_ids, 1)
    chinese_hit3 = hit_at_k(result.chinese_evidence_ids, gold.required_chinese_evidence_ids, 3)
    bilingual_complete = bool(english_hit3 and chinese_hit3)
    term_pair_correct = bool(top1 and not critical_confusion)
    unsupported = int(result.unsupported_claim_count or 0)
    contradictions = int(result.contradiction_count or 0)
    explanation_score = result.explanation_score if result.explanation_score is not None else 0
    review = review_proxy_decision(
        term_pair_correct=term_pair_correct,
        bilingual_evidence_complete=bilingual_complete,
        explanation_score=explanation_score,
        unsupported_claim_count=unsupported,
        contradiction_count=contradictions,
        source_reference_complete=result.source_reference_complete,
        chunk_reference_complete=result.chunk_reference_complete,
    )
    secondary = _failure_attributions(
        result,
        candidate_surface=candidate_surface,
        term_pair_correct=term_pair_correct,
        english_hit3=english_hit3,
        chinese_hit3=chinese_hit3,
        bilingual_complete=bilingual_complete,
        explanation_score=explanation_score,
        unsupported=unsupported,
        contradictions=contradictions,
    )
    primary = secondary[0] if secondary else ""
    return {
        "concept_id": gold.concept_id,
        "english_term": result.english_term or gold.english_term,
        "system_chinese_term": result.chinese_term,
        "accepted_chinese_terms": list(gold.accepted_chinese_terms),
        "candidate_recalled": candidate_surface,
        "top1_chinese_term_correct": top1,
        "top3_chinese_term_correct": top3,
        "critical_confusion": critical_confusion,
        "english_evidence_hit_at_1": english_hit1,
        "english_evidence_hit_at_3": english_hit3,
        "english_recall_at_3": recall_at_k(result.english_evidence_ids, gold.required_english_evidence_ids, 3),
        "chinese_evidence_hit_at_1": chinese_hit1,
        "chinese_evidence_hit_at_3": chinese_hit3,
        "chinese_recall_at_3": recall_at_k(result.chinese_evidence_ids, gold.required_chinese_evidence_ids, 3),
        "bilingual_evidence_complete": bilingual_complete,
        "term_pair_correct": term_pair_correct,
        "exact_term_pair_correct": term_pair_correct,
        "explanation_score": explanation_score,
        "unsupported_claim_count": unsupported,
        "contradiction_count": contradictions,
        "source_reference_complete": bool(result.source_reference_complete),
        "chunk_reference_complete": bool(result.chunk_reference_complete),
        "parse_reference_complete_when_available": result.parse_reference_complete_when_available,
        "page_bbox_complete_when_available": result.page_bbox_complete_when_available,
        "review_proxy_decision": review,
        "primary_failure_attribution": primary,
        "secondary_failure_attributions": secondary[1:] if secondary else [],
        "provider_error": result.provider_error,
        "workflow_error": result.workflow_error,
    }


def _missing_concept_result(gold: GoldConcept) -> dict[str, Any]:
    return {
        "concept_id": gold.concept_id,
        "english_term": gold.english_term,
        "system_chinese_term": "",
        "accepted_chinese_terms": list(gold.accepted_chinese_terms),
        "candidate_recalled": False,
        "top1_chinese_term_correct": False,
        "top3_chinese_term_correct": False,
        "critical_confusion": False,
        "english_evidence_hit_at_1": False,
        "english_evidence_hit_at_3": False,
        "english_recall_at_3": 0.0,
        "chinese_evidence_hit_at_1": False,
        "chinese_evidence_hit_at_3": False,
        "chinese_recall_at_3": 0.0,
        "bilingual_evidence_complete": False,
        "term_pair_correct": False,
        "exact_term_pair_correct": False,
        "explanation_score": 0,
        "unsupported_claim_count": 0,
        "contradiction_count": 0,
        "source_reference_complete": False,
        "chunk_reference_complete": False,
        "parse_reference_complete_when_available": None,
        "page_bbox_complete_when_available": None,
        "review_proxy_decision": "reject",
        "primary_failure_attribution": "WORKFLOW_OR_PERSISTENCE_DEFECT",
        "secondary_failure_attributions": [],
        "provider_error": "",
        "workflow_error": "missing_result",
    }


def _failure_attributions(
    result: SystemConceptResult,
    *,
    candidate_surface: bool,
    term_pair_correct: bool,
    english_hit3: bool,
    chinese_hit3: bool,
    bilingual_complete: bool,
    explanation_score: int,
    unsupported: int,
    contradictions: int,
) -> list[str]:
    values: list[str] = []
    if result.workflow_error:
        values.append("WORKFLOW_OR_PERSISTENCE_DEFECT")
    if result.provider_error:
        values.append("PROVIDER_FAILURE")
    if result.candidate_error:
        values.append("CANDIDATE_EXTRACTION_DEFECT")
    if not candidate_surface:
        values.append("CHINESE_CANDIDATE_DEFECT")
    if not english_hit3:
        values.append("ENGLISH_RETRIEVAL_DEFECT")
    if not chinese_hit3:
        values.append("CHINESE_RETRIEVAL_DEFECT")
    if candidate_surface and not term_pair_correct:
        values.append("TERM_ALIGNMENT_DEFECT")
    if explanation_score < 2 or unsupported > 0 or contradictions > 0:
        values.append("EXPLANATION_GENERATION_DEFECT")
    if result.provenance_error or not result.source_reference_complete or not result.chunk_reference_complete:
        values.append("PROVENANCE_LOSS")
    return _unique_ordered(values)


def review_proxy_decision(
    *,
    term_pair_correct: bool,
    bilingual_evidence_complete: bool,
    explanation_score: int,
    unsupported_claim_count: int,
    contradiction_count: int,
    source_reference_complete: bool,
    chunk_reference_complete: bool,
) -> str:
    if (
        not term_pair_correct
        or not bilingual_evidence_complete
        or unsupported_claim_count > 0
        or contradiction_count > 0
        or not source_reference_complete
        or not chunk_reference_complete
    ):
        return "reject"
    if explanation_score >= 2:
        return "approve"
    return "edit"


def compute_quality_metrics(
    gold_items: list[GoldConcept],
    results_by_concept: dict[str, SystemConceptResult],
) -> dict[str, Any]:
    scored = {
        gold.concept_id: score_concept(gold, results_by_concept.get(gold.concept_id))
        for gold in gold_items
    }
    total = len(gold_items)

    def ratio(predicate) -> float:
        if total == 0:
            return 0.0
        return sum(1 for item in scored.values() if predicate(item)) / total

    approve = sum(1 for item in scored.values() if item["review_proxy_decision"] == "approve")
    edit = sum(1 for item in scored.values() if item["review_proxy_decision"] == "edit")
    reject = sum(1 for item in scored.values() if item["review_proxy_decision"] == "reject")
    unsupported_total = sum(int(item["unsupported_claim_count"] or 0) for item in scored.values())
    metrics = {
        "evaluated_concept_count": total,
        "result_count": len(results_by_concept),
        "missing_result_count": max(0, total - len(results_by_concept)),
        "candidate_recall": ratio(lambda item: item["candidate_recalled"]),
        "candidate_precision": _candidate_precision(scored),
        "missing_concept_count": sum(1 for item in scored.values() if not item["candidate_recalled"]),
        "duplicate_candidate_count": 0,
        "chinese_term_top1_accuracy": ratio(lambda item: item["top1_chinese_term_correct"]),
        "chinese_term_top3_accuracy": ratio(lambda item: item["top3_chinese_term_correct"]),
        "wrong_term_rate": ratio(lambda item: bool(item["system_chinese_term"]) and not item["top1_chinese_term_correct"]),
        "missing_term_rate": ratio(lambda item: not item["system_chinese_term"]),
        "confusion_rate": ratio(lambda item: item["critical_confusion"]),
        "english_hit_at_1": ratio(lambda item: item["english_evidence_hit_at_1"]),
        "english_hit_at_3": ratio(lambda item: item["english_evidence_hit_at_3"]),
        "english_recall_at_3": _average(item["english_recall_at_3"] for item in scored.values()),
        "english_irrelevant_evidence_rate": ratio(lambda item: not item["english_evidence_hit_at_3"]),
        "chinese_hit_at_1": ratio(lambda item: item["chinese_evidence_hit_at_1"]),
        "chinese_hit_at_3": ratio(lambda item: item["chinese_evidence_hit_at_3"]),
        "chinese_recall_at_3": _average(item["chinese_recall_at_3"] for item in scored.values()),
        "chinese_irrelevant_evidence_rate": ratio(lambda item: not item["chinese_evidence_hit_at_3"]),
        "bilingual_evidence_completeness": ratio(lambda item: item["bilingual_evidence_complete"]),
        "term_pair_accuracy": ratio(lambda item: item["term_pair_correct"]),
        "exact_term_pair_accuracy": ratio(lambda item: item["exact_term_pair_correct"]),
        "accepted_alias_accuracy": ratio(lambda item: item["term_pair_correct"]),
        "critical_confusion_count": sum(1 for item in scored.values() if item["critical_confusion"]),
        "unsupported_claim_count": unsupported_total,
        "unsupported_claim_rate": unsupported_total / total if total else 0.0,
        "contradiction_count": sum(int(item["contradiction_count"] or 0) for item in scored.values()),
        "source_reference_completeness": ratio(lambda item: item["source_reference_complete"]),
        "chunk_reference_completeness": ratio(lambda item: item["chunk_reference_complete"]),
        "language_label_completeness": 1.0 if total else 0.0,
        "parse_reference_completeness_when_available": _nullable_ratio(
            item["parse_reference_complete_when_available"] for item in scored.values()
        ),
        "page_bbox_completeness_when_available": _nullable_ratio(
            item["page_bbox_complete_when_available"] for item in scored.values()
        ),
        "approve_proxy_rate": approve / total if total else 0.0,
        "edit_proxy_rate": edit / total if total else 0.0,
        "reject_proxy_rate": reject / total if total else 0.0,
        "concept_results": scored,
        "failure_attribution_counts": _failure_counts(scored),
    }
    metrics["thresholds"] = dict(QUALITY_THRESHOLDS)
    metrics["threshold_pass"] = threshold_pass(metrics)
    metrics["overall_quality_pass"] = all(metrics["threshold_pass"].values()) if metrics["threshold_pass"] else False
    return metrics


def threshold_pass(summary: dict[str, Any]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for key, threshold in QUALITY_THRESHOLDS.items():
        value = summary.get(key)
        if key in {"unsupported_claim_rate", "reject_proxy_rate"}:
            result[key] = value is not None and value <= threshold
        elif key == "critical_confusion_count":
            result[key] = value == threshold
        else:
            result[key] = value is not None and value >= threshold
    return result


def dominant_failure_stage(summary: dict[str, Any]) -> str:
    counts = dict(summary.get("failure_attribution_counts") or {})
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def sanitize_artifact(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key or "").casefold()
            if lowered in FULL_TEXT_KEYS:
                continue
            if lowered not in SAFE_SENSITIVE_METRIC_KEYS and (
                lowered in SENSITIVE_KEYS
                or lowered.endswith("_token")
                or lowered.endswith("_secret")
                or "api_key" in lowered
                or lowered == "authorization"
            ):
                safe[str(key)] = "[REDACTED]"
            else:
                safe[str(key)] = sanitize_artifact(item)
        return safe
    if isinstance(value, list):
        return [sanitize_artifact(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_artifact(item) for item in value]
    return value


def validate_artifact(artifact: dict[str, Any]) -> None:
    status = artifact.get("status")
    if status not in QUALITY_STATUSES:
        raise ValueError("invalid Task 11E status")
    if artifact.get("task") != "11E":
        raise ValueError("invalid task identifier")
    privacy = artifact.get("privacy_network") or {}
    for key in ("private_data_egress", "external_document_api_requests", "private_pdf_usage", "secret_exposure", "model_downloads"):
        if privacy.get(key) != 0:
            raise ValueError(f"{key} must be zero")


def _candidate_precision(scored: dict[str, dict[str, Any]]) -> float:
    with_candidates = [item for item in scored.values() if item["system_chinese_term"]]
    if not with_candidates:
        return 0.0
    return sum(1 for item in with_candidates if item["top1_chinese_term_correct"]) / len(with_candidates)


def _failure_counts(scored: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in scored.values():
        primary = item.get("primary_failure_attribution")
        if primary:
            counts[primary] = counts.get(primary, 0) + 1
    return dict(sorted(counts.items()))


def _average(values) -> float:
    materialized = [float(value or 0.0) for value in values]
    if not materialized:
        return 0.0
    return sum(materialized) / len(materialized)


def _nullable_ratio(values) -> float | None:
    materialized = [value for value in values if value is not None]
    if not materialized:
        return None
    return sum(1 for value in materialized if value) / len(materialized)


def _unique_ordered(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in FAILURE_ATTRIBUTIONS and value not in seen:
            seen.add(value)
            result.append(value)
    return result
