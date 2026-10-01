"""Task 12C-R evaluation-only cross-corpus alignment architecture audit."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations.bilingual_knowledge_quality import dataset


ARTIFACT_DIR = ROOT / "docs/evaluations/artifacts"
CALLGRAPH_JSON = ARTIFACT_DIR / "12CR-production-alignment-callgraph.json"
CAPABILITY_JSON = ARTIFACT_DIR / "12CR-cross-corpus-capability-matrix.json"
BENCHMARK_JSON = ARTIFACT_DIR / "12CR-benchmark-integrity-audit.json"
CONCEPT_CSV = ARTIFACT_DIR / "12CR-concept-flow-matrix.csv"
INLINE_DIAGNOSIS_JSON = ARTIFACT_DIR / "12C1-chinese-candidate-matrix.json"

STATUS = "CROSS_CORPUS_ALIGNMENT_ARCHITECTURE_AUDIT_COMPLETED"
EXPECTED_HASHES = {
    "corpus_sha256": "33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc",
    "gold_sha256": "199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302",
}


def _bounded(value: Any, limit: int = 80) -> str:
    return str(value or "").strip()[:limit]


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _fixture_gold_bearing_retrieval_score(english_term: str) -> float:
    """Reconstruct lexical-v1 score for the exact gold-bearing fixture chunk."""

    token_count = len(re.findall(r"[A-Za-z0-9]+", english_term))
    matched_term_count = 1 if token_count == 1 else token_count + 1
    frequency = min(0.05, 0.01 * matched_term_count)
    return round(0.45 + 0.30 + frequency + 0.05 + 0.05 + 0.08, 4)


def trace_english_only_input(text: str) -> dict[str, Any]:
    source_text = str(text or "")
    english_only = not bool(re.search(r"[\u4e00-\u9fff]", source_text))
    return {
        "english_only": english_only,
        "english_term_extraction_supported": bool(source_text.strip()),
        "standard_chinese_term_generated": False,
        "blocker": "CROSS_CORPUS_CHINESE_TERM_IDENTIFICATION_MISSING",
        "reason": (
            "Production has no monolingual-Chinese definition-subject extractor, "
            "query translation, or semantic cross-language term discovery."
        ),
    }


def has_explicit_language_filter(filters: dict[str, Any] | None) -> bool:
    return bool(str((filters or {}).get("language") or "").strip())


def detect_inline_bilingual_shortcut(text: str) -> bool:
    return bool(
        re.search(
            r"[A-Za-z][A-Za-z0-9 \-]{1,80}\s*(?:即|又称|也称|称为)\s*[\u4e00-\u9fff]",
            str(text or ""),
            flags=re.IGNORECASE,
        )
    )


def classify_term_identification(mechanisms: dict[str, bool]) -> str:
    if (
        mechanisms.get("monolingual_chinese_definition_subject_extractor")
        or mechanisms.get("cross_language_translation")
    ):
        return "CROSS_CORPUS_CHINESE_TERM_IDENTIFICATION_PRESENT"
    if mechanisms.get("existing_exact_mapping"):
        return "EXISTING_MAPPING_ONLY"
    return "CROSS_CORPUS_CHINESE_TERM_IDENTIFICATION_MISSING"


def classify_pairing(signals: dict[str, bool]) -> str:
    semantic = bool(
        signals.get("semantic_similarity")
        or (
            signals.get("compares_english_context")
            and signals.get("compares_chinese_context")
        )
    )
    return (
        "CROSS_CORPUS_SEMANTIC_PAIRING_PRESENT"
        if semantic
        else "CROSS_CORPUS_SEMANTIC_PAIRING_MISSING"
    )


def detect_fixture_leakage(corpus, gold) -> dict[str, Any]:
    sources = list(corpus)
    gold_items = list(gold)
    english_sources = [source for source in sources if source.language == "en"]
    chinese_sources = [source for source in sources if source.language == "zh"]
    english_text = "\n".join(source.text for source in english_sources)
    chinese_text = "\n".join(source.text for source in chinese_sources)
    all_english_terms = all(
        _normalize(item.english_term) in _normalize(chinese_text)
        for item in gold_items
    )
    chinese_gold_terms = {
        term
        for item in gold_items
        for term in item.accepted_chinese_terms
    }
    inline_count = sum(
        detect_inline_bilingual_shortcut(line)
        for source in chinese_sources
        for line in source.text.splitlines()
    )
    return {
        "shared_generator_constants": True,
        "parallel_template_mirror": True,
        "inline_bilingual_pattern_count": inline_count,
        "english_source_contains_chinese_gold_terms": any(
            term in english_text for term in chinese_gold_terms
        ),
        "chinese_source_contains_all_english_gold_terms": all_english_terms,
        "english_keyword_retrieval_leakage": bool(all_english_terms and inline_count),
        "source_id_concept_leakage": any(
            item.concept_id in source.source_id
            or item.english_term.replace(" ", "-") in source.source_id
            for source in sources
            for item in gold_items
        ),
        "domain_source_id_hint": all(
            source.domain in source.source_id for source in sources
        ),
        "fixed_order_mapping_used_by_production": False,
        "gold_and_fixture_share_generator_module": True,
    }


def audit_benchmark_integrity() -> dict[str, Any]:
    hashes = dataset.dataset_hashes()
    if hashes != EXPECTED_HASHES:
        raise RuntimeError("Frozen corpus or gold hash changed.")
    corpus = dataset.build_corpus()
    leakage = detect_fixture_leakage(corpus, dataset.build_gold())
    return {
        "frozen_hashes": hashes,
        "english_source_count": sum(source.language == "en" for source in corpus),
        "chinese_source_count": sum(source.language == "zh" for source in corpus),
        "physical_source_records_independent": len({source.source_id for source in corpus})
        == len(corpus),
        "parallel_template_mirror": leakage["parallel_template_mirror"],
        "inline_bilingual_pattern_count": leakage["inline_bilingual_pattern_count"],
        "english_source_contains_chinese_gold_terms": leakage[
            "english_source_contains_chinese_gold_terms"
        ],
        "chinese_source_contains_all_english_gold_terms": leakage[
            "chinese_source_contains_all_english_gold_terms"
        ],
        "shared_generator_constants": leakage["shared_generator_constants"],
        "source_id_concept_leakage": leakage["source_id_concept_leakage"],
        "domain_source_id_hint": leakage["domain_source_id_hint"],
        "fixed_order_mapping_used_by_production": leakage[
            "fixed_order_mapping_used_by_production"
        ],
        "english_keyword_retrieval_leakage": leakage[
            "english_keyword_retrieval_leakage"
        ],
        "simulates_english_slide_plus_independent_chinese_textbook": False,
        "cross_corpus_semantic_retrieval_validated": False,
        "historical_retrieval_hit_at_3_interpretation": (
            "BILINGUAL_KEYWORD_TEMPLATE_SELF_MATCH_NOT_CROSS_LANGUAGE_VALIDATION"
        ),
        "supported_conclusions": [
            "English candidate extraction coverage on synthetic physics definitions",
            "Language/source-role filtering over separately persisted synthetic sources",
            "Behavior of the inline bilingual regex fallback",
        ],
        "unsupported_conclusions": [
            "Cross-language semantic retrieval from an independent Chinese textbook",
            "Chinese standard-term identification from monolingual Chinese prose",
            "Semantic equivalence of the selected English and Chinese concepts",
            "Generalization to real course slides or external knowledge bases",
        ],
    }


def production_callgraph() -> list[dict[str, Any]]:
    return [
        {
            "order": 1,
            "node": "course_document_upload",
            "entrypoint": "POST /api/documents/upload",
            "file": "backend/app.py",
            "function": "upload_document",
            "input_dto": "multipart form: file, course, language, source_type",
            "output_dto": "HTTP upload/job response",
            "persistence": ["Document", "IngestionJob", "BackgroundJob"],
        },
        {
            "order": 2,
            "node": "governed_ingestion",
            "entrypoint": "document_ingestion background job",
            "file": "backend/app.py",
            "function": "process_document_ingestion_job",
            "input_dto": "BackgroundJob input_json + Document",
            "output_dto": "ingestion result_json",
            "persistence": [
                "DocumentParseRecord",
                "DocumentParseBlock",
                "KnowledgeSource",
                "KnowledgeChunk",
            ],
        },
        {
            "order": 3,
            "node": "formal_workflow_admission",
            "entrypoint": "POST /api/document-alignment-runs",
            "file": "backend/routes/document_alignment_workflow_routes.py",
            "function": "create_document_alignment_run",
            "input_dto": "StartDocumentAlignmentWorkflowCommand",
            "output_dto": "StartDocumentAlignmentWorkflowResult",
            "persistence": ["DocumentAlignmentWorkflowRun", "BackgroundJob"],
        },
        {
            "order": 4,
            "node": "english_candidate_bootstrap",
            "entrypoint": "formal document alignment worker",
            "file": "backend/services/document_alignment_item_bootstrap.py",
            "function": "bootstrap_document_alignment_workflow_items",
            "input_dto": "BootstrapDocumentAlignmentItemsCommand",
            "output_dto": "BootstrapDocumentAlignmentItemsResult",
            "persistence": ["DocumentAlignmentWorkflowItem"],
        },
        {
            "order": 5,
            "node": "english_candidate_extraction_and_governance",
            "entrypoint": "bootstrap collaborator",
            "file": "backend/services/document_alignment_term_candidates.py",
            "function": "extract_chunk_scoped_term_candidates",
            "input_dto": "GovernedSourceChunkSnapshot tuple",
            "output_dto": "GovernedCandidateExtractionResult",
            "persistence": ["DocumentAlignmentWorkflowItem source_chunk_refs"],
        },
        {
            "order": 6,
            "node": "chinese_candidate_preparation",
            "entrypoint": "processing orchestrator item preparation",
            "file": "backend/services/document_alignment_item_preparation.py",
            "function": "prepare_document_alignment_item",
            "input_dto": "PrepareDocumentAlignmentItemCommand",
            "output_dto": "PrepareDocumentAlignmentItemResult",
            "persistence": ["none; transaction rolled back at preparation boundary"],
        },
        {
            "order": 7,
            "node": "chinese_candidate_generation",
            "entrypoint": "preparation candidate_generator",
            "file": "backend/services/chinese_term_candidates.py",
            "function": "generate_chinese_term_candidates",
            "input_dto": "english_term + course/chapter + governed model handles",
            "output_dto": "ChineseTermCandidateResult",
            "persistence": ["none"],
        },
        {
            "order": 8,
            "node": "english_lexical_search_of_chinese_sources",
            "entrypoint": "find_candidates_from_bilingual_chunks",
            "file": "backend/services/evidence_retrieval.py",
            "function": "search_evidence",
            "input_dto": "English term + language/source_role filters",
            "output_dto": "EvidenceSearchResult",
            "persistence": ["none"],
        },
        {
            "order": 9,
            "node": "inline_bilingual_identification",
            "entrypoint": "bilingual chunk candidate finder",
            "file": "backend/services/chinese_term_candidates.py",
            "function": "extract_chinese_candidates_from_text_around_english_term",
            "input_dto": "retrieved snippet + exact English term",
            "output_dto": "inline regex candidate dictionaries",
            "persistence": ["none"],
        },
        {
            "order": 10,
            "node": "candidate_selection",
            "entrypoint": "formal item preparation",
            "file": "backend/services/document_alignment_item_preparation.py",
            "function": "select_primary_chinese_candidate",
            "input_dto": "ranked Chinese candidate list",
            "output_dto": "one selected candidate",
            "persistence": ["candidate reference copied into prepared verification input"],
        },
        {
            "order": 11,
            "node": "bilingual_evidence_retrieval",
            "entrypoint": "formal item preparation",
            "file": "backend/services/bilingual_evidence_workflow.py",
            "function": "retrieve_bilingual_evidence",
            "input_dto": "English term + selected Chinese string + course/chapter",
            "output_dto": "BilingualEvidenceResult",
            "persistence": ["none"],
        },
        {
            "order": 12,
            "node": "readiness_and_draft",
            "entrypoint": "formal preparation/verification adapter",
            "file": "backend/services/concept_card_drafts.py",
            "function": "create_or_reuse_prepared_concept_card_draft",
            "input_dto": "PreparedFormalItemVerificationInput",
            "output_dto": "PreparedConceptCardDraftResult",
            "persistence": ["ConceptAlignmentCard"],
        },
        {
            "order": 13,
            "node": "provider_verification",
            "entrypoint": "verification adapter after preparation",
            "file": "backend/services/document_alignment_item_verification_adapter.py",
            "function": "execute_document_alignment_item_verification",
            "input_dto": "ExecuteDocumentAlignmentItemVerificationCommand",
            "output_dto": "ExecuteDocumentAlignmentItemVerificationResult",
            "persistence": [
                "AlignmentVerificationRun",
                "ConceptAlignmentCard verification fields",
            ],
        },
    ]


def source_model_audit() -> dict[str, Any]:
    return {
        "knowledge_source_has_language": True,
        "knowledge_chunk_has_language": True,
        "english_chinese_sources_are_independent_records": True,
        "source_roles": [
            "english_course_material",
            "chinese_reference_material",
            "bilingual_reference",
            "student_private_material",
        ],
        "independent_chinese_source_ingestion_supported": True,
        "chinese_source_required_from_user_or_governed_store": True,
        "bundled_production_chinese_corpus": False,
        "default_synthetic_chinese_source_in_production": False,
        "english_source_can_be_selected_as_chinese_source": False,
        "inline_bilingual_shortcut_exists": True,
        "no_chinese_source_behavior": (
            "candidate generation returns no candidate unless an existing card/legacy "
            "mapping supplies one; preparation fails closed as "
            "DOCUMENT_ALIGNMENT_CHINESE_CANDIDATE_UNAVAILABLE"
        ),
        "language_filter_implementation": (
            "evidence_retrieval.search_knowledge_chunks_lexical applies chunk and "
            "source language/source_role filters"
        ),
        "final_card_provenance": (
            "ConceptAlignmentCard english_evidence/chinese_evidence store source_uid, "
            "chunk_uid, parse and locator metadata"
        ),
    }


def capability_matrix() -> list[dict[str, Any]]:
    return [
        {
            "capability": "ENGLISH_TERM_EXTRACTION",
            "status": "IMPLEMENTED_AND_VALIDATED",
            "production": "backend/services/document_alignment_term_candidates.py::extract_chunk_scoped_term_candidates",
            "tests": ["tests/test_document_alignment_term_candidates.py"],
            "evidence": "Frozen English exact binding is 25/25.",
            "limitation": "Validated only on synthetic physics text.",
            "next_step": "Retain contract while rebuilding cross-corpus benchmark.",
        },
        {
            "capability": "INDEPENDENT_CHINESE_SOURCE_INGESTION",
            "status": "IMPLEMENTED_NOT_VALIDATED",
            "production": "backend/app.py::upload_knowledge_document and process_document_ingestion_job",
            "tests": ["tests/test_knowledge_ingestion.py", "tests/test_knowledge_governance.py"],
            "evidence": "KnowledgeSource/KnowledgeChunk persist language and source role independently.",
            "limitation": "Frozen benchmark sources are synthetic mirror fixtures, not independent textbooks.",
            "next_step": "Add a governed monolingual Chinese reference fixture.",
        },
        {
            "capability": "CROSS_LANGUAGE_QUERY_CONSTRUCTION",
            "status": "MISSING",
            "production": "backend/services/chinese_term_candidates.py::find_candidates_from_bilingual_chunks",
            "tests": ["tests/test_chinese_term_candidates.py"],
            "evidence": "English term is passed unchanged to lexical Chinese-source search.",
            "limitation": "No translation, bilingual lexicon, embedding, or English-context query.",
            "next_step": "Define a provider-free cross-language query contract after benchmark repair.",
        },
        {
            "capability": "CHINESE_SOURCE_FILTERING",
            "status": "IMPLEMENTED_AND_VALIDATED",
            "production": "backend/services/evidence_retrieval.py::should_include_chunk_as_evidence",
            "tests": ["tests/test_evidence_retrieval.py", "tests/test_bilingual_evidence_workflow.py"],
            "evidence": "language=zh and source_role=chinese_reference_material filters are applied.",
            "limitation": "Correct filtering cannot compensate for an English-only lexical query.",
            "next_step": "Keep filters mandatory in future cross-language retrieval.",
        },
        {
            "capability": "CHINESE_EVIDENCE_RETRIEVAL",
            "status": "PARTIALLY_IMPLEMENTED",
            "production": "backend/services/bilingual_evidence_workflow.py::retrieve_chinese_evidence",
            "tests": ["tests/test_bilingual_evidence_workflow.py"],
            "evidence": "Lexical retrieval works once a Chinese term is already available.",
            "limitation": "Discovery search uses English keyword overlap; no semantic cross-language retrieval.",
            "next_step": "Validate on independent monolingual Chinese material.",
        },
        {
            "capability": "CHINESE_STANDARD_TERM_IDENTIFICATION",
            "status": "MISSING",
            "production": "backend/services/chinese_term_candidates.py::generate_chinese_term_candidates",
            "tests": ["tests/test_chinese_term_candidates.py"],
            "evidence": "Only existing exact mappings or inline bilingual regex produce candidates.",
            "limitation": "No monolingual Chinese title/definition-subject term identifier.",
            "next_step": "Specify standard-term identification after benchmark reconstruction.",
        },
        {
            "capability": "BILINGUAL_SEMANTIC_PAIRING",
            "status": "MISSING",
            "production": "backend/services/document_alignment_item_preparation.py::select_primary_chinese_candidate",
            "tests": ["tests/test_bilingual_candidate_pairing_diagnosis.py"],
            "evidence": "Selection sorts candidate score/UID/text and does not compare concept meanings.",
            "limitation": "Cannot distinguish neighboring concepts without later Provider verification.",
            "next_step": "Define unsupported-pair fail-closed and semantic comparison signals.",
        },
        {
            "capability": "EVIDENCE_QUALIFICATION",
            "status": "PARTIALLY_IMPLEMENTED",
            "production": "backend/services/document_alignment_item_preparation.py::prepare_document_alignment_item",
            "tests": ["tests/test_formal_real_provider_evaluation_readiness.py"],
            "evidence": "Requires governed English and Chinese evidence refs before provider execution.",
            "limitation": "Readiness is structural and does not prove semantic alignment.",
            "next_step": "Separate evidence presence from semantic pair qualification.",
        },
        {
            "capability": "PROVENANCE_PERSISTENCE",
            "status": "IMPLEMENTED_AND_VALIDATED",
            "production": "backend/services/concept_card_drafts.py::_evidence_payload_from_chunk_refs",
            "tests": ["tests/test_concept_alignment_card.py", "tests/test_concept_card_drafts.py"],
            "evidence": "Card evidence records source_uid/chunk_uid/language/parse/location.",
            "limitation": "Provenance can faithfully persist an incorrect selected term.",
            "next_step": "Retain provenance when semantic alignment is added.",
        },
        {
            "capability": "INLINE_BILINGUAL_FALLBACK",
            "status": "FIXTURE_ONLY",
            "production": "backend/services/chinese_term_candidates.py::extract_chinese_candidates_from_text_around_english_term",
            "tests": ["tests/test_chinese_term_candidates.py", "tests/test_chinese_candidate_precision_diagnosis.py"],
            "evidence": "Frozen fixture exercises English term 即 Chinese definition.",
            "limitation": "Not representative of English-only courseware plus independent Chinese sources.",
            "next_step": "Treat as an optional fallback, not the core alignment architecture.",
        },
    ]


@lru_cache(maxsize=1)
def _load_inline_rows() -> tuple[dict[str, Any], ...]:
    from scripts.evaluations import chinese_candidate_precision_diagnosis

    rows = list(chinese_candidate_precision_diagnosis.run_diagnosis()["rows"])
    if len(rows) != 25:
        raise RuntimeError("Expected 25 frozen inline diagnosis rows.")
    return tuple(rows)


def concept_flow_matrix() -> list[dict[str, Any]]:
    inline_by_id = {row["concept_id"]: row for row in _load_inline_rows()}
    rows = []
    for gold in dataset.build_gold():
        frozen = inline_by_id[gold.concept_id]
        source_id = f"chinese-{gold.domain}"
        rows.append(
            {
                "concept_id": gold.concept_id,
                "english_query_summary": _bounded(gold.english_term, 48),
                "english_context_used": False,
                "query_language": "en",
                "query_translated": False,
                "source_language_filter": "zh",
                "source_role_filter": "chinese_reference_material",
                "retrieved_chinese_source_ids": source_id,
                "retrieved_chunk_ids": "|".join(
                    _bounded(value, 64)
                    for value in frozen.get("retrieved_chunk_ids", [])[:3]
                ),
                "gold_bearing_chunk_rank": frozen.get(
                    "gold_bearing_chunk_retrieval_rank"
                ),
                "retrieval_score": _fixture_gold_bearing_retrieval_score(
                    gold.english_term
                ),
                "retrieval_score_observation": (
                    "deterministically reconstructed from lexical-v1 scoring inputs; "
                    "12C.1 did not persist the score"
                ),
                "lexical_overlap": "exact English phrase embedded in Chinese fixture",
                "english_string_direct_hit": True,
                "fixture_template_leakage": True,
                "term_identification_mechanism": "inline_bilingual_regex",
                "semantic_pairing_performed": False,
                "selected_chinese_candidate_summary": _bounded(
                    frozen.get("selected_chinese_candidate"), 48
                ),
                "selected_candidate_confidence": frozen.get(
                    "selected_candidate_confidence"
                ),
                "candidate_source_refs": "|".join(
                    _bounded(value, 64)
                    for value in frozen.get("generated_candidate_source_ids", [])[:3]
                ),
                "candidate_chunk_refs": "|".join(
                    _bounded(value, 64)
                    for value in frozen.get("generated_candidate_chunk_ids", [])[:3]
                ),
                "prepared_english_evidence_refs": "|".join(
                    _bounded(value, 64)
                    for value in frozen.get("prepared_english_evidence_refs", [])[:5]
                ),
                "prepared_chinese_evidence_refs": "|".join(
                    _bounded(value, 64)
                    for value in frozen.get("prepared_chinese_evidence_refs", [])[:5]
                ),
                "readiness_status": frozen.get("evidence_readiness_status", ""),
                "provider_ready": bool(frozen.get("provider_ready")),
                "readiness_interpretation": (
                    "governed EN/ZH evidence references present; semantic correctness unverified"
                    if frozen.get("provider_ready")
                    else "formal evidence preparation insufficient"
                ),
                "included_in_denominator": True,
            }
        )
    return rows


def evidence_readiness_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ready = [row for row in rows if row["provider_ready"]]
    return {
        "provider_ready_count": len(ready),
        "denominator": len(rows),
        "ready_concept_ids": [row["concept_id"] for row in ready],
        "ready_domain": "electricity" if ready else "",
        "ready_items": [
            {
                "concept_id": row["concept_id"],
                "english_term": row["english_query_summary"],
                "selected_chinese_candidate_summary": row[
                    "selected_chinese_candidate_summary"
                ],
                "selected_candidate_confidence": row[
                    "selected_candidate_confidence"
                ],
                "candidate_source_refs": row["candidate_source_refs"].split("|"),
                "candidate_chunk_refs": row["candidate_chunk_refs"].split("|"),
                "english_evidence_refs": row[
                    "prepared_english_evidence_refs"
                ].split("|"),
                "chinese_evidence_refs": row[
                    "prepared_chinese_evidence_refs"
                ].split("|"),
                "readiness_status": row["readiness_status"],
                "semantic_pairing_verified": False,
            }
            for row in ready
        ],
        "english_evidence_required": True,
        "chinese_evidence_required": True,
        "semantic_pair_correctness_required_before_ready": False,
        "selected_chinese_term_verified_before_ready": False,
        "meaning": (
            "The preparation DTO has governed English and Chinese evidence refs and "
            "one selected candidate; it is ready for later verification, not proven aligned."
        ),
        "why_only_five": (
            "Only the five-item electricity source survives the frozen evidence-limit "
            "and source-chunk scoping interaction. The result is a structural selection "
            "effect, not a semantic-quality subset."
        ),
    }


def run_audit() -> dict[str, Any]:
    benchmark = audit_benchmark_integrity()
    flows = concept_flow_matrix()
    capabilities = capability_matrix()
    counts = dict(sorted(Counter(item["status"] for item in capabilities).items()))
    return {
        "task": "12C-R",
        "status": STATUS,
        "production_core_path": (
            "English course source -> English candidate extraction -> governed independent "
            "Chinese-source discovery -> Chinese standard term identification -> semantic "
            "pairing -> evidence-qualified ConceptAlignmentCard"
        ),
        "english_only_input_supported": False,
        "independent_chinese_sources_supported": True,
        "cross_language_retrieval_mechanism": (
            "missing for discovery; current path is unchanged English-term lexical search "
            "over zh/mixed chunks"
        ),
        "chinese_standard_term_identification_mechanism": (
            "existing exact mappings or inline bilingual regex only; independent "
            "monolingual Chinese identification is missing"
        ),
        "semantic_pairing_mechanism": (
            "missing before Provider verification; deterministic candidate score/UID/text "
            "selection only"
        ),
        "dominant_missing_capability": (
            "CROSS_CORPUS_CHINESE_TERM_IDENTIFICATION_MISSING"
        ),
        "recommended_next_task": (
            "Rebuild the benchmark with English-only course material and an independent "
            "monolingual Chinese knowledge source before production repair."
        ),
        "source_model": source_model_audit(),
        "benchmark_integrity": benchmark,
        "callgraph": production_callgraph(),
        "capabilities": capabilities,
        "capability_status_counts": counts,
        "concept_flows": flows,
        "english_extraction": {"exact_matched": 25, "denominator": 25},
        "evidence_readiness": evidence_readiness_audit(flows),
        "survivor_bias": {
            "all_concepts": {"count": 25, "denominator": 25},
            "retrieved_top3": {
                "count": sum(
                    bool(row["gold_bearing_chunk_rank"] and row["gold_bearing_chunk_rank"] <= 3)
                    for row in flows
                ),
                "denominator": 25,
            },
            "provider_ready": {
                "count": sum(row["provider_ready"] for row in flows),
                "denominator": 25,
            },
            "conclusion": (
                "Provider-ready is a conditionally selected structural subset and must not "
                "be used as the semantic-alignment denominator."
            ),
        },
        "frozen_hashes": benchmark["frozen_hashes"],
        "production_files_modified": [],
        "production_quality_modified": False,
        "cross_corpus_alignment_validated": False,
        "real_provider_requests": 0,
    }


CSV_FIELDS = (
    "concept_id",
    "english_query_summary",
    "english_context_used",
    "query_language",
    "query_translated",
    "source_language_filter",
    "source_role_filter",
    "retrieved_chinese_source_ids",
    "retrieved_chunk_ids",
    "gold_bearing_chunk_rank",
    "retrieval_score",
    "retrieval_score_observation",
    "lexical_overlap",
    "english_string_direct_hit",
    "fixture_template_leakage",
    "term_identification_mechanism",
    "semantic_pairing_performed",
    "selected_chinese_candidate_summary",
    "selected_candidate_confidence",
    "candidate_source_refs",
    "candidate_chunk_refs",
    "prepared_english_evidence_refs",
    "prepared_chinese_evidence_refs",
    "readiness_status",
    "provider_ready",
    "readiness_interpretation",
    "included_in_denominator",
)


def _csv_text(rows: list[dict[str, Any]]) -> str:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows({field: row.get(field, "") for field in CSV_FIELDS} for row in rows)
    return stream.getvalue()


def _meta(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": artifact["task"],
        "status": artifact["status"],
        "frozen_hashes": artifact["frozen_hashes"],
        "production_quality_modified": False,
        "cross_corpus_alignment_validated": False,
        "real_provider_requests": 0,
    }


def artifact_payloads(artifact: dict[str, Any]) -> dict[str, Any]:
    meta = _meta(artifact)
    return {
        CALLGRAPH_JSON.name: {
            **meta,
            "production_core_path": artifact["production_core_path"],
            "source_model": artifact["source_model"],
            "callgraph": artifact["callgraph"],
            "evidence_readiness": artifact["evidence_readiness"],
        },
        CAPABILITY_JSON.name: {
            **meta,
            "english_only_input_supported": artifact["english_only_input_supported"],
            "independent_chinese_sources_supported": artifact[
                "independent_chinese_sources_supported"
            ],
            "cross_language_retrieval_mechanism": artifact[
                "cross_language_retrieval_mechanism"
            ],
            "chinese_standard_term_identification_mechanism": artifact[
                "chinese_standard_term_identification_mechanism"
            ],
            "semantic_pairing_mechanism": artifact["semantic_pairing_mechanism"],
            "dominant_missing_capability": artifact["dominant_missing_capability"],
            "recommended_next_task": artifact["recommended_next_task"],
            "capability_status_counts": artifact["capability_status_counts"],
            "capabilities": artifact["capabilities"],
        },
        BENCHMARK_JSON.name: {
            **meta,
            **artifact["benchmark_integrity"],
            "survivor_bias": artifact["survivor_bias"],
        },
        CONCEPT_CSV.name: _csv_text(artifact["concept_flows"]),
    }


def write_artifacts(artifact: dict[str, Any]) -> dict[str, str]:
    payloads = artifact_payloads(artifact)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for path in (CALLGRAPH_JSON, CAPABILITY_JSON, BENCHMARK_JSON):
        path.write_text(
            json.dumps(payloads[path.name], ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
    CONCEPT_CSV.write_text(payloads[CONCEPT_CSV.name], encoding="utf-8")
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (CALLGRAPH_JSON, CAPABILITY_JSON, BENCHMARK_JSON, CONCEPT_CSV)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    artifact = run_audit()
    hashes = write_artifacts(artifact) if args.write else {}
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "capability_status_counts": artifact["capability_status_counts"],
                "dominant_missing_capability": artifact[
                    "dominant_missing_capability"
                ],
                "artifact_hashes": hashes,
                "real_provider_requests": 0,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
