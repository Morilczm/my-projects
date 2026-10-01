"""Sanitized Task 12H evaluation over the frozen Task 12G.1 matrix."""

from __future__ import annotations

import csv
from pathlib import Path

from services import provider_readiness


ROOT = Path(__file__).resolve().parents[2]
INPUT_MATRIX = (
    ROOT / "docs/evaluations/artifacts/12G1-qualification-safety-matrix.csv"
)


def _bool(value):
    return str(value or "").strip().lower() == "true"


def run_evaluation(*, use_fake_provider_config: bool = True):
    if not use_fake_provider_config:
        raise ValueError("Task 12H evaluation requires injected fake local configuration.")
    rows = []
    with INPUT_MATRIX.open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    for source in source_rows:
        qualification = source.get("qualification_decision") or ""
        executed = qualification in {"QUALIFIED", "REVIEW_REQUIRED", "REJECTED"}
        qualified = qualification == "QUALIFIED"
        formal_complete = bool(
            qualified
            and _bool(source.get("evidence_qualification_eligible"))
            and source.get("selected_pair_uid")
        )
        readiness_input = provider_readiness.ProviderReadinessInput(
            qualification_decision=qualification,
            qualification_policy=(
                provider_readiness.ACTIVE_QUALIFICATION_POLICY if executed else ""
            ),
            qualification_result_id=(
                f"qualification:{source['concept_id']}" if executed else ""
            ),
            qualification_score=float(source.get("qualification_score") or 0.0),
            qualification_reason_codes=tuple(
                filter(None, (source.get("qualification_reason_codes") or "").split("|"))
            ),
            qualification_risk_labels=(),
            english_term="bounded-english-term" if executed else "",
            chinese_term=source.get("selected_pair_text") or "",
            english_evidence_refs=(
                (f"en:{source['concept_id']}:chunk:span",) if formal_complete else ()
            ),
            chinese_evidence_refs=(
                (f"zh:{source['concept_id']}:chunk:span",) if formal_complete else ()
            ),
            pair_rank=1 if source.get("selected_pair_uid") else 0,
            pair_score=float(source.get("pair_consistency_score") or 0.0),
            pair_model_metadata_complete=formal_complete,
            provider_id="fake-formal-provider",
            provider_policy_id="formal-provider-policy@1.0.0",
            provider_allowed=True,
            provider_config_complete=True,
            credential_reference_configured=True,
            prompt_registry_id="term_alignment",
            prompt_version="v1",
            prompt_approved=True,
            privacy_classification="SYNTHETIC",
            privacy_gate_passed=True,
            provenance_gate_passed=formal_complete,
            source_governance_passed=formal_complete,
            request_token_budget=1200,
            cost_ceiling=0.05,
            retry_budget=0,
            timeout_seconds=30,
            idempotency_key=f"readiness:{source['concept_id']}",
            audit_context="cross-corpus-v2-evaluation",
            upstream_fatal_reasons=(
                ()
                if qualified
                else (source.get("primary_attribution") or "QUALIFICATION_NOT_APPROVED",)
            ),
        )
        result = provider_readiness.evaluate_provider_readiness(readiness_input)
        rows.append(
            {
                "concept_id": source["concept_id"],
                "qualification_decision": qualification or "MISSING",
                "formal_input_complete": formal_complete,
                "provider_readiness_eligible": formal_complete,
                "readiness_decision": result.decision,
                "readiness_id": result.readiness_id,
                "reason_codes": list(result.reason_codes),
                "privacy_result": result.privacy_result,
                "provenance_result": result.provenance_result,
                "budget_result": result.budget_result,
                "provider_configuration_result": result.provider_configuration_result,
                "execution_admission": result.execution_admission,
            }
        )
    qualification_qualified = sum(
        row["qualification_decision"] == "QUALIFIED" for row in rows
    )
    qualification_review = sum(
        row["qualification_decision"] == "REVIEW_REQUIRED" for row in rows
    )
    return {
        "summary": {
            "all_25": len(rows),
            "qualification_executed": sum(
                row["qualification_decision"] != "MISSING" for row in rows
            ),
            "qualification_qualified": qualification_qualified,
            "qualification_review": qualification_review,
            "qualification_rejected": sum(
                row["qualification_decision"] == "REJECTED" for row in rows
            ),
            "provider_readiness_eligible": sum(
                row["provider_readiness_eligible"] for row in rows
            ),
            "ready": sum(row["readiness_decision"] == "READY" for row in rows),
            "review_required": sum(
                row["readiness_decision"] == "REVIEW_REQUIRED" for row in rows
            ),
            "not_ready": sum(
                row["readiness_decision"] == "NOT_READY" for row in rows
            ),
            "false_ready": sum(
                row["execution_admission"]
                and row["qualification_decision"] != "QUALIFIED"
                for row in rows
            ),
            "real_provider_requests": 0,
            "external_api_requests": 0,
            "real_credentials_read": False,
        },
        "rows": rows,
        "policy": provider_readiness.policy_manifest(),
    }
