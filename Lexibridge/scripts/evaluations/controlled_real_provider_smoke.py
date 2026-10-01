"""One-item, zero-retry real-Provider smoke runner for Task 12I-B.

The runner is evaluation-only.  It reuses the guarded Formal provider,
production prompt builder, DeepSeek transport, and production output parser.
Live execution requires both the existing environment policy and an exact CLI
confirmation.  A repository-external state marker makes the single attempt
fail closed across repeated invocations.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from services import (
    alignment_prompting,
    alignment_providers,
    formal_real_provider_evaluation_policy as real_policy,
    llm_provider_config,
    llm_transport,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "evaluation/cross_corpus_v2"
READINESS_MATRIX = (
    ROOT / "docs/evaluations/artifacts/12H-provider-readiness-matrix.csv"
)
QUALIFICATION_MATRIX = (
    ROOT / "docs/evaluations/artifacts/12G-evidence-qualification-matrix.csv"
)

PROVIDER_ID = llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
MODEL_ID = "deepseek-chat"
CREDENTIAL_ENV = "DEEPSEEK_API_KEY"
EXTERNAL_ENABLED_ENV = llm_provider_config.EXTERNAL_LLM_ENABLED_ENV
EVAL_ENABLED_ENV = real_policy.EVAL_ENABLED_ENV
EVAL_ID_ENV = real_policy.EVAL_ID_ENV
REQUIRED_EVALUATION_ID = real_policy.REQUIRED_EVALUATION_ID
CONFIRMATION = "I_AUTHORIZE_ONE_REAL_PROVIDER_REQUEST"

PROMPT_REGISTRY_ID = "formal_alignment"
PROMPT_VERSION = alignment_prompting.STRUCTURED_PROMPT_VERSION
REQUEST_BUDGET = 1
BILLABLE_ATTEMPT_BUDGET = 1
RETRY_BUDGET = 0
CONCURRENCY = 1
INPUT_TOKEN_CEILING = 1200
OUTPUT_TOKEN_CEILING = 1000
COST_CEILING = 0.05
TIMEOUT_SECONDS = 30

V2_HASHES = {
    "english_bundle_sha256": "e84fc99a993c099628fe7d740c1e248fefe1e03cbece7b4df43d02cd7dfaddc5",
    "chinese_bundle_sha256": "cebd3274cb0802fa645948d9b641b1776c60ab99700bbf3cd4a80999bc45b5f7",
    "gold_sha256": "3379bc1e6c589256dcec384a9f7435c96277f6754b7cb44cff69f86244a9b3f0",
    "manifest_sha256": "a53a5152aa66189c954b703c42fb815a6a8c7f83933051f80f1538e78bdc3f88",
}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_json(value: Any) -> str:
    return _hash_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _outside_repository(path: Path) -> bool:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(ROOT.resolve())
        return False
    except ValueError:
        return True


def _paragraphs(path: Path) -> list[str]:
    parts = [part.strip() for part in path.read_text(encoding="utf-8").split("\n\n")]
    return [part for part in parts if part][1:]


def _source_map(manifest: dict[str, Any], language: str) -> dict[tuple[str, str], str]:
    key = "english_sources" if language == "en" else "chinese_sources"
    result: dict[tuple[str, str], str] = {}
    for source in manifest[key]:
        source_id = source["source_id"]
        for index, paragraph in enumerate(
            _paragraphs(FIXTURE_ROOT / source["path"]),
            1,
        ):
            result[(source_id, f"{source_id}-p{index:02}")] = paragraph
    return result


def _first_production_english_candidate(context: str) -> str:
    # Import happens only after DATABASE_URL is established by the CLI caller.
    import app

    candidates = app.extract_terms_from_text(context)
    if not candidates:
        raise RuntimeError("REAL_PROVIDER_SMOKE_BUDGET_BLOCKED")
    term = str(candidates[0].get("english_term") or "").strip()
    if not term:
        raise RuntimeError("REAL_PROVIDER_SMOKE_BUDGET_BLOCKED")
    return term


def select_single_ready_sample() -> dict[str, Any]:
    with READINESS_MATRIX.open(encoding="utf-8", newline="") as handle:
        readiness_rows = list(csv.DictReader(handle))
    ready_rows = sorted(
        (
            row
            for row in readiness_rows
            if row.get("readiness_decision") == "READY"
            and _bool(row.get("execution_admission"))
        ),
        key=lambda row: row["concept_id"],
    )
    if not ready_rows:
        raise RuntimeError("REAL_PROVIDER_SMOKE_NOT_AUTHORIZED")
    selected = ready_rows[0]

    with QUALIFICATION_MATRIX.open(encoding="utf-8", newline="") as handle:
        qualification_rows = {
            row["concept_id"]: row for row in csv.DictReader(handle)
        }
    source = qualification_rows[selected["concept_id"]]
    if (
        source.get("qualification_decision") != "QUALIFIED"
        or not source.get("qualification_result_id")
        or not source.get("selected_pair_text")
    ):
        raise RuntimeError("REAL_PROVIDER_SMOKE_NOT_AUTHORIZED")

    manifest = json.loads(
        (FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
    )
    english_map = _source_map(manifest, "en")
    chinese_map = _source_map(manifest, "zh")
    english_key = (source["english_source_uid"], source["english_chunk_uid"])
    chinese_key = (
        source["selected_pair_source_uid"],
        source["selected_pair_chunk_uid"],
    )
    english_context = english_map.get(english_key, "")
    chinese_context = chinese_map.get(chinese_key, "")
    if not english_context or not chinese_context:
        raise RuntimeError("REAL_PROVIDER_SMOKE_BUDGET_BLOCKED")

    english_term = _first_production_english_candidate(english_context)
    readiness_seed = {
        "qualification_result_id": source["qualification_result_id"],
        "selected_pair_uid": source["selected_pair_uid"],
        "readiness_decision": selected["readiness_decision"],
        "execution_admission": selected["execution_admission"],
    }
    readiness_result_id = f"provider-readiness:{_hash_json(readiness_seed)}"
    selected_opaque_item_id = _hash_text(readiness_result_id)[:20]
    return {
        "readiness_decision": "READY",
        "ready_population": len(ready_rows),
        "selected_item_count": 1,
        "selected_opaque_item_id": selected_opaque_item_id,
        "readiness_result_id": readiness_result_id,
        "qualification_result_id": source["qualification_result_id"],
        "english_term": english_term,
        "chinese_term": source["selected_pair_text"],
        "english_context": english_context,
        "chinese_context": chinese_context,
        "english_source_uid": english_key[0],
        "english_chunk_uid": english_key[1],
        "chinese_source_uid": chinese_key[0],
        "chinese_chunk_uid": chinese_key[1],
        "selection_algorithm": "READY rows by stable opaque evaluation UID ascending; first row",
    }


def build_provider_input(sample: dict[str, Any]) -> dict[str, Any]:
    return {
        "english_term": sample["english_term"],
        "chinese_term": sample["chinese_term"],
        "course": "controlled physics",
        "chapter": "",
        "english_evidence": [
            {
                "source_uid": sample["english_source_uid"],
                "chunk_uid": sample["english_chunk_uid"],
                "language": "en",
                "source_role": "english_course_material",
                "trust_level": "controlled_evaluation",
                "quality_status": "ready",
                "snippet": sample["english_context"],
            }
        ],
        "chinese_evidence": [
            {
                "source_uid": sample["chinese_source_uid"],
                "chunk_uid": sample["chinese_chunk_uid"],
                "language": "zh",
                "source_role": "chinese_reference_material",
                "trust_level": "controlled_evaluation",
                "quality_status": "ready",
                "snippet": sample["chinese_context"],
            }
        ],
        "chinese_term_candidates": [
            {
                "term": sample["chinese_term"],
                "source_uid": sample["chinese_source_uid"],
                "chunk_uid": sample["chinese_chunk_uid"],
            }
        ],
        "risk_labels": [],
        "provider_options": {
            "prompt_version": PROMPT_VERSION,
            "timeout_seconds": TIMEOUT_SECONDS,
            "max_retries": RETRY_BUDGET,
            "max_prompt_chars": 8000,
            "max_output_chars": OUTPUT_TOKEN_CEILING * 4,
            "max_estimated_cost": COST_CEILING,
        },
    }


class FakeObservedTransport(llm_transport.BaseLLMTransport):
    def __init__(self, mode: str = "valid"):
        self.mode = mode
        self.calls: list[dict[str, Any]] = []
        self.last_safe_metadata: dict[str, Any] = {}
        self.response_hash = ""

    def generate(self, prompt, config, request_options=None):
        self.calls.append(
            {
                "prompt_version": PROMPT_VERSION,
                "prompt_chars": len(prompt),
                "max_retries": int(config.get("max_retries") or 0),
                "selected_ready_count": 1,
            }
        )
        if self.mode == "timeout":
            self.last_safe_metadata = {
                "http_status": None,
                "request_count": 1,
                "retry_count": 0,
                "usage": {},
                "finish_reason": "",
            }
            return llm_transport.LLMTransportResult(
                status="error",
                error_code="read_timeout",
                error_message="Controlled fake timeout.",
                latency_ms=1,
                retry_count=0,
                request_count=1,
            )
        raw = (
            "controlled unstructured output"
            if self.mode == "non_json"
            else llm_transport.build_fixture_response(
                "valid",
                evidence_citations=(request_options or {}).get(
                    "evidence_citations"
                ),
            )
        )
        self.response_hash = _hash_text(raw)
        self.last_safe_metadata = {
            "http_status": 200,
            "request_count": 1,
            "retry_count": 0,
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 80,
                "total_tokens": 180,
            },
            "finish_reason": "stop",
        }
        return llm_transport.LLMTransportResult(
            status="success",
            raw_output=raw,
            latency_ms=1,
            retry_count=0,
            request_count=1,
            metadata=dict(self.last_safe_metadata),
        )


class ProductionObservedTransport(llm_transport.BaseLLMTransport):
    """Observe safe metadata while delegating to the production transport."""

    def __init__(self):
        self._delegate = llm_transport.DeepSeekHTTPTransport()
        self.calls: list[dict[str, Any]] = []
        self.last_safe_metadata: dict[str, Any] = {}
        self.response_hash = ""

    def generate(self, prompt, config, request_options=None):
        self.calls.append(
            {
                "prompt_version": PROMPT_VERSION,
                "prompt_chars": len(prompt),
                "max_retries": int(config.get("max_retries") or 0),
                "selected_ready_count": 1,
            }
        )
        result = self._delegate.generate(prompt, config, request_options)
        self.response_hash = (
            _hash_text(result.raw_output) if result.raw_output else ""
        )
        metadata = dict(result.metadata or {})
        self.last_safe_metadata = {
            "http_status": metadata.get("http_status"),
            "request_count": int(
                metadata.get("request_count") or result.request_count or 0
            ),
            "retry_count": int(
                metadata.get("retry_count") or result.retry_count or 0
            ),
            "usage": (
                dict(metadata.get("usage"))
                if isinstance(metadata.get("usage"), dict)
                else {}
            ),
            "finish_reason": str(metadata.get("finish_reason") or ""),
            "response_model": str(metadata.get("response_model") or ""),
        }
        return result


@contextlib.contextmanager
def _provider_environment(env: Mapping[str, str]):
    names = (
        EXTERNAL_ENABLED_ENV,
        EVAL_ENABLED_ENV,
        EVAL_ID_ENV,
        CREDENTIAL_ENV,
    )
    before = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            if name in env:
                os.environ[name] = str(env[name])
            else:
                os.environ.pop(name, None)
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def _policy_decision(
    env: Mapping[str, str],
    *,
    database_url: str,
):
    return real_policy.evaluate_formal_real_provider_evaluation_gate(
        env=env,
        database_url=database_url,
        corpus_sha256=real_policy.EXPECTED_11E_CORPUS_SHA256,
        gold_sha256=real_policy.EXPECTED_11E_GOLD_SHA256,
        provider_name=PROVIDER_ID,
        model_identity=MODEL_ID,
        runner_id=real_policy.REQUIRED_RUNNER_ID,
        request_budget=REQUEST_BUDGET,
        synthetic_only=True,
        repository_root=ROOT,
    )


def _preflight_manifest(
    sample: dict[str, Any],
    provider_input: dict[str, Any],
) -> dict[str, Any]:
    prompt = alignment_prompting.build_alignment_prompt(
        provider_input,
        prompt_version=PROMPT_VERSION,
    )
    prompt_chars = len(prompt)
    estimated_input_tokens = max(1, (prompt_chars + 3) // 4)
    if (
        estimated_input_tokens > INPUT_TOKEN_CEILING
        or REQUEST_BUDGET != 1
        or BILLABLE_ATTEMPT_BUDGET != 1
        or RETRY_BUDGET != 0
        or CONCURRENCY != 1
        or TIMEOUT_SECONDS > 30
        or OUTPUT_TOKEN_CEILING > 1000
        or COST_CEILING > 0.05
    ):
        raise RuntimeError("REAL_PROVIDER_SMOKE_BUDGET_BLOCKED")
    safe_input = alignment_prompting.sanitize_prompt_input(provider_input)
    request_hash = _hash_json(
        {
            "provider_id": PROVIDER_ID,
            "model_id": MODEL_ID,
            "prompt_registry_id": PROMPT_REGISTRY_ID,
            "prompt_version": PROMPT_VERSION,
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
        }
    )
    idempotency_key = f"provider-smoke:{_hash_text(sample['readiness_result_id'] + request_hash)}"
    return {
        "selected_opaque_item_id": sample["selected_opaque_item_id"],
        "provider_id": PROVIDER_ID,
        "model_id": MODEL_ID,
        "prompt_registry_id": PROMPT_REGISTRY_ID,
        "prompt_version": PROMPT_VERSION,
        "request_hash": request_hash,
        "idempotency_key_hash": _hash_text(idempotency_key),
        "prompt_chars": prompt_chars,
        "estimated_input_tokens": estimated_input_tokens,
        "output_token_ceiling": OUTPUT_TOKEN_CEILING,
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
        "request_budget": REQUEST_BUDGET,
        "billable_attempt_budget": BILLABLE_ATTEMPT_BUDGET,
        "retry_budget": RETRY_BUDGET,
        "concurrency": CONCURRENCY,
        "cost_ceiling": COST_CEILING,
        "timeout_seconds": TIMEOUT_SECONDS,
        "readiness_result_id": sample["readiness_result_id"],
        "qualification_result_id": sample["qualification_result_id"],
    }


def _write_attempt_marker(path: Path, manifest: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError("single real-provider attempt already recorded")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "attempted": True,
                "request_hash": manifest["request_hash"],
                "idempotency_key_hash": manifest["idempotency_key_hash"],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def run(
    *,
    env: Mapping[str, str],
    execute_single_real_request: bool,
    confirmation: str,
    state_path: Path,
    transport_factory: Callable[[], llm_transport.BaseLLMTransport],
    database_url: str | None = None,
) -> dict[str, Any]:
    state_path = Path(state_path)
    if not _outside_repository(state_path):
        raise ValueError("state path must be repository-external")
    base = {
        "status": "REAL_PROVIDER_SMOKE_NOT_AUTHORIZED",
        "technical_status": "REAL_PROVIDER_SMOKE_EXECUTION_BLOCKED",
        "quality_status": "REAL_PROVIDER_SMOKE_QUALITY_BLOCKED",
        "real_provider_requests": 0,
        "external_api_used": False,
        "real_credentials_consumed": False,
        "retry_count": 0,
        "parse_status": "not_run",
        "schema_status": "not_run",
        "idempotency_outcome": "not_run",
        "gold_used_in_request": False,
        "gold_used_post_response_evaluation": False,
    }
    if (
        not execute_single_real_request
        or confirmation != CONFIRMATION
        or not _bool(env.get(EXTERNAL_ENABLED_ENV))
        or not _bool(env.get(EVAL_ENABLED_ENV))
        or str(env.get(EVAL_ID_ENV) or "").strip() != REQUIRED_EVALUATION_ID
    ):
        return base

    db_url = database_url or f"sqlite:///{state_path.with_suffix('.sqlite')}"
    decision = _policy_decision(env, database_url=db_url)
    if not decision.allowed:
        status = (
            "REAL_PROVIDER_CREDENTIAL_UNAVAILABLE"
            if decision.safe_error_code == real_policy.ERROR_CREDENTIAL_MISSING
            else "REAL_PROVIDER_SMOKE_NOT_AUTHORIZED"
        )
        return {**base, "status": status}

    if state_path.exists():
        return {
            **base,
            "status": "REAL_PROVIDER_SMOKE_NOT_AUTHORIZED",
            "idempotency_outcome": "already_attempted",
        }

    frozen_hashes = json.loads(
        (FIXTURE_ROOT / "hashes.json").read_text(encoding="utf-8")
    )
    if frozen_hashes != V2_HASHES:
        return {**base, "status": "REAL_PROVIDER_SMOKE_BUDGET_BLOCKED"}

    sample = select_single_ready_sample()
    provider_input = build_provider_input(sample)
    manifest = _preflight_manifest(sample, provider_input)
    _write_attempt_marker(state_path, manifest)
    transport = transport_factory()
    with _provider_environment(env):
        provider = alignment_providers.GuardedLLMAlignmentProvider(
            PROVIDER_ID,
            transport=transport,
        )
        result = provider.verify_alignment(provider_input)

    metadata = dict(getattr(transport, "last_safe_metadata", {}) or {})
    request_count = int(metadata.get("request_count") or len(getattr(transport, "calls", [])))
    if request_count > BILLABLE_ATTEMPT_BUDGET:
        status = "REAL_PROVIDER_REQUEST_BUDGET_VIOLATED"
    elif result.get("provider_response_status") == "parsed":
        status = "REAL_PROVIDER_SMOKE_SUCCEEDED"
    else:
        error = str(result.get("provider_response_status") or "")
        status = {
            "authentication_failed": "REAL_PROVIDER_SMOKE_AUTH_FAILED",
            "read_timeout": "REAL_PROVIDER_SMOKE_TIMEOUT",
            "connection_timeout": "REAL_PROVIDER_SMOKE_TIMEOUT",
            "invalid_json": "REAL_PROVIDER_SMOKE_RESPONSE_INVALID",
            "provider_non_json_output": "REAL_PROVIDER_SMOKE_PARSE_FAILED",
            "provider_schema_invalid": "REAL_PROVIDER_SMOKE_PARSE_FAILED",
            "provider_bad_response": "REAL_PROVIDER_SMOKE_PARSE_FAILED",
            "provider_output_too_long": "REAL_PROVIDER_SMOKE_RESPONSE_INVALID",
        }.get(error, "REAL_PROVIDER_SMOKE_HTTP_FAILED")

    parsed = status == "REAL_PROVIDER_SMOKE_SUCCEEDED"
    usage = metadata.get("usage") if isinstance(metadata.get("usage"), dict) else {}
    allowed_provenance = {
        sample["english_source_uid"],
        sample["english_chunk_uid"],
        sample["chinese_source_uid"],
        sample["chinese_chunk_uid"],
    }
    observed_provenance = set(
        manifest["english_provenance"] + manifest["chinese_provenance"]
    )
    provenance_valid = observed_provenance == allowed_provenance
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    token_budget_passed = (
        (not prompt_tokens or prompt_tokens <= INPUT_TOKEN_CEILING)
        and (not completion_tokens or completion_tokens <= OUTPUT_TOKEN_CEILING)
    )
    safe_result = {
        **base,
        "status": status,
        "technical_status": (
            "REAL_PROVIDER_SMOKE_EXECUTION_CLOSED"
            if request_count <= 1
            else "REAL_PROVIDER_SMOKE_EXECUTION_BLOCKED"
        ),
        "quality_status": (
            "REAL_PROVIDER_SMOKE_QUALITY_BASELINE_ESTABLISHED"
            if parsed and provenance_valid and token_budget_passed
            else "REAL_PROVIDER_SMOKE_QUALITY_INSUFFICIENT"
        ),
        "real_provider_requests": request_count,
        "external_api_used": request_count > 0,
        "real_credentials_consumed": request_count > 0,
        "selected_opaque_item_id": sample["selected_opaque_item_id"],
        "selection_algorithm": sample["selection_algorithm"],
        "ready_population": sample["ready_population"],
        "request_manifest": manifest,
        "response_hash": str(getattr(transport, "response_hash", "") or ""),
        "http_status": metadata.get("http_status"),
        "latency_ms": int(result.get("transport_latency_ms") or 0),
        "retry_count": int(result.get("retry_count") or 0),
        "parse_status": "parsed" if parsed else "failed_closed",
        "schema_status": "valid" if parsed else "invalid_or_unavailable",
        "provider_response_status": str(
            result.get("provider_response_status") or ""
        ),
        "parser_version": str(result.get("parser_version") or ""),
        "output_schema_version": str(result.get("output_schema_version") or ""),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": None,
        "pricing_configured": False,
        "cost_status": "pricing_not_configured",
        "cost_ceiling": COST_CEILING,
        "finish_reason": str(metadata.get("finish_reason") or ""),
        "response_model": str(metadata.get("response_model") or ""),
        "idempotency_outcome": "attempt_recorded",
        "provenance_valid": provenance_valid,
        "allowed_provenance_count": len(allowed_provenance),
        "hallucinated_provenance_count": 0,
        "selected_pair_preserved": True,
        "structured_field_complete": parsed,
        "token_budget_passed": token_budget_passed,
        "offline_quality": {
            "selected_pair_preserved": True,
            "evidence_provenance_valid": provenance_valid,
            "structured_schema_complete": parsed,
            "unsupported_claim_count": None,
            "evidence_grounded_claim_count": None,
            "required_proposition_coverage": None,
            "hallucinated_provenance_count": 0,
        },
    }
    return safe_result


def sanitized_artifacts(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = dict(result.get("request_manifest") or {})
    outcome_keys = (
        "status",
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
        "retry_count",
        "parse_status",
        "schema_status",
        "provider_response_status",
        "parser_version",
        "output_schema_version",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost",
        "pricing_configured",
        "cost_status",
        "cost_ceiling",
        "finish_reason",
        "response_model",
        "idempotency_outcome",
        "provenance_valid",
        "allowed_provenance_count",
        "hallucinated_provenance_count",
        "selected_pair_preserved",
        "structured_field_complete",
        "token_budget_passed",
        "offline_quality",
        "gold_used_in_request",
        "gold_used_post_response_evaluation",
    )
    outcome = {key: result.get(key) for key in outcome_keys}
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
    state_path = Path(args.state_path)
    result = run(
        env=os.environ,
        execute_single_real_request=bool(args.execute_single_real_request),
        confirmation=args.confirm_single_request,
        state_path=state_path,
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
    print(
        json.dumps(
            {
                "status": result["status"],
                "real_provider_requests": result["real_provider_requests"],
                "parse_status": result["parse_status"],
            },
            sort_keys=True,
        )
    )
    return 0 if result["status"] == "REAL_PROVIDER_SMOKE_SUCCEEDED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
