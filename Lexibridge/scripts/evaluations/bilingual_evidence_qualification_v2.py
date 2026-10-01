"""Provider-free Task 12G qualification over the production-selected top-1 pair."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "evaluation/cross_corpus_v2"
OUT = ROOT / "docs/evaluations/artifacts"
PAIRING_RUNNER = ROOT / "scripts/evaluations/bilingual_pairing_reranker_v2.py"
sys.path.insert(0, str(ROOT / "backend"))

from services import bilingual_evidence_qualification as qualification  # noqa: E402


ALL_25_DENOMINATOR = 25
REAL_PROVIDER_REQUESTS = 0


class _FakeBiEncoder:
    backend_id = "local_multilingual_e5_pytorch_cpu_v1"
    model_id = "intfloat/multilingual-e5-small"
    model_revision = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    dimension = 2

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def embed_queries(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_passages(self, texts):
        return [[1.0, 0.0] for _ in texts]


class _FakeReranker:
    backend_id = "local_bge_reranker_v2_m3_cpu_v1"
    model_id = "BAAI/bge-reranker-v2-m3"
    model_revision = "79c481748842b7efa0a12db59915db91731f0b93"

    def readiness(self):
        return type("Readiness", (), {"ready": True})()

    def score_pairs(self, pairs):
        # Stable fixture behavior, not a lexical or gold-aware substitute.
        return [0.5 - index * 0.01 for index, _ in enumerate(pairs)]


class DeterministicQualificationFixture:
    use_frozen_upstream_snapshot = True


def _load_pairing_runner():
    spec = importlib.util.spec_from_file_location("task_12f1_for_12g", PAIRING_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frozen_pairing_snapshot():
    matrix = ROOT / "docs/evaluations/artifacts/12F1-bilingual-reranking-matrix.csv"
    results = json.loads(
        (ROOT / "docs/evaluations/artifacts/12F1-bilingual-reranking-results.json").read_text()
    )
    rows = []
    bool_fields = {"retrieval_eligible", "identification_eligible", "pairing_eligible"}
    int_fields = {
        "gold_chunk_rank", "candidate_pool_size", "exact_candidate_rank",
        "correct_pair_rank",
    }
    float_fields = {
        "semantic_score", "cross_encoder_score", "final_score", "score_margin",
    }
    with matrix.open(newline="") as handle:
        for source in csv.DictReader(handle):
            row = dict(source)
            for key in bool_fields:
                row[key] = row[key] == "True"
            for key in int_fields:
                row[key] = int(row[key]) if row[key] else ""
            for key in float_fields:
                row[key] = float(row[key]) if row[key] else ""
            row.update({
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
            })
            rows.append(row)
    return {"rows": rows, "metrics": results["metrics"]}


def _paragraphs(source):
    text = (FIX / source["path"]).read_text()
    return [part.strip() for part in text.split("\n\n") if part.strip()][1:]


def _source_maps(manifest):
    english = {}
    chinese = {}
    for source in manifest["english_sources"]:
        for index, paragraph in enumerate(_paragraphs(source), 1):
            english[(source["source_id"], f"{source['source_id']}-p{index:02}")] = paragraph
    for source in manifest["chinese_sources"]:
        for index, paragraph in enumerate(_paragraphs(source), 1):
            chinese[(source["source_id"], f"{source['source_id']}-p{index:02}")] = paragraph
    return english, chinese


def _hash(value):
    return hashlib.sha256(str(value or "").encode()).hexdigest()


def _qualification_input(item, row, english_context, chinese_context):
    selected_term = row["selected_pair_text"]
    return qualification.BilingualEvidenceQualificationInput(
        english_candidate_uid="system-" + _hash(item["english_term"])[:12],
        english_term=item["english_term"],
        normalized_english_term=item["english_term"].casefold(),
        english_context=english_context,
        english_source_uid=row["english_source_uid"],
        english_chunk_uid=row["english_chunk_uid"],
        english_evidence_span=english_context,
        english_source_language="en",
        english_source_status="active",
        english_quality_status="ready",
        chinese_candidate_uid=row["selected_pair_uid"],
        chinese_term=selected_term,
        normalized_chinese_term=selected_term,
        chinese_context=chinese_context,
        chinese_source_uid=row["selected_pair_source_uid"],
        chinese_chunk_uid=row["selected_pair_chunk_uid"],
        chinese_evidence_span=chinese_context,
        chinese_source_language="zh",
        chinese_source_status="active",
        chinese_quality_status="ready",
        retrieval_score=float(row["selected_pair_retrieval_score"] or 0.0),
        retrieval_rank=int(row["selected_pair_retrieval_rank"] or 999),
        extraction_score=float(row["selected_pair_extraction_score"] or 0.0),
        extraction_rank=int(row["selected_pair_extraction_rank"] or 999),
        pair_rank=1,
        bi_encoder_score=float(row["selected_pair_semantic_score"] or 0.0),
        reranker_score=(
            float(row["selected_pair_cross_encoder_score"])
            if row["selected_pair_cross_encoder_score"] != ""
            else None
        ),
        final_pair_score=float(row["selected_pair_final_score"] or 0.0),
        pair_score_margin=float(row["selected_pair_margin"] or 0.0),
        pair_backend_id=row["selected_pair_backend_id"],
        pair_model_id=row["selected_pair_model_id"],
        pair_model_revision=row["selected_pair_model_revision"],
        reranker_backend_id=row["selected_pair_reranker_backend_id"],
        reranker_model_id=row["selected_pair_reranker_model_id"],
        reranker_model_revision=row["selected_pair_reranker_model_revision"],
        english_representation_hash=row["selected_pair_english_hash"],
        chinese_representation_hash=row["selected_pair_chinese_hash"],
    )


def evaluate(backends):
    pairing = (
        _frozen_pairing_snapshot()
        if getattr(backends, "use_frozen_upstream_snapshot", False)
        else _load_pairing_runner().evaluate(
            backends.bi_encoder,
            backends.reranker,
        )
    )
    gold = json.loads((FIX / "gold.json").read_text())
    manifest = json.loads((FIX / "manifest.json").read_text())
    by_id = {item["concept_id"]: item for item in gold}
    english_map, chinese_map = _source_maps(manifest)
    rows = []
    decisions = Counter()
    reasons = Counter()
    false_qualified = 0
    margins = []

    for source_row in pairing["rows"]:
        row = dict(source_row)
        item = by_id[row["concept_id"]]
        row.update({
            "english_source_uid": "",
            "english_chunk_uid": "",
            "evidence_qualification_eligible": False,
            "qualification_decision": "",
            "qualification_score": "",
            "qualification_reason_codes": "",
            "qualification_result_id": "",
            "false_qualification": False,
        })
        if row["english_binding"] == "matched":
            for (source_uid, chunk_uid), paragraph in english_map.items():
                if item["english_term"].casefold() in paragraph.casefold():
                    row["english_source_uid"] = source_uid
                    row["english_chunk_uid"] = chunk_uid
                    break

        correct_top1 = bool(
            row["pairing_eligible"] and int(row["correct_pair_rank"] or 0) == 1
        )
        row["evidence_qualification_eligible"] = correct_top1
        if row["selected_pair_uid"]:
            english_context = english_map.get(
                (row["english_source_uid"], row["english_chunk_uid"]),
                "",
            )
            chinese_context = chinese_map.get(
                (
                    row["selected_pair_source_uid"],
                    row["selected_pair_chunk_uid"],
                ),
                "",
            )
            result = qualification.qualify_bilingual_evidence_v1(
                _qualification_input(item, row, english_context, chinese_context)
            )
            row["qualification_decision"] = result.decision
            row["qualification_score"] = result.qualification_score
            row["qualification_reason_codes"] = "|".join(result.reason_codes)
            row["qualification_result_id"] = result.result_id
            decisions[result.decision] += int(correct_top1)
            reasons.update(result.reason_codes if correct_top1 else ())
            if correct_top1:
                margins.append(result.pair_margin)
            elif result.decision == qualification.QUALIFIED:
                row["false_qualification"] = True
                false_qualified += 1

        if not row["retrieval_eligible"]:
            attribution = row["primary_attribution"]
        elif not row["identification_eligible"]:
            attribution = "UPSTREAM_CROSS_LANGUAGE_RETRIEVAL_MISS"
        elif not row["pairing_eligible"]:
            attribution = "UPSTREAM_CHINESE_TERM_IDENTIFICATION_MISSING"
        elif not correct_top1:
            attribution = "UPSTREAM_BILINGUAL_SEMANTIC_PAIRING_MISS"
        elif row["qualification_decision"] == qualification.QUALIFIED:
            attribution = "PROVIDER_READINESS_NOT_EVALUATED"
        elif row["qualification_decision"] == qualification.REVIEW_REQUIRED:
            attribution = "EVIDENCE_QUALIFICATION_REVIEW_REQUIRED"
        else:
            attribution = "EVIDENCE_QUALIFICATION_REJECTED"
        row["primary_attribution"] = attribution
        rows.append(row)

    eligible = [row for row in rows if row["evidence_qualification_eligible"]]
    metrics = {
        **pairing["metrics"],
        "evidence_qualification_eligible": len(eligible),
        "qualified": decisions[qualification.QUALIFIED],
        "review_required": decisions[qualification.REVIEW_REQUIRED],
        "rejected": decisions[qualification.REJECTED],
        "qualification_rate": round(
            decisions[qualification.QUALIFIED] / len(eligible), 4
        ) if eligible else 0.0,
        "false_qualification_count": false_qualified,
        "no_decision_count": sum(not row["qualification_decision"] for row in eligible),
        "evidence_qualified": decisions[qualification.QUALIFIED],
        "evidence_qualification_missing": (
            decisions[qualification.REVIEW_REQUIRED]
            + decisions[qualification.REJECTED]
        ),
        "provider_ready": 0,
        "pair_margin_min": min(margins) if margins else None,
        "pair_margin_median": (
            sorted(margins)[len(margins) // 2] if margins else None
        ),
        "pair_margin_max": max(margins) if margins else None,
        "dominant_next_failure": (
            "PROVIDER_READINESS_NOT_EVALUATED"
            if decisions[qualification.QUALIFIED]
            else "EVIDENCE_QUALIFICATION_MISSING"
        ),
    }
    return {
        "technical_status": "BILINGUAL_EVIDENCE_QUALIFICATION_CONTRACT_CLOSED",
        "quality_status": (
            "BILINGUAL_EVIDENCE_QUALIFICATION_QUALITY_INSUFFICIENT"
            if false_qualified
            else "BILINGUAL_EVIDENCE_QUALIFICATION_QUALITY_BASELINE_ESTABLISHED"
        ),
        "metrics": metrics,
        "reason_counts": dict(sorted(reasons.items())),
        "rows": rows,
        "confusion_groups": _confusion_rows(rows),
        "policy": qualification.legacy_policy_manifest(),
        "external_api_requests": 0,
        "real_provider_requests": 0,
        "scoring_reference_data_used_by_policy": False,
        "threshold_changed": False,
    }


def _confusion_rows(rows):
    groups = {
        "electric field / electric field strength": "cx-7f22",
        "electric potential / electric potential energy": "cx-7f23",
        "angular velocity / angular acceleration": "cx-7f18",
        "momentum / angular momentum": "cx-7f03",
        "mass / weight": "cx-7f05",
    }
    by_id = {row["concept_id"]: row for row in rows}
    return [{
        "group": group,
        "concept_id": concept_id,
        "upstream_eligibility": bool(by_id[concept_id]["pairing_eligible"]),
        "selected_pair": by_id[concept_id]["selected_pair_text"],
        "pair_rank": 1 if by_id[concept_id]["selected_pair_text"] else "",
        "pair_score": by_id[concept_id]["selected_pair_final_score"],
        "pair_margin": by_id[concept_id]["selected_pair_margin"],
        "english_source_uid": by_id[concept_id]["english_source_uid"],
        "english_chunk_uid": by_id[concept_id]["english_chunk_uid"],
        "chinese_source_uid": by_id[concept_id]["selected_pair_source_uid"],
        "chinese_chunk_uid": by_id[concept_id]["selected_pair_chunk_uid"],
        "qualification_decision": by_id[concept_id]["qualification_decision"],
        "reason_codes": by_id[concept_id]["qualification_reason_codes"].split("|")
        if by_id[concept_id]["qualification_reason_codes"] else [],
        "false_qualification": by_id[concept_id]["false_qualification"],
        "error_layer": by_id[concept_id]["primary_attribution"],
    } for group, concept_id in groups.items()]


def sanitized_results(result):
    return json.dumps(
        {
            key: value
            for key, value in result.items()
            if key not in {"rows", "confusion_groups"}
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def write(result):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "12G-evidence-qualification-results.json").write_text(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"rows", "confusion_groups"}
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )
    (OUT / "12G-evidence-qualification-confusion-audit.json").write_text(
        json.dumps(result["confusion_groups"], indent=2, ensure_ascii=False) + "\n"
    )
    (OUT / "12G-evidence-qualification-policy-manifest.json").write_text(
        json.dumps(result["policy"], indent=2, ensure_ascii=False) + "\n"
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(result["rows"][0]),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(result["rows"])
    (OUT / "12G-evidence-qualification-matrix.csv").write_text(buffer.getvalue())


if __name__ == "__main__":
    import os
    from services.local_bilingual_reranker import LocalBilingualReranker
    from services.local_multilingual_embedding import LocalMultilingualEmbeddingBackend

    cache = os.environ["LEXIBRIDGE_MODEL_CACHE_DIR"]
    runtime = type("Backends", (), {
        "bi_encoder": LocalMultilingualEmbeddingBackend(model_cache_dir=cache),
        "reranker": LocalBilingualReranker(model_cache_dir=cache),
    })()
    output = evaluate(runtime)
    write(output)
    print(json.dumps(output["metrics"], sort_keys=True))
