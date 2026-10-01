"""Transport abstractions for guarded alignment LLM providers."""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from services import llm_provider_config


@dataclass
class LLMTransportResult:
    status: str
    raw_output: str = ""
    error_code: str = ""
    error_message: str = ""
    latency_ms: int = 0
    retry_count: int = 0
    request_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, repr=False)
class LLMHTTPRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: str
    timeout_seconds: int
    connect_timeout_seconds: int
    read_timeout_seconds: int

    def __repr__(self) -> str:
        safe_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() != "authorization"
        }
        return (
            "LLMHTTPRequest("
            f"method={self.method!r}, url={self.url!r}, "
            f"headers={safe_headers!r}, body_chars={len(self.body)}, "
            f"timeout_seconds={self.timeout_seconds}, "
            f"connect_timeout_seconds={self.connect_timeout_seconds}, "
            f"read_timeout_seconds={self.read_timeout_seconds})"
        )


@dataclass(frozen=True)
class LLMHTTPResponse:
    status_code: int
    body: str
    headers: dict[str, str] = field(default_factory=dict)


class LLMTransportConnectionTimeout(TimeoutError):
    """Raised by injected HTTP executors when connection setup times out."""


class LLMTransportReadTimeout(TimeoutError):
    """Raised by injected HTTP executors when response reading times out."""


class LLMTransportNetworkError(OSError):
    """Raised by injected HTTP executors for non-HTTP network failures."""


class BaseLLMTransport:
    """Base transport interface for alignment providers."""

    def generate(self, prompt: str, config: dict[str, Any], request_options: dict[str, Any] | None = None) -> LLMTransportResult:
        raise NotImplementedError


class DisabledLLMTransport(BaseLLMTransport):
    def generate(self, prompt: str, config: dict[str, Any], request_options: dict[str, Any] | None = None) -> LLMTransportResult:
        del prompt, request_options
        return LLMTransportResult(
            status="error",
            error_code="provider_disabled",
            error_message=f"External LLM provider is disabled: {config.get('provider_name', '')}",
            retry_count=0,
        )


class FakeLLMTransport(BaseLLMTransport):
    def generate(self, prompt: str, config: dict[str, Any], request_options: dict[str, Any] | None = None) -> LLMTransportResult:
        del prompt, config
        options = request_options or {}
        response_type = str(options.get("fake_response_type") or "valid").strip()
        return LLMTransportResult(
            status="success",
            raw_output=build_fixture_response(
                response_type, evidence_citations=options.get("evidence_citations")
            ),
            retry_count=0,
        )


class ReplayLLMTransport(BaseLLMTransport):
    def generate(self, prompt: str, config: dict[str, Any], request_options: dict[str, Any] | None = None) -> LLMTransportResult:
        del prompt, config
        options = request_options or {}
        response_type = str(options.get("replay_response_type") or "valid").strip()
        return LLMTransportResult(
            status="success",
            raw_output=build_fixture_response(
                response_type, evidence_citations=options.get("evidence_citations")
            ),
            retry_count=0,
        )


class UrllibLLMHTTPExecutor:
    """Small urllib executor with no retry policy."""

    def __call__(self, request: LLMHTTPRequest) -> LLMHTTPResponse:
        request_obj = urllib.request.Request(
            request.url,
            data=request.body.encode("utf-8"),
            headers=request.headers,
            method=request.method,
        )
        try:
            with urllib.request.urlopen(request_obj, timeout=request.timeout_seconds) as response:
                return LLMHTTPResponse(
                    status_code=int(getattr(response, "status", 0) or response.getcode()),
                    body=response.read().decode("utf-8", errors="replace"),
                    headers={str(key).lower(): str(value) for key, value in response.headers.items()},
                )
        except urllib.error.HTTPError as exc:
            return LLMHTTPResponse(
                status_code=int(exc.code or 0),
                body=exc.read().decode("utf-8", errors="replace"),
                headers={str(key).lower(): str(value) for key, value in exc.headers.items()},
            )
        except socket.timeout as exc:
            raise LLMTransportReadTimeout("Provider read timed out.") from exc
        except TimeoutError as exc:
            raise LLMTransportConnectionTimeout("Provider connection timed out.") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, socket.timeout):
                raise LLMTransportReadTimeout("Provider read timed out.") from exc
            raise LLMTransportNetworkError("Provider network error.") from exc


class DeepSeekHTTPTransport(BaseLLMTransport):
    """DeepSeek OpenAI-compatible chat-completions transport."""

    def __init__(
        self,
        *,
        http_executor: Callable[[LLMHTTPRequest], LLMHTTPResponse] | None = None,
        credential_resolver: Callable[[str], str] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._http_executor = http_executor or UrllibLLMHTTPExecutor()
        self._credential_resolver = credential_resolver or _resolve_env_credential
        self._clock = clock or time.monotonic

    def generate(self, prompt: str, config: dict[str, Any], request_options: dict[str, Any] | None = None) -> LLMTransportResult:
        del request_options
        started = self._clock()
        provider = str(config.get("provider_name") or llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME)
        model = str(config.get("model_name") or "").strip()
        json_object_mode = provider == llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME
        metadata = {
            "provider": provider,
            "model": model,
            "requested_model": model,
            "resolved_model": "",
            "model_policy_version": str(config.get("model_policy_version") or ""),
            "pricing_model_identity": str(config.get("pricing_model_identity") or ""),
            "response_format": (
                "json_object"
                if json_object_mode
                else ""
            ),
            "http_status": None,
            "request_count": 0,
            "retry_count": 0,
            "error_category": "",
        }
        if (
            provider in llm_provider_config.PERMANENTLY_DISABLED_PROVIDER_NAMES
            or not config.get("enabled")
            or not config.get("feature_enabled")
            or config.get("replay_mode")
        ):
            return self._error(
                "provider_disabled",
                "DeepSeek alignment provider is disabled.",
                started,
                request_count=0,
                metadata=metadata,
            )

        api_key_env_name = str(config.get("api_key_env_name") or "").strip()
        api_key = str(self._credential_resolver(api_key_env_name) or "").strip() if api_key_env_name else ""
        if not api_key:
            return self._error(
                "credential_missing",
                "DeepSeek alignment provider credential is missing.",
                started,
                request_count=0,
                metadata=metadata,
            )

        request = self._build_request(prompt, config, api_key)
        try:
            response = self._http_executor(request)
        except LLMTransportConnectionTimeout:
            return self._error("connection_timeout", "DeepSeek provider connection timed out.", started, request_count=1, metadata=metadata)
        except (LLMTransportReadTimeout, socket.timeout):
            return self._error("read_timeout", "DeepSeek provider read timed out.", started, request_count=1, metadata=metadata)
        except LLMTransportNetworkError:
            return self._error("network_error", "DeepSeek provider network error.", started, request_count=1, metadata=metadata)
        except OSError:
            return self._error("network_error", "DeepSeek provider network error.", started, request_count=1, metadata=metadata)

        status_code = int(response.status_code or 0)
        metadata["http_status"] = status_code
        metadata["request_count"] = 1
        if not 200 <= status_code < 300:
            return self._error(
                _http_error_code(status_code),
                _http_error_message(status_code),
                started,
                request_count=1,
                http_status=status_code,
                metadata=metadata,
            )

        try:
            envelope = json.loads(response.body)
        except json.JSONDecodeError:
            return self._error("invalid_json", "DeepSeek provider response was not valid JSON.", started, request_count=1, http_status=status_code, metadata=metadata)
        if not isinstance(envelope, dict):
            return self._error("malformed_provider_response", "DeepSeek provider response envelope was malformed.", started, request_count=1, http_status=status_code, metadata=metadata)

        choices = envelope.get("choices")
        if not isinstance(choices, list) or not choices:
            return self._error("malformed_provider_response", "DeepSeek provider response did not include choices.", started, request_count=1, http_status=status_code, metadata=metadata)
        first = choices[0]
        if not isinstance(first, dict) or not isinstance(first.get("message"), dict):
            return self._error("malformed_provider_response", "DeepSeek provider response choice was malformed.", started, request_count=1, http_status=status_code, metadata=metadata)
        metadata["usage"] = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else {}
        metadata["response_model"] = envelope.get("model") if isinstance(envelope.get("model"), str) else ""
        metadata["resolved_model"] = metadata["response_model"]
        metadata["finish_reason"] = first.get("finish_reason") if isinstance(first.get("finish_reason"), str) else ""
        content = first["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            return self._error("missing_response_content", "DeepSeek provider response content was missing.", started, request_count=1, http_status=status_code, metadata=metadata)
        identity = llm_provider_config.validate_response_model_identity(
            model,
            metadata["response_model"],
        )
        metadata.update(identity)
        if not identity["compatible"]:
            return self._error(
                "response_model_not_allowed",
                "DeepSeek provider response model is not allowed by the fixed model policy.",
                started,
                request_count=1,
                http_status=status_code,
                metadata=metadata,
            )
        if metadata["finish_reason"] == "length":
            return self._error(
                "response_truncated",
                "DeepSeek provider response reached the output token limit.",
                started,
                request_count=1,
                http_status=status_code,
                metadata=metadata,
            )

        return LLMTransportResult(
            status="success",
            raw_output=content,
            latency_ms=_elapsed_ms(started, self._clock),
            retry_count=0,
            request_count=1,
            metadata=metadata,
        )

    def _build_request(self, prompt: str, config: dict[str, Any], api_key: str) -> LLMHTTPRequest:
        base_url = str(config.get("base_url") or "").rstrip("/")
        model = str(config.get("model_name") or "").strip()
        timeout = llm_provider_config.normalize_provider_timeout(config.get("timeout_seconds"))
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": str(prompt or "")}],
            "stream": False,
        }
        if str(config.get("provider_name") or "") == llm_provider_config.DEEPSEEK_EXTERNAL_PROVIDER_NAME:
            payload["response_format"] = {"type": "json_object"}
            payload["max_tokens"] = max(
                llm_provider_config.MIN_ALIGNMENT_SCHEMA_OUTPUT_TOKENS,
                min(
                    int(
                        config.get("max_output_tokens")
                        or llm_provider_config.DEFAULT_MAX_OUTPUT_TOKENS
                    ),
                    4096,
                ),
            )
        return LLMHTTPRequest(
            method="POST",
            url=f"{base_url}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            body=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            timeout_seconds=timeout,
            connect_timeout_seconds=timeout,
            read_timeout_seconds=timeout,
        )

    def _error(
        self,
        error_code: str,
        error_message: str,
        started: float,
        *,
        request_count: int,
        metadata: dict[str, Any],
        http_status: int | None = None,
    ) -> LLMTransportResult:
        safe_metadata = dict(metadata)
        safe_metadata.update({
            "http_status": http_status,
            "request_count": request_count,
            "retry_count": 0,
            "error_category": error_code,
        })
        return LLMTransportResult(
            status="error",
            error_code=error_code,
            error_message=error_message,
            latency_ms=_elapsed_ms(started, self._clock),
            retry_count=0,
            request_count=request_count,
            metadata=safe_metadata,
        )


class HTTPTransport(BaseLLMTransport):
    def generate(self, prompt: str, config: dict[str, Any], request_options: dict[str, Any] | None = None) -> LLMTransportResult:
        del prompt, config, request_options
        return LLMTransportResult(
            status="error",
            error_code="provider_disabled",
            error_message="HTTP transport is not enabled in this task.",
            retry_count=0,
        )


def _resolve_env_credential(env_name: str) -> str:
    return os.environ.get(env_name, "")


def _http_error_code(status_code: int) -> str:
    if status_code in {401, 403}:
        return "authentication_failed"
    if status_code == 429:
        return "rate_limited"
    if 400 <= status_code <= 499:
        return "invalid_request"
    if 500 <= status_code <= 599:
        return "provider_server_error"
    return "network_error"


def _http_error_message(status_code: int) -> str:
    if status_code in {401, 403}:
        return "DeepSeek provider authentication failed."
    if status_code == 429:
        return "DeepSeek provider rate limited the request."
    if 400 <= status_code <= 499:
        return "DeepSeek provider rejected the request."
    if 500 <= status_code <= 599:
        return "DeepSeek provider server error."
    return "DeepSeek provider HTTP request failed."


def _elapsed_ms(started: float, clock: Callable[[], float]) -> int:
    return max(0, int((clock() - started) * 1000))


def build_fixture_response(
    response_type: str = "valid",
    *,
    evidence_citations: dict[str, Any] | None = None,
) -> str:
    if response_type == "non_json":
        return "non-json replay response"
    if response_type == "output_too_long":
        return "x" * 10000
    response = {
        "alignment_decision": "likely_aligned",
        "alignment_confidence": 0.69,
        "recommendation": "ready_for_human_review",
        "risk_labels": [
            "bilingual_alignment_not_verified",
            "candidate_not_alignment_verified",
        ],
        "evidence_assessment": {
            "english_evidence_supported": True,
            "chinese_evidence_supported": True,
            "cross_language_support": "moderate",
            "evidence_limitations": [
                "replay_fixture_only",
                "not_a_production_llm_judgment",
            ],
        },
        "term_assessment": {
            "english_term_ok": True,
            "chinese_term_ok": True,
            "candidate_ambiguity": "none",
            "notes": "Replay fixture response.",
        },
        "course_context_assessment": {
            "course_match": True,
            "chapter_match": True,
            "notes": "Replay fixture context.",
        },
        "explanation": "Replay fixture for guarded external provider parsing. This is not production output.",
        "limitations": [
            "replay_fixture_only",
            "no_external_model_called",
            "requires_human_review",
        ],
        "evidence_citations": evidence_citations or {
            "english": [{"source_uid": "fixture-en-source", "chunk_uid": "fixture-en-chunk"}],
            "chinese": [{"source_uid": "fixture-zh-source", "chunk_uid": "fixture-zh-chunk"}],
        },
    }
    if response_type == "missing_fields":
        response.pop("recommendation", None)
    elif response_type == "confidence_out_of_range":
        response["alignment_confidence"] = 1.5
    elif response_type == "insufficient_evidence":
        response.update({
            "alignment_decision": "insufficient_evidence",
            "alignment_confidence": 0.2,
            "recommendation": "insufficient_evidence",
            "risk_labels": [
                "bilingual_alignment_not_verified",
                "candidate_not_alignment_verified",
                "no_english_evidence",
                "no_chinese_evidence",
            ],
        })
        response["evidence_assessment"]["english_evidence_supported"] = False
        response["evidence_assessment"]["chinese_evidence_supported"] = False
        response["evidence_assessment"]["cross_language_support"] = "missing"
    elif response_type == "ambiguous_candidate":
        response.update({
            "alignment_decision": "uncertain",
            "alignment_confidence": 0.41,
            "recommendation": "candidate_ambiguous",
            "risk_labels": [
                "bilingual_alignment_not_verified",
                "candidate_not_alignment_verified",
                "ambiguous_chinese_candidates",
            ],
        })
        response["term_assessment"]["candidate_ambiguity"] = "high"
    return json.dumps(response, ensure_ascii=False, sort_keys=True)
