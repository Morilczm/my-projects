"""Task 12I-A zero-request dry run over frozen Task 12H readiness rows."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from services import provider_execution


ROOT = Path(__file__).resolve().parents[2]
READINESS_MATRIX = (
    ROOT / "docs/evaluations/artifacts/12H-provider-readiness-matrix.csv"
)
PAIR_MATRIX = (
    ROOT / "docs/evaluations/artifacts/12G1-qualification-safety-matrix.csv"
)


def _opaque_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def run_evaluation():
    with READINESS_MATRIX.open(encoding="utf-8", newline="") as handle:
        readiness_rows = list(csv.DictReader(handle))
    with PAIR_MATRIX.open(encoding="utf-8", newline="") as handle:
        pair_rows = {
            row["concept_id"]: row for row in csv.DictReader(handle)
        }

    ledger = provider_execution.InMemoryExecutionLedger()
    transport = provider_execution.DeterministicFakeProviderTransport()
    rows = []
    for readiness in readiness_rows:
        ready = readiness["readiness_decision"] == "READY"
        request_constructed = False
        if ready:
            opaque = _opaque_key(readiness["concept_id"])
            pair = pair_rows[readiness["concept_id"]]
            request = provider_execution.ProviderExecutionRequest(
                readiness_decision="READY",
                readiness_policy=provider_execution.ACTIVE_READINESS_POLICY,
                readiness_result_id=f"provider-readiness:{opaque}",
                qualification_decision="QUALIFIED",
                qualification_policy=provider_execution.ACTIVE_QUALIFICATION_POLICY,
                qualification_result_id=f"qualification:{opaque}",
                execution_admission=True,
                privacy_gate_passed=True,
                provenance_gate_passed=True,
                budget_gate_passed=True,
                provider_id="fake-llm-v1",
                model_id="fake-llm-v1:v1",
                prompt_registry_id="term_alignment",
                prompt_version="v1",
                english_term="bounded production-selected English term",
                english_context="Bounded production-selected English evidence context.",
                english_evidence=(f"en-source:en-chunk:{opaque}:span",),
                chinese_term=pair["selected_pair_text"],
                chinese_context="有界的生产中文证据上下文。",
                chinese_evidence=(f"zh-source:zh-chunk:{opaque}:span",),
                request_token_ceiling=1200,
                cost_ceiling=0.05,
                timeout_seconds=30,
                retry_budget=1,
                idempotency_key=f"execution:{opaque}",
                audit_correlation_id=f"audit:{opaque}",
            )
            request_constructed = True
            result = provider_execution.execute_provider_request(
                request, transport=transport, ledger=ledger
            )
            status = result.status
            parse_status = result.parse_status
            request_hash = result.request_hash
            response_hash = result.response_hash
            reason_codes = list(result.reason_codes)
        else:
            status = "BLOCKED_BY_READINESS"
            parse_status = "not_run"
            request_hash = ""
            response_hash = ""
            reason_codes = [
                provider_execution.PROVIDER_EXECUTION_REVIEW_REQUIRED
                if readiness["readiness_decision"] == "REVIEW_REQUIRED"
                else provider_execution.PROVIDER_EXECUTION_NOT_READY
            ]
        rows.append(
            {
                "concept_id": readiness["concept_id"],
                "readiness_decision": readiness["readiness_decision"],
                "request_constructed": request_constructed,
                "execution_status": status,
                "parse_status": parse_status,
                "request_hash": request_hash,
                "response_hash": response_hash,
                "reason_codes": reason_codes,
            }
        )

    ready_denominator = sum(
        row["readiness_decision"] == "READY" for row in rows
    )
    return {
        "summary": {
            "all_25": len(rows),
            "ready_denominator": ready_denominator,
            "request_constructed": sum(row["request_constructed"] for row in rows),
            "fake_execution_success": sum(
                row["execution_status"] == provider_execution.SUCCEEDED
                for row in rows
            ),
            "parse_success": sum(row["parse_status"] == "parsed" for row in rows),
            "budget_denied": 0,
            "idempotency_conflict": 0,
            "review_not_ready_blocked": sum(
                row["execution_status"] == "BLOCKED_BY_READINESS" for row in rows
            ),
            "review_not_ready_executed": sum(
                row["request_constructed"]
                and row["readiness_decision"] != "READY"
                for row in rows
            ),
            "false_execution_count": sum(
                row["execution_status"] == provider_execution.SUCCEEDED
                and row["readiness_decision"] != "READY"
                for row in rows
            ),
            "fake_transport_calls": transport.call_count,
            "external_network_requests": transport.network_calls,
            "real_provider_requests": 0,
            "real_credentials_read": False,
        },
        "rows": rows,
        "policy": provider_execution.policy_manifest(),
    }
