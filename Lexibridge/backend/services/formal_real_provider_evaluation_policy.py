"""Evaluation-only gate for controlled real Formal alignment providers.

The default Formal Workflow provider remains the deterministic mock. This
module only validates whether a standalone synthetic evaluation runner may use
an already-registered external provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

from services import ai_registry, alignment_providers, llm_provider_config


EXPECTED_11E_CORPUS_SHA256 = "33715999c16a74610091b1e40896ee41921570a3740ebc2815565cf0ab7202dc"
EXPECTED_11E_GOLD_SHA256 = "199baed9a8cb6deb68ae3480c3a67679b2daf273d3733e909d4e861685d45302"
REQUIRED_EVALUATION_ID = "11E_BILINGUAL_QUALITY"
REQUIRED_RUNNER_ID = "11F_CONTROLLED_FORMAL_ALIGNMENT_RUNNER"

EVAL_ENABLED_ENV = "LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVAL_ENABLED"
EVAL_ID_ENV = "LEXIBRIDGE_FORMAL_REAL_PROVIDER_EVALUATION_ID"

ERROR_GATE_DISABLED = "FORMAL_REAL_PROVIDER_EVAL_GATE_DISABLED"
ERROR_EVAL_ID_INVALID = "FORMAL_REAL_PROVIDER_EVAL_ID_INVALID"
ERROR_RUNNER_INVALID = "FORMAL_REAL_PROVIDER_EVAL_RUNNER_INVALID"
ERROR_CORPUS_HASH_INVALID = "FORMAL_REAL_PROVIDER_EVAL_CORPUS_HASH_INVALID"
ERROR_GOLD_HASH_INVALID = "FORMAL_REAL_PROVIDER_EVAL_GOLD_HASH_INVALID"
ERROR_DATABASE_NOT_ISOLATED = "FORMAL_REAL_PROVIDER_EVAL_DATABASE_NOT_ISOLATED"
ERROR_PROVIDER_UNKNOWN = "FORMAL_REAL_PROVIDER_EVAL_PROVIDER_UNKNOWN"
ERROR_PROVIDER_NOT_EXTERNAL = "FORMAL_REAL_PROVIDER_EVAL_PROVIDER_NOT_EXTERNAL"
ERROR_PROVIDER_NOT_ENABLED = "FORMAL_REAL_PROVIDER_EVAL_PROVIDER_NOT_ENABLED"
ERROR_MODEL_NOT_ALLOWED = "FORMAL_REAL_PROVIDER_EVAL_MODEL_NOT_ALLOWED"
ERROR_BUDGET_INVALID = "FORMAL_REAL_PROVIDER_EVAL_BUDGET_INVALID"
ERROR_CREDENTIAL_MISSING = "FORMAL_REAL_PROVIDER_EVAL_CREDENTIAL_MISSING"

MAX_11F_PROVIDER_REQUESTS = 35
_TRUE_VALUES = {"1", "true", "yes", "on"}
_EVALUATION_CAPABILITY_SEAL = object()


@dataclass(frozen=True)
class FormalRealProviderEvaluationDecision:
    allowed: bool
    safe_error_code: str = ""
    safe_error_message: str = ""
    provider_name: str = ""
    model_identity: str = ""
    provider_type: str = ""
    credential_env_name: str = ""
    request_budget: int = 0
    evaluation_id: str = ""
    runner_id: str = ""
    corpus_sha256: str = ""
    gold_sha256: str = ""
    synthetic_only: bool = False
    database_isolated: bool = False
    gate_checks: dict[str, bool] = field(default_factory=dict)
    _capability_seal: object | None = field(default=None, repr=False, compare=False)

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "safe_error_code": self.safe_error_code,
            "safe_error_message": self.safe_error_message,
            "provider_name": self.provider_name,
            "model_identity": self.model_identity,
            "provider_type": self.provider_type,
            "credential_env_name": self.credential_env_name,
            "request_budget": self.request_budget,
            "evaluation_id": self.evaluation_id,
            "runner_id": self.runner_id,
            "corpus_sha256": self.corpus_sha256,
            "gold_sha256": self.gold_sha256,
            "synthetic_only": self.synthetic_only,
            "database_isolated": self.database_isolated,
            "gate_checks": dict(sorted(self.gate_checks.items())),
        }


def is_trusted_formal_real_provider_evaluation_context(
    context: Any,
    *,
    provider_name: str = "",
    model_identity: str = "",
) -> bool:
    """Recognize only a complete capability issued by this policy module."""

    return bool(
        isinstance(context, FormalRealProviderEvaluationDecision)
        and context._capability_seal is _EVALUATION_CAPABILITY_SEAL
        and context.allowed
        and context.evaluation_id == REQUIRED_EVALUATION_ID
        and context.runner_id == REQUIRED_RUNNER_ID
        and context.corpus_sha256 == EXPECTED_11E_CORPUS_SHA256
        and context.gold_sha256 == EXPECTED_11E_GOLD_SHA256
        and context.synthetic_only
        and context.database_isolated
        and 1 <= context.request_budget <= MAX_11F_PROVIDER_REQUESTS
        and (not provider_name or context.provider_name == _text(provider_name))
        and (not model_identity or context.model_identity == _text(model_identity))
    )


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in _TRUE_VALUES


def _text(value: Any) -> str:
    return str(value or "").strip()


def _deny(
    error_code: str,
    message: str,
    *,
    provider_name: str = "",
    model_identity: str = "",
    provider_type: str = "",
    credential_env_name: str = "",
    request_budget: int = 0,
    gate_checks: dict[str, bool] | None = None,
) -> FormalRealProviderEvaluationDecision:
    return FormalRealProviderEvaluationDecision(
        allowed=False,
        safe_error_code=error_code,
        safe_error_message=message,
        provider_name=provider_name,
        model_identity=model_identity,
        provider_type=provider_type,
        credential_env_name=credential_env_name,
        request_budget=request_budget,
        gate_checks=gate_checks or {},
    )


def _sqlite_path(database_url: str) -> Path | None:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        return None
    raw_path = unquote(parsed.path or "")
    if not raw_path or raw_path == ":memory:":
        return None
    return Path(raw_path).expanduser().resolve()


def _is_path_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _database_is_isolated(database_url: str, repository_root: Path) -> bool:
    db_path = _sqlite_path(database_url)
    if db_path is None:
        return False
    repo = repository_root.resolve()
    accident_db = repo / "backend" / "lexibridge.db"
    return db_path != accident_db and not _is_path_within(db_path, repo)


def evaluate_formal_real_provider_evaluation_gate(
    *,
    env: Mapping[str, str],
    database_url: str,
    corpus_sha256: str,
    gold_sha256: str,
    provider_name: str,
    model_identity: str,
    runner_id: str,
    request_budget: int,
    synthetic_only: bool,
    repository_root: str | Path | None = None,
) -> FormalRealProviderEvaluationDecision:
    """Return a safe allow/deny decision for Task 11F-style evaluation runs."""

    repo = Path(repository_root) if repository_root is not None else Path(__file__).resolve().parents[2]
    provider = _text(provider_name)
    model = _text(model_identity)
    budget = int(request_budget or 0)
    gate_checks: dict[str, bool] = {
        "explicit_gate_enabled": _truthy(env.get(EVAL_ENABLED_ENV, "")),
        "evaluation_id_matches": _text(env.get(EVAL_ID_ENV, "")) == REQUIRED_EVALUATION_ID,
        "runner_id_matches": _text(runner_id) == REQUIRED_RUNNER_ID,
        "corpus_hash_matches": _text(corpus_sha256) == EXPECTED_11E_CORPUS_SHA256,
        "gold_hash_matches": _text(gold_sha256) == EXPECTED_11E_GOLD_SHA256,
        "database_is_isolated": _database_is_isolated(database_url, repo),
        "request_budget_valid": 1 <= budget <= MAX_11F_PROVIDER_REQUESTS,
        "synthetic_only": synthetic_only is True,
    }

    if not gate_checks["explicit_gate_enabled"]:
        return _deny(ERROR_GATE_DISABLED, "Controlled Formal provider evaluation gate is disabled.", gate_checks=gate_checks)
    if not gate_checks["evaluation_id_matches"]:
        return _deny(ERROR_EVAL_ID_INVALID, "Controlled Formal provider evaluation id is invalid.", gate_checks=gate_checks)
    if not gate_checks["runner_id_matches"]:
        return _deny(ERROR_RUNNER_INVALID, "Controlled Formal provider runner identity is invalid.", gate_checks=gate_checks)
    if not gate_checks["corpus_hash_matches"]:
        return _deny(ERROR_CORPUS_HASH_INVALID, "Controlled Formal provider corpus hash is invalid.", gate_checks=gate_checks)
    if not gate_checks["gold_hash_matches"]:
        return _deny(ERROR_GOLD_HASH_INVALID, "Controlled Formal provider gold hash is invalid.", gate_checks=gate_checks)
    if not gate_checks["database_is_isolated"]:
        return _deny(ERROR_DATABASE_NOT_ISOLATED, "Controlled Formal provider database is not isolated.", gate_checks=gate_checks)
    if not gate_checks["request_budget_valid"]:
        return _deny(ERROR_BUDGET_INVALID, "Controlled Formal provider request budget is invalid.", request_budget=budget, gate_checks=gate_checks)
    if not gate_checks["synthetic_only"]:
        return _deny(
            ERROR_CORPUS_HASH_INVALID,
            "Controlled Formal provider evaluation is not synthetic-only.",
            request_budget=budget,
            gate_checks=gate_checks,
        )

    try:
        provider_adapter = alignment_providers.get_alignment_provider(provider)
        config = llm_provider_config.get_llm_provider_config(provider, env=env)
    except Exception:
        return _deny(ERROR_PROVIDER_UNKNOWN, "Controlled Formal provider is not registered.", provider_name=provider, model_identity=model, request_budget=budget, gate_checks=gate_checks)

    provider_type = str(config.get("provider_type") or getattr(provider_adapter, "provider_type", "") or "")
    credential_env_name = _text(config.get("api_key_env_name"))
    gate_checks.update({
        "provider_registered": True,
        "provider_supports_external_calls": bool(getattr(provider_adapter, "supports_external_calls", False)),
        "provider_is_external_llm": provider_type == "external_llm",
        "provider_config_enabled": bool(config.get("enabled")),
        "external_provider_enabled": bool(config.get("feature_enabled")),
        "provider_executable": bool(config.get("executable")),
        "model_matches_allowlist": model == _text(config.get("model_name")),
        "credential_env_configured": bool(credential_env_name),
        "credential_present": bool(config.get("credential_present")) if credential_env_name else False,
        "credential_not_placeholder": not ai_registry.is_placeholder_secret(env.get(credential_env_name, "")) if credential_env_name else False,
    })

    common = {
        "provider_name": provider,
        "model_identity": model,
        "provider_type": provider_type,
        "credential_env_name": credential_env_name,
        "request_budget": budget,
        "gate_checks": gate_checks,
    }
    if not gate_checks["provider_supports_external_calls"] or not gate_checks["provider_is_external_llm"]:
        return _deny(ERROR_PROVIDER_NOT_EXTERNAL, "Controlled Formal provider is not an external LLM provider.", **common)
    if not gate_checks["provider_config_enabled"] or not gate_checks["external_provider_enabled"]:
        return _deny(ERROR_PROVIDER_NOT_ENABLED, "Controlled Formal provider external execution is disabled.", **common)
    if not gate_checks["model_matches_allowlist"]:
        return _deny(ERROR_MODEL_NOT_ALLOWED, "Controlled Formal provider model is not allowlisted.", **common)
    if not gate_checks["credential_env_configured"] or not gate_checks["credential_present"] or not gate_checks["credential_not_placeholder"]:
        return _deny(ERROR_CREDENTIAL_MISSING, "Controlled Formal provider credential is missing or invalid.", **common)
    if not gate_checks["provider_executable"]:
        return _deny(ERROR_PROVIDER_NOT_ENABLED, "Controlled Formal provider is not executable.", **common)

    return FormalRealProviderEvaluationDecision(
        allowed=True,
        evaluation_id=_text(env.get(EVAL_ID_ENV, "")),
        runner_id=_text(runner_id),
        corpus_sha256=_text(corpus_sha256),
        gold_sha256=_text(gold_sha256),
        synthetic_only=True,
        database_isolated=True,
        _capability_seal=_EVALUATION_CAPABILITY_SEAL,
        **common,
    )
