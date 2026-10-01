"""Unified AI provider execution layer for LexiBridge AI."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .ai_registry import ProviderSelection


class BaseAIProvider:
    provider_name = "none"
    provider_mode = "none"
    is_real_provider = False

    def __init__(self, selection: ProviderSelection):
        self.selection = selection

    def call(self, task_type, prompt_text, input_payload, json_schema=None):
        return {
            "status": "error",
            "error_code": "AI_PROVIDER_NOT_CONFIGURED",
            "message": "AI provider is not configured.",
        }


class NoneAIProvider(BaseAIProvider):
    provider_name = "none"
    provider_mode = "none"


class MockAIProvider(BaseAIProvider):
    provider_name = "mock"
    provider_mode = "mock"

    def call(self, task_type, prompt_text, input_payload, json_schema=None):
        if task_type == "term_extraction":
            text = json.dumps(input_payload, ensure_ascii=False)
            terms = []
            for phrase in ["Fourier Transform", "Convolution", "Hash Table", "Angular Frequency", "Wavelength"]:
                if phrase.lower() in text.lower():
                    terms.append({
                        "english_term": phrase,
                        "context_sentence": "",
                        "reason": "Mock deterministic extraction.",
                        "confidence": 60,
                    })
            result = {"terms": terms}
        elif task_type == "term_alignment":
            english_term = str(input_payload.get("english_term", "")).strip()
            hint = str(input_payload.get("translation_candidate_hint", "")).strip() or english_term
            result = {
                "alignment_status": "unverified_translation",
                "candidate_chinese_term": hint,
                "concept_explanation": "Mock AI result for local demonstration only.",
                "alignment_reason": "Mock provider cannot verify semantic equivalence.",
                "ai_confidence": 0.45,
                "risk_flags": ["mock_ai"],
                "requires_human_review": True,
            }
        else:
            result = {
                "classification": "teacher_review_needed",
                "root_cause": "unknown",
                "severity": "medium",
                "summary": "Mock provider result.",
                "risk_flags": ["mock_ai"],
            }
        return {"status": "success", "result": result}


class LocalHeuristicAIProvider(MockAIProvider):
    provider_name = "local_heuristic"
    provider_mode = "local_heuristic"

    def call(self, task_type, prompt_text, input_payload, json_schema=None):
        response = super().call(task_type, prompt_text, input_payload, json_schema=json_schema)
        if response.get("status") == "success":
            result = response.setdefault("result", {})
            flags = list(result.get("risk_flags", []) or [])
            if "local_heuristic_ai" not in flags:
                flags.append("local_heuristic_ai")
            if "mock_ai" in flags:
                flags.remove("mock_ai")
            result["risk_flags"] = flags
            if task_type == "term_alignment":
                result["alignment_reason"] = "Local heuristic fallback; requires human review."
                result["requires_human_review"] = True
        return response


class OpenAICompatibleProvider(BaseAIProvider):
    provider_name = "custom_openai_compatible"
    provider_mode = "live"
    is_real_provider = True

    def call(self, task_type, prompt_text, input_payload, json_schema=None):
        if not self.selection.api_key:
            return {
                "status": "error",
                "error_code": "AI_PROVIDER_NOT_CONFIGURED",
                "message": "AI provider API key is missing.",
            }
        payload = {
            "model": self.selection.model_name,
            "messages": [
                {"role": "system", "content": prompt_text},
                {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "stream": False,
            "response_format": {"type": "json_object"},
        }
        url = self.selection.base_url.rstrip("/") + "/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.selection.api_key}",
            },
            method="POST",
        )
        last_error = None
        for attempt in range(self.selection.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.selection.timeout_seconds) as response:
                    raw = json.loads(response.read().decode("utf-8"))
                content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
                if not content:
                    return {"status": "error", "error_code": "AI_INVALID_RESPONSE", "message": "Empty AI response."}
                try:
                    result = json.loads(content)
                except json.JSONDecodeError:
                    start = content.find("{")
                    end = content.rfind("}")
                    if start == -1 or end <= start:
                        return {"status": "error", "error_code": "AI_INVALID_RESPONSE", "message": "AI response is not JSON."}
                    result = json.loads(content[start:end + 1])
                return {"status": "success", "result": result}
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.selection.max_retries:
                    time.sleep(min(3, 0.5 * (attempt + 1)))
        return {
            "status": "error",
            "error_code": "AI_PROVIDER_FAILED",
            "message": f"AI provider request failed: {last_error}",
        }


class DeepSeekAIProvider(OpenAICompatibleProvider):
    provider_name = "deepseek"


class OpenAIProvider(OpenAICompatibleProvider):
    provider_name = "openai"


def provider_from_selection(selection: ProviderSelection):
    mode = selection.provider_mode
    provider = selection.provider_name
    if mode == "none" or provider == "none":
        return NoneAIProvider(selection)
    if mode == "mock" or provider == "mock":
        return MockAIProvider(selection)
    if mode == "local_heuristic" or provider == "local_heuristic":
        return LocalHeuristicAIProvider(selection)
    if provider == "deepseek":
        return DeepSeekAIProvider(selection)
    if provider == "openai":
        return OpenAIProvider(selection)
    return OpenAICompatibleProvider(selection)
