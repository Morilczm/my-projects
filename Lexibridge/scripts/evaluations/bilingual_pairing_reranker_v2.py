"""One-shot offline Task 12F.1 V2 reranking evaluation."""
from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/evaluations/artifacts"
PAIRING_RUNNER = ROOT / "scripts/evaluations/bilingual_semantic_pairing_v2.py"
sys.path.insert(0, str(ROOT / "backend"))

from services.local_bilingual_reranker import (  # noqa: E402
    BACKEND_ID,
    MAX_CHINESE_TOKENS,
    MAX_ENGLISH_TOKENS,
    MAX_PAIR_TOKENS,
    MODEL_ARCHITECTURE,
    MODEL_ID,
    MODEL_LICENSE,
    MODEL_REVISION,
)


ALL_25_DENOMINATOR = 25
REAL_PROVIDER_REQUESTS = 0

BASELINE_ERROR_CATEGORIES = {
    "cx-7f01": "TERM_SCOPE_CONFUSION",
    "cx-7f05": "AUXILIARY_PRIOR_DOMINANCE",
    "cx-7f10": "TERM_SCOPE_CONFUSION",
    "cx-7f11": "TERM_SCOPE_CONFUSION",
    "cx-7f13": "AUXILIARY_PRIOR_DOMINANCE",
    "cx-7f15": "AUXILIARY_PRIOR_DOMINANCE",
    "cx-7f20": "TERM_SCOPE_CONFUSION",
    "cx-7f24": "TERM_SCOPE_CONFUSION",
}


class TimedReranker:
    def __init__(self, backend):
        self._backend = backend
        self.backend_id = backend.backend_id
        self.model_id = backend.model_id
        self.model_revision = backend.model_revision
        self.elapsed_seconds = 0.0
        self.pairs_scored = 0

    def readiness(self):
        return self._backend.readiness()

    def score_pairs(self, pairs):
        started = time.perf_counter()
        scores = self._backend.score_pairs(pairs)
        self.elapsed_seconds += time.perf_counter() - started
        self.pairs_scored += len(pairs)
        return scores


def _pairing_runner():
    spec = importlib.util.spec_from_file_location(
        "bilingual_semantic_pairing_v2_for_12f1",
        PAIRING_RUNNER,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate(bi_encoder_backend, reranker_backend):
    timed = TimedReranker(reranker_backend)
    result = _pairing_runner().evaluate(
        bi_encoder_backend,
        reranker_backend=timed,
    )
    metrics = result["metrics"]
    for row in result["rows"]:
        row["baseline_error_category"] = BASELINE_ERROR_CATEGORIES.get(
            row["concept_id"],
            "",
        )
    remaining_pairing_misses = sum(
        row["primary_attribution"] == "BILINGUAL_SEMANTIC_PAIRING_MISS"
        for row in result["rows"]
    )
    evidence_missing = sum(
        row["primary_attribution"] == "EVIDENCE_QUALIFICATION_MISSING"
        for row in result["rows"]
    )
    baseline = {
        "pair_top1": 0.4286,
        "pair_top3": 0.8571,
        "pair_mrr": 0.6476,
        "pairing_miss": 8,
        "evidence_qualification_missing": 6,
    }
    improved = (
        metrics["pair_top1"] > baseline["pair_top1"]
        or metrics["pair_mrr"] > baseline["pair_mrr"]
    )
    technical_status = "BILINGUAL_RERANKING_CONTRACT_CLOSED"
    quality_status = (
        "BILINGUAL_RERANKING_QUALITY_IMPROVED"
        if improved and metrics["pair_top3"] >= baseline["pair_top3"]
        else "BILINGUAL_RERANKING_QUALITY_INSUFFICIENT"
    )
    dominant = (
        "EVIDENCE_QUALIFICATION_MISSING"
        if evidence_missing > remaining_pairing_misses
        else "BILINGUAL_SEMANTIC_PAIRING_MISS"
    )
    return {
        "technical_status": technical_status,
        "quality_status": quality_status,
        "baseline": baseline,
        "metrics": {
            **metrics,
            "pairing_miss": remaining_pairing_misses,
            "evidence_qualification_missing": evidence_missing,
            "dominant_next_failure": dominant,
        },
        "error_categories": dict(Counter(BASELINE_ERROR_CATEGORIES.values())),
        "rows": result["rows"],
        "confusion_groups": result["confusion_groups"],
        "runtime": {
            "backend_ready": bool(timed.readiness().ready),
            "backend_id": timed.backend_id,
            "model_id": timed.model_id,
            "model_revision": timed.model_revision,
            "pairs_scored": timed.pairs_scored,
            "reranking_seconds": round(timed.elapsed_seconds, 6),
            "offline_only": True,
            "external_api_requests": 0,
            "real_provider_requests": 0,
        },
        "real_provider_requests": 0,
        "external_api_requests": 0,
        "gold_alias_mapping_added": False,
    }


def write(result):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "12F1-bilingual-reranking-results.json").write_text(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"rows", "confusion_groups", "runtime"}
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )
    (OUT / "12F1-bilingual-reranking-confusion-audit.json").write_text(
        json.dumps(result["confusion_groups"], indent=2, ensure_ascii=False) + "\n"
    )
    manifest = {
        "backend_id": BACKEND_ID,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "license": MODEL_LICENSE,
        "architecture": MODEL_ARCHITECTURE,
        "controlled_pair_token_limit": MAX_PAIR_TOKENS,
        "controlled_english_token_limit": MAX_ENGLISH_TOKENS,
        "controlled_chinese_token_limit": MAX_CHINESE_TOKENS,
        "runtime": "Transformers + PyTorch CPU",
        "local_files_only": True,
        "trust_remote_code": False,
        "repository_external_cache": True,
        "model_cache_tracked": False,
        **result["runtime"],
    }
    (OUT / "12F1-reranker-backend-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    )
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(result["rows"][0]),
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(result["rows"])
    (OUT / "12F1-bilingual-reranking-matrix.csv").write_text(buffer.getvalue())


if __name__ == "__main__":
    import os

    from services.local_bilingual_reranker import LocalBilingualReranker
    from services.local_multilingual_embedding import (
        LocalMultilingualEmbeddingBackend,
    )

    cache_dir = os.environ["LEXIBRIDGE_MODEL_CACHE_DIR"]
    output = evaluate(
        LocalMultilingualEmbeddingBackend(model_cache_dir=cache_dir),
        LocalBilingualReranker(model_cache_dir=cache_dir),
    )
    write(output)
    print(json.dumps(output["metrics"], sort_keys=True))
