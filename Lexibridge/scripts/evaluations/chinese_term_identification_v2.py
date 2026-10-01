"""Provider-free Task 12E Cross-Corpus V2 Chinese term evaluation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "evaluation/cross_corpus_v2"
OUT = ROOT / "docs/evaluations/artifacts"
sys.path.insert(0, str(ROOT / "backend"))

from services.chinese_term_candidates import (  # noqa: E402
    DEFINITION_PREDICATES,
    GENERIC_CHINESE_TERMS,
    identify_standard_chinese_terms,
)
from services.cross_language_retrieval import (  # noqa: E402
    CrossLanguageRetrievalQuery,
    SemanticPassage,
    rank_chinese_passages,
)


def _paragraphs(source):
    text = (FIX / source["path"]).read_text()
    return [part.strip() for part in text.split("\n\n") if part.strip()][1:]


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _norm(text):
    return unicodedata.normalize("NFKC", str(text or "")).strip()


def evaluate(backend):
    gold = json.loads((FIX / "gold.json").read_text())
    manifest = json.loads((FIX / "manifest.json").read_text())
    import app

    extracted = []
    for source in manifest["english_sources"]:
        extracted.extend(
            item["english_term"]
            for item in app.extract_terms_from_text((FIX / source["path"]).read_text())
        )
    keys = {}
    for term in extracted:
        keys.setdefault(term.casefold().strip(), []).append(term)

    passages = []
    for source in manifest["chinese_sources"]:
        for index, text in enumerate(_paragraphs(source), 1):
            passages.append(SemanticPassage(
                source_uid=source["source_id"],
                chunk_uid=f"{source['source_id']}-p{index:02}",
                content=text,
                language="zh",
                source_status="active",
                quality_status="ready",
                content_hash=_hash(text),
            ))

    rows = []
    retrieval_ranks = []
    identification_ranks = []
    for item in gold:
        matches = keys.get(item["english_term"].casefold(), [])
        binding = "matched" if len(matches) == 1 else "missing" if not matches else "ambiguous"
        if binding != "matched":
            rows.append({
                "concept_id": item["concept_id"],
                "english_binding": binding,
                "retrieval_eligible": False,
                "identification_eligible": False,
                "retrieved_chunk_ids": "",
                "gold_chunk_rank": "",
                "candidate_ids": "",
                "candidate_summaries": "",
                "exact_candidate_rank": "",
                "exact_candidate_score": "",
                "score_margin": "",
                "candidate_count": 0,
                "generic_false_positive_count": 0,
                "definition_fragment_count": 0,
                "primary_attribution": (
                    "UPSTREAM_ENGLISH_EXTRACTION_MISSING"
                    if binding == "missing"
                    else "UPSTREAM_ENGLISH_BINDING_AMBIGUOUS"
                ),
            })
            continue

        context = ""
        for source in manifest["english_sources"]:
            for paragraph in _paragraphs(source):
                if item["english_term"].casefold() in paragraph.casefold():
                    context = paragraph
                    break
            if context:
                break
        query = CrossLanguageRetrievalQuery(
            english_candidate_uid="system-" + _hash(item["english_term"])[:12],
            canonical_english_term=item["english_term"],
            normalized_english_term=item["english_term"].casefold(),
            english_context=context,
            discipline=item["discipline"],
            allowed_chinese_source_uids=tuple(
                source["source_id"] for source in manifest["chinese_sources"]
            ),
            top_k=3,
            retrieval_budget=200,
        )
        found = rank_chinese_passages(query, passages, backend)
        correct_chunks = {
            passage.chunk_uid
            for passage in passages
            if item["chinese_term"] in passage.content
            or any(alias in passage.content for alias in item["accepted_chinese_aliases"])
        }
        gold_chunk_rank = next(
            (result.rank for result in found if result.chunk_uid in correct_chunks),
            None,
        )
        if gold_chunk_rank:
            retrieval_ranks.append(gold_chunk_rank)
        identification_eligible = bool(gold_chunk_rank and gold_chunk_rank <= 3)
        evidence = [{
            "source_uid": result.source_uid,
            "chunk_uid": result.chunk_uid,
            "language": "zh",
            "snippet": result.snippet,
            "rank": result.rank,
            "score": result.score,
            "status": result.source_status,
            "quality_status": result.quality_status,
            "source_role": "chinese_reference_material",
            "provenance": result.provenance,
        } for result in found]
        identified = identify_standard_chinese_terms(
            item["english_term"],
            evidence,
            discipline=item["discipline"],
            limit=10,
        )
        candidates = identified.candidates
        exact_rank = next(
            (
                candidate["rank"]
                for candidate in candidates
                if _norm(candidate["chinese_term"]) == _norm(item["chinese_term"])
            ),
            None,
        )
        exact_candidate = next(
            (
                candidate
                for candidate in candidates
                if _norm(candidate["chinese_term"]) == _norm(item["chinese_term"])
            ),
            None,
        )
        strongest_alternative = next(
            (candidate for candidate in candidates if candidate is not exact_candidate),
            None,
        )
        exact_score = float(exact_candidate["score"]) if exact_candidate else None
        score_margin = (
            round(exact_score - float(strongest_alternative["score"]), 4)
            if exact_candidate and strongest_alternative
            else ""
        )
        if identification_eligible and exact_rank:
            identification_ranks.append(exact_rank)
        generic_count = sum(
            _norm(candidate["chinese_term"]) in GENERIC_CHINESE_TERMS
            for candidate in candidates
        )
        fragment_count = sum(
            any(predicate in candidate["chinese_term"] for predicate in DEFINITION_PREDICATES)
            for candidate in candidates
        )
        if not identification_eligible:
            attribution = "UPSTREAM_CROSS_LANGUAGE_RETRIEVAL_MISS"
        elif not candidates:
            attribution = "CHINESE_TERM_IDENTIFICATION_MISSING"
        elif not exact_rank:
            attribution = "CHINESE_TERM_RANKING_OR_EXTRACTION_DEFECT"
        else:
            attribution = "BILINGUAL_SEMANTIC_PAIRING_MISSING"
        rows.append({
            "concept_id": item["concept_id"],
            "english_binding": binding,
            "retrieval_eligible": True,
            "identification_eligible": identification_eligible,
            "retrieved_chunk_ids": "|".join(result.chunk_uid for result in found),
            "gold_chunk_rank": gold_chunk_rank or "",
            "candidate_ids": "|".join(candidate["candidate_uid"] for candidate in candidates),
            "candidate_summaries": "|".join(
                candidate["chinese_term"][:24] for candidate in candidates
            ),
            "exact_candidate_rank": exact_rank or "",
            "exact_candidate_score": exact_score if exact_score is not None else "",
            "score_margin": score_margin,
            "candidate_count": len(candidates),
            "generic_false_positive_count": generic_count,
            "definition_fragment_count": fragment_count,
            "primary_attribution": attribution,
        })

    retrieval_eligible = [row for row in rows if row["retrieval_eligible"]]
    identification_eligible = [row for row in rows if row["identification_eligible"]]
    denominator = len(identification_eligible)
    generated = sum(bool(row["exact_candidate_rank"]) for row in identification_eligible)
    top1 = sum(row["exact_candidate_rank"] == 1 for row in identification_eligible)
    top3 = sum(
        bool(row["exact_candidate_rank"]) and int(row["exact_candidate_rank"]) <= 3
        for row in identification_eligible
    )
    metrics = {
        "coverage": len(rows),
        "english_matched": sum(row["english_binding"] == "matched" for row in rows),
        "english_missing": sum(row["english_binding"] == "missing" for row in rows),
        "english_ambiguous": sum(row["english_binding"] == "ambiguous" for row in rows),
        "retrieval_eligible": len(retrieval_eligible),
        "identification_eligible": denominator,
        "retrieval_hit_at_1": round(sum(rank == 1 for rank in retrieval_ranks) / 18, 4),
        "retrieval_hit_at_3": round(sum(rank <= 3 for rank in retrieval_ranks) / 18, 4),
        "retrieval_mrr": round(sum(1 / rank for rank in retrieval_ranks) / 18, 4),
        "chinese_evidence_retrieved": sum(bool(row["retrieved_chunk_ids"]) for row in retrieval_eligible),
        "exact_candidate_generated": generated,
        "exact_candidate_top1": top1,
        "exact_candidate_top3": top3,
        "candidate_mrr": round(
            sum(1 / int(row["exact_candidate_rank"]) for row in identification_eligible if row["exact_candidate_rank"])
            / denominator,
            4,
        ) if denominator else 0.0,
        "no_candidate_count": sum(row["candidate_count"] == 0 for row in identification_eligible),
        "generic_false_positive_count": sum(row["generic_false_positive_count"] for row in identification_eligible),
        "definition_fragment_count": sum(row["definition_fragment_count"] for row in identification_eligible),
        "pair_top1": 0,
        "pair_top3": 0,
        "evidence_qualified": 0,
        "provider_ready": 0,
    }

    groups = [
        ("电场 / 电场强度", "electric field"),
        ("电势 / 电势能", "electric potential"),
        ("角速度 / 角加速度", "angular velocity"),
        ("动量 / 角动量", "momentum"),
        ("质量 / 重量", "mass"),
    ]
    by_english = {item["english_term"]: item for item in gold}
    confusion = []
    for label, english_term in groups:
        item = by_english[english_term]
        row = next(row for row in rows if row["concept_id"] == item["concept_id"])
        rank = row["exact_candidate_rank"]
        candidate_terms = row["candidate_summaries"].split("|") if row["candidate_summaries"] else []
        confusion.append({
            "group": label,
            "concept_id": item["concept_id"],
            "retrieved_chunk_ids": row["retrieved_chunk_ids"],
            "generated_candidates": candidate_terms[:10],
            "correct_term_rank": rank,
            "score_margin": row["score_margin"],
            "generic_interference": bool(row["generic_false_positive_count"]),
            "definition_fragment_interference": bool(row["definition_fragment_count"]),
            "requires_semantic_pairing": bool(row["identification_eligible"]),
            "upstream_status": row["primary_attribution"] if not row["identification_eligible"] else "",
        })
    return {
        "technical_status": "CHINESE_STANDARD_TERM_IDENTIFICATION_CONTRACT_CLOSED",
        "quality_status": "CHINESE_STANDARD_TERM_IDENTIFICATION_QUALITY_BASELINE_ESTABLISHED",
        "metrics": metrics,
        "rows": rows,
        "confusion_groups": confusion,
        "real_provider_requests": 0,
        "external_api_requests": 0,
    }


def write(result):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "12E-chinese-term-identification-results.json").write_text(
        json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2, ensure_ascii=False) + "\n"
    )
    (OUT / "12E-chinese-term-confusion-audit.json").write_text(
        json.dumps(result["confusion_groups"], indent=2, ensure_ascii=False) + "\n"
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(result["rows"][0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(result["rows"])
    (OUT / "12E-chinese-term-identification-matrix.csv").write_text(buffer.getvalue())


if __name__ == "__main__":
    import os
    from services.local_multilingual_embedding import LocalMultilingualEmbeddingBackend

    output = evaluate(
        LocalMultilingualEmbeddingBackend(
            model_cache_dir=os.environ["LEXIBRIDGE_MODEL_CACHE_DIR"]
        )
    )
    write(output)
    print(json.dumps(output["metrics"], sort_keys=True))
