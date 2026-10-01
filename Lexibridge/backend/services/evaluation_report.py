from services.evaluation_metrics import evaluate_release_gate


def _format_metric(value):
    if value is None:
        return "not covered"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def generate_evaluation_report(run_info, results, metrics):
    gate = evaluate_release_gate(metrics)
    failures = [
        item for item in results
        if item.get("failure_reason")
        or not item.get("expected_term_found")
        or not item.get("alignment_status_correct")
        or item.get("wrongly_auto_approved")
        or item.get("no_evidence_forced_alignment")
    ]
    retrieval_errors = [
        item for item in results
        if item.get("retrieval_error")
        or (item.get("english_evidence_returned") and not item.get("english_evidence_correct"))
        or (item.get("chinese_evidence_returned") and not item.get("chinese_evidence_correct"))
    ]
    alignment_errors = [item for item in results if not item.get("alignment_status_correct")]
    auto_errors = [item for item in results if item.get("wrongly_auto_approved")]

    report_json = {
        "basic_information": run_info,
        "metrics": metrics,
        "release_gate": gate,
        "top_failure_cases": failures[:10],
        "retrieval_errors": retrieval_errors[:10],
        "alignment_errors": alignment_errors[:10],
        "auto_approval_errors": auto_errors[:10],
        "results": results,
    }

    lines = [
        "# LexiBridge AI Evaluation Report",
        "",
        "## Basic Information",
        f"- evaluation_set_id: {run_info.get('evaluation_set_id')}",
        f"- evaluation_set_name: {run_info.get('evaluation_set_name')}",
        f"- split: {run_info.get('split')}",
        f"- model_version: {run_info.get('model_version')}",
        f"- prompt_version: {run_info.get('prompt_version')}",
        f"- retrieval_version: {run_info.get('retrieval_version')}",
        f"- created_at: {run_info.get('created_at')}",
        f"- input_count: {metrics.get('input_count')}",
        f"- skipped_count: {metrics.get('skipped_count')}",
        "",
        "## Metrics",
    ]
    for name in [
        "extraction_precision",
        "extraction_recall",
        "english_evidence_accuracy",
        "chinese_evidence_accuracy",
        "evidence_accuracy",
        "alignment_accuracy",
        "false_positive_rate",
        "auto_approval_error_rate",
        "no_evidence_forced_alignment_rate",
        "ocr_noise_term_rate",
    ]:
        lines.append(f"- {name}: {_format_metric(metrics.get(name))}")

    lines.extend([
        "",
        "## Release Gate Result",
        "PASS" if gate["passed"] else "FAIL",
        "",
        "## Top Failure Cases",
    ])
    if failures:
        for item in failures[:10]:
            lines.append(
                f"- {item.get('item_id')}: {item.get('english_term')} -> "
                f"expected {item.get('expected_chinese_term')} / {item.get('expected_alignment_status')}, "
                f"actual {item.get('actual_alignment_status')}; {item.get('failure_reason') or 'metric mismatch'}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Retrieval Errors"])
    if retrieval_errors:
        for item in retrieval_errors[:10]:
            lines.append(f"- {item.get('item_id')}: {item.get('retrieval_error') or item.get('failure_reason') or 'incorrect evidence'}")
    else:
        lines.append("- None")

    lines.extend(["", "## Alignment Errors"])
    if alignment_errors:
        for item in alignment_errors[:10]:
            lines.append(
                f"- {item.get('item_id')}: expected {item.get('expected_alignment_status')}, "
                f"actual {item.get('actual_alignment_status')}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Auto Approval Errors"])
    if auto_errors:
        for item in auto_errors[:10]:
            lines.append(f"- {item.get('item_id')}: wrongly auto-approved")
    else:
        lines.append("- None")

    lines.extend([
        "",
        "## Notes",
        "- This Local MVP smoke evaluation is repeatable but small.",
        "- Metrics are not production accuracy claims.",
        "- Train/dev/test split is preserved in item metadata; do not tune thresholds on test and claim objective performance.",
    ])

    return "\n".join(lines), report_json
