"""Task 12A evaluation-only frozen candidate failure diagnosis.

This module never imports a Provider transport. Runtime execution is explicitly
configured against a temporary database and uses the production ingestion,
chunking, and deterministic candidate extractor without changing their output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluations.bilingual_knowledge_quality import dataset, runner


ARTIFACT_DIR = ROOT / "docs/evaluations/artifacts"
MATRIX_JSON = ARTIFACT_DIR / "12A-candidate-failure-matrix.json"
MATRIX_CSV = ARTIFACT_DIR / "12A-candidate-failure-matrix.csv"
AUDIT_JSON = ARTIFACT_DIR / "12A-benchmark-audit.json"
REAL_PROVIDER_REQUESTS = 0
EXPECTED_CORPUS_SHA256 = "33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc"
EXPECTED_GOLD_SHA256 = "199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302"


@dataclass(frozen=True)
class DiagnosticTrace:
    concept_id: str
    source_term_present: bool
    parsed_text_term_present: bool
    chunk_term_present: bool
    exact_candidate_present: bool
    near_candidate_present: bool
    overlong_candidate_present: bool
    fragmented_candidate_present: bool
    normalized_match_present: bool
    binding_status: str
    benchmark_status: str
    candidate_alias_present: bool = False
    source_candidate_limit_exceeded: bool = False
    candidate_governance_overflow_present: bool = False
    candidate_overflow_match_present: bool = False
    ambiguous_binding: bool = False


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", normalize(value)))


def compare_candidate(gold: str, candidate: str) -> dict[str, Any]:
    gold_norm, candidate_norm = normalize(gold), normalize(candidate)
    gold_tokens, candidate_tokens = _tokens(gold), _tokens(candidate)
    overlap = len(set(gold_tokens) & set(candidate_tokens))
    union = len(set(gold_tokens) | set(candidate_tokens))
    return {
        "raw_exact": str(gold) == str(candidate),
        "normalized_exact": gold_norm == candidate_norm,
        "containment": bool(gold_norm and (gold_norm in candidate_norm or candidate_norm in gold_norm)),
        "token_overlap": round(overlap / union, 4) if union else 0.0,
        "token_order_independent_exact": sorted(gold_tokens) == sorted(candidate_tokens),
        "prefix": bool(gold_norm and candidate_norm.startswith(gold_norm)),
        "suffix": bool(gold_norm and candidate_norm.endswith(gold_norm)),
    }


def attribute_failure(trace: DiagnosticTrace) -> str:
    if trace.benchmark_status in {
        "BENCHMARK_TERM_NOT_IN_SOURCE",
        "BENCHMARK_EVIDENCE_INSUFFICIENT",
        "BENCHMARK_AMBIGUOUS_CONCEPT",
        "BENCHMARK_OTHER_DEFECT",
    } and not trace.source_term_present:
        return "BENCHMARK_FIXTURE_DEFECT"
    if not trace.source_term_present:
        return "SOURCE_TEXT_ABSENT"
    if not trace.parsed_text_term_present:
        return "PARSING_DEFECT"
    if not trace.chunk_term_present:
        return "CHUNKING_DEFECT"
    if trace.binding_status == "matched":
        return "NO_DEFECT_MATCHED"
    if trace.candidate_overflow_match_present:
        return "CANDIDATE_GOVERNANCE_OVERFLOW"
    if trace.source_candidate_limit_exceeded or trace.overlong_candidate_present:
        return "CANDIDATE_BOUNDARY_DEFECT"
    if trace.fragmented_candidate_present:
        return "CANDIDATE_FRAGMENTATION_DEFECT"
    if trace.ambiguous_binding:
        return "AMBIGUOUS_BINDING"
    if trace.normalized_match_present:
        return "BINDING_DEFECT"
    if trace.near_candidate_present or trace.candidate_alias_present:
        return "NORMALIZATION_DEFECT"
    return "CANDIDATE_EXTRACTION_DEFECT"


def audit_benchmark_item(
    *,
    english_term: str,
    english_aliases: Iterable[str],
    chinese_term: str,
    chinese_aliases: Iterable[str],
    english_source: str,
    chinese_source: str,
) -> dict[str, Any]:
    english_values = (english_term, *tuple(english_aliases))
    chinese_values = (chinese_term, *tuple(chinese_aliases))
    en_found = next((value for value in english_values if normalize(value) in normalize(english_source)), "")
    zh_found = next((value for value in chinese_values if str(value) in chinese_source), "")
    status = "BENCHMARK_SOURCE_VALID"
    observations: list[str] = []
    alias_gap = normalize(english_term) == "potential difference" and (
        re.search(r"\bvoltage\b", english_source, re.I)
        and "voltage" not in {normalize(value) for value in english_values}
        or ("也称电压" in chinese_source and "电压" not in chinese_values)
    )
    if alias_gap and (en_found or zh_found):
        status = "BENCHMARK_ALIAS_INCOMPLETE"
        observations.append("source_contains_reasonable_voltage_alias")
    elif not en_found or not zh_found:
        status = "BENCHMARK_TERM_NOT_IN_SOURCE"
    return {
        "benchmark_status": status,
        "english_source_form": en_found,
        "chinese_source_form": zh_found,
        "orthographic_differences": [],
        "definition_context_sufficient": bool(en_found and zh_found and len(english_source) > 30 and len(chinese_source) > 15),
        "multiple_reasonable_expressions": status == "BENCHMARK_ALIAS_INCOMPLETE",
        "secondary_observations": observations,
    }


def build_diagnostic_rows(items, *, trace_item: Callable[[dict[str, Any]], DiagnosticTrace]):
    rows = []
    for item in tuple(items):
        trace = trace_item(item)
        row = asdict(trace)
        row["primary_attribution"] = attribute_failure(trace)
        row["included_in_denominator"] = True
        rows.append(row)
    return rows


def sanitize_artifact(value: Any) -> Any:
    forbidden_keys = {"source_text", "source_excerpt", "parsed_text", "path", "api_key", "credential"}
    if isinstance(value, dict):
        return {
            key: sanitize_artifact(item)
            for key, item in value.items()
            if str(key).casefold() not in forbidden_keys
        }
    if isinstance(value, list):
        return [sanitize_artifact(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_artifact(item) for item in value]
    return value


def _source_for_concept(gold, corpus):
    domain = gold.domain
    return (
        next(source for source in corpus if source.language == "en" and source.domain == domain),
        next(source for source in corpus if source.language == "zh" and source.domain == domain),
    )


def _contains(text: str, values: Iterable[str]) -> tuple[bool, str]:
    normalized_text = normalize(text)
    for value in values:
        if normalize(value) in normalized_text:
            return True, str(value)
    return False, ""


def _candidate_diagnostics(term: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    comparisons = [
        (candidate, compare_candidate(term, candidate["text"]))
        for candidate in candidates
    ]
    exact = [candidate for candidate, comp in comparisons if comp["raw_exact"] or comp["normalized_exact"]]
    near = [
        candidate for candidate, comp in comparisons
        if not (comp["raw_exact"] or comp["normalized_exact"])
        and (
            comp["token_order_independent_exact"]
            or comp["token_overlap"] >= 0.75
            or normalize(candidate["text"]).startswith(f"{normalize(term)} ")
        )
    ]
    overlong = [
        candidate for candidate in near
        if normalize(term) in normalize(candidate["text"]) and len(_tokens(candidate["text"])) > len(_tokens(term))
    ]
    term_tokens = set(_tokens(term))
    fragment_pool = {
        token for candidate in candidates for token in _tokens(candidate["text"])
        if len(_tokens(candidate["text"])) < len(_tokens(term))
    }
    fragmented = bool(len(term_tokens) > 1 and term_tokens <= fragment_pool and not exact)
    bounded = sorted(
        candidates,
        key=lambda item: compare_candidate(term, item["text"])["token_overlap"],
        reverse=True,
    )[:5]
    return {
        "exact": exact,
        "near": near,
        "overlong": overlong,
        "fragmented": fragmented,
        "bounded": bounded,
    }


def run_diagnosis() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if dataset.dataset_hashes() != {
        "corpus_sha256": EXPECTED_CORPUS_SHA256,
        "gold_sha256": EXPECTED_GOLD_SHA256,
    }:
        raise RuntimeError("Frozen corpus or gold hash mismatch.")
    before_db = runner.database_state()
    corpus, gold_items = dataset.build_corpus(), dataset.build_gold()
    audit_rows: list[dict[str, Any]] = []
    matrix_rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="lexibridge-12a-") as temp_name:
        temp_root = Path(temp_name)
        module = runner.load_app_module(temp_db=temp_root / "evaluation.sqlite", upload_dir=temp_root / "uploads")
        client = module.app.test_client()
        _, token = runner.create_login_user(module, client, role="teacher", prefix="teacher_12a")
        course = runner.create_course(client, token, dataset.COURSE_NAME)
        runtime_sources: dict[str, dict[str, Any]] = {}
        for source in corpus:
            upload = runner.upload_source(client, token, course_id=course["id"], source=source)
            result = runner.run_ingestion_job(module, upload["job_id"])
            runtime_sources[source.source_id] = result

        with module.app.app_context():
            from services.document_alignment_term_candidates import (
                GovernedSourceChunkSnapshot,
                extract_chunk_scoped_term_candidates,
            )

            for gold in gold_items:
                en_source, zh_source = _source_for_concept(gold, corpus)
                en_result = runtime_sources[en_source.source_id]
                zh_result = runtime_sources[zh_source.source_id]
                en_doc = module.Document.query.get(
                    module.KnowledgeSource.query.filter_by(source_uid=en_result["source_uid"]).one().document_id
                )
                zh_doc = module.Document.query.get(
                    module.KnowledgeSource.query.filter_by(source_uid=zh_result["source_uid"]).one().document_id
                )
                en_chunks = module.KnowledgeChunk.query.filter_by(source_uid=en_result["source_uid"]).order_by(module.KnowledgeChunk.chunk_index).all()
                zh_chunks = module.KnowledgeChunk.query.filter_by(source_uid=zh_result["source_uid"]).order_by(module.KnowledgeChunk.chunk_index).all()
                english_aliases: tuple[str, ...] = ()
                chinese_term = gold.accepted_chinese_terms[0]
                chinese_aliases = tuple(gold.accepted_chinese_terms[1:])
                audit = audit_benchmark_item(
                    english_term=gold.english_term,
                    english_aliases=english_aliases,
                    chinese_term=chinese_term,
                    chinese_aliases=chinese_aliases,
                    english_source=en_source.text,
                    chinese_source=zh_source.text,
                )
                audit_rows.append({
                    "concept_id": gold.concept_id,
                    "gold_english_term": gold.english_term,
                    "accepted_english_aliases": list(english_aliases),
                    "gold_chinese_term": chinese_term,
                    "accepted_chinese_aliases": list(chinese_aliases),
                    "english_source_id": en_source.source_id,
                    "chinese_source_id": zh_source.source_id,
                    "gold_english_present": bool(audit["english_source_form"]),
                    "gold_chinese_present": bool(audit["chinese_source_form"]),
                    "english_source_form": audit["english_source_form"],
                    "chinese_source_form": audit["chinese_source_form"],
                    "definition_context_sufficient": audit["definition_context_sufficient"],
                    "gold_evidence_resolves_to_ingested_chunks": bool(en_chunks and zh_chunks),
                    "benchmark_status": audit["benchmark_status"],
                    "secondary_observations": audit["secondary_observations"],
                })

                raw_candidates: list[dict[str, Any]] = []
                for chunk in en_chunks:
                    for index, candidate in enumerate(module.extract_terms_from_text(chunk.content)):
                        text = str(candidate.get("english_term") or "")
                        raw_candidates.append({
                            "id": hashlib.sha256(f"{chunk.chunk_uid}:{index}:{text}".encode()).hexdigest()[:16],
                            "text": text,
                            "chunk_uid": str(chunk.chunk_uid),
                            "length": len(text),
                            "normalized": normalize(text),
                        })
                source_obj = module.KnowledgeSource.query.filter_by(source_uid=en_result["source_uid"]).one()
                snapshots = [
                    GovernedSourceChunkSnapshot(
                        chunk_uid=str(chunk.chunk_uid),
                        source_uid=str(chunk.source_uid),
                        parse_uid=str(chunk.parse_uid),
                        source_version=str(source_obj.version),
                        chunk_index=int(chunk.chunk_index),
                        text=str(chunk.content or ""),
                        language=str(chunk.language or ""),
                        chapter_scope=str(chunk.chapter or ""),
                    )
                    for chunk in en_chunks
                ]
                formal = extract_chunk_scoped_term_candidates(
                    snapshots,
                    module.extract_terms_from_text,
                    expected_source_uid=str(source_obj.source_uid),
                    expected_parse_uid=str(source_obj.parse_uid),
                    expected_source_version=str(source_obj.version),
                )
                final_candidates = [
                    {
                        "id": hashlib.sha256(f"{source_obj.source_uid}:{candidate.normalized_term}".encode()).hexdigest()[:16],
                        "text": candidate.candidate_term,
                        "chunk_uids": list(candidate.source_chunk_uids),
                        "length": len(candidate.candidate_term),
                        "normalized": candidate.normalized_term,
                    }
                    for candidate in formal.candidates
                ]
                overflow_candidates = [
                    {
                        "id": candidate.candidate_id,
                        "text": candidate.candidate_term,
                        "chunk_uids": list(candidate.source_chunk_uids),
                        "length": len(candidate.candidate_term),
                        "normalized": candidate.normalized_term,
                    }
                    for candidate in formal.overflow_candidates
                ]
                candidate_diag = _candidate_diagnostics(
                    gold.english_term,
                    final_candidates or overflow_candidates or raw_candidates,
                )
                source_present, _ = _contains(en_source.text, (gold.english_term, *english_aliases))
                parsed_present, _ = _contains(en_doc.parsed_text, (gold.english_term, *english_aliases))
                chunk_present = any(_contains(chunk.content, (gold.english_term, *english_aliases))[0] for chunk in en_chunks)
                zh_source_present, _ = _contains(zh_source.text, (chinese_term, *chinese_aliases))
                zh_parsed_present, _ = _contains(zh_doc.parsed_text, (chinese_term, *chinese_aliases))
                zh_chunk_present = any(_contains(chunk.content, (chinese_term, *chinese_aliases))[0] for chunk in zh_chunks)
                exact_final = [item for item in final_candidates if normalize(item["text"]) == normalize(gold.english_term)]
                exact_overflow = [
                    item for item in overflow_candidates
                    if normalize(item["text"]) == normalize(gold.english_term)
                ]
                binding = "matched" if len(exact_final) == 1 else ("ambiguous" if len(exact_final) > 1 else "missing")
                trace = DiagnosticTrace(
                    concept_id=gold.concept_id,
                    source_term_present=source_present and zh_source_present,
                    parsed_text_term_present=parsed_present and zh_parsed_present,
                    chunk_term_present=chunk_present and zh_chunk_present,
                    exact_candidate_present=bool(exact_final),
                    near_candidate_present=bool(candidate_diag["near"]),
                    overlong_candidate_present=bool(candidate_diag["overlong"]),
                    fragmented_candidate_present=bool(candidate_diag["fragmented"]),
                    normalized_match_present=bool(exact_final),
                    binding_status=binding,
                    benchmark_status=audit["benchmark_status"],
                    source_candidate_limit_exceeded=formal.outcome == "item_limit_exceeded",
                    candidate_governance_overflow_present=bool(formal.overflow_candidates),
                    candidate_overflow_match_present=bool(exact_overflow),
                    ambiguous_binding=binding == "ambiguous",
                )
                primary = attribute_failure(trace)
                earliest = {
                    "PARSING_DEFECT": "parsing",
                    "CHUNKING_DEFECT": "chunking",
                    "CANDIDATE_EXTRACTION_DEFECT": "candidate_extraction",
                    "CANDIDATE_BOUNDARY_DEFECT": "candidate_boundary",
                    "CANDIDATE_GOVERNANCE_OVERFLOW": "candidate_governance",
                    "CANDIDATE_FRAGMENTATION_DEFECT": "candidate_fragmentation",
                    "NORMALIZATION_DEFECT": "normalization",
                    "BINDING_DEFECT": "binding",
                    "NO_DEFECT_MATCHED": "none",
                    "BENCHMARK_FIXTURE_DEFECT": "benchmark",
                    "SOURCE_TEXT_ABSENT": "source",
                }.get(primary, "binding")
                matrix_rows.append({
                    "concept_id": gold.concept_id,
                    "benchmark_status": audit["benchmark_status"],
                    "source_term_present": trace.source_term_present,
                    "parsed_text_term_present": trace.parsed_text_term_present,
                    "chunk_term_present": trace.chunk_term_present,
                    "exact_candidate_present": trace.exact_candidate_present,
                    "candidate_exact_present": trace.exact_candidate_present,
                    "candidate_alias_present": trace.candidate_alias_present,
                    "near_candidate_present": trace.near_candidate_present,
                    "candidate_near_present": trace.near_candidate_present,
                    "overlong_candidate_present": trace.overlong_candidate_present,
                    "candidate_overlong_present": trace.overlong_candidate_present,
                    "fragmented_candidate_present": trace.fragmented_candidate_present,
                    "candidate_fragment_present": trace.fragmented_candidate_present,
                    "normalized_match_present": trace.normalized_match_present,
                    "normalization_status": "normalized_match" if trace.normalized_match_present else "no_normalized_match",
                    "binding_status": binding,
                    "earliest_failure_stage": earliest,
                    "disappearance_stage": earliest,
                    "primary_attribution": primary,
                    "candidate_governance_overflow_present": trace.candidate_governance_overflow_present,
                    "candidate_overflow_match_present": trace.candidate_overflow_match_present,
                    "english_source_id": en_source.source_id,
                    "chinese_source_id": zh_source.source_id,
                    "chunk_ids": [str(chunk.chunk_uid) for chunk in en_chunks if _contains(chunk.content, (gold.english_term,))[0]][:5],
                    "system_candidate_ids": [item["id"] for item in candidate_diag["bounded"]],
                    "system_candidate_summaries": [item["text"][:120] for item in candidate_diag["bounded"]],
                    "candidate_lengths": [item["length"] for item in candidate_diag["bounded"]],
                    "normalization_results": [item["normalized"][:120] for item in candidate_diag["bounded"]],
                    "language_trace": {
                        "english": {"source": source_present, "parsed": parsed_present, "chunk": chunk_present},
                        "chinese": {"source": zh_source_present, "parsed": zh_parsed_present, "chunk": zh_chunk_present},
                    },
                    "secondary_observations": [
                        f"formal_extraction_outcome={formal.outcome}",
                        f"raw_candidate_count={len(raw_candidates)}",
                        f"canonical_candidate_count={formal.canonical_candidate_count}",
                        f"admitted_candidate_count={formal.admitted_candidate_count}",
                        f"overflow_candidate_count={formal.overflow_candidate_count}",
                        *audit["secondary_observations"],
                    ],
                    "included_in_denominator": True,
                })
    after_db = runner.database_state()
    if before_db != after_db:
        raise RuntimeError("Accident database changed.")
    return matrix_rows, audit_rows, {"before": before_db, "after": after_db, "real_provider_requests": 0}


def _write_json(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sanitize_artifact(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_artifacts(matrix_rows, audit_rows):
    _write_json(MATRIX_JSON, {"task": "12A", "benchmark_coverage": len(matrix_rows), "rows": matrix_rows})
    _write_json(AUDIT_JSON, {"task": "12A", "benchmark_coverage": len(audit_rows), "rows": audit_rows})
    columns = [
        "concept_id", "benchmark_status", "source_term_present", "parsed_text_term_present",
        "chunk_term_present", "exact_candidate_present", "near_candidate_present",
        "overlong_candidate_present", "fragmented_candidate_present", "normalization_status",
        "binding_status", "earliest_failure_stage", "primary_attribution",
        "secondary_observations", "included_in_denominator",
    ]
    with MATRIX_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=columns, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        for row in matrix_rows:
            copy = dict(row)
            copy["secondary_observations"] = "|".join(row["secondary_observations"])
            writer.writerow(copy)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    matrix, audit, safety = run_diagnosis()
    if args.write:
        write_artifacts(matrix, audit)
    counts: dict[str, int] = {}
    for row in matrix:
        counts[row["primary_attribution"]] = counts.get(row["primary_attribution"], 0) + 1
    print(json.dumps({
        "coverage": len(matrix),
        "matched": sum(row["binding_status"] == "matched" for row in matrix),
        "missing": sum(row["binding_status"] == "missing" for row in matrix),
        "attribution_counts": counts,
        "benchmark_defects": sum(row["benchmark_status"] != "BENCHMARK_SOURCE_VALID" for row in audit),
        **safety,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
