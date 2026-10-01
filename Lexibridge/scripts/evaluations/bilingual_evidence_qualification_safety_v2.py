"""Task 12G.1 provider-free false-accept safety evaluation."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASE_RUNNER = ROOT / "scripts/evaluations/bilingual_evidence_qualification_v2.py"
FIX = ROOT / "evaluation/cross_corpus_v2"
OUT = ROOT / "docs/evaluations/artifacts"
sys.path.insert(0, str(ROOT / "backend"))

from services import bilingual_evidence_qualification as qualification  # noqa: E402


BASELINE_FALSE_QUALIFICATION_COUNT = 6
BASELINE_FALSE_CONCEPT_IDS = frozenset({
    "cx-7f05",
    "cx-7f15",
    "cx-7f17",
    "cx-7f19",
    "cx-7f21",
    "cx-7f25",
})
REAL_PROVIDER_REQUESTS = 0


def _load_base_runner():
    spec = importlib.util.spec_from_file_location("task_12g_base", BASE_RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _load_base_runner()


class DeterministicSafetyFixture:
    """CI-only backend; it neither downloads a model nor reads scoring gold."""

    def score_pairs(self, pairs):
        return [7.0 for _ in pairs]


def _hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode()).hexdigest()


def _frozen_task_12g_snapshot() -> dict[str, Any]:
    snapshot = BASE._frozen_pairing_snapshot()
    matrix = OUT / "12G-evidence-qualification-matrix.csv"
    with matrix.open(newline="") as handle:
        task_12g_rows = {
            row["concept_id"]: row for row in csv.DictReader(handle)
        }
    selected_fields = (
        "selected_pair_text",
        "selected_pair_uid",
        "selected_pair_semantic_score",
        "selected_pair_cross_encoder_score",
        "selected_pair_final_score",
        "selected_pair_margin",
        "selected_pair_source_uid",
        "selected_pair_chunk_uid",
        "selected_pair_retrieval_rank",
        "selected_pair_retrieval_score",
        "selected_pair_extraction_rank",
        "selected_pair_extraction_score",
        "selected_pair_backend_id",
        "selected_pair_model_id",
        "selected_pair_model_revision",
        "selected_pair_reranker_backend_id",
        "selected_pair_reranker_model_id",
        "selected_pair_reranker_model_revision",
        "selected_pair_english_hash",
        "selected_pair_chinese_hash",
    )
    numeric_fields = {
        "selected_pair_semantic_score",
        "selected_pair_cross_encoder_score",
        "selected_pair_final_score",
        "selected_pair_margin",
        "selected_pair_retrieval_score",
        "selected_pair_extraction_score",
    }
    integer_fields = {
        "selected_pair_retrieval_rank",
        "selected_pair_extraction_rank",
    }
    for row in snapshot["rows"]:
        historical = task_12g_rows[row["concept_id"]]
        for field in selected_fields:
            value: Any = historical[field]
            if value and field in numeric_fields:
                value = float(value)
            elif value and field in integer_fields:
                value = int(value)
            row[field] = value
    return snapshot


def _consistency_score(
    backend: Any,
    *,
    item: dict[str, Any],
    row: dict[str, Any],
    english_context: str,
    chinese_context: str,
) -> float:
    pair = qualification._pair_consistency_inputs(
        english_term=item["english_term"],
        english_context=english_context,
        chinese_term=row["selected_pair_text"],
        chinese_context=chinese_context,
        discipline=item.get("discipline", "physics"),
    )
    values = backend.score_pairs([pair])
    if len(values) != 1:
        raise RuntimeError("EVIDENCE_QUALIFICATION_EXECUTION_FAILED")
    return float(values[0])


def _false_category(row: dict[str, Any]) -> str:
    # Evaluation-only labels use frozen gold-derived upstream attribution.
    if not row["identification_eligible"]:
        return "UPSTREAM_STATE_GATE_BYPASS"
    if not row["pairing_eligible"]:
        return "UPSTREAM_STATE_GATE_BYPASS"
    return "TERM_SCOPE_FALSE_ACCEPT"


def evaluate(backends: Any) -> dict[str, Any]:
    pairing = _frozen_task_12g_snapshot()
    gold = json.loads((FIX / "gold.json").read_text())
    manifest = json.loads((FIX / "manifest.json").read_text())
    by_id = {item["concept_id"]: item for item in gold}
    english_map, chinese_map = BASE._source_maps(manifest)

    rows = []
    eligible_decisions = Counter()
    outside_decisions = Counter()
    false_categories = Counter()
    correct_review = 0
    false_qualified = 0

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
            "pair_consistency_score": "",
            "false_qualification": False,
            "false_qualification_category": "",
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
                (row["english_source_uid"], row["english_chunk_uid"]), ""
            )
            chinese_context = chinese_map.get(
                (row["selected_pair_source_uid"], row["selected_pair_chunk_uid"]),
                "",
            )
            consistency_score = _consistency_score(
                backends,
                item=item,
                row=row,
                english_context=english_context,
                chinese_context=chinese_context,
            )
            value = BASE._qualification_input(
                item, row, english_context, chinese_context
            )
            result = qualification.qualify_bilingual_evidence(
                replace(
                    value,
                    english_binding_status="matched",
                    retrieval_status="ready",
                    candidate_pool_status="ready",
                    pair_execution_status="succeeded",
                    pair_consistency_score=consistency_score,
                )
            )
            row["pair_consistency_score"] = round(consistency_score, 8)
            row["qualification_decision"] = result.decision
            row["qualification_score"] = result.qualification_score
            row["qualification_reason_codes"] = "|".join(result.reason_codes)
            row["qualification_result_id"] = result.result_id
            if correct_top1:
                eligible_decisions[result.decision] += 1
                if result.decision == qualification.REVIEW_REQUIRED:
                    correct_review += 1
            else:
                outside_decisions[result.decision] += 1
                if row["concept_id"] in BASELINE_FALSE_CONCEPT_IDS:
                    category = _false_category(row)
                    row["false_qualification_category"] = category
                    false_categories[category] += 1
                if result.decision == qualification.QUALIFIED:
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
    outside = [row for row in rows if not row["evidence_qualification_eligible"]]
    executed_outside = [row for row in outside if row["qualification_decision"]]
    metrics = {
        **pairing["metrics"],
        "all_25": len(rows),
        "evidence_qualification_eligible": len(eligible),
        "eligible": {
            "qualified": eligible_decisions[qualification.QUALIFIED],
            "review_required": eligible_decisions[qualification.REVIEW_REQUIRED],
            "rejected": eligible_decisions[qualification.REJECTED],
            "missing_decisions": sum(
                not row["qualification_decision"] for row in eligible
            ),
        },
        "outside_eligible": {
            "total": len(outside),
            "qualification_executed": len(executed_outside),
            "qualified": outside_decisions[qualification.QUALIFIED],
            "review_required": outside_decisions[qualification.REVIEW_REQUIRED],
            "rejected": outside_decisions[qualification.REJECTED],
        },
        "baseline_false_qualification_count": BASELINE_FALSE_QUALIFICATION_COUNT,
        "false_qualification_count": false_qualified,
        "correct_pair_review_count": correct_review,
        "evidence_qualified": eligible_decisions[qualification.QUALIFIED],
        "evidence_qualification_missing": (
            eligible_decisions[qualification.REVIEW_REQUIRED]
            + eligible_decisions[qualification.REJECTED]
        ),
        "provider_ready": 0,
        "dominant_next_failure": (
            "PROVIDER_READINESS_NOT_EVALUATED"
            if false_qualified == 0
            else "EVIDENCE_QUALIFICATION_FALSE_ACCEPT"
        ),
    }
    return {
        "technical_status": "EVIDENCE_QUALIFICATION_SAFETY_CONTRACT_CLOSED",
        "quality_status": (
            "EVIDENCE_QUALIFICATION_FALSE_ACCEPTS_CLOSED"
            if false_qualified == 0
            else "EVIDENCE_QUALIFICATION_FALSE_ACCEPTS_REDUCED"
            if false_qualified < BASELINE_FALSE_QUALIFICATION_COUNT
            else "EVIDENCE_QUALIFICATION_FALSE_ACCEPTS_UNCHANGED"
        ),
        "metrics": metrics,
        "baseline_false_qualification_categories": {
            "UPSTREAM_STATE_GATE_BYPASS": 3,
            "PAIR_UNCERTAINTY_NOT_PROPAGATED": 0,
            "TERM_SCOPE_FALSE_ACCEPT": 3,
            "SCORE_COMPONENT_DOMINANCE": 0,
            "POLICY_REASON_MAPPING_DEFECT": 0,
            "OTHER_FALSE_ACCEPT_DEFECT": 0,
        },
        "observed_outside_eligible_categories": dict(
            sorted(false_categories.items())
        ),
        "rows": rows,
        "confusion_groups": _confusion_rows(rows),
        "policy": qualification.policy_manifest(),
        "production_policy_uses_gold": False,
        "threshold_changed": False,
        "threshold_calibration_source": (
            "benchmark-external synthetic semantic-equivalence fixtures"
        ),
        "external_api_requests": 0,
        "real_provider_requests": REAL_PROVIDER_REQUESTS,
    }


def _confusion_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        "selected_pair": by_id[concept_id]["selected_pair_text"],
        "pair_score": by_id[concept_id]["selected_pair_final_score"],
        "pair_margin": by_id[concept_id]["selected_pair_margin"],
        "pair_consistency_score": by_id[concept_id]["pair_consistency_score"],
        "qualification_decision": by_id[concept_id]["qualification_decision"],
        "reason_codes": (
            by_id[concept_id]["qualification_reason_codes"].split("|")
            if by_id[concept_id]["qualification_reason_codes"]
            else []
        ),
        "false_qualification": by_id[concept_id]["false_qualification"],
        "error_layer": by_id[concept_id]["primary_attribution"],
        "english_source_uid": by_id[concept_id]["english_source_uid"],
        "english_chunk_uid": by_id[concept_id]["english_chunk_uid"],
        "chinese_source_uid": by_id[concept_id]["selected_pair_source_uid"],
        "chinese_chunk_uid": by_id[concept_id]["selected_pair_chunk_uid"],
    } for group, concept_id in groups.items()]


def write(result: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    results_payload = {
        key: value
        for key, value in result.items()
        if key not in {"rows", "confusion_groups"}
    }
    (OUT / "12G1-qualification-safety-results.json").write_text(
        json.dumps(results_payload, indent=2, ensure_ascii=False) + "\n"
    )
    (OUT / "12G1-false-qualification-audit.json").write_text(
        json.dumps(
            {
                "baseline_categories": result[
                    "baseline_false_qualification_categories"
                ],
                "observed_categories": result[
                    "observed_outside_eligible_categories"
                ],
                "confusion_groups": result["confusion_groups"],
            },
            indent=2,
            ensure_ascii=False,
        ) + "\n"
    )
    (OUT / "12G1-qualification-policy-v11-manifest.json").write_text(
        json.dumps(result["policy"], indent=2, ensure_ascii=False) + "\n"
    )
    buffer = io.StringIO()
    fields = [
        "concept_id",
        "english_binding",
        "retrieval_eligible",
        "identification_eligible",
        "pairing_eligible",
        "evidence_qualification_eligible",
        "selected_pair_text",
        "selected_pair_uid",
        "pair_consistency_score",
        "qualification_decision",
        "qualification_score",
        "qualification_reason_codes",
        "false_qualification",
        "false_qualification_category",
        "primary_attribution",
    ]
    writer = csv.DictWriter(
        buffer,
        fieldnames=fields,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(result["rows"])
    (OUT / "12G1-qualification-safety-matrix.csv").write_text(buffer.getvalue())


if __name__ == "__main__":
    raise SystemExit(
        "Use an explicitly configured local offline reranker backend."
    )
