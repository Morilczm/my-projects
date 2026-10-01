"""Modular, reusable translation provider interface.

Public API:

- ``translate_term(term, context_sentence="", glossary=None, provider=None)``
- ``translate_terms_batch(terms, context_sentence="", glossary=None, provider=None)``
- ``translate_layout_blocks(blocks, glossary=None, provider=None)``
- ``register_provider(name, factory)`` to plug in additional backends

Provider selection is explicit (``provider="ollama"`` / ``TRANSLATION_PROVIDER``)
or routed (``provider="auto"`` walks ``TRANSLATION_PROVIDER_CHAIN`` in order,
recording every attempt). A glossary is the highest-trust tier: exact matches
short-circuit before any model call, and misses are injected into the model
prompt to enforce consistent terminology. Every call degrades gracefully and
never raises into the calling pipeline.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from services.layout_analysis import SKIPPED_TEXT_LAYOUT_TYPES


# --- Configuration ---------------------------------------------------------

TRANSLATION_PROVIDER_ENV = "TRANSLATION_PROVIDER"
TRANSLATION_PROVIDER_CHAIN_ENV = "TRANSLATION_PROVIDER_CHAIN"
TRANSLATION_TIMEOUT_ENV = "TRANSLATION_TIMEOUT_SECONDS"
TRANSLATION_GLOSSARY_MAX_ENTRIES_ENV = "TRANSLATION_GLOSSARY_MAX_ENTRIES"
OLLAMA_BASE_URL_ENV = "OLLAMA_BASE_URL"
OLLAMA_MODEL_ENV = "OLLAMA_MODEL"

PROVIDER_NONE = "none"
PROVIDER_OLLAMA = "ollama"
PROVIDER_AUTO = "auto"
PROVIDER_GLOSSARY = "glossary"

DEFAULT_PROVIDER_CHAIN = "ollama"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "translategemma:12b"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_GLOSSARY_MAX_ENTRIES = 25

SYSTEM_PROMPT = (
    "You are a technical translation engine for bilingual course materials. "
    "Translate the given English technical term into Simplified Chinese. "
    "Reply with the Chinese translation only: no explanations, no pinyin, "
    "no alternative translations, no punctuation at the end."
)
TEXT_SYSTEM_PROMPT = (
    "You are a technical translation engine for bilingual course materials. "
    "Translate the given English text into Simplified Chinese. "
    "Reply with the Chinese translation only: no explanations, no comments, "
    "preserve the original line structure."
)
GLOSSARY_PROMPT_HEADER = "术语表（严格统一使用该译法）："


def _env_int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _result(status, chinese_term="", provider="", model="", error="", attempted=None, glossary_hit=False):
    return {
        "status": status,
        "chinese_term": chinese_term,
        "provider": provider,
        "model": model,
        "error": error,
        "attempted": list(attempted or []),
        "glossary_hit": glossary_hit,
        "generated": True,
        "no_evidence": True,
        "provenance_type": "GENERATED_HINT",
        "eligible_as_chinese_evidence": False,
        "eligible_as_canonical_term": False,
        "eligible_for_qualification": False,
        "eligible_for_provider_readiness": False,
    }


def _finalize_result(result, provider_name):
    result = dict(result or {})
    result.setdefault("status", "translation_failed")
    result.setdefault("chinese_term", "")
    result.setdefault("provider", provider_name)
    result.setdefault("model", "")
    result.setdefault("error", "")
    result.setdefault("attempted", [])
    result.setdefault("glossary_hit", False)
    result.setdefault("generated", True)
    result.setdefault("no_evidence", True)
    result.setdefault("provenance_type", "GENERATED_HINT")
    result.setdefault("eligible_as_chinese_evidence", False)
    result.setdefault("eligible_as_canonical_term", False)
    result.setdefault("eligible_for_qualification", False)
    result.setdefault("eligible_for_provider_readiness", False)
    return result


# --- Glossary ----------------------------------------------------------------

def normalize_glossary(glossary, max_entries=None):
    """Clean an en->zh glossary mapping; non-dict input yields an empty one."""
    if not isinstance(glossary, dict):
        return {}
    limit = max_entries or _env_int(TRANSLATION_GLOSSARY_MAX_ENTRIES_ENV, DEFAULT_GLOSSARY_MAX_ENTRIES)
    limit = max(1, limit)
    normalized = {}
    for key, value in glossary.items():
        english = str(key or "").strip()
        chinese = str(value or "").strip()
        if not english or not chinese:
            continue
        normalized[english] = chinese
        if len(normalized) >= limit:
            break
    return normalized


def lookup_glossary(glossary, english_term):
    """Case-insensitive exact-match glossary lookup."""
    term = str(english_term or "").strip().lower()
    if not term:
        return ""
    for english, chinese in (glossary or {}).items():
        if english.lower() == term:
            return chinese
    return ""


def format_glossary_prompt(glossary):
    if not glossary:
        return ""
    lines = [f"{english} = {chinese}" for english, chinese in glossary.items()]
    return GLOSSARY_PROMPT_HEADER + "\n" + "\n".join(lines)


def _build_system_prompt(base_prompt, glossary):
    glossary_text = format_glossary_prompt(glossary)
    if not glossary_text:
        return base_prompt
    return f"{base_prompt}\n\n{glossary_text}"


# --- Term/text cleaning -------------------------------------------------------

def clean_translated_term(text):
    """Reduce a raw model response to a single candidate term."""
    first_line = str(text or "").strip().splitlines()[0] if str(text or "").strip() else ""
    cleaned = first_line.strip().strip('"\'`“”‘’。.;；,，')
    cleaned = re.sub(r"[。.;；,，]+$", "", cleaned).strip().strip('"\'`“”‘’')
    if not cleaned or len(cleaned) > 60:
        return ""
    return cleaned


def clean_translated_text(text):
    """Lightly clean a raw model response for longer text blocks."""
    cleaned = str(text or "").strip()
    if cleaned.startswith(("\"", "“", "`")) and cleaned.endswith(("\"", "”", "`")) and len(cleaned) > 1:
        cleaned = cleaned[1:-1].strip()
    if not cleaned or len(cleaned) > 4000:
        return ""
    return cleaned


def normalize_provider_name(value):
    provider = (value or PROVIDER_NONE).strip().lower()
    if provider in {"", "none", "off", "disabled"}:
        return PROVIDER_NONE
    return provider


# --- Providers -----------------------------------------------------------------

class TranslationProvider:
    provider_name = "none"

    def is_available(self):
        return False

    def translate_term(self, english_term, context_sentence="", glossary=None):
        return _result(
            "translation_unavailable",
            provider=self.provider_name,
            error="No translation provider is configured.",
        )

    def translate_text(self, text, context_sentence="", glossary=None):
        return self.translate_term(text, context_sentence=context_sentence, glossary=glossary)


class NoneTranslationProvider(TranslationProvider):
    provider_name = PROVIDER_NONE


class OllamaTranslationProvider(TranslationProvider):
    provider_name = PROVIDER_OLLAMA

    def __init__(self, base_url=None, model=None):
        self.base_url = (base_url or os.environ.get(OLLAMA_BASE_URL_ENV, DEFAULT_OLLAMA_BASE_URL)).rstrip("/")
        self.model = (model or os.environ.get(OLLAMA_MODEL_ENV, DEFAULT_OLLAMA_MODEL)).strip()
        self.timeout_seconds = max(3, min(_env_int(TRANSLATION_TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS), 120))

    def _urlopen_json(self, request, timeout):
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def is_available(self):
        request = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            payload = self._urlopen_json(request, timeout=min(3, self.timeout_seconds))
        except (urllib.error.URLError, OSError, ValueError):
            return False
        models = {str(item.get("name", "")) for item in payload.get("models", []) or []}
        if not models:
            return False
        if self.model in models:
            return True
        # Allow tags without an explicit ":latest" suffix mismatch.
        return any(name.split(":")[0] == self.model.split(":")[0] for name in models)

    def _chat(self, system_prompt, user_content):
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
            "options": {"temperature": 0},
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        raw = self._urlopen_json(request, timeout=self.timeout_seconds)
        return (raw.get("message") or {}).get("content", "")

    def _translate(self, text, context_sentence, glossary, system_prompt, cleaner, empty_error):
        if not self.is_available():
            return _result(
                "translation_unavailable",
                provider=self.provider_name,
                model=self.model,
                error=f"Ollama server or model '{self.model}' is not available at {self.base_url}.",
            )

        user_content = text
        context = str(context_sentence or "").strip()
        if context:
            user_content = f"{text}\n\nContext sentence (for disambiguation only): {context[:500]}"

        try:
            content = self._chat(_build_system_prompt(system_prompt, glossary or {}), user_content)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return _result(
                "translation_failed",
                provider=self.provider_name,
                model=self.model,
                error=f"Ollama translation request failed: {exc}",
            )

        chinese = cleaner(content)
        if not chinese:
            return _result(
                "translation_failed",
                provider=self.provider_name,
                model=self.model,
                error=empty_error,
            )

        return _result("ok", chinese_term=chinese, provider=self.provider_name, model=self.model)

    def translate_term(self, english_term, context_sentence="", glossary=None):
        term = str(english_term or "").strip()
        if not term:
            return _result(
                "translation_failed",
                provider=self.provider_name,
                model=self.model,
                error="Empty English term.",
            )
        return self._translate(
            term,
            context_sentence,
            glossary,
            SYSTEM_PROMPT,
            clean_translated_term,
            "Ollama returned an empty or unusable translation.",
        )

    def translate_text(self, text, context_sentence="", glossary=None):
        content = str(text or "").strip()
        if not content:
            return _result(
                "translation_failed",
                provider=self.provider_name,
                model=self.model,
                error="Empty source text.",
            )
        return self._translate(
            content,
            context_sentence,
            glossary,
            TEXT_SYSTEM_PROMPT,
            clean_translated_text,
            "Ollama returned an empty or unusable translation.",
        )


# --- Provider registry ----------------------------------------------------------

_PROVIDER_REGISTRY = {
    PROVIDER_OLLAMA: OllamaTranslationProvider,
}


def register_provider(name, factory):
    """Register an additional translation backend.

    ``factory`` is a zero-argument callable returning a ``TranslationProvider``.
    Reserved names (none/auto/glossary) cannot be overridden.
    """
    provider = normalize_provider_name(name)
    if provider in {PROVIDER_NONE, PROVIDER_AUTO, PROVIDER_GLOSSARY}:
        raise ValueError(f"Provider name is reserved: {provider}.")
    if not callable(factory):
        raise ValueError("Provider factory must be callable.")
    _PROVIDER_REGISTRY[provider] = factory
    return provider


def get_translation_provider(name=None):
    provider = normalize_provider_name(name or os.environ.get(TRANSLATION_PROVIDER_ENV, PROVIDER_NONE))
    factory = _PROVIDER_REGISTRY.get(provider)
    if factory is None:
        return NoneTranslationProvider()
    return factory()


def parse_provider_chain(value):
    """Parse an ordered provider chain, dropping blanks and unknown names."""
    chain = []
    for item in str(value or "").split(","):
        provider = normalize_provider_name(item)
        if provider in _PROVIDER_REGISTRY and provider not in chain:
            chain.append(provider)
    return chain


# --- Routing ---------------------------------------------------------------------

def _requested_provider(provider):
    return normalize_provider_name(
        provider if provider is not None else os.environ.get(TRANSLATION_PROVIDER_ENV, PROVIDER_NONE)
    )


def _translate_term_single(english_term, context_sentence, requested, glossary, resolved=None):
    try:
        instance = resolved if resolved is not None else get_translation_provider(requested)
        return _finalize_result(
            instance.translate_term(english_term, context_sentence, glossary=glossary),
            requested,
        )
    except Exception as exc:  # defensive: translation must never break the calling pipeline
        return _result(
            "translation_failed",
            provider=requested,
            error=f"Translation provider raised unexpectedly: {exc}",
        )


def _translate_term_auto(english_term, context_sentence, glossary):
    chain = parse_provider_chain(os.environ.get(TRANSLATION_PROVIDER_CHAIN_ENV, DEFAULT_PROVIDER_CHAIN))
    if not chain:
        return _result(
            "translation_unavailable",
            provider=PROVIDER_AUTO,
            error="Translation provider chain is empty.",
            attempted=[],
        )

    attempted = []
    errors = []
    for name in chain:
        attempted.append(name)
        result = _translate_term_single(english_term, context_sentence, name, glossary)
        if result.get("status") == "ok" and result.get("chinese_term"):
            result["attempted"] = attempted
            return result
        errors.append(f"{name}: {result.get('error') or result.get('status')}")

    return _result(
        "translation_unavailable",
        provider=PROVIDER_AUTO,
        error="; ".join(errors) or "No translation provider in the chain succeeded.",
        attempted=attempted,
    )


# --- Public API -------------------------------------------------------------------

def translate_term(english_term, context_sentence="", glossary=None, provider=None):
    """Translate one English term, degrading gracefully.

    Glossary exact matches short-circuit before any model call. With
    ``provider="auto"`` the chain from ``TRANSLATION_PROVIDER_CHAIN`` is tried
    in order and the first successful translation wins. Never raises.
    """
    normalized_glossary = normalize_glossary(glossary)
    hit = lookup_glossary(normalized_glossary, english_term)
    if hit:
        return _result("ok", chinese_term=hit, provider=PROVIDER_GLOSSARY, glossary_hit=True)

    requested = _requested_provider(provider)
    if requested == PROVIDER_AUTO:
        return _translate_term_auto(english_term, context_sentence, normalized_glossary)
    if requested != PROVIDER_NONE and requested not in _PROVIDER_REGISTRY:
        return _result(
            "translation_unavailable",
            error=f"Unknown translation provider: {requested}.",
        )
    return _translate_term_single(english_term, context_sentence, requested, normalized_glossary)


def translate_terms_batch(terms, context_sentence="", glossary=None, provider=None):
    """Translate several terms, sharing one provider instance when possible."""
    normalized_glossary = normalize_glossary(glossary)
    requested = _requested_provider(provider)
    resolved = None
    if requested != PROVIDER_AUTO and requested in _PROVIDER_REGISTRY:
        resolved = get_translation_provider(requested)

    results = []
    for term in terms or []:
        hit = lookup_glossary(normalized_glossary, term)
        if hit:
            results.append(_result("ok", chinese_term=hit, provider=PROVIDER_GLOSSARY, glossary_hit=True))
            continue
        if resolved is not None:
            results.append(_translate_term_single(term, context_sentence, requested, normalized_glossary, resolved=resolved))
        else:
            results.append(translate_term(term, context_sentence=context_sentence, glossary=normalized_glossary, provider=requested))
    return results


def translate_layout_blocks(blocks, glossary=None, provider=None):
    """Translate the text of layout blocks, preserving structure.

    Blocks whose ``layout_type`` is in ``SKIPPED_TEXT_LAYOUT_TYPES``
    (headers/footers, page numbers, figures, formulas) are passed through
    untranslated with ``skipped=True``. Never raises: when no provider is
    available every block is returned untranslated.
    """
    normalized_glossary = normalize_glossary(glossary)
    requested = _requested_provider(provider)
    resolved = None
    if requested != PROVIDER_AUTO and requested in _PROVIDER_REGISTRY:
        try:
            candidate = get_translation_provider(requested)
            if candidate.is_available():
                resolved = candidate
        except Exception:
            resolved = None

    translated = []
    for block in blocks or []:
        layout_type = getattr(block, "layout_type", "text")
        source_text = str(getattr(block, "text", "") or "")
        entry = {
            "page_number": getattr(block, "page_number", None),
            "reading_order": getattr(block, "reading_order", 0),
            "layout_type": layout_type,
            "source_text": source_text,
            "translated_text": "",
            "provider": "",
            "skipped": True,
        }

        if layout_type in SKIPPED_TEXT_LAYOUT_TYPES or not source_text.strip():
            translated.append(entry)
            continue

        hit = lookup_glossary(normalized_glossary, source_text)
        if hit:
            entry.update({"translated_text": hit, "provider": PROVIDER_GLOSSARY, "skipped": False})
            translated.append(entry)
            continue

        if resolved is not None:
            try:
                result = _finalize_result(
                    resolved.translate_text(source_text, glossary=normalized_glossary),
                    requested,
                )
            except Exception as exc:
                result = _result("translation_failed", provider=requested, error=str(exc))
        else:
            result = translate_term(source_text, glossary=normalized_glossary, provider=requested)

        if result.get("status") == "ok" and result.get("chinese_term"):
            entry.update({
                "translated_text": result["chinese_term"],
                "provider": result.get("provider", ""),
                "skipped": False,
            })
        translated.append(entry)

    return translated
