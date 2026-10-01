"""Retrieval experiment metric helpers."""

from __future__ import annotations

import json
import time


BACKENDS_TO_COMPARE = ["lexical", "vector", "hybrid", "hybrid_rerank"]


def expected_text_for_case(case):
    return str(case.get("expected_chinese_evidence") or case.get("expected_english_evidence") or case.get("expected_positive_chunk_text") or "")


def negative_text_for_case(case):
    return str(case.get("negative_chinese_evidence") or case.get("negative_english_evidence") or case.get("negative_chunk_text") or "")


def result_text(result):
    return str(result.get("content_excerpt") or result.get("content") or "")


def evaluate_backend_cases(cases, backend_name, search_func):
    total = len(cases)
    top1 = top3 = top5 = negative_errors = forced = empty = restricted = personal_leakage = 0
    reciprocal_sum = 0.0
    latencies = []
    details = []
    for case in cases:
        start = time.time()
        results = search_func(backend_name, case)
        latencies.append((time.time() - start) * 1000)
        if not results:
            empty += 1
        expected = expected_text_for_case(case)
        negative = negative_text_for_case(case)
        expect_no = bool(case.get("expect_no_evidence"))
        rank = 0
        if expected:
            for index, result in enumerate(results[:5], start=1):
                text = result_text(result)
                if expected[:40] in text or any(token and token in text for token in expected.split()[:3]):
                    rank = index
                    break
        if rank == 1:
            top1 += 1
        if rank and rank <= 3:
            top3 += 1
        if rank and rank <= 5:
            top5 += 1
        if rank:
            reciprocal_sum += 1.0 / rank
        if negative:
            if any(negative[:40] and negative[:40] in result_text(result) for result in results[:5]):
                negative_errors += 1
        if expect_no and results:
            forced += 1
        for result in results:
            if result.get("authorization_status") == "restricted_no_derivative" and result.get("evidence_strength") == "strong":
                restricted += 1
            if result.get("visibility") == "private" and str(result.get("owner_user_id") or "") != str(case.get("owner_user_id") or ""):
                personal_leakage += 1
        details.append({"query": case.get("query"), "result_count": len(results), "expected_rank": rank})
    denominator = max(total, 1)
    return {
        "backend": backend_name,
        "case_count": total,
        "top1_accuracy": round(top1 / denominator, 4),
        "top3_accuracy": round(top3 / denominator, 4),
        "top5_accuracy": round(top5 / denominator, 4),
        "negative_match_error_rate": round(negative_errors / denominator, 4),
        "no_evidence_forced_match_rate": round(forced / denominator, 4),
        "mean_reciprocal_rank": round(reciprocal_sum / denominator, 4),
        "average_latency_ms": round(sum(latencies) / max(len(latencies), 1), 2),
        "empty_result_rate": round(empty / denominator, 4),
        "restricted_source_violation_count": restricted,
        "personal_leakage_count": personal_leakage,
        "details": details[:20],
    }


def recommend_backend(metrics_by_backend):
    lexical = metrics_by_backend.get("lexical") or {}
    best_name = "lexical"
    best = lexical
    for name, metrics in metrics_by_backend.items():
        if metrics.get("skipped"):
            continue
        if metrics.get("top1_accuracy", 0) > best.get("top1_accuracy", 0):
            best_name = name
            best = metrics
    if best_name == "lexical":
        return "Keep lexical. No tested backend improved top1 accuracy."
    if best.get("top1_accuracy", 0) - lexical.get("top1_accuracy", 0) < 0.05:
        return f"Do not promote {best_name}; top1 improvement is below 0.05."
    if best.get("negative_match_error_rate", 0) > lexical.get("negative_match_error_rate", 0):
        return f"Do not promote {best_name}; negative match error rate increased."
    if best.get("no_evidence_forced_match_rate", 0) != 0:
        return f"Do not promote {best_name}; no-evidence forced match rate is non-zero."
    if best.get("personal_leakage_count", 0) or best.get("restricted_source_violation_count", 0):
        return f"Do not promote {best_name}; safety violation count is non-zero."
    return f"{best_name} can be considered for promotion after teacher review."


def markdown_report(experiment):
    metrics = experiment.get("results", {})
    lines = [
        "# Retrieval Experiment Report",
        "",
        f"- course_id: {experiment.get('course_id')}",
        f"- kb_version_id: {experiment.get('kb_version_id')}",
        f"- recommendation: {experiment.get('recommendation')}",
        "",
        "## Metrics",
    ]
    for name, values in metrics.items():
        lines.append(f"### {name}")
        lines.append("```json")
        lines.append(json.dumps(values, ensure_ascii=False, indent=2))
        lines.append("```")
    return "\n".join(lines) + "\n"
