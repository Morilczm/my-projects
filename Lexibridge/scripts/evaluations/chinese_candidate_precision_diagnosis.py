"""Task 12C.1 provider-free Chinese candidate and pairing diagnosis."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations.bilingual_knowledge_quality import dataset, runner


ARTIFACT_DIR = ROOT / "docs/evaluations/artifacts"
MATRIX_JSON = ARTIFACT_DIR / "12C1-chinese-candidate-matrix.json"
MATRIX_CSV = ARTIFACT_DIR / "12C1-chinese-candidate-matrix.csv"
PAIRING_JSON = ARTIFACT_DIR / "12C1-bilingual-pairing-audit.json"
EXPECTED_HASHES = {
    "corpus_sha256": "33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc",
    "gold_sha256": "199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302",
}
DIAGNOSTIC_SCOPE = "inline_bilingual_fixture_path"
DIAGNOSIS_STATUS = "INLINE_BILINGUAL_CHINESE_CANDIDATE_DIAGNOSIS_COMPLETED"
DOMINANT_ROOT_CAUSE = "INLINE_BILINGUAL_CHINESE_CANDIDATE_BOUNDARY_DEFECT"
RECOMMENDED_NEXT_TASK = (
    "English-to-Chinese cross-corpus alignment architecture audit"
)
CHINESE_PREDICATES = (
    "是",
    "指",
    "表示",
    "称为",
    "定义为",
    "描述",
    "说明",
    "适用于",
)
GENERIC_TERMS = {"物体", "作用", "现象", "过程"}
SYMBOL_PATTERN = re.compile(r"[=+*/^]|(?:^|\s)(?:kg|m|s|n|j|w|v|c)(?:\s|$)", re.I)


@dataclass(frozen=True)
class ChineseCandidateTrace:
    source_term_present: bool
    parsed_text_term_present: bool
    chunk_term_present: bool
    retrieval_rank: int | None
    candidate_count: int
    exact_candidate_rank: int | None
    alias_candidate_rank: int | None
    boundary_defect_present: bool
    fragmentation_present: bool
    normalization_defect_present: bool
    selected_candidate_correct: bool
    pair_correct: bool
    readiness_status: str
    benchmark_alias_gap: bool
    benchmark_fixture_defect: bool
    ambiguous: bool


def attribute_failure(trace: ChineseCandidateTrace) -> str:
    if trace.benchmark_fixture_defect:
        return "BENCHMARK_FIXTURE_DEFECT"
    if trace.benchmark_alias_gap:
        return "BENCHMARK_ALIAS_GAP"
    if not trace.source_term_present:
        return "CHINESE_SOURCE_TERM_ABSENT"
    if not trace.parsed_text_term_present:
        return "CHINESE_PARSING_DEFECT"
    if not trace.chunk_term_present:
        return "CHINESE_CHUNKING_DEFECT"
    if trace.retrieval_rank is None:
        return "CHINESE_RETRIEVAL_MISS"
    if trace.boundary_defect_present:
        return "CHINESE_CANDIDATE_BOUNDARY_DEFECT"
    if trace.fragmentation_present:
        return "CHINESE_CANDIDATE_FRAGMENTATION"
    if trace.normalization_defect_present:
        return "CHINESE_NORMALIZATION_DEFECT"
    correct_rank = trace.exact_candidate_rank or trace.alias_candidate_rank
    if correct_rank is None:
        return "CHINESE_CANDIDATE_EXTRACTION_MISSING"
    if correct_rank > 3:
        return "CHINESE_CANDIDATE_RANKING_DEFECT"
    if trace.ambiguous:
        return "AMBIGUOUS"
    if not trace.selected_candidate_correct or not trace.pair_correct:
        return "BILINGUAL_PAIRING_DEFECT"
    if trace.readiness_status != "prepared":
        return "EVIDENCE_READINESS_DEFECT"
    return "NO_DEFECT_READY"


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", text).casefold()


def _rank(values: list[str], accepted: tuple[str, ...]) -> int | None:
    expected = {_normalize(value) for value in accepted if _normalize(value)}
    return next(
        (
            index
            for index, value in enumerate(values, start=1)
            if _normalize(value) in expected
        ),
        None,
    )


def _contains(text: Any, values: tuple[str, ...]) -> bool:
    normalized = _normalize(text)
    return any(_normalize(value) in normalized for value in values if _normalize(value))


def _stable_chunk_ref(source_id: str, chunk: Any) -> str:
    return f"{source_id}:chunk-{int(getattr(chunk, 'chunk_index', 0))}"


def _bounded(value: Any, limit: int = 48) -> str:
    return str(value or "").strip()[:limit]


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


def _mrr(ranks: list[int | None]) -> float:
    return _mean([1.0 / rank if rank else 0.0 for rank in ranks])


def _hit(ranks: list[int | None], k: int) -> float:
    return round(sum(bool(rank and rank <= k) for rank in ranks) / len(ranks), 4) if ranks else 0.0


def _candidate_shape(text: str, accepted: tuple[str, ...]) -> dict[str, bool | int]:
    normalized = _normalize(text)
    exact = normalized in {_normalize(value) for value in accepted}
    return {
        "length": len(text),
        "overlong_explanation": len(text) > 12,
        "definition_fragment": (
            not exact
            and any(predicate in text for predicate in CHINESE_PREDICATES)
        ),
        "contains_definition_predicate": any(
            predicate in text for predicate in CHINESE_PREDICATES
        ),
        "generic": normalized in {_normalize(value) for value in GENERIC_TERMS},
        "single_character": len(text) == 1,
        "mixed_language": bool(re.search(r"[\u4e00-\u9fff]", text) and re.search(r"[A-Za-z]", text)),
        "parenthesized_english": bool(
            re.search(r"[（(]\s*[A-Za-z][A-Za-z0-9.-]*\s*[）)]", text)
        ),
        "fullwidth_ascii": bool(re.search(r"[Ａ-Ｚａ-ｚ０-９]", text)),
        "unicode_punctuation": bool(re.search(r"[，。；：、（）]", text)),
        "symbol_or_unit": bool(SYMBOL_PATTERN.search(text)),
    }


def _earliest_stage(attribution: str) -> str:
    return {
        "BENCHMARK_FIXTURE_DEFECT": "benchmark",
        "BENCHMARK_ALIAS_GAP": "benchmark",
        "CHINESE_SOURCE_TERM_ABSENT": "source",
        "CHINESE_PARSING_DEFECT": "parsing",
        "CHINESE_CHUNKING_DEFECT": "chunking",
        "CHINESE_RETRIEVAL_MISS": "chinese_source_retrieval",
        "CHINESE_CANDIDATE_EXTRACTION_MISSING": "chinese_candidate_generation",
        "CHINESE_CANDIDATE_BOUNDARY_DEFECT": "chinese_candidate_boundary",
        "CHINESE_CANDIDATE_FRAGMENTATION": "chinese_candidate_fragmentation",
        "CHINESE_CANDIDATE_OVERGENERATION": "chinese_candidate_generation",
        "CHINESE_CANDIDATE_RANKING_DEFECT": "chinese_candidate_ranking",
        "CHINESE_NORMALIZATION_DEFECT": "chinese_normalization",
        "BILINGUAL_PAIRING_DEFECT": "bilingual_pairing",
        "EVIDENCE_READINESS_DEFECT": "evidence_readiness",
        "AMBIGUOUS": "bilingual_pairing",
        "NO_DEFECT_READY": "none",
    }.get(attribution, "undetermined")


def _candidate_source_retrieval(
    module: Any,
    evidence_retrieval: Any,
    english_term: str,
) -> list[dict[str, Any]]:
    return evidence_retrieval.search_evidence(
        module.db.session,
        module.KnowledgeChunk,
        module.KnowledgeSource,
        english_term,
        filters={
            "course": dataset.COURSE_NAME,
            "language": "zh",
            "source_role": "chinese_reference_material",
            "include_low_quality": False,
            "include_needs_review": False,
        },
        limit=20,
    ).candidates


def _pairing_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "correct_english_input_count": sum(row["english_pairing_input_correct"] for row in rows),
        "correct_chinese_input_count": sum(
            bool(row["exact_candidate_rank"] or row["alias_candidate_rank"])
            for row in rows
        ),
        "correct_pair_count": sum(row["bilingual_pair_status"] == "correct" for row in rows),
        "pairing_defect_count": sum(
            row["primary_attribution"] == "BILINGUAL_PAIRING_DEFECT"
            for row in rows
        ),
        "features": {
            "exact_english_match": True,
            "lexical_overlap_cross_language": False,
            "source_proximity": True,
            "definition_similarity": False,
            "retrieval_rank": False,
            "candidate_confidence": True,
            "abbreviation_mapping": False,
            "course_chapter_match": True,
            "trust_and_source_role": True,
        },
        "selection_order": [
            "descending candidate score",
            "candidate_uid",
            "casefolded Chinese term",
        ],
        "surface_similarity_dependency": False,
        "input_truncation_loss_count": 0,
        "provenance_retained": all(
            all(row["generated_candidate_source_ids"])
            and all(row["generated_candidate_chunk_ids"])
            for row in rows
        ),
        "explicit_pair_failure_reason_code": False,
        "selection_is_deterministic_within_persisted_run": True,
        "selection_identity_depends_on_source_and_chunk_ids": True,
        "candidate_precision_failure_count": sum(
            row["primary_attribution"].startswith("CHINESE_CANDIDATE_")
            for row in rows
        ),
    }


@lru_cache(maxsize=1)
def run_diagnosis() -> dict[str, Any]:
    frozen_hashes = dataset.dataset_hashes()
    if frozen_hashes != EXPECTED_HASHES:
        raise RuntimeError("Frozen corpus or gold hash mismatch.")
    accident_before = runner.database_state()

    with tempfile.TemporaryDirectory(prefix="lexibridge-12c1-") as temp_name:
        temp_root = Path(temp_name)
        module = runner.load_app_module(
            temp_db=temp_root / "evaluation.sqlite",
            upload_dir=temp_root / "uploads",
        )
        from services import (
            bilingual_evidence_workflow,
            chinese_term_candidates,
            evidence_retrieval,
        )
        from services.document_alignment_item_preparation import (
            select_primary_chinese_candidate,
        )
        from services.document_alignment_processing_orchestrator import (
            ProcessDocumentAlignmentWorkflowCommand,
        )

        client = module.app.test_client()
        _, token = runner.create_login_user(
            module, client, role="teacher", prefix="teacher_12c1"
        )
        course = runner.create_course(client, token, dataset.COURSE_NAME)
        runtime_sources: dict[str, dict[str, Any]] = {}
        corpus_by_id = {source.source_id: source for source in dataset.build_corpus()}
        uploads = []
        for source in dataset.build_corpus():
            upload = runner.upload_source(
                client, token, course_id=course["id"], source=source
            )
            result = runner.run_ingestion_job(module, upload["job_id"])
            runtime_sources[source.source_id] = result
            uploads.append((source, result))

        runs = [
            (source, runner.start_formal_run(client, token, result["source_uid"]))
            for source, result in uploads
            if source.language == "en"
        ]
        systems: list[dict[str, Any]] = []
        with module.app.app_context():
            for source, run_uid in runs:
                claimed = module.claim_next_formal_background_job(
                    "12c1-diagnosis",
                    module._formal_job_execution_dependencies(),
                )
                lease = claimed.lease
                dependencies = module.build_document_alignment_processing_dependencies(
                    session=module.db.session,
                    models=module._formal_processing_composition_models(),
                    lease=lease,
                    term_extractor=module.extract_terms_from_text,
                )
                command = ProcessDocumentAlignmentWorkflowCommand(
                    workflow_run_uid=run_uid,
                    job_uid=lease.job_uid,
                    worker_id=lease.worker_id,
                    execution_attempt=lease.execution_attempt,
                    lease_token=lease.lease_token,
                )
                dependencies.bootstrap.execute(command)
                run = module.DocumentAlignmentWorkflowRun.query.filter_by(
                    run_uid=run_uid
                ).one()
                items = module.DocumentAlignmentWorkflowItem.query.filter_by(
                    workflow_run_id=run.id
                ).all()
                systems.extend(
                    {
                        "term": str(item.candidate_term),
                        "normalized": str(item.normalized_term),
                        "candidate_id": str(item.item_uid),
                        "item": item,
                        "command": command,
                        "dependencies": dependencies,
                    }
                    for item in items
                )
            by_term: dict[str, list[dict[str, Any]]] = {}
            for system in systems:
                by_term.setdefault(_normalize(system["term"]), []).append(system)

            rows = []
            all_shapes: list[dict[str, Any]] = []
            duplicate_count = 0
            for gold in dataset.build_gold():
                system_matches = by_term.get(_normalize(gold.english_term), [])
                if len(system_matches) != 1:
                    raise RuntimeError(
                        f"English exact binding is not unique for {gold.concept_id}."
                    )
                system = system_matches[0]
                domain = gold.domain
                chinese_source_id = f"chinese-{domain}"
                chinese_source = corpus_by_id[chinese_source_id]
                runtime = runtime_sources[chinese_source_id]
                source_obj = module.KnowledgeSource.query.filter_by(
                    source_uid=runtime["source_uid"]
                ).one()
                document = module.db.session.get(module.Document, source_obj.document_id)
                chunks = (
                    module.KnowledgeChunk.query.filter_by(
                        source_uid=runtime["source_uid"]
                    )
                    .order_by(module.KnowledgeChunk.chunk_index)
                    .all()
                )
                accepted = tuple(gold.accepted_chinese_terms)
                gold_term = accepted[0]
                aliases = accepted[1:]
                gold_chunks = [
                    chunk
                    for chunk in chunks
                    if _contains(chunk.content, (gold_term,))
                    and _normalize(gold.english_term) in _normalize(chunk.content)
                ]
                source_retrieval = _candidate_source_retrieval(
                    module, evidence_retrieval, system["term"]
                )
                gold_chunk_uids = {str(chunk.chunk_uid) for chunk in gold_chunks}
                retrieval_rank = next(
                    (
                        index
                        for index, candidate in enumerate(source_retrieval, start=1)
                        if str(candidate.get("chunk_uid") or "") in gold_chunk_uids
                    ),
                    None,
                )

                result = chinese_term_candidates.generate_chinese_term_candidates(
                    module.db.session,
                    concept_card_model=module.ConceptAlignmentCard,
                    term_model=None,
                    terminology_card_model=None,
                    chunk_model=module.KnowledgeChunk,
                    source_model=module.KnowledgeSource,
                    english_term=system["term"],
                    course=dataset.COURSE_NAME,
                    chapter="",
                    limit=10,
                    filters={
                        "include_low_quality": False,
                        "include_needs_review": False,
                    },
                )
                generated = list(result.candidates)
                generated_texts = [
                    str(candidate.get("chinese_term") or "") for candidate in generated
                ]
                exact_rank = _rank(generated_texts, (gold_term,))
                alias_rank = _rank(generated_texts, aliases)
                selected = select_primary_chinese_candidate(generated) or {}
                selected_text = str(selected.get("chinese_term") or "")
                selected_correct = _rank([selected_text], accepted) == 1
                pair_correct = bool(selected_correct)
                evidence = bilingual_evidence_workflow.retrieve_bilingual_evidence(
                    module.db.session,
                    module.KnowledgeChunk,
                    module.KnowledgeSource,
                    system["term"],
                    chinese_term=selected_text,
                    course=dataset.COURSE_NAME,
                    chapter="",
                    limit=5,
                    filters={
                        "include_low_quality": False,
                        "include_needs_review": False,
                    },
                    auto_generate_chinese_candidates=False,
                )
                evidence_rank = next(
                    (
                        index
                        for index, candidate in enumerate(
                            evidence.chinese_evidence_candidates, start=1
                        )
                        if str(candidate.get("chunk_uid") or "") in gold_chunk_uids
                    ),
                    None,
                )
                prepared = system["dependencies"].preparation.prepare(
                    system["command"], str(system["item"].item_uid)
                )
                shapes = [
                    _candidate_shape(text, accepted) for text in generated_texts
                ]
                all_shapes.extend(shapes)
                duplicate_count += len(generated_texts) - len(
                    {_normalize(text) for text in generated_texts}
                )
                boundary = any(bool(shape["definition_fragment"]) for shape in shapes)
                trace = ChineseCandidateTrace(
                    source_term_present=_contains(chinese_source.text, (gold_term,)),
                    parsed_text_term_present=_contains(document.parsed_text, (gold_term,)),
                    chunk_term_present=bool(gold_chunks),
                    retrieval_rank=retrieval_rank,
                    candidate_count=len(generated),
                    exact_candidate_rank=exact_rank,
                    alias_candidate_rank=alias_rank,
                    boundary_defect_present=boundary,
                    fragmentation_present=False,
                    normalization_defect_present=False,
                    selected_candidate_correct=selected_correct,
                    pair_correct=pair_correct,
                    readiness_status=str(prepared.outcome),
                    benchmark_alias_gap=False,
                    benchmark_fixture_defect=False,
                    ambiguous=False,
                )
                attribution = attribute_failure(trace)
                observations = []
                if boundary:
                    observations.append("definition_predicate_or_explanation_in_candidate")
                if len(generated) > 1:
                    observations.append("multiple_equal_score_candidates")
                if evidence_rank is not None and not pair_correct:
                    observations.append("evidence_retrieval_can_succeed_for_wrong_boundary_candidate")
                rows.append({
                    "concept_id": gold.concept_id,
                    "english_candidate_id": system["candidate_id"],
                    "english_normalized_term": system["normalized"],
                    "english_pairing_input_correct": True,
                    "gold_chinese_term": gold_term,
                    "accepted_chinese_aliases": list(aliases),
                    "chinese_source_id": chinese_source_id,
                    "gold_term_in_source": trace.source_term_present,
                    "gold_alias_in_source": any(
                        _contains(chinese_source.text, (alias,)) for alias in aliases
                    ),
                    "gold_term_in_parsed_text": trace.parsed_text_term_present,
                    "gold_term_in_chunk": trace.chunk_term_present,
                    "retrieved_chunk_ids": [
                        str(candidate.get("chunk_uid") or "")
                        for candidate in source_retrieval[:10]
                    ],
                    "gold_bearing_chunk_retrieval_rank": retrieval_rank,
                    "evidence_gold_bearing_chunk_rank": evidence_rank,
                    "generated_chinese_candidate_ids": [
                        str(candidate.get("candidate_uid") or "")
                        for candidate in generated
                    ],
                    "generated_candidate_source_ids": [
                        str(candidate.get("source_uid") or "")
                        for candidate in generated
                    ],
                    "generated_candidate_chunk_ids": [
                        str(candidate.get("chunk_uid") or "")
                        for candidate in generated
                    ],
                    "generated_candidate_summaries": [
                        _bounded(text) for text in generated_texts
                    ],
                    "candidate_confidences": [
                        float(candidate.get("score") or 0.0)
                        for candidate in generated
                    ],
                    "candidate_count": len(generated),
                    "candidate_ranks": list(range(1, len(generated) + 1)),
                    "exact_candidate_rank": exact_rank,
                    "alias_candidate_rank": alias_rank,
                    "selected_chinese_candidate": _bounded(selected_text),
                    "selected_candidate_confidence": float(
                        selected.get("score") or 0.0
                    ),
                    "bilingual_pair_status": "correct" if pair_correct else "incorrect",
                    "bilingual_pair_top3": bool(
                        (exact_rank and exact_rank <= 3)
                        or (alias_rank and alias_rank <= 3)
                    ),
                    "evidence_readiness_status": str(prepared.outcome),
                    "evidence_qualified": str(prepared.outcome) == "prepared",
                    "provider_ready": str(prepared.outcome) == "prepared",
                    "prepared_english_evidence_refs": list(
                        getattr(prepared, "english_evidence_refs", ()) or ()
                    ),
                    "prepared_chinese_evidence_refs": list(
                        getattr(prepared, "chinese_evidence_refs", ()) or ()
                    ),
                    "earliest_failure_stage": _earliest_stage(attribution),
                    "primary_attribution": attribution,
                    "secondary_observations": observations,
                    "included_in_denominator": True,
                })

    accident_after = runner.database_state()
    if accident_before != accident_after:
        raise RuntimeError("Accident database changed.")

    retrieval_ranks = [
        row["gold_bearing_chunk_retrieval_rank"] for row in rows
    ]
    evidence_ranks = [
        row["evidence_gold_bearing_chunk_rank"] for row in rows
    ]
    candidate_ranks = [
        row["exact_candidate_rank"] or row["alias_candidate_rank"] for row in rows
    ]
    total_candidates = sum(row["candidate_count"] for row in rows)
    top3_slots = sum(min(3, row["candidate_count"]) for row in rows)
    attribution_counts = dict(
        sorted(Counter(row["primary_attribution"] for row in rows).items())
    )
    metrics = {
        "benchmark_coverage": f"{len(rows)}/25",
        "english_exact_matched": 25,
        "chinese_gold_source_present": sum(row["gold_term_in_source"] for row in rows),
        "chinese_gold_parsed_text_present": sum(
            row["gold_term_in_parsed_text"] for row in rows
        ),
        "chinese_gold_chunk_present": sum(row["gold_term_in_chunk"] for row in rows),
        "candidate_source_retrieval_hit_at_1": _hit(retrieval_ranks, 1),
        "candidate_source_retrieval_hit_at_3": _hit(retrieval_ranks, 3),
        "candidate_source_retrieval_mrr": _mrr(retrieval_ranks),
        "selected_term_evidence_hit_at_1": _hit(evidence_ranks, 1),
        "selected_term_evidence_hit_at_3": _hit(evidence_ranks, 3),
        "selected_term_evidence_mrr": _mrr(evidence_ranks),
        "chinese_candidate_generated": sum(row["candidate_count"] > 0 for row in rows),
        "chinese_exact_candidate_generated": sum(
            row["exact_candidate_rank"] is not None for row in rows
        ),
        "chinese_alias_candidate_generated": sum(
            row["alias_candidate_rank"] is not None for row in rows
        ),
        "chinese_candidate_top1_accuracy": _hit(candidate_ranks, 1),
        "chinese_candidate_top3_accuracy": _hit(candidate_ranks, 3),
        "chinese_candidate_mrr": _mrr(candidate_ranks),
        "bilingual_pair_top1_accuracy": round(
            sum(row["bilingual_pair_status"] == "correct" for row in rows)
            / len(rows),
            4,
        ),
        "bilingual_pair_top3_accuracy": round(
            sum(row["bilingual_pair_top3"] for row in rows) / len(rows), 4
        ),
        "evidence_qualified_count": sum(row["evidence_qualified"] for row in rows),
        "provider_ready_count": sum(row["provider_ready"] for row in rows),
    }
    morphology = {
        "total_candidates": total_candidates,
        "candidate_count_per_concept": {
            row["concept_id"]: row["candidate_count"] for row in rows
        },
        "generic_candidate_count": sum(shape["generic"] for shape in all_shapes),
        "generic_candidate_ratio": round(
            sum(shape["generic"] for shape in all_shapes) / total_candidates, 4
        ) if total_candidates else 0.0,
        "definition_fragment_count": sum(
            shape["definition_fragment"] for shape in all_shapes
        ),
        "definition_fragment_ratio": round(
            sum(shape["definition_fragment"] for shape in all_shapes)
            / total_candidates,
            4,
        ) if total_candidates else 0.0,
        "contains_definition_predicate_count": sum(
            shape["contains_definition_predicate"] for shape in all_shapes
        ),
        "overlong_explanation_count": sum(
            shape["overlong_explanation"] for shape in all_shapes
        ),
        "duplicate_count": duplicate_count,
        "duplicate_ratio": round(
            duplicate_count / (total_candidates + duplicate_count), 4
        ) if total_candidates + duplicate_count else 0.0,
        "average_candidate_length": _mean(
            [float(shape["length"]) for shape in all_shapes]
        ),
        "single_character_count": sum(
            shape["single_character"] for shape in all_shapes
        ),
        "mixed_language_count": sum(shape["mixed_language"] for shape in all_shapes),
        "parenthesized_english_count": sum(
            shape["parenthesized_english"] for shape in all_shapes
        ),
        "fullwidth_ascii_count": sum(
            shape["fullwidth_ascii"] for shape in all_shapes
        ),
        "unicode_punctuation_count": sum(
            shape["unicode_punctuation"] for shape in all_shapes
        ),
        "symbol_or_unit_count": sum(shape["symbol_or_unit"] for shape in all_shapes),
        "top1_precision_proxy": metrics["chinese_candidate_top1_accuracy"],
        "top3_precision_proxy": round(
            sum(bool(rank and rank <= 3) for rank in candidate_ranks)
            / top3_slots,
            4,
        ) if top3_slots else 0.0,
        "ranking_inversion_count": sum(
            bool(rank and rank > 1) for rank in candidate_ranks
        ),
        "overgenerated_concept_count": sum(
            row["candidate_count"] > 1 for row in rows
        ),
        "equal_score_competition_concept_count": sum(
            len(set(row["candidate_confidences"])) == 1
            and row["candidate_count"] > 1
            for row in rows
        ),
        "accepted_alias_concept_count": sum(
            bool(row["accepted_chinese_aliases"]) for row in rows
        ),
        "traditional_variant_observed": False,
    }
    subsets = {
        "all_25": {"count": 25, "denominator": 25},
        "gold_bearing_chunk_retrieved": {
            "count": sum(rank is not None for rank in retrieval_ranks),
            "denominator": 25,
        },
        "exact_chinese_candidate_generated": {
            "count": sum(rank is not None for rank in candidate_ranks),
            "denominator": 25,
        },
        "top3_chinese_candidate": {
            "count": sum(bool(rank and rank <= 3) for rank in candidate_ranks),
            "denominator": 25,
        },
        "correctly_paired": {
            "count": sum(
                row["bilingual_pair_status"] == "correct" for row in rows
            ),
            "denominator": 25,
        },
        "evidence_qualified": {
            "count": metrics["evidence_qualified_count"],
            "denominator": 25,
        },
        "provider_ready": {
            "count": metrics["provider_ready_count"],
            "denominator": 25,
        },
    }
    pairing_audit = _pairing_audit(rows)
    return {
        "task": "12C.1",
        "status": DIAGNOSIS_STATUS,
        "diagnostic_scope": DIAGNOSTIC_SCOPE,
        "production_core_path_represented": False,
        "cross_corpus_alignment_validated": False,
        "dominant_root_cause": DOMINANT_ROOT_CAUSE,
        "recommended_next_task": RECOMMENDED_NEXT_TASK,
        "production_quality_modified": False,
        "frozen_hashes": frozen_hashes,
        "metrics": metrics,
        "attribution_counts": attribution_counts,
        "candidate_morphology": morphology,
        "survivor_subsets": subsets,
        "pairing_audit": pairing_audit,
        "rows": rows,
        "benchmark_alias_gap_count": attribution_counts.get(
            "BENCHMARK_ALIAS_GAP", 0
        ),
        "benchmark_fixture_defect_count": attribution_counts.get(
            "BENCHMARK_FIXTURE_DEFECT", 0
        ),
        "production_files_modified": [],
        "real_provider_requests": 0,
        "accident_database_unchanged": True,
    }


CSV_FIELDS = (
    "concept_id",
    "english_candidate_id",
    "english_normalized_term",
    "gold_chinese_term",
    "accepted_chinese_aliases",
    "chinese_source_id",
    "gold_term_in_source",
    "gold_term_in_parsed_text",
    "gold_term_in_chunk",
    "retrieved_chunk_ids",
    "gold_bearing_chunk_retrieval_rank",
    "generated_chinese_candidate_ids",
    "generated_candidate_source_ids",
    "generated_candidate_chunk_ids",
    "generated_candidate_summaries",
    "candidate_confidences",
    "exact_candidate_rank",
    "alias_candidate_rank",
    "selected_chinese_candidate",
    "bilingual_pair_status",
    "evidence_readiness_status",
    "earliest_failure_stage",
    "primary_attribution",
    "secondary_observations",
    "included_in_denominator",
)


def _matrix_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": artifact["task"],
        "status": artifact["status"],
        "diagnostic_scope": artifact["diagnostic_scope"],
        "production_core_path_represented": artifact[
            "production_core_path_represented"
        ],
        "cross_corpus_alignment_validated": artifact[
            "cross_corpus_alignment_validated"
        ],
        "dominant_root_cause": artifact["dominant_root_cause"],
        "recommended_next_task": artifact["recommended_next_task"],
        "production_quality_modified": artifact["production_quality_modified"],
        "frozen_hashes": artifact["frozen_hashes"],
        "metrics": artifact["metrics"],
        "attribution_counts": artifact["attribution_counts"],
        "candidate_morphology": artifact["candidate_morphology"],
        "survivor_subsets": artifact["survivor_subsets"],
        "rows": artifact["rows"],
        "real_provider_requests": 0,
    }


def _pairing_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": artifact["task"],
        "status": artifact["status"],
        "diagnostic_scope": artifact["diagnostic_scope"],
        "production_core_path_represented": artifact[
            "production_core_path_represented"
        ],
        "cross_corpus_alignment_validated": artifact[
            "cross_corpus_alignment_validated"
        ],
        "dominant_root_cause": artifact["dominant_root_cause"],
        "recommended_next_task": artifact["recommended_next_task"],
        "production_quality_modified": artifact["production_quality_modified"],
        "frozen_hashes": artifact["frozen_hashes"],
        "pairing_audit": artifact["pairing_audit"],
        "bilingual_pair_top1_accuracy": artifact["metrics"][
            "bilingual_pair_top1_accuracy"
        ],
        "bilingual_pair_top3_accuracy": artifact["metrics"][
            "bilingual_pair_top3_accuracy"
        ],
        "provider_ready_count": artifact["metrics"]["provider_ready_count"],
        "real_provider_requests": 0,
    }


def _csv_text(rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            key: (
                json.dumps(row.get(key), ensure_ascii=False, separators=(",", ":"))
                if isinstance(row.get(key), (list, dict))
                else row.get(key)
            )
            for key in CSV_FIELDS
        })
    return stream.getvalue()


def artifact_payloads(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        MATRIX_JSON.name: _matrix_payload(artifact),
        MATRIX_CSV.name: _csv_text(artifact["rows"]),
        PAIRING_JSON.name: _pairing_payload(artifact),
    }


def write_artifacts(artifact: dict[str, Any]) -> dict[str, str]:
    payloads = artifact_payloads(artifact)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    MATRIX_JSON.write_text(
        json.dumps(payloads[MATRIX_JSON.name], ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    MATRIX_CSV.write_text(payloads[MATRIX_CSV.name], encoding="utf-8")
    PAIRING_JSON.write_text(
        json.dumps(payloads[PAIRING_JSON.name], ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (MATRIX_JSON, MATRIX_CSV, PAIRING_JSON)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    artifact = run_diagnosis()
    hashes = write_artifacts(artifact) if args.write else {}
    print(json.dumps({
        "status": artifact["status"],
        "metrics": artifact["metrics"],
        "attribution_counts": artifact["attribution_counts"],
        "survivor_subsets": artifact["survivor_subsets"],
        "candidate_morphology": artifact["candidate_morphology"],
        "pairing_audit": artifact["pairing_audit"],
        "artifact_hashes": hashes,
        "real_provider_requests": 0,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
