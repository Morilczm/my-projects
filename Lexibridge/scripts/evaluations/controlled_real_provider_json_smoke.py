"""Task 12I-C-B one-request verification of the frozen JSON output contract."""

from __future__ import annotations

import argparse
import csv
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from services import (
    alignment_output_parser,
    alignment_prompting,
    alignment_providers,
    llm_provider_config,
    llm_transport,
)
from scripts.evaluations import controlled_real_provider_smoke as base_runner


ROOT = base_runner.ROOT
PROVIDER_ID = base_runner.PROVIDER_ID
MODEL_ID = base_runner.MODEL_ID
CREDENTIAL_ENV = base_runner.CREDENTIAL_ENV
EXTERNAL_ENABLED_ENV = base_runner.EXTERNAL_ENABLED_ENV
EVAL_ENABLED_ENV = base_runner.EVAL_ENABLED_ENV
EVAL_ID_ENV = base_runner.EVAL_ID_ENV
REQUIRED_EVALUATION_ID = base_runner.REQUIRED_EVALUATION_ID
CONFIRMATION = "I_AUTHORIZE_ONE_REAL_PROVIDER_JSON_REQUEST"

PROMPT_REGISTRY_ID = "formal_alignment"
PROMPT_VERSION = alignment_prompting.STRUCTURED_PROMPT_VERSION
PARSER_VERSION = alignment_output_parser.STRUCTURED_PARSER_VERSION
OUTPUT_SCHEMA_VERSION = alignment_output_parser.STRUCTURED_OUTPUT_SCHEMA_VERSION
REQUEST_BUDGET = 1
BILLABLE_ATTEMPT_BUDGET = 1
RETRY_BUDGET = 0
CONCURRENCY = 1
INPUT_TOKEN_CEILING = base_runner.INPUT_TOKEN_CEILING
OUTPUT_TOKEN_CEILING = base_runner.OUTPUT_TOKEN_CEILING
COST_CEILING = base_runner.COST_CEILING
TIMEOUT_SECONDS = base_runner.TIMEOUT_SECONDS
V2_HASHES = dict(base_runner.V2_HASHES)

EXPECTED_SELECTED_OPAQUE_ITEM_ID = "6f6945108e85f8ec6a1f"
PREVIOUS_EVALUATION_ID = "12I-B-controlled-real-provider-smoke"
PREVIOUS_IDEMPOTENCY_KEY_HASH = (
    "f30048a054dbb1ef8d7f846a2beb28330ddc0dc571526e5d3b0e5b5ee3a218bd"
)


def _new_id() -> str:
    return uuid.uuid4().hex


def _base_result() -> dict[str, Any]:
    return {
        "execution_status": "REAL_PROVIDER_JSON_SMOKE_NOT_AUTHORIZED",
        "technical_status": "REAL_PROVIDER_JSON_SMOKE_EXECUTION_BLOCKED",
        "quality_status": "REAL_PROVIDER_JSON_SMOKE_QUALITY_BLOCKED",
        "real_provider_requests": 0,
        "external_api_used": False,
        "real_credentials_consumed": False,
        "retry_count": 0,
        "parse_status": "not_run",
        "schema_status": "not_run",
        "gold_used_in_request": False,
        "gold_used_post_response_evaluation": False,
    }


def _selected_concept_id(sample: dict[str, Any]) -> str:
    with base_runner.QUALIFICATION_MATRIX.open(
        encoding="utf-8", newline=""
    ) as handle:
        for row in csv.DictReader(handle):
            if (
                row.get("qualification_result_id")
                == sample["qualification_result_id"]
            ):
                return str(row.get("concept_id") or "")
    return ""


def _preflight_manifest(
    sample: dict[str, Any],
    provider_input: dict[str, Any],
    *,
    evaluation_run_id: str,
    audit_correlation_id: str,
    idempotency_salt: str,
) -> dict[str, Any]:
    prompt = alignment_prompting.build_alignment_prompt(
        provider_input,
        prompt_version=PROMPT_VERSION,
    )
    prompt_chars = len(prompt)
    estimated_input_tokens = max(1, (prompt_chars + 3) // 4)
    config = llm_provider_config.get_llm_provider_config(
        PROVIDER_ID,
        env={
            EXTERNAL_ENABLED_ENV: "1",
            CREDENTIAL_ENV: "evaluation-presence-only",
        },
    )
    response_format = {"type": "json_object"}
    max_tokens = int(config.get("max_output_tokens") or 0)
    allowed_provenance = {
        sample["english_source_uid"],
        sample["english_chunk_uid"],
        sample["chinese_source_uid"],
        sample["chinese_chunk_uid"],
    }
    observed_provenance = {
        provider_input["english_evidence"][0]["source_uid"],
        provider_input["english_evidence"][0]["chunk_uid"],
        provider_input["chinese_evidence"][0]["source_uid"],
        provider_input["chinese_evidence"][0]["chunk_uid"],
    }
    if (
        PROVIDER_ID != llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
        or MODEL_ID != str(config.get("model_name") or "")
        or PROMPT_VERSION != alignment_prompting.STRUCTURED_PROMPT_VERSION
        or not config.get("supports_json_object_response_format")
        or response_format != {"type": "json_object"}
        or not (
            llm_provider_config.MIN_ALIGNMENT_SCHEMA_OUTPUT_TOKENS
            <= max_tokens
            <= OUTPUT_TOKEN_CEILING
        )
        or estimated_input_tokens > INPUT_TOKEN_CEILING
        or REQUEST_BUDGET != 1
        or BILLABLE_ATTEMPT_BUDGET != 1
        or RETRY_BUDGET != 0
        or CONCURRENCY != 1
        or COST_CEILING != 0.05
        or TIMEOUT_SECONDS != llm_provider_config.DEFAULT_TIMEOUT_SECONDS
        or observed_provenance != allowed_provenance
    ):
        raise RuntimeError("REAL_PROVIDER_JSON_SMOKE_PREFLIGHT_BLOCKED")

    safe_input = alignment_prompting.sanitize_prompt_input(provider_input)
    request_hash = base_runner._hash_json({
        "provider_id": PROVIDER_ID,
        "model_id": MODEL_ID,
        "prompt_registry_id": PROMPT_REGISTRY_ID,
        "prompt_version": PROMPT_VERSION,
        "response_format": response_format,
        "max_tokens": max_tokens,
        "safe_input": safe_input,
        "readiness_result_id": sample["readiness_result_id"],
        "qualification_result_id": sample["qualification_result_id"],
        "budget": {
            "request_budget": REQUEST_BUDGET,
            "billable_attempt_budget": BILLABLE_ATTEMPT_BUDGET,
            "retry_budget": RETRY_BUDGET,
            "concurrency": CONCURRENCY,
            "input_token_ceiling": INPUT_TOKEN_CEILING,
            "output_token_ceiling": OUTPUT_TOKEN_CEILING,
            "cost_ceiling": COST_CEILING,
            "timeout_seconds": TIMEOUT_SECONDS,
        },
    })
    idempotency_key = (
        f"provider-json-smoke:{evaluation_run_id}:"
        f"{base_runner._hash_text(request_hash + idempotency_salt)}"
    )
    idempotency_key_hash = base_runner._hash_text(idempotency_key)
    if idempotency_key_hash == PREVIOUS_IDEMPOTENCY_KEY_HASH:
        raise RuntimeError("REAL_PROVIDER_JSON_SMOKE_PREFLIGHT_BLOCKED")

    return {
        "artifact_schema_version": "12ICB-real-provider-json-smoke-manifest-v1",
        "previous_evaluation_id": PREVIOUS_EVALUATION_ID,
        "evaluation_run_id": evaluation_run_id,
        "audit_correlation_id": audit_correlation_id,
        "selected_opaque_item_id": sample["selected_opaque_item_id"],
        "selection_algorithm": sample["selection_algorithm"],
        "selection_matches_12ib": True,
        "ready_population": sample["ready_population"],
        "selected_item_count": 1,
        "provider_id": PROVIDER_ID,
        "requested_model_id": MODEL_ID,
        "prompt_registry_id": PROMPT_REGISTRY_ID,
        "prompt_version": PROMPT_VERSION,
        "response_format": response_format,
        "max_tokens": max_tokens,
        "request_hash": request_hash,
        "idempotency_key_hash": idempotency_key_hash,
        "previous_idempotency_key_hash_reused": False,
        "prompt_chars": prompt_chars,
        "estimated_input_tokens": estimated_input_tokens,
        "english_context_chars": len(sample["english_context"]),
        "chinese_context_chars": len(sample["chinese_context"]),
        "english_provenance": [
            sample["english_source_uid"],
            sample["english_chunk_uid"],
        ],
        "chinese_provenance": [
            sample["chinese_source_uid"],
            sample["chinese_chunk_uid"],
        ],
        "qualification_result_id": sample["qualification_result_id"],
        "readiness_result_id": sample["readiness_result_id"],
        "request_budget": REQUEST_BUDGET,
        "billable_attempt_budget": BILLABLE_ATTEMPT_BUDGET,
        "retry_budget": RETRY_BUDGET,
        "concurrency": CONCURRENCY,
        "cost_ceiling": COST_CEILING,
        "timeout_seconds": TIMEOUT_SECONDS,
        "gold_included_in_request": False,
        "stores_request_content": False,
        "stores_prompt_content": False,
        "credential_stored": False,
    }


class FakeObservedTransport(base_runner.FakeObservedTransport):
    def generate(self, prompt, config, request_options=None):
        result = super().generate(prompt, config, request_options)
        metadata = dict(result.metadata or {})
        metadata.update({
            "requested_model": MODEL_ID,
            "response_model": MODEL_ID,
            "resolved_model": MODEL_ID,
            "model_policy_version": (
                llm_provider_config.DEEPSEEK_MODEL_POLICY_VERSION
            ),
            "pricing_model_identity": MODEL_ID,
            "response_format": "json_object",
        })
        result.metadata = metadata
        self.last_safe_metadata = dict(metadata)
        return result


class ProductionObservedTransport(llm_transport.BaseLLMTransport):
    """Capture only bounded metadata while delegating to production transport."""

    def __init__(self):
        self._delegate = llm_transport.DeepSeekHTTPTransport()
        self.calls: list[dict[str, Any]] = []
        self.last_safe_metadata: dict[str, Any] = {}
        self.response_hash = ""

    def generate(self, prompt, config, request_options=None):
        self.calls.append({
            "prompt_version": PROMPT_VERSION,
            "prompt_chars": len(prompt),
            "max_retries": int(config.get("max_retries") or 0),
            "selected_ready_count": 1,
        })
        result = self._delegate.generate(prompt, config, request_options)
        self.response_hash = (
            base_runner._hash_text(result.raw_output)
            if result.raw_output
            else ""
        )
        metadata = dict(result.metadata or {})
        self.last_safe_metadata = {
            key: metadata.get(key)
            for key in (
                "http_status",
                "request_count",
                "retry_count",
                "usage",
                "finish_reason",
                "requested_model",
                "response_model",
                "resolved_model",
                "model_policy_version",
                "pricing_model_identity",
                "response_format",
            )
        }
        return result


def _execution_status(result: dict[str, Any], request_count: int) -> str:
    if request_count > 1:
        return "REAL_PROVIDER_REQUEST_BUDGET_VIOLATED"
    response_status = str(result.get("provider_response_status") or "")
    if response_status == "parsed":
        return "REAL_PROVIDER_JSON_SMOKE_SUCCEEDED"
    return {
        "authentication_failed": "REAL_PROVIDER_JSON_SMOKE_AUTH_FAILED",
        "read_timeout": "REAL_PROVIDER_JSON_SMOKE_TIMEOUT",
        "connection_timeout": "REAL_PROVIDER_JSON_SMOKE_TIMEOUT",
        "response_model_not_allowed": (
            "REAL_PROVIDER_JSON_SMOKE_MODEL_POLICY_FAILED"
        ),
        "invalid_json": "REAL_PROVIDER_JSON_SMOKE_RESPONSE_INVALID",
        "malformed_provider_response": (
            "REAL_PROVIDER_JSON_SMOKE_RESPONSE_INVALID"
        ),
        "missing_response_content": (
            "REAL_PROVIDER_JSON_SMOKE_RESPONSE_INVALID"
        ),
        "response_truncated": "REAL_PROVIDER_JSON_SMOKE_RESPONSE_INVALID",
        "provider_non_json_output": "REAL_PROVIDER_JSON_SMOKE_PARSE_FAILED",
        "provider_schema_invalid": "REAL_PROVIDER_JSON_SMOKE_PARSE_FAILED",
        "provider_bad_response": "REAL_PROVIDER_JSON_SMOKE_PARSE_FAILED",
        "provider_cost_limit_exceeded": (
            "REAL_PROVIDER_JSON_SMOKE_BUDGET_BLOCKED"
        ),
        "provider_pricing_unavailable": (
            "REAL_PROVIDER_JSON_SMOKE_BUDGET_BLOCKED"
        ),
    }.get(response_status, "REAL_PROVIDER_JSON_SMOKE_HTTP_FAILED")


def _actual_cost(
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, Any]:
    config = llm_provider_config.DEFAULT_PROVIDER_CONFIGS[PROVIDER_ID]
    input_rate = config.get("cost_per_1k_input_cache_miss_tokens")
    output_rate = config.get("cost_per_1k_output_tokens")
    if input_rate is None or output_rate is None:
        return {
            "pricing_available": False,
            "estimated_cost": None,
            "cost_status": "pricing_unavailable",
        }
    cost = round(
        prompt_tokens / 1000.0 * float(input_rate)
        + completion_tokens / 1000.0 * float(output_rate),
        8,
    )
    return {
        "pricing_available": True,
        "pricing_policy_version": str(config["pricing_policy_version"]),
        "pricing_model_identity": str(config["pricing_model_identity"]),
        "pricing_effective_date": str(config["pricing_effective_date"]),
        "currency": str(config["pricing_currency"]),
        "input_price_basis": "cache_miss_worst_case",
        "estimated_cost": cost,
        "cost_ceiling": COST_CEILING,
        "cost_ceiling_passed": cost <= COST_CEILING,
        "cost_status": "estimated_from_reported_usage",
    }


def _offline_quality(
    sample: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    concept_id = _selected_concept_id(sample)
    gold = json.loads(
        (base_runner.FIXTURE_ROOT / "gold.json").read_text(encoding="utf-8")
    )
    gold_row = next(
        (row for row in gold if row.get("concept_id") == concept_id),
        {},
    )
    citations = result.get("evidence_citations")
    citation_count = sum(
        len(citations.get(language, []))
        for language in ("english", "chinese")
    ) if isinstance(citations, dict) else 0
    return {
        "selected_pair_preserved": True,
        "canonical_term_correct": bool(
            gold_row
            and sample["chinese_term"] == gold_row.get("chinese_term")
        ),
        "schema_field_complete": True,
        "evidence_citation_valid": citation_count >= 2,
        "hallucinated_provenance_count": 0,
        "unsupported_claim_count": None,
        "evidence_grounded_claim_count": None,
        "required_proposition_coverage": None,
        "draft_formable_but_not_published": True,
    }


def run(
    *,
    env: Mapping[str, str],
    execute_single_real_request: bool,
    confirmation: str,
    state_path: Path,
    transport_factory: Callable[[], llm_transport.BaseLLMTransport],
    database_url: str | None = None,
    id_factory: Callable[[], str] | None = None,
) -> dict[str, Any]:
    state_path = Path(state_path)
    if not base_runner._outside_repository(state_path):
        raise ValueError("state path must be repository-external")
    base = _base_result()
    if (
        not execute_single_real_request
        or confirmation != CONFIRMATION
        or not base_runner._bool(env.get(EXTERNAL_ENABLED_ENV))
        or not base_runner._bool(env.get(EVAL_ENABLED_ENV))
        or str(env.get(EVAL_ID_ENV) or "").strip() != REQUIRED_EVALUATION_ID
    ):
        return base

    db_url = database_url or f"sqlite:///{state_path.with_suffix('.sqlite')}"
    decision = base_runner._policy_decision(env, database_url=db_url)
    if not decision.allowed:
        return base
    if state_path.exists():
        return {
            **base,
            "idempotency_outcome": "already_attempted",
        }
    frozen_hashes = json.loads(
        (base_runner.FIXTURE_ROOT / "hashes.json").read_text(
            encoding="utf-8"
        )
    )
    if frozen_hashes != V2_HASHES:
        return {
            **base,
            "execution_status": "REAL_PROVIDER_JSON_SMOKE_PREFLIGHT_BLOCKED",
        }

    sample = base_runner.select_single_ready_sample()
    if sample["selected_opaque_item_id"] != EXPECTED_SELECTED_OPAQUE_ITEM_ID:
        return {
            **base,
            "execution_status": "REAL_PROVIDER_JSON_SMOKE_SELECTION_DRIFT",
            "selected_opaque_item_id": sample["selected_opaque_item_id"],
        }

    factory = id_factory or _new_id
    evaluation_run_id = f"12ICB-{factory()}"
    audit_correlation_id = f"12ICB-audit-{factory()}"
    idempotency_salt = factory()
    provider_input = base_runner.build_provider_input(sample)
    try:
        manifest = _preflight_manifest(
            sample,
            provider_input,
            evaluation_run_id=evaluation_run_id,
            audit_correlation_id=audit_correlation_id,
            idempotency_salt=idempotency_salt,
        )
    except RuntimeError:
        return {
            **base,
            "execution_status": "REAL_PROVIDER_JSON_SMOKE_PREFLIGHT_BLOCKED",
        }

    base_runner._write_attempt_marker(state_path, manifest)
    transport = transport_factory()
    with base_runner._provider_environment(env):
        provider = alignment_providers.GuardedLLMAlignmentProvider(
            PROVIDER_ID,
            transport=transport,
        )
        provider_result = provider.verify_alignment(provider_input)

    metadata = dict(
        getattr(transport, "last_safe_metadata", {}) or {}
    )
    request_count = int(
        metadata.get("request_count")
        or len(getattr(transport, "calls", []))
    )
    execution_status = _execution_status(provider_result, request_count)
    parsed = execution_status == "REAL_PROVIDER_JSON_SMOKE_SUCCEEDED"
    usage = metadata.get("usage")
    usage = dict(usage) if isinstance(usage, dict) else {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(
        usage.get("total_tokens")
        or prompt_tokens + completion_tokens
    )
    output_shape_source = provider_result.get("raw_output_summary")
    output_shape_source = (
        dict(output_shape_source)
        if isinstance(output_shape_source, dict)
        else {}
    )
    output_shape = {
        key: output_shape_source.get(key)
        for key in (
            "content_present",
            "content_length_bucket",
            "first_non_whitespace_character_class",
            "looks_like_json_object",
            "outer_code_fence_present",
            "finish_reason",
            "response_model",
            "response_hash",
            "schema_validation_stage",
            "stable_parser_reason",
        )
    }
    requested_model = str(
        metadata.get("requested_model") or MODEL_ID
    )
    resolved_model = str(
        metadata.get("resolved_model")
        or metadata.get("response_model")
        or (MODEL_ID if isinstance(transport, FakeObservedTransport) else "")
    )
    model_compatibility = llm_provider_config.validate_response_model_identity(
        requested_model,
        resolved_model,
    )
    cost = _actual_cost(prompt_tokens, completion_tokens)
    token_budget_passed = (
        (not prompt_tokens or prompt_tokens <= INPUT_TOKEN_CEILING)
        and (
            not completion_tokens
            or completion_tokens <= OUTPUT_TOKEN_CEILING
        )
    )
    offline_quality = (
        _offline_quality(sample, provider_result)
        if parsed
        else {
            "selected_pair_preserved": True,
            "canonical_term_correct": None,
            "schema_field_complete": False,
            "evidence_citation_valid": False,
            "hallucinated_provenance_count": None,
            "unsupported_claim_count": None,
            "evidence_grounded_claim_count": None,
            "required_proposition_coverage": None,
            "draft_formable_but_not_published": False,
        }
    )
    provenance_valid = bool(
        offline_quality["evidence_citation_valid"]
        if parsed
        else True
    )
    quality_established = bool(
        parsed
        and provenance_valid
        and token_budget_passed
        and cost.get("cost_ceiling_passed")
        and model_compatibility["compatible"]
    )
    return {
        **base,
        "execution_status": execution_status,
        "technical_status": (
            "REAL_PROVIDER_JSON_SMOKE_EXECUTION_CLOSED"
            if request_count <= 1
            else "REAL_PROVIDER_JSON_SMOKE_EXECUTION_BLOCKED"
        ),
        "quality_status": (
            "REAL_PROVIDER_JSON_SMOKE_QUALITY_BASELINE_ESTABLISHED"
            if quality_established
            else "REAL_PROVIDER_JSON_SMOKE_QUALITY_INSUFFICIENT"
        ),
        "real_provider_requests": request_count,
        "external_api_used": request_count > 0,
        "real_credentials_consumed": request_count > 0,
        "selected_opaque_item_id": sample["selected_opaque_item_id"],
        "selection_algorithm": sample["selection_algorithm"],
        "ready_population": sample["ready_population"],
        "request_manifest": manifest,
        "response_hash": str(
            getattr(transport, "response_hash", "") or ""
        ),
        "http_status": metadata.get("http_status"),
        "latency_ms": (
            int(provider_result["transport_latency_ms"])
            if provider_result.get("transport_latency_ms") is not None
            else None
        ),
        "latency_status": (
            "reported_by_transport"
            if provider_result.get("transport_latency_ms") is not None
            else "provider_transport_latency_unavailable"
        ),
        "retry_count": int(provider_result.get("retry_count") or 0),
        "parse_status": "parsed" if parsed else "failed_closed",
        "schema_status": "valid" if parsed else "invalid_or_unavailable",
        "provider_response_status": str(
            provider_result.get("provider_response_status") or ""
        ),
        "parser_version": str(
            provider_result.get("parser_version") or PARSER_VERSION
        ),
        "output_schema_version": str(
            provider_result.get("output_schema_version")
            or OUTPUT_SCHEMA_VERSION
        ),
        "requested_model": requested_model,
        "resolved_model": resolved_model,
        "model_compatibility": model_compatibility,
        "finish_reason": str(metadata.get("finish_reason") or ""),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "pricing": cost,
        "output_shape": output_shape,
        "idempotency_outcome": "attempt_recorded",
        "provenance_valid": provenance_valid,
        "selected_pair_preserved": True,
        "token_budget_passed": token_budget_passed,
        "offline_quality": offline_quality,
        "gold_used_in_request": False,
        "gold_used_post_response_evaluation": parsed,
        "stores_request_content": False,
        "stores_response_content": False,
        "credential_disclosed": False,
    }


def sanitized_artifacts(
    result: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = dict(result.get("request_manifest") or {})
    outcome_keys = (
        "execution_status",
        "technical_status",
        "quality_status",
        "real_provider_requests",
        "external_api_used",
        "real_credentials_consumed",
        "selected_opaque_item_id",
        "selection_algorithm",
        "ready_population",
        "response_hash",
        "http_status",
        "latency_ms",
        "latency_status",
        "retry_count",
        "parse_status",
        "schema_status",
        "provider_response_status",
        "parser_version",
        "output_schema_version",
        "requested_model",
        "resolved_model",
        "model_compatibility",
        "finish_reason",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "pricing",
        "output_shape",
        "idempotency_outcome",
        "provenance_valid",
        "selected_pair_preserved",
        "token_budget_passed",
        "offline_quality",
        "gold_used_in_request",
        "gold_used_post_response_evaluation",
        "stores_request_content",
        "stores_response_content",
        "credential_disclosed",
    )
    outcome = {
        "artifact_schema_version": (
            "12ICB-real-provider-json-smoke-result-v1"
        ),
        **{key: result.get(key) for key in outcome_keys},
    }
    return manifest, outcome


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-single-real-request", action="store_true")
    parser.add_argument("--confirm-single-request", default="")
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--manifest-output", required=True)
    parser.add_argument("--result-output", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run(
        env=os.environ,
        execute_single_real_request=bool(
            args.execute_single_real_request
        ),
        confirmation=args.confirm_single_request,
        state_path=Path(args.state_path),
        transport_factory=ProductionObservedTransport,
        database_url=os.environ.get("DATABASE_URL", ""),
    )
    manifest, outcome = sanitized_artifacts(result)
    Path(args.manifest_output).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    Path(args.result_output).write_text(
        json.dumps(outcome, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "execution_status": result["execution_status"],
        "real_provider_requests": result["real_provider_requests"],
        "parse_status": result["parse_status"],
    }, sort_keys=True))
    return (
        0
        if result["execution_status"]
        == "REAL_PROVIDER_JSON_SMOKE_SUCCEEDED"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
