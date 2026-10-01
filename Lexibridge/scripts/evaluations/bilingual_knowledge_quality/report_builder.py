"""Report builders for Task 11E bilingual knowledge quality artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.evaluations.bilingual_knowledge_quality import dataset, metrics


BASELINE_COMMIT = "0ff4f22ac3b2060629b779bdfb1c37ae36838b62"
TASK_ID = "11E"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_artifact(
    *,
    status: str,
    branch: str,
    runtime: dict[str, Any],
    provider: dict[str, Any],
    pipeline: dict[str, Any],
    quality_metrics: dict[str, Any],
    concept_outputs: list[dict[str, Any]],
    database_protection: dict[str, Any],
    privacy_network: dict[str, Any],
    blocker: str = "",
) -> dict[str, Any]:
    artifact = {
        "task": TASK_ID,
        "schema_version": dataset.SCHEMA_VERSION,
        "created_at": utc_now(),
        "status": status,
        "baseline_commit": BASELINE_COMMIT,
        "branch": branch,
        "blocker": blocker,
        "corpus": {
            "course": dataset.COURSE_NAME,
            "random_seed": dataset.RANDOM_SEED,
            "sources": [source.to_dict(include_text=False) for source in dataset.build_corpus()],
            **dataset.dataset_hashes(),
            "frozen_before_run": True,
        },
        "gold": {
            "concept_count": len(dataset.build_gold()),
            "concepts": [item.to_dict() for item in dataset.build_gold()],
        },
        "runtime": runtime,
        "provider": provider,
        "pipeline": pipeline,
        "quality_metrics": _json_safe_metrics(quality_metrics),
        "concept_outputs": [metrics.sanitize_artifact(item) for item in concept_outputs],
        "dominant_failure_stage": metrics.dominant_failure_stage(quality_metrics),
        "database_protection": database_protection,
        "privacy_network": privacy_network,
        "remaining_limitations": [
            "Synthetic corpus only; no real teacher blind review.",
            "Real semantic quality is blocked unless a production allowlisted Provider is available through the Formal Workflow policy.",
            "Complex PDF parsing is outside Task 11E.",
            "Production embedding/vector retrieval is not implemented in this task.",
            "Formula structure recognition, LaTeX, and MathML are outside this task.",
        ],
    }
    safe = metrics.sanitize_artifact(artifact)
    metrics.validate_artifact(safe)
    return safe


def build_review_packet_lines(concept_outputs: list[dict[str, Any]], quality_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    scored = quality_metrics.get("concept_results") or {}
    lines = []
    for item in sorted(concept_outputs, key=lambda value: value.get("concept_id", "")):
        concept_id = item.get("concept_id", "")
        concept_score = scored.get(concept_id, {})
        lines.append(metrics.sanitize_artifact({
            "concept_id": concept_id,
            "system_english_term": item.get("english_term", ""),
            "system_chinese_term": item.get("chinese_term", ""),
            "english_evidence": item.get("english_evidence", []),
            "chinese_evidence": item.get("chinese_evidence", []),
            "explanation": item.get("explanation", ""),
            "confidence": item.get("confidence", None),
            "provenance": item.get("provenance", {}),
            "gold_based_proxy_decision": concept_score.get("review_proxy_decision", "reject"),
            "primary_failure_attribution": concept_score.get("primary_failure_attribution", ""),
        }))
    return lines


def build_markdown_report(artifact: dict[str, Any]) -> str:
    quality = artifact.get("quality_metrics") or {}
    provider = artifact.get("provider") or {}
    runtime = artifact.get("runtime") or {}
    lines = [
        "# Task 11E Bilingual Knowledge Quality Baseline",
        "",
        "## Executive Conclusion",
        "",
        f"- Status: `{artifact.get('status')}`",
        f"- Blocker: `{artifact.get('blocker') or 'none'}`",
        f"- Dominant failure stage: `{artifact.get('dominant_failure_stage') or 'not_available'}`",
        "- Current quality verdict: real semantic quality baseline is not established when the Formal Workflow only permits mock alignment verification.",
        "",
        "## Corpus And Gold",
        "",
        f"- Course: {artifact.get('corpus', {}).get('course')}",
        f"- Concept count: {artifact.get('gold', {}).get('concept_count')}",
        f"- Corpus SHA-256: `{artifact.get('corpus', {}).get('corpus_sha256')}`",
        f"- Gold SHA-256: `{artifact.get('corpus', {}).get('gold_sha256')}`",
        "- Frozen before run: true",
        "",
        "## Runtime",
        "",
        f"- Temporary DB: `{runtime.get('temporary_database_path', '')}`",
        f"- Provider: `{provider.get('provider_name', '')}`",
        f"- Model: `{provider.get('model_identity', '')}`",
        f"- Provider requests: {provider.get('requests', 0)}",
        f"- Provider preflight: `{provider.get('preflight_status', '')}`",
        "",
        "## Metrics",
        "",
        "| Metric | Result | Threshold | Pass |",
        "| ------ | -----: | --------: | :--: |",
    ]
    threshold_pass = quality.get("threshold_pass") or {}
    thresholds = quality.get("thresholds") or {}
    for key, threshold in thresholds.items():
        value = quality.get(key)
        lines.append(f"| `{key}` | { _format_metric(value) } | {threshold} | {threshold_pass.get(key)} |")
    lines.extend([
        "",
        "## Concept-Level Results",
        "",
        "| Concept | EN Retrieval | ZH Retrieval | Term Pair | Explanation | Proxy Decision | Attribution |",
        "| ------- | ------------ | ------------ | --------- | ----------- | -------------- | ----------- |",
    ])
    for concept_id, item in sorted((quality.get("concept_results") or {}).items()):
        lines.append(
            "| "
            + " | ".join([
                concept_id,
                "hit@3" if item.get("english_evidence_hit_at_3") else "miss",
                "hit@3" if item.get("chinese_evidence_hit_at_3") else "miss",
                "correct" if item.get("term_pair_correct") else "wrong",
                str(item.get("explanation_score")),
                item.get("review_proxy_decision", ""),
                item.get("primary_failure_attribution", ""),
            ])
            + " |"
        )
    lines.extend([
        "",
        "## Confusion Analysis",
        "",
        "- speed / velocity, momentum / impulse, work / energy, electric potential / potential difference, and angular momentum / torque are present in the synthetic corpus and gold confusions.",
        "- Confusion outcomes are recorded in `critical_confusion_count` and per-concept results.",
        "",
        "## Provenance",
        "",
        f"- Source reference completeness: {_format_metric(quality.get('source_reference_completeness'))}",
        f"- Chunk reference completeness: {_format_metric(quality.get('chunk_reference_completeness'))}",
        "- Page/bbox is not expected for simple text uploads; missing geometry is reported as location unavailable, not fabricated.",
        "",
        "## Safety",
        "",
        f"- Accident DB before hash: `{artifact.get('database_protection', {}).get('before_sha256', '')}`",
        f"- Accident DB after hash: `{artifact.get('database_protection', {}).get('after_sha256', '')}`",
        f"- Private data egress: {artifact.get('privacy_network', {}).get('private_data_egress')}",
        f"- External document API requests: {artifact.get('privacy_network', {}).get('external_document_api_requests')}",
        f"- Synthetic Provider egress: {artifact.get('privacy_network', {}).get('synthetic_text_egress')}",
        "",
        "## Remaining Limitations",
        "",
    ])
    for limitation in artifact.get("remaining_limitations") or []:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json_safe_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    return metrics.sanitize_artifact(summary)


def _format_metric(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.4f}"
    if value is None:
        return "n/a"
    return str(value)
