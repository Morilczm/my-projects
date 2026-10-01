"""Provider-free Task 12F Cross-Corpus V2 semantic pairing evaluation."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "evaluation/cross_corpus_v2"
OUT = ROOT / "docs/evaluations/artifacts"
sys.path.insert(0, str(ROOT / "backend"))

from services.bilingual_semantic_pairing import (  # noqa: E402
    EnglishPairingInput,
    rank_bilingual_pairs,
)
from services.chinese_term_candidates import (  # noqa: E402
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
    return hashlib.sha256(str(text).encode()).hexdigest()


def _norm(text):
    return unicodedata.normalize("NFKC", str(text or "")).strip()


class TimedBackend:
    """Measure local calls without changing backend semantics."""

    def __init__(self, backend):
        self._backend = backend
        self.backend_id = backend.backend_id
        self.model_id = backend.model_id
        self.model_revision = backend.model_revision
        self.dimension = getattr(backend, "dimension", 384)
        self.query_embedding_seconds = 0.0
        self.passage_embedding_seconds = 0.0
        self.query_batches = 0
        self.passage_batches = 0

    def readiness(self):
        return self._backend.readiness()

    def embed_queries(self, texts):
        started = time.perf_counter()
        values = self._backend.embed_queries(texts)
        self.query_embedding_seconds += time.perf_counter() - started
        self.query_batches += 1
        return values

    def embed_passages(self, texts):
        started = time.perf_counter()
        values = self._backend.embed_passages(texts)
        self.passage_embedding_seconds += time.perf_counter() - started
        self.passage_batches += 1
        return values


def _english_inventory(manifest):
    import app

    extracted = []
    contexts = {}
    for source in manifest["english_sources"]:
        source_text = (FIX / source["path"]).read_text()
        extracted.extend(item["english_term"] for item in app.extract_terms_from_text(source_text))
        for index, paragraph in enumerate(_paragraphs(source), 1):
            contexts[(source["source_id"], index)] = paragraph
    keys = {}
    for term in extracted:
        keys.setdefault(term.casefold().strip(), []).append(term)
    return keys, contexts


def _find_english_context(item, manifest):
    for source in manifest["english_sources"]:
        for index, paragraph in enumerate(_paragraphs(source), 1):
            if item["english_term"].casefold() in paragraph.casefold():
                return source["source_id"], f"{source['source_id']}-p{index:02}", paragraph
    return "", "", ""


def _chinese_passages(manifest):
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
    return passages


def evaluate(backend, reranker_backend=None):
    timed = TimedBackend(backend)
    gold = json.loads((FIX / "gold.json").read_text())
    manifest = json.loads((FIX / "manifest.json").read_text())
    english_keys, _ = _english_inventory(manifest)
    passages = _chinese_passages(manifest)
    allowed_sources = tuple(source["source_id"] for source in manifest["chinese_sources"])

    rows = []
    retrieval_ranks = []
    candidate_ranks = []
    pair_ranks = []
    pairs_scored = 0
    ranking_seconds = 0.0
    for item in gold:
        matches = english_keys.get(item["english_term"].casefold(), [])
        binding = "matched" if len(matches) == 1 else "missing" if not matches else "ambiguous"
        base = {
            "concept_id": item["concept_id"],
            "english_binding": binding,
            "retrieval_eligible": binding == "matched",
            "identification_eligible": False,
            "pairing_eligible": False,
            "gold_chunk_rank": "",
            "candidate_pool_size": 0,
            "candidate_summaries": "",
            "exact_candidate_rank": "",
            "pair_summaries": "",
            "correct_pair_rank": "",
            "semantic_score": "",
            "cross_encoder_score": "",
            "final_score": "",
            "score_margin": "",
            "selected_pair_text": "",
            "selected_pair_uid": "",
            "selected_pair_semantic_score": "",
            "selected_pair_cross_encoder_score": "",
            "selected_pair_final_score": "",
            "selected_pair_margin": "",
            "selected_pair_source_uid": "",
            "selected_pair_chunk_uid": "",
            "selected_pair_retrieval_rank": "",
            "selected_pair_retrieval_score": "",
            "selected_pair_extraction_rank": "",
            "selected_pair_extraction_score": "",
            "selected_pair_backend_id": "",
            "selected_pair_model_id": "",
            "selected_pair_model_revision": "",
            "selected_pair_reranker_backend_id": "",
            "selected_pair_reranker_model_id": "",
            "selected_pair_reranker_model_revision": "",
            "selected_pair_english_hash": "",
            "selected_pair_chinese_hash": "",
            "primary_attribution": "",
        }
        if binding != "matched":
            base["primary_attribution"] = (
                "UPSTREAM_ENGLISH_EXTRACTION_MISSING"
                if binding == "missing"
                else "UPSTREAM_ENGLISH_BINDING_AMBIGUOUS"
            )
            rows.append(base)
            continue

        english_source_uid, english_chunk_uid, context = _find_english_context(item, manifest)
        query = CrossLanguageRetrievalQuery(
            english_candidate_uid="system-" + _hash(item["english_term"])[:12],
            canonical_english_term=item["english_term"],
            normalized_english_term=item["english_term"].casefold(),
            english_context=context,
            discipline=item["discipline"],
            allowed_chinese_source_uids=allowed_sources,
            top_k=3,
            retrieval_budget=200,
        )
        found = rank_chinese_passages(query, passages, timed)
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
        candidates = identify_standard_chinese_terms(
            item["english_term"],
            evidence,
            discipline=item["discipline"],
            limit=10,
        ).candidates
        exact_candidate_rank = next(
            (
                candidate["rank"]
                for candidate in candidates
                if _norm(candidate["chinese_term"]) == _norm(item["chinese_term"])
            ),
            None,
        )
        if identification_eligible and exact_candidate_rank:
            candidate_ranks.append(exact_candidate_rank)
        pairing_eligible = bool(identification_eligible and exact_candidate_rank)
        pairs = []
        if candidates:
            started = time.perf_counter()
            pairs = rank_bilingual_pairs(
                EnglishPairingInput(
                    english_candidate_uid=query.english_candidate_uid,
                    canonical_english_term=item["english_term"],
                    normalized_english_term=item["english_term"].casefold(),
                    english_context=context,
                    discipline=item["discipline"],
                    provenance={
                        "source_uid": english_source_uid,
                        "chunk_uid": english_chunk_uid,
                    },
                ),
                candidates,
                timed,
                reranker_backend=reranker_backend,
            )
            ranking_seconds += time.perf_counter() - started
            pairs_scored += len(pairs)
        correct_pair = next(
            (
                pair for pair in pairs
                if _norm(pair.chinese_candidate_text) == _norm(item["chinese_term"])
            ),
            None,
        )
        correct_pair_rank = correct_pair.rank if correct_pair else None
        if pairing_eligible and correct_pair_rank:
            pair_ranks.append(correct_pair_rank)
        strongest_wrong = next(
            (
                pair for pair in pairs
                if _norm(pair.chinese_candidate_text) != _norm(item["chinese_term"])
            ),
            None,
        )
        margin = (
            round(correct_pair.final_score - strongest_wrong.final_score, 6)
            if correct_pair and strongest_wrong
            else ""
        )
        selected_pair = pairs[0] if pairs else None
        selected_candidate = next(
            (
                candidate
                for candidate in candidates
                if selected_pair
                and candidate.get("candidate_uid")
                == selected_pair.chinese_candidate_uid
            ),
            None,
        )
        selected_margin = (
            round(pairs[0].final_score - pairs[1].final_score, 6)
            if len(pairs) > 1
            else (round(pairs[0].final_score, 6) if pairs else "")
        )
        if not identification_eligible:
            attribution = "UPSTREAM_CROSS_LANGUAGE_RETRIEVAL_MISS"
        elif not pairing_eligible:
            attribution = "UPSTREAM_CHINESE_TERM_IDENTIFICATION_MISSING"
        elif correct_pair_rank != 1:
            attribution = "BILINGUAL_SEMANTIC_PAIRING_MISS"
        else:
            attribution = "EVIDENCE_QUALIFICATION_MISSING"
        base.update({
            "identification_eligible": identification_eligible,
            "pairing_eligible": pairing_eligible,
            "gold_chunk_rank": gold_chunk_rank or "",
            "candidate_pool_size": len(candidates),
            "candidate_summaries": "|".join(
                candidate["chinese_term"][:24] for candidate in candidates
            ),
            "exact_candidate_rank": exact_candidate_rank or "",
            "pair_summaries": "|".join(
                f"{pair.chinese_candidate_text[:24]}:{pair.final_score:.6f}"
                for pair in pairs
            ),
            "correct_pair_rank": correct_pair_rank or "",
            "semantic_score": correct_pair.semantic_score if correct_pair else "",
            "cross_encoder_score": (
                correct_pair.cross_encoder_score
                if correct_pair and correct_pair.cross_encoder_score is not None
                else ""
            ),
            "final_score": correct_pair.final_score if correct_pair else "",
            "score_margin": margin,
            "selected_pair_text": (
                selected_pair.chinese_candidate_text if selected_pair else ""
            ),
            "selected_pair_uid": (
                selected_pair.chinese_candidate_uid if selected_pair else ""
            ),
            "selected_pair_semantic_score": (
                selected_pair.semantic_score if selected_pair else ""
            ),
            "selected_pair_cross_encoder_score": (
                selected_pair.cross_encoder_score
                if selected_pair and selected_pair.cross_encoder_score is not None
                else ""
            ),
            "selected_pair_final_score": (
                selected_pair.final_score if selected_pair else ""
            ),
            "selected_pair_margin": selected_margin,
            "selected_pair_source_uid": (
                selected_pair.source_uid if selected_pair else ""
            ),
            "selected_pair_chunk_uid": (
                selected_pair.chunk_uid if selected_pair else ""
            ),
            "selected_pair_retrieval_rank": (
                selected_pair.retrieval_rank if selected_pair else ""
            ),
            "selected_pair_retrieval_score": (
                selected_candidate.get("retrieval_score", "")
                if selected_candidate
                else ""
            ),
            "selected_pair_extraction_rank": (
                selected_pair.extraction_rank if selected_pair else ""
            ),
            "selected_pair_extraction_score": (
                selected_candidate.get("score", "")
                if selected_candidate
                else ""
            ),
            "selected_pair_backend_id": (
                selected_pair.backend_id if selected_pair else ""
            ),
            "selected_pair_model_id": (
                selected_pair.model_id if selected_pair else ""
            ),
            "selected_pair_model_revision": (
                selected_pair.model_revision if selected_pair else ""
            ),
            "selected_pair_reranker_backend_id": (
                selected_pair.reranker_backend_id if selected_pair else ""
            ),
            "selected_pair_reranker_model_id": (
                selected_pair.reranker_model_id if selected_pair else ""
            ),
            "selected_pair_reranker_model_revision": (
                selected_pair.reranker_model_revision if selected_pair else ""
            ),
            "selected_pair_english_hash": (
                selected_pair.english_representation_hash if selected_pair else ""
            ),
            "selected_pair_chinese_hash": (
                selected_pair.chinese_representation_hash if selected_pair else ""
            ),
            "primary_attribution": attribution,
        })
        rows.append(base)

    retrieval_eligible = [row for row in rows if row["retrieval_eligible"]]
    identification_eligible = [row for row in rows if row["identification_eligible"]]
    pairing_eligible = [row for row in rows if row["pairing_eligible"]]

    def _ranking_metrics(ranks, denominator):
        return {
            "top1": round(sum(rank == 1 for rank in ranks) / denominator, 4) if denominator else 0.0,
            "top3": round(sum(rank <= 3 for rank in ranks) / denominator, 4) if denominator else 0.0,
            "mrr": round(sum(1 / rank for rank in ranks) / denominator, 4) if denominator else 0.0,
        }

    pair_metrics = _ranking_metrics(pair_ranks, len(pairing_eligible))
    candidate_metrics = _ranking_metrics(candidate_ranks, len(identification_eligible))
    metrics = {
        "coverage": len(rows),
        "english_matched": sum(row["english_binding"] == "matched" for row in rows),
        "english_missing": sum(row["english_binding"] == "missing" for row in rows),
        "english_ambiguous": sum(row["english_binding"] == "ambiguous" for row in rows),
        "retrieval_eligible": len(retrieval_eligible),
        "identification_eligible": len(identification_eligible),
        "pairing_eligible": len(pairing_eligible),
        "retrieval_hit_at_1": round(sum(rank == 1 for rank in retrieval_ranks) / len(retrieval_eligible), 4),
        "retrieval_hit_at_3": round(sum(rank <= 3 for rank in retrieval_ranks) / len(retrieval_eligible), 4),
        "retrieval_mrr": round(sum(1 / rank for rank in retrieval_ranks) / len(retrieval_eligible), 4),
        "exact_chinese_candidates": sum(bool(row["exact_candidate_rank"]) for row in rows),
        "candidate_top1_count": sum(rank == 1 for rank in candidate_ranks),
        "candidate_top3_count": sum(rank <= 3 for rank in candidate_ranks),
        "candidate_top1": candidate_metrics["top1"],
        "candidate_top3": candidate_metrics["top3"],
        "candidate_mrr": candidate_metrics["mrr"],
        "pair_top1_count": sum(rank == 1 for rank in pair_ranks),
        "pair_top3_count": sum(rank <= 3 for rank in pair_ranks),
        "pair_top1": pair_metrics["top1"],
        "pair_top3": pair_metrics["top3"],
        "pair_mrr": pair_metrics["mrr"],
        "no_pair_count": sum(not row["correct_pair_rank"] for row in pairing_eligible),
        "chinese_evidence_retrieved": len(retrieval_eligible),
        "correct_chinese_evidence_top3": len(identification_eligible),
        "evidence_qualified": 0,
        "provider_ready": 0,
    }
    groups = [
        ("electric field / electric field strength", "electric field"),
        ("electric potential / electric potential energy", "electric potential"),
        ("angular velocity / angular acceleration", "angular velocity"),
        ("momentum / angular momentum", "momentum"),
        ("mass / weight", "mass"),
    ]
    by_english = {item["english_term"]: item for item in gold}
    confusion = []
    for label, english_term in groups:
        item = by_english[english_term]
        row = next(row for row in rows if row["concept_id"] == item["concept_id"])
        pair_terms = [
            part.split(":", 1)[0] for part in row["pair_summaries"].split("|") if part
        ]
        confusion.append({
            "group": label,
            "concept_id": item["concept_id"],
            "upstream_eligible": row["pairing_eligible"],
            "english_query_hash": _hash(english_term),
            "candidate_pool": row["candidate_summaries"].split("|")[:10] if row["candidate_summaries"] else [],
            "candidate_extraction_rank": row["exact_candidate_rank"],
            "semantic_pairing_ranks": pair_terms[:10],
            "correct_pair_rank": row["correct_pair_rank"],
            "semantic_score": row["semantic_score"],
            "final_score": row["final_score"],
            "score_margin": row["score_margin"],
            "primary_attribution": row["primary_attribution"],
            "requires_reranker": row["primary_attribution"] == "BILINGUAL_SEMANTIC_PAIRING_MISS",
        })
    runtime = {
        "backend_ready": bool(timed.readiness().ready),
        "backend_id": timed.backend_id,
        "model_id": timed.model_id,
        "model_revision": timed.model_revision,
        "pairing_eligible": len(pairing_eligible),
        "candidate_pairs_scored": pairs_scored,
        "query_embedding_seconds": round(timed.query_embedding_seconds, 6),
        "passage_embedding_seconds": round(timed.passage_embedding_seconds, 6),
        "pairing_total_seconds": round(ranking_seconds, 6),
        "cache_contract": "repository_external_model_cache; request-local representations",
        "failure_reasons": {
            reason: sum(row["primary_attribution"] == reason for row in rows)
            for reason in sorted({row["primary_attribution"] for row in rows})
        },
    }
    return {
        "technical_status": "BILINGUAL_SEMANTIC_PAIRING_CONTRACT_CLOSED",
        "quality_status": "BILINGUAL_SEMANTIC_PAIRING_QUALITY_BASELINE_ESTABLISHED",
        "metrics": metrics,
        "rows": rows,
        "confusion_groups": confusion,
        "runtime": runtime,
        "real_provider_requests": 0,
        "external_api_requests": 0,
        "gold_alias_mapping_added": False,
    }


def write(result):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "12F-bilingual-semantic-pairing-results.json").write_text(
        json.dumps(
            {
                "technical_status": result["technical_status"],
                "quality_status": result["quality_status"],
                "metrics": result["metrics"],
                "real_provider_requests": 0,
                "external_api_requests": 0,
                "gold_alias_mapping_added": False,
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )
    (OUT / "12F-bilingual-pairing-confusion-audit.json").write_text(
        json.dumps(result["confusion_groups"], indent=2, ensure_ascii=False) + "\n"
    )
    (OUT / "12F-bilingual-pairing-backend-runtime.json").write_text(
        json.dumps(result["runtime"], indent=2, ensure_ascii=False) + "\n"
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(result["rows"][0]),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(result["rows"])
    (OUT / "12F-bilingual-semantic-pairing-matrix.csv").write_text(buffer.getvalue())


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
